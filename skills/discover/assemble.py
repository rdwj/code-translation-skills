#!/usr/bin/env python3
"""Assemble a skeleton spec.json from treeloom CPG and optional tool outputs.

Reads a treeloom CPG JSON file and optional sanicode/veripak output files,
then produces a spec.json conforming to the code translation kit's spec schema.
The spec layers semantic understanding on top of the CPG — this script
populates structure (elements, cpg_ref) and tool findings (security, deps),
leaving behavioral contracts as empty stubs for later extraction.
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def compute_sha256(path: str) -> str:
    """Return the hex SHA-256 digest of the file at *path*."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CPG loading & normalization
# ---------------------------------------------------------------------------

def load_cpg(path: str) -> dict:
    """Load a treeloom CPG JSON file and flatten location fields on nodes.

    Raw CPG nodes nest file/line/column under ``location`` and
    ``end_location``.  This function hoists them to top-level keys
    (``file``, ``line``, ``column``, ``end_line``) so the rest of the
    code can access them uniformly.
    """
    with open(path) as f:
        cpg = json.load(f)
    for key in ("nodes", "edges"):
        if key not in cpg:
            raise SystemExit(f"CPG file missing required key '{key}'")

    for node in cpg["nodes"]:
        loc = node.get("location") or {}
        node.setdefault("file", loc.get("file", ""))
        node.setdefault("line", loc.get("line", 0))
        node.setdefault("column", loc.get("column", 0))
        end_loc = node.get("end_location") or {}
        node["end_line"] = end_loc.get("line")

    return cpg


# ---------------------------------------------------------------------------
# cpg_ref
# ---------------------------------------------------------------------------

def build_cpg_ref(cpg: dict, cpg_path: str, rel_path: str | None) -> dict:
    """Build the cpg_ref section of the spec."""
    nodes = cpg["nodes"]
    edges = cpg["edges"]
    unique_files = {n["file"] for n in nodes if n.get("file")}
    fn_count = sum(1 for n in nodes if n["kind"] == "function")

    return {
        "path": rel_path or os.path.basename(cpg_path),
        "sha256": compute_sha256(cpg_path),
        "built_at": _now_iso(),
        "treeloom_version": cpg.get("treeloom_version", "unknown"),
        "stats": {
            "nodes": len(nodes),
            "edges": len(edges),
            "files": len(unique_files),
            "functions": fn_count,
        },
    }


# ---------------------------------------------------------------------------
# Qualified name derivation
# ---------------------------------------------------------------------------

def infer_source_root_prefix(cpg: dict, source_root: str) -> str:
    """Find the source root prefix in CPG file paths.

    Handles both absolute paths (old CPGs without --relative-root) and
    relative paths (new CPGs built with --relative-root).

    Returns the prefix including source_root and trailing slash, e.g.:
      - Absolute: '/Users/x/project/src/'
      - Relative: 'src/'
    """
    source_root = source_root.rstrip("/")

    for node in cpg["nodes"]:
        fpath = node.get("file", "")
        if not fpath:
            continue
        # Absolute paths: look for /<source_root>/
        abs_marker = f"/{source_root}/"
        idx = fpath.find(abs_marker)
        if idx != -1:
            return fpath[: idx + len(abs_marker)]
        # Relative paths: check if path starts with <source_root>/
        rel_marker = f"{source_root}/"
        if fpath.startswith(rel_marker):
            return rel_marker

    raise SystemExit(
        f"Could not locate source root '{source_root}' in any CPG node file path. "
        "Check the --source-root argument."
    )


def qualified_name_from_file(file_path: str, source_root_prefix: str,
                             language: str) -> str:
    """Convert an absolute file path to a dotted qualified module name.

    Steps:
      1. Strip source_root_prefix prefix.
      2. Strip extension.
      3. For Python __init__.py: strip trailing /__init__.
      4. Replace '/' with '.'.
    """
    if not file_path.startswith(source_root_prefix):
        raise ValueError(
            f"File path '{file_path}' does not start with "
            f"source root '{source_root_prefix}'"
        )
    rel = file_path[len(source_root_prefix):]
    base, _ext = os.path.splitext(rel)

    if language == "python" and base.endswith("/__init__"):
        base = base[: -len("/__init__")]
    # Edge case: top-level __init__.py directly under source root
    if language == "python" and base == "__init__":
        base = os.path.basename(source_root_prefix.rstrip("/"))

    return base.replace("/", ".")


