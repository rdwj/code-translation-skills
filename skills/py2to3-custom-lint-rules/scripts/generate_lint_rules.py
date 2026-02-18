#!/usr/bin/env python3
"""
Custom Lint Rule Generator — Main Lint Rules Generation Script

Reads Phase 0 analysis outputs to understand project structure and generates:
  - AST-based pylint plugin (py2_idioms_checker.py)
  - Pattern-based flake8 plugin (flake8_project_checker.py)
  - Per-phase pylintrc files (pylintrc-phase1 through pylintrc-phase4)
  - .pre-commit-config.yaml for both plugins
  - lint-rules-report.json with all rule definitions

Produces:
  - plugins/py2_idioms_checker.py — Pylint plugin
  - plugins/flake8_project_checker.py — Flake8 plugin
  - pylintrc-phase1 through pylintrc-phase4 — Phase-specific configs
  - .pre-commit-config.yaml — Pre-commit hook configuration
  - lint-rules-report.json — Rule definitions and metadata

Usage:
    # Auto-detect patterns from Phase 0 analysis
    python3 generate_lint_rules.py <phase_0_analysis_dir> --output <output_dir>

    # With custom project patterns
    python3 generate_lint_rules.py <phase_0_analysis_dir> --output <output_dir> \\
        --project-patterns custom-patterns.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ──────────────────────────────────────────────────────────────────────────────

def load_json(path: str) -> Dict[str, Any]:
    """Load JSON from file."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(path: str, data: Dict[str, Any]) -> None:
    """Save JSON to file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def write_file(path: str, content: str) -> None:
    """Write content to file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


# ──────────────────────────────────────────────────────────────────────────────
# Analyze Phase 0 Outputs
# ──────────────────────────────────────────────────────────────────────────────

def analyze_phase0_outputs(analysis_dir: str) -> Dict[str, Any]:
    """Analyze Phase 0 outputs to extract project patterns."""

    analysis = {
        "has_scada": False,
        "has_binary_io": False,
        "has_pickle": False,
        "has_encoding_issues": False,
        "modules_by_type": {},
        "module_count": 0,
    }

    analysis_path = Path(analysis_dir)

    # Try to load raw-scan.json
    raw_scan = load_json(str(analysis_path / "raw-scan.json"))
    if raw_scan and "files" in raw_scan:
        analysis["module_count"] = len(raw_scan["files"])

    # Try to load data-layer-report.json
    data_layer = load_json(str(analysis_path / "data-layer-report.json"))
    if data_layer:
        if "serialization_patterns" in data_layer:
            analysis["has_pickle"] = True
            analysis["has_binary_io"] = True
        if "scada_handlers" in data_layer:
            analysis["has_scada"] = True

    # Try to load encoding issues
    try:
        for file in analysis_path.glob("*encoding*.json"):
            analysis["has_encoding_issues"] = True
            break
    except Exception:
        pass

    return analysis


# ──────────────────────────────────────────────────────────────────────────────
# Generate Pylint Plugin
# ──────────────────────────────────────────────────────────────────────────────

