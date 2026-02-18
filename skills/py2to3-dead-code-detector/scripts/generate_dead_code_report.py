#!/usr/bin/env python3
"""
Dead Code Report Generator

Reads dead-code-report.json and generates a human-readable Markdown report
with findings grouped by category and confidence level.

Usage:
    python3 generate_dead_code_report.py \
        <output_dir>/dead-code-report.json \
        --output <output_dir>/dead-code-report.md
"""

import json
import sys
import argparse
import os
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ── Helper Functions ─────────────────────────────────────────────────────────

def load_json(path: str) -> Dict:
    """Load JSON file, return empty dict if not found."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def group_by_type(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """Group findings by type."""
    by_type = defaultdict(list)
    for finding in findings:
        by_type[finding.get("type", "unknown")].append(finding)
    return dict(by_type)


def group_by_confidence(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """Group findings by confidence level."""
    by_conf = defaultdict(list)
    for finding in findings:
        by_conf[finding.get("confidence", "MEDIUM")].append(finding)
    return dict(by_conf)


def group_by_file(findings: List[Dict]) -> Dict[str, List[Dict]]:
    """Group findings by file."""
    by_file = defaultdict(list)
    for finding in findings:
        by_file[finding.get("file", "unknown")].append(finding)
    return dict(by_file)


def format_lines(lineno: int, endlineno: int) -> str:
    """Format line range."""
    if lineno == endlineno:
        return f"Line {lineno}"
    else:
        return f"Lines {lineno}–{endlineno}"


def get_remediation_steps(finding: Dict) -> str:
    """Get remediation steps based on finding type."""
    finding_type = finding.get("type", "")
    confidence = finding.get("confidence", "MEDIUM")

    if finding_type == "version_guard_dead_code":
        reason = finding.get("reason", "")
        return (
            f"**Removal**: This code is dead in Python 3. Remove the entire block.\n\n"
            f"**Reason**: {reason}\n\n"
            f"**Verification**: Ensure no other code dynamically imports or calls functions "
            f"from this block. Cross-check with safe-to-remove.json before deletion."
        )

    elif finding_type == "compat_function":
        name = finding.get("name", "unknown")
        return (
            f"**Review**: Function `{name}()` matches Py2 compatibility naming pattern.\n\n"
            f"**Action**: Check if this function is used only in dead code or version-guarded blocks. "
            f"If yes, mark for removal. If no, may be public API or dynamically called.\n\n"
            f"**Tools**: Use safe-to-remove.json for high-confidence removals only."
        )

    elif finding_type == "unused_import":
        name = finding.get("name", "unknown")
        module = finding.get("module", "unknown")
        return (
            f"**Removal**: Import `from {module} import {name}` is never referenced.\n\n"
            f"**Action**: Remove the import statement. Verify no code depends on "
            f"this import for re-export or public API.\n\n"
            f"**Caution**: Check if this import is used for side effects (e.g., import-time registration)."
        )

    elif finding_type == "dead_test_code":
        name = finding.get("name", "")
        decorator = finding.get("decorator", "")
        return (
            f"**Removal**: Test function `{name}()` is explicitly skipped (decorator: `{decorator}`).\n\n"
            f"**Action**: Remove this test function and any associated fixtures. "
            f"Test results won't include this function, and it's safe to delete.\n\n"
            f"**Impact**: Improves test clarity and reduces maintenance burden."
        )

    else:
        return "Review and determine if safe to remove based on usage analysis."


# ── Report Generation ────────────────────────────────────────────────────────

def generate_report(report_data: Dict, safe_data: Dict) -> str:
    """Generate Markdown report."""
    output = []

    # Header
    output.append("# Dead Code Detection Report\n")
    output.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.append(f"**Target Version**: Python {report_data.get('target_version', 'unknown')}\n")
    output.append(f"**Codebase**: {report_data.get('codebase_path', 'unknown')}\n")
    output.append("")

    # Executive Summary
    summary = report_data.get("summary", {})
    total = report_data.get("total_findings", 0)

    output.append("## Executive Summary\n")
    output.append(f"- **Files Scanned**: {report_data.get('files_scanned', 0)}\n")
    output.append(f"- **Total Findings**: {total}\n")
    output.append(f"- **Safe to Remove (HIGH confidence)**: {safe_data.get('total_safe_removals', 0)}\n")
    output.append("")

    # Summary by Type
    output.append("### Findings by Category\n")
    output.append(f"- Version-guarded dead code: {summary.get('version_guard_dead_code', 0)}\n")
    output.append(f"- Py2 compatibility functions: {summary.get('compat_functions', 0)}\n")
    output.append(f"- Unused imports: {summary.get('unused_imports', 0)}\n")
    output.append(f"- Dead test code: {summary.get('dead_test_code', 0)}\n")
    output.append("")

    # Summary by Confidence
    conf_summary = summary.get("confidence", {})
    output.append("### Confidence Distribution\n")
    output.append(f"- **HIGH** (safe to auto-remove): {conf_summary.get('HIGH', 0)}\n")
    output.append(f"- **MEDIUM** (review required): {conf_summary.get('MEDIUM', 0)}\n")
    output.append(f"- **LOW** (manual verification needed): {conf_summary.get('LOW', 0)}\n")
    output.append("")

    # Findings by Category
    findings = report_data.get("findings", [])
    by_type = group_by_type(findings)

    for finding_type in ["version_guard_dead_code", "compat_function", "unused_import", "dead_test_code"]:
        if finding_type in by_type:
            type_findings = by_type[finding_type]
            type_count = len(type_findings)
            output.append(f"## {finding_type.replace('_', ' ').title()} ({type_count})\n")

            # Group by confidence
            by_conf = group_by_confidence(type_findings)
            for conf in ["HIGH", "MEDIUM", "LOW"]:
                if conf in by_conf:
                    conf_findings = by_conf[conf]
                    output.append(f"### {conf} Confidence ({len(conf_findings)})\n")

                    for finding in conf_findings[:10]:  # Limit per confidence level
                        file_path = finding.get("file", "unknown")
                        lineno = finding.get("lineno", "?")
                        endlineno = finding.get("endlineno", lineno)
                        name = finding.get("name", "")
                        desc = finding.get("description", "")

                        output.append(f"\n**File**: `{file_path}`  \n")
                        output.append(f"**Location**: {format_lines(lineno, endlineno)}  \n")
                        if name:
                            output.append(f"**Name**: `{name}`  \n")
                        output.append(f"**Description**: {desc}  \n")
                        output.append(f"\n{get_remediation_steps(finding)}\n")

                    if len(conf_findings) > 10:
                        output.append(f"\n*... and {len(conf_findings) - 10} more ...*\n")

            output.append("")

    # Safe to Remove List
    if safe_data.get("total_safe_removals", 0) > 0:
        output.append("## Safe to Remove (HIGH Confidence)\n")
        output.append(
            "These findings are high-confidence dead code that can be automatically removed.\n\n"
        )

        safe_by_type = safe_data.get("by_category", {})
        for category in safe_by_type:
            findings_list = safe_by_type[category]
            output.append(f"### {category.replace('_', ' ').title()} ({len(findings_list)})\n")

            for finding in findings_list[:20]:
                file_path = finding.get("file", "unknown")
                lineno = finding.get("lineno", "?")
                name = finding.get("name", "")
                output.append(f"- `{file_path}` (Line {lineno})")
                if name:
                    output.append(f" — {name}")
                output.append("\n")

            if len(findings_list) > 20:
                output.append(f"\n*... and {len(findings_list) - 20} more ...*\n\n")

    # Cleanup Strategy
    output.append("## Recommended Cleanup Strategy\n")
    output.append(
        """
