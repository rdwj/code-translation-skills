#!/usr/bin/env python3
"""
Completeness Report Generator

Generates a comprehensive markdown report from completeness-report.json
and cleanup-tasks.json.

Usage:
    python3 generate_completeness_report.py \
        --completeness-report <completeness-report.json> \
        [--output <completeness-report.md>]

Outputs:
    Markdown report summarizing migration completeness with category breakdown,
    finding details, cleanup task list, and remediation guidance.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file."""
    p = Path(path)
    if not p.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


CATEGORY_NAMES = {
    1: "Remaining Py2 Syntax",
    2: "Compatibility Library Usage",
    3: "Unnecessary __future__ Imports",
    4: "Version Guard Patterns",
    5: "Migration TODO/FIXME Comments",
    6: "Type Ignore Comments",
    7: "Encoding Declarations",
    8: "Dual-Compatibility Patterns",
    9: "Deprecated Stdlib Usage",
    10: "Lint Compliance",
}

CATEGORY_URGENCY = {
    1: "CRITICAL — Py2 syntax must be eliminated before migration is valid",
    2: "HIGH — Compatibility libraries should be removed for clean Py3",
    3: "LOW — Cleanup: __future__ imports are harmless but add noise",
    4: "HIGH — Version guards add dead code paths and maintenance burden",
    5: "MEDIUM — Unresolved migration TODOs may indicate incomplete work",
    6: "LOW — Type ignores may be resolvable but are not blocking",
    7: "LOW — Encoding declarations are mostly cosmetic in Py3",
    8: "MEDIUM — Compat patterns add complexity; simplify for maintainability",
    9: "CRITICAL — Removed stdlib modules will cause ImportError at runtime",
    10: "MEDIUM — Lint suppressions may hide real issues",
}


def generate_header(report: Dict[str, Any]) -> str:
    """Generate report header with overall status."""
    summary = report.get("summary", {})
    files_scanned = summary.get("files_scanned", 0)
    files_with_findings = summary.get("files_with_findings", 0)
    files_clean = summary.get("files_clean", 0)
    total_findings = summary.get("total_findings", 0)
    error_count = summary.get("error_count", 0)
    warning_count = summary.get("warning_count", 0)
    info_count = summary.get("info_count", 0)
    gate_blocking = summary.get("gate_blocking_count", 0)
    completeness_score = summary.get("completeness_score", 0)

    if gate_blocking == 0 and total_findings == 0:
        status = "COMPLETE"
        status_note = "Migration is fully complete. No remaining artifacts found."
    elif gate_blocking == 0:
        status = "PASS"
        status_note = f"Gate check passes. {total_findings} non-blocking finding(s) remain for cleanup."
    elif error_count > 0:
        status = "FAIL"
        status_note = f"{gate_blocking} gate-blocking finding(s). {error_count} ERROR(s) must be resolved."
    else:
        status = "FAIL"
        status_note = f"{gate_blocking} gate-blocking finding(s) in strict mode."

    header = f"""# Migration Completeness Report

**Generated:** {report.get("timestamp", "unknown")}
**Target Version:** Python {report.get("target_version", "3.x")}
**Status:** {status}
**Strict Mode:** {"Yes" if report.get("strict_mode") else "No"}

> {status_note}

## Overall Summary

| Metric | Count |
|--------|-------|
| Files scanned | {files_scanned} |
| Files with findings | {files_with_findings} |
| Files clean | {files_clean} |
| Total findings | {total_findings} |
| ERROR (gate-blocking) | {error_count} |
| WARNING | {warning_count} |
| INFO (advisory) | {info_count} |
| **Gate-blocking total** | **{gate_blocking}** |
| **Completeness score** | **{completeness_score:.1f}%** |

"""
    return header


