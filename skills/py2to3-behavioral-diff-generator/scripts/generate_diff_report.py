#!/usr/bin/env python3
"""
Behavioral Diff Report Generator

Generates a comprehensive markdown report from behavioral-diff-report.json,
expected-differences.json, and potential-bugs.json.

Usage:
    python3 generate_diff_report.py \
        --diff-report <behavioral-diff-report.json> \
        [--output <behavioral-diff-report.md>]

Outputs:
    Markdown report summarizing all behavioral differences, categorized as
    expected or potential bugs, with investigation guidance.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
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


def generate_header(report: Dict[str, Any]) -> str:
    """Generate report header with summary metrics."""
    summary = report.get("summary", {})
    total = summary.get("total_tests", 0)
    no_diffs = summary.get("tests_no_diffs", 0)
    expected_only = summary.get("tests_expected_diffs_only", 0)
    bugs = summary.get("tests_with_potential_bugs", 0)
    pass_rate = summary.get("pass_rate", 0)
    total_expected = summary.get("total_expected_diffs", 0)
    total_bugs = summary.get("total_potential_bugs", 0)

    if bugs == 0:
        status_icon = "PASS"
        status_note = "All behavioral differences are expected Py2/Py3 changes."
    else:
        status_icon = "FAIL"
        status_note = f"{bugs} test(s) have unexpected behavioral differences that need investigation."

    header = f"""# Behavioral Diff Report

**Generated:** {report.get("timestamp", "unknown")}
**Target Version:** Python {report.get("target_version", "3.x")}
**Status:** {status_icon}

> {status_note}

## Summary

| Metric | Count |
|--------|-------|
| Total tests executed | {total} |
| Tests with no diffs | {no_diffs} |
| Tests with expected diffs only | {expected_only} |
| Tests with potential bugs | {bugs} |
| Total expected diffs | {total_expected} |
| Total potential bugs | {total_bugs} |
| **Pass rate** | **{pass_rate:.1f}%** |

"""
    return header


def generate_diff_type_breakdown(report: Dict[str, Any]) -> str:
    """Generate breakdown by diff type."""
    diff_types = report.get("diff_types", {})
    bug_types = report.get("bug_types", {})

    if not diff_types:
        return ""

    section = "## Differences by Type\n\n"
    section += "| Type | Total Diffs | Potential Bugs |\n"
    section += "|------|-------------|----------------|\n"

    for dtype in sorted(diff_types.keys()):
        total = diff_types[dtype]
        bugs = bug_types.get(dtype, 0)
        marker = " ⚠" if bugs > 0 else ""
        section += f"| {dtype} | {total} | {bugs}{marker} |\n"

    section += "\n"
    return section


def generate_potential_bugs_section(report: Dict[str, Any]) -> str:
    """Generate detailed section for potential bugs."""
    test_results = report.get("test_results", [])
    bug_tests = [tr for tr in test_results if tr.get("has_unexpected_diffs")]

    if not bug_tests:
        return "## Potential Bugs\n\nNo potential bugs found. All differences are expected.\n\n"

    section = f"## Potential Bugs\n\n**{len(bug_tests)} test(s) with unexpected differences:**\n\n"

    for tr in bug_tests:
        test_id = tr.get("test_id", "unknown")
        section += f"### `{test_id}`\n\n"

        bug_diffs = [d for d in tr.get("diffs", []) if d.get("category") == "potential_bug"]
        for diff in bug_diffs:
            diff_type = diff.get("type", "unknown")
            description = diff.get("description", "No description")

            section += f"**Type:** {diff_type}\n\n"
            section += f"**Description:** {description}\n\n"

            # Show Py2 vs Py3 values/snippets
            if "py2_value" in diff and "py3_value" in diff:
                section += f"- **Py2 value:** `{diff['py2_value']}`\n"
                section += f"- **Py3 value:** `{diff['py3_value']}`\n\n"
            if "py2_snippet" in diff:
                section += f"**Py2 output:**\n```\n{diff['py2_snippet'][:500]}\n```\n\n"
            if "py3_snippet" in diff:
                section += f"**Py3 output:**\n```\n{diff['py3_snippet'][:500]}\n```\n\n"
            if "py2_seconds" in diff:
                section += (
                    f"- **Py2 time:** {diff['py2_seconds']:.3f}s\n"
                    f"- **Py3 time:** {diff['py3_seconds']:.3f}s\n\n"
                )

        section += "---\n\n"

    return section


def generate_expected_diffs_section(report: Dict[str, Any]) -> str:
    """Generate summary of expected differences."""
    test_results = report.get("test_results", [])
    expected_tests = [
        tr for tr in test_results
        if tr.get("expected_count", 0) > 0 and not tr.get("has_unexpected_diffs")
    ]

    if not expected_tests:
        return "## Expected Differences\n\nNo expected differences found.\n\n"

    section = f"## Expected Differences\n\n"
    section += f"**{len(expected_tests)} test(s) with only expected differences:**\n\n"

    # Group by pattern type
    pattern_counts = Counter()
    for tr in expected_tests:
        for diff in tr.get("diffs", []):
            if diff.get("category") == "expected":
                for p in diff.get("patterns_matched", []):
                    pattern_counts[p] += 1
                if not diff.get("patterns_matched"):
                    pattern_counts[diff.get("type", "other")] += 1

    section += "### Patterns Matched\n\n"
    section += "| Pattern | Count |\n"
    section += "|---------|-------|\n"
    for pattern, count in pattern_counts.most_common():
        section += f"| {pattern} | {count} |\n"
    section += "\n"

    # List tests with expected diffs
    section += "### Tests with Expected Diffs\n\n"
    for tr in expected_tests[:20]:  # Cap at 20 to keep report readable
        test_id = tr.get("test_id", "unknown")
        count = tr.get("expected_count", 0)
        section += f"- `{test_id}` — {count} expected diff(s)\n"

    if len(expected_tests) > 20:
        section += f"\n... and {len(expected_tests) - 20} more tests\n"

    section += "\n"
    return section


def generate_clean_tests_section(report: Dict[str, Any]) -> str:
    """Generate section for tests with no diffs."""
    test_results = report.get("test_results", [])
    clean_tests = [tr for tr in test_results if tr.get("total_diffs", 0) == 0]

    summary = report.get("summary", {})
    total = summary.get("total_tests", 0)

    if not clean_tests:
        return ""

    section = f"## Clean Tests (No Diffs)\n\n"
    section += f"**{len(clean_tests)} of {total} tests** produced identical output under both interpreters.\n\n"

    if len(clean_tests) <= 30:
        for tr in clean_tests:
            section += f"- `{tr.get('test_id', 'unknown')}`\n"
    else:
        section += f"All {len(clean_tests)} tests listed in behavioral-diff-report.json.\n"

    section += "\n"
    return section


def generate_investigation_guide(report: Dict[str, Any]) -> str:
    """Generate investigation guide for potential bugs."""
    summary = report.get("summary", {})
    bugs = summary.get("total_potential_bugs", 0)
    bug_types = report.get("bug_types", {})

    if bugs == 0:
        return ""

    section = "## Investigation Guide\n\n"
    section += "For each potential bug, follow these steps:\n\n"

    if bug_types.get("returncode", 0) > 0:
        section += """### Return Code Differences