def generate_pylint_plugin() -> str:
    """Generate AST-based pylint plugin for Python 2 idiom detection."""

    plugin_code = '''"""
Pylint Plugin: py2_idioms_checker

Detects Python 2 idioms and enforces migration discipline across phases.
Each phase has specific rules that progressively enforce Python 3 standards.
"""

from pylint.checkers import BaseChecker
from pylint.interfaces import IAstroidChecker
import astroid


class Py2IdiomsChecker(BaseChecker):
    """Checker for Python 2 idioms during migration."""

    __implements__ = (IAstroidChecker,)

    name = "py2-idioms"
    priority = -1
    msgs = {
        "PY2001": (
            "Module missing __future__ imports",
            "missing-future-imports",
            "Phase 1+: All modules should have from __future__ import statements",
        ),
        "PY2002": (
            "Using print statement instead of print_function",
            "print-statement",
            "Phase 1+: Should use from __future__ import print_function",
        ),
        "PY2003": (
            "Using old except syntax (except E, e:)",
            "old-except-syntax",
            "Phase 1+: Use except E as e: instead",
        ),
        "PY2004": (
            "Using xrange() instead of range()",
            "xrange-builtin",
            "Phase 2+: xrange was renamed to range in Python 3",
        ),
        "PY2005": (
            "Using .iteritems() instead of .items()",
            "iteritems-method",
            "Phase 2+: Use .items() for Python 3 compatibility",
        ),
        "PY2006": (
            "Using basestring instead of str",
            "basestring-builtin",
            "Phase 2+: basestring was removed in Python 3",
        ),
        "PY2007": (
            "Using __unicode__ method instead of __str__",
            "unicode-method",
            "Phase 3+: Python 3 uses __str__ for unicode strings",
        ),
        "PY2008": (
            "Using six.string_types for type checks",
            "six-string-types",
            "Phase 3+: Use str directly instead of six.string_types",
        ),
        "PY2009": (
            "Using future library imports",
            "future-imports",
            "Phase 3+: future library should be removed in Python 3",
        ),
        "PY2010": (
            "Potential bytes/str mixing",
            "bytes-str-mixing",
            "Phase 3+: Ensure consistent bytes/str handling",
        ),
        "PY2011": (
            "Public function missing type annotations",
            "missing-type-annotations",
            "Phase 4+: Public functions should have type annotations",
        ),
    }

    def visit_module(self, node):
        """Check module for future imports."""
        # Check for __future__ imports
        has_future = False
        for child in node.body:
            if isinstance(child, astroid.ImportFrom):
                if child.modname == "__future__":
                    has_future = True
                    break

        if not has_future and node.name and not node.name.startswith("_"):
            # Skip private modules and __init__.py for now
            if node.name != "__init__":
                self.add_message("PY2001", node=node)

    def visit_name(self, node):
        """Check for Python 2 builtins."""
        if node.name == "xrange":
            self.add_message("PY2004", node=node)
        elif node.name == "basestring":
            self.add_message("PY2006", node=node)
        elif node.name == "unicode":
            self.add_message("PY2006", node=node)

    def visit_call(self, node):
        """Check for method calls like .iteritems()."""
        if isinstance(node.func, astroid.Attribute):
            if node.func.attrname in ("iteritems", "iterkeys", "itervalues"):
                self.add_message("PY2005", node=node)

    def visit_functiondef(self, node):
        """Check for __unicode__ methods."""
        if node.name == "__unicode__":
            self.add_message("PY2007", node=node)


def register(linter):
    """Register the checker with pylint."""
    linter.register_checker(Py2IdiomsChecker(linter))
'''
    return plugin_code


# ──────────────────────────────────────────────────────────────────────────────
# Generate Flake8 Plugin
# ──────────────────────────────────────────────────────────────────────────────

