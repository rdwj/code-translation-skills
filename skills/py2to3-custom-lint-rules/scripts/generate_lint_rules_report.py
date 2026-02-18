#!/usr/bin/env python3
"""
Custom Lint Rule Generator — Report Generator

Reads lint-rules-report.json and produces a comprehensive Markdown report
documenting all custom rules, their phases, examples, and configuration guidance.

Usage:
    python3 generate_lint_rules_report.py <lint-rules-report.json> --output <report.md>
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


def load_json(path: str) -> Dict[str, Any]:
    """Load JSON from file."""
    with open(path, 'r') as f:
        return json.load(f)


def write_file(path: str, content: str) -> None:
    """Write content to file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


def generate_rule_examples() -> Dict[str, Dict[str, str]]:
    """Generate code examples for each rule."""
    return {
        "PY2001": {
            "title": "Module Missing __future__ Imports",
            "bad": '''"""Module docstring."""

print "Hello"  # Using print statement
x = 5
y = 2 / 3  # Integer division
''',
            "good": '''"""Module docstring."""
from __future__ import print_function, division, absolute_import

print("Hello")  # Using print function
x = 5
y = 2 / 3  # True division (5.0 / 3)
'''
        },
        "PY2002": {
            "title": "Print Statement",
            "bad": 'print "Hello, world"',
            "good": 'print("Hello, world")'
        },
        "PY2003": {
            "title": "Old Except Syntax",
            "bad": '''try:
    something()
except ValueError, e:
    print(e)
''',
            "good": '''try:
    something()
except ValueError as e:
    print(e)
'''
        },
        "PY2004": {
            "title": "xrange() Builtin",
            "bad": 'for i in xrange(10):\n    print(i)',
            "good": 'for i in range(10):\n    print(i)'
        },
        "PY2005": {
            "title": ".iteritems() Method",
            "bad": '''d = {"a": 1, "b": 2}
for k, v in d.iteritems():
    print(k, v)
''',
            "good": '''d = {"a": 1, "b": 2}
for k, v in d.items():
    print(k, v)
'''
        },
        "PY2006": {
            "title": "basestring Type",
            "bad": '''def process_string(s):
    if isinstance(s, basestring):
        return s.upper()
''',
            "good": '''def process_string(s):
    if isinstance(s, str):
        return s.upper()
'''
        },
        "PY2007": {
            "title": "__unicode__ Method",
            "bad": '''class MyClass:
    def __unicode__(self):
        return u"MyClass instance"
''',
            "good": '''class MyClass:
    def __str__(self):
        return "MyClass instance"
'''
        },
        "PY2008": {
            "title": "six.string_types",
            "bad": '''import six

if isinstance(obj, six.string_types):
    print("It's a string")
''',
            "good": '''if isinstance(obj, str):
    print("It's a string")
'''
        },
        "PY2009": {
            "title": "future Library Usage",
            "bad": '''from builtins import str
from builtins import dict
x = dict(a=1)
''',
            "good": '''# Just use native Python 3 builtins
x = dict(a=1)
'''
        },
        "PY2010": {
            "title": "Bytes/String Mixing",
            "bad": '''# Mixing bytes and strings
data = b"prefix_" + "suffix"  # Error!
header = "HEADER" + struct.pack("i", 42)  # Error!
''',
            "good": '''# Keep types consistent
data = b"prefix_" + b"suffix"
header = b"HEADER" + struct.pack("i", 42)
'''
        },
        "PY2011": {
            "title": "Missing Type Annotations",
            "bad": '''def process_data(records):
    """Process a list of records."""
    return [r.upper() for r in records]
''',
            "good": '''def process_data(records: List[str]) -> List[str]:
    """Process a list of records."""
    return [r.upper() for r in records]
'''
        },
        "E950": {
            "title": "SCADA Module Missing Encoding",
            "bad": '''"""Modbus protocol handler."""

def read_registers(address):
    return None
''',
            "good": '''# coding: utf-8
"""Modbus protocol handler."""

def read_registers(address):
    return None
'''
        },
        "E951": {
            "title": "Binary I/O Mode",
            "bad": '''# Wrong: opening binary file in text mode
with open("data.pkl") as f:
    data = pickle.load(f)
''',
            "good": '''# Correct: opening binary file in binary mode
with open("data.pkl", "rb") as f:
    data = pickle.load(f)
'''
        },
        "E952": {
            "title": "Pickle Protocol Version",
            "bad": '''import pickle

data = pickle.dumps(obj)  # Uses default protocol
''',
            "good": '''import pickle

data = pickle.dumps(obj, protocol=2)  # Explicit protocol
'''
        },
    }


