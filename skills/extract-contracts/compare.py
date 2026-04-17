#!/usr/bin/env python3
"""Compare LLM-extracted contracts against hand-crafted gold-standard contracts.

Reads two spec.json files and produces a field-by-field comparison for each
element that appears in both specs (with optional ID remapping).
"""

import argparse
import json
import re
import sys


# --Stopwords for keyword overlap
# --

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "that", "this",
    "it", "its", "not", "no", "if", "then", "each", "any", "all", "also",
    "than", "into", "via", "per", "whether", "only", "when",
}

ARRAY_FIELDS = (
    "preconditions", "postconditions", "invariants",
    "side_effects", "error_conditions",
)
TRUST_KEYS = ("input_trust", "output_trust", "sanitization")


# --CLI
# --

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare LLM-extracted contracts against hand-crafted gold-standard contracts."
    )
    parser.add_argument("--extracted", required=True,
                        help="spec.json with LLM-extracted contracts.")
    parser.add_argument("--reference", required=True,
                        help="spec.json with hand-crafted contracts (gold standard).")
    parser.add_argument("--id-map", action="append", default=[], metavar="KEY=VAL",
                        help="Map extracted element ID to reference element ID. Repeatable.")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="Output format (default: text).")
    return parser.parse_args()


def parse_id_map(raw: list[str]) -> dict[str, str]:
    result = {}
    for item in raw:
        if "=" not in item:
            print(f"WARNING: ignoring malformed --id-map entry (no '='): {item}",
                  file=sys.stderr)
            continue
        k, _, v = item.partition("=")
        result[k.strip()] = v.strip()
    return result


# --Helpers
# --

