#!/usr/bin/env python3
"""
Serialization Report Generator

Reads serialization-report.json and generates a human-readable Markdown report
with findings, risk breakdown, and remediation recommendations.

Usage:
    python3 generate_serialization_report.py \
        <output_dir>/serialization-report.json \
        --output <output_dir>/serialization-report.md
"""

import json
import sys
import argparse
import os
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any


# ── Helper Functions ─────────────────────────────────────────────────────────

def load_json(path: str) -> Dict:
    """Load JSON file, return empty dict if not found."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def format_number(n: int) -> str:
    """Format a number with comma separators."""
    return f"{n:,}"


def categorize_findings(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """Group findings by category."""
    by_category = defaultdict(list)
    for finding in findings:
        by_category[finding["category"]].append(finding)
    return by_category


def group_by_risk(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """Group findings by risk level."""
    by_risk = defaultdict(list)
    for finding in findings:
        by_risk[finding["risk"]].append(finding)
    return by_risk


def group_by_file(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """Group findings by file."""
    by_file = defaultdict(list)
    for finding in findings:
        by_file[finding["file"]].append(finding)
    return by_file


def get_remediation_advice(category: str, risk: str) -> str:
    """Get specific remediation advice based on category and risk."""
    advice_map = {
        "pickle": {
            "CRITICAL": "Immediately audit pickle.load() calls. Add `encoding='latin1'` or `encoding='bytes'` parameter to safely load Py2 pickle data. Plan for data migration (read old format, re-save in Py3 protocol 4).",
            "HIGH": "Add `encoding=` parameter to all pickle.load() calls. Update cPickle imports to pickle.",
            "MEDIUM": "Review protocol version usage. Py3 uses protocol 3+ by default; Py2 data must be loaded with proper encoding.",
            "LOW": "Standard pickle usage; ensure encoding parameter is present.",
        },
        "marshal": {
            "CRITICAL": "BLOCKER: marshal is not suitable for persistent data. Code must be refactored to use pickle or another format. Plan significant refactoring.",
            "HIGH": "marshal usage should be replaced with pickle.",
            "MEDIUM": "",
            "LOW": "",
        },
        "shelve": {
            "CRITICAL": "",
            "HIGH": "Test shelve database compatibility with Py3 target version. The underlying DBM format may differ. Plan migration: read with Py2, migrate to pickle or sqlite3.",
            "MEDIUM": "Review shelve usage and test with Py3.",
            "LOW": "",
        },
        "json": {
            "CRITICAL": "",
            "HIGH": "Ensure no non-string keys in JSON objects. JSON is text-safe; Py3 compatibility should be straightforward.",
            "MEDIUM": "",
            "LOW": "JSON is text-based and Py3-safe. No action needed.",
        },
        "yaml": {
            "CRITICAL": "SECURITY ISSUE: yaml.load() without Loader allows arbitrary code execution. Replace with yaml.safe_load() immediately.",
            "HIGH": "Use yaml.safe_load() instead of yaml.load().",
            "MEDIUM": "",
            "LOW": "yaml.safe_load() is safe and Py3-compatible.",
        },
        "msgpack": {
            "CRITICAL": "",
            "HIGH": "",
            "MEDIUM": "Test msgpack pack/unpack with Py3. Check custom type handlers for bytes/string assumptions.",
            "LOW": "Standard msgpack usage should work with Py3; test thoroughly.",
        },
        "protobuf": {
            "CRITICAL": "",
            "HIGH": "",
            "MEDIUM": "",
            "LOW": "protobuf has built-in versioning and Py3 support is solid. No action needed.",
        },
        "struct": {
            "CRITICAL": "",
            "HIGH": "",
            "MEDIUM": "Review struct.pack/unpack for string/bytes mixing. Ensure binary data is not treated as strings.",
            "LOW": "",
        },
        "custom_serialization": {
            "CRITICAL": "",
            "HIGH": "Audit __getstate__, __setstate__, __reduce__ methods for Py3 compatibility. These often assume Py2 object layouts or return bytes vs. strings incorrectly.",
            "MEDIUM": "",
            "LOW": "",
        },
        "binary_io": {
            "CRITICAL": "",
            "HIGH": "",
            "MEDIUM": "Review binary file I/O. Ensure proper handling of bytes vs. strings when reading serialized data.",
            "LOW": "",
        },
    }

    if category in advice_map and risk in advice_map[category]:
        return advice_map[category][risk]
    return "Review for Py3 compatibility."


# ── Report Generation ────────────────────────────────────────────────────────

def generate_report(report_data: Dict, data_migration: Dict) -> str:
    """Generate the full Markdown report."""

    lines = []

    def w(text=""):
        lines.append(text)

    # ── Header ───────────────────────────────────────────────────────────

    w("# Serialization Boundary Detection Report")
    w()
    w(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    w()

    # ── Executive Summary ────────────────────────────────────────────────

    w("## Executive Summary")
    w()

    summary = report_data.get("summary", {})
    codebase = report_data.get("codebase", "unknown")
    target_version = report_data.get("target_version", "unknown")

    w(f"**Codebase**: {codebase}  ")
    w(f"**Target Python Version**: {target_version}  ")
    w(f"**Files Scanned**: {report_data.get('files_scanned', 0)}  ")
    w()

    total_findings = summary.get("total_findings", 0)
    critical = summary.get("critical_count", 0)
    high = summary.get("high_count", 0)
    medium = summary.get("medium_count", 0)
    low = summary.get("low_count", 0)

    w(f"| Severity | Count |")
    w(f"|----------|-------|")
    w(f"| **CRITICAL** | {critical} |")
    w(f"| **HIGH** | {high} |")
    w(f"| **MEDIUM** | {medium} |")
    w(f"| **LOW** | {low} |")
    w(f"| **TOTAL** | {total_findings} |")
    w()

    if critical > 0:
        w("> **CRITICAL ISSUES FOUND**: Do not migrate to Python 3 without addressing these. "
          "These are blockers that will cause data loss or runtime failures.")
        w()

    if high > 0:
        w("> **HIGH-RISK AREAS**: Require careful testing and likely code changes. Plan for "
          "data migration and backward compatibility verification.")
        w()

    # ── Risk Breakdown ───────────────────────────────────────────────────

    w("## Risk Breakdown by Category")
    w()

    findings = report_data.get("findings", [])
    by_category = categorize_findings(findings)

    w("| Category | Critical | High | Medium | Low | Total | Risk Level |")
    w("|----------|----------|------|--------|-----|-------|------------|")

    for category in sorted(by_category.keys()):
        cat_findings = by_category[category]
        cat_crit = sum(1 for f in cat_findings if f["risk"] == "CRITICAL")
        cat_high = sum(1 for f in cat_findings if f["risk"] == "HIGH")
        cat_med = sum(1 for f in cat_findings if f["risk"] == "MEDIUM")
        cat_low = sum(1 for f in cat_findings if f["risk"] == "LOW")
        total = len(cat_findings)

        # Overall risk
        if cat_crit > 0:
            risk_level = "🔴 CRITICAL"
        elif cat_high > 0:
            risk_level = "🟠 HIGH"
        elif cat_med > 0:
            risk_level = "🟡 MEDIUM"
        else:
            risk_level = "🟢 LOW"

        w(f"| {category} | {cat_crit} | {cat_high} | {cat_med} | {cat_low} | {total} | {risk_level} |")

    w()

    # ── Category Details ────────────────────────────────────────────────

    category_descriptions = {
        "pickle": "Python pickle format (most commonly used, high risk due to protocol versions)",
        "marshal": "Python marshal format (unsafe for persistent data, version-sensitive)",
        "shelve": "Database-backed dict interface (DBM format compatibility issues)",
        "json": "JSON text format (generally safe, text-based)",
        "yaml": "YAML format (risk depends on safe_load vs unsafe load)",
        "msgpack": "MessagePack binary format (modern, type handling may have issues)",
        "protobuf": "Protocol Buffers (modern, built-in versioning)",
        "struct": "Binary struct packing (risk from string/bytes mixing)",
        "custom_serialization": "Custom __getstate__/__setstate__/__reduce__ methods (highly variable risk)",
        "binary_io": "Generic binary I/O (may contain serialized data)",
    }

    for category in sorted(by_category.keys()):
        w(f"### {category.capitalize()}")
        w()
        desc = category_descriptions.get(category, "")
        if desc:
            w(f"{desc}")
            w()

        cat_findings = by_category[category]
        w(f"**Count**: {len(cat_findings)} findings")
        w()

        # Group by risk
        by_risk = defaultdict(list)
        for f in cat_findings:
            by_risk[f["risk"]].append(f)

        for risk in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            if risk in by_risk:
                w(f"#### {risk}")
                w()
                for finding in by_risk[risk]:
                    w(f"**File**: `{finding['file']}`  ")
                    w(f"**Line**: {finding.get('line', '?')}  ")
                    w(f"**Code**: `{finding['code']}`  ")
                    w()
                    advice = get_remediation_advice(category, risk)
                    if advice:
                        w(f"**Action**: {advice}")
                        w()

        w()

    # ── Per-File Details ────────────────────────────────────────────────

    w("## Per-File Details")
    w()

    by_file = group_by_file(findings)

    for filepath in sorted(by_file.keys()):
        file_findings = by_file[filepath]
        critical_in_file = sum(1 for f in file_findings if f["risk"] == "CRITICAL")
        high_in_file = sum(1 for f in file_findings if f["risk"] == "HIGH")

        risk_badge = ""
        if critical_in_file > 0:
            risk_badge = "🔴"
        elif high_in_file > 0:
            risk_badge = "🟠"

        w(f"### {risk_badge} `{filepath}`")
        w()
        w(f"**Findings**: {len(file_findings)}")
        w()

        for finding in sorted(file_findings, key=lambda x: x.get("line", 0)):
            w(f"- **Line {finding.get('line', '?')}** [{finding['risk']}] {finding['category']}: {finding['description']}")
            w(f"  ```python")
            w(f"  {finding['code']}")
            w(f"  ```")
            w()

    # ── Data Files ──────────────────────────────────────────────────────

    data_files = report_data.get("data_files_found", [])
    if data_files:
        w("## Data Files Found")
        w()
        w("The following serialized data files were discovered:")
        w()
        w("| Path | Format | Size (bytes) |")
        w("|------|--------|--------------|")
        for data_file in data_files:
            size = data_file.get("size", 0)
            fmt = data_file.get("format", "?")
            path = data_file.get("path", "?")
            w(f"| `{path}` | {fmt} | {format_number(size)} |")
        w()

    # ── Data Migration Plan ──────────────────────────────────────────────

    if data_migration.get("steps"):
        w("## Data Migration Plan")
        w()
        for step in data_migration["steps"]:
            step_num = step.get("step_number", "?")
            action = step.get("action", "")
            effort = step.get("effort", "unknown")
            w(f"### Step {step_num}: {action}")
            w()
            w(f"**Effort**: {effort}")
            w()

            affected = step.get("affected_files", [])
            if affected:
                w("**Affected source files**:")
                for f in affected[:5]:
                    w(f"- `{f}`")
                if len(affected) > 5:
                    w(f"- ... and {len(affected) - 5} more")
                w()

            data_files = step.get("data_files", [])
            if data_files:
                w("**Data files to migrate**:")
                for f in data_files[:5]:
                    w(f"- `{f}`")
                if len(data_files) > 5:
                    w(f"- ... and {len(data_files) - 5} more")
                w()

    # ── Recommendations ────────────────────────────────────────────────

    w("## Recommendations")
    w()

    if critical > 0:
        w(f"1. **IMMEDIATE**: Fix {critical} critical issues before migration")
        w("   - Address all CRITICAL findings first")
        w("   - Do not proceed to Phase 1 until critical issues are resolved")
        w()

    w("2. **AUDIT**: Review all serialization boundaries")
    w("   - Verify pickle.load() calls have encoding= parameter")
    w("   - Test all custom __getstate__/__setstate__ methods with Py3")
    w("   - Check for cPickle imports (must become pickle)")
    w()

    w("3. **DATA MIGRATION**: Plan for persisted data files")
    w(f"   - {len(data_files)} data files found requiring attention")
    w("   - Create backup before attempting any migration")
    w("   - Test read/write with both Py2 and Py3")
    w()

    w("4. **TESTING**: Intensive testing required")
    w("   - Pickle protocol versions must be tested")
    w("   - Shelve database compatibility must be verified")
    w("   - Binary data handling must be tested with non-ASCII data")
    w()

    w("## References")
    w()
    w("- [PEP 3109: Pickle Protocol 3](https://www.python.org/dev/peps/pep-3109/)")
    w("- [Python 3 pickle documentation](https://docs.python.org/3/library/pickle.html)")
    w("- [Bytes/String Migration in Python 3](https://docs.python.org/3/howto/unicode.html)")
    w()

    return "\n".join(lines)


# ── Main Entry Point ────────────────────────────────────────────────────────

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Markdown report from serialization detection"
    )
    parser.add_argument("report_json", help="Path to serialization-report.json")
    parser.add_argument("--migration-json",
                       help="Path to data-migration-plan.json")
    parser.add_argument("--output", help="Output file path (default: stdout)")

    args = parser.parse_args()

    report = load_json(args.report_json)
    if not report:
        print(f"Error: Could not load {args.report_json}", file=sys.stderr)
        sys.exit(1)

    migration = {}
    if args.migration_json:
        migration = load_json(args.migration_json)

    markdown = generate_report(report, migration)

    if args.output:
        os.makedirs(os.path.dirname(args.output), exist_ok=True)
        with open(args.output, "w") as f:
            f.write(markdown)
        print(f"Wrote: {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
