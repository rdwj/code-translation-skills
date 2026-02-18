#!/usr/bin/env python3
"""
Boundary Report Generator

Generates a comprehensive markdown report from bytes-str-fixes.json,
decisions-needed.json, and encoding-annotations.json.

Usage:
    python3 generate_boundary_report.py \
        --fixes <bytes-str-fixes.json> \
        --decisions <decisions-needed.json> \
        --encodings <encoding-annotations.json> \
        [--output <report.md>]

Outputs:
    markdown report summarizing all boundaries, fixes, decisions, and encoding issues.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file."""
    p = Path(path)
    if not p.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_summary_section(
    fixes: Dict[str, Any],
    decisions: Dict[str, Any],
    encodings: Dict[str, Any],
) -> str:
    """Generate summary section of report."""
    total_fixes = fixes.get("total_fixes", 0)
    total_decisions = decisions.get("total_ambiguous", 0)
    total_encodings = encodings.get("total_encoding_ops", 0)

    summary = f"""# Bytes/String Boundary Report

**Generated:** {fixes.get("timestamp", "unknown")}

## Summary

| Metric | Count |
|--------|-------|
| Total boundaries detected | {total_fixes + total_decisions} |
| Automatic fixes applied | {total_fixes} |
| Ambiguous cases (need review) | {total_decisions} |
| Encoding operations found | {total_encodings} |

"""

    # Fix types breakdown
    if fixes.get("fixes_by_type"):
        summary += "### Fixes Applied by Type\n\n"
        for fix_type, count in fixes["fixes_by_type"].items():
            summary += f"- `{fix_type}`: {count}\n"
        summary += "\n"

    return summary


def generate_fixes_section(fixes: Dict[str, Any]) -> str:
    """Generate detailed fixes section."""
    fixes_list = fixes.get("fixes", [])
    if not fixes_list:
        return "## Automatic Fixes Applied\n\nNo fixes applied.\n\n"

    section = "## Automatic Fixes Applied\n\n"

    # Group fixes by file
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for fix in fixes_list:
        file_path = fix.get("file", "unknown")
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(fix)

    for file_path in sorted(by_file.keys()):
        section += f"### `{file_path}`\n\n"
        for fix in by_file[file_path]:
            section += f"**Line {fix.get('line')}** — {fix.get('type', 'unknown')}\n\n"
            section += f"**Rationale:** {fix.get('rationale', 'N/A')}\n\n"
            section += f"**Before:**\n```\n{fix.get('source_before', '')}\n```\n\n"
            section += f"**After:**\n```\n{fix.get('source_after', '')}\n```\n\n"
            section += f"**Confidence:** {fix.get('confidence', 0):.2%}\n\n"

    return section


def generate_decisions_section(decisions: Dict[str, Any]) -> str:
    """Generate decisions-needed section."""
    decisions_list = decisions.get("decisions", [])
    if not decisions_list:
        return "## Decisions Needed\n\nNo ambiguous boundaries requiring human review.\n\n"

    section = f"## Decisions Needed\n\n**{len(decisions_list)} ambiguous boundaries require human review:**\n\n"

    # Group by file
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for decision in decisions_list:
        file_path = decision.get("file", "unknown")
        if file_path not in by_file:
            by_file[file_path] = []
        by_file[file_path].append(decision)

    for file_path in sorted(by_file.keys()):
        section += f"### `{file_path}`\n\n"
        for decision in by_file[file_path]:
            line = decision.get("line", "?")
            boundary_type = decision.get("boundary_type", "unknown")
            section += f"#### Line {line} — {boundary_type}\n\n"

            section += f"**Source:**\n```\n{decision.get('source_code', '')}\n```\n\n"
            section += f"**Context:** {decision.get('context', 'N/A')}\n\n"
            section += (
                f"**Confidence:** "
                f"Bytes: {decision.get('confidence_bytes', 0):.0%}, "
                f"Text: {decision.get('confidence_text', 0):.0%}\n\n"
            )

            # Options
            options = decision.get("options", [])
            if options:
                section += "**Options for Fix:**\n\n"
                for opt in options:
                    section += (
                        f"**Option {opt.get('option', '?')}:** "
                        f"{opt.get('description', 'N/A')}\n\n"
                    )
                    section += (
                        f"_Rationale: {opt.get('rationale', 'N/A')}_\n\n"
                    )

            section += f"**Impact:** {decision.get('impact', 'N/A')}\n\n"
            section += f"**Next Step:** {decision.get('next_step', 'N/A')}\n\n"

    return section


