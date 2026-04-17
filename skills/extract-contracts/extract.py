#!/usr/bin/env python3
"""Extract behavioral contracts from source code using LLM inference.

Reads a skeleton spec.json (produced by M1 discover), enriches each element
with a behavioral contract by querying greploom for context, then writes
the enriched spec back in-place.
"""

import argparse
import json
import subprocess
from datetime import datetime, timezone

import requests


# --System prompt
# --

SYSTEM_PROMPT = """\
You are a code analysis expert extracting behavioral contracts from source code. \
A behavioral contract describes WHAT code does (observable behavior), not HOW \
(implementation details). These contracts will be used to verify that translated \
code preserves the same behavior.

Produce a JSON contract with these fields:
- purpose: One paragraph. State what the element does, its role in the module, \
and when/why a caller would use it (vs alternatives).
- preconditions: Array of strings. Specific parameter type constraints, required \
state, value ranges. Name the actual parameters and types.
- postconditions: Array of strings. Specific return types, guaranteed properties \
of the return value, state changes. Name the actual return type.
- invariants: Array of strings. Be SPECIFIC — not "input is not modified" but \
"token processing is single-pass left-to-right" or "disambiguation is \
deterministic given the same dayfirst/yearfirst settings". Invariants should \
describe properties a test could verify.
- side_effects: Array of strings. Use ["None. Pure function."] for pure functions.
- error_conditions: Array of {condition, behavior, severity} objects. \
severity is one of: fatal, recoverable, advisory. Name the exact exception class.
- trust_boundary: {input_trust, output_trust, sanitization}. \
input_trust/output_trust: trusted, untrusted, mixed, n/a. \
For sanitization, describe HOW the element validates/sanitizes input — \
not just "validates input" but "tokenizes input into discrete tokens, matches \
each against known patterns, no eval or dynamic code execution". Say "None" \
only if the element truly performs no validation.
- thread_safety: String. Omit the field entirely if not relevant.
- performance: String. Omit the field entirely if not relevant.

CRITICAL RULES:
1. Security findings listed in the prompt MUST appear in error_conditions and \
trust_boundary. If a CVE is mentioned, add an error_condition for the attack \
vector with severity "fatal" and reference the CVE ID.
2. All array items (preconditions, postconditions, invariants, side_effects) \
must be plain strings, NOT objects.
3. Do not include fields with null values. Omit optional fields instead.
4. Base your analysis ONLY on the source code provided. Do not infer behavior \
from the element name alone.

Respond with ONLY valid JSON. No markdown fencing, no explanation.\
"""


# --CLI
# --

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enrich a skeleton spec.json with LLM-extracted behavioral contracts."
    )
    parser.add_argument("--spec", required=True,
                        help="Path to skeleton spec.json (modified in-place).")
    parser.add_argument("--greploom-db", required=True,
                        help="Path to greploom.db (semantic index).")
    parser.add_argument("--cpg", required=True,
                        help="Path to cpg.json (code property graph).")
    parser.add_argument("--llm-endpoint", required=True,
                        help="OpenAI-compatible API base URL.")
    parser.add_argument("--llm-model", default="default",
                        help="Model name for API calls (default: 'default').")
    parser.add_argument("--scope",
                        help="Only extract elements whose ID starts with this prefix.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show extraction plan without calling LLM.")
    parser.add_argument("--max-group-size", type=int, default=6,
                        help="Max methods per class group before splitting (default: 6).")
    parser.add_argument("--concurrency", type=int, default=4,
                        help="Max parallel LLM calls (default: 4; currently sequential).")
    return parser.parse_args()


# --Spec I/O
# --

