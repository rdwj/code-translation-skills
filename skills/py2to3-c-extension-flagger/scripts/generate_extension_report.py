#!/usr/bin/env python3
"""
C Extension Report Generator

Reads c-extension-report.json and generates a human-readable Markdown report
with findings, API compatibility matrix, and remediation guidance.

Usage:
    python3 generate_extension_report.py \
        <output_dir>/c-extension-report.json \
        --output <output_dir>/c-extension-report.md
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


def group_findings(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """Group findings by type."""
    by_type = defaultdict(list)
    for finding in findings:
        by_type[finding.get("type", "unknown")].append(finding)
    return by_type


def group_by_risk(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """Group findings by risk level."""
    by_risk = defaultdict(list)
    for finding in findings:
        by_risk[finding.get("severity", "MEDIUM")].append(finding)
    return by_risk


def group_by_file(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """Group findings by file."""
    by_file = defaultdict(list)
    for finding in findings:
        by_file[finding.get("file", "unknown")].append(finding)
    return by_file


def get_remediation_steps(finding: Dict) -> str:
    """Get specific remediation steps based on finding type."""
    finding_type = finding.get("type", "")
    severity = finding.get("severity", "MEDIUM")

    if finding_type == "c_extension_marker":
        return (
            "1. Audit the C code for deprecated C API usage\n"
            "2. Check for version-specific `#ifdef PY_VERSION_HEX` guards\n"
            "3. Update to use stable ABI via `Py_LIMITED_API` if possible\n"
            "4. Recompile for each target Python version"
        )

    elif finding_type == "deprecated_c_api":
        api = finding.get("api", "unknown")
        removed_in = finding.get("removed_in", "unknown")
        if severity == "CRITICAL":
            return (
                f"BLOCKER: {api} was removed in Python {removed_in}\n"
                f"Replacement required before migration to this version"
            )
        else:
            return (
                f"Refactor to avoid {api}\n"
                f"Check Python {removed_in}+ release notes for replacement API"
            )

    elif finding_type == "cython_file":
        return (
            "1. Ensure Cython is updated to support target Python version\n"
            "2. Regenerate .c files from .pyx with: `cython <file>.pyx`\n"
            "3. Audit the generated C code for deprecated API\n"
            "4. Consider using Cython's modern syntax if not already"
        )

    elif finding_type == "swig_file":
        return (
            "1. Ensure SWIG is updated to support target Python version\n"
            "2. Regenerate wrapper code with: `swig -python <file>.i`\n"
            "3. Audit generated wrapper for deprecated API\n"
            "4. Update type mappings for Py3 compatibility"
        )

    elif finding_type == "binding_usage":
        category = finding.get("category", "")
        if category == "ctypes":
            return (
                "1. Review type mappings (c_int, c_char_p, c_void_p, etc.)\n"
                "2. Test with both ASCII and non-ASCII data\n"
                "3. Verify struct layouts match in Py3\n"
                "4. Consider CFFI if type handling becomes complex"
            )
        elif category == "cffi":
            return (
                "1. Review FFI type definitions in ffi.cdef()\n"
                "2. Test buffer/memoryview handling\n"
                "3. Ensure type signatures match C library\n"
                "4. CFFI generally has better Py3 support than ctypes"
            )
        elif category == "swig":
            return (
                "1. Regenerate wrapper code with current SWIG\n"
                "2. Update type mappings for Py3\n"
                "3. Test thoroughly with Py3 target version\n"
                "4. Consider modernizing build configuration"
            )

    elif finding_type == "extension_definition":
        return (
            "1. Update Extension definition in setup.py\n"
            "2. Ensure sources reference up-to-date C code\n"
            "3. Add language='c++' or compiler flags as needed\n"
            "4. Test build with: `python setup.py build_ext --inplace`"
        )

    elif finding_type == "ext_modules_setup":
        return (
            "1. Review all Extension definitions in ext_modules\n"
            "2. Ensure compiler flags are Py3-compatible\n"
            "3. Update any version checks (PY_VERSION_HEX)\n"
            "4. Plan for recompilation per target version"
        )

    elif finding_type == "limited_api_guard":
        return (
            "GOOD: Using Py_LIMITED_API (stable ABI)\n"
            "This extension can work with multiple Python 3 versions\n"
            "Ensure Py_LIMITED_API macro value matches minimum supported version"
        )

    return "Review for Py3 compatibility"


# ── Report Generation ────────────────────────────────────────────────────────

def generate_report(report_data: Dict) -> str:
    """Generate the full Markdown report."""

    lines = []

    def w(text=""):
        lines.append(text)

    # ── Header ───────────────────────────────────────────────────────────

    w("# C Extension Detection Report")
    w()
    w(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    w()

    # ── Executive Summary ────────────────────────────────────────────────

    w("## Executive Summary")
    w()

    codebase = report_data.get("codebase", "unknown")
    target_version = report_data.get("target_version", "unknown")
    files_scanned = report_data.get("files_scanned", 0)

    w(f"**Codebase**: {codebase}  ")
    w(f"**Target Python Version**: {target_version}  ")
    w(f"**Files Scanned**: {files_scanned}  ")
    w()

    summary = report_data.get("summary", {})
    total = summary.get("total_findings", 0)
    risk_summary = summary.get("risk_summary", {})

    w(f"| Severity | Count |")
    w(f"|----------|-------|")
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
        count = risk_summary.get(sev, 0)
        if count > 0 or sev in ["CRITICAL", "HIGH"]:
            w(f"| **{sev}** | {count} |")

    w()
    w(f"**Total findings**: {total}")
    w()

    if risk_summary.get("CRITICAL", 0) > 0:
        w("> **CRITICAL ISSUES FOUND**: C extensions with removed C API in target version. "
          "These are blockers that will cause compilation failures.")
        w()

    if risk_summary.get("HIGH", 0) > 0:
        w("> **HIGH-RISK EXTENSIONS**: These require significant attention. "
          "Plan for code updates and recompilation.")
        w()

    # ── Extension Inventory ──────────────────────────────────────────────

    w("## Extension Inventory")
    w()

    findings = report_data.get("findings", [])
    by_type = group_findings(findings)

    w(f"| Type | Count | Description |")
    w(f"|------|-------|-------------|")
    type_descriptions = {
        "c_extension_marker": "C extension source files (*.c, *.h with Python.h)",
        "cython_file": "Cython source files (*.pyx, *.pxd)",
        "swig_file": "SWIG interface files (*.i)",
        "binding_usage": "ctypes/CFFI/SWIG usage in Python code",
        "deprecated_c_api": "Deprecated/removed C API function calls",
        "extension_definition": "Extension definitions in setup.py",
        "ext_modules_setup": "ext_modules parameter in setup()",
        "limited_api_guard": "Py_LIMITED_API stable ABI usage (good)",
    }

    for ext_type in sorted(by_type.keys()):
        count = len(by_type[ext_type])
        desc = type_descriptions.get(ext_type, ext_type)
        w(f"| {ext_type} | {count} | {desc} |")

    w()

    # ── C Extensions (High Risk) ─────────────────────────────────────────

    if "c_extension_marker" in by_type:
        w("## C Extensions Found")
        w()
        w("These files contain C code that directly uses the Python C API:")
        w()

        for finding in by_type["c_extension_marker"]:
            filepath = finding.get("file", "")
            w(f"### `{filepath}`")
            w()
            desc = finding.get("description", "")
            w(f"{desc}")
            w()
            w("**Remediation steps**:")
            w(f"```")
            w(get_remediation_steps(finding))
            w(f"```")
            w()

    # ── Cython Files ─────────────────────────────────────────────────────

    if "cython_file" in by_type:
        w("## Cython Source Files")
        w()
        w("These Cython files must be regenerated for Python 3 target version:")
        w()

        pyx_files = [f for f in by_type["cython_file"] if f.get("extension") == ".pyx"]
        pxd_files = [f for f in by_type["cython_file"] if f.get("extension") == ".pxd"]

        if pyx_files:
            w("### .pyx source files")
            w()
            for finding in pyx_files:
                w(f"- `{finding.get('file', '')}`")
            w()

        if pxd_files:
            w("### .pxd definition files")
            w()
            for finding in pxd_files:
                w(f"- `{finding.get('file', '')}`")
            w()

        w("**Actions**:")
        w("```")
        w("1. Update Cython to latest version: pip install --upgrade Cython")
        w("2. Regenerate C code: cython -3 <file>.pyx")
        w("3. Recompile extension: python setup.py build_ext --inplace")
        w("4. Test thoroughly")
        w("```")
        w()

    # ── SWIG Files ───────────────────────────────────────────────────────

    if "swig_file" in by_type:
        w("## SWIG Interface Files")
        w()
        w("These SWIG interfaces must be regenerated for Python 3:")
        w()

        for finding in by_type["swig_file"]:
            w(f"- `{finding.get('file', '')}`")
        w()

        w("**Actions**:")
        w("```")
        w("1. Update SWIG to latest version: swig -version")
        w("2. Regenerate wrappers: swig -python -py3 <file>.i")
        w("3. Update type mappings in .i file for Py3")
        w("4. Recompile extension")
        w("```")
        w()

    # ── Deprecated C API ─────────────────────────────────────────────────

    if "deprecated_c_api" in by_type:
        w("## Deprecated/Removed C API Usage")
        w()

        by_risk = group_by_risk(by_type["deprecated_c_api"])

        for severity in ["CRITICAL", "HIGH", "MEDIUM"]:
            if severity in by_risk:
                findings_at_sev = by_risk[severity]
                w(f"### {severity} ({len(findings_at_sev)} uses)")
                w()

                by_file = group_by_file(findings_at_sev)

                for filepath in sorted(by_file.keys()):
                    file_findings = by_file[filepath]
                    w(f"**File**: `{filepath}`")
                    w()

                    for finding in sorted(file_findings, key=lambda x: x.get("line", 0)):
                        api = finding.get("api", "")
                        line = finding.get("line", "?")
                        removed_in = finding.get("removed_in", "")
                        code = finding.get("code", "")

                        w(f"- **Line {line}**: `{api}` (removed in Python {removed_in})")
                        if code:
                            w(f"  ```c")
                            w(f"  {code}")
                            w(f"  ```")

                    w()

    # ── ctypes/CFFI Usage ────────────────────────────────────────────────

    if "binding_usage" in by_type:
        w("## Foreign Function Interface Usage")
        w()

        bindings = by_type["binding_usage"]
        by_category = defaultdict(list)
        for b in bindings:
            by_category[b.get("category", "unknown")].append(b)

        for category in sorted(by_category.keys()):
            cat_findings = by_category[category]
            w(f"### {category.upper()} ({len(cat_findings)} uses)")
            w()

            by_file = group_by_file(cat_findings)
            for filepath in sorted(by_file.keys()):
                file_findings = by_file[filepath]
                w(f"**File**: `{filepath}`")
                w()

                for finding in sorted(file_findings, key=lambda x: x.get("line", 0)):
                    line = finding.get("line", "?")
                    code = finding.get("code", "")
                    w(f"- **Line {line}**: {code}")

                w()

    # ── Stable ABI Usage ─────────────────────────────────────────────────

    if "limited_api_guard" in by_type:
        w("## Stable ABI (Py_LIMITED_API) Usage")
        w()
        w("✓ These files use the stable ABI and will work across multiple Python 3 versions:")
        w()

        for finding in by_type["limited_api_guard"]:
            w(f"- `{finding.get('file', '')}`")

        w()
        w("**Benefit**: No recompilation needed for different Python 3.x versions.")
        w()

    # ── Recommendations ────────────────────────────────────────────────

    w("## Recommendations")
    w()

    critical = risk_summary.get("CRITICAL", 0)
    high = risk_summary.get("HIGH", 0)

    if critical > 0:
        w(f"1. **CRITICAL**: {critical} deprecated API call(s) incompatible with target version")
        w("   - Must be replaced before migration")
        w("   - Consider using Py_LIMITED_API for future compatibility")
        w()

    if high > 0:
        w(f"2. **HIGH PRIORITY**: {high} high-risk extension(s) found")
        w("   - Plan for code updates and recompilation")
        w("   - Test thoroughly with target Python version")
        w()

    if "c_extension_marker" in by_type:
        c_ext_count = len(by_type["c_extension_marker"])
        w(f"3. **C Extension Audit**: {c_ext_count} C extension(s) detected")
        w("   - Schedule code review for C API compatibility")
        w("   - Update version checks to target version")
        w()

    if "cython_file" in by_type:
        cython_count = len(by_type["cython_file"])
        w(f"4. **Cython Update**: {cython_count} Cython file(s) require regeneration")
        w("   - Update Cython compiler")
        w("   - Regenerate C files for target version")
        w()

    if "limited_api_guard" not in by_type or len(by_type.get("limited_api_guard", [])) == 0:
        w("5. **Consider Stable ABI**: Use Py_LIMITED_API in new extensions")
        w("   - Works with multiple Python 3.x versions")
        w("   - Reduces maintenance burden")
        w()

    w("## References")
    w()
    w("- [Python C API](https://docs.python.org/3/c-api/)")
    w("- [Py_LIMITED_API Stable ABI](https://docs.python.org/3/c-api/stable.html)")
    w("- [Cython Documentation](https://cython.readthedocs.io/)")
    w("- [SWIG Documentation](https://swig.org/)")
    w()

    return "\n".join(lines)


# ── Main Entry Point ────────────────────────────────────────────────────────

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Markdown report from C extension detection"
    )
    parser.add_argument("report_json", help="Path to c-extension-report.json")
    parser.add_argument("--output", help="Output file path (default: stdout)")

    args = parser.parse_args()

    report = load_json(args.report_json)
    if not report:
        print(f"Error: Could not load {args.report_json}", file=sys.stderr)
        sys.exit(1)

    markdown = generate_report(report)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w") as f:
            f.write(markdown)
        print(f"Wrote: {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
