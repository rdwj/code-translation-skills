#!/usr/bin/env python3
"""
Build System Report Generator: Creates markdown report from build-system-report.json

Reads JSON output from update_build.py and generates a comprehensive markdown report
with findings, changes, distutils migration guidance, and dependency concerns.

Usage:
    python3 generate_build_report.py --report build-system-report.json --output report.md
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


def load_json(filepath: str) -> Dict[str, Any]:
    """Load JSON from file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: Failed to load {filepath}: {e}", file=sys.stderr)
        return {}


def generate_markdown_report(report_data: Dict[str, Any]) -> str:
    """Generate comprehensive markdown report."""

    lines = []

    # Header
    lines.append("# Build System Updater Report\n")
    lines.append(f"**Generated**: {report_data.get('timestamp', 'unknown')}")
    lines.append(f"**Codebase**: {report_data.get('codebase_path', 'unknown')}")
    lines.append(f"**Target Version**: Python {report_data.get('target_version', 'unknown')}")
    lines.append(f"**Mode**: {'Dry-run (no modifications)' if report_data.get('dry_run') else 'Modified files'}\n")

    # Summary Section
    summary = report_data.get('summary', {})
    lines.append("## Summary\n")
    lines.append(f"- Total build files discovered: **{summary.get('total_build_files', 0)}**")
    lines.append(f"- Files updated: **{summary.get('files_updated', 0)}**")
    lines.append(f"- Dependency concerns flagged: **{summary.get('dependency_concerns', 0)}**\n")

    # Discovered Files Section
    discovered = report_data.get('discovered_files', {})
    if discovered:
        lines.append("## Discovered Build Files\n")
        for file_type, count in discovered.items():
            lines.append(f"- {file_type}: {count}")
        lines.append()

    # Updates and Changes
    updates = report_data.get('updates', {})
    if updates:
        lines.append("## Changes Applied\n")

        for filepath, update_info in updates.items():
            file_type = update_info.get('type', 'unknown')
            lines.append(f"### {filepath}\n")
            lines.append(f"**Type**: {file_type}\n")

            # Changes list
            changes = update_info.get('changes', [])
            if changes:
                lines.append("**Changes**:\n")
                for change in changes:
                    lines.append(f"- {change}")
                lines.append()

            # Analysis details for setup.py
            if file_type == 'setup.py':
                analysis = update_info.get('analysis', {})

                if analysis.get('uses_distutils'):
                    lines.append("**Critical Issue**: Uses distutils (incompatible with Python 3.12+)")
                    distutils_imports = analysis.get('distutils_imports', [])
                    if distutils_imports:
                        lines.append("\nDistutils imports found:")
                        for imp in distutils_imports:
                            lines.append(f"- `{imp}`")
                    lines.append()

                python_requires = analysis.get('python_requires')
                if python_requires:
                    lines.append(f"**Current python_requires**: `{python_requires}`\n")

                classifiers = analysis.get('classifiers', [])
                if classifiers:
                    lines.append(f"**Found {len(classifiers)} classifiers**")
                    py2_count = len([c for c in classifiers if 'Python :: 2' in c])
                    if py2_count > 0:
                        lines.append(f"- ⚠ {py2_count} Python 2.x classifiers (should be removed)\n")

                # Issues
                issues = analysis.get('issues', [])
                if issues:
                    lines.append("**Issues Found**:\n")
                    for issue in issues:
                        severity = issue.get('severity', 'info').upper()
                        message = issue.get('message', '')
                        fix = issue.get('fix', '')
                        lines.append(f"- [{severity}] {message}")
                        if fix:
                            lines.append(f"  - Fix: {fix}")
                    lines.append()
    else:
        lines.append("## Changes Applied\n")
        lines.append("No changes required.\n")

    # Distutils Migration Guidance
    setup_files = [u for u in updates.values() if u.get('type') == 'setup.py']
    if setup_files:
        lines.append("## Distutils Migration Guidance\n")
        lines.append("""
**Why distutils matters**: Python 3.12+ removed distutils. If your setup.py uses distutils,
you must migrate to setuptools.

### Migration Steps

1. **Replace imports**:
   ```python
   # Before
   from distutils.core import setup

   # After
   from setuptools import setup
   ```

2. **Replace Extension imports** (if using C extensions):
   ```python
   # Before
   from distutils.extension import Extension

   # After
   from setuptools import Extension
   ```

3. **Replace command imports**:
   ```python
   # Before
   from distutils.command.build_ext import build_ext

   # After
   from setuptools.command.build_ext import build_ext
   ```

4. **Update python_requires and classifiers**:
   ```python
   python_requires='>=3.9',  # Specify minimum version
   classifiers=[
       'Programming Language :: Python :: 3',
       'Programming Language :: Python :: 3.9',
       'Programming Language :: Python :: 3.10',
       'Programming Language :: Python :: 3.11',
       'Programming Language :: Python :: 3.12',
   ],
   ```

5. **Consider migrating to pyproject.toml** (PEP 517/518 modern standard):
   ```toml
   [build-system]
   requires = ["setuptools>=45", "wheel"]
   build-backend = "setuptools.build_meta"

   [project]
   name = "mypackage"
   version = "1.0.0"
   requires-python = ">=3.9"
   ```

### References
- [setuptools documentation](https://setuptools.pypa.io/)
- [PEP 621: pyproject.toml](https://www.python.org/dev/peps/pep-0621/)
- [Python 3.12 distutils removal](https://docs.python.org/3.12/whatsnew/3.12.html#distutils)
""")

    # Dependency Concerns
    concerns = report_data.get('dependency_concerns', [])
    if concerns:
        lines.append("## Dependency Version Concerns\n")
        lines.append("""
The following packages have pinned or constrained versions that should be manually verified
for Python 3 compatibility. **No automatic changes were made** — review and update as needed.
\n""")

        # Group by file
        by_file = {}
        for concern in concerns:
            file_name = concern.get('file', 'unknown')
            if file_name not in by_file:
                by_file[file_name] = []
            by_file[file_name].append(concern)

        for file_name, file_concerns in by_file.items():
            lines.append(f"### {file_name}\n")
            for concern in file_concerns:
                pkg = concern.get('package', 'unknown')
                spec = concern.get('spec', 'unknown')
                concern_msg = concern.get('concern', '')
                lines.append(f"- **{pkg}** `{spec}`")
                if concern_msg:
                    lines.append(f"  - {concern_msg}")
            lines.append()

    # Footer with next steps
    lines.append("## Next Steps\n")
    lines.append("""
1. **Review all changes** in the JSON report (`build-system-report.json`)
2. **Test the updated build** with your target Python version:
   ```bash
   python3 -m pip install -e .
   python3 -m pytest  # or your test suite
   ```
3. **Address dependency concerns**: Review pinned versions and update package versions as needed
4. **Update CI/CD** configuration to test with new Python version
5. **Update documentation** to reflect new Python version requirements
6. **Tag a release** after verification

""")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description='Generate markdown report from build-system-report.json'
    )
    parser.add_argument(
        '--report',
        required=True,
        help='Path to build-system-report.json'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output markdown file path'
    )

    args = parser.parse_args()

    # Load report
    report_data = load_json(args.report)
    if not report_data:
        print("Error: Could not load report data", file=sys.stderr)
        return 1

    # Generate markdown
    markdown = generate_markdown_report(report_data)

    # Write output
    try:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(markdown)
        print(f"Report written to {args.output}", file=sys.stderr)
    except Exception as e:
        print(f"Error writing report: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