def generate_category_breakdown(report: Dict[str, Any]) -> str:
    """Generate category-by-category breakdown."""
    cat_summary = report.get("category_summary", {})

    if not cat_summary:
        return "## Category Breakdown\n\nNo findings in any category.\n\n"

    section = "## Category Breakdown\n\n"
    section += "| # | Category | Total | Error | Warning | Info | Urgency |\n"
    section += "|---|----------|-------|-------|---------|------|--------|\n"

    for cat_id_str in sorted(cat_summary.keys(), key=lambda x: int(x)):
        cat_id = int(cat_id_str)
        stats = cat_summary[cat_id_str]
        name = stats.get("name", CATEGORY_NAMES.get(cat_id, f"Category {cat_id}"))
        total = stats.get("total", 0)
        errors = stats.get("error", 0)
        warnings = stats.get("warning", 0)
        infos = stats.get("info", 0)
        urgency = CATEGORY_URGENCY.get(cat_id, "")

        marker = ""
        if errors > 0:
            marker = " **!!**"
        elif warnings > 0:
            marker = " ⚠"

        section += f"| {cat_id} | {name}{marker} | {total} | {errors} | {warnings} | {infos} | {urgency} |\n"

    section += "\n"
    return section


def generate_top_patterns(report: Dict[str, Any]) -> str:
    """Generate top patterns section."""
    top_patterns = report.get("top_patterns", [])

    if not top_patterns:
        return ""

    section = "## Most Common Patterns\n\n"
    section += "| Pattern | Count |\n"
    section += "|---------|-------|\n"

    for entry in top_patterns[:15]:
        pattern = entry.get("pattern", "unknown")
        count = entry.get("count", 0)
        section += f"| `{pattern}` | {count} |\n"

    section += "\n"
    return section


def generate_error_findings(report: Dict[str, Any]) -> str:
    """Generate detailed section for ERROR-severity findings."""
    findings = report.get("findings", [])
    errors = [f for f in findings if f.get("severity") == "ERROR"]

    if not errors:
        return "## ERROR Findings (Gate-Blocking)\n\nNo ERROR-severity findings. Gate check passes.\n\n"

    section = f"## ERROR Findings (Gate-Blocking) — {len(errors)} total\n\n"
    section += "These must be resolved before Phase 4→5 advancement.\n\n"

    # Group by category
    by_category: Dict[int, List[Dict[str, Any]]] = {}
    for f in errors:
        cat = f.get("category", 0)
        by_category.setdefault(cat, []).append(f)

    for cat in sorted(by_category.keys()):
        cat_errors = by_category[cat]
        cat_name = CATEGORY_NAMES.get(cat, f"Category {cat}")
        section += f"### {cat_name} ({len(cat_errors)} errors)\n\n"

        for f in cat_errors[:30]:  # Cap per category
            file_path = f.get("file", "unknown")
            line = f.get("line", 0)
            pattern = f.get("pattern", "unknown")
            description = f.get("description", "")
            snippet = f.get("snippet", "")

            section += f"- **{file_path}:{line}** — `{pattern}`\n"
            section += f"  {description}\n"
            if snippet:
                section += f"  ```\n  {snippet}\n  ```\n"
            section += "\n"

        if len(cat_errors) > 30:
            section += f"... and {len(cat_errors) - 30} more errors in this category\n\n"

    return section


def generate_warning_findings(report: Dict[str, Any]) -> str:
    """Generate summary of WARNING-severity findings."""
    findings = report.get("findings", [])
    warnings = [f for f in findings if f.get("severity") == "WARNING"]

    if not warnings:
        return "## WARNING Findings\n\nNo WARNING-severity findings.\n\n"

    section = f"## WARNING Findings — {len(warnings)} total\n\n"
    section += "These should be resolved but are not gate-blocking (unless --strict mode).\n\n"

    # Group by file for compact display
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for f in warnings:
        file_path = f.get("file", "unknown")
        by_file.setdefault(file_path, []).append(f)

    # Show top 20 files with most warnings
    sorted_files = sorted(by_file.items(), key=lambda x: -len(x[1]))

    for file_path, file_warnings in sorted_files[:20]:
        section += f"### `{file_path}` ({len(file_warnings)} warnings)\n\n"
        for f in file_warnings[:10]:
            line = f.get("line", 0)
            pattern = f.get("pattern", "unknown")
            description = f.get("description", "")
            section += f"- **Line {line}**: `{pattern}` — {description}\n"
        if len(file_warnings) > 10:
            section += f"- ... and {len(file_warnings) - 10} more\n"
        section += "\n"

    if len(sorted_files) > 20:
        section += f"... and {len(sorted_files) - 20} more files with warnings\n\n"

    return section