def generate_report(report_data: Dict[str, Any]) -> str:
    """Generate comprehensive Markdown report."""

    lines = []
    lines.append("# Custom Lint Rules Documentation")
    lines.append("")
    lines.append("## Overview")
    lines.append("")
    lines.append("This document describes all custom lint rules generated for your Python 2→3")
    lines.append("migration. Each rule is tagged with a migration phase and category, helping you")
    lines.append("understand what each check enforces and why it matters.")
    lines.append("")

    # Summary
    pylint_rules = report_data.get("rules_generated", {}).get("pylint_plugin", {}).get("rules", [])
    flake8_rules = report_data.get("rules_generated", {}).get("flake8_plugin", {}).get("rules", [])
    total_rules = len(pylint_rules) + len(flake8_rules)

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total rules**: {total_rules}")
    lines.append(f"- **Pylint rules**: {len(pylint_rules)}")
    lines.append(f"- **Flake8 rules**: {len(flake8_rules)}")
    lines.append(f"- **Target Python 3 version**: {report_data.get('target_python3_version', '3.9')}")
    lines.append("")

    # Phase organization
    lines.append("## Rules by Phase")
    lines.append("")

    examples = generate_rule_examples()

    for phase in range(1, 5):
        phase_rules = [r for r in pylint_rules if r.get("phase") == phase]
        if not phase_rules:
            continue

        lines.append(f"### Phase {phase}")
        lines.append("")

        phase_descriptions = {
            1: "Inject `__future__` imports to prepare code for Python 3 compatibility.",
            2: "Convert Python 2-specific syntax to Python 3 syntax.",
            3: "Remove compatibility shims (six, future libraries) that are no longer needed.",
            4: "Enforce strict Python 3 standards including type annotations."
        }

        lines.append(phase_descriptions.get(phase, ""))
        lines.append("")

        for rule in phase_rules:
            code = rule.get("code", "")
            message = rule.get("message", "")
            category = rule.get("category", "")
            automatable = rule.get("automatable", False)

            lines.append(f"#### {code}: {message}")
            lines.append("")
            lines.append(f"**Category**: {category.capitalize()}")
            lines.append(f"**Automatable**: {'Yes' if automatable else 'No'}")
            lines.append("")

            if code in examples:
                ex = examples[code]
                lines.append("**Example**")
                lines.append("")
                lines.append("❌ Wrong:")
                lines.append("")
                lines.append("```python")
                lines.append(ex["bad"])
                lines.append("```")
                lines.append("")
                lines.append("✓ Correct:")
                lines.append("")
                lines.append("```python")
                lines.append(ex["good"])
                lines.append("```")
                lines.append("")

    # Flake8 rules
    if flake8_rules:
        lines.append("## Project-Specific Rules (Flake8)")
        lines.append("")
        lines.append("These rules enforce patterns discovered during Phase 0 analysis of your")
        lines.append("specific codebase.")
        lines.append("")

        for rule in flake8_rules:
            code = rule.get("code", "")
            message = rule.get("message", "")
            pattern = rule.get("pattern", "")

            lines.append(f"### {code}: {message}")
            lines.append("")
            lines.append(f"**Pattern**: {pattern}")
            lines.append("")

            if code in examples:
                ex = examples[code]
                lines.append("**Example**")
                lines.append("")
                lines.append("❌ Wrong:")
                lines.append("")
                lines.append("```python")
                lines.append(ex["bad"])
                lines.append("```")
                lines.append("")
                lines.append("✓ Correct:")
                lines.append("")
                lines.append("```python")
                lines.append(ex["good"])
                lines.append("```")
                lines.append("")

    # Configuration guidance
    lines.append("## Configuration and Usage")
    lines.append("")

    lines.append("### Phase-Specific Pylintrc Files")
    lines.append("")
    lines.append("Four pylintrc files are generated, one for each phase:")
    lines.append("")
    lines.append("- **pylintrc-phase1**: Basic checks for `__future__` imports and print statements")
    lines.append("- **pylintrc-phase2**: Adds checks for Python 2 stdlib calls and types")
    lines.append("- **pylintrc-phase3**: Adds checks for compatibility library usage")
    lines.append("- **pylintrc-phase4**: Adds checks for type annotations and modern Python 3 style")
    lines.append("")

    lines.append("### Using in CI/CD")
    lines.append("")
    lines.append("Configure your CI pipeline to use the appropriate pylintrc for each phase:")
    lines.append("")
    lines.append("```bash")
    lines.append("# Phase 1: Only check __future__ imports")
    lines.append("pylint --rcfile=pylintrc-phase1 app/")
    lines.append("")
    lines.append("# Phase 2: Check for Py2 syntax issues")
    lines.append("pylint --rcfile=pylintrc-phase2 app/")
    lines.append("")
    lines.append("# Phase 3: Check for compat library usage")
    lines.append("pylint --rcfile=pylintrc-phase3 app/")
    lines.append("")
    lines.append("# Phase 4: Full Python 3 enforcement")
    lines.append("pylint --rcfile=pylintrc-phase4 app/")
    lines.append("```")
    lines.append("")

    lines.append("### Using Custom Plugins Locally")
    lines.append("")
    lines.append("Copy the generated plugins to your project:")
    lines.append("")
    lines.append("```bash")
    lines.append("mkdir -p .lint-plugins")
    lines.append("cp plugins/*.py .lint-plugins/")
    lines.append("```")
    lines.append("")
    lines.append("Then load them when running pylint:")
    lines.append("")
    lines.append("```bash")
    lines.append("pylint --load-plugins=.lint_plugins.py2_idioms_checker app/")
    lines.append("```")
    lines.append("")

    lines.append("### Using Pre-Commit Hooks")
    lines.append("")
    lines.append("Install pre-commit and use the generated configuration:")
    lines.append("")
    lines.append("```bash")
    lines.append("pip install pre-commit")
    lines.append("cp .pre-commit-config.yaml ./")
    lines.append("pre-commit install")
    lines.append("")
    lines.append("# Run all hooks on all files")
    lines.append("pre-commit run --all-files")
    lines.append("```")
    lines.append("")

    # Rule categories
    lines.append("## Rules by Category")
    lines.append("")

    categories = {}
    for rule in pylint_rules:
        cat = rule.get("category", "unknown")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(rule)

    for cat in sorted(categories.keys()):
        rules = categories[cat]
        lines.append(f"### {cat.capitalize()}")
        lines.append("")
        for rule in rules:
            lines.append(f"- **{rule.get('code')}**: {rule.get('message')}")
        lines.append("")

    # Integration guide
    lines.append("## Integration with Migration Process")
    lines.append("")
    lines.append("### Before Phase Transition")
    lines.append("")
    lines.append("Before moving a module from phase N to phase N+1:")
    lines.append("")
    lines.append("1. Run pylint with the target phase's pylintrc:")
    lines.append("   ```bash")
    lines.append("   pylint --rcfile=pylintrc-phaseN+1 module.py")
    lines.append("   ```")
    lines.append("")
    lines.append("2. Fix all reported issues")
    lines.append("")
    lines.append("3. Commit with message: `Phase N→N+1 migration: module.py`")
    lines.append("")

    lines.append("### Continuous Enforcement")
    lines.append("")
    lines.append("Use the phase-specific pylintrc in your CI pipeline:")
    lines.append("")
    lines.append("```yaml")
    lines.append("# Example GitHub Actions")
    lines.append("- name: Lint with phase-specific pylint")
    lines.append("  run: |")
    lines.append("    pylint --rcfile=pylintrc-phase${{ env.CURRENT_PHASE }} app/")
    lines.append("```")
    lines.append("")

    lines.append("### Per-Module Migration Tracking")
    lines.append("")
    lines.append("Track which phase each module is in:")
    lines.append("")
    lines.append("```json")
    lines.append("{")
    lines.append("  \"modules\": {")
    lines.append("    \"app/core/utils.py\": {\"phase\": 3, \"lint_status\": \"pass\"},")
    lines.append("    \"app/api/handlers.py\": {\"phase\": 2, \"lint_status\": \"pass\"},")
    lines.append("    \"app/scada/modbus.py\": {\"phase\": 1, \"lint_status\": \"pass\"}")
    lines.append("  }")
    lines.append("}")
    lines.append("```")
    lines.append("")

    # Troubleshooting
    lines.append("## Troubleshooting")
    lines.append("")

    lines.append("### Plugin Not Loading")
    lines.append("")
    lines.append("If pylint can't find the custom plugins:")
    lines.append("")
    lines.append("1. Ensure the `.lint-plugins` directory exists")
    lines.append("2. Ensure `__init__.py` is in the plugins directory")
    lines.append("3. Use absolute paths if needed:")
    lines.append("   ```bash")
    lines.append("   pylint --load-plugins=/absolute/path/to/.lint-plugins.py2_idioms_checker")
    lines.append("   ```")
    lines.append("")

    lines.append("### False Positives")
    lines.append("")
    lines.append("Some rules may generate false positives:")
    lines.append("")
    lines.append("- **PY2010 (bytes/str mixing)**: May flag legitimate operations. Review and adjust")
    lines.append("  custom patterns if needed.")
    lines.append("- **PY2011 (missing type annotations)**: Doesn't detect inline type hints. Modern")
    lines.append("  code using `# type: ignore` comments won't trigger this.")
    lines.append("")

    lines.append("### Disabling Rules for Specific Files")
    lines.append("")
    lines.append("To disable a rule for a specific file:")
    lines.append("")
    lines.append("```python")
    lines.append("# pylint: disable=PY2001")
    lines.append("\"\"\"This module intentionally doesn't use __future__ imports.\"\"\"")
    lines.append("```")
    lines.append("")

    # Important notes
    lines.append("## Important Notes")
    lines.append("")

    lines.append("### Progression is Key")
    lines.append("")
    lines.append("Don't try to apply all phase 4 rules at once. Progress through phases in order:")
    lines.append("Phase 1 → Phase 2 → Phase 3 → Phase 4. Each phase builds on the previous one.")
    lines.append("")

    lines.append("### Automate What You Can")
    lines.append("")
    lines.append("Rules marked as 'Automatable' can be fixed with tools like `pyupgrade`, `autopep8`,")
    lines.append("or custom scripts. Use automation for mechanical changes, manual review for complex logic.")
    lines.append("")

    lines.append("### Test After Lint Fixes")
    lines.append("")
    lines.append("Always run your full test suite after fixing lint issues:")
    lines.append("")
    lines.append("```bash")
    lines.append("# Fix linting issues")
    lines.append("pylint --rcfile=pylintrc-phaseN app/")
    lines.append("")
    lines.append("# Run tests")
    lines.append("pytest tests/ -v")
    lines.append("")
    lines.append("# Test on both Python versions")
    lines.append("tox")
    lines.append("```")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"Report generated: {datetime.now().isoformat()}")
    lines.append("")
    lines.append("For more information, see the Custom Lint Rule Generator skill documentation.")

    return "\n".join(lines)


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate comprehensive lint rules documentation"
    )
    parser.add_argument(
        "report_json",
        help="Path to lint-rules-report.json"
    )
    parser.add_argument(
        "--output",
        default="lint-rules-documentation.md",
        help="Output Markdown file (default: lint-rules-documentation.md)"
    )

    args = parser.parse_args()

    # Validate input
    if not Path(args.report_json).exists():
        print(f"Error: file not found: {args.report_json}", file=sys.stderr)
        sys.exit(1)

    try:
        # Load JSON
        report_data = load_json(args.report_json)

        # Generate report
        report = generate_report(report_data)

        # Write report
        write_file(args.output, report)

        print(f"Documentation generated: {args.output}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
