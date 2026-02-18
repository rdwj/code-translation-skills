#!/usr/bin/env python3
"""
Gate Checker — Main Gate Validation Script

Validates that all gate criteria for a migration phase have been met before
a module, conversion unit, or the entire codebase can advance.

Reads:
  - migration-state.json (from the Migration State Tracker)
  - Evidence files produced by other skills
  - Optional gate-config.json for custom thresholds

Produces:
  - gate-check-report.json — machine-readable pass/fail per criterion

Usage:
    # Check a single module
    python3 check_gate.py <state_file> \
        --module "src/scada/modbus_reader.py" \
        --output <output_dir>

    # Check a conversion unit
    python3 check_gate.py <state_file> \
        --unit "scada-core" \
        --output <output_dir>

    # Check all modules at a given phase
    python3 check_gate.py <state_file> \
        --all \
        --output <output_dir>

    # With custom config and evidence directory
    python3 check_gate.py <state_file> \
        --module "src/scada/modbus_reader.py" \
        --output <output_dir> \
        --gate-config gate-config.json \
        --analysis-dir ./migration-analysis \
        --evidence-dir ./migration-analysis
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Default Gate Criteria
# ═══════════════════════════════════════════════════════════════════════════

# Each criterion is a dict with:
#   name          — unique identifier
#   description   — human-readable explanation
#   check_type    — how to validate (file_exists, state_flag, threshold, evidence_field)
#   threshold     — the target value (meaning depends on check_type)
#   evidence_file — which file to look for (relative to evidence_dir)
#   evidence_field — JSON path within the evidence file (dot-separated)

DEFAULT_CRITERIA = {
    "0_to_1": [
        {
            "name": "analysis_complete",
            "description": "Phase 0 codebase analysis outputs exist",
            "check_type": "file_exists",
            "evidence_file": "raw-scan.json",
            "threshold": True,
        },
        {
            "name": "data_layer_analyzed",
            "description": "Data Format Analyzer has produced its report",
            "check_type": "file_exists",
            "evidence_file": "data-layer-report.json",
            "threshold": True,
        },
        {
            "name": "target_version_selected",
            "description": "Target Python version is set in project config",
            "check_type": "state_field",
            "state_path": "project.target_version",
            "threshold": "non_empty",
        },
        {
            "name": "report_reviewed",
            "description": "Migration report has been reviewed (decision or note recorded)",
            "check_type": "module_has_decisions_or_notes",
            "threshold": True,
        },
    ],
    "1_to_2": [
        {
            "name": "future_imports_added",
            "description": "Future imports injected into module files",
            "check_type": "file_exists",
            "evidence_file": "future-imports-report.json",
            "threshold": True,
        },
        {
            "name": "test_coverage",
            "description": "Test coverage on critical-path modules meets threshold",
            "check_type": "evidence_threshold",
            "evidence_file": "test-coverage-report.json",
            "evidence_field": "coverage_percent",
            "threshold": 60,
            "comparison": ">=",
        },
        {
            "name": "lint_baseline_stable",
            "description": "Lint scores haven't regressed from baseline",
            "check_type": "file_exists",
            "evidence_file": "lint-baseline.json",
            "threshold": True,
        },
        {
            "name": "ci_green_py2",
            "description": "CI passes under Python 2 with future imports",
            "check_type": "evidence_threshold",
            "evidence_file": "ci-results.json",
            "evidence_field": "py2_pass",
            "threshold": True,
            "comparison": "==",
        },
        {
            "name": "high_risk_triaged",
            "description": "All high-risk modules have been triaged (decisions or notes)",
            "check_type": "high_risk_triaged",
            "threshold": True,
        },
    ],
    "2_to_3": [
        {
            "name": "conversion_complete",
            "description": "Automated converter has processed the module",
            "check_type": "file_exists",
            "evidence_file": "conversion-report.json",
            "threshold": True,
        },
        {
            "name": "tests_pass_py2",
            "description": "Tests pass under Python 2 after conversion",
            "check_type": "evidence_threshold",
            "evidence_file": "test-results-py2.json",
            "evidence_field": "pass_rate",
            "threshold": 100,
            "comparison": ">=",
        },
        {
            "name": "tests_pass_py3",
            "description": "Tests pass under Python 3 after conversion",
            "check_type": "evidence_threshold",
            "evidence_file": "test-results-py3.json",
            "evidence_field": "pass_rate",
            "threshold": 90,
            "comparison": ">=",
        },
        {
            "name": "no_lint_regressions",
            "description": "No lint score regressions from baseline",
            "check_type": "evidence_threshold",
            "evidence_file": "lint-comparison.json",
            "evidence_field": "regressions",
            "threshold": 0,
            "comparison": "<=",
        },
        {
            "name": "conversion_reviewed",
            "description": "Conversion diff has been reviewed",
            "check_type": "module_has_decisions_or_notes",
            "threshold": True,
        },
    ],
    "3_to_4": [
        {
            "name": "tests_pass_py3_full",
            "description": "Full test suite passes under Python 3",
            "check_type": "evidence_threshold",
            "evidence_file": "test-results-py3.json",
            "evidence_field": "pass_rate",
            "threshold": 100,
            "comparison": ">=",
        },
        {
            "name": "no_encoding_errors",
            "description": "No encoding-related errors in test logs",
            "check_type": "evidence_threshold",
            "evidence_file": "test-results-py3.json",
            "evidence_field": "encoding_errors",
            "threshold": 0,
            "comparison": "<=",
        },
        {
            "name": "bytes_str_boundaries_resolved",
            "description": "All bytes/str boundaries have explicit handling",
            "check_type": "evidence_threshold",
            "evidence_file": "bytes-str-fixes.json",
            "evidence_field": "unresolved_count",
            "threshold": 0,
            "comparison": "<=",
        },
        {
            "name": "type_hints_public",
            "description": "Public interfaces have type annotations",
            "check_type": "evidence_threshold",
            "evidence_file": "typing-report.json",
            "evidence_field": "public_coverage_percent",
            "threshold": 80,
            "comparison": ">=",
        },
        {
            "name": "semantic_fixes_reviewed",
            "description": "All semantic fix decisions have rationale recorded",
            "check_type": "module_decisions_have_rationale",
            "threshold": True,
        },
    ],
    "4_to_5": [
        {
            "name": "zero_behavioral_diffs",
            "description": "No unexpected behavioral differences between Py2 and Py3",
            "check_type": "evidence_threshold",
            "evidence_file": "behavioral-diff-report.json",
            "evidence_field": "unexpected_diffs",
            "threshold": 0,
            "comparison": "<=",
        },
        {
            "name": "performance_acceptable",
            "description": "No performance regressions beyond threshold",
            "check_type": "evidence_threshold",
            "evidence_file": "performance-report.json",
            "evidence_field": "max_regression_percent",
            "threshold": 10,
            "comparison": "<=",
        },
        {
            "name": "encoding_stress_pass",
            "description": "Encoding stress tests pass",
            "check_type": "evidence_threshold",
            "evidence_file": "encoding-stress-report.json",
            "evidence_field": "pass_rate",
            "threshold": 100,
            "comparison": ">=",
        },
        {
            "name": "completeness_100",
            "description": "Migration completeness checker reports done",
            "check_type": "evidence_threshold",
            "evidence_file": "completeness-report.json",
            "evidence_field": "completeness_percent",
            "threshold": 100,
            "comparison": ">=",
        },
        {
            "name": "stakeholder_signoff",
            "description": "Stakeholder has signed off on cutover readiness",
            "check_type": "module_has_decisions_or_notes",
            "threshold": True,
        },
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def load_json(path: str) -> Optional[Dict[str, Any]]:
    """Load a JSON file, returning None if it doesn't exist."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_json_required(path: str, label: str) -> Dict[str, Any]:
    """Load a JSON file, exiting with error if it doesn't exist."""
    data = load_json(path)
    if data is None:
        print(f"Error: Required file not found or invalid: {path} ({label})", file=sys.stderr)
        sys.exit(1)
    return data


