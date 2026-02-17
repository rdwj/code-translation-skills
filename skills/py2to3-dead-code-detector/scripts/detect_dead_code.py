#!/usr/bin/env python3
"""
Dead Code Detector — Main Detection Script

Identifies code that was only reachable under Python 2, dead Py2 compatibility functions,
unused imports, unreachable code, and Py2 compatibility modules.

Usage:
    python3 detect_dead_code.py <codebase_path> \
        --target-version 3.12 \
        --output ./dead-code-output/

Output:
    dead-code-report.json — Complete inventory with confidence levels
    safe-to-remove.json — HIGH-confidence removals only
"""

import ast
import json
import os
import re
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Set, Tuple


# ── Helper Functions ─────────────────────────────────────────────────────────

def load_json(path: str) -> Dict:
    """Load JSON file, return empty dict if not found."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(data: Dict, path: str) -> None:
    """Save JSON to file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def read_file(path: str) -> str:
    """Read file contents."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (FileNotFoundError, UnicodeDecodeError):
        return ""


def should_skip(filepath: str, exclude_patterns: List[str]) -> bool:
    """Check if file matches exclusion patterns."""
    path_obj = Path(filepath)
    for pattern in exclude_patterns:
        if path_obj.match(pattern):
            return True
    return False


def is_test_file(filepath: str) -> bool:
    """Check if file is a test file."""
    name = Path(filepath).name
    return (
        name.startswith("test_") or name.endswith("_test.py") or
        "tests" in Path(filepath).parts or
        "test" in Path(filepath).parts
    )


# ── Version Guard Detection ──────────────────────────────────────────────────

VERSION_GUARD_PATTERNS = [
    r"sys\.version_info\[0\]\s*<\s*3",
    r"sys\.version_info\[0\]\s*==\s*2",
    r"sys\.version_info\s*<\s*\(3",
    r"sys\.version_info\s*==\s*\(2",
    r"\bPY2\b",
    r"six\.PY2",
    r"python_2",
]

INVERSE_VERSION_PATTERNS = [
    r"sys\.version_info\[0\]\s*>=\s*3",
    r"sys\.version_info\[0\]\s*>\s*2",
    r"sys\.version_info\s*>=\s*\(3",
    r"\bPY3\b",
    r"six\.PY3",
]

COMPAT_FUNCTION_PATTERNS = [
    r".*_compat$",
    r"^ensure_.*",
    r"^to_(text|bytes|unicode|native_str|str)",
    r"^compat_.*",
    r"^py2_.*",
    r"^py3_.*",
    r"^(string_types|text_type|binary_type|integer_types)$",
]


def is_version_guard(condition_str: str) -> Tuple[bool, bool]:
    """
    Check if condition is a version guard.
    Returns (is_guard, is_dead_in_py3).
    """
    for pattern in VERSION_GUARD_PATTERNS:
        if re.search(pattern, condition_str):
            return True, True  # Condition is dead in Py3

    for pattern in INVERSE_VERSION_PATTERNS:
        if re.search(pattern, condition_str):
            return True, False  # Condition is dead in else block

    return False, False


def extract_condition_str(node: ast.AST) -> Optional[str]:
    """Extract condition as string from AST node."""
    try:
        if isinstance(node, ast.Compare):
            return ast.unparse(node) if hasattr(ast, 'unparse') else None
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return ast.unparse(node) if hasattr(ast, 'unparse') else None
    except Exception:
        pass
    return None


# ── AST Analysis ─────────────────────────────────────────────────────────────

class CodeAnalyzer(ast.NodeVisitor):
    """AST visitor to analyze code structure."""

    def __init__(self, filepath: str, content: str):
        self.filepath = filepath
        self.content = content
        self.functions = {}  # name -> {lineno, endlineno, body}
        self.classes = {}
        self.imports = {}  # module -> {names, lineno}
        self.references = set()  # names referenced in code
        self.dead_blocks = []  # (lineno, endlineno, reason)
        self.decorators = defaultdict(list)  # function_name -> list of decorators

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Track function definitions."""
        self.functions[node.name] = {
            "lineno": node.lineno,
            "endlineno": node.end_lineno or node.lineno,
            "args": [arg.arg for arg in node.args.args],
            "decorators": [self._get_decorator_name(d) for d in node.decorator_list],
        }

        # Track decorator usage
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                self.decorators[node.name].append(dec.id)
            elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                self.decorators[node.name].append(dec.func.id)

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        """Track class definitions."""
        self.classes[node.name] = {
            "lineno": node.lineno,
            "endlineno": node.end_lineno or node.lineno,
            "bases": [self._get_base_name(b) for b in node.bases],
        }
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import):
        """Track imports."""
        for alias in node.names:
            self.imports[alias.name] = {
                "type": "import",
                "lineno": node.lineno,
                "asname": alias.asname,
            }
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Track from imports."""
        module = node.module or ""
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports[name] = {
                "type": "from",
                "module": module,
                "lineno": node.lineno,
                "asname": alias.asname,
            }
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        """Track name references (excluding definitions)."""
        if isinstance(node.ctx, (ast.Load, ast.Del)):
            self.references.add(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute):
        """Track attribute accesses."""
        self.references.add(node.attr)
        self.generic_visit(node)

    def visit_If(self, node: ast.If):
        """Track version-guarded blocks."""
        condition_str = extract_condition_str(node.test)
        if condition_str:
            is_guard, is_dead = is_version_guard(condition_str)
            if is_guard:
                if is_dead:
                    # If block is dead in Py3
                    if node.body:
                        end = node.body[-1].end_lineno or node.body[-1].lineno
                        self.dead_blocks.append({
                            "lineno": node.body[0].lineno,
                            "endlineno": end,
                            "reason": f"Version guard (dead in Py3): {condition_str}",
                            "confidence": "HIGH",
                        })
                else:
                    # Else block is dead in Py3
                    if node.orelse:
                        end = node.orelse[-1].end_lineno or node.orelse[-1].lineno
                        self.dead_blocks.append({
                            "lineno": node.orelse[0].lineno,
                            "endlineno": end,
                            "reason": f"Version guard (dead in Py3): {condition_str}",
                            "confidence": "HIGH",
                        })

        self.generic_visit(node)

    def visit_Return(self, node: ast.Return):
        """Track unreachable code after return statements."""
        self.generic_visit(node)

    def visit_Raise(self, node: ast.Raise):
        """Track unreachable code after raise statements."""
        self.generic_visit(node)

    def _check_unreachable_code(self, body: List[ast.stmt]) -> None:
        """Check for unreachable code in a block (after return/raise)."""
        for i, stmt in enumerate(body):
            if i == 0:
                continue
            # Check if previous statement is terminal (return/raise)
            prev = body[i - 1]
            is_terminal = isinstance(prev, (ast.Return, ast.Raise))
            if is_terminal:
                # Current statement is unreachable
                end = stmt.end_lineno or stmt.lineno
                self.dead_blocks.append({
                    "lineno": stmt.lineno,
                    "endlineno": end,
                    "reason": "Code after return/raise statement (unreachable)",
                    "confidence": "HIGH",
                })

    def _get_decorator_name(self, node: ast.AST) -> str:
        """Extract decorator name."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return node.func.id
            elif isinstance(node.func, ast.Attribute):
                return node.func.attr
        return "unknown"

    def _get_base_name(self, node: ast.AST) -> str:
        """Extract base class name."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return node.attr
        return "unknown"


# ── Dead Code Detection ──────────────────────────────────────────────────────

def analyze_file(filepath: str) -> Dict[str, Any]:
    """Analyze a single Python file for dead code."""
    content = read_file(filepath)
    if not content.strip():
        return {}

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {}

    analyzer = CodeAnalyzer(filepath, content)
    analyzer.visit(tree)

    # Check for unreachable code in functions
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            analyzer._check_unreachable_code(node.body)

    return {
        "functions": analyzer.functions,
        "classes": analyzer.classes,
        "imports": analyzer.imports,
        "references": analyzer.references,
        "dead_blocks": analyzer.dead_blocks,
        "decorators": dict(analyzer.decorators),
    }


def is_compat_function(name: str) -> bool:
    """Check if function name matches compatibility patterns."""
    for pattern in COMPAT_FUNCTION_PATTERNS:
        if re.match(pattern, name):
            return True
    return False


def detect_unused_imports(analysis: Dict, filepath: str) -> List[Dict]:
    """Detect unused imports in analyzed file."""
    findings = []

    for import_name, import_info in analysis.get("imports", {}).items():
        # Skip re-exports in __init__.py
        if "__init__" in filepath and import_info.get("asname"):
            continue

        # Check if referenced in code
        if import_name not in analysis.get("references", set()):
            findings.append({
                "type": "unused_import",
                "file": filepath,
                "lineno": import_info.get("lineno"),
                "name": import_name,
                "module": import_info.get("module", import_name),
                "confidence": "MEDIUM",
                "description": f"Import '{import_name}' is never used",
            })

    return findings


def detect_compat_functions(analysis: Dict, filepath: str) -> List[Dict]:
    """Detect compatibility functions."""
    findings = []

    for func_name, func_info in analysis.get("functions", {}).items():
        if is_compat_function(func_name):
            findings.append({
                "type": "compat_function",
                "file": filepath,
                "lineno": func_info.get("lineno"),
                "name": func_name,
                "confidence": "LOW",
                "description": f"Function '{func_name}' matches Py2 compatibility pattern",
            })

    return findings


def detect_test_dead_code(analysis: Dict, filepath: str) -> List[Dict]:
    """Detect dead test code."""
    findings = []

    if not is_test_file(filepath):
        return findings

    for func_name, func_info in analysis.get("functions", {}).items():
        decorators = func_info.get("decorators", [])
        for dec in decorators:
            if "skip" in dec.lower() and ("py3" in dec.lower() or "py2" in dec.lower()):
                findings.append({
                    "type": "dead_test_code",
                    "file": filepath,
                    "lineno": func_info.get("lineno"),
                    "name": func_name,
                    "decorator": dec,
                    "confidence": "HIGH",
                    "description": f"Test function '{func_name}' is skipped with decorator '{dec}'",
                })

    return findings


# ── Main Analysis ────────────────────────────────────────────────────────────

def analyze_codebase(
    codebase_path: str,
    target_version: str,
    exclude_patterns: List[str],
    modules: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Analyze entire codebase for dead code."""

    report = {
        "target_version": target_version,
        "codebase_path": codebase_path,
        "files_scanned": 0,
        "total_findings": 0,
        "summary": {
            "version_guard_dead_code": 0,
            "compat_functions": 0,
            "unused_imports": 0,
            "dead_test_code": 0,
            "confidence": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
        },
        "findings": [],
    }

    # Collect all Python files
    python_files = []
    for root, dirs, files in os.walk(codebase_path):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if not should_skip(os.path.join(root, d), exclude_patterns)]

        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                if not should_skip(filepath, exclude_patterns):
                    python_files.append(filepath)

    # Analyze each file
    all_analyses = {}
    for filepath in python_files:
        report["files_scanned"] += 1
        analysis = analyze_file(filepath)
        if analysis:
            all_analyses[filepath] = analysis

    # Detect dead code categories
    for filepath, analysis in all_analyses.items():
        # Version-guarded dead code
        for dead_block in analysis.get("dead_blocks", []):
            dead_block["file"] = filepath
            report["findings"].append(dead_block)
            report["summary"]["version_guard_dead_code"] += 1
            report["summary"]["confidence"][dead_block.get("confidence", "MEDIUM")] += 1
            report["total_findings"] += 1

        # Compatibility functions
        compat_findings = detect_compat_functions(analysis, filepath)
        for finding in compat_findings:
            report["findings"].append(finding)
            report["summary"]["compat_functions"] += 1
            report["summary"]["confidence"][finding.get("confidence", "MEDIUM")] += 1
            report["total_findings"] += 1

        # Unused imports
        unused_findings = detect_unused_imports(analysis, filepath)
        for finding in unused_findings:
            report["findings"].append(finding)
            report["summary"]["unused_imports"] += 1
            report["summary"]["confidence"][finding.get("confidence", "MEDIUM")] += 1
            report["total_findings"] += 1

        # Dead test code
        test_findings = detect_test_dead_code(analysis, filepath)
        for finding in test_findings:
            report["findings"].append(finding)
            report["summary"]["dead_test_code"] += 1
            report["summary"]["confidence"][finding.get("confidence", "MEDIUM")] += 1
            report["total_findings"] += 1

    return report