1. Check the Py3 stderr output for the specific error message
2. Common causes:
   - `TypeError: cannot use a bytes-like object` → bytes/str boundary issue
   - `ModuleNotFoundError` → library not installed or renamed in Py3
   - `SyntaxError` → unconverted Py2 syntax
3. Cross-reference with bytes-str-fixes.json and library-replacements.json
4. Fix the root cause, then re-run the behavioral diff

"""

    if bug_types.get("stdout", 0) > 0:
        section += """### Stdout Differences

1. Compare the Py2 and Py3 snippets in the diff record
2. Common causes:
   - Integer division: `7/2 = 3` (Py2) vs `3.5` (Py3) — add `//` operator
   - Sort order: mixed-type sorting fails in Py3 — add key function
   - Encoding: `str(bytes_obj)` produces `b'...'` in Py3 — add `.decode()`
3. Check if the difference matters for downstream consumers
4. If expected, add to expected-diffs-config.json

"""

    if bug_types.get("stderr", 0) > 0:
        section += """### Stderr Differences

1. Check for new exceptions or errors not present in Py2 run
2. Common causes:
   - `ResourceWarning` for unclosed files (new in Py3)
   - `DeprecationWarning` for removed features
   - Encoding errors on non-UTF-8 data
3. Warnings may be safe to ignore; errors need fixing

"""

    if bug_types.get("file_output", 0) > 0:
        section += """### File Output Differences

1. Compare the actual file contents (not just size)
2. For binary files: check byte-by-byte
3. For text files: check encoding, line endings, dict ordering in serialized output
4. For protocol/SCADA data: verify byte-level correctness is preserved

"""

    return section


def generate_next_steps(report: Dict[str, Any]) -> str:
    """Generate next steps section."""
    summary = report.get("summary", {})
    bugs = summary.get("total_potential_bugs", 0)

    section = "## Next Steps\n\n"

    if bugs == 0:
        section += "All behavioral diffs are expected. The codebase is ready for:\n\n"
        section += "1. Run encoding stress tests (Skill 4.3) for adversarial input coverage\n"
        section += "2. Run migration completeness checker (Skill 4.4) for remaining artifacts\n"
        section += "3. Run performance benchmarker (Skill 4.2) for regression detection\n"
        section += "4. Run the Phase 4→5 gate check (Skill X.3)\n"
    else:
        section += f"**{bugs} potential bug(s) must be resolved before Phase 4→5 advancement:**\n\n"
        section += "1. Investigate each potential bug in the 'Potential Bugs' section above\n"
        section += "2. For each bug:\n"
        section += "   - Determine root cause (bytes/str, division, sort order, etc.)\n"
        section += "   - Apply fix using appropriate Phase 3 skill\n"
        section += "   - Or classify as expected and add to expected-diffs-config.json\n"
        section += "3. Re-run behavioral diff generator to verify fixes\n"
        section += "4. Repeat until zero unexpected diffs\n"

    section += "\n"
    return section


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate markdown behavioral diff report from JSON output"
    )
    parser.add_argument(
        "--diff-report", required=True,
        help="Path to behavioral-diff-report.json",
    )
    parser.add_argument(
        "--output", default="behavioral-diff-report.md",
        help="Output markdown file (default: behavioral-diff-report.md)",
    )

    args = parser.parse_args()

    print("# ── Loading JSON Report ──────────────────────────────────────", file=sys.stdout)
    report = load_json(args.diff_report)

    print("# ── Generating Markdown Report ───────────────────────────────", file=sys.stdout)

    md = ""
    md += generate_header(report)
    md += generate_diff_type_breakdown(report)
    md += generate_potential_bugs_section(report)
    md += generate_expected_diffs_section(report)
    md += generate_clean_tests_section(report)
    md += generate_investigation_guide(report)
    md += generate_next_steps(report)

    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"Wrote report to {output_path}", file=sys.stdout)
    print("Done.", file=sys.stdout)


if __name__ == "__main__":
    main()