def resolve_json_path(data: Dict[str, Any], path: str) -> Any:
    """Walk a dot-separated path into a nested dict. Returns None if any key is missing."""
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def compare_value(actual: Any, threshold: Any, comparison: str) -> bool:
    """Compare actual against threshold using the given operator."""
    if actual is None:
        return False
    try:
        actual_num = float(actual) if not isinstance(actual, bool) else actual
        threshold_num = float(threshold) if not isinstance(threshold, bool) else threshold
    except (ValueError, TypeError):
        actual_num = actual
        threshold_num = threshold

    if comparison == ">=":
        return actual_num >= threshold_num
    elif comparison == "<=":
        return actual_num <= threshold_num
    elif comparison == "==":
        return actual_num == threshold_num
    elif comparison == ">":
        return actual_num > threshold_num
    elif comparison == "<":
        return actual_num < threshold_num
    elif comparison == "!=":
        return actual_num != threshold_num
    return False


def format_threshold(criterion: Dict[str, Any]) -> str:
    """Format a threshold for display."""
    comp = criterion.get("comparison", "==")
    threshold = criterion.get("threshold")
    if isinstance(threshold, bool):
        return "required" if threshold else "not required"
    return f"{comp} {threshold}"


# ═══════════════════════════════════════════════════════════════════════════
# Gate Check Engine
# ═══════════════════════════════════════════════════════════════════════════

