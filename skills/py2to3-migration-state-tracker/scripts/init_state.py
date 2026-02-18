#!/usr/bin/env python3
"""
Migration State Tracker — Initialization Script

Reads Phase 0 Codebase Analyzer outputs (raw-scan.json, dependency-graph.json,
migration-order.json) and creates the initial migration-state.json with every
module at phase 0.

Usage:
    python3 init_state.py <analysis_dir> \
        --project-name "Legacy SCADA System" \
        --target-version 3.12 \
        [--output <path>/migration-state.json]

If --output is omitted, writes to <analysis_dir>/migration-state.json.

The analysis_dir should contain the outputs from Skill 0.1 (Codebase Analyzer):
  - raw-scan.json        — per-file scan results
  - dependency-graph.json — module dependency graph
  - migration-order.json  — topological sort with clusters
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


# ── Utility Functions ──────────────────────────────────────────────────────


def load_json(path: Union[str, Path]) -> Dict[str, Any]:
    """Load a JSON file, exiting with a clear message if it doesn't exist."""
    p = Path(path)
    if not p.exists():
        print(f"Error: Required file not found: {path}", file=sys.stderr)
        print(
            "Run the Codebase Analyzer (Skill 0.1) first to generate Phase 0 outputs.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Module State Extraction ────────────────────────────────────────────────


def extract_module_state(
    file_entry: Dict[str, Any],
    dep_graph: Dict[str, Any],
    module_path: str,
) -> Dict[str, Any]:
    """Build the initial module state dict from Phase 0 scan data.

    Pulls risk factors, py2-ism counts, and metrics from the raw scan,
    and dependency fan-in/fan-out from the graph.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Extract py2-ism counts by category from the scan results.
    # The raw scan stores findings as a list; we count by category.
    findings = file_entry.get("findings", [])
    py2_ism_counts = {
        "syntax": 0,
        "semantic_iterator": 0,
        "semantic_bytes_str": 0,
        "semantic_division": 0,
        "semantic_import": 0,
        "metaclass": 0,
    }

    # Map the pattern categories from analyze.py to our summary buckets
    category_map = {
        "syntax": "syntax",
        "semantic": "semantic_iterator",  # default semantic bucket
        "string_bytes": "semantic_bytes_str",
        "bytes_str": "semantic_bytes_str",
        "division": "semantic_division",
        "numeric": "semantic_division",
        "import": "semantic_import",
        "module": "semantic_import",
        "metaclass": "metaclass",
        "class": "metaclass",
    }

    for finding in findings:
        cat = finding.get("category", "syntax").lower()
        bucket = category_map.get(cat, "syntax")
        py2_ism_counts[bucket] = py2_ism_counts.get(bucket, 0) + 1

    # Compute risk factors
    risk_factors = file_entry.get("risk_factors", [])
    risk_score = file_entry.get("risk_score", "medium")

    # Metrics from the scan
    metrics = file_entry.get("metrics", {})
    loc = metrics.get("lines_of_code", metrics.get("loc", 0))
    num_functions = metrics.get("num_functions", metrics.get("functions", 0))
    num_classes = metrics.get("num_classes", metrics.get("classes", 0))

    # Fan-in / fan-out from the dependency graph
    fan_in = 0
    fan_out = 0
    if "nodes" in dep_graph and "edges" in dep_graph:
        for edge in dep_graph.get("edges", []):
            if edge.get("target") == module_path or edge.get("to") == module_path:
                fan_in += 1
            if edge.get("source") == module_path or edge.get("from") == module_path:
                fan_out += 1

    return {
        "current_phase": 0,
        "phase_history": [
            {
                "phase": 0,
                "started": now,
                "completed": None,
                "gate_passed": False,
                "gate_report": None,
                "skill_outputs": [],
            }
        ],
        "conversion_unit": None,
        "risk_score": risk_score,
        "risk_factors": risk_factors,
        "blockers": [],
        "decisions": [],
        "notes": [],
        "py2_ism_counts": py2_ism_counts,
        "metrics": {
            "lines_of_code": loc,
            "num_functions": num_functions,
            "num_classes": num_classes,
            "test_coverage_percent": None,
            "dependency_fan_in": fan_in,
            "dependency_fan_out": fan_out,
        },
    }


# ── Conversion Unit Extraction ─────────────────────────────────────────────


def extract_conversion_units(migration_order: Dict[str, Any]) -> Dict[str, Any]:
    """Build initial conversion unit entries from migration-order.json.

    The migration order file contains cluster information — groups of modules
    that must be converted together due to mutual imports.
    """
    units = {}
    clusters = migration_order.get("clusters", [])

    for i, cluster in enumerate(clusters):
        members = cluster.get("modules", cluster.get("members", []))
        if len(members) <= 1:
            # Single-module clusters don't need a conversion unit
            continue

        unit_name = cluster.get("name", f"cluster-{i:03d}")
        units[unit_name] = {
            "modules": members,
            "current_phase": 0,
            "dependencies": cluster.get("dependencies", []),
            "risk_score": cluster.get("risk_score", "medium"),
            "assigned_to": None,
            "notes": [],
        }

    return units


# ── Summary Statistics ─────────────────────────────────────────────────────


def compute_summary(modules: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the summary statistics from the modules dict."""
    total = len(modules)
    by_phase = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    by_risk = {"low": 0, "medium": 0, "high": 0, "critical": 0}

    for mod in modules.values():
        phase_key = str(mod.get("current_phase", 0))
        by_phase[phase_key] = by_phase.get(phase_key, 0) + 1

        risk = mod.get("risk_score", "medium").lower()
        by_risk[risk] = by_risk.get(risk, 0) + 1

    return {
        "total_modules": total,
        "by_phase": by_phase,
        "by_risk": by_risk,
    }


# ── State Builder ──────────────────────────────────────────────────────────


def build_state(
    analysis_dir: str,
    project_name: str,
    target_version: str,
    codebase_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the complete migration-state.json from Phase 0 outputs."""
    analysis = Path(analysis_dir)
    now = datetime.now(timezone.utc).isoformat()

    # Load Phase 0 outputs
    raw_scan = load_json(analysis / "raw-scan.json")
    dep_graph = load_json(analysis / "dependency-graph.json")
    migration_order = load_json(analysis / "migration-order.json")

    # Determine codebase path from scan data or argument
    if codebase_path is None:
        codebase_path = raw_scan.get(
            "codebase_path", raw_scan.get("root", str(analysis.parent))
        )

    # Build per-module state
    modules = {}
    file_entries = raw_scan.get("files", raw_scan.get("modules", {}))

    # Handle both list-of-dicts and dict-keyed-by-path formats
    if isinstance(file_entries, list):
        for entry in file_entries:
            path = entry.get("path", entry.get("module_path", ""))
            if path:
                modules[path] = extract_module_state(entry, dep_graph, path)
    elif isinstance(file_entries, dict):
        for path, entry in file_entries.items():
            modules[path] = extract_module_state(entry, dep_graph, path)

    # Build conversion units from clusters
    conversion_units = extract_conversion_units(migration_order)

    # Link modules to their conversion units
    for unit_name, unit in conversion_units.items():
        for mod_path in unit["modules"]:
            if mod_path in modules:
                modules[mod_path]["conversion_unit"] = unit_name

    # Compute summary
    summary = compute_summary(modules)

    state = {
        "project": {
            "name": project_name,
            "codebase_path": str(codebase_path),
            "target_version": target_version,
            "created": now,
            "last_updated": now,
        },
        "modules": modules,
        "conversion_units": conversion_units,
        "global_decisions": [],
        "waivers": [],
        "rollbacks": [],
        "summary": summary,
    }

    return state


# ── Main ──────────────────────────────────────────────────────────────────


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Initialize migration state from Phase 0 analysis outputs."
    )
    parser.add_argument(
        "analysis_dir",
        help="Directory containing Phase 0 outputs (raw-scan.json, dependency-graph.json, migration-order.json)",
    )
    parser.add_argument(
        "--project-name",
        required=True,
        help="Human-readable project name",
    )
    parser.add_argument(
        "--target-version",
        required=True,
        help="Target Python 3 version (e.g. 3.12)",
    )
    parser.add_argument(
        "--codebase-path",
        default=None,
        help="Path to the codebase root (auto-detected from scan if omitted)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for migration-state.json (defaults to <analysis_dir>/migration-state.json)",
    )

    args = parser.parse_args()

    output_path = args.output or os.path.join(args.analysis_dir, "migration-state.json")

    # Don't overwrite an existing state file without confirmation
    if os.path.exists(output_path):
        print(f"Warning: {output_path} already exists.", file=sys.stderr)
        print(
            "Pass --output to a different path, or delete the existing file to reinitialize.",
            file=sys.stderr,
        )
        sys.exit(1)

    state = build_state(
        analysis_dir=args.analysis_dir,
        project_name=args.project_name,
        target_version=args.target_version,
        codebase_path=args.codebase_path,
    )

    # Write the state file
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    # Print summary
    summary = state["summary"]
    units = len(state["conversion_units"])
    print(f"Migration state initialized: {output_path}")
    print(f"  Project: {state['project']['name']}")
    print(f"  Target version: Python {state['project']['target_version']}")
    print(f"  Modules tracked: {summary['total_modules']}")
    print(f"  Conversion units: {units}")
    print(f"  Risk breakdown: {summary['by_risk']}")


if __name__ == "__main__":
    main()