def generate_flake8_plugin(analysis: Dict[str, Any], custom_patterns: Dict[str, Any]) -> str:
    """Generate pattern-based flake8 plugin for project-specific rules."""

    has_scada = analysis.get("has_scada", False) or custom_patterns.get("scada_modules")
    has_binary = analysis.get("has_binary_io", False) or custom_patterns.get("binary_modules")
    has_pickle = analysis.get("has_pickle", False) or custom_patterns.get("pickle_modules")
    requires_encoding = custom_patterns.get("requires_encoding", has_scada)

    rules = []

    if requires_encoding:
        rules.append("""
    E950 = "SCADA module missing encoding declaration"
""")

    if has_binary:
        rules.append("""
    E951 = "Binary I/O module should use binary mode"
""")

    if has_pickle:
        rules.append("""
    E952 = "Pickle usage should specify protocol version"
""")

    rules_str = "".join(rules) if rules else ""

    plugin_code = f'''"""
Flake8 Plugin: flake8_project_checker

Project-specific linting rules for Python 2→3 migration.
Enforces patterns discovered in Phase 0 analysis.
"""

import re
from typing import Generator, Tuple


class ProjectChecker:
    """Project-specific pattern checker for flake8."""

    name = "project-checker"
    version = "1.0.0"

    def __init__(self, tree):
        self.tree = tree
        self.filename = ""
        self.lines = []

    def __call__(self, physical_line, line_number):
        """Check a single line."""
        if not self.lines:
            return

        line = self.lines[line_number - 1] if line_number <= len(self.lines) else ""

        # E950: SCADA module encoding check
        if {requires_encoding} and "scada" in self.filename.lower():
            if line_number <= 2 and not re.search(r"coding[:=]", line):
                if line_number == 2:  # Only report on second line to avoid duplicates
                    yield (0, "E950 SCADA module missing encoding declaration")

        # E951: Binary I/O mode check
        if {has_binary}:
            if re.search(r'open\\([^,)]*["\'](?!b)[rb]["\']', line):
                if "rb" not in line and "wb" not in line:
                    yield (0, "E951 Binary I/O should use binary mode (rb/wb)")

        # E952: Pickle protocol check
        if {has_pickle}:
            if re.search(r'pickle\\.(dumps?|loads)', line):
                if "protocol=" not in line:
                    yield (0, "E952 Pickle should specify protocol version")

    def run(self) -> Generator[Tuple[int, int, str, type], None, None]:
        """Run the checker on the file."""
        self.lines = self.tree.split("\\n")
        for line_number, line in enumerate(self.lines, 1):
            yield from self.__call__(line, line_number)


def load_config(config):
    """Load configuration (no-op for now)."""
    pass
'''
    return plugin_code


# ──────────────────────────────────────────────────────────────────────────────
# Generate Per-Phase Pylintrc Files
# ──────────────────────────────────────────────────────────────────────────────

def generate_pylintrc_phase1() -> str:
    """Generate pylintrc for Phase 1 (Inject futures)."""
    return """[MASTER]
load-plugins=py2_idioms_checker
jobs=1

[MESSAGES CONTROL]
disable=
    missing-docstring,
    too-many-arguments,
    too-many-locals,
    too-few-public-methods,
    too-many-branches,
    too-many-statements

[REPORTS]
reports=yes
score=yes

[FORMAT]
max-line-length=100

[DESIGN]
max-attributes=10
max-arguments=5
"""


def generate_pylintrc_phase2() -> str:
    """Generate pylintrc for Phase 2 (Py3 syntax conversion)."""
    return """[MASTER]
load-plugins=py2_idioms_checker
jobs=1

[MESSAGES CONTROL]
disable=
    missing-docstring,
    too-many-arguments,
    too-many-locals,
    too-few-public-methods,
    too-many-branches,
    too-many-statements

enable=
    PY2001,
    PY2002,
    PY2003,
    PY2004,
    PY2005,
    PY2006

[REPORTS]
reports=yes
score=yes

[FORMAT]
max-line-length=100

[DESIGN]
max-attributes=10
max-arguments=5
"""


def generate_pylintrc_phase3() -> str:
    """Generate pylintrc for Phase 3 (Remove compat shims)."""
    return """[MASTER]
load-plugins=py2_idioms_checker,flake8_project_checker
jobs=1

[MESSAGES CONTROL]
disable=
    missing-docstring,
    too-many-arguments,
    too-many-locals,
    too-few-public-methods

enable=
    PY2001,
    PY2002,
    PY2003,
    PY2004,
    PY2005,
    PY2006,
    PY2007,
    PY2008,
    PY2009,
    PY2010

[REPORTS]
reports=yes
score=yes

[FORMAT]
max-line-length=100

[DESIGN]
max-attributes=10
"""