def get_criteria_for_transition(
    current_phase: int,
    config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Return the list of criteria for a phase transition.

    Merges defaults with any overrides from gate-config.json.
    """
    transition_key = f"{current_phase}_to_{current_phase + 1}"
    criteria = DEFAULT_CRITERIA.get(transition_key, [])

    if not criteria:
        return []

    # Deep-copy to avoid mutating defaults
    criteria = [dict(c) for c in criteria]

    if config:
        # Apply threshold overrides
        thresholds = config.get("thresholds", {})
        phase_key = f"phase_{current_phase}_to_{current_phase + 1}"
        overrides = thresholds.get(phase_key, {})

        for criterion in criteria:
            if criterion["name"] in overrides:
                criterion["threshold"] = overrides[criterion["name"]]

        # Remove disabled criteria
        disabled = set(config.get("disabled_criteria", []))
        criteria = [c for c in criteria if c["name"] not in disabled]

    return criteria


def check_file_exists(
    criterion: Dict[str, Any],
    evidence_dir: str,
    analysis_dir: str,
) -> Tuple[str, Any, str]:
    """Check whether an evidence file exists. Returns (status, actual, details)."""
    evidence_file = criterion.get("evidence_file", "")

    # Look in evidence dir first, then analysis dir
    for search_dir in [evidence_dir, analysis_dir]:
        if search_dir:
            full_path = os.path.join(search_dir, evidence_file)
            if os.path.exists(full_path):
                return "pass", True, f"Found: {full_path}"

    return "not_evaluated", False, f"File not found: {evidence_file}"


def check_state_field(
    criterion: Dict[str, Any],
    state: Dict[str, Any],
) -> Tuple[str, Any, str]:
    """Check a field in the migration state."""
    state_path = criterion.get("state_path", "")
    value = resolve_json_path(state, state_path)

    threshold = criterion.get("threshold")
    if threshold == "non_empty":
        if value and str(value).strip():
            return "pass", value, f"Field '{state_path}' = '{value}'"
        return "fail", value, f"Field '{state_path}' is empty or missing"

    if value == threshold:
        return "pass", value, f"Field '{state_path}' = {value}"
    return "fail", value, f"Field '{state_path}' = {value}, expected {threshold}"


def check_evidence_threshold(
    criterion: Dict[str, Any],
    evidence_dir: str,
    analysis_dir: str,
) -> Tuple[str, Any, str]:
    """Check a value inside an evidence file against a threshold."""
    evidence_file = criterion.get("evidence_file", "")
    evidence_field = criterion.get("evidence_field", "")
    comparison = criterion.get("comparison", ">=")
    threshold = criterion["threshold"]

    # Find the evidence file
    data = None
    found_path = None
    for search_dir in [evidence_dir, analysis_dir]:
        if search_dir:
            full_path = os.path.join(search_dir, evidence_file)
            data = load_json(full_path)
            if data is not None:
                found_path = full_path
                break

    if data is None:
        return "not_evaluated", None, f"Evidence file not found: {evidence_file}"

    actual = resolve_json_path(data, evidence_field)
    if actual is None:
        return (
            "not_evaluated",
            None,
            f"Field '{evidence_field}' not found in {evidence_file}",
        )

    if compare_value(actual, threshold, comparison):
        return "pass", actual, f"{evidence_field} = {actual} ({comparison} {threshold})"
    return (
        "fail",
        actual,
        f"{evidence_field} = {actual}, required {comparison} {threshold}",
    )


def check_module_has_decisions_or_notes(
    module_state: Optional[Dict[str, Any]],
) -> Tuple[str, Any, str]:
    """Check that a module has at least one decision or note recorded."""
    if module_state is None:
        return "not_evaluated", False, "Module not found in state"

    decisions = module_state.get("decisions", [])
    notes = module_state.get("notes", [])
    total = len(decisions) + len(notes)

    if total > 0:
        return "pass", total, f"{len(decisions)} decision(s), {len(notes)} note(s)"
    return "fail", 0, "No decisions or notes recorded — review has not been documented"


def check_module_decisions_have_rationale(
    module_state: Optional[Dict[str, Any]],
) -> Tuple[str, Any, str]:
    """Check that all decisions for a module have a rationale."""
    if module_state is None:
        return "not_evaluated", False, "Module not found in state"

    decisions = module_state.get("decisions", [])
    if not decisions:
        return "pass", True, "No decisions to check"

    missing = [d for d in decisions if not d.get("rationale")]
    if not missing:
        return "pass", True, f"All {len(decisions)} decision(s) have rationale"
    return (
        "fail",
        False,
        f"{len(missing)} of {len(decisions)} decision(s) missing rationale",
    )


def check_high_risk_triaged(
    state: Dict[str, Any],
) -> Tuple[str, Any, str]:
    """Check that all high/critical risk modules have decisions or notes."""
    modules = state.get("modules", {})
    high_risk = {
        p: m
        for p, m in modules.items()
        if m.get("risk_score", "").lower() in ("high", "critical")
    }

    if not high_risk:
        return "pass", True, "No high-risk modules found"

    untriaged = []
    for path, mod in high_risk.items():
        decisions = mod.get("decisions", [])
        notes = mod.get("notes", [])
        if not decisions and not notes:
            untriaged.append(path)

    if not untriaged:
        return "pass", True, f"All {len(high_risk)} high/critical-risk modules triaged"
    return (
        "fail",
        False,
        f"{len(untriaged)} of {len(high_risk)} high/critical-risk modules untriaged: "
        + ", ".join(untriaged[:5])
        + ("..." if len(untriaged) > 5 else ""),
    )


def evaluate_criterion(
    criterion: Dict[str, Any],
    state: Dict[str, Any],
    module_state: Optional[Dict[str, Any]],
    evidence_dir: str,
    analysis_dir: str,
    waivers: List[Dict[str, Any]],
    current_phase: int,
) -> Dict[str, Any]:
    """Evaluate a single criterion and return the result."""
    check_type = criterion.get("check_type", "")
    status = "not_evaluated"
    actual = None
    details = ""

    if check_type == "file_exists":
        status, actual, details = check_file_exists(criterion, evidence_dir, analysis_dir)

    elif check_type == "state_field":
        status, actual, details = check_state_field(criterion, state)

    elif check_type == "evidence_threshold":
        status, actual, details = check_evidence_threshold(
            criterion, evidence_dir, analysis_dir
        )

    elif check_type == "module_has_decisions_or_notes":
        status, actual, details = check_module_has_decisions_or_notes(module_state)

    elif check_type == "module_decisions_have_rationale":
        status, actual, details = check_module_decisions_have_rationale(module_state)

    elif check_type == "high_risk_triaged":
        status, actual, details = check_high_risk_triaged(state)

    else:
        details = f"Unknown check type: {check_type}"

    # Check for waivers
    waived = False
    waiver_info = None
    if status in ("fail", "not_evaluated"):
        for w in waivers:
            # Match waiver by criterion name or description substring
            waiver_criterion = w.get("criterion", "")
            if (
                criterion["name"] in waiver_criterion
                or waiver_criterion in criterion["name"]
                or criterion.get("description", "") in waiver_criterion
            ):
                waived = True
                waiver_info = w
                break

    if waived:
        status = "waived"
        details += f" [WAIVED: {waiver_info.get('justification', 'no justification')}]"

    # Build the evidence file path for the report
    evidence_path = None
    if criterion.get("evidence_file"):
        for search_dir in [evidence_dir, analysis_dir]:
            if search_dir:
                candidate = os.path.join(search_dir, criterion["evidence_file"])
                if os.path.exists(candidate):
                    evidence_path = candidate
                    break

    return {
        "name": criterion["name"],
        "description": criterion.get("description", ""),
        "threshold": format_threshold(criterion),
        "actual": actual,
        "status": status,
        "evidence_file": evidence_path,
        "details": details,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Gate Check Orchestration
# ═══════════════════════════════════════════════════════════════════════════

def check_module_gate(
    state: Dict[str, Any],
    module_path: str,
    evidence_dir: str,
    analysis_dir: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run all gate criteria for a single module's next phase transition."""
    modules = state.get("modules", {})
    if module_path not in modules:
        return {
            "scope": "module",
            "scope_name": module_path,
            "error": f"Module not found: {module_path}",
        }

    module_state = modules[module_path]
    current_phase = module_state.get("current_phase", 0)
    target_phase = current_phase + 1

    if target_phase > 5:
        return {
            "scope": "module",
            "scope_name": module_path,
            "current_phase": current_phase,
            "target_phase": None,
            "result": "pass",
            "criteria": [],
            "summary": {"total_criteria": 0, "passed": 0, "failed": 0, "waived": 0, "not_evaluated": 0},
            "details": "Module is at phase 5 (final phase). No further advancement.",
        }

    criteria = get_criteria_for_transition(current_phase, config)
    waivers = state.get("waivers", [])

    # Filter waivers relevant to this phase and module
    relevant_waivers = [
        w for w in waivers
        if w.get("phase") == target_phase
        and (w.get("module") is None or w.get("module") == module_path)
    ]

    results = []
    for criterion in criteria:
        result = evaluate_criterion(
            criterion, state, module_state,
            evidence_dir, analysis_dir,
            relevant_waivers, current_phase,
        )
        results.append(result)

    # Summarize
    passed = sum(1 for r in results if r["status"] == "pass")
    failed = sum(1 for r in results if r["status"] == "fail")
    waived = sum(1 for r in results if r["status"] == "waived")
    not_evaluated = sum(1 for r in results if r["status"] == "not_evaluated")

    if failed > 0 or not_evaluated > 0:
        overall = "fail"
    elif waived > 0:
        overall = "pass_with_waivers"
    else:
        overall = "pass"

    return {
        "scope": "module",
        "scope_name": module_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_phase": current_phase,
        "target_phase": target_phase,
        "result": overall,
        "criteria": results,
        "waivers_applied": relevant_waivers,
        "summary": {
            "total_criteria": len(results),
            "passed": passed,
            "failed": failed,
            "waived": waived,
            "not_evaluated": not_evaluated,
        },
    }


def check_unit_gate(
    state: Dict[str, Any],
    unit_name: str,
    evidence_dir: str,
    analysis_dir: str,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run gate checks for all modules in a conversion unit."""
    units = state.get("conversion_units", {})
    if unit_name not in units:
        return {
            "scope": "unit",
            "scope_name": unit_name,
            "error": f"Conversion unit not found: {unit_name}",
        }

    unit = units[unit_name]
    members = unit.get("modules", [])
    member_results = []

    for mod_path in members:
        result = check_module_gate(state, mod_path, evidence_dir, analysis_dir, config)
        member_results.append(result)

    # Unit passes only if ALL members pass
    all_pass = all(r.get("result") in ("pass", "pass_with_waivers") for r in member_results)
    any_waiver = any(r.get("result") == "pass_with_waivers" for r in member_results)

    if all_pass and any_waiver:
        overall = "pass_with_waivers"
    elif all_pass:
        overall = "pass"
    else:
        overall = "fail"

    total_criteria = sum(r.get("summary", {}).get("total_criteria", 0) for r in member_results)
    total_passed = sum(r.get("summary", {}).get("passed", 0) for r in member_results)
    total_failed = sum(r.get("summary", {}).get("failed", 0) for r in member_results)
    total_waived = sum(r.get("summary", {}).get("waived", 0) for r in member_results)
    total_not_eval = sum(r.get("summary", {}).get("not_evaluated", 0) for r in member_results)

    return {
        "scope": "unit",
        "scope_name": unit_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "current_phase": unit.get("current_phase", 0),
        "target_phase": unit.get("current_phase", 0) + 1,
        "result": overall,
        "member_results": member_results,
        "summary": {
            "total_members": len(members),
            "members_passing": sum(1 for r in member_results if r.get("result") in ("pass", "pass_with_waivers")),
            "members_failing": sum(1 for r in member_results if r.get("result") == "fail"),
            "total_criteria": total_criteria,
            "passed": total_passed,
            "failed": total_failed,
            "waived": total_waived,
            "not_evaluated": total_not_eval,
        },
    }


def check_all_gates(
    state: Dict[str, Any],
    evidence_dir: str,
    analysis_dir: str,
    config: Optional[Dict[str, Any]] = None,
    target_phase: Optional[int] = None,
) -> Dict[str, Any]:
    """Run gate checks across all modules, optionally filtering by current phase."""
    modules = state.get("modules", {})
    module_results = []

    for mod_path, mod in sorted(modules.items()):
        current = mod.get("current_phase", 0)
        if target_phase is not None and current != target_phase:
            continue
        # Only check modules that aren't already at the final phase
        if current >= 5:
            continue
        result = check_module_gate(state, mod_path, evidence_dir, analysis_dir, config)
        module_results.append(result)

    can_advance = [r for r in module_results if r.get("result") in ("pass", "pass_with_waivers")]
    cannot_advance = [r for r in module_results if r.get("result") == "fail"]

    return {
        "scope": "all",
        "scope_name": f"phase {target_phase}" if target_phase is not None else "all phases",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "result": "pass" if not cannot_advance else "fail",
        "module_results": module_results,
        "summary": {
            "total_checked": len(module_results),
            "can_advance": len(can_advance),
            "cannot_advance": len(cannot_advance),
            "by_phase": _count_by_phase(module_results),
        },
    }


def _count_by_phase(results: List[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    """Count pass/fail by phase transition."""
    by_phase: Dict[str, Dict[str, int]] = {}
    for r in results:
        key = f"{r.get('current_phase', '?')}_to_{r.get('target_phase', '?')}"
        if key not in by_phase:
            by_phase[key] = {"pass": 0, "fail": 0, "pass_with_waivers": 0}
        result = r.get("result", "fail")
        by_phase[key][result] = by_phase[key].get(result, 0) + 1
    return by_phase


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Check gate criteria for migration phase advancement."
    )
    parser.add_argument(
        "state_file",
        help="Path to migration-state.json",
    )

    scope_group = parser.add_mutually_exclusive_group(required=True)
    scope_group.add_argument("--module", help="Module path to check")
    scope_group.add_argument("--unit", help="Conversion unit name to check")
    scope_group.add_argument("--all", action="store_true", help="Check all modules")

    parser.add_argument(
        "--phase",
        type=int,
        default=None,
        help="Only check modules at this phase (with --all)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for gate-check-report.json",
    )
    parser.add_argument(
        "--gate-config",
        default=None,
        help="Path to gate-config.json for custom thresholds",
    )
    parser.add_argument(
        "--analysis-dir",
        default=None,
        help="Directory containing Phase 0 outputs (for file-existence checks)",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="Directory containing gate evidence files",
    )

    args = parser.parse_args()

    # Load the migration state
    state = load_json_required(args.state_file, "migration state")

    # Load optional gate config
    config = None
    if args.gate_config:
        config = load_json(args.gate_config)
        if config is None:
            print(f"Warning: Gate config not found: {args.gate_config}", file=sys.stderr)

    # Determine evidence and analysis directories
    evidence_dir = args.evidence_dir or args.output
    analysis_dir = args.analysis_dir or os.path.dirname(os.path.abspath(args.state_file))

    # Run the appropriate check
    if args.module:
        report = check_module_gate(state, args.module, evidence_dir, analysis_dir, config)
    elif args.unit:
        report = check_unit_gate(state, args.unit, evidence_dir, analysis_dir, config)
    else:
        report = check_all_gates(
            state, evidence_dir, analysis_dir, config, target_phase=args.phase
        )

    # Write the report
    os.makedirs(args.output, exist_ok=True)
    output_path = os.path.join(args.output, "gate-check-report.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Print summary
    result = report.get("result", "unknown")
    summary = report.get("summary", {})
    scope = report.get("scope", "?")
    scope_name = report.get("scope_name", "?")

    result_marker = {"pass": "✅", "pass_with_waivers": "⚠️", "fail": "❌"}.get(result, "?")

    print(f"{result_marker} Gate check: {result.upper()}")
    print(f"  Scope: {scope} — {scope_name}")

    if scope == "module":
        print(
            f"  Phase {report.get('current_phase', '?')} → "
            f"{report.get('target_phase', '?')}"
        )
        print(
            f"  Criteria: {summary.get('passed', 0)} passed, "
            f"{summary.get('failed', 0)} failed, "
            f"{summary.get('waived', 0)} waived, "
            f"{summary.get('not_evaluated', 0)} not evaluated"
        )
    elif scope == "unit":
        print(
            f"  Members: {summary.get('members_passing', 0)} passing, "
            f"{summary.get('members_failing', 0)} failing"
        )
    elif scope == "all":
        print(
            f"  Modules: {summary.get('can_advance', 0)} can advance, "
            f"{summary.get('cannot_advance', 0)} cannot"
        )

    print(f"  Report: {output_path}")


if __name__ == "__main__":
    main()