# ---------------------------------------------------------------------------
# Parent linkage via scope field
# ---------------------------------------------------------------------------

def resolve_parent_element(node: dict, node_map: dict[str, dict]) -> dict | None:
    """Walk up the scope chain to find the nearest module/class/function ancestor."""
    scope_id = node.get("scope")
    while scope_id:
        parent = node_map.get(scope_id)
        if not parent:
            return None
        if parent["kind"] in ("module", "class", "function"):
            return parent
        scope_id = parent.get("scope")
    return None


# ---------------------------------------------------------------------------
# Element ID generation
# ---------------------------------------------------------------------------

def node_to_element_id(node: dict, parent_element: dict | None,
                       parent_element_id: str | None,
                       language: str, source_root_prefix: str) -> str:
    """Compute a deterministic element ID for a CPG node.

    - module   → mod:<file_qname>
    - class    → cls:<parent_qname>.<ClassName>
    - function → fn:<parent_qname>/<func_name>

    Uses pre-computed *parent_element_id* to correctly handle deeply
    nested structures (nested classes, inner functions).
    """
    kind = node["kind"]
    name = node["name"]
    file_qname = qualified_name_from_file(node["file"], source_root_prefix, language)

    if kind == "module":
        return f"mod:{file_qname}"

    # Derive parent qualified name — prefer already-computed parent ID
    if parent_element_id:
        parent_qname = parent_element_id.split(":", 1)[1]
    elif parent_element:
        parent_qname = qualified_name_from_file(
            parent_element["file"], source_root_prefix, language
        )
    else:
        parent_qname = file_qname

    if kind == "class":
        # Java convention: primary class name matches file stem.  When the
        # parent is a module and the class name equals the last component of
        # the file qname, use the file qname directly to avoid duplication
        # (e.g. cls:org.jsoup.safety.Cleaner, not Cleaner.Cleaner).
        if (parent_element and parent_element["kind"] == "module"
                and file_qname.rsplit(".", 1)[-1] == name):
            return f"cls:{file_qname}"
        return f"cls:{parent_qname}.{name}"

    if kind == "function":
        return f"fn:{parent_qname}/{name}"

    return f"{kind}:{parent_qname}.{name}"


def _project_root_from_source_root(source_root_prefix: str, source_root: str) -> str:
    """Derive project root by stripping the source_root suffix.

    For absolute paths:  '/Users/x/project/src/' → '/Users/x/project/'
    For relative paths:  'src/' → '' (paths are already project-relative)
    """
    sr = source_root.strip("/")
    stripped = source_root_prefix.rstrip("/")
    if stripped.endswith(sr):
        prefix = stripped[: -len(sr)]
        if not prefix or prefix == "/":
            return ""
        return prefix.rstrip("/") + "/"
    return source_root_prefix