def load_spec(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def keywords(text: str) -> set[str]:
    """Return significant lowercase words from a string."""
    words = re.findall(r"[a-z]+", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 2}


def keyword_overlap(a: str, b: str) -> tuple[int, int]:
    """Return (overlap_count, reference_word_count)."""
    ref_kw = keywords(b)
    ext_kw = keywords(a)
    if not ref_kw:
        return 0, 0
    return len(ref_kw & ext_kw), len(ref_kw)


def item_to_text(item) -> str:
    """Flatten an array item (string or dict) to a comparable text blob."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return " ".join(str(v) for v in item.values())
    return str(item)


def covers(ref_item, ext_items: list) -> bool:
    """Return True if any extracted item shares significant keywords with ref_item."""
    ref_text = item_to_text(ref_item)
    ref_kw = keywords(ref_text)
    if not ref_kw:
        return False
    threshold = max(1, len(ref_kw) // 3)
    for ext in ext_items:
        ext_kw = keywords(item_to_text(ext))
        if len(ref_kw & ext_kw) >= threshold:
            return True
    return False


def compare_trust_boundary(ref_tb: dict, ext_tb: dict) -> dict:
    """Compare trust_boundary fields. Returns per-key match status."""
    result = {}
    for key in TRUST_KEYS:
        ref_val = ref_tb.get(key)
        ext_val = ext_tb.get(key)
        if ref_val is None and ext_val is None:
            continue
        if ref_val is None:
            result[key] = "EXTRA"
        elif ext_val is None:
            result[key] = "MISSING"
        elif key == "sanitization":
            # Prose field — use keyword overlap as a proxy.
            overlap, total = keyword_overlap(str(ext_val), str(ref_val))
            pct = (overlap / total * 100) if total else 0
            result[key] = "MATCH" if pct >= 40 else "PARTIAL"
        else:
            result[key] = "MATCH" if ref_val == ext_val else f"MISMATCH ({ext_val!r} vs ref {ref_val!r})"
    return result


def compare_error_conditions(ref_list: list, ext_list: list) -> tuple[int, int]:
    """Return (matched_count, reference_count)."""
    matched = sum(1 for r in ref_list if covers(r, ext_list))
    return matched, len(ref_list)


def compare_element(ext_contract: dict, ref_contract: dict) -> dict:
    """Produce a structured comparison for one element."""
    all_fields = set(ref_contract) | set(ext_contract)
    matched_fields = sorted(all_fields & set(ext_contract) & set(ref_contract))
    missing_fields = sorted(set(ref_contract) - set(ext_contract))
    extra_fields = sorted(set(ext_contract) - set(ref_contract))

    result: dict = {
        "matched_fields": matched_fields,
        "missing_fields": missing_fields,
        "extra_fields": extra_fields,
        "details": {},
    }

    # Purpose
    if "purpose" in ref_contract and "purpose" in ext_contract:
        overlap, total = keyword_overlap(
            str(ext_contract["purpose"]), str(ref_contract["purpose"])
        )
        pct = (overlap / total * 100) if total else 0
        result["details"]["purpose"] = {
            "reference": str(ref_contract["purpose"])[:200],
            "extracted": str(ext_contract["purpose"])[:200],
            "keyword_overlap": f"{overlap}/{total} ({pct:.0f}%)",
        }

    # Array fields
    for field in ARRAY_FIELDS:
        if field not in ref_contract:
            continue
        ref_items = ref_contract[field] if isinstance(ref_contract[field], list) else [ref_contract[field]]
        if field not in ext_contract:
            result["details"][field] = f"0/{len(ref_items)} covered (field missing)"
            continue
        ext_items = ext_contract[field] if isinstance(ext_contract[field], list) else [ext_contract[field]]

        if field == "error_conditions":
            matched, total = compare_error_conditions(ref_items, ext_items)
        else:
            matched = sum(1 for r in ref_items if covers(r, ext_items))
            total = len(ref_items)

        if matched == total:
            result["details"][field] = f"{matched}/{total} covered"
        else:
            uncovered = [
                item_to_text(r)[:120]
                for r in ref_items
                if not covers(r, ext_items)
            ]
            result["details"][field] = {
                "coverage": f"{matched}/{total} covered",
                "missing": uncovered,
            }

    # Trust boundary
    if "trust_boundary" in ref_contract:
        ref_tb = ref_contract["trust_boundary"] if isinstance(ref_contract["trust_boundary"], dict) else {}
        ext_tb = ext_contract.get("trust_boundary") or {}
        if not isinstance(ext_tb, dict):
            ext_tb = {}
        result["details"]["trust_boundary"] = compare_trust_boundary(ref_tb, ext_tb)

    # Severity consistency for error_conditions
    if "error_conditions" in ref_contract and "error_conditions" in ext_contract:
        ref_ec = ref_contract["error_conditions"]
        ext_ec = ext_contract["error_conditions"]
        if isinstance(ref_ec, list) and isinstance(ext_ec, list):
            ref_sevs = {e.get("severity") for e in ref_ec if isinstance(e, dict)}
            ext_sevs = {e.get("severity") for e in ext_ec if isinstance(e, dict)}
            result["details"]["error_severity_levels"] = {
                "reference": sorted(s for s in ref_sevs if s),
                "extracted": sorted(s for s in ext_sevs if s),
                "match": ref_sevs == ext_sevs,
            }

    return result


# --Text rendering
# --

def render_text(comparisons: list[dict], summary: dict) -> str:
    lines = []
    for item in comparisons:
        eid = item["element_id"]
        ref_id = item.get("reference_id")
        header = f"=== {eid} ==="
        if ref_id and ref_id != eid:
            header += f" (mapped to {ref_id})"
        lines.append(header)

        cmp = item["comparison"]
        lines.append(f"  Matched fields:  {', '.join(cmp['matched_fields']) or '(none)'}")
        if cmp["missing_fields"]:
            lines.append(f"  Missing fields:  {', '.join(cmp['missing_fields'])}")
        if cmp["extra_fields"]:
            lines.append(f"  Extra fields:    {', '.join(cmp['extra_fields'])}")
        lines.append("")

        for field, detail in cmp["details"].items():
            lines.append(f"  {field}:")
            if isinstance(detail, str):
                lines.append(f"    {detail}")
            elif isinstance(detail, dict):
                if field == "purpose":
                    lines.append(f"    REFERENCE: \"{detail['reference']}\"")
                    lines.append(f"    EXTRACTED: \"{detail['extracted']}\"")
                    lines.append(f"    Keywords overlap: {detail['keyword_overlap']}")
                elif field == "trust_boundary":
                    for k, v in detail.items():
                        lines.append(f"    {k}={v}")
                elif field == "error_severity_levels":
                    match_label = "MATCH" if detail["match"] else "MISMATCH"
                    lines.append(f"    {match_label} — ref: {detail['reference']}, extracted: {detail['extracted']}")
                else:
                    lines.append(f"    {detail.get('coverage', '')}")
                    for m in detail.get("missing", []):
                        lines.append(f"      missing: \"{m}\"")
            lines.append("")

    # Summary
    lines.append("Summary:")
    lines.append(f"  Elements compared: {summary['elements_compared']}")
    if summary["elements_compared"] > 0:
        lines.append(f"  Avg field coverage: {summary['avg_field_coverage_pct']:.0f}%")
        lines.append(f"  Avg keyword overlap (purpose): {summary['avg_purpose_overlap_pct']:.0f}%")
        lines.append(f"  Elements with all error_conditions: {summary['full_error_coverage']}/{summary['elements_with_error_conditions']}")
        lines.append(f"  Elements with matching trust_boundary: {summary['trust_boundary_match']}/{summary['elements_with_trust_boundary']}")

    return "\n".join(lines)


# --Summary stats
# --

def compute_summary(comparisons: list[dict]) -> dict:
    n = len(comparisons)
    if n == 0:
        return {
            "elements_compared": 0,
            "avg_field_coverage_pct": 0.0,
            "avg_purpose_overlap_pct": 0.0,
            "full_error_coverage": 0,
            "elements_with_error_conditions": 0,
            "trust_boundary_match": 0,
            "elements_with_trust_boundary": 0,
        }

    field_coverages = []
    purpose_overlaps = []
    full_error_coverage = 0
    elements_with_errors = 0
    trust_match = 0
    elements_with_trust = 0

    for item in comparisons:
        cmp = item["comparison"]
        all_ref_fields = len(cmp["matched_fields"]) + len(cmp["missing_fields"])
        if all_ref_fields > 0:
            field_coverages.append(len(cmp["matched_fields"]) / all_ref_fields * 100)

        details = cmp["details"]

        if "purpose" in details:
            raw = details["purpose"]["keyword_overlap"]
            nums = re.findall(r"\d+", raw)
            if len(nums) >= 2 and int(nums[1]) > 0:
                purpose_overlaps.append(int(nums[0]) / int(nums[1]) * 100)

        if "error_conditions" in details:
            elements_with_errors += 1
            ec = details["error_conditions"]
            coverage_str = ec if isinstance(ec, str) else ec.get("coverage", "")
            nums = re.findall(r"\d+", coverage_str)
            if len(nums) >= 2 and nums[0] == nums[1]:
                full_error_coverage += 1

        if "trust_boundary" in details:
            elements_with_trust += 1
            tb = details["trust_boundary"]
            if isinstance(tb, dict):
                statuses = list(tb.values())
                if statuses and all(s in ("MATCH", "PARTIAL") for s in statuses):
                    if all(s == "MATCH" for s in statuses):
                        trust_match += 1

    return {
        "elements_compared": n,
        "avg_field_coverage_pct": sum(field_coverages) / len(field_coverages) if field_coverages else 0.0,
        "avg_purpose_overlap_pct": sum(purpose_overlaps) / len(purpose_overlaps) if purpose_overlaps else 0.0,
        "full_error_coverage": full_error_coverage,
        "elements_with_error_conditions": elements_with_errors,
        "trust_boundary_match": trust_match,
        "elements_with_trust_boundary": elements_with_trust,
    }


# --Entry point
# --

def main() -> None:
    args = parse_args()
    id_map = parse_id_map(args.id_map)

    extracted_spec = load_spec(args.extracted)
    reference_spec = load_spec(args.reference)

    ext_elements = extracted_spec.get("elements", {})
    ref_elements = reference_spec.get("elements", {})

    comparisons = []
    skipped = []

    for ext_id, ext_elem in ext_elements.items():
        ref_id = id_map.get(ext_id, ext_id)

        if ref_id not in ref_elements:
            skipped.append(ext_id)
            continue

        ext_contract = ext_elem.get("contract") or {}
        ref_contract = ref_elements[ref_id].get("contract") or {}

        if not ref_contract:
            skipped.append(ext_id)
            continue

        comparisons.append({
            "element_id": ext_id,
            "reference_id": ref_id,
            "comparison": compare_element(ext_contract, ref_contract),
        })

    summary = compute_summary(comparisons)

    if args.format == "json":
        output = {"comparisons": comparisons, "summary": summary, "skipped": skipped}
        print(json.dumps(output, indent=2))
    else:
        if skipped:
            print(f"Skipped (no reference match): {', '.join(skipped)}\n",
                  file=sys.stderr)
        print(render_text(comparisons, summary))


if __name__ == "__main__":
    main()
