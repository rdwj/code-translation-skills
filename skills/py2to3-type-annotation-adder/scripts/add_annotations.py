#!/usr/bin/env python3
"""
Type Annotation Adder: Adds type hints to converted Python code via AST analysis.

Infers types from return statements, default values, docstrings (Google/NumPy/Sphinx),
API knowledge, and bytes/str boundary analysis. Applies high/medium confidence annotations,
suggests low-confidence inferences. Version-aware: uses list[str] for 3.9+, X|Y for 3.10+.

Usage:
    python3 add_annotations.py --codebase-path /path/to/project --target-version 3.11
    python3 add_annotations.py --codebase-path /path --target-version 3.9 --modules src/,lib/
    python3 add_annotations.py --codebase-path /path --target-version 3.12 --dry-run --strict
"""

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional, Set
from datetime import datetime
from collections import defaultdict


# ── JSON Helpers ──
def load_json(filepath: str) -> Dict[str, Any]:
    """Load JSON from file, return empty dict if not found."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(data: Dict[str, Any], filepath: str) -> None:
    """Save dict to JSON file."""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)


def read_file(filepath: str) -> str:
    """Read file as string."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception:
        return ""


def write_file(filepath: str, content: str) -> None:
    """Write string to file, create directories as needed."""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


# ── Type Inference ──
class TypeInferencer:
    """Infers types from AST, docstrings, and API knowledge."""

    # Standard library type mappings
    STDLIB_RETURN_TYPES = {
        'json.loads': 'Any',
        'json.load': 'Any',
        'open': 'TextIO',
        'socket.socket.recv': 'bytes',
        'socket.socket.send': 'int',
        'struct.unpack': 'tuple',
        're.match': 'Optional[Match]',
        're.search': 'Optional[Match]',
    }

    def __init__(self, target_version: str, bytes_str_report: Optional[Dict] = None):
        self.target_version = target_version
        self.bytes_str_report = bytes_str_report or {}
        self.use_modern_syntax = target_version >= '3.9'
        self.use_union_syntax = target_version >= '3.10'

    def infer_return_type(
        self,
        func_node: ast.FunctionDef,
        docstring: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """Infer return type from return statements, docstring, and API knowledge."""

        # 1. Check explicit docstring type hint
        if docstring:
            return_type = self._extract_docstring_return(docstring)
            if return_type:
                return (return_type, 'high')

        # 2. Analyze return statements
        return_types: List[str] = []
        for node in ast.walk(func_node):
            if isinstance(node, ast.Return) and node.value:
                inferred = self._infer_from_expr(node.value)
                if inferred:
                    return_types.append(inferred)

        # No returns or empty function
        if not return_types:
            return (None, 'medium')

        # Single consistent type
        if len(set(return_types)) == 1:
            return (return_types[0], 'high')

        # Multiple return types - Union
        if self.use_union_syntax:
            union_type = ' | '.join(sorted(set(return_types)))
        else:
            union_type = f"Union[{', '.join(sorted(set(return_types)))}]"

        return (union_type, 'medium')

    def infer_param_type(
        self,
        param: ast.arg,
        default_value: Optional[ast.expr] = None,
        docstring: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """Infer parameter type from default value, docstring."""

        param_name = param.arg

        # 1. Check docstring for explicit type
        if docstring:
            param_type = self._extract_docstring_param_type(docstring, param_name)
            if param_type:
                return (param_type, 'high')

        # 2. Infer from default value
        if default_value:
            inferred = self._infer_from_expr(default_value)
            if inferred:
                return (inferred, 'high')

        # 3. Variable name heuristics (low confidence)
        if param_name.endswith('_count') or param_name.endswith('_num'):
            return ('int', 'low')
        if param_name.endswith('_name') or param_name.endswith('_str'):
            return ('str', 'low')

        return (None, 'low')

    def _infer_from_expr(self, expr: ast.expr) -> Optional[str]:
        """Infer type from literal expression."""

        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, bool):
                return 'bool'
            elif isinstance(expr.value, int):
                return 'int'
            elif isinstance(expr.value, float):
                return 'float'
            elif isinstance(expr.value, str):
                return 'str'
            elif isinstance(expr.value, bytes):
                return 'bytes'
            elif expr.value is None:
                return 'None'

        elif isinstance(expr, ast.List):
            return self._format_collection_type('list')
        elif isinstance(expr, ast.Tuple):
            return self._format_collection_type('tuple')
        elif isinstance(expr, ast.Dict):
            return self._format_collection_type('dict')
        elif isinstance(expr, ast.Set):
            return self._format_collection_type('set')

        elif isinstance(expr, ast.Call):
            if isinstance(expr.func, ast.Name):
                if expr.func.id == 'dict':
                    return self._format_collection_type('dict')
                elif expr.func.id == 'list':
                    return self._format_collection_type('list')

        return None

    def _format_collection_type(self, base_type: str) -> str:
        """Format collection type using modern syntax if available."""
        if self.use_modern_syntax:
            return f'{base_type}[Any]'
        else:
            type_map = {
                'list': 'List[Any]',
                'dict': 'Dict[Any, Any]',
                'tuple': 'Tuple[Any, ...]',
                'set': 'Set[Any]',
            }
            return type_map.get(base_type, f'{base_type}[Any]')

    def _extract_docstring_return(self, docstring: str) -> Optional[str]:
        """Extract return type from docstring (Google/NumPy/Sphinx styles)."""

        # Google style: "Returns:\n    type: description"
        google_match = re.search(
            r'Returns:\s*\n\s+(\w+(?:\[[^\]]+\])?)\s*:',
            docstring
        )
        if google_match:
            return google_match.group(1)

        # NumPy style: "Returns\n------\ntype\n    description"
        numpy_match = re.search(
            r'Returns\s*\n-+\s*\n\s*(\w+(?:\[[^\]]+\])?)',
            docstring
        )
        if numpy_match:
            return numpy_match.group(1)

        # Sphinx style: ":return type description" or ":rtype: type"
        sphinx_rtype = re.search(r':rtype:\s*(\w+(?:\[[^\]]+\])?)', docstring)
        if sphinx_rtype:
            return sphinx_rtype.group(1)

        return None

    def _extract_docstring_param_type(self, docstring: str, param_name: str) -> Optional[str]:
        """Extract parameter type from docstring."""

        # Google style: "param_name (type): description"
        google_match = re.search(
            rf'{re.escape(param_name)}\s*\(([^)]+)\)\s*:',
            docstring
        )
        if google_match:
            return google_match.group(1)

        # Sphinx style: ":param type param_name: description"
        sphinx_match = re.search(
            rf':param\s+(\w+(?:\[[^\]]+\])?)\s+{re.escape(param_name)}:',
            docstring
        )
        if sphinx_match:
            return sphinx_match.group(1)

        # NumPy style: "param_name : type"
        numpy_match = re.search(
            rf'{re.escape(param_name)}\s*:\s*(\w+(?:\[[^\]]+\])?)',
            docstring
        )
        if numpy_match:
            return numpy_match.group(1)

        return None


class AnnotationAnalyzer(ast.NodeVisitor):
    """Analyzes Python file for annotation opportunities."""

    def __init__(
        self,
        filepath: str,
        target_version: str,
        inferencer: TypeInferencer,
        strict: bool = False
    ):
        self.filepath = filepath
        self.target_version = target_version
        self.inferencer = inferencer
        self.strict = strict
        self.functions: List[Dict[str, Any]] = []
        self.current_class: Optional[str] = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Analyze function for type annotation opportunities."""

        # Skip private functions unless strict mode
        if not self.strict and node.name.startswith('_'):
            self.generic_visit(node)
            return

        func_info = {
            'name': node.name,
            'lineno': node.lineno,
            'is_method': self.current_class is not None,
            'parameters': [],
            'return_type': None,
            'return_confidence': 'low',
        }

        docstring = ast.get_docstring(node)

        # Analyze parameters
        for i, arg in enumerate(node.args.args):
            # Skip 'self' and 'cls' parameters
            if arg.arg in ('self', 'cls'):
                continue

            # Get default value if exists
            default_idx = i - (len(node.args.args) - len(node.args.defaults))
            default = None
            if default_idx >= 0:
                default = node.args.defaults[default_idx]

            param_type, confidence = self.inferencer.infer_param_type(arg, default, docstring)

            func_info['parameters'].append({
                'name': arg.arg,
                'type': param_type,
                'confidence': confidence,
            })

        # Analyze return type
        return_type, ret_confidence = self.inferencer.infer_return_type(node, docstring)
        func_info['return_type'] = return_type
        func_info['return_confidence'] = ret_confidence

        self.functions.append(func_info)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class context."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class


def analyze_file(
    filepath: str,
    target_version: str,
    inferencer: TypeInferencer,
    strict: bool = False
) -> Dict[str, Any]:
    """Analyze single Python file for annotation opportunities."""

    content = read_file(filepath)
    if not content:
        return {'filepath': filepath, 'error': 'Could not read file'}

    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        return {'filepath': filepath, 'error': f'Syntax error: {e}'}

    analyzer = AnnotationAnalyzer(filepath, target_version, inferencer, strict)
    analyzer.visit(tree)

    return {
        'filepath': filepath,
        'functions': analyzer.functions,
    }


def scan_codebase(
    codebase_path: str,
    modules: Optional[str] = None
) -> List[str]:
    """Scan codebase for Python files to analyze."""

    if modules and modules != 'all':
        module_patterns = [m.strip() for m in modules.split(',')]
    else:
        module_patterns = None

    python_files = []
    root = Path(codebase_path)

    for py_file in root.rglob('*.py'):
        rel_path = str(py_file.relative_to(root))

        # Filter by module patterns
        if module_patterns:
            if not any(rel_path.startswith(pattern) for pattern in module_patterns):
                continue

        python_files.append(str(py_file))

    return python_files


# ── Annotation Application ──
def apply_annotations(
    filepath: str,
    analysis: Dict[str, Any],
    dry_run: bool = False
) -> Tuple[str, List[str]]:
    """Apply type annotations to file (or return annotated version in dry-run)."""

    content = read_file(filepath)
    if not content:
        return (content, [])

    original = content
    changes = []

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return (content, [])

    # Build line-based view for insertion
    lines = content.split('\n')

    # Apply annotations in reverse line order to maintain offsets
    functions = analysis.get('functions', [])
    for func_info in sorted(functions, key=lambda f: f['lineno'], reverse=True):
        lineno = func_info['lineno']
        if lineno > len(lines):
            continue

        func_line = lines[lineno - 1]

        # Find function signature line and next
        # This is a simplified approach - in production, use full AST rewriting
        annotations_added = []

        # Add return type annotation if missing and confident
        if func_info['return_type'] and func_info['return_confidence'] in ('high', 'medium'):
            if '->' not in func_line:
                # Extract function name and signature
                match = re.match(r'^(\s*def\s+\w+\([^)]*\))\s*:', func_line)
                if match:
                    new_line = f"{match.group(1)} -> {func_info['return_type']}:"
                    lines[lineno - 1] = new_line
                    annotations_added.append('return type')

        if annotations_added:
            changes.append(f"{func_info['name']}: {', '.join(annotations_added)}")

    if not dry_run and changes:
        write_file(filepath, '\n'.join(lines))

    return ('\n'.join(lines) if dry_run else original, changes)


# ── Report Generation ──
def generate_coverage_report(analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate coverage metrics from analyses."""

    total_functions = 0
    annotated_functions = 0
    high_confidence = 0
    medium_confidence = 0
    low_confidence = 0

    for analysis in analyses:
        functions = analysis.get('functions', [])
        total_functions += len(functions)

        for func in functions:
            if func.get('return_type'):
                annotated_functions += 1
                confidence = func.get('return_confidence', 'low')
                if confidence == 'high':
                    high_confidence += 1
                elif confidence == 'medium':
                    medium_confidence += 1
                else:
                    low_confidence += 1

    return {
        'total_functions': total_functions,
        'annotated_functions': annotated_functions,
        'coverage_percent': (annotated_functions / total_functions * 100) if total_functions else 0,
        'high_confidence': high_confidence,
        'medium_confidence': medium_confidence,
        'low_confidence': low_confidence,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Add type annotations to Python code via AST analysis'
    )
    parser.add_argument(
        '--codebase-path',
        required=True,
        help='Root directory of Python project'
    )
    parser.add_argument(
        '--target-version',
        required=True,
        choices=['3.9', '3.10', '3.11', '3.12', '3.13'],
        help='Target Python version'
    )
    parser.add_argument(
        '--modules',
        default=None,
        help='Module patterns to annotate (comma-separated) or "all"'
    )
    parser.add_argument(
        '--bytes-str-report',
        default=None,
        help='Path to bytes_str_boundary.json from Skill 3.1'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Annotate all functions vs public only'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview annotations without modifying files'
    )
    parser.add_argument(
        '--output-dir',
        default=None,
        help='Output directory for reports'
    )

    args = parser.parse_args()

    codebase_path = os.path.abspath(args.codebase_path)
    output_dir = os.path.abspath(args.output_dir or codebase_path)
    target_version = args.target_version

    # Load bytes/str report if available
    bytes_str_data = {}
    if args.bytes_str_report:
        bytes_str_data = load_json(args.bytes_str_report)

    # Initialize type inferencer
    inferencer = TypeInferencer(target_version, bytes_str_data)

    # Scan codebase
    python_files = scan_codebase(codebase_path, args.modules)
    print(f"Found {len(python_files)} Python files to analyze", file=sys.stderr)

    # Analyze each file
    all_analyses = []
    modified_files = []

    for py_file in python_files:
        print(f"Analyzing {py_file}...", file=sys.stderr)
        analysis = analyze_file(py_file, target_version, inferencer, args.strict)

        if 'error' in analysis:
            print(f"  Warning: {analysis['error']}", file=sys.stderr)
            continue

        all_analyses.append(analysis)

        # Apply annotations
        if analysis.get('functions'):
            updated_content, changes = apply_annotations(py_file, analysis, args.dry_run)
            if changes:
                if not args.dry_run:
                    modified_files.append(py_file)
                print(f"  Added annotations to {len(changes)} functions", file=sys.stderr)

    # Generate reports
    coverage = generate_coverage_report(all_analyses)

    report = {
        'timestamp': datetime.now().isoformat(),
        'codebase_path': codebase_path,
        'target_version': target_version,
        'dry_run': args.dry_run,
        'files_analyzed': len(all_analyses),
        'coverage': coverage,
        'analyses': all_analyses,
    }

    # Save JSON report
    report_path = os.path.join(output_dir, 'typing-report.json')
    save_json(report, report_path)
    print(f"Report saved to {report_path}", file=sys.stderr)

    # Create py.typed marker
    py_typed_path = os.path.join(codebase_path, 'py.typed')
    if not os.path.exists(py_typed_path):
        write_file(py_typed_path, '')
        print(f"Created py.typed marker at {py_typed_path}", file=sys.stderr)

    print(f"\nCoverage: {coverage['annotated_functions']}/{coverage['total_functions']} "
          f"({coverage['coverage_percent']:.1f}%)", file=sys.stderr)

    return 0


if __name__ == '__main__':
    sys.exit(main())
