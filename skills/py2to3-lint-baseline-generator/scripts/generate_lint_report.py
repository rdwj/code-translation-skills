#!/usr/bin/env python3
"""
Lint Baseline Generator — Markdown Report Script

Reads lint-baseline.json and produces a human-readable markdown report
with summary statistics, per-module scores, and a prioritized fix list.

Usage:
    python3 generate_lint_report.py <lint_baseline_json> \
        --output <output_path>
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


def load_baseline(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        print(f"Error: Baseline file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def render_report(baseline: Dict[str, Any], project_name: str = "Python 2 Codebase") -> str:
    lines = []

    total = baseline.get("total_findings", 0)
    files = baseline.get("files_scanned", 0)
    total_lines = baseline.get("total_lines", 0)
    automatable_pct = baseline.get("automatable_percent", 0)
    target = baseline.get("target_version", "3.x")
    timestamp = baseline.get("timestamp", "")[:19]

    lines.append(f"# Lint Baseline Report: {project_name}")
    lines.append("")
    lines.append(f"**Generated**: {timestamp}  ")
    lines.append(f"**Target version**: Python {target}  ")
    lines.append(f"**Files scanned**: {files}  ")
    lines.append(f"**Total lines of code**: {total_lines:,}")
    lines.append("")

    # Executive summary
    lines.append("## Executive Summary")
    lines.append("")
    density = round(total / max(files, 1), 1)
    lines.append(
        f"The linters found **{total:,} findings** across {files} files "
        f"({density} findings per file on average). "
        f"**{automatable_pct}%** of findings are automatable — these can be fixed by "
        f"the Automated Converter (Skill 2.2) without manual review."
    )
    lines.append("")

    # By severity
    by_severity = baseline.get("by_severity", {})
    if by_severity:
        lines.append("## Findings by Severity")
        lines.append("")
        lines.append("| Severity | Count | % of Total |")
        lines.append("|----------|-------|------------|")
        for sev in ["error", "warning", "convention", "info"]:
            count = by_severity.get(sev, 0)
            pct = round(count / max(total, 1) * 100, 1)
            lines.append(f"| {sev.capitalize()} | {count:,} | {pct}% |")
        lines.append("")

    # By category
    by_category = baseline.get("by_category", {})
    if by_category:
        lines.append("## Findings by Category")
        lines.append("")
        lines.append("| Category | Count | % of Total | Migration Phase |")
        lines.append("|----------|-------|------------|-----------------|")
        category_phase_map = {
            "syntax": "Phase 2 (Mechanical)",
            "semantic": "Phase 3 (Semantic)",
            "import": "Phase 2 (Mechanical)",
            "stdlib": "Phase 3 (Library Replacement)",
            "compat": "Phase 3 (Dynamic Patterns)",
        }
        for cat in sorted(by_category.keys(), key=lambda c: by_category[c], reverse=True):
            count = by_category[cat]
            pct = round(count / max(total, 1) * 100, 1)
            phase = category_phase_map.get(cat, "Various")
            lines.append(f"| {cat.capitalize()} | {count:,} | {pct}% | {phase} |")
        lines.append("")

    # By linter
    by_linter = baseline.get("by_linter", {})
    if by_linter:
        lines.append("## Findings by Linter")
        lines.append("")
        lines.append("| Linter | Findings |")
        lines.append("|--------|----------|")
        for linter, count in sorted(by_linter.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"| {linter} | {count:,} |")
        lines.append("")

    # Module scores — top and bottom
    module_scores = baseline.get("module_scores", {})
    if module_scores:
        sorted_scores = sorted(module_scores.items(), key=lambda x: x[1]["score"])

        lines.append("## Module Scores")
        lines.append("")
        lines.append(
            "Scores range from 0 (heavily laden with Py2-isms) to 100 (clean). "
            "Scores factor in finding density and severity."
        )
        lines.append("")

        # Worst modules
        worst = sorted_scores[:15]
        if worst:
            lines.append("### Lowest-Scoring Modules (most work needed)")
            lines.append("")
            lines.append("| Module | Score | Findings | LOC | Automatable |")
            lines.append("|--------|-------|----------|-----|-------------|")
            for path, data in worst:
                lines.append(
                    f"| `{path}` | {data['score']} | {data['total_findings']} "
                    f"| {data['lines_of_code']} | {data['automatable_percent']}% |"
                )
            lines.append("")

        # Best modules
        best = sorted_scores[-10:]
        best.reverse()
        if best:
            lines.append("### Highest-Scoring Modules (least work needed)")
            lines.append("")
            lines.append("| Module | Score | Findings | LOC |")
            lines.append("|--------|-------|----------|-----|")
            for path, data in best:
                lines.append(
                    f"| `{path}` | {data['score']} | {data['total_findings']} "
                    f"| {data['lines_of_code']} |"
                )
            lines.append("")

    # Score distribution
    if module_scores:
        buckets = {"0-25": 0, "26-50": 0, "51-75": 0, "76-100": 0}
        for data in module_scores.values():
            s = data["score"]
            if s <= 25:
                buckets["0-25"] += 1
            elif s <= 50:
                buckets["26-50"] += 1
            elif s <= 75:
                buckets["51-75"] += 1
            else:
                buckets["76-100"] += 1

        lines.append("### Score Distribution")
        lines.append("")
        lines.append("| Range | Modules |")
        lines.append("|-------|---------|")
        for range_label, count in buckets.items():
            bar = "█" * max(1, count // 2)
            lines.append(f"| {range_label} | {count} {bar} |")
        lines.append("")

    # Priority list
    priority_list = baseline.get("priority_list", [])
    if priority_list:
        lines.append("## Prioritized Fix List")
        lines.append("")
        lines.append(
            "Modules ordered by priority: gateway modules (high fan-in) with many "
            "automatable issues rank first."
        )
        lines.append("")
        lines.append("| # | Module | Score | Findings | Automatable | Fan-in |")
        lines.append("|---|--------|-------|----------|-------------|--------|")
        for i, item in enumerate(priority_list[:30], 1):
            lines.append(
                f"| {i} | `{item['module']}` | {item['score']} "
                f"| {item['total_findings']} | {item['automatable_percent']}% "
                f"| {item['fan_in']} |"
            )
        if len(priority_list) > 30:
            lines.append(f"| ... | *{len(priority_list) - 30} more modules* | | | | |")
        lines.append("")

    # Linters used
    linters_used = baseline.get("linters_used", {})
    if linters_used:
        lines.append("## Linters Used")
        lines.append("")
        for name, version in linters_used.items():
            lines.append(f"- **{name}**: {version}")
        lines.append("")

    return "\n".join(lines)


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate a markdown report from a lint baseline."
    )
    parser.add_argument("baseline_file", help="Path to lint-baseline.json")
    parser.add_argument("--output", default=None, help="Output path (stdout if omitted)")
    parser.add_argument("--project-name", default="Python 2 Codebase", help="Project name")

    args = parser.parse_args()
    baseline = load_baseline(args.baseline_file)
    markdown = render_report(baseline, args.project_name)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"Report written to {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