### Phase 1: Version Guard Removal

1. **Review** all version-guarded blocks in safe-to-remove.json
2. **Verify** no dynamic calls to functions inside guards
3. **Remove** the entire if/else block and simplify control flow

Example:
```python
# Before
if sys.version_info[0] < 3:
    def compat_func():
        pass
else:
    def compat_func():
        pass

# After
def compat_func():
    pass
```

### Phase 2: Compatibility Function Removal

1. **Review** compatibility functions in safe-to-remove.json
2. **Check** if they're called from anywhere (use find-in-files)
3. **Replace** any calls with direct Py3 equivalents
4. **Remove** the function definition

### Phase 3: Unused Import Cleanup

1. **Remove** imports marked as unused
2. **Run tests** to ensure no dynamic imports break
3. **Check CI/coverage** for any regressions

### Phase 4: Dead Test Code Removal

1. **Remove** test functions decorated with @skipIf(PY3) or similar
2. **Remove** associated fixtures and test utilities
3. **Update** CI to only run non-skipped tests

### Verification

- Run full test suite after each phase
- Check code coverage before and after
- Review git diff to confirm removals are correct
- Run type checker (mypy) to catch any issues

"""
    )

    # Guidelines
    output.append("## Dead Code Detection Guidelines\n")
    output.append(
        """
### What Gets Marked as Dead

- **Version guards**: Code inside `if PY2:`, `if sys.version_info[0] < 3:`, etc.
- **Compatibility functions**: Functions matching patterns like `ensure_*`, `to_*`, `compat_*`
- **Unused imports**: Imports with no references in the code
- **Dead tests**: Tests with `@skipIf(PY3)` or similar decorators

### High Confidence Signals