def generate_info_summary(report: Dict[str, Any]) -> str:
    """Generate compact summary of INFO-severity findings."""
    findings = report.get("findings", [])
    infos = [f for f in findings if f.get("severity") == "INFO"]

    if not infos:
        return ""

    section = f"## INFO Findings (Advisory) — {len(infos)} total\n\n"
    section += "These are cleanup suggestions, not blocking issues.\n\n"

    # Group by pattern for compact display
    pattern_counts = Counter(f.get("pattern", "unknown") for f in infos)
    section += "| Pattern | Occurrences |\n"
    section += "|---------|-------------|\n"
    for pattern, count in pattern_counts.most_common():
        section += f"| `{pattern}` | {count} |\n"
    section += "\n"

    return section


def generate_cleanup_tasks_section(
    report: Dict[str, Any],
    tasks_path: str,
) -> str:
    """Generate cleanup tasks section."""
    # Try to load cleanup tasks
    try:
        tasks = load_json(tasks_path)
    except SystemExit:
        return ""

    if not tasks:
        return "## Cleanup Tasks\n\nNo cleanup tasks generated.\n\n"

    # Count by priority
    critical = [t for t in tasks if t.get("priority") == "critical"]
    high = [t for t in tasks if t.get("priority") == "high"]
    low = [t for t in tasks if t.get("priority") == "low"]

    # Count by automation
    auto = [t for t in tasks if t.get("automation") == "auto"]
    semi = [t for t in tasks if t.get("automation") == "semi-auto"]
    manual = [t for t in tasks if t.get("automation") == "manual"]

    section = f"## Cleanup Tasks ({len(tasks)} total)\n\n"
    section += "| Priority | Count | Automation | Count |\n"
    section += "|----------|-------|------------|-------|\n"
    section += f"| Critical | {len(critical)} | Auto-fixable | {len(auto)} |\n"
    section += f"| High | {len(high)} | Semi-auto | {len(semi)} |\n"
    section += f"| Low | {len(low)} | Manual | {len(manual)} |\n\n"

    # Show critical tasks in detail
    if critical:
        section += "### Critical Tasks (Must Fix)\n\n"
        for t in critical[:20]:
            file_path = t.get("file", "unknown")
            description = t.get("description", "")
            occurrences = t.get("occurrences", 1)
            automation = t.get("automation", "manual")
            section += f"- **{file_path}** — {description} ({occurrences}x, {automation})\n"
        if len(critical) > 20:
            section += f"- ... and {len(critical) - 20} more critical tasks\n"
        section += "\n"

    # Show high-priority tasks as summary
    if high:
        section += "### High-Priority Tasks\n\n"
        # Group by pattern
        pattern_counts = Counter(t.get("pattern", "unknown") for t in high)
        section += "| Pattern | Tasks |\n"
        section += "|---------|-------|\n"
        for pattern, count in pattern_counts.most_common(10):
            section += f"| `{pattern}` | {count} |\n"
        section += "\n"

    return section


def generate_remediation_guide(report: Dict[str, Any]) -> str:
    """Generate remediation guidance based on findings."""
    cat_summary = report.get("category_summary", {})

    if not cat_summary:
        return ""

    section = "## Remediation Guide\n\n"

    has_findings = {int(k): v.get("total", 0) > 0 for k, v in cat_summary.items()}

    if has_findings.get(1, False):
        section += """### Fix Remaining Py2 Syntax

Category 1 findings are critical — they indicate unconverted Python 2 code:

1. Re-run the Automated Converter (Skill 2.2) on affected files
2. If converter already ran, these may be in code paths it couldn't parse
3. Fix manually: `print x` → `print(x)`, `except E, e:` → `except E as e:`
4. After fixing, verify with `python3 -c "import ast; ast.parse(open('file').read())"`

"""

    if has_findings.get(2, False):
        section += """### Remove Compatibility Libraries

Category 2 findings indicate `six`/`future`/`past` usage that should be simplified:

1. Replace `six.text_type` → `str`, `six.binary_type` → `bytes`
2. Replace `six.moves.range` → `range`, `six.moves.configparser` → `configparser`
3. Replace `six.PY2`/`six.PY3` guards — collapse to the Py3 branch
4. Remove `from builtins import ...` lines
5. After cleanup, remove `six` and `future` from requirements.txt

"""

    if has_findings.get(3, False):
        section += """### Remove __future__ Imports

Category 3 findings are low priority but easy cleanup:

1. Remove all `from __future__ import print_function, division, absolute_import, unicode_literals`
2. Keep `from __future__ import annotations` if using PEP 563 deferred annotations
3. This can be done with: `pyupgrade --py3X-plus` (where X is your target minor version)

"""

    if has_findings.get(4, False):
        section += """### Collapse Version Guards

Category 4 findings indicate code branching on Python version:

1. Find `if sys.version_info[0] >= 3:` / `if PY2:` blocks
2. Keep only the Py3 branch; delete the Py2 branch
3. Remove the guard condition entirely
4. Be careful with guards that check for 3.10+ features — those may still be needed

"""

    if has_findings.get(9, False):
        section += """### Replace Removed Stdlib Modules

Category 9 findings are critical — the target Python version has removed these modules:

1. `distutils` → `setuptools` or `sysconfig`
2. `cgi` → `urllib.parse` for form parsing, or `html` for escaping
3. `pipes` → `shlex`
4. `telnetlib` → `telnetlib3` (third-party) or custom socket code
5. Check `stdlib-removals-by-version.md` for full replacement guidance

"""

    return section


