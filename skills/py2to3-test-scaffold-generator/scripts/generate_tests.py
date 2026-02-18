#!/usr/bin/env python3
"""
Test Scaffold Generator — Main Test Generation Script

Analyzes a Python module via AST and generates characterization tests,
encoding boundary tests, and serialization round-trip tests.

Produces:
  - test_<module>_characterization.py  — behavior-capture tests
  - test_<module>_encoding.py          — encoding boundary tests
  - test_<module>_roundtrip.py         — serialization round-trip tests
  - test-manifest.json                 — catalog of generated tests

Usage:
    python3 generate_tests.py <module_path> \
        --output <output_dir> \
        --target-version 3.12 \
        [--data-report <data-layer-report.json>] \
        [--encoding-map <encoding-map.json>] \
        [--framework pytest] \
        [--include-hypothesis]
"""

import argparse
import ast
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# AST Analysis
# ═══════════════════════════════════════════════════════════════════════════

def analyze_module(filepath: str) -> Dict[str, Any]:
    """Analyze a Python module and extract testable elements.

    Falls back to regex-based analysis if AST parsing fails (which is expected
    for Python 2-only syntax).
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except IOError as e:
        return {"error": str(e), "functions": [], "classes": []}

    module_name = Path(filepath).stem

    # Try AST parsing first
    try:
        tree = ast.parse(source)
        return _analyze_ast(tree, source, module_name)
    except SyntaxError:
        # Fall back to regex for Py2-only syntax
        return _analyze_regex(source, module_name)


def _analyze_ast(tree: ast.Module, source: str, module_name: str) -> Dict[str, Any]:
    """Extract functions, classes, and patterns from an AST."""
    functions = []
    classes = []
    imports = []
    data_patterns = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Only public functions (not starting with _)
            if not node.name.startswith("_") or node.name.startswith("__"):
                func_info = {
                    "name": node.name,
                    "args": _extract_args(node),
                    "decorators": [_get_decorator_name(d) for d in node.decorator_list],
                    "has_return": _has_return(node),
                    "docstring": ast.get_docstring(node) or "",
                    "line": node.lineno,
                    "is_method": False,
                }
                functions.append(func_info)

        elif isinstance(node, ast.ClassDef):
            methods = []
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append({
                        "name": item.name,
                        "args": _extract_args(item),
                        "has_return": _has_return(item),
                        "is_special": item.name.startswith("__"),
                    })
            classes.append({
                "name": node.name,
                "methods": methods,
                "bases": [_get_name(b) for b in node.bases],
                "has_init": any(m["name"] == "__init__" for m in methods),
                "has_getstate": any(m["name"] == "__getstate__" for m in methods),
                "has_setstate": any(m["name"] == "__setstate__" for m in methods),
                "line": node.lineno,
            })

        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    # Detect data patterns
    source_lower = source.lower()
    if "pickle" in source_lower or "cpickle" in source_lower:
        data_patterns.append("serialization_pickle")
    if "struct.pack" in source or "struct.unpack" in source:
        data_patterns.append("binary_protocol")
    if "socket" in source_lower:
        data_patterns.append("network_io")
    if "serial" in source_lower:
        data_patterns.append("serial_io")
    if ".encode(" in source or ".decode(" in source:
        data_patterns.append("encoding_operations")
    if "open(" in source:
        data_patterns.append("file_io")

    return {
        "module_name": module_name,
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "data_patterns": data_patterns,
    }


def _extract_args(func_node: ast.FunctionDef) -> List[Dict[str, Any]]:
    """Extract argument info from a function definition."""
    args = []
    for arg in func_node.args.args:
        name = arg.arg if hasattr(arg, "arg") else getattr(arg, "id", "?")
        if name == "self" or name == "cls":
            continue
        args.append({"name": name, "has_default": False})

    # Mark args with defaults
    num_defaults = len(func_node.args.defaults)
    if num_defaults > 0:
        for i in range(num_defaults):
            idx = len(args) - num_defaults + i
            if 0 <= idx < len(args):
                args[idx]["has_default"] = True

    return args


def _has_return(func_node: ast.FunctionDef) -> bool:
    """Check if a function has a return statement with a value."""
    for node in ast.walk(func_node):
        if isinstance(node, ast.Return) and node.value is not None:
            return True
    return False


def _get_decorator_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_get_name(node.value)}.{node.attr}"
    return "unknown"


def _get_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    elif isinstance(node, ast.Attribute):
        return f"{_get_name(node.value)}.{node.attr}"
    return "?"


def _analyze_regex(source: str, module_name: str) -> Dict[str, Any]:
    """Regex-based analysis for files that fail AST parsing (Py2 syntax)."""
    functions = []
    classes = []

    # Find function definitions
    func_re = re.compile(r"^def\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE)
    for match in func_re.finditer(source):
        name = match.group(1)
        args_str = match.group(2)
        args = []
        for arg in args_str.split(","):
            arg = arg.strip()
            if arg and arg not in ("self", "cls"):
                arg_name = arg.split("=")[0].strip().split(":")[0].strip()
                if arg_name:
                    args.append({
                        "name": arg_name,
                        "has_default": "=" in arg,
                    })
        if not name.startswith("_") or name.startswith("__"):
            functions.append({
                "name": name,
                "args": args,
                "decorators": [],
                "has_return": True,  # Assume yes for regex fallback
                "docstring": "",
                "line": source[:match.start()].count("\n") + 1,
                "is_method": False,
            })

    # Find class definitions
    class_re = re.compile(r"^class\s+(\w+)\s*(?:\(([^)]*)\))?:", re.MULTILINE)
    for match in class_re.finditer(source):
        name = match.group(1)
        bases = (match.group(2) or "").split(",")
        bases = [b.strip() for b in bases if b.strip()]
        classes.append({
            "name": name,
            "methods": [],
            "bases": bases,
            "has_init": "__init__" in source,
            "has_getstate": "__getstate__" in source,
            "has_setstate": "__setstate__" in source,
            "line": source[:match.start()].count("\n") + 1,
        })

    data_patterns = []
    if "pickle" in source.lower():
        data_patterns.append("serialization_pickle")
    if "struct" in source:
        data_patterns.append("binary_protocol")
    if "socket" in source.lower():
        data_patterns.append("network_io")
    if "open(" in source:
        data_patterns.append("file_io")

    return {
        "module_name": module_name,
        "functions": functions,
        "classes": classes,
        "imports": [],
        "data_patterns": data_patterns,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Test Code Generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_characterization_tests(
    analysis: Dict[str, Any],
    module_path: str,
    framework: str = "pytest",
) -> Tuple[str, List[Dict[str, Any]]]:
    """Generate characterization tests for public functions and classes."""
    module_name = analysis["module_name"]
    manifest_entries = []
    lines = []

    # Header
    lines.append(f'"""')
    lines.append(f"Characterization tests for {module_name}.")
    lines.append(f"")
    lines.append(f"These tests capture the module's current behavior under Python 2.")
    lines.append(f"After conversion to Python 3, verify that behavior is preserved.")
    lines.append(f"Tests marked CHARACTERIZATION may need updating if behavior")
    lines.append(f"intentionally changes during migration.")
    lines.append(f'"""')
    lines.append(f"")

    if framework == "pytest":
        lines.append("import pytest")
    else:
        lines.append("import unittest")
    lines.append("import sys")
    lines.append("import os")
    lines.append("")
    lines.append(f"# Adjust import path as needed for your project structure")
    lines.append(f"# import {module_name}")
    lines.append("")
    lines.append("")

    # Generate tests for each public function
    for func in analysis.get("functions", []):
        if func["name"].startswith("__") and func["name"].endswith("__"):
            continue  # Skip dunder methods at module level

        test_name = f"test_{func['name']}_characterization"
        args_placeholder = ", ".join(
            f"{a['name']}=None" if a["has_default"] else f"# {a['name']}"
            for a in func["args"]
        )

        lines.append(f"class Test{_camel_case(func['name'])}Characterization:")
        lines.append(f'    """Characterization tests for {func["name"]}()."""')
        lines.append(f"")
        lines.append(f"    def test_basic_call(self):")
        lines.append(f'        """CHARACTERIZATION: capture basic behavior."""')
        lines.append(f"        # TODO: Replace with actual arguments and expected result")
        lines.append(f"        # result = {module_name}.{func['name']}({args_placeholder})")
        lines.append(f"        # assert result == <expected>")
        lines.append(f"        pass")
        lines.append(f"")

        if func["has_return"]:
            lines.append(f"    def test_return_type(self):")
            lines.append(f'        """CHARACTERIZATION: verify return type."""')
            lines.append(f"        # result = {module_name}.{func['name']}({args_placeholder})")
            lines.append(f"        # assert isinstance(result, <expected_type>)")
            lines.append(f"        pass")
            lines.append(f"")

        lines.append(f"    def test_with_none_input(self):")
        lines.append(f'        """CHARACTERIZATION: behavior with None/empty input."""')
        lines.append(f"        # Test edge case handling")
        lines.append(f"        pass")
        lines.append(f"")
        lines.append(f"")

        manifest_entries.append({
            "file": f"test_{module_name}_characterization.py",
            "test_name": test_name,
            "type": "characterization",
            "target_function": func["name"],
            "data_category": None,
            "notes": f"Captures behavior of {func['name']}()",
        })

    # Generate tests for each class
    for cls in analysis.get("classes", []):
        lines.append(f"class Test{cls['name']}Characterization:")
        lines.append(f'    """Characterization tests for {cls["name"]}."""')
        lines.append(f"")

        if cls.get("has_init"):
            lines.append(f"    def test_construction(self):")
            lines.append(f'        """CHARACTERIZATION: object construction."""')
            lines.append(f"        # obj = {module_name}.{cls['name']}()")
            lines.append(f"        # assert obj is not None")
            lines.append(f"        pass")
            lines.append(f"")

        for method in cls.get("methods", []):
            if method["name"].startswith("_") and not method["name"].startswith("__"):
                continue
            if method["name"] in ("__init__", "__del__"):
                continue

            lines.append(f"    def test_{method['name'].strip('_')}_basic(self):")
            lines.append(f'        """CHARACTERIZATION: {method["name"]}() behavior."""')
            lines.append(f"        # obj = {module_name}.{cls['name']}()")
            lines.append(f"        # result = obj.{method['name']}()")
            lines.append(f"        pass")
            lines.append(f"")

        lines.append(f"")

        manifest_entries.append({
            "file": f"test_{module_name}_characterization.py",
            "test_name": f"Test{cls['name']}Characterization",
            "type": "characterization",
            "target_function": cls["name"],
            "data_category": None,
            "notes": f"Characterization tests for class {cls['name']}",
        })

    return "\n".join(lines), manifest_entries