def build_elements(cpg: dict, language: str,
                   source_root: str,
                   source_root_prefix: str) -> dict[str, dict]:
    """Build element stubs for every module, class, and function in the CPG."""
    node_map = {n["id"]: n for n in cpg["nodes"]}
    project_root = _project_root_from_source_root(source_root_prefix, source_root)

    relevant_kinds = ("module", "class", "function")
    relevant_nodes = [n for n in cpg["nodes"] if n["kind"] in relevant_kinds]

    # Sort: modules first, then classes, then functions — ensures parents
    # are ID'd before their children.
    kind_order = {"module": 0, "class": 1, "function": 2}
    relevant_nodes.sort(key=lambda n: kind_order.get(n["kind"], 3))

    # First pass: compute element IDs.
    element_id_of: dict[str, str] = {}
    seen_ids: set[str] = set()

    for node in relevant_nodes:
        parent_elem = resolve_parent_element(node, node_map)
        parent_eid = element_id_of.get(parent_elem["id"]) if parent_elem else None
        eid = node_to_element_id(
            node, parent_elem, parent_eid, language, source_root_prefix
        )
        if eid in seen_ids:
            eid = f"{eid}@{node['line']}"
        seen_ids.add(eid)
        element_id_of[node["id"]] = eid

    # Second pass: build element dicts.
    elements: dict[str, dict] = {}
    for node in relevant_nodes:
        eid = element_id_of[node["id"]]
        parent_elem = resolve_parent_element(node, node_map)

        elem: dict = {
            "hierarchy_level": node["kind"],
            "node_ref": node["id"],
            "name": node["name"],
            "file": _make_relative_file(node["file"], project_root),
            "line": node["line"],
            "contract": {},
            "metadata": {
                "confidence": "high",
                "source": "static_analysis",
                "status": "extracted",
            },
        }

        if node["kind"] != "module" and parent_elem is not None:
            parent_eid = element_id_of.get(parent_elem["id"])
            if parent_eid:
                elem["parent"] = parent_eid

        elements[eid] = elem

    return elements


def _make_relative_file(file_path: str, project_root: str) -> str:
    """Strip project root to produce a project-relative file path."""
    if file_path.startswith(project_root):
        return file_path[len(project_root):]
    return file_path


# ---------------------------------------------------------------------------
# Sanicode → security_findings
# ---------------------------------------------------------------------------

def _build_function_line_index(
    cpg: dict,
) -> dict[str, list[tuple[int, int | None, str]]]:
    """Build file-basename → [(start_line, end_line, node_id)] index.

    Uses the ``end_line`` field (from ``end_location``) when available,
    falling back to start-line-only matching.
    """
    index: dict[str, list[tuple[int, int | None, str]]] = {}
    for node in cpg["nodes"]:
        if node["kind"] != "function":
            continue
        basename = os.path.basename(node.get("file", ""))
        if basename:
            index.setdefault(basename, []).append(
                (node["line"], node.get("end_line"), node["id"])
            )
    for entries in index.values():
        entries.sort(key=lambda t: t[0])
    return index


def _find_enclosing_function(
    file_basename: str, line: int,
    func_index: dict[str, list[tuple[int, int | None, str]]]
) -> str | None:
    """Find the CPG function enclosing *file_basename:line*."""
    candidates = func_index.get(file_basename, [])
    # Prefer exact range match when end_line is available
    for start, end, node_id in candidates:
        if end is not None and start <= line <= end:
            return node_id
    # Fallback: nearest function whose start line <= target line
    best = None
    for start, _end, node_id in candidates:
        if start <= line:
            best = node_id
        else:
            break
    return best


def map_sanicode_finding(
    finding: dict,
    func_index: dict[str, list[tuple[int, int | None, str]]]
) -> dict:
    """Map a single sanicode finding to the spec's security_finding schema."""
    severity_raw = (finding.get("derived_severity")
                    or finding.get("severity", "info"))
    severity = severity_raw.lower()
    if severity not in ("critical", "high", "medium", "low", "info"):
        severity = "info"

    result: dict = {
        "file": finding["file"],
        "line": finding["line"],
        "rule_id": finding["rule_id"],
        "severity": severity,
        "metadata": {
            "confidence": "high",
            "source": "static_analysis",
            "status": "extracted",
        },
    }

    if finding.get("column") is not None:
        result["column"] = finding["column"]
    if finding.get("message"):
        result["message"] = finding["message"]
    if finding.get("cwe_id") is not None:
        result["cwe_id"] = finding["cwe_id"]
    if finding.get("cwe_name"):
        result["cwe_name"] = finding["cwe_name"]
    if finding.get("remediation"):
        result["remediation"] = finding["remediation"]
    if finding.get("action") in ("fix", "review", "accept", "defer"):
        result["action"] = finding["action"]

    # Compliance: extract only the 4 allowed sub-objects
    raw_comp = finding.get("compliance", {})
    if raw_comp:
        compliance: dict = {}
        for key in ("owasp_asvs", "nist_800_53", "asd_stig", "pci_dss"):
            val = raw_comp.get(key)
            if val:
                compliance[key] = val
        if compliance:
            result["compliance"] = compliance

    # Best-effort node_ref
    file_basename = os.path.basename(finding["file"])
    node_ref = _find_enclosing_function(file_basename, finding["line"], func_index)
    if node_ref:
        result["node_ref"] = node_ref

    return result


