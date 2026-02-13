#!/usr/bin/env python3
"""
Dynamic Pattern Report Generator

Reads dynamic-pattern-report.json and manual-review-needed.json,
generates human-readable markdown summary with recommendations.

Usage:
    python3 generate_pattern_report.py <output_dir>

Output:
    <output_dir>/dynamic-pattern-summary.md — Markdown report
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict


# ── Report Templates ────────────────────────────────────────────────────────

PATTERN_DESCRIPTIONS = {
    "metaclass": "Class metaclass redefinition",
    "nonzero": "Truthiness test method",
    "unicode": "Unicode string representation",
    "div": "Division operator",
    "getslice": "Slice protocol methods",
    "cmp": "Comparison method",
    "hash": "Hash method requirement",
    "map_filter_zip": "Iterator-returning functions",
    "dict_views": "Dictionary view methods",
    "sorted_cmp": "Sorted with comparison function",
    "reduce": "Reduction function",
    "apply": "Function application with unpacking",
    "buffer": "Memory buffer creation",
    "cmp_builtin": "Comparison builtin function",
    "execfile": "File execution",
    "reload": "Module reloading",
    "division": "Integer division ambiguity",
}


class PatternReporter:
    """Generate markdown report from pattern analysis."""

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.report_file = self.output_dir / "dynamic-pattern-report.json"
        self.review_file = self.output_dir / "manual-review-needed.json"

        # Load reports
        self.report = {}
        self.manual_review = []

        if self.report_file.exists():
            with open(self.report_file) as f:
                self.report = json.load(f)

        if self.review_file.exists():
            with open(self.review_file) as f:
                self.manual_review = json.load(f)

    def generate(self) -> str:
        """Generate markdown report."""
        sections = []

        sections.append(self._header())
        sections.append(self._summary())
        sections.append(self._category_breakdown())
        sections.append(self._auto_fixed_items())
        sections.append(self._manual_review_items())
        sections.append(self._recommendations())

        return "\n".join(sections)

    def _header(self) -> str:
        """Generate header section."""
        return """# Dynamic Pattern Resolution Report