def generate_pylintrc_phase4() -> str:
    """Generate pylintrc for Phase 4 (Final Python 3)."""
    return """[MASTER]
load-plugins=py2_idioms_checker,flake8_project_checker
jobs=1

[MESSAGES CONTROL]
disable=
    too-few-public-methods

enable=
    PY2001,
    PY2002,
    PY2003,
    PY2004,
    PY2005,
    PY2006,
    PY2007,
    PY2008,
    PY2009,
    PY2010,
    PY2011

[REPORTS]
reports=yes
score=yes

[FORMAT]
max-line-length=100

[DESIGN]
max-attributes=10
"""


# ──────────────────────────────────────────────────────────────────────────────
# Generate Pre-Commit Config
# ──────────────────────────────────────────────────────────────────────────────

def generate_precommit_config() -> str:
    """Generate .pre-commit-config.yaml."""
    return """# Pre-commit hooks for Python 2→3 migration
# Run this before committing to catch migration regressions

repos:
  - repo: local
    hooks:
      - id: pylint-py2-idioms
        name: Pylint (Python 2 idioms)
        entry: pylint --load-plugins=.lint-plugins.py2_idioms_checker
        language: system
        types: [python]
        require_serial: true
        stages: [commit]

      - id: flake8-project
        name: Flake8 (Project-specific rules)
        entry: flake8 --select=E950,E951,E952
        language: system
        types: [python]
        stages: [commit]

      - id: pyupgrade
        name: Pyupgrade
        entry: pyupgrade --py39-plus
        language: system
        types: [python]
        stages: [commit]
        require_serial: true
"""


# ──────────────────────────────────────────────────────────────────────────────
# Main Function
# ──────────────────────────────────────────────────────────────────────────────

