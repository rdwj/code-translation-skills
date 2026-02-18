#!/usr/bin/env python3
"""
Encoding Stress Report Generator

Generates a comprehensive markdown report from encoding-stress-report.json
and encoding-failures.json.

Usage:
    python3 generate_stress_report.py \
        --stress-report <encoding-stress-report.json> \
        [--output <encoding-stress-report.md>]

Outputs:
    Markdown report summarizing encoding stress test results with pass/fail
    matrix, failure details, and remediation guidance.
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


CATEGORY_NAMES = {
    1: "Valid Baseline",
    2: "Wrong Encoding",
    3: "Malformed Input",
    4: "Boundary Conditions",
    5: "Mixed Encodings",
    6: "Binary-as-Text",
}

CATEGORY_DESCRIPTIONS = {
    1: "Correct encoding inputs that should always pass",
    2: "Data sent with wrong encoding — should error gracefully",
    3: "Deliberately malformed sequences — should reject cleanly",
    4: "Edge cases: empty, single byte, max length, buffer boundaries",
    5: "Multiple encodings in single input — needs split decoding",
    6: "Binary data that coincidentally looks like valid text",
}


def generate_header(report: Dict[str, Any]) -> str:
    """Generate report header with overall status."""
    summary = report.get("summary", {})
    total = summary.get("total_tests", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    pass_rate = summary.get("pass_rate", 0)

    if failed == 0:
        status = "PASS"
        status_note = "All encoding stress tests passed."
    elif pass_rate >= 90:
        status = "PARTIAL"
        status_note = f"{failed} test(s) failed. Review failures before Phase 4→5 advancement."
    else:
        status = "FAIL"
        status_note = f"{failed} test(s) failed. Significant encoding issues remain."

    header = f"""# Encoding Stress Test Report

**Generated:** {report.get("timestamp", "unknown")}
**Target Version:** Python {report.get("target_version", "3.x")}
**Status:** {status}
**Data Paths Scanned:** {report.get("data_paths_scanned", 0)}

> {status_note}

## Overall Summary

| Metric | Count |
|--------|-------|
| Total tests | {total} |
| Passed | {passed} |
| Failed | {failed} |
| **Pass rate** | **{pass_rate:.1f}%** |

"""
    return header


def generate_category_matrix(report: Dict[str, Any]) -> str:
    """Generate pass/fail matrix by category."""
    cat_summary = report.get("category_summary", {})

    if not cat_summary:
        return ""

    section = "## Results by Category\n\n"
    section += "| Category | Description | Total | Passed | Failed | Rate |\n"
    section += "|----------|-------------|-------|--------|--------|------|\n"

    for cat_name in sorted(cat_summary.keys()):
        stats = cat_summary[cat_name]
        total = stats.get("total", 0)
        passed = stats.get("passed", 0)
        failed = stats.get("failed", 0)
        rate = stats.get("pass_rate", 0)
        marker = " ⚠" if failed > 0 else ""
        section += f"| {cat_name} | {CATEGORY_DESCRIPTIONS.get(cat_name, '')} | {total} | {passed} | {failed}{marker} | {rate:.0f}% |\n"

    section += "\n"

    # Category interpretation
    section += "### Category Interpretation\n\n"
    section += "- **Category 1 failures** are critical — if valid baseline data doesn't work, the migration has fundamental issues\n"
    section += "- **Category 2 failures** indicate missing error handling for wrong-encoding data\n"
    section += "- **Category 3 failures** indicate missing input validation for malformed data\n"
    section += "- **Category 4 failures** indicate edge-case handling gaps (empty input, buffer boundaries)\n"
    section += "- **Category 5 failures** indicate the code can't handle mixed-encoding data sources\n"
    section += "- **Category 6 failures** indicate binary data is being accidentally decoded as text\n\n"

    return section


def generate_failures_section(report: Dict[str, Any]) -> str:
    """Generate detailed failures section."""
    results = report.get("results", [])
    failures = [r for r in results if not r.get("passed")]

    if not failures:
        return "## Failures\n\nNo failures. All encoding stress tests passed.\n\n"

    section = f"## Failures ({len(failures)} total)\n\n"

    # Group by category
    by_category = {}
    for f in failures:
        cat = f.get("category", 0)
        cat_name = CATEGORY_NAMES.get(cat, f"Category {cat}")
        by_category.setdefault(cat_name, []).append(f)

    for cat_name in sorted(by_category.keys()):
        cat_failures = by_category[cat_name]
        section += f"### {cat_name} ({len(cat_failures)} failures)\n\n"

        for f in cat_failures:
            vector_id = f.get("vector_id", "unknown")
            vector_name = f.get("vector_name", "unknown")
            encoding = f.get("encoding_tested", "unknown")
            expected = f.get("expected_behavior", "unknown")
            actual = f.get("actual_behavior", "unknown")
            error = f.get("error", "N/A")
            data_hex = f.get("data_hex", "N/A")

            section += f"**{vector_id}**: {vector_name}\n\n"
            section += f"- **Encoding tested:** {encoding}\n"
            section += f"- **Expected:** {expected}\n"
            section += f"- **Actual:** {actual}\n"
            if error and error != "N/A":
                section += f"- **Error:** `{error[:200]}`\n"
            section += f"- **Data (hex):** `{data_hex[:80]}`\n"
            section += "\n"

    return section


def generate_remediation_guide(report: Dict[str, Any]) -> str:
    """Generate remediation guidance based on failure patterns."""
    results = report.get("results", [])
    failures = [r for r in results if not r.get("passed")]

    if not failures:
        return ""

    section = "## Remediation Guide\n\n"

    # Analyze failure patterns
    has_baseline_failures = any(f["category"] == 1 for f in failures)
    has_wrong_encoding = any(f["category"] == 2 for f in failures)
    has_malformed = any(f["category"] == 3 for f in failures)
    has_boundary = any(f["category"] == 4 for f in failures)
    has_mixed = any(f["category"] == 5 for f in failures)
    has_binary_text = any(f["category"] == 6 for f in failures)

    if has_baseline_failures:
        section += """### Fix Baseline Failures First

