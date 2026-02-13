#!/usr/bin/env python3
"""
Compatibility Shim Removal Report Generator

Reads shim-removal-report.json and generates human-readable markdown report
showing what compatibility code was removed and test results.

Usage:
    python3 generate_shim_report.py shim-removal-report.json \
        --output ./cleaned/

Output:
    shim-removal-report.md — Detailed removal summary and per-file changes
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
from collections import defaultdict


# ── Helper Functions ──────────────────────────────────────────────────────────

def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def write_file(path: str, content: str) -> None:
    """Write content to file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


# ── Report Generation ─────────────────────────────────────────────────────────

def generate_removal_report(report_data: Dict[str, Any]) -> str:
    """Generate comprehensive removal report markdown."""

    metadata = report_data['metadata']
    removals = report_data['removal_summary']
    per_file = report_data['per_file_changes']
    test_results = report_data['batch_test_results']
    failed_files = report_data['failed_files']
    req_cleanup = report_data['requirements_cleanup']

    # Build report
    md = f"""# Compatibility Shim Removal Report

**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Codebase**: {metadata['codebase_path']}
**Target Python Version**: {metadata['target_version']}
**Mode**: {'DRY RUN (no changes)' if metadata['dry_run'] else 'PRODUCTION (files modified)'}

---

## Executive Summary

Successfully removed compatibility code from **{metadata['python_files_processed']}** Python files.

### Key Statistics

| Metric | Count |
|--------|-------|
| **Total Files Processed** | {metadata['python_files_processed']} |
| **Files Modified** | {metadata['files_modified']} |
| **Total Removals** | {report_data['total_removals']} |
| **Test Batches** | {len(test_results)} |
| **Passing Batches** | {len([r for r in test_results if r['success']])} |
| **Failed Batches** | {len([r for r in test_results if not r['success']])} |

---

## Removal Breakdown by Category

### Summary Table

| Category | Count | Description |
|----------|-------|-------------|
"""

    # Sort removals by count
    sorted_removals = sorted(removals.items(), key=lambda x: x[1], reverse=True)

    category_descriptions = {
        'future_imports': '__future__ imports removed',
        'six_text_type': 'six.text_type → str replacements',
        'six_binary_type': 'six.binary_type → bytes replacements',
        'six_string_types': 'six.string_types → (str,) replacements',
        'six_integer_types': 'six.integer_types → (int,) replacements',
        'six_iteritems': 'six.iteritems(d) → d.items() replacements',
        'six_itervalues': 'six.itervalues(d) → d.values() replacements',
        'six_iterkeys': 'six.iterkeys(d) → d.keys() replacements',
        'six_moves_imports': 'six.moves import statements removed',
        'six_ensure_str': 'six.ensure_str() → str() replacements',
        'six_ensure_text': 'six.ensure_text() → str() replacements',
        'six_py2': 'six.PY2 → False replacements',
        'six_py3': 'six.PY3 → True replacements',
        'six_metaclass': '@six.add_metaclass decorators updated',
        'six_unicode_decorator': '@six.python_2_unicode_compatible removed',
        'six_imports': 'import six statements removed',
        'future_module_imports': 'from __future__ module imports removed',
        'version_guards': 'sys.version_info guards collapsed',
        'import_guards': 'try-except import guards simplified',
    }

    for category, count in sorted_removals:
        desc = category_descriptions.get(category, category)
        md += f"| `{category}` | {count} | {desc} |\n"

    md += f"""

---

## Detailed Changes by Category

### 1. __future__ Imports

**Removed**: {removals.get('future_imports', 0)} import lines

The `__future__` module provides imports that change Python behavior. In Python 3, these are
built-in and no longer needed:

- `from __future__ import print_function` — print() is a function in Py3
- `from __future__ import division` — true division is default in Py3
- `from __future__ import unicode_literals` — all strings are unicode in Py3
- `from __future__ import absolute_import` — absolute imports are default in Py3
- `from __future__ import with_statement` — with is a language feature in Py3

All these imports have been removed from {removals.get('future_imports', 0)} lines of code.

### 2. six Library Removals

**Type Checks Replaced**: {removals.get('six_text_type', 0) + removals.get('six_binary_type', 0) + removals.get('six_string_types', 0) + removals.get('six_integer_types', 0)}

The `six` library provided abstractions for Py2/Py3 differences. In Py3-only code:

- `six.text_type` → `str` ({removals.get('six_text_type', 0)} changes)
- `six.binary_type` → `bytes` ({removals.get('six_binary_type', 0)} changes)
- `six.string_types` → `(str,)` ({removals.get('six_string_types', 0)} changes)
- `six.integer_types` → `(int,)` ({removals.get('six_integer_types', 0)} changes)

**Iteration Methods Replaced**: {removals.get('six_iteritems', 0) + removals.get('six_itervalues', 0) + removals.get('six_iterkeys', 0)}

Dictionary iteration in Py3 is native:

- `six.iteritems(d)` → `d.items()` ({removals.get('six_iteritems', 0)} changes)
- `six.itervalues(d)` → `d.values()` ({removals.get('six_itervalues', 0)} changes)
- `six.iterkeys(d)` → `d.keys()` ({removals.get('six_iterkeys', 0)} changes)

**Utility Functions Replaced**: {removals.get('six_ensure_str', 0) + removals.get('six_ensure_text', 0)}

- `six.ensure_str()` → `str()` ({removals.get('six_ensure_str', 0)} changes)
- `six.ensure_text()` → `str()` ({removals.get('six_ensure_text', 0)} changes)

**Version Checks Replaced**: {removals.get('six_py2', 0) + removals.get('six_py3', 0)}

- `six.PY2` → `False` ({removals.get('six_py2', 0)} changes) — code after this is now dead
- `six.PY3` → `True` ({removals.get('six_py3', 0)} changes) — code before this is now dead

**Decorators Removed**: {removals.get('six_unicode_decorator', 0)}

- `@six.python_2_unicode_compatible` — removed ({removals.get('six_unicode_decorator', 0)} decorators)

**Class Decorators Updated**: {removals.get('six_metaclass', 0)}

- `@six.add_metaclass(Meta)` → `class X(metaclass=Meta):` ({removals.get('six_metaclass', 0)} changes)

### 3. Version Guards Collapsed

**Collapsed**: {removals.get('version_guards', 0)}

Code like `if sys.version_info < (3, ...):` has been collapsed to keep only the Py3 branch:

```python
# Before:
if sys.version_info < (3, 0):
    # Py2 code
    x = unicode(s)
else:
    # Py3 code
    x = str(s)

# After:
x = str(s)
```

### 4. Import Guards Simplified

**Simplified**: {removals.get('import_guards', 0)}

Try-except import patterns have been simplified to Py3-only imports:

```python
# Before:
try:
    from urllib.parse import urlencode  # Py3
except ImportError:
    from urllib import urlencode  # Py2

# After:
from urllib.parse import urlencode  # Py3 only
```

### 5. Dependency Cleanup

**Cleanup Results**:

| File | Cleaned | Changes |
|------|---------|---------|
| `requirements.txt` | {"✓" if req_cleanup.get("requirements_txt") else "✗"} | {"six, future removed" if req_cleanup.get("requirements_txt") else "No changes"} |
| `setup.py` | {"✓" if req_cleanup.get("setup_py") else "✗"} | {"six, future removed from install_requires" if req_cleanup.get("setup_py") else "No changes"} |
| `pyproject.toml` | {"✓" if req_cleanup.get("pyproject_toml") else "✗"} | {"six, future removed" if req_cleanup.get("pyproject_toml") else "No changes"} |
| `setup.cfg` | {"✓" if req_cleanup.get("setup_cfg") else "✗"} | {"six, future removed" if req_cleanup.get("setup_cfg") else "No changes"} |

The `six` and `python-future` dependencies are no longer needed and have been removed.

---

## Test Results

### Summary

"""

    if test_results:
        passing = len([r for r in test_results if r['success']])
        failing = len([r for r in test_results if not r['success']])

        md += f"""**Batches Tested**: {len(test_results)}
**Passing**: {passing} ✓
**Failing**: {failing} ✗

### Per-Batch Results

| Batch | Status | Output |
|-------|--------|--------|
"""

        for result in test_results:
            status = "✓ PASS" if result['success'] else "✗ FAIL"
            output_preview = result['output'][:100].replace('\n', ' ')
            md += f"| Batch {result['batch']} | {status} | `{output_preview}...` |\n"

    else:
        md += """No tests were run (--test-command not specified).

To verify changes are correct, run your test suite:
```bash
pytest -xvs
```

"""

    if failed_files:
        md += f"""

### Failed Files

The following files caused test failures. Manual review recommended:

"""
        for file in failed_files:
            md += f"- `{file}`\n"

    md += f"""

---

## Per-File Changes Summary

Total files with changes: {metadata['files_modified']} / {metadata['python_files_processed']}

### Files with Most Changes

"""

    # Sort by changes
    sorted_files = sorted(per_file, key=lambda x: x['changes'], reverse=True)

    for file_report in sorted_files[:20]:  # Top 20
        if file_report['changes'] > 0:
            md += f"- **{file_report['filepath']}** — {file_report['changes']} changes\n"

    if len(sorted_files) > 20:
        md += f"- ... and {len(sorted_files) - 20} more files\n"

    md += f"""

### Change Distribution

Files with most removals:

"""

    # Generate histogram
    change_counts = [f['changes'] for f in per_file if f['changes'] > 0]
    if change_counts:
        max_changes = max(change_counts)
        avg_changes = sum(change_counts) / len(change_counts)
        md += f"""- Maximum changes in single file: {max_changes}
- Average changes per modified file: {avg_changes:.1f}
- Median changes per modified file: {sorted(change_counts)[len(change_counts)//2]}

"""

    md += f"""

---

## Remaining Code Review

### Files to Review Manually

After automated removal, the following patterns may need manual review:

1. **Complex Version Guards**: If version guards had complex nesting, manual cleanup may be needed
2. **Custom Compatibility Code**: Code that mimicked six but wasn't using the library
3. **Conditional Imports**: Dynamic imports or optional dependencies
4. **Type Stub Compatibility**: If using type stubs, verify they're Py3-compatible

### Search Patterns for Remaining Issues

Run these searches to find potential remaining issues:

```bash
# Look for remaining six usage
grep -r "import six" .
grep -r "from six" .

# Look for remaining future usage
grep -r "from __future__" .
grep -r "from future" .
grep -r "from builtins" .

# Look for version checks
grep -r "version_info" .
grep -r "PY2\\|PY3" .
grep -r "sys.version" .

# Look for unicode/string compatibility
grep -r "unicode(" .
grep -r "basestring" .
```

---

## Success Indicators

Your migration is successful if:

✓ All tests pass after removal
✓ No remaining six or future imports
✓ Code is cleaner and more readable
✓ Performance is stable or improved
✓ Type hints work correctly (no forward references issues)

---

## Next Steps

1. **Code Review**: Have team review the changes
2. **Testing**: Run full test suite locally and in CI/CD
3. **Staging Deployment**: Deploy to staging environment
4. **Production Deployment**: Gradually roll out to production
5. **Modernization**: Consider applying `pyupgrade` for further modernization

### Modernization Suggestions

After removing compatibility code, consider modernizing to latest Python 3 idioms:

```bash
# Install pyupgrade if not already installed
pip install pyupgrade

# Modernize code for target version
pyupgrade --py{target_version.replace('.', '')}-plus file1.py file2.py ...
```

This will:
- Convert `"{0}".format()` to f-strings
- Replace `type()` checks with `isinstance()`
- Use `dataclasses` instead of `namedtuple`
- Simplify type hints (e.g., `list[int]` instead of `List[int]`)
- Remove unnecessary imports and code

---

## Troubleshooting

### "Tests failed after removal"

1. Check which batch failed
2. Review files in that batch
3. Identify which removal caused the failure
4. Revert that specific change and investigate
5. May need manual fix for edge case

### "Found remaining six usage"

If the automated remover missed some six usage:

1. Identify the pattern
2. Update the remover script
3. Re-run on those files
4. Submit pattern for improvement

### "Performance degraded"

1. Unlikely from removal, more likely from differences elsewhere
2. Profile code to identify hot path
3. Optimize that specific code for Py3
4. Check dependency versions for performance issues

---

## Statistics

### Removal Statistics

**Total Removals by Type**:

"""

    for category, count in sorted_removals:
        percentage = (count / report_data['total_removals'] * 100) if report_data['total_removals'] > 0 else 0
        md += f"- `{category}`: {count} ({percentage:.1f}%)\n"

    md += f"""

### File Statistics

- **Total Files Processed**: {metadata['python_files_processed']}
- **Files Modified**: {metadata['files_modified']}
- **Files Unchanged**: {metadata['python_files_processed'] - metadata['files_modified']}
- **Lines Added by Removal** (net): Likely negative (more was removed than added)

---

## References

- Skill: Compatibility Shim Remover
- Original report: `shim-removal-report.json`
- Removed dependencies: `six`, `python-future`
- Target Python version: {metadata['target_version']}

### External References

- [six Documentation](https://six.readthedocs.io/)
- [python-future Documentation](https://python-future.org/)
- [PEP 420 - Implicit Namespace Packages](https://www.python.org/dev/peps/pep-0420/)
- [PEP 3104 - Access to Names in Outer Scopes](https://www.python.org/dev/peps/pep-3104/)
- [PEP 3131 - Supporting Non-ASCII Identifiers](https://www.python.org/dev/peps/pep-3131/)

---

*Generated by Compatibility Shim Removal Script*
*For questions or issues, contact the Python 3 migration team*
"""

    return md


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate removal report from shim removal data"
    )
    parser.add_argument('report_file', help='Path to shim-removal-report.json')
    parser.add_argument('--output', default='.',
                       help='Output directory for report')

    args = parser.parse_args()

    if not os.path.exists(args.report_file):
        print(f"Error: {args.report_file} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Loading report from {args.report_file}...")
    report = load_json(args.report_file)

    print("Generating shim-removal-report.md...")
    markdown = generate_removal_report(report)

    output_path = os.path.join(args.output, 'shim-removal-report.md')
    write_file(output_path, markdown)

    print(f"✓ Report generated: {output_path}")
    print(f"  Total removals: {report['total_removals']}")
    print(f"  Files modified: {report['metadata']['files_modified']}")


if __name__ == '__main__':
    main()