def extract_safe_removals(report: Dict) -> Dict[str, Any]:
    """Extract HIGH-confidence findings for safe removal."""
    safe_report = {
        "target_version": report.get("target_version"),
        "total_safe_removals": 0,
        "by_category": defaultdict(list),
        "findings": [],
    }

    for finding in report.get("findings", []):
        if finding.get("confidence") == "HIGH":
            safe_report["findings"].append(finding)
            category = finding.get("type", "unknown")
            safe_report["by_category"][category].append(finding)
            safe_report["total_safe_removals"] += 1

    safe_report["by_category"] = dict(safe_report["by_category"])
    return safe_report


# ── Main Entry Point ────────────────────────────────────────────────────────

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Dead Code Detector for Py2→Py3 migration"
    )
    parser.add_argument("codebase_path", help="Root directory of migrated codebase")
    parser.add_argument("--target-version", default="3.12",
                       help="Target Python 3.x version (default: 3.12)")
    parser.add_argument("--exclude", nargs="*",
                       default=["**/vendor/**", "**/.git/**", "**/__pycache__/**"],
                       help="Glob patterns to exclude")
    parser.add_argument("--output", default=".",
                       help="Output directory for reports")
    parser.add_argument("--coverage-data", default=None,
                       help="Path to .coverage file for cross-reference")
    parser.add_argument("--modules", nargs="*", default=None,
                       help="Specific modules to scan (default: all)")

    args = parser.parse_args()

    if not os.path.isdir(args.codebase_path):
        print(f"Error: codebase path not found: {args.codebase_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning codebase: {args.codebase_path}")
    print(f"Target version: {args.target_version}")

    # Run analysis
    report = analyze_codebase(
        args.codebase_path,
        args.target_version,
        args.exclude,
        args.modules,
    )

    # Save outputs
    os.makedirs(args.output, exist_ok=True)

    report_path = os.path.join(args.output, "dead-code-report.json")
    save_json(report, report_path)
    print(f"Wrote: {report_path}")

    # Extract and save safe removals
    safe_removals = extract_safe_removals(report)
    safe_path = os.path.join(args.output, "safe-to-remove.json")
    save_json(safe_removals, safe_path)
    print(f"Wrote: {safe_path}")

    # Extract medium/low confidence items for review
    flagged_for_review = {
        "target_version": report.get("target_version"),
        "total_flagged": 0,
        "findings": [],
    }

    for finding in report.get("findings", []):
        if finding.get("confidence") in ("MEDIUM", "LOW"):
            flagged_for_review["findings"].append(finding)
            flagged_for_review["total_flagged"] += 1

    if flagged_for_review["total_flagged"] > 0:
        flagged_path = os.path.join(args.output, "flagged-for-review.json")
        save_json(flagged_for_review, flagged_path)
        print(f"Wrote: {flagged_path}")

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files scanned: {report['files_scanned']}")
    print(f"Total findings: {report['total_findings']}")
    print()
    print("By type:")
    print(f"  Version-guarded dead code: {report['summary']['version_guard_dead_code']}")
    print(f"  Compat functions: {report['summary']['compat_functions']}")
    print(f"  Unused imports: {report['summary']['unused_imports']}")
    print(f"  Dead test code: {report['summary']['dead_test_code']}")
    print()
    print("By confidence:")
    for conf in ["HIGH", "MEDIUM", "LOW"]:
        count = report["summary"]["confidence"].get(conf, 0)
        if count > 0:
            print(f"  {conf}: {count}")
    print()
    print(f"Safe to remove (HIGH confidence): {safe_removals['total_safe_removals']}")

    sys.exit(0)


if __name__ == "__main__":
    main()