Semantic Python 2→3 pattern analysis and resolution results.
"""

    def _summary(self) -> str:
        """Generate summary statistics."""
        total_patterns = sum(self.report.get("patterns_found", {}).values())
        total_fixed = sum(self.report.get("patterns_auto_fixed", {}).values())
        total_review = sum(self.report.get("patterns_needing_review", {}).values())
        files_analyzed = self.report.get("files_analyzed", 0)

        target_version = self.report.get("target_version", "3.9")
        timestamp = self.report.get("timestamp", "N/A")

        lines = [
            "# ── Summary ──────────────────────────────────────────────────────",
            "",
            f"**Target Python Version**: {target_version}",
            f"**Analysis Date**: {timestamp}",
            f"**Files Analyzed**: {files_analyzed}",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Total Patterns Found | {total_patterns} |",
            f"| Auto-Fixed | {total_fixed} |",
            f"| Needing Manual Review | {total_review} |",
            f"| Success Rate | {total_fixed}/{total_patterns} ({100*total_fixed//max(1, total_patterns)}%) |",
            "",
        ]

        return "\n".join(lines)

    def _category_breakdown(self) -> str:
        """Generate per-category breakdown."""
        found = self.report.get("patterns_found", {})
        fixed = self.report.get("patterns_auto_fixed", {})
        review = self.report.get("patterns_needing_review", {})

        lines = [
            "# ── Pattern Categories ──────────────────────────────────────────",
            "",
            "| Pattern Type | Found | Fixed | Needs Review |",
            "|--------------|-------|-------|--------------|",
        ]

        for pattern_type in sorted(found.keys()):
            count_found = found.get(pattern_type, 0)
            count_fixed = fixed.get(pattern_type, 0)
            count_review = review.get(pattern_type, 0)
            description = PATTERN_DESCRIPTIONS.get(pattern_type, pattern_type)
            lines.append(
                f"| {description} | {count_found} | {count_fixed} | {count_review} |"
            )

        lines.append("")
        return "\n".join(lines)

    def _auto_fixed_items(self) -> str:
        """List auto-fixed items by category."""
        lines = [
            "# ── Auto-Fixed Patterns ──────────────────────────────────────────",
            "",
        ]

        # Group by pattern type
        by_type = defaultdict(list)
        for filename, file_info in self.report.get("files", {}).items():
            if file_info.get("status") == "processed":
                for pattern_type, patterns in file_info.get("patterns_by_type", {}).items():
                    for p in patterns:
                        if "resolution" in p:
                            by_type[pattern_type].append({
                                "file": filename,
                                "pattern": p["pattern"],
                                "resolution": p["resolution"],
                            })

        for pattern_type in sorted(by_type.keys()):
            items = by_type[pattern_type]
            description = PATTERN_DESCRIPTIONS.get(pattern_type, pattern_type)
            lines.append(f"## {description}")
            lines.append("")

            for item in items[:5]:  # Show first 5 examples
                lineno = item["pattern"].get("lineno", "?")
                lines.append(f"**File**: {item['file']}:{lineno}")
                resolution = item["resolution"]
                if isinstance(resolution, dict):
                    for key, value in resolution.items():
                        if key != "action":
                            lines.append(f"  - {key}: {value}")
                lines.append("")

            if len(items) > 5:
                lines.append(f"... and {len(items) - 5} more")
                lines.append("")

        return "\n".join(lines)

    def _manual_review_items(self) -> str:
        """List items needing manual review."""
        if not self.manual_review:
            return "# ── Manual Review Items ──────────────────────────────────────────\n\nNone.\n\n"

        lines = [
            "# ── Manual Review Items ──────────────────────────────────────────",
            "",
        ]

        by_type = defaultdict(list)
        for item in self.manual_review:
            pattern_type = item.get("type")
            by_type[pattern_type].append(item)

        for pattern_type in sorted(by_type.keys()):
            items = by_type[pattern_type]
            description = PATTERN_DESCRIPTIONS.get(pattern_type, pattern_type)
            lines.append(f"## {description}")
            lines.append("")

            for item in items[:5]:
                lineno = item.get("line", "?")
                filename = item.get("file", "?")
                lines.append(f"**{filename}:{lineno}**")
                lines.append(f"  - Reason: {item.get('reason', 'Unknown')}")
                if "pattern" in item and isinstance(item["pattern"], dict):
                    context = item["pattern"].get("context", "")
                    if context:
                        context_lines = context.split("\n")
                        for ctx_line in context_lines[:3]:
                            lines.append(f"    {ctx_line}")
                lines.append("")

            if len(items) > 5:
                lines.append(f"... and {len(items) - 5} more")
                lines.append("")

        return "\n".join(lines)

    def _recommendations(self) -> str:
        """Generate recommendations."""
        lines = [
            "# ── Recommendations ──────────────────────────────────────────────",
            "",
        ]

        total_patterns = sum(self.report.get("patterns_found", {}).values())
        total_fixed = sum(self.report.get("patterns_auto_fixed", {}).values())
        total_review = sum(self.report.get("patterns_needing_review", {}).values())

        if total_patterns == 0:
            lines.append("No patterns found. Code appears to be Py3-compatible.")
        elif total_review == 0:
            lines.append(
                f"✓ All {total_fixed} patterns have been auto-fixed. "
                "Run tests to validate correctness."
            )
        else:
            lines.append(
                f"⚠ {total_review}/{total_patterns} patterns require manual review. "
                "See Manual Review Items above."
            )
            lines.append("")
            lines.append("**Next Steps**:")
            lines.append("1. Review items flagged for manual analysis")
            lines.append("2. Assess code context and business logic")
            lines.append("3. Apply appropriate fixes (or update tool if needed)")
            lines.append("4. Run full test suite to validate")
            lines.append("5. Update conversion state file with decisions")

        lines.append("")
        return "\n".join(lines)

    def write(self, filepath: str) -> None:
        """Write report to file."""
        report_md = self.generate()
        with open(filepath, "w") as f:
            f.write(report_md)
        print(f"Report written to {filepath}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 generate_pattern_report.py <output_dir>")
        sys.exit(1)

    output_dir = sys.argv[1]
    reporter = PatternReporter(output_dir)
    report_path = Path(output_dir) / "dynamic-pattern-summary.md"
    reporter.write(str(report_path))


if __name__ == "__main__":
    main()
