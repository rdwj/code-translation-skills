#!/usr/bin/env python3
"""
Dynamic Pattern Resolver — Main Pattern Resolution Script

Scans Python 2 codebase for semantic patterns that changed in Python 3,
auto-fixes high-confidence patterns, and flags ambiguous ones for manual review.

Patterns handled:
  - Class transformations: __metaclass__, __nonzero__, __unicode__, __div__, __cmp__,
    __getslice__/__setslice__/__delslice__, __hash__
  - Iterators & views: map/filter/zip returning iterators, dict views
  - Builtins: reduce, apply, buffer, cmp, execfile, reload
  - Division: integer / vs // distinction
  - Comparisons: mixed-type comparisons

Usage:
    python3 resolve_patterns.py <conversion_unit_path> \
        --target-version 3.9 \
        --output <output_dir> \
        [--state-file <state.json>] \
        [--phase0-dir <phase0_output>] \
        [--conversion-plan <plan.json>] \
        [--dry-run] \
        [--auto-only]

Output:
    <output_dir>/fixed_files/ — Modified source files
    <output_dir>/dynamic-pattern-report.json — Full pattern analysis
    <output_dir>/manual-review-needed.json — Patterns needing human decision
"""

import ast
import json
import os
import sys
import re
import argparse
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple, Set
from datetime import datetime


# ── Pattern Definitions ──────────────────────────────────────────────────────

PATTERN_CATEGORIES = {
    "metaclass": {
        "description": "__metaclass__ attribute",
        "auto_fixable": True,
        "confidence": "high",
    },
    "nonzero": {
        "description": "__nonzero__ → __bool__",
        "auto_fixable": True,
        "confidence": "high",
    },
    "unicode": {
        "description": "__unicode__ → __str__",
        "auto_fixable": True,
        "confidence": "medium",
    },
    "div": {
        "description": "__div__ → __truediv__/__floordiv__",
        "auto_fixable": "partial",
        "confidence": "high",
    },
    "getslice": {
        "description": "__getslice__/__setslice__/__delslice__ → __getitem__ with slice",
        "auto_fixable": True,
        "confidence": "high",
    },
    "cmp": {
        "description": "__cmp__ → rich comparison methods",
        "auto_fixable": "conditional",
        "confidence": "medium",
    },
    "hash": {
        "description": "__hash__ implicit → explicit when __eq__ defined",
        "auto_fixable": "conditional",
        "confidence": "high",
    },
    "map_filter_zip": {
        "description": "map/filter/zip returning iterators",
        "auto_fixable": "conditional",
        "confidence": "medium",
    },
    "dict_views": {
        "description": "dict.keys()/values()/items() returning views",
        "auto_fixable": "conditional",
        "confidence": "medium",
    },
    "sorted_cmp": {
        "description": "sorted(cmp=...) → sorted(key=cmp_to_key(...))",
        "auto_fixable": True,
        "confidence": "high",
    },
    "reduce": {
        "description": "reduce() → functools.reduce()",
        "auto_fixable": True,
        "confidence": "high",
    },
    "apply": {
        "description": "apply(f, args, kwargs) → f(*args, **kwargs)",
        "auto_fixable": True,
        "confidence": "high",
    },
    "buffer": {
        "description": "buffer() → memoryview()",
        "auto_fixable": "conditional",
        "confidence": "medium",
    },
    "cmp_builtin": {
        "description": "cmp(a, b) → (a > b) - (a < b)",
        "auto_fixable": True,
        "confidence": "high",
    },
    "execfile": {
        "description": "execfile(f) → exec(open(f).read())",
        "auto_fixable": True,
        "confidence": "high",
    },
    "reload": {
        "description": "reload(m) → importlib.reload(m)",
        "auto_fixable": True,
        "confidence": "high",
    },
    "division": {
        "description": "/ on integers → needs review or //",
        "auto_fixable": "conditional",
        "confidence": "low",
    },
}


# ── AST Visitor for Pattern Detection ────────────────────────────────────────