- Inside version-guarded blocks (guaranteed dead in Py3)
- Only called from other dead code
- Explicitly marked with skip decorators
- Pattern matches + zero references

### Medium Confidence Signals

- No references found in codebase scan (could be dynamic)
- Compat function names but with some uses in live code
- Unused imports (could be for public API)

### Low Confidence Signals

- Name pattern suggests compat but actually used
- Heuristic matches without strong signals
- Requires manual review

### False Positives to Watch For

- Functions/imports used dynamically via getattr(), eval(), exec()
- Public API exported in __all__ (check __init__.py)
- Imports for side effects (import-time registration)
- Compatibility imports that are re-exported

""")

    # Cleanup Automation
    output.append("## Automated Removal Recommendations\n\n")
    output.append("""
### Using safe-to-remove.json

The `safe-to-remove.json` file contains HIGH-confidence findings only. These can be:

1. **Automatically removed** via CI/CD pipeline
2. **Manually reviewed** by engineers (recommended)
3. **Progressively removed** across multiple PRs (safest)

### Safe Removal Script

```bash
#!/bin/bash
# Remove safe-to-remove version-guarded blocks

python3 << 'EOF'
import json
with open('safe-to-remove.json') as f:
    data = json.load(f)

for finding in data['findings']:
    if finding['type'] == 'version_guard_dead_code':
        filepath = finding['file']
        startline = finding['lineno']
        endline = finding['endlineno']
        print(f"# Remove lines {startline}-{endline} from {filepath}")
EOF
```

### Testing After Removal

After each removal phase:

```bash
# Run full test suite
python3 -m pytest tests/ --tb=short

# Check code coverage
python3 -m pytest tests/ --cov=mymodule --cov-report=html

# Run type checker
mypy src/ --strict

# Check for import errors
python3 -m py_compile src/**/*.py
```

""")

    # Common Patterns to Remove
    output.append("## Common Dead Code Patterns\n\n")
    output.append("""
### Pattern 1: Version Guard Wrapper

Before (dead code inside `if PY2:`):
```python
if sys.version_info[0] < 3:
    def ensure_bytes(s):
        if isinstance(s, unicode):
            return s.encode('utf-8')
        return s
else:
    def ensure_bytes(s):
        if isinstance(s, bytes):
            return s
        return s.encode('utf-8')
```

After (remove if block, keep else):
```python
def ensure_bytes(s):
    if isinstance(s, bytes):
        return s
    return s.encode('utf-8')
```

### Pattern 2: Unused Import Chain

Before (importing compat package):
```python
import six
from six import string_types, text_type
```

After (remove if unused):
```python
# Removed unused imports
```

### Pattern 3: Dead Test Code

Before (skipped test):
```python
@skipIf(PY3, "Py2-only test")
def test_unicode_coercion():
    # This test never runs in Py3
    pass
```

After (remove entirely):
```python
# Test removed — no longer needed in Py3
```

### Pattern 4: Compat Function

Before (compatibility function):
```python
def to_native_str(s):
    \"\"\"Convert bytes or unicode to native string.\"\"\"
    if six.PY3:
        if isinstance(s, bytes):
            return s.decode('utf-8')
        return str(s)
    else:
        if isinstance(s, unicode):
            return s.encode('utf-8')
        return str(s)
```

After (simplify):
```python
def to_native_str(s):
    \"\"\"Convert bytes to native string.\"\"\"
    if isinstance(s, bytes):
        return s.decode('utf-8')
    return str(s)
```

""")

    return "\n".join(output)


# ── Main Entry Point ────────────────────────────────────────────────────────

@log_execution
def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Markdown report from dead code detection results"
    )
    parser.add_argument("report_json", help="Path to dead-code-report.json")
    parser.add_argument("--output", default="dead-code-report.md",
                       help="Output Markdown file (default: dead-code-report.md)")
    parser.add_argument("--safe-json", default=None,
                       help="Path to safe-to-remove.json")

    args = parser.parse_args()

    # Load reports
    report_data = load_json(args.report_json)
    if not report_data:
        print(f"Error: Could not load {args.report_json}", file=sys.stderr)
        sys.exit(1)

    # Try to auto-locate safe-to-remove.json
    safe_json_path = args.safe_json
    if not safe_json_path:
        # Look in same directory as report
        report_dir = os.path.dirname(os.path.abspath(args.report_json))
        auto_path = os.path.join(report_dir, "safe-to-remove.json")
        if os.path.exists(auto_path):
            safe_json_path = auto_path

    safe_data = load_json(safe_json_path) if safe_json_path else {}

    # Generate report
    markdown = generate_report(report_data, safe_data)

    # Write output
    with open(args.output, "w") as f:
        f.write(markdown)

    print(f"Wrote: {args.output}")
    sys.exit(0)


if __name__ == "__main__":
    main()