def generate_encodings_section(encodings: Dict[str, Any]) -> str:
    """Generate encoding operations section."""
    annotations = encodings.get("annotations", [])
    if not annotations:
        return "## Encoding Operations\n\nNo encoding operations found.\n\n"

    section = f"## Encoding Operations\n\n**{len(annotations)} encoding operations documented:**\n\n"

    # Group by codec
    by_codec: Dict[str, List[Dict[str, Any]]] = {}
    for ann in annotations:
        codec = ann.get("codec", "unknown")
        if codec not in by_codec:
            by_codec[codec] = []
        by_codec[codec].append(ann)

    for codec in sorted(by_codec.keys()):
        section += f"### Codec: `{codec}`\n\n"
        anns = by_codec[codec]
        section += f"**Count:** {len(anns)}\n\n"

        # Risk summary
        risk_counts = Counter(a.get("risk", "unknown") for a in anns)
        section += "**Risk Levels:**\n\n"
        for risk_level in ["low", "medium", "high"]:
            count = risk_counts.get(risk_level, 0)
            if count > 0:
                section += f"- {risk_level.capitalize()}: {count}\n"
        section += "\n"

        # Details
        section += "**Details:**\n\n"
        for ann in sorted(anns, key=lambda a: a.get("file", "")):
            file_path = ann.get("file", "?")
            line = ann.get("line", "?")
            operation = ann.get("operation", "?")
            risk = ann.get("risk", "?")
            note = ann.get("note", "")

            section += (
                f"- `{file_path}:{line}` — "
                f"**{operation}** "
                f"[Risk: {risk}]\n"
            )
            if note:
                section += f"  - {note}\n"
        section += "\n"

    return section


def generate_risk_summary(
    fixes: Dict[str, Any],
    decisions: Dict[str, Any],
    encodings: Dict[str, Any],
) -> str:
    """Generate overall risk summary."""
    decisions_list = decisions.get("decisions", [])
    annotations = encodings.get("annotations", [])

    # Count risk levels in decisions
    decision_risks = Counter(
        opt.get("impact", "unknown")
        for decision in decisions_list
        for opt in decision.get("options", [])
    )

    # Count risk levels in encodings
    encoding_risks = Counter(a.get("risk", "unknown") for a in annotations)

    section = "## Risk Summary\n\n"
    section += f"**Ambiguous boundaries:** {len(decisions_list)} (require human review)\n"
    section += f"**High-risk encodings:** {encoding_risks.get('high', 0)}\n"
    section += f"**Medium-risk encodings:** {encoding_risks.get('medium', 0)}\n"
    section += f"**Low-risk encodings:** {encoding_risks.get('low', 0)}\n\n"

    if len(decisions_list) > 0:
        section += (
            "**Action Required:** Review and resolve all ambiguous boundaries "
            "before final migration.\n\n"
        )

    return section


def generate_next_steps(decisions: Dict[str, Any]) -> str:
    """Generate next steps section."""
    decisions_list = decisions.get("decisions", [])

    section = "## Next Steps\n\n"

    if len(decisions_list) == 0:
        section += "✓ All boundaries classified with high confidence.\n\n"
        section += "1. Review automatic fixes in `bytes-str-fixes.json`\n"
        section += "2. Run encoding stress tests (Skill 4.3)\n"
        section += "3. Proceed to verification phase\n\n"
    else:
        section += f"⚠️ **{len(decisions_list)} ambiguous boundaries require review:**\n\n"
        section += "1. Review each decision in the 'Decisions Needed' section above\n"
        section += "2. For each ambiguous boundary:\n"
        section += "   - Understand the data source and purpose\n"
        section += "   - Check with domain expert (SCADA, mainframe, serial protocol expert)\n"
        section += "   - Select appropriate option and apply fix manually or with next iteration\n"
        section += "3. After resolving ambiguous cases:\n"
        section += "   - Regenerate this report\n"
        section += "   - Run encoding stress tests (Skill 4.3)\n"
        section += "   - Proceed to verification phase\n\n"

    return section


@log_execution
def main():
    parser = argparse.ArgumentParser(description="Generate boundary report from JSON outputs")
    parser.add_argument("--fixes", required=True, help="Path to bytes-str-fixes.json")
    parser.add_argument("--decisions", required=True, help="Path to decisions-needed.json")
    parser.add_argument("--encodings", required=True, help="Path to encoding-annotations.json")
    parser.add_argument(
        "--output",
        default="bytes-str-boundary-report.md",
        help="Output markdown file (default: bytes-str-boundary-report.md)",
    )

    args = parser.parse_args()

    print("# ── Loading JSON Reports ──────────────────────────────────────", file=sys.stdout)
    fixes = load_json(args.fixes)
    decisions = load_json(args.decisions)
    encodings = load_json(args.encodings)

    print("# ── Generating Report ────────────────────────────────────────", file=sys.stdout)

    report = ""
    report += generate_summary_section(fixes, decisions, encodings)
    report += generate_fixes_section(fixes)
    report += generate_decisions_section(decisions)
    report += generate_encodings_section(encodings)
    report += generate_risk_summary(fixes, decisions, encodings)
    report += generate_next_steps(decisions)

    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"Wrote report to {output_path}", file=sys.stdout)
    print("Done.", file=sys.stdout)


if __name__ == "__main__":
    main()