def load_spec(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# --Scope filtering
# --

def filter_elements(elements: dict, scope: str) -> dict:
    """Return only elements in scope.

    An element is in scope if its own ID or any ancestor in the parent chain
    starts with the scope prefix. Walks the full chain to handle deeply nested
    elements (e.g. module → class → inner class → method).
    """
    result = {}
    for eid, elem in elements.items():
        if eid.startswith(scope):
            result[eid] = elem
            continue
        # Walk the parent chain up to the root.
        ancestor_id = elem.get("parent", "")
        while ancestor_id:
            if ancestor_id.startswith(scope):
                result[eid] = elem
                break
            ancestor_id = elements.get(ancestor_id, {}).get("parent", "")
    return result


# --Element grouping
# --

def group_elements(elements: dict, max_group_size: int = 6) -> list[dict]:
    """Group class methods with their parent class.

    Each group is one of:
      {"type": "class", "class_id": str, "member_ids": [str], "all_ids": [str]}
      {"type": "single", "element_id": str}

    A function is grouped with its parent class when its parent starts with
    "cls:". Modules and standalone functions (parent starts with "mod:") are
    singles. A class with no methods in scope is also a single.

    Classes with more than max_group_size methods are split: the class itself
    becomes a single, and each method becomes a single. This keeps prompts
    small enough for remote LLM endpoints.
    """
    class_members: dict[str, list[str]] = {}  # class_id -> [method_ids]
    class_ids: set[str] = set()
    grouped_methods: set[str] = set()

    # First pass: identify classes and collect their in-scope methods.
    for eid, elem in elements.items():
        if elem.get("hierarchy_level") == "class":
            class_ids.add(eid)
            class_members.setdefault(eid, [])

    for eid, elem in elements.items():
        if elem.get("hierarchy_level") == "function":
            parent = elem.get("parent", "")
            if parent.startswith("cls:") and parent in class_ids:
                class_members[parent].append(eid)
                grouped_methods.add(eid)

    groups: list[dict] = []

    # Emit class groups or split oversized ones.
    for cid in class_ids:
        members = class_members[cid]
        if not members:
            groups.append({"type": "single", "element_id": cid})
        elif len(members) <= max_group_size:
            groups.append({
                "type": "class",
                "class_id": cid,
                "member_ids": members,
                "all_ids": [cid] + members,
            })
        else:
            # Too many methods — extract class and each method individually.
            groups.append({"type": "single", "element_id": cid})
            for mid in members:
                groups.append({"type": "single", "element_id": mid})

    # Emit singles: modules and standalone functions.
    for eid, elem in elements.items():
        if eid in class_ids or eid in grouped_methods:
            continue
        groups.append({"type": "single", "element_id": eid})

    return groups


# --Greploom
# --

def query_greploom(node_ref: str, db_path: str, cpg_path: str) -> list[dict]:
    """Query greploom for source code and structural context.

    Returns the results list from greploom JSON output.
    """
    cmd = [
        "greploom", "query",
        "--db", str(db_path),
        "--cpg", str(cpg_path),
        "--node", node_ref,
        "--include-source",
        "--format", "json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"greploom query failed: {result.stderr.strip()}")
    data = json.loads(result.stdout)
    return data.get("results", [])


# --Security findings
# --

def get_security_findings(spec: dict, file_path: str) -> list[dict]:
    """Return security findings relevant to the given file.

    Uses suffix matching because findings may use short paths
    (``parser/_parser.py``) while elements use full paths
    (``src/dateutil/parser/_parser.py``).
    """
    if not file_path:
        return []
    findings = spec.get("security_findings", [])
    matched = []
    for f in findings:
        f_file = f.get("file", "")
        if f_file and (f_file == file_path or file_path.endswith(f_file)
                       or f_file.endswith(file_path)):
            matched.append(f)
        elif file_path in f.get("location", ""):
            matched.append(f)
    return matched


def get_ecosystem_cves(spec: dict) -> str:
    """Format known CVEs from ecosystem_dependencies for inclusion in prompts."""
    deps = spec.get("ecosystem_dependencies", [])
    lines = []
    for dep in deps:
        for cve in dep.get("cves", []):
            cve_id = cve.get("id", "")
            summary = cve.get("summary", "")
            severity = cve.get("severity", "")
            if cve_id:
                lines.append(f"- {cve_id} ({severity}): {summary}")
    if not lines:
        return ""
    return "Known CVEs for this codebase:\n" + "\n".join(lines)


def format_findings_section(findings: list[dict]) -> str:
    """Format security findings for inclusion in an LLM prompt."""
    if not findings:
        return ""
    lines = ["Relevant security findings:"]
    for f in findings:
        fid = f.get("id", f.get("rule_id", "unknown"))
        title = f.get("title", f.get("rule_id", ""))
        sev = f.get("severity", "unknown")
        desc = f.get("description", f.get("message", ""))
        lines.append(f"- {fid}: {title} (severity: {sev}) — {desc}")
    return "\n".join(lines)


# --Prompt builders
# --

def _format_context(context_results: list[dict]) -> tuple[str, str]:
    """Format greploom results into (source_code, structural_context).

    Greploom returns a ``text`` field per result containing formatted
    markdown with embedded source code and structural info. The first
    result (relationship=="hit") carries the primary source; remaining
    results provide callers, callees, and parameters.
    """
    hit_text = ""
    related_parts = []
    for r in context_results:
        text = r.get("text", "")
        if not text:
            continue
        rel = r.get("relationship", "")
        if rel == "hit" or not hit_text:
            hit_text = text
        else:
            related_parts.append(text)

    source_code = hit_text if hit_text else "(source not available)"
    structural_context = "\n\n".join(related_parts) if related_parts else "(no additional structural context)"
    return source_code, structural_context


def build_prompt_single(element_id: str, element: dict,
                        context_results: list[dict],
                        findings_section: str) -> str:
    source_code, structural_context = _format_context(context_results)
    parts = [
        f"Extract the behavioral contract for the following {element.get('hierarchy_level', 'element')}.",
        "",
        f"Element: {element_id}",
        f"File: {element.get('file', 'unknown')}",
        f"Line: {element.get('line', 'unknown')}",
        "",
        "Source code:",
        "```",
        source_code,
        "```",
        "",
        "Structural context:",
        structural_context,
    ]
    if findings_section:
        parts += ["", "IMPORTANT — " + findings_section,
                  "", "You MUST incorporate these findings into the contract's "
                  "error_conditions and trust_boundary fields."]
    parts += ["", "Respond with a single JSON object containing the contract fields."]
    return "\n".join(parts)


def build_prompt_class(class_id: str, member_ids: list[str],
                       elements: dict,
                       context_results: list[dict],
                       findings_section: str) -> str:
    source_code, structural_context = _format_context(context_results)
    all_ids = [class_id] + member_ids
    id_list = "\n".join(f"  - {eid}" for eid in all_ids)
    parts = [
        "Extract behavioral contracts for the following class and its methods.",
        "",
        "Elements:",
        id_list,
        "",
        "Source code:",
        "```",
        source_code,
        "```",
        "",
        "Structural context:",
        structural_context,
    ]
    if findings_section:
        parts += ["", "IMPORTANT — " + findings_section,
                  "", "You MUST incorporate these findings into the contract's "
                  "error_conditions and trust_boundary fields."]
    parts += [
        "",
        "Respond with a JSON object where each key is an element ID and each "
        "value is the contract for that element.",
    ]
    return "\n".join(parts)


# --LLM call
# --

def resolve_model_name(endpoint: str) -> str:
    """Query /v1/models to get the served model ID."""
    url = f"{endpoint.rstrip('/')}/v1/models"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    models = resp.json().get("data", [])
    if not models:
        raise RuntimeError(f"No models served at {endpoint}")
    return models[0]["id"]


def call_llm(endpoint: str, model: str,
             system_prompt: str, user_prompt: str,
             timeout: int = 180, retries: int = 2) -> str:
    """Call OpenAI-compatible chat completions API.

    No API key is needed for on-premise vLLM endpoints.
    Retries on connection errors with exponential backoff.
    Returns the raw text content of the response.
    """
    import time as _time

    url = f"{endpoint.rstrip('/')}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 4096,
    }
    last_err = None
    for attempt in range(1 + retries):
        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            if attempt < retries:
                wait = 5 * (2 ** attempt)
                _time.sleep(wait)
    raise last_err


# --Response parsing & validation
# --

def parse_contract_response(raw_text: str,
                            expected_ids: "str | list[str] | None" = None
                            ) -> dict[str, dict]:
    """Parse LLM response into {element_id: contract} mapping.

    Strips markdown fencing if present. For single-element calls, expected_ids
    is the element ID string. For class groups, it is the list of all IDs.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    parsed = json.loads(text)

    if isinstance(expected_ids, str):
        return {expected_ids: validate_contract(parsed)}

    if isinstance(expected_ids, list) and isinstance(parsed, dict):
        result = {}
        for eid in expected_ids:
            if eid in parsed:
                result[eid] = validate_contract(parsed[eid])
        return result

    return {}


def _stringify_array(items: list) -> list[str]:
    """Coerce array items to strings. LLMs sometimes return objects."""
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # Flatten dict fields into a readable string.
            parts = [f"{v}" for v in item.values() if v]
            result.append(": ".join(parts) if parts else str(item))
        else:
            result.append(str(item))
    return result


def validate_contract(contract: dict) -> dict:
    """Validate and normalise contract field types."""
    VALID_FIELDS = {
        "purpose", "preconditions", "postconditions", "invariants",
        "side_effects", "error_conditions", "state_transitions",
        "trust_boundary", "thread_safety", "performance",
    }
    cleaned = {k: v for k, v in contract.items() if k in VALID_FIELDS}

    # Drop null/None values for optional string fields.
    for field in ("thread_safety", "performance"):
        if field in cleaned and cleaned[field] is None:
            del cleaned[field]

    # Coerce string-or-array fields to arrays of strings.
    for field in ("preconditions", "postconditions", "invariants", "side_effects"):
        if field in cleaned:
            val = cleaned[field]
            if isinstance(val, str):
                cleaned[field] = [val]
            elif isinstance(val, list):
                cleaned[field] = _stringify_array(val)
            elif isinstance(val, dict):
                # LLM returned a dict instead of array — flatten.
                cleaned[field] = [f"{k}: {v}" for k, v in val.items() if v]
            else:
                cleaned[field] = [str(val)]

    if "trust_boundary" in cleaned:
        tb = cleaned["trust_boundary"]
        if isinstance(tb, dict):
            valid_trust = {"trusted", "untrusted", "mixed", "n/a"}
            for key in ("input_trust", "output_trust"):
                if key in tb and tb[key] not in valid_trust:
                    tb[key] = "mixed"
            # Drop null sanitization.
            if tb.get("sanitization") is None:
                del tb["sanitization"]

    if "error_conditions" in cleaned:
        valid_severity = {"fatal", "recoverable", "advisory"}
        valid_ec_keys = {"condition", "behavior", "severity"}
        normalized = []
        for ec in cleaned["error_conditions"]:
            if isinstance(ec, dict):
                # Strip unknown keys (e.g. exception_class).
                ec = {k: v for k, v in ec.items() if k in valid_ec_keys}
                if "severity" in ec and ec["severity"] not in valid_severity:
                    del ec["severity"]
                normalized.append(ec)
        cleaned["error_conditions"] = normalized

    return cleaned


# --Metadata update
# --

def update_element_metadata(element: dict, model_name: str) -> None:
    element["metadata"] = {
        "confidence": "medium",
        "source": "llm_inference",
        "status": "needs_review",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": f"extract-contracts/{model_name}",
    }


# --Group extraction
# --

def extract_group(group: dict, spec: dict,
                  greploom_db: str, cpg_path: str,
                  llm_endpoint: str, llm_model: str,
                  system_prompt: str) -> tuple[int, int, list[str]]:
    """Extract contracts for one group (single element or class+methods).

    Returns (successes, failures, error_messages).
    """
    elements = spec["elements"]

    # Ecosystem CVE context (same for all elements in the spec).
    cve_section = get_ecosystem_cves(spec)

    if group["type"] == "single":
        eid = group["element_id"]
        elem = elements[eid]

        context_results = query_greploom(elem["node_ref"], greploom_db, cpg_path)
        findings = get_security_findings(spec, elem.get("file", ""))
        findings_section = format_findings_section(findings)
        if cve_section:
            findings_section = (findings_section + "\n\n" + cve_section
                                if findings_section else cve_section)

        user_prompt = build_prompt_single(eid, elem, context_results, findings_section)
        raw = call_llm(llm_endpoint, llm_model, system_prompt, user_prompt)
        contracts = parse_contract_response(raw, expected_ids=eid)

        if eid in contracts:
            elem["contract"] = contracts[eid]
            update_element_metadata(elem, llm_model)
            return 1, 0, []
        return 0, 1, [f"{eid}: contract not found in LLM response"]

    # Class group
    class_id = group["class_id"]
    all_ids = group["all_ids"]
    class_elem = elements[class_id]

    context_results = query_greploom(class_elem["node_ref"], greploom_db, cpg_path)
    findings = get_security_findings(spec, class_elem.get("file", ""))
    findings_section = format_findings_section(findings)
    if cve_section:
        findings_section = (findings_section + "\n\n" + cve_section
                            if findings_section else cve_section)

    user_prompt = build_prompt_class(
        class_id, group["member_ids"], elements, context_results, findings_section
    )
    raw = call_llm(llm_endpoint, llm_model, system_prompt, user_prompt)
    contracts = parse_contract_response(raw, expected_ids=all_ids)

    successes, failures, errors = 0, 0, []
    for eid in all_ids:
        if eid in contracts:
            elements[eid]["contract"] = contracts[eid]
            update_element_metadata(elements[eid], llm_model)
            successes += 1
        else:
            failures += 1
            errors.append(f"{eid}: missing from class group response")

    return successes, failures, errors


# --Entry point
# --

def main() -> None:
    args = parse_args()
    spec = load_spec(args.spec)
    elements = spec["elements"]

    # Resolve model name from endpoint if not specified.
    if args.llm_model == "default":
        args.llm_model = resolve_model_name(args.llm_endpoint)
        print(f"Resolved model: {args.llm_model}")

    if args.scope:
        in_scope = filter_elements(elements, args.scope)
        print(f"Scope '{args.scope}': {len(in_scope)} elements (of {len(elements)} total)")
    else:
        in_scope = elements
        print(f"Full scope: {len(in_scope)} elements")

    groups = group_elements(in_scope, max_group_size=args.max_group_size)
    n_class = sum(1 for g in groups if g["type"] == "class")
    n_single = sum(1 for g in groups if g["type"] == "single")
    print(f"Grouped into {len(groups)} extraction units "
          f"({n_class} class groups, {n_single} singles)")

    if args.dry_run:
        for g in groups:
            if g["type"] == "class":
                print(f"  CLASS:  {g['class_id']} + {len(g['member_ids'])} methods")
            else:
                print(f"  SINGLE: {g['element_id']}")
        print("\nDry run — no LLM calls made.")
        return

    total_success, total_fail, all_errors = 0, 0, []

    for i, group in enumerate(groups, 1):
        label = group.get("class_id") or group.get("element_id")
        print(f"[{i}/{len(groups)}] Extracting {label}...", end=" ", flush=True)
        try:
            s, f, errs = extract_group(
                group, spec,
                args.greploom_db, args.cpg,
                args.llm_endpoint, args.llm_model,
                SYSTEM_PROMPT,
            )
            total_success += s
            total_fail += f
            all_errors.extend(errs)
            if f == 0:
                print(f"ok ({s} extracted)")
            else:
                print(f"partial ({s} ok, {f} failed)")
        except Exception as exc:
            n = len(group.get("all_ids", [group.get("element_id")]))
            total_fail += n
            all_errors.append(f"{label}: {exc}")
            print(f"FAILED: {exc}")

    with open(args.spec, "w") as fh:
        json.dump(spec, fh, indent=2)
        fh.write("\n")

    print(f"\nDone. {total_success} contracts extracted, {total_fail} failures.")
    if all_errors:
        print("Errors:")
        for err in all_errors:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