def build_security_findings(
    sanicode_path: str,
    cpg: dict | None = None,
) -> tuple[list[dict], str | None]:
    """Load sanicode output and map all findings. Returns (findings, version)."""
    with open(sanicode_path) as f:
        data = json.load(f)

    version = data.get("sanicode_version")
    raw_findings = data.get("findings", [])

    func_index: dict[str, list[tuple[int, int | None, str]]] = {}
    if cpg:
        func_index = _build_function_line_index(cpg)

    mapped = [map_sanicode_finding(fd, func_index) for fd in raw_findings]
    return mapped, version


# ---------------------------------------------------------------------------
# Veripak → ecosystem_dependencies
# ---------------------------------------------------------------------------

_URGENCY_MAP = {
    "immediate": "immediate",
    "critical": "immediate",
    "high": "high",
    "medium": "medium",
    "low": "low",
    "none": "none",
}

_CVE_SEVERITY_MAP = {
    "critical": "CRITICAL",
    "high": "HIGH",
    "medium": "MEDIUM",
    "low": "LOW",
}

_MAX_RECOMMENDATION_LEN = 500


def map_veripak_output(data: dict) -> dict:
    """Map a single veripak JSON output to the spec's ecosystem_dependency schema."""
    result: dict = {
        "package": data["package"],
        "ecosystem": data["ecosystem"],
        "metadata": {
            "confidence": "high",
            "source": "static_analysis",
            "status": "extracted",
        },
    }

    # latest_version
    version_str = None
    ver_obj = data.get("version")
    if isinstance(ver_obj, dict) and ver_obj.get("version"):
        version_str = ver_obj["version"]
    if not version_str:
        summary = data.get("summary") or {}
        version_str = summary.get("latest_version")
    if version_str:
        result["latest_version"] = str(version_str)

    # CVEs
    cves_section = data.get("cves") or {}
    raw_cves = (cves_section.get("versions_cves") or []) + \
               (cves_section.get("latest_cves") or [])
    if raw_cves:
        mapped_cves = []
        for cve in raw_cves:
            cve_entry: dict = {"id": cve.get("id", cve.get("cve_id", "unknown"))}
            sev = str(cve.get("severity", "")).lower()
            cve_entry["severity"] = _CVE_SEVERITY_MAP.get(sev, "MEDIUM")
            if cve.get("summary"):
                cve_entry["summary"] = cve["summary"]
            elif cve.get("description"):
                cve_entry["summary"] = cve["description"]
            mapped_cves.append(cve_entry)
        result["cves"] = mapped_cves

    # EOL
    eol_data = data.get("eol") or {}
    if eol_data:
        eol: dict = {}
        if "eol" in eol_data:
            eol["is_eol"] = eol_data["eol"]
        if "eol_date" in eol_data:
            eol["eol_date"] = eol_data["eol_date"]
        conf = eol_data.get("confidence")
        if conf in ("high", "medium", "low"):
            eol["confidence"] = conf
        if eol:
            result["eol"] = eol

    # Recommendation
    summary = data.get("summary") or {}
    rec = summary.get("recommendation")
    if not rec:
        rec = summary.get("upgrade_path")
    if rec:
        if len(rec) > _MAX_RECOMMENDATION_LEN:
            rec = rec[: _MAX_RECOMMENDATION_LEN - 3] + "..."
        result["recommendation"] = rec

    # Urgency
    raw_urgency = str(summary.get("urgency", "")).lower()
    urgency = _URGENCY_MAP.get(raw_urgency)
    if urgency:
        result["urgency"] = urgency

    return result


def build_ecosystem_deps(veripak_paths: list[str]) -> tuple[list[dict], str | None]:
    """Load all veripak outputs and map them. Returns (deps, version)."""
    deps: list[dict] = []
    version = None
    for path in veripak_paths:
        with open(path) as f:
            data = json.load(f)
        if not version:
            version = data.get("veripak_version")
        deps.append(map_veripak_output(data))
    return deps, version