class PatternDetector(ast.NodeVisitor):
    """Traverse AST and detect all dynamic patterns."""

    def __init__(self, source_lines: List[str], filename: str):
        self.source_lines = source_lines
        self.filename = filename
        self.patterns = []
        self.imports = set()
        self.has_future_division = False
        self.class_stack = []  # Track class context for method detection
        self.function_stack = []  # Track function context

    def get_source_context(self, lineno: int, context_lines: int = 2) -> str:
        """Get source context around a line."""
        start = max(0, lineno - context_lines - 1)
        end = min(len(self.source_lines), lineno + context_lines)
        lines = self.source_lines[start:end]
        marker = ">>> " if start + context_lines == lineno - 1 else "    "
        return "\n".join(
            f"{marker}{self.source_lines[i]}" if i == lineno - 1 else f"    {self.source_lines[i]}"
            for i in range(start, end)
        )

    def visit_Module(self, node: ast.Module) -> None:
        """Check module-level imports and future statements."""
        for item in node.body:
            if isinstance(item, ast.ImportFrom):
                if item.module == "__future__":
                    for alias in item.names:
                        if alias.name == "division":
                            self.has_future_division = True
            elif isinstance(item, ast.Import):
                for alias in item.names:
                    self.imports.add(alias.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit class definitions."""
        self.class_stack.append(node)

        # Check for __metaclass__ attribute
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__metaclass__":
                        self.patterns.append({
                            "type": "metaclass",
                            "lineno": item.lineno,
                            "class_name": node.name,
                            "context": self.get_source_context(item.lineno),
                        })

        # Check for dunder methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name == "__nonzero__":
                    self.patterns.append({
                        "type": "nonzero",
                        "lineno": item.lineno,
                        "class_name": node.name,
                        "method_name": "__nonzero__",
                        "context": self.get_source_context(item.lineno),
                    })
                elif item.name == "__unicode__":
                    self.patterns.append({
                        "type": "unicode",
                        "lineno": item.lineno,
                        "class_name": node.name,
                        "method_name": "__unicode__",
                        "has_str": any(
                            isinstance(sub, ast.FunctionDef) and sub.name == "__str__"
                            for sub in node.body
                        ),
                        "context": self.get_source_context(item.lineno),
                    })
                elif item.name == "__div__":
                    self.patterns.append({
                        "type": "div",
                        "lineno": item.lineno,
                        "class_name": node.name,
                        "context": self.get_source_context(item.lineno),
                    })
                elif item.name in ("__getslice__", "__setslice__", "__delslice__"):
                    self.patterns.append({
                        "type": "getslice",
                        "lineno": item.lineno,
                        "class_name": node.name,
                        "slice_type": item.name,
                        "context": self.get_source_context(item.lineno),
                    })
                elif item.name == "__cmp__":
                    self.patterns.append({
                        "type": "cmp",
                        "lineno": item.lineno,
                        "class_name": node.name,
                        "context": self.get_source_context(item.lineno),
                    })
                elif item.name == "__eq__":
                    # Check if __hash__ is defined
                    has_hash = any(
                        isinstance(sub, ast.FunctionDef) and sub.name == "__hash__"
                        for sub in node.body
                    )
                    if not has_hash:
                        self.patterns.append({
                            "type": "hash",
                            "lineno": item.lineno,
                            "class_name": node.name,
                            "eq_defined": True,
                            "hash_defined": False,
                            "context": self.get_source_context(item.lineno),
                        })

        self.generic_visit(node)
        self.class_stack.pop()

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function calls to detect builtins and method calls."""
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        # Builtin function patterns
        if func_name == "map" or func_name == "filter" or func_name == "zip":
            self.patterns.append({
                "type": "map_filter_zip",
                "lineno": node.lineno,
                "function": func_name,
                "context": self.get_source_context(node.lineno),
                "confidence": "conditional",
            })

        elif func_name == "sorted":
            # Check for cmp= parameter
            for keyword in node.keywords:
                if keyword.arg == "cmp":
                    self.patterns.append({
                        "type": "sorted_cmp",
                        "lineno": node.lineno,
                        "context": self.get_source_context(node.lineno),
                    })

        elif func_name == "reduce":
            self.patterns.append({
                "type": "reduce",
                "lineno": node.lineno,
                "has_import": "reduce" in self.imports or "functools" in self.imports,
                "context": self.get_source_context(node.lineno),
            })

        elif func_name == "apply":
            self.patterns.append({
                "type": "apply",
                "lineno": node.lineno,
                "context": self.get_source_context(node.lineno),
            })

        elif func_name == "buffer":
            self.patterns.append({
                "type": "buffer",
                "lineno": node.lineno,
                "context": self.get_source_context(node.lineno),
            })

        elif func_name == "cmp" and len(node.args) == 2:
            self.patterns.append({
                "type": "cmp_builtin",
                "lineno": node.lineno,
                "context": self.get_source_context(node.lineno),
            })

        elif func_name == "execfile":
            self.patterns.append({
                "type": "execfile",
                "lineno": node.lineno,
                "context": self.get_source_context(node.lineno),
            })

        elif func_name == "reload":
            self.patterns.append({
                "type": "reload",
                "lineno": node.lineno,
                "has_import": "importlib" in self.imports,
                "context": self.get_source_context(node.lineno),
            })

        # Dict view methods
        if isinstance(node.func, ast.Attribute):
            if node.func.attr in ("keys", "values", "items"):
                self.patterns.append({
                    "type": "dict_views",
                    "lineno": node.lineno,
                    "method": node.func.attr,
                    "context": self.get_source_context(node.lineno),
                    "confidence": "conditional",
                })

        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        """Visit binary operations to detect division issues."""
        if isinstance(node.op, ast.Div):
            # Check if operands are likely integers
            left_is_int = self._is_likely_int(node.left)
            right_is_int = self._is_likely_int(node.right)

            if left_is_int and right_is_int:
                self.patterns.append({
                    "type": "division",
                    "lineno": node.lineno,
                    "left_type": "literal_int" if isinstance(node.left, ast.Constant) else "inferred_int",
                    "right_type": "literal_int" if isinstance(node.right, ast.Constant) else "inferred_int",
                    "has_future_division": self.has_future_division,
                    "context": self.get_source_context(node.lineno),
                })

        self.generic_visit(node)

    def _is_likely_int(self, node: ast.expr) -> bool:
        """Heuristic: is this expression likely an integer?"""
        if isinstance(node, ast.Constant):
            return isinstance(node.value, int) and not isinstance(node.value, bool)
        if isinstance(node, ast.Num):  # Python 3.7 compatibility
            return isinstance(node.n, int) and not isinstance(node.n, bool)
        return False


# ── Pattern Resolution Strategies ────────────────────────────────────────────

class PatternResolver:
    """Base class for pattern-specific resolvers."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        """Check if this resolver handles the pattern type."""
        return False

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Return (modified_source, resolution_details)."""
        return source, {"action": "skipped", "reason": "not implemented"}

    def is_auto_fixable(self, pattern: Dict[str, Any]) -> bool:
        """Determine if pattern can be auto-fixed."""
        return PATTERN_CATEGORIES.get(pattern["type"], {}).get("auto_fixable", False)


class MetaclassResolver(PatternResolver):
    """Resolve __metaclass__ attribute → metaclass= keyword."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        return pattern["type"] == "metaclass"

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Extract metaclass name and rewrite class definition."""
        lines = source.split("\n")
        lineno = pattern["lineno"]

        # Find the metaclass assignment
        metaclass_match = None
        metaclass_name = None
        for i in range(lineno - 1, min(lineno + 5, len(lines))):
            match = re.search(r"__metaclass__\s*=\s*(\w+)", lines[i])
            if match:
                metaclass_name = match.group(1)
                metaclass_match = i
                break

        if not metaclass_name:
            return source, {"action": "failed", "reason": "could not extract metaclass name"}

        # Find the class definition line
        class_lineno = None
        for i in range(lineno - 1, -1, -1):
            if re.search(r"^class\s+\w+", lines[i]):
                class_lineno = i
                break

        if class_lineno is None:
            return source, {"action": "failed", "reason": "could not find class definition"}

        # Rewrite class line
        class_line = lines[class_lineno]
        new_class_line = re.sub(
            r"(class\s+\w+\([^)]*)\)",
            rf"\1, metaclass={metaclass_name})",
            class_line,
        )
        if new_class_line == class_line:
            # No base class
            new_class_line = re.sub(
                r"(class\s+\w+)\s*:",
                rf"\1(metaclass={metaclass_name}):",
                class_line,
            )

        lines[class_lineno] = new_class_line

        # Remove __metaclass__ assignment
        if metaclass_match is not None:
            lines[metaclass_match] = ""

        modified = "\n".join(lines)
        return modified, {
            "action": "fixed",
            "metaclass": metaclass_name,
            "class": pattern["class_name"],
        }


class NonzeroResolver(PatternResolver):
    """Resolve __nonzero__ → __bool__."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        return pattern["type"] == "nonzero"

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Rename __nonzero__ to __bool__."""
        lines = source.split("\n")
        lineno = pattern["lineno"]

        # Simple rename
        if lineno - 1 < len(lines):
            lines[lineno - 1] = lines[lineno - 1].replace("__nonzero__", "__bool__")

        modified = "\n".join(lines)
        return modified, {
            "action": "fixed",
            "from": "__nonzero__",
            "to": "__bool__",
            "class": pattern["class_name"],
        }


class UnicodeResolver(PatternResolver):
    """Resolve __unicode__ → __str__ and __str__ → __bytes__."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        return pattern["type"] == "unicode"

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Rename __unicode__ to __str__; old __str__ → __bytes__ if present."""
        lines = source.split("\n")
        lineno = pattern["lineno"]

        # Rename __unicode__ to __str__
        if lineno - 1 < len(lines):
            lines[lineno - 1] = lines[lineno - 1].replace("__unicode__", "__str__")

        # If original __str__ exists, we'd need to rename it to __bytes__
        # This is complex without full AST rewriting; flag for review
        return "\n".join(lines), {
            "action": "partial_fix",
            "note": "Renamed __unicode__ to __str__. "
            "Check if original __str__ should be renamed to __bytes__.",
            "class": pattern["class_name"],
        }


class DivResolver(PatternResolver):
    """Resolve __div__ → __truediv__ (and suggest __floordiv__)."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        return pattern["type"] == "div"

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Rename __div__ to __truediv__."""
        lines = source.split("\n")
        lineno = pattern["lineno"]

        if lineno - 1 < len(lines):
            lines[lineno - 1] = lines[lineno - 1].replace("__div__", "__truediv__")

        return "\n".join(lines), {
            "action": "partial_fix",
            "note": "Renamed __div__ to __truediv__. "
            "Consider adding __floordiv__ for // operator if needed.",
            "class": pattern["class_name"],
        }


class ReduceResolver(PatternResolver):
    """Resolve reduce() → functools.reduce()."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        return pattern["type"] == "reduce"

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Add functools import if missing."""
        has_import = pattern.get("has_import", False)

        if has_import:
            return source, {"action": "already_imported", "module": "functools"}

        # Add import at top of file
        lines = source.split("\n")

        # Find insertion point (after __future__ and before other imports)
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("from __future__"):
                insert_at = i + 1
            elif line.startswith("import ") or line.startswith("from "):
                if insert_at == 0:
                    insert_at = i
                break

        lines.insert(insert_at, "from functools import reduce")
        return "\n".join(lines), {
            "action": "fixed",
            "added_import": "from functools import reduce",
        }


class ApplyResolver(PatternResolver):
    """Resolve apply() → direct function call with *args/**kwargs."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        return pattern["type"] == "apply"

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Flag for manual review (complex transformation)."""
        return source, {
            "action": "needs_review",
            "reason": "apply() requires unpacking analysis; suggest manual rewrite to func(*args, **kwargs)",
        }


class CmpBuiltinResolver(PatternResolver):
    """Resolve cmp(a, b) → (a > b) - (a < b)."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        return pattern["type"] == "cmp_builtin"

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Replace cmp(a, b) with comparison expression."""
        lines = source.split("\n")
        lineno = pattern["lineno"]

        if lineno - 1 < len(lines):
            # Simple replacement using regex
            lines[lineno - 1] = re.sub(
                r"cmp\(([^,]+),\s*([^)]+)\)",
                r"((\1) > (\2)) - ((\1) < (\2))",
                lines[lineno - 1],
            )

        return "\n".join(lines), {
            "action": "fixed",
            "transformation": "cmp(a, b) → (a > b) - (a < b)",
        }


class ExecfileResolver(PatternResolver):
    """Resolve execfile() → exec(open().read())."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        return pattern["type"] == "execfile"

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Replace execfile(f) with exec(open(f).read())."""
        lines = source.split("\n")
        lineno = pattern["lineno"]

        if lineno - 1 < len(lines):
            lines[lineno - 1] = re.sub(
                r"execfile\(([^)]+)\)",
                r"exec(open(\1).read())",
                lines[lineno - 1],
            )

        return "\n".join(lines), {
            "action": "fixed",
            "transformation": "execfile(f) → exec(open(f).read())",
        }


class ReloadResolver(PatternResolver):
    """Resolve reload() → importlib.reload()."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        return pattern["type"] == "reload"

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Add importlib import if missing."""
        has_import = pattern.get("has_import", False)

        if has_import:
            return source, {"action": "already_imported", "module": "importlib"}

        # Add import at top of file
        lines = source.split("\n")

        # Find insertion point
        insert_at = 0
        for i, line in enumerate(lines):
            if line.startswith("from __future__"):
                insert_at = i + 1
            elif line.startswith("import ") or line.startswith("from "):
                if insert_at == 0:
                    insert_at = i
                break

        lines.insert(insert_at, "from importlib import reload")
        return "\n".join(lines), {
            "action": "fixed",
            "added_import": "from importlib import reload",
        }


class SortedCmpResolver(PatternResolver):
    """Resolve sorted(cmp=...) → sorted(key=cmp_to_key(...))."""

    def can_handle(self, pattern: Dict[str, Any]) -> bool:
        return pattern["type"] == "sorted_cmp"

    def resolve(self, source: str, pattern: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """Replace sorted(cmp=...) with sorted(key=cmp_to_key(...))."""
        lines = source.split("\n")
        lineno = pattern["lineno"]

        if lineno - 1 < len(lines):
            # Replace cmp= with key=cmp_to_key(...)
            lines[lineno - 1] = re.sub(
                r"cmp\s*=\s*(\w+)",
                r"key=functools.cmp_to_key(\1)",
                lines[lineno - 1],
            )

        # Ensure functools is imported
        modified = "\n".join(lines)
        if "from functools import cmp_to_key" not in modified:
            lines_list = modified.split("\n")
            insert_at = 0
            for i, line in enumerate(lines_list):
                if line.startswith("from __future__"):
                    insert_at = i + 1
                elif line.startswith("import ") or line.startswith("from "):
                    if insert_at == 0:
                        insert_at = i
                    break
            lines_list.insert(insert_at, "from functools import cmp_to_key")
            modified = "\n".join(lines_list)

        return modified, {
            "action": "fixed",
            "transformation": "sorted(cmp=f) → sorted(key=functools.cmp_to_key(f))",
        }


# ── Main Script ──────────────────────────────────────────────────────────────

class DynamicPatternResolver:
    """Main resolver orchestrator."""

    def __init__(self, output_dir: str, target_version: str = "3.9", dry_run: bool = False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.target_version = target_version
        self.dry_run = dry_run
        self.resolvers = [
            MetaclassResolver(),
            NonzeroResolver(),
            UnicodeResolver(),
            DivResolver(),
            ReduceResolver(),
            ApplyResolver(),
            CmpBuiltinResolver(),
            ExecfileResolver(),
            ReloadResolver(),
            SortedCmpResolver(),
        ]
        self.report = {
            "timestamp": datetime.now().isoformat(),
            "target_version": target_version,
            "files_analyzed": 0,
            "patterns_found": defaultdict(int),
            "patterns_auto_fixed": defaultdict(int),
            "patterns_needing_review": defaultdict(int),
            "files": {},
        }
        self.manual_review = []

    def process_file(self, filepath: str) -> None:
        """Analyze and resolve patterns in a single file."""
        filepath = Path(filepath)
        if not filepath.suffix == ".py":
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                source = f.read()
        except Exception as e:
            self.report["files"][str(filepath)] = {
                "status": "error",
                "error": str(e),
            }
            return

        source_lines = source.split("\n")

        # Parse AST
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            self.report["files"][str(filepath)] = {
                "status": "parse_error",
                "error": str(e),
            }
            return

        # Detect patterns
        detector = PatternDetector(source_lines, str(filepath))
        detector.visit(tree)

        if not detector.patterns:
            self.report["files"][str(filepath)] = {
                "status": "ok",
                "patterns_found": 0,
            }
            return

        # Resolve patterns
        modified_source = source
        file_patterns = defaultdict(list)
        auto_fixed_count = 0

        for pattern in detector.patterns:
            pattern_type = pattern["type"]
            self.report["patterns_found"][pattern_type] += 1

            # Find resolver
            resolver = next(
                (r for r in self.resolvers if r.can_handle(pattern)), None
            )

            if resolver is None:
                file_patterns[pattern_type].append({
                    "pattern": pattern,
                    "action": "no_resolver",
                })
                self.report["patterns_needing_review"][pattern_type] += 1
                self.manual_review.append({
                    "file": str(filepath),
                    "line": pattern.get("lineno"),
                    "type": pattern_type,
                    "pattern": pattern,
                    "reason": "No resolver available",
                })
                continue

            if not resolver.is_auto_fixable(pattern):
                file_patterns[pattern_type].append({
                    "pattern": pattern,
                    "action": "needs_review",
                    "reason": "Not auto-fixable",
                })
                self.report["patterns_needing_review"][pattern_type] += 1
                self.manual_review.append({
                    "file": str(filepath),
                    "line": pattern.get("lineno"),
                    "type": pattern_type,
                    "pattern": pattern,
                    "reason": "Requires manual review or semantic analysis",
                })
                continue

            # Apply resolver
            try:
                modified_source, details = resolver.resolve(modified_source, pattern)
                file_patterns[pattern_type].append({
                    "pattern": pattern,
                    "resolution": details,
                })
                self.report["patterns_auto_fixed"][pattern_type] += 1
                auto_fixed_count += 1
            except Exception as e:
                file_patterns[pattern_type].append({
                    "pattern": pattern,
                    "action": "resolution_failed",
                    "error": str(e),
                })
                self.report["patterns_needing_review"][pattern_type] += 1

        # Write modified file
        output_filepath = self.output_dir / filepath.relative_to("/").as_posix()
        output_filepath.parent.mkdir(parents=True, exist_ok=True)

        if not self.dry_run:
            with open(output_filepath, "w", encoding="utf-8") as f:
                f.write(modified_source)

        self.report["files"][str(filepath)] = {
            "status": "processed",
            "patterns_found": len(detector.patterns),
            "patterns_fixed": auto_fixed_count,
            "patterns_by_type": dict(file_patterns),
        }
        self.report["files_analyzed"] += 1

    def process_directory(self, dirpath: str) -> None:
        """Recursively process all Python files in directory."""
        dirpath = Path(dirpath)
        for py_file in dirpath.rglob("*.py"):
            self.process_file(str(py_file))

    def generate_report(self) -> None:
        """Write JSON reports."""
        # Dynamic pattern report
        report_file = self.output_dir / "dynamic-pattern-report.json"
        with open(report_file, "w") as f:
            json.dump(self.report, f, indent=2, default=str)

        # Manual review report
        if self.manual_review:
            review_file = self.output_dir / "manual-review-needed.json"
            with open(review_file, "w") as f:
                json.dump(self.manual_review, f, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(
        description="Resolve dynamic Python 2→3 patterns in source code"
    )
    parser.add_argument("conversion_unit_path", help="Path to file or directory")
    parser.add_argument("--target-version", default="3.9", help="Python 3 target version")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--state-file", help="State file to update")
    parser.add_argument("--phase0-dir", help="Phase 0 discovery output directory")
    parser.add_argument("--conversion-plan", help="Conversion plan JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be changed")
    parser.add_argument("--auto-only", action="store_true", help="Only auto-fix, skip ambiguous")

    args = parser.parse_args()

    resolver = DynamicPatternResolver(args.output, args.target_version, args.dry_run)

    # Process input
    input_path = Path(args.conversion_unit_path)
    if input_path.is_file():
        resolver.process_file(str(input_path))
    elif input_path.is_dir():
        resolver.process_directory(str(input_path))
    else:
        print(f"Error: {args.conversion_unit_path} not found")
        sys.exit(1)

    # Generate reports
    resolver.generate_report()

    # Update state file if provided
    if args.state_file:
        state = {}
        if Path(args.state_file).exists():
            with open(args.state_file) as f:
                state = json.load(f)

        state["dynamic_pattern_resolver"] = {
            "timestamp": datetime.now().isoformat(),
            "patterns_found": dict(resolver.report["patterns_found"]),
            "patterns_fixed": dict(resolver.report["patterns_auto_fixed"]),
        }

        with open(args.state_file, "w") as f:
            json.dump(state, f, indent=2)

    print(f"Analysis complete. Output: {args.output}")
    print(f"Files analyzed: {resolver.report['files_analyzed']}")
    print(f"Patterns found: {sum(resolver.report['patterns_found'].values())}")
    print(f"Auto-fixed: {sum(resolver.report['patterns_auto_fixed'].values())}")
    print(f"Needing review: {sum(resolver.report['patterns_needing_review'].values())}")


if __name__ == "__main__":
    main()