Category 1 failures indicate fundamental encoding issues:

1. Check that all `open()` calls have explicit `encoding=` parameter
2. Verify EBCDIC paths use `cp500` (or correct variant), not `utf-8`
3. Ensure binary data paths use `'rb'` mode, not text mode
4. Run Skill 3.1 (Bytes/String Boundary Fixer) on affected modules

"""

    if has_wrong_encoding:
        section += """### Add Error Handling for Wrong Encoding

Category 2 failures indicate data paths don't handle wrong-encoding input:

1. Add `errors='strict'` to all `.decode()` calls in data ingestion
2. Wrap decode operations in try/except and log the error with context
3. For SCADA data: add encoding validation before processing
4. Never use `errors='ignore'` on protocol data

"""

    if has_malformed:
        section += """### Add Input Validation for Malformed Data

Category 3 failures indicate missing validation:

1. Validate UTF-8 sequences before processing (reject overlong, surrogates)
2. Add length checks before multi-byte character parsing
3. Handle truncated sequences at end of buffer reads

"""

    if has_binary_text:
        section += """### Fix Binary-as-Text Confusion

Category 6 failures indicate binary data is being decoded as text:

1. Ensure all binary data paths (Modbus, struct, serial) stay as `bytes`
2. Check that `open()` for binary files uses `'rb'` mode
3. Verify `struct.unpack()` input is `bytes`, not `str`
4. Review Skill 3.1 boundary classifications for these paths

"""

    return section


def generate_next_steps(report: Dict[str, Any]) -> str:
    """Generate next steps section."""
    summary = report.get("summary", {})
    failed = summary.get("failed", 0)

    section = "## Next Steps\n\n"

    if failed == 0:
        section += "All encoding stress tests passed. The codebase is ready for:\n\n"
        section += "1. Run behavioral diff generator (Skill 4.1) if not already done\n"
        section += "2. Run migration completeness checker (Skill 4.4)\n"
        section += "3. Run performance benchmarker (Skill 4.2)\n"
        section += "4. Run the Phase 4→5 gate check (Skill X.3)\n"
    else:
        section += f"**{failed} failure(s) must be resolved:**\n\n"
        section += "1. Follow the remediation guide above\n"
        section += "2. Fix the root causes in the affected data paths\n"
        section += "3. Re-run encoding stress tester to verify fixes\n"
        section += "4. Add generated test cases to permanent test suite\n"
        section += "5. Repeat until 100% pass rate\n"

    section += "\n"
    return section


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate markdown encoding stress test report"
    )
    parser.add_argument(
        "--stress-report", required=True,
        help="Path to encoding-stress-report.json",
    )
    parser.add_argument(
        "--output", default="encoding-stress-report.md",
        help="Output markdown file (default: encoding-stress-report.md)",
    )

    args = parser.parse_args()

    print("# ── Loading JSON Report ──────────────────────────────────────", file=sys.stdout)
    report = load_json(args.stress_report)

    print("# ── Generating Markdown Report ───────────────────────────────", file=sys.stdout)

    md = ""
    md += generate_header(report)
    md += generate_category_matrix(report)
    md += generate_failures_section(report)
    md += generate_remediation_guide(report)
    md += generate_next_steps(report)

    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"Wrote report to {output_path}", file=sys.stdout)
    print("Done.", file=sys.stdout)


if __name__ == "__main__":
    main()
