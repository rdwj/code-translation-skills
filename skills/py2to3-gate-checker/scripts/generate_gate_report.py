#!/usr/bin/env python3
"""
Gate Checker — Markdown Report Generator

Reads gate-check-report.json and produces a human-readable markdown report
suitable for stakeholder review.

Usage:
    python3 generate_gate_report.py <gate_check_report_json> \
        --output <output_path>

If --output is omitted, prints to stdout.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


PHASE_NAMES = {
    0: "Discovery",
    1: "Foundation",
    2: "Mechanical Conversion",
    3: "Semantic Fixes",
    4: "Verification",
    5: "Cutover",
}

STATUS_MARKERS = {
    "pass": "✅",
    "fail": "❌",
    "waived": "⚠️",
    "not_evaluated": "⬜",
}

RESULT_LABELS = {
    "pass": "PASS",
    "pass_with_waivers": "PASS (with waivers)",
    "fail": "FAIL",
}


def load_report(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        print(f"Error: Report file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Module Report ─────────────────────────────────────────────────────────

def render_module_report(report: Dict[str, Any]) -> str:
    """Render a gate check report for a single module."""
    lines = []
    scope_name = report.get("scope_name", "unknown")
    result = report.get("result", "unknown")
    current = report.get("current_phase", "?")
    target = report.get("target_phase", "?")
    summary = report.get("summary", {})
    timestamp = report.get("timestamp", "")[:19]

    result_marker = STATUS_MARKERS.get(result, "?")
    result_label = RESULT_LABELS.get(result, result)

    lines.append(f"# Gate Check Report: {scope_name}")
    lines.append("")
    lines.append(f"**Result**: {result_marker} {result_label}  ")
    lines.append(
        f"**Transition**: Phase {current} ({PHASE_NAMES.get(current, '?')}) → "
        f"Phase {target} ({PHASE_NAMES.get(target, '?')})  "
    )
    lines.append(f"**Checked**: {timestamp}")
    lines.append("")

    # Summary bar
    total = summary.get("total_criteria", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    waived = summary.get("waived", 0)
    not_eval = summary.get("not_evaluated", 0)

    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Passed | Failed | Waived | Not Evaluated | Total |")
    lines.append(f"|--------|--------|--------|---------------|-------|")
    lines.append(f"| {passed} | {failed} | {waived} | {not_eval} | {total} |")
    lines.append("")

    # Criteria details
    criteria = report.get("criteria", [])
    if criteria:
        lines.append("## Criteria Details")
        lines.append("")

        # Failed and not-evaluated first (most actionable)
        for status_filter, header in [
            ("fail", "Failed"),
            ("not_evaluated", "Not Evaluated"),
            ("waived", "Waived"),
            ("pass", "Passed"),
        ]:
            matching = [c for c in criteria if c.get("status") == status_filter]
            if not matching:
                continue

            marker = STATUS_MARKERS.get(status_filter, "")
            lines.append(f"### {marker} {header} ({len(matching)})")
            lines.append("")

            for c in matching:
                lines.append(f"**{c['name']}** — {c.get('description', '')}")
                lines.append(f"- Threshold: {c.get('threshold', '?')}")
                if c.get("actual") is not None:
                    lines.append(f"- Actual: {c['actual']}")
                if c.get("details"):
                    lines.append(f"- Details: {c['details']}")
                if c.get("evidence_file"):
                    lines.append(f"- Evidence: `{c['evidence_file']}`")
                lines.append("")

    # Waivers
    waivers = report.get("waivers_applied", [])
    if waivers:
        lines.append("## Waivers Applied")
        lines.append("")
        for w in waivers:
            lines.append(
                f"- **{w.get('criterion', '?')}**: {w.get('justification', 'no justification')}"
            )
            lines.append(
                f"  Approved by: {w.get('approved_by', '?')} "
                f"({w.get('timestamp', '?')[:10]})"
            )
        lines.append("")

    # Next steps
    if result == "fail":
        lines.append("## Next Steps")
        lines.append("")
        failed_criteria = [c for c in criteria if c["status"] == "fail"]
        not_eval_criteria = [c for c in criteria if c["status"] == "not_evaluated"]

        if not_eval_criteria:
            lines.append("**Run these skills first** (evidence not yet generated):")
            lines.append("")
            for c in not_eval_criteria:
                evidence = c.get("evidence_file") or c.get("name")
                lines.append(f"- {c['name']}: needs `{evidence}`")
            lines.append("")

        if failed_criteria:
            lines.append("**Fix these issues**:")
            lines.append("")
            for c in failed_criteria:
                lines.append(f"- {c['name']}: {c.get('details', 'see above')}")
            lines.append("")

    return "\n".join(lines)


# ── Unit Report ───────────────────────────────────────────────────────────

def render_unit_report(report: Dict[str, Any]) -> str:
    """Render a gate check report for a conversion unit."""
    lines = []
    unit_name = report.get("scope_name", "unknown")
    result = report.get("result", "unknown")
    summary = report.get("summary", {})
    timestamp = report.get("timestamp", "")[:19]

    result_marker = STATUS_MARKERS.get(result, "?")
    result_label = RESULT_LABELS.get(result, result)

    lines.append(f"# Gate Check Report: Unit '{unit_name}'")
    lines.append("")
    lines.append(f"**Result**: {result_marker} {result_label}  ")
    lines.append(f"**Checked**: {timestamp}")
    lines.append("")

    # Unit summary
    lines.append("## Unit Summary")
    lines.append("")
    lines.append(
        f"| Total Members | Passing | Failing |"
    )
    lines.append(f"|---------------|---------|---------|")
    lines.append(
        f"| {summary.get('total_members', 0)} "
        f"| {summary.get('members_passing', 0)} "
        f"| {summary.get('members_failing', 0)} |"
    )
    lines.append("")

    # Per-member results
    member_results = report.get("member_results", [])
    if member_results:
        lines.append("## Member Results")
        lines.append("")
        for mr in member_results:
            mr_result = mr.get("result", "unknown")
            mr_marker = STATUS_MARKERS.get(mr_result, "?")
            mr_name = mr.get("scope_name", "?")
            mr_summary = mr.get("summary", {})
            lines.append(
                f"- {mr_marker} **{mr_name}** — "
                f"{mr_summary.get('passed', 0)} passed, "
                f"{mr_summary.get('failed', 0)} failed, "
                f"{mr_summary.get('waived', 0)} waived"
            )
        lines.append("")

        # Expand failing members
        failing = [mr for mr in member_results if mr.get("result") == "fail"]
        if failing:
            lines.append("## Failing Members — Details")
            lines.append("")
            for mr in failing:
                lines.append(f"### {mr.get('scope_name', '?')}")
                lines.append("")
                for c in mr.get("criteria", []):
                    if c.get("status") in ("fail", "not_evaluated"):
                        marker = STATUS_MARKERS.get(c["status"], "?")
                        lines.append(f"- {marker} **{c['name']}**: {c.get('details', '')}")
                lines.append("")

    return "\n".join(lines)


# ── All-Modules Report ────────────────────────────────────────────────────

def render_all_report(report: Dict[str, Any]) -> str:
    """Render a comprehensive gate check report across all modules."""
    lines = []
    scope_name = report.get("scope_name", "all")
    result = report.get("result", "unknown")
    summary = report.get("summary", {})
    timestamp = report.get("timestamp", "")[:19]

    result_marker = STATUS_MARKERS.get(result, "?")

    lines.append(f"# Gate Check Report: {scope_name.capitalize()}")
    lines.append("")
    lines.append(f"**Overall**: {result_marker} {RESULT_LABELS.get(result, result)}  ")
    lines.append(f"**Checked**: {timestamp}")
    lines.append("")

    # Overview
    lines.append("## Overview")
    lines.append("")
    lines.append(
        f"| Checked | Can Advance | Cannot Advance |"
    )
    lines.append(f"|---------|-------------|----------------|")
    lines.append(
        f"| {summary.get('total_checked', 0)} "
        f"| {summary.get('can_advance', 0)} "
        f"| {summary.get('cannot_advance', 0)} |"
    )
    lines.append("")

    # Breakdown by phase
    by_phase = summary.get("by_phase", {})
    if by_phase:
        lines.append("## By Phase Transition")
        lines.append("")
        lines.append("| Transition | Pass | Fail | Pass w/ Waivers |")
        lines.append("|------------|------|------|-----------------|")
        for key, counts in sorted(by_phase.items()):
            parts = key.split("_to_")
            if len(parts) == 2:
                try:
                    from_p = int(parts[0])
                    to_p = int(parts[1])
                    label = f"Phase {from_p} → {to_p}"
                except ValueError:
                    label = key
            else:
                label = key
            lines.append(
                f"| {label} "
                f"| {counts.get('pass', 0)} "
                f"| {counts.get('fail', 0)} "
                f"| {counts.get('pass_with_waivers', 0)} |"
            )
        lines.append("")

    # Modules that can advance
    module_results = report.get("module_results", [])
    ready = [mr for mr in module_results if mr.get("result") in ("pass", "pass_with_waivers")]
    blocked = [mr for mr in module_results if mr.get("result") == "fail"]

    if ready:
        lines.append(f"## Ready to Advance ({len(ready)})")
        lines.append("")
        for mr in ready:
            marker = STATUS_MARKERS.get(mr["result"], "?")
            lines.append(
                f"- {marker} {mr.get('scope_name', '?')} "
                f"(Phase {mr.get('current_phase', '?')} → {mr.get('target_phase', '?')})"
            )
        lines.append("")

    if blocked:
        lines.append(f"## Blocked ({len(blocked)})")
        lines.append("")
        for mr in blocked:
            mr_summary = mr.get("summary", {})
            lines.append(
                f"- ❌ **{mr.get('scope_name', '?')}** "
                f"(Phase {mr.get('current_phase', '?')} → {mr.get('target_phase', '?')}) "
                f"— {mr_summary.get('failed', 0)} failed, "
                f"{mr_summary.get('not_evaluated', 0)} not evaluated"
            )
            # Show the specific failures
            for c in mr.get("criteria", []):
                if c.get("status") in ("fail", "not_evaluated"):
                    c_marker = STATUS_MARKERS.get(c["status"], "?")
                    lines.append(f"  - {c_marker} {c['name']}: {c.get('details', '')}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate a markdown report from a gate check JSON report."
    )
    parser.add_argument(
        "report_file",
        help="Path to gate-check-report.json",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for markdown report (prints to stdout if omitted)",
    )

    args = parser.parse_args()
    report = load_report(args.report_file)

    # Route to the appropriate renderer
    scope = report.get("scope", "module")
    if scope == "unit":
        markdown = render_unit_report(report)
    elif scope == "all":
        markdown = render_all_report(report)
    else:
        markdown = render_module_report(report)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"Gate report written to {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