def generate_next_steps(report: Dict[str, Any]) -> str:
    """Generate next steps section."""
    summary = report.get("summary", {})
    gate_blocking = summary.get("gate_blocking_count", 0)
    total = summary.get("total_findings", 0)

    section = "## Next Steps\n\n"

    if gate_blocking == 0 and total == 0:
        section += "Migration is complete. The codebase is ready for:\n\n"
        section += "1. Final gate check (Skill X.3) for Phase 4→5 advancement\n"
        section += "2. Begin Phase 5: Cutover & Cleanup\n"
        section += "3. Canary deployment planning (Skill 5.1)\n"
    elif gate_blocking == 0:
        section += f"Gate check passes with {total} non-blocking finding(s). Recommended:\n\n"
        section += "1. Address high-priority cleanup tasks for code quality\n"
        section += "2. Run `pyupgrade --py3X-plus` for automated cleanup\n"
        section += "3. Proceed with Phase 4→5 gate check (Skill X.3)\n"
        section += "4. Schedule remaining cleanup for post-cutover\n"
    else:
        section += f"**{gate_blocking} gate-blocking finding(s) must be resolved:**\n\n"
        section += "1. Fix all ERROR-severity findings (categories 1 and 9 are most critical)\n"
        section += "2. Follow the remediation guide above for each category\n"
        section += "3. Re-run completeness checker to verify fixes\n"
        section += "4. Repeat until zero gate-blocking findings\n"
        section += "5. Then proceed with Phase 4→5 gate check (Skill X.3)\n"

    section += "\n"
    return section


def main():
    parser = argparse.ArgumentParser(
        description="Generate markdown migration completeness report"
    )
    parser.add_argument(
        "--completeness-report", required=True,
        help="Path to completeness-report.json",
    )
    parser.add_argument(
        "--cleanup-tasks",
        help="Path to cleanup-tasks.json (default: same directory as report)",
    )
    parser.add_argument(
        "--output", default="completeness-report.md",
        help="Output markdown file (default: completeness-report.md)",
    )

    args = parser.parse_args()

    # Derive cleanup tasks path if not provided
    tasks_path = args.cleanup_tasks
    if not tasks_path:
        report_dir = Path(args.completeness_report).parent
        tasks_path = str(report_dir / "cleanup-tasks.json")

    print("# ── Loading JSON Report ──────────────────────────────────────", file=sys.stdout)
    report = load_json(args.completeness_report)

    print("# ── Generating Markdown Report ───────────────────────────────", file=sys.stdout)

    md = ""
    md += generate_header(report)
    md += generate_category_breakdown(report)
    md += generate_top_patterns(report)
    md += generate_error_findings(report)
    md += generate_warning_findings(report)
    md += generate_info_summary(report)
    md += generate_cleanup_tasks_section(report, tasks_path)
    md += generate_remediation_guide(report)
    md += generate_next_steps(report)

    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"Wrote report to {output_path}", file=sys.stdout)
    print("Done.", file=sys.stdout)


if __name__ == "__main__":
    main()