def generate_encoding_tests(
    analysis: Dict[str, Any],
    module_path: str,
    data_report: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Generate encoding boundary tests."""
    module_name = analysis["module_name"]
    manifest_entries = []
    lines = []

    lines.append(f'"""')
    lines.append(f"Encoding boundary tests for {module_name}.")
    lines.append(f"")
    lines.append(f"These tests exercise data paths with non-ASCII input to ensure")
    lines.append(f"encoding handling works correctly after Python 3 migration.")
    lines.append(f'"""')
    lines.append(f"")
    lines.append("import pytest")
    lines.append("import sys")
    lines.append("")
    lines.append(f"# import {module_name}")
    lines.append("")
    lines.append("")
    lines.append("# ── Test Data ──────────────────────────────────────────────────")
    lines.append("")
    lines.append("# UTF-8 test strings")
    lines.append('UTF8_SAMPLES = [')
    lines.append('    "hello",                    # Pure ASCII')
    lines.append('    "café résumé naïve",        # Latin accented')
    lines.append('    "日本語テスト",              # CJK characters')
    lines.append('    "🔧⚙️🏭",                   # Emoji (industrial theme)')
    lines.append('    "Ñoño",                     # Spanish')
    lines.append('    "",                          # Empty string')
    lines.append("]")
    lines.append("")
    lines.append("# Latin-1 byte sequences (not valid UTF-8)")
    lines.append("LATIN1_BYTES = [")
    lines.append("    b'\\xe9\\xe8\\xea',           # é è ê")
    lines.append("    b'\\xf1\\xfc\\xe4',           # ñ ü ä")
    lines.append("    b'\\xff\\xfe',               # ÿ þ")
    lines.append("]")
    lines.append("")
    lines.append("# EBCDIC byte sequences (cp500)")
    lines.append("EBCDIC_BYTES = [")
    lines.append("    b'\\xc8\\x85\\x93\\x93\\x96',  # 'Hello' in EBCDIC cp500")
    lines.append("    b'\\xf0\\xf1\\xf2\\xf3',       # '0123' in EBCDIC cp500")
    lines.append("]")
    lines.append("")
    lines.append("# Binary data (not valid in any text encoding)")
    lines.append("BINARY_SAMPLES = [")
    lines.append("    b'\\x00\\x01\\x02\\xff\\xfe\\xfd',")
    lines.append("    b'\\x80\\x81\\x82',")
    lines.append("    bytes(range(256)),")
    lines.append("]")
    lines.append("")
    lines.append("")

    # Generate tests for functions that handle data
    data_functions = [
        f for f in analysis.get("functions", [])
        if any(
            pattern in str(f.get("name", "")).lower()
            for pattern in ["read", "write", "parse", "decode", "encode", "load", "dump",
                           "send", "recv", "process", "handle", "convert", "format"]
        )
        or f.get("args")  # Any function with arguments is worth testing with encoding data
    ]

    # Also include all functions if module has data patterns
    if analysis.get("data_patterns"):
        data_functions = analysis.get("functions", [])

    for func in data_functions[:20]:  # Cap at 20 functions to avoid huge test files
        if func["name"].startswith("__") and func["name"].endswith("__"):
            continue

        test_class = f"Test{_camel_case(func['name'])}Encoding"
        lines.append(f"class {test_class}:")
        lines.append(f'    """Encoding boundary tests for {func["name"]}()."""')
        lines.append(f"")

        # UTF-8 tests
        lines.append(f"    @pytest.mark.parametrize('text', UTF8_SAMPLES)")
        lines.append(f"    def test_utf8_input(self, text):")
        lines.append(f'        """Encoding test: verify behavior with UTF-8 input."""')
        lines.append(f"        # result = {module_name}.{func['name']}(text)")
        lines.append(f"        # assert result is not None")
        lines.append(f"        pass")
        lines.append(f"")

        # Binary tests (for functions likely handling bytes)
        if any(p in analysis.get("data_patterns", [])
               for p in ["binary_protocol", "network_io", "serial_io"]):
            lines.append(f"    @pytest.mark.parametrize('data', BINARY_SAMPLES)")
            lines.append(f"    def test_binary_input(self, data):")
            lines.append(f'        """Encoding test: verify behavior with raw binary input."""')
            lines.append(f"        # result = {module_name}.{func['name']}(data)")
            lines.append(f"        # Verify no UnicodeDecodeError")
            lines.append(f"        pass")
            lines.append(f"")

        # Mixed encoding test
        lines.append(f"    def test_mixed_ascii_nonascii(self):")
        lines.append(f'        """Encoding test: mixed ASCII and non-ASCII data."""')
        lines.append(f"        # Test with data that contains both ASCII and non-ASCII")
        lines.append(f"        # input_data = b'Status: OK \\xe9\\xe8'  # ASCII + Latin-1")
        lines.append(f"        pass")
        lines.append(f"")
        lines.append(f"")

        manifest_entries.append({
            "file": f"test_{module_name}_encoding.py",
            "test_name": test_class,
            "type": "encoding_boundary",
            "target_function": func["name"],
            "data_category": "encoding",
            "notes": f"Encoding boundary tests for {func['name']}()",
        })

    return "\n".join(lines), manifest_entries


def generate_roundtrip_tests(
    analysis: Dict[str, Any],
    module_path: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Generate serialization round-trip tests."""
    module_name = analysis["module_name"]
    manifest_entries = []
    lines = []

    # Only generate if there are serialization patterns
    has_serialization = any(
        "serialization" in p for p in analysis.get("data_patterns", [])
    )
    has_getstate = any(
        cls.get("has_getstate") for cls in analysis.get("classes", [])
    )

    if not has_serialization and not has_getstate:
        return "", []

    lines.append(f'"""')
    lines.append(f"Serialization round-trip tests for {module_name}.")
    lines.append(f"")
    lines.append(f"Verify that objects survive serialize/deserialize cycles.")
    lines.append(f"Critical: Py2 pickled str becomes Py3 bytes.")
    lines.append(f'"""')
    lines.append(f"")
    lines.append("import pickle")
    lines.append("import json")
    lines.append("import pytest")
    lines.append("")
    lines.append(f"# import {module_name}")
    lines.append("")
    lines.append("")

    for cls in analysis.get("classes", []):
        if cls.get("has_getstate") or cls.get("has_setstate") or has_serialization:
            lines.append(f"class Test{cls['name']}RoundTrip:")
            lines.append(f'    """Serialization round-trip tests for {cls["name"]}."""')
            lines.append(f"")
            lines.append(f"    def _make_instance(self):")
            lines.append(f'        """Create a test instance. Adjust constructor args."""')
            lines.append(f"        # return {module_name}.{cls['name']}()")
            lines.append(f"        pass")
            lines.append(f"")
            lines.append(f"    def test_pickle_roundtrip_protocol2(self):")
            lines.append(f'        """Round-trip: pickle with protocol 2 (Py2 compatible)."""')
            lines.append(f"        # obj = self._make_instance()")
            lines.append(f"        # data = pickle.dumps(obj, protocol=2)")
            lines.append(f"        # restored = pickle.loads(data)")
            lines.append(f"        # assert restored == obj")
            lines.append(f"        pass")
            lines.append(f"")
            lines.append(f"    def test_pickle_roundtrip_highest_protocol(self):")
            lines.append(f'        """Round-trip: pickle with highest available protocol."""')
            lines.append(f"        # obj = self._make_instance()")
            lines.append(f"        # data = pickle.dumps(obj, protocol=pickle.HIGHEST_PROTOCOL)")
            lines.append(f"        # restored = pickle.loads(data)")
            lines.append(f"        # assert restored == obj")
            lines.append(f"        pass")
            lines.append(f"")

            if cls.get("has_getstate"):
                lines.append(f"    def test_getstate_setstate_consistency(self):")
                lines.append(f'        """Verify __getstate__/__setstate__ round-trip."""')
                lines.append(f"        # obj = self._make_instance()")
                lines.append(f"        # state = obj.__getstate__()")
                lines.append(f"        # new_obj = {module_name}.{cls['name']}.__new__({module_name}.{cls['name']})")
                lines.append(f"        # new_obj.__setstate__(state)")
                lines.append(f"        # assert new_obj == obj")
                lines.append(f"        pass")
                lines.append(f"")

            lines.append(f"")

            manifest_entries.append({
                "file": f"test_{module_name}_roundtrip.py",
                "test_name": f"Test{cls['name']}RoundTrip",
                "type": "roundtrip",
                "target_function": cls["name"],
                "data_category": "serialization",
                "notes": f"Pickle round-trip tests for {cls['name']}",
            })

    return "\n".join(lines), manifest_entries


def _camel_case(name: str) -> str:
    """Convert snake_case to CamelCase."""
    return "".join(word.capitalize() for word in name.split("_"))


def generate_property_tests(
    analysis: Dict[str, Any],
    module_path: str,
) -> Tuple[str, List[Dict[str, Any]]]:
    """Generate property-based tests using hypothesis."""
    module_name = analysis["module_name"]
    manifest_entries = []
    lines = []

    # Check if hypothesis is available (it's optional)
    lines.append(f'"""')
    lines.append(f"Property-based tests for {module_name}.")
    lines.append(f"")
    lines.append(f"These tests use hypothesis to explore the input space automatically.")
    lines.append(f"Properties should hold across all valid inputs.")
    lines.append(f'"""')
    lines.append(f"")
    lines.append("import pytest")
    lines.append("")
    lines.append("try:")
    lines.append("    from hypothesis import given, strategies as st")
    lines.append("    HAS_HYPOTHESIS = True")
    lines.append("except ImportError:")
    lines.append("    HAS_HYPOTHESIS = False")
    lines.append("    st = None")
    lines.append("")
    lines.append(f"# import {module_name}")
    lines.append("")
    lines.append("")

    if not analysis.get("data_patterns"):
        lines.append("# No data transformation patterns detected.")
    else:
        # Generate property tests for data functions
        for func in analysis.get("functions", [])[:10]:  # Cap at 10
            if func["name"].startswith("__"):
                continue

            # Generate basic property test
            test_class = f"Test{_camel_case(func['name'])}Properties"
            lines.append(f"@pytest.mark.skipif(not HAS_HYPOTHESIS, reason='hypothesis not installed')")
            lines.append(f"class {test_class}:")
            lines.append(f'    """Property-based tests for {func["name"]}()."""')
            lines.append(f"")

            # Property 1: Function should not crash with reasonable input
            lines.append(f"    @given(st.text())")
            lines.append(f"    def test_text_input_does_not_crash(self, text):")
            lines.append(f'        """Property: {func["name"]}() accepts text without crashing."""')
            lines.append(f"        try:")
            lines.append(f"            # result = {module_name}.{func['name']}(text)")
            lines.append(f"            pass")
            lines.append(f"        except (TypeError, ValueError):")
            lines.append(f"            # Function may reject certain types — that's ok")
            lines.append(f"            pass")
            lines.append(f"")

            # Property 2: Bytes input handling
            lines.append(f"    @given(st.binary())")
            lines.append(f"    def test_binary_input_does_not_crash(self, binary_data):")
            lines.append(f'        """Property: {func["name"]}() handles binary input."""')
            lines.append(f"        try:")
            lines.append(f"            # result = {module_name}.{func['name']}(binary_data)")
            lines.append(f"            pass")
            lines.append(f"        except (TypeError, ValueError):")
            lines.append(f"            pass")
            lines.append(f"")

            # Property 3: Numbers (if function might handle numeric input)
            lines.append(f"    @given(st.integers())")
            lines.append(f"    def test_integer_input_does_not_crash(self, number):")
            lines.append(f'        """Property: {func["name"]}() handles integers."""')
            lines.append(f"        try:")
            lines.append(f"            # result = {module_name}.{func['name']}(number)")
            lines.append(f"            pass")
            lines.append(f"        except (TypeError, ValueError):")
            lines.append(f"            pass")
            lines.append(f"")

            manifest_entries.append({
                "file": f"test_{module_name}_properties.py",
                "test_name": test_class,
                "type": "property_based",
                "target_function": func["name"],
                "data_category": "input_validation",
                "notes": f"Property-based tests for {func['name']}()",
            })

    lines.append("")
    return "\n".join(lines), manifest_entries


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate test scaffolds for Python 2→3 migration."
    )
    parser.add_argument("module_path", help="Path to the module to test")
    parser.add_argument("--output", required=True, help="Output directory for test files")
    parser.add_argument(
        "--target-version", default="3.12",
        help="Target Python 3 version",
    )
    parser.add_argument("--data-report", default=None, help="Path to data-layer-report.json")
    parser.add_argument("--encoding-map", default=None, help="Path to encoding-map.json")
    parser.add_argument(
        "--framework", default="pytest", choices=["pytest", "unittest"],
        help="Test framework",
    )
    parser.add_argument("--include-hypothesis", action="store_true", help="Generate property-based tests")

    args = parser.parse_args()

    if not os.path.exists(args.module_path):
        print(f"Error: Module not found: {args.module_path}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    # Load optional data report
    data_report = None
    if args.data_report and os.path.exists(args.data_report):
        with open(args.data_report, "r") as f:
            data_report = json.load(f)

    # Analyze the module
    print(f"Analyzing {args.module_path}...")
    analysis = analyze_module(args.module_path)
    module_name = analysis["module_name"]

    print(f"  Functions found: {len(analysis.get('functions', []))}")
    print(f"  Classes found: {len(analysis.get('classes', []))}")
    print(f"  Data patterns: {analysis.get('data_patterns', [])}")

    all_manifest = []

    # Generate characterization tests
    print("Generating characterization tests...")
    char_code, char_manifest = generate_characterization_tests(
        analysis, args.module_path, args.framework,
    )
    if char_code.strip():
        char_path = os.path.join(args.output, f"test_{module_name}_characterization.py")
        with open(char_path, "w", encoding="utf-8") as f:
            f.write(char_code)
        print(f"  Written: {char_path}")
        all_manifest.extend(char_manifest)

    # Generate encoding tests
    print("Generating encoding boundary tests...")
    enc_code, enc_manifest = generate_encoding_tests(
        analysis, args.module_path, data_report,
    )
    if enc_code.strip():
        enc_path = os.path.join(args.output, f"test_{module_name}_encoding.py")
        with open(enc_path, "w", encoding="utf-8") as f:
            f.write(enc_code)
        print(f"  Written: {enc_path}")
        all_manifest.extend(enc_manifest)

    # Generate round-trip tests
    print("Generating round-trip tests...")
    rt_code, rt_manifest = generate_roundtrip_tests(analysis, args.module_path)
    if rt_code.strip():
        rt_path = os.path.join(args.output, f"test_{module_name}_roundtrip.py")
        with open(rt_path, "w", encoding="utf-8") as f:
            f.write(rt_code)
        print(f"  Written: {rt_path}")
        all_manifest.extend(rt_manifest)

    # Generate property-based tests if requested
    if args.include_hypothesis:
        print("Generating property-based tests...")
        prop_code, prop_manifest = generate_property_tests(analysis, args.module_path)
        if prop_code.strip():
            prop_path = os.path.join(args.output, f"test_{module_name}_properties.py")
            with open(prop_path, "w", encoding="utf-8") as f:
                f.write(prop_code)
            print(f"  Written: {prop_path}")
            all_manifest.extend(prop_manifest)

    # Write manifest
    manifest = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "module": args.module_path,
        "module_name": module_name,
        "target_version": args.target_version,
        "framework": args.framework,
        "tests": all_manifest,
        "coverage": {"before": None, "after": None},
    }
    manifest_path = os.path.join(args.output, "test-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nManifest: {manifest_path}")

    # Summary
    print(f"\n{'='*50}")
    print(f"Test Generation Summary")
    print(f"{'='*50}")
    print(f"Module:              {module_name}")
    print(f"Tests generated:     {len(all_manifest)}")
    char_count = sum(1 for m in all_manifest if m["type"] == "characterization")
    enc_count = sum(1 for m in all_manifest if m["type"] == "encoding_boundary")
    rt_count = sum(1 for m in all_manifest if m["type"] == "roundtrip")
    print(f"  Characterization:  {char_count}")
    print(f"  Encoding:          {enc_count}")
    print(f"  Round-trip:        {rt_count}")
    print(f"\nNext: Fill in the TODO placeholders with actual test data.")
    print(f"The tests use placeholder assertions — run against Py2 to capture actual behavior.")


if __name__ == "__main__":
    main()