def generate_lint_rules(
    analysis_dir: str,
    output_dir: str,
    target_version: str = "3.9",
    project_patterns_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate all lint rules and configurations.

    Returns report dict.
    """

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    # Analyze Phase 0 outputs
    analysis = analyze_phase0_outputs(analysis_dir)

    # Load custom patterns if provided
    custom_patterns = {}
    if project_patterns_file:
        try:
            custom_patterns = load_json(project_patterns_file)
        except Exception as e:
            print(f"Warning: Could not load custom patterns: {e}")

    # Generate plugins directory
    plugins_dir = out_path / "plugins"
    plugins_dir.mkdir(exist_ok=True)

    # Generate pylint plugin
    pylint_plugin = generate_pylint_plugin()
    write_file(str(plugins_dir / "py2_idioms_checker.py"), pylint_plugin)

    # Generate flake8 plugin
    flake8_plugin = generate_flake8_plugin(analysis, custom_patterns)
    write_file(str(plugins_dir / "flake8_project_checker.py"), flake8_plugin)

    # Generate __init__.py for plugins
    write_file(str(plugins_dir / "__init__.py"), "# Lint plugins package\n")

    # Generate per-phase pylintrc files
    write_file(str(out_path / "pylintrc-phase1"), generate_pylintrc_phase1())
    write_file(str(out_path / "pylintrc-phase2"), generate_pylintrc_phase2())
    write_file(str(out_path / "pylintrc-phase3"), generate_pylintrc_phase3())
    write_file(str(out_path / "pylintrc-phase4"), generate_pylintrc_phase4())

    # Generate pre-commit config
    write_file(str(out_path / ".pre-commit-config.yaml"), generate_precommit_config())

    # Build report
    pylint_rules = [
        {"code": "PY2001", "message": "Module missing __future__ imports", "phase": 1, "category": "future-imports", "automatable": True},
        {"code": "PY2002", "message": "Using print statement", "phase": 1, "category": "syntax", "automatable": True},
        {"code": "PY2003", "message": "Using old except syntax", "phase": 1, "category": "syntax", "automatable": True},
        {"code": "PY2004", "message": "Using xrange()", "phase": 2, "category": "stdlib", "automatable": True},
        {"code": "PY2005", "message": "Using .iteritems()", "phase": 2, "category": "stdlib", "automatable": True},
        {"code": "PY2006", "message": "Using basestring", "phase": 2, "category": "stdlib", "automatable": True},
        {"code": "PY2007", "message": "Using __unicode__ method", "phase": 3, "category": "syntax", "automatable": True},
        {"code": "PY2008", "message": "Using six.string_types", "phase": 3, "category": "compat", "automatable": True},
        {"code": "PY2009", "message": "Using future library", "phase": 3, "category": "compat", "automatable": True},
        {"code": "PY2010", "message": "Bytes/str mixing", "phase": 3, "category": "semantic", "automatable": False},
        {"code": "PY2011", "message": "Missing type annotations", "phase": 4, "category": "typing", "automatable": False},
    ]

    flake8_rules = []
    if custom_patterns.get("requires_encoding") or analysis.get("has_scada"):
        flake8_rules.append({
            "code": "E950",
            "message": "SCADA module missing encoding declaration",
            "pattern": "scada",
            "automatable": False
        })

    if analysis.get("has_binary_io") or custom_patterns.get("binary_modules"):
        flake8_rules.append({
            "code": "E951",
            "message": "Binary I/O should use binary mode",
            "pattern": "binary",
            "automatable": True
        })

    if analysis.get("has_pickle") or custom_patterns.get("pickle_modules"):
        flake8_rules.append({
            "code": "E952",
            "message": "Pickle should specify protocol version",
            "pattern": "pickle",
            "automatable": True
        })

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "analysis_dir": analysis_dir,
        "target_python3_version": target_version,
        "rules_generated": {
            "pylint_plugin": {
                "count": len(pylint_rules),
                "rules": pylint_rules,
            },
            "flake8_plugin": {
                "count": len(flake8_rules),
                "rules": flake8_rules,
            }
        },
        "analysis_summary": analysis,
        "custom_patterns": custom_patterns,
        "configuration_files": {
            "pylintrc_phase1": "pylintrc-phase1",
            "pylintrc_phase2": "pylintrc-phase2",
            "pylintrc_phase3": "pylintrc-phase3",
            "pylintrc_phase4": "pylintrc-phase4",
            "pre_commit_config": ".pre-commit-config.yaml",
            "py2_idioms_plugin": "plugins/py2_idioms_checker.py",
            "flake8_project_plugin": "plugins/flake8_project_checker.py",
        }
    }

    return report


# ──────────────────────────────────────────────────────────────────────────────
# main()
# ──────────────────────────────────────────────────────────────────────────────

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate custom lint rules and configurations for migration phases"
    )
    parser.add_argument(
        "analysis_dir",
        help="Phase 0 analysis output directory"
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output directory for generated rules and configs"
    )
    parser.add_argument(
        "--target-version",
        default="3.9",
        choices=["3.9", "3.11", "3.12", "3.13"],
        help="Target Python 3 version (default: 3.9)"
    )
    parser.add_argument(
        "--project-patterns",
        help="JSON file with custom project patterns"
    )

    args = parser.parse_args()

    # Validate inputs
    if not Path(args.analysis_dir).exists():
        print(f"Error: analysis_dir not found: {args.analysis_dir}", file=sys.stderr)
        sys.exit(1)

    if args.project_patterns and not Path(args.project_patterns).exists():
        print(f"Error: project_patterns file not found: {args.project_patterns}", file=sys.stderr)
        sys.exit(1)

    # Run generation
    try:
        report = generate_lint_rules(
            args.analysis_dir,
            args.output,
            target_version=args.target_version,
            project_patterns_file=args.project_patterns,
        )

        # Save report
        report_path = Path(args.output) / "lint-rules-report.json"
        save_json(str(report_path), report)

        print(f"Lint rules generated successfully")
        print(f"Report: {report_path}")
        print(f"Configuration files:")
        for name, path in report["configuration_files"].items():
            print(f"  - {path}")
        print(f"Total rules generated: {report['rules_generated']['pylint_plugin']['count'] + report['rules_generated']['flake8_plugin']['count']}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