# ---------------------------------------------------------------------------
# Meta section
# ---------------------------------------------------------------------------

def build_meta(project_name: str, language: str,
               source_version: str | None,
               tools: dict[str, str]) -> dict:
    """Build the meta section of the spec."""
    now = _now_iso()
    meta: dict = {
        "project_name": project_name,
        "spec_version": "0.1.0",
        "source_language": language,
        "created_at": now,
        "updated_at": now,
    }
    if source_version:
        meta["source_version"] = source_version
    if tools:
        meta["tools"] = tools
    return meta


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------

def assemble_spec(
    cpg_path: str,
    project_name: str,
    language: str,
    source_root: str,
    source_version: str | None = None,
    sanicode_path: str | None = None,
    veripak_paths: list[str] | None = None,
    cpg_rel_path: str | None = None,
) -> dict:
    """Orchestrate spec assembly from all inputs."""
    cpg = load_cpg(cpg_path)
    source_root_prefix = infer_source_root_prefix(cpg, source_root)

    tools: dict[str, str] = {}
    tv = cpg.get("treeloom_version")
    if tv:
        tools["treeloom"] = tv

    cpg_ref = build_cpg_ref(cpg, cpg_path, cpg_rel_path)
    elements = build_elements(cpg, language, source_root, source_root_prefix)

    security_findings: list[dict] | None = None
    if sanicode_path:
        security_findings, sani_ver = build_security_findings(sanicode_path, cpg)
        if sani_ver:
            tools["sanicode"] = sani_ver

    eco_deps: list[dict] | None = None
    if veripak_paths:
        eco_deps, veri_ver = build_ecosystem_deps(veripak_paths)
        if veri_ver:
            tools["veripak"] = veri_ver

    meta = build_meta(project_name, language, source_version, tools)

    spec: dict = {
        "meta": meta,
        "cpg_ref": cpg_ref,
        "elements": elements,
    }
    if security_findings is not None:
        spec["security_findings"] = security_findings
    if eco_deps is not None:
        spec["ecosystem_dependencies"] = eco_deps

    return spec


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Assemble a skeleton spec.json from treeloom CPG "
                    "and optional sanicode/veripak outputs."
    )
    parser.add_argument("--cpg", required=True,
                        help="Path to treeloom CPG JSON file.")
    parser.add_argument("--project-name", required=True,
                        help="Project name for the spec metadata.")
    parser.add_argument("--language", required=True,
                        help="Source language (e.g. python, java).")
    parser.add_argument("--source-root", required=True,
                        help="Relative source root (e.g. 'src', 'src/main/java').")
    parser.add_argument("--source-version",
                        help="Source language version (e.g. '3.11', '17').")
    parser.add_argument("--sanicode",
                        help="Path to sanicode result JSON (optional).")
    parser.add_argument("--veripak", action="append", default=[],
                        help="Path to veripak output JSON (repeatable).")
    parser.add_argument("--cpg-rel-path",
                        help="Relative path from spec to CPG file "
                             "(defaults to basename of --cpg).")
    parser.add_argument("-o", "--output", required=True,
                        help="Output path for the spec JSON file.")

    args = parser.parse_args()

    spec = assemble_spec(
        cpg_path=args.cpg,
        project_name=args.project_name,
        language=args.language,
        source_root=args.source_root,
        source_version=args.source_version,
        sanicode_path=args.sanicode,
        veripak_paths=args.veripak or None,
        cpg_rel_path=args.cpg_rel_path,
    )

    with open(args.output, "w") as f:
        json.dump(spec, f, indent=2)
        f.write("\n")

    elem_count = len(spec["elements"])
    finding_count = len(spec.get("security_findings", []))
    dep_count = len(spec.get("ecosystem_dependencies", []))
    print(f"Wrote {args.output}: {elem_count} elements, "
          f"{finding_count} security findings, {dep_count} dependencies",
          file=sys.stderr)


if __name__ == "__main__":
    main()
