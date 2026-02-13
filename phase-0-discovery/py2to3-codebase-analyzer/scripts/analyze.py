#!/usr/bin/env python3
"""
Codebase Analyzer — Main Analysis Script

Walks a Python 2 codebase, parses each .py file, and produces a comprehensive
inventory of Python 2 patterns, imports, metrics, and migration risk assessments.

Usage:
    python3 analyze.py <codebase_path> --output <output_dir> \
        [--exclude "**/vendor/**"] \
        [--target-versions 3.9 3.11 3.12 3.13]

Output:
    <output_dir>/raw-scan.json — Complete scan results for all files
    <output_dir>/py2-ism-inventory.json — Categorized Python 2 patterns
    <output_dir>/version-matrix.md — Target version compatibility matrix
"""

import ast
import json
import os
import re
import sys
import fnmatch
import argparse
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Any, Optional, Tuple, Set


# ── Pattern Definitions ──────────────────────────────────────────────────────

# Regex patterns for Python 2 constructs that won't parse under Python 3 AST.
# These catch syntax that Python 3's parser rejects outright.
REGEX_PATTERNS = {
    "print_statement": {
        "pattern": r"^\s*print\s+[^(]",
        "category": "syntax",
        "risk": "low",
        "description": "print statement (not function call)",
        "py3_fix": "print() function",
    },
    "except_comma": {
        "pattern": r"except\s+\w[\w.]*\s*,\s*\w+",
        "category": "syntax",
        "risk": "low",
        "description": "except with comma syntax",
        "py3_fix": "except Exception as e:",
    },
    "backtick_repr": {
        "pattern": r"`[^`]+`",
        "category": "syntax",
        "risk": "low",
        "description": "backtick repr()",
        "py3_fix": "repr()",
    },
    "diamond_operator": {
        "pattern": r"<>",
        "category": "syntax",
        "risk": "low",
        "description": "<> operator",
        "py3_fix": "!= operator",
    },
    "long_literal": {
        "pattern": r"\b\d+[lL]\b",
        "category": "syntax",
        "risk": "low",
        "description": "long integer literal",
        "py3_fix": "regular int (no L suffix)",
    },
    "octal_literal_old": {
        "pattern": r"\b0\d{2,}\b",
        "category": "syntax",
        "risk": "low",
        "description": "old-style octal literal (0777)",
        "py3_fix": "0o777 syntax",
    },
    "raise_string": {
        "pattern": r"raise\s+['\"]",
        "category": "syntax",
        "risk": "low",
        "description": "raise string exception",
        "py3_fix": "raise Exception('...')",
    },
    "exec_statement": {
        "pattern": r"^\s*exec\s+[^(]",
        "category": "syntax",
        "risk": "medium",
        "description": "exec statement (not function)",
        "py3_fix": "exec() function",
    },
    "unicode_prefix": {
        "pattern": r"""(?<![brBR])u['"]""",
        "category": "semantic_string",
        "risk": "medium",
        "description": "u'' unicode string prefix",
        "py3_fix": "regular string (all strings are unicode in Py3)",
    },
}

# AST-based patterns — these we detect by walking the parsed AST.
# Defined as (node_type, check_function_name, metadata).
AST_PATTERNS = {
    "has_key": {
        "description": "dict.has_key() method",
        "category": "syntax",
        "risk": "low",
        "py3_fix": "'key in dict' operator",
    },
    "iteritems": {
        "description": "dict.iteritems()/itervalues()/iterkeys()",
        "category": "semantic_iterator",
        "risk": "low",
        "py3_fix": "dict.items()/values()/keys()",
    },
    "xrange": {
        "description": "xrange() builtin",
        "category": "syntax",
        "risk": "low",
        "py3_fix": "range()",
    },
    "raw_input": {
        "description": "raw_input() builtin",
        "category": "syntax",
        "risk": "low",
        "py3_fix": "input()",
    },
    "unicode_builtin": {
        "description": "unicode() builtin",
        "category": "semantic_string",
        "risk": "medium",
        "py3_fix": "str()",
    },
    "apply_builtin": {
        "description": "apply() builtin",
        "category": "syntax",
        "risk": "low",
        "py3_fix": "direct function call with *args/**kwargs",
    },
    "reduce_builtin": {
        "description": "reduce() builtin (moved to functools)",
        "category": "semantic_import",
        "risk": "low",
        "py3_fix": "functools.reduce()",
    },
    "cmp_builtin": {
        "description": "cmp() builtin",
        "category": "semantic_comparison",
        "risk": "medium",
        "py3_fix": "(a > b) - (a < b) or custom function",
    },
    "long_builtin": {
        "description": "long() builtin",
        "category": "syntax",
        "risk": "low",
        "py3_fix": "int()",
    },
    "buffer_builtin": {
        "description": "buffer() builtin",
        "category": "semantic_other",
        "risk": "medium",
        "py3_fix": "memoryview()",
    },
    "file_builtin": {
        "description": "file() builtin",
        "category": "syntax",
        "risk": "low",
        "py3_fix": "open()",
    },
    "execfile_builtin": {
        "description": "execfile() builtin",
        "category": "syntax",
        "risk": "medium",
        "py3_fix": "exec(open(...).read())",
    },
    "reload_builtin": {
        "description": "reload() builtin",
        "category": "semantic_import",
        "risk": "low",
        "py3_fix": "importlib.reload()",
    },
    "cmp_method": {
        "description": "__cmp__ method definition",
        "category": "semantic_comparison",
        "risk": "medium",
        "py3_fix": "__lt__, __eq__, etc. or functools.total_ordering",
    },
    "nonzero_method": {
        "description": "__nonzero__ method definition",
        "category": "semantic_other",
        "risk": "low",
        "py3_fix": "__bool__",
    },
    "unicode_method": {
        "description": "__unicode__ method definition",
        "category": "semantic_string",
        "risk": "medium",
        "py3_fix": "__str__ (old __str__ becomes __bytes__)",
    },
    "getslice_method": {
        "description": "__getslice__/__setslice__/__delslice__ method",
        "category": "semantic_other",
        "risk": "medium",
        "py3_fix": "__getitem__ with slice objects",
    },
    "div_method": {
        "description": "__div__ method definition",
        "category": "semantic_numeric",
        "risk": "medium",
        "py3_fix": "__truediv__ and/or __floordiv__",
    },
    "metaclass_attribute": {
        "description": "__metaclass__ class attribute",
        "category": "semantic_class",
        "risk": "medium",
        "py3_fix": "class Foo(metaclass=Meta):",
    },
    "old_style_class": {
        "description": "old-style class (no base class)",
        "category": "semantic_class",
        "risk": "low",
        "py3_fix": "all classes are new-style in Py3 (inheriting from object is optional)",
    },
    "map_result_indexed": {
        "description": "map()/filter()/zip() result used as list (indexed/sliced/len'd)",
        "category": "semantic_iterator",
        "risk": "medium",
        "py3_fix": "list(map(...)) or list comprehension",
    },
    "dict_keys_indexed": {
        "description": "dict.keys()/values()/items() result indexed or used as list",
        "category": "semantic_iterator",
        "risk": "medium",
        "py3_fix": "list(dict.keys()) or refactor",
    },
    "integer_division": {
        "description": "/ operator on integer operands (behavior changes)",
        "category": "semantic_numeric",
        "risk": "high",
        "py3_fix": "// for integer division, / for true division",
    },
    "sorted_cmp": {
        "description": "sorted() or .sort() with cmp= parameter",
        "category": "semantic_comparison",
        "risk": "medium",
        "py3_fix": "key= parameter with functools.cmp_to_key()",
    },
    "open_without_encoding": {
        "description": "open() without explicit encoding or binary mode",
        "category": "semantic_string",
        "risk": "high",
        "py3_fix": "open(f, encoding='...') or open(f, 'rb')",
    },
    "struct_usage": {
        "description": "struct.pack/unpack usage (binary data handling)",
        "category": "data_layer",
        "risk": "high",
        "py3_fix": "verify bytes/str handling at boundaries",
    },
    "pickle_usage": {
        "description": "pickle.load/dump usage (serialization)",
        "category": "data_layer",
        "risk": "high",
        "py3_fix": "verify cross-version compatibility, set protocol",
    },
    "socket_recv": {
        "description": "socket.recv() usage (returns bytes in Py3)",
        "category": "data_layer",
        "risk": "high",
        "py3_fix": "handle bytes return value, decode explicitly",
    },
    "encode_decode": {
        "description": ".encode()/.decode() calls",
        "category": "semantic_string",
        "risk": "medium",
        "py3_fix": "verify encoding correctness — presence may indicate awareness",
    },
    "ebcdic_codec": {
        "description": "EBCDIC codec usage (cp500, cp1047, etc.)",
        "category": "data_layer",
        "risk": "high",
        "py3_fix": "verify EBCDIC handling is bytes-aware",
    },
    "renamed_stdlib": {
        "description": "import from renamed stdlib module",
        "category": "semantic_import",
        "risk": "low",
        "py3_fix": "update import to Py3 name",
    },
    "removed_stdlib": {
        "description": "import from removed stdlib module",
        "category": "semantic_import",
        "risk": "high",
        "py3_fix": "replace with alternative library",
    },
    "future_import": {
        "description": "from __future__ import (positive signal)",
        "category": "info",
        "risk": "none",
        "py3_fix": "already present — good sign",
    },
    "relative_import": {
        "description": "implicit relative import",
        "category": "semantic_import",
        "risk": "medium",
        "py3_fix": "explicit relative import (from . import ...)",
    },
}

# Stdlib modules renamed between Py2 and Py3
RENAMED_STDLIB = {
    "ConfigParser": "configparser",
    "Queue": "queue",
    "SocketServer": "socketserver",
    "HTMLParser": "html.parser",
    "httplib": "http.client",
    "urlparse": "urllib.parse",
    "urllib2": "urllib.request",
    "cPickle": "pickle",
    "cStringIO": "io.StringIO",
    "cProfile": "cProfile",  # actually same name, but import path may differ
    "repr": "reprlib",
    "Tkinter": "tkinter",
    "tkFont": "tkinter.font",
    "thread": "_thread",
    "commands": "subprocess",
    "copy_reg": "copyreg",
    "markupbase": "_markupbase",
    "dbhash": "dbm.bsd",
    "dumbdbm": "dbm.dumb",
    "gdbm": "dbm.gnu",
    "xmlrpclib": "xmlrpc.client",
    "DocXMLRPCServer": "xmlrpc.server",
    "SimpleXMLRPCServer": "xmlrpc.server",
    "BaseHTTPServer": "http.server",
    "SimpleHTTPServer": "http.server",
    "CGIHTTPServer": "http.server",
    "Cookie": "http.cookies",
    "cookielib": "http.cookiejar",
    "htmlentitydefs": "html.entities",
    "robotparser": "urllib.robotparser",
    "UserDict": "collections",
    "UserList": "collections",
    "UserString": "collections",
}

# Stdlib modules removed in specific Python 3 versions
# Format: module_name -> version_removed
REMOVED_STDLIB = {
    # Removed in Python 3.12
    "aifc": "3.12",
    "audioop": "3.12",
    "cgi": "3.12",
    "cgitb": "3.12",
    "chunk": "3.12",
    "crypt": "3.12",
    "imghdr": "3.12",
    "mailcap": "3.12",
    "msilib": "3.12",
    "nis": "3.12",
    "nntplib": "3.12",
    "ossaudiodev": "3.12",
    "pipes": "3.12",
    "sndhdr": "3.12",
    "spwd": "3.12",
    "sunau": "3.12",
    "telnetlib": "3.12",
    "uu": "3.12",
    "xdrlib": "3.12",
    # distutils — the big one
    "distutils": "3.12",
}

EBCDIC_CODECS = {"cp037", "cp500", "cp1047", "cp1140", "cp273", "cp424", "cp875"}


# ── AST Visitor ──────────────────────────────────────────────────────────────

class Py2PatternVisitor(ast.NodeVisitor):
    """Walk a Python AST and collect Python 2 patterns."""

    def __init__(self, source_lines: List[str], filename: str):
        self.findings: List[Dict[str, Any]] = []
        self.imports: List[Dict[str, Any]] = []
        self.source_lines = source_lines
        self.filename = filename
        self.future_imports: List[str] = []
        self.has_encoding_declaration = False
        self.encoding_declared: Optional[str] = None
        self.metrics = {
            "functions": 0,
            "classes": 0,
            "lines": len(source_lines),
        }

    def _add_finding(self, pattern_key: str, lineno: int, extra: Optional[Dict] = None):
        info = AST_PATTERNS.get(pattern_key, {})
        finding = {
            "pattern": pattern_key,
            "file": self.filename,
            "line": lineno,
            "category": info.get("category", "unknown"),
            "risk": info.get("risk", "unknown"),
            "description": info.get("description", pattern_key),
            "py3_fix": info.get("py3_fix", ""),
            "source": self.source_lines[lineno - 1].rstrip() if lineno <= len(self.source_lines) else "",
        }
        if extra:
            finding.update(extra)
        self.findings.append(finding)

    def _add_import(self, module: str, names: List[str], lineno: int, is_from: bool):
        self.imports.append({
            "module": module,
            "names": names,
            "line": lineno,
            "is_from_import": is_from,
            "file": self.filename,
        })

    # ── Import tracking ──────────────────────────────────────────────────

    def visit_Import(self, node):
        for alias in node.names:
            self._add_import(alias.name, [alias.asname or alias.name], node.lineno, False)
            self._check_import_name(alias.name, node.lineno)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        names = [alias.name for alias in node.names]

        # Check for __future__ imports
        if module == "__future__":
            self.future_imports.extend(names)
            self._add_finding("future_import", node.lineno, {"names": names})
        else:
            self._add_import(module, names, node.lineno, True)
            self._check_import_name(module, node.lineno)

        # Check for relative imports (level > 0 is explicit relative, which is fine;
        # level == 0 with a module that shadows a stdlib name could be implicit relative)
        if node.level == 0 and module and "." not in module:
            # This could be an implicit relative import in Py2.
            # We flag it as potentially needing investigation.
            pass  # Hard to detect without knowing the package structure

        self.generic_visit(node)

    def _check_import_name(self, module_name: str, lineno: int):
        """Check if an imported module is renamed or removed in Py3."""
        top_level = module_name.split(".")[0]
        if top_level in RENAMED_STDLIB:
            self._add_finding("renamed_stdlib", lineno, {
                "module": top_level,
                "py3_name": RENAMED_STDLIB[top_level],
            })
        if top_level in REMOVED_STDLIB:
            self._add_finding("removed_stdlib", lineno, {
                "module": top_level,
                "removed_in": REMOVED_STDLIB[top_level],
            })

    # ── Function/method definitions ──────────────────────────────────────

    def visit_FunctionDef(self, node):
        self.metrics["functions"] += 1
        # Check for Py2-specific magic methods
        if node.name == "__cmp__":
            self._add_finding("cmp_method", node.lineno)
        elif node.name == "__nonzero__":
            self._add_finding("nonzero_method", node.lineno)
        elif node.name == "__unicode__":
            self._add_finding("unicode_method", node.lineno)
        elif node.name in ("__getslice__", "__setslice__", "__delslice__"):
            self._add_finding("getslice_method", node.lineno)
        elif node.name == "__div__":
            self._add_finding("div_method", node.lineno)
        self.generic_visit(node)

    # ── Class definitions ────────────────────────────────────────────────

    def visit_ClassDef(self, node):
        self.metrics["classes"] += 1
        # Check for __metaclass__ in class body
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__metaclass__":
                        self._add_finding("metaclass_attribute", item.lineno)
        # Old-style class (no bases)
        if not node.bases:
            self._add_finding("old_style_class", node.lineno)
        self.generic_visit(node)

    # ── Function calls ───────────────────────────────────────────────────

    def visit_Call(self, node):
        func = node.func

        # Direct name calls: xrange(), raw_input(), etc.
        if isinstance(func, ast.Name):
            name = func.id
            if name == "xrange":
                self._add_finding("xrange", node.lineno)
            elif name == "raw_input":
                self._add_finding("raw_input", node.lineno)
            elif name == "unicode":
                self._add_finding("unicode_builtin", node.lineno)
            elif name == "apply":
                self._add_finding("apply_builtin", node.lineno)
            elif name == "reduce":
                self._add_finding("reduce_builtin", node.lineno)
            elif name == "cmp":
                self._add_finding("cmp_builtin", node.lineno)
            elif name == "long":
                self._add_finding("long_builtin", node.lineno)
            elif name == "buffer":
                self._add_finding("buffer_builtin", node.lineno)
            elif name == "file":
                self._add_finding("file_builtin", node.lineno)
            elif name == "execfile":
                self._add_finding("execfile_builtin", node.lineno)
            elif name == "reload":
                self._add_finding("reload_builtin", node.lineno)
            elif name == "open":
                self._check_open_call(node)
            elif name == "sorted":
                self._check_sorted_cmp(node)

        # Attribute calls: dict.has_key(), dict.iteritems(), etc.
        elif isinstance(func, ast.Attribute):
            attr = func.attr
            if attr == "has_key":
                self._add_finding("has_key", node.lineno)
            elif attr in ("iteritems", "itervalues", "iterkeys"):
                self._add_finding("iteritems", node.lineno, {"method": attr})
            elif attr in ("encode", "decode"):
                self._check_encode_decode(node, attr)
            elif attr == "sort":
                self._check_sorted_cmp(node)

            # struct.pack / struct.unpack
            if isinstance(func.value, ast.Name) and func.value.id == "struct":
                if attr in ("pack", "unpack", "pack_into", "unpack_from"):
                    self._add_finding("struct_usage", node.lineno)

            # pickle usage
            if isinstance(func.value, ast.Name) and func.value.id in ("pickle", "cPickle"):
                if attr in ("load", "loads", "dump", "dumps"):
                    self._add_finding("pickle_usage", node.lineno)

            # socket.recv
            if isinstance(func.value, ast.Name) and attr == "recv":
                self._add_finding("socket_recv", node.lineno)

        self.generic_visit(node)

    def _check_open_call(self, node):
        """Check if open() is called without explicit encoding or binary mode."""
        has_encoding = False
        has_binary_mode = False
        for kw in node.keywords:
            if kw.arg == "encoding":
                has_encoding = True
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                if "b" in str(kw.value.value):
                    has_binary_mode = True
        # Check positional mode argument
        if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            mode_val = str(node.args[1].value)
            if "b" in mode_val:
                has_binary_mode = True
        if not has_encoding and not has_binary_mode:
            self._add_finding("open_without_encoding", node.lineno)

    def _check_sorted_cmp(self, node):
        """Check if sorted() or .sort() uses cmp= parameter."""
        for kw in node.keywords:
            if kw.arg == "cmp":
                self._add_finding("sorted_cmp", node.lineno)

    def _check_encode_decode(self, node, method: str):
        """Track encode/decode calls and check for EBCDIC codecs."""
        codec = None
        if node.args and isinstance(node.args[0], ast.Constant):
            codec = str(node.args[0].value).lower().replace("-", "").replace("_", "")
        for kw in node.keywords:
            if kw.arg == "encoding" and isinstance(kw.value, ast.Constant):
                codec = str(kw.value.value).lower().replace("-", "").replace("_", "")

        self._add_finding("encode_decode", node.lineno, {"method": method, "codec": codec})
        if codec and codec in EBCDIC_CODECS:
            self._add_finding("ebcdic_codec", node.lineno, {"codec": codec})


# ── File Analysis ────────────────────────────────────────────────────────────

def check_encoding_declaration(source: str) -> Tuple[bool, Optional[str]]:
    """Check for PEP 263 encoding declaration in first two lines."""
    encoding_pattern = re.compile(r"#.*?coding[:=]\s*([-\w.]+)")
    lines = source.split("\n", 2)
    for line in lines[:2]:
        match = encoding_pattern.search(line)
        if match:
            return True, match.group(1)
    return False, None


def check_shebang(source: str) -> Optional[str]:
    """Extract shebang line if present."""
    if source.startswith("#!"):
        return source.split("\n", 1)[0]
    return None


def analyze_file_regex(filepath: str, source: str) -> List[Dict[str, Any]]:
    """Regex-based analysis for files that fail AST parsing.
    
    This handles Python 2 syntax that Python 3's parser can't parse.
    """
    findings = []
    lines = source.split("\n")
    for lineno, line in enumerate(lines, 1):
        for key, pdef in REGEX_PATTERNS.items():
            if re.search(pdef["pattern"], line):
                # Skip if it's inside a string (rough heuristic)
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                findings.append({
                    "pattern": key,
                    "file": filepath,
                    "line": lineno,
                    "category": pdef["category"],
                    "risk": pdef["risk"],
                    "description": pdef["description"],
                    "py3_fix": pdef["py3_fix"],
                    "source": line.rstrip(),
                    "detection": "regex",
                })
    return findings


def analyze_file(filepath: str, codebase_root: str) -> Dict[str, Any]:
    """Analyze a single Python file and return all findings."""
    rel_path = os.path.relpath(filepath, codebase_root)

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except Exception as e:
        return {
            "file": rel_path,
            "error": f"Could not read file: {e}",
            "findings": [],
            "imports": [],
            "metrics": {"lines": 0, "functions": 0, "classes": 0},
            "parse_success": False,
        }

    lines = source.split("\n")
    has_encoding, encoding = check_encoding_declaration(source)
    shebang = check_shebang(source)

    # Try AST parsing first
    try:
        tree = ast.parse(source, filename=filepath)
        visitor = Py2PatternVisitor(lines, rel_path)
        visitor.has_encoding_declaration = has_encoding
        visitor.encoding_declared = encoding
        visitor.visit(tree)

        # Also run regex patterns to catch things AST might miss
        regex_findings = analyze_file_regex(rel_path, source)
        # Deduplicate — prefer AST findings over regex for same line
        ast_lines = {(f["pattern"], f["line"]) for f in visitor.findings}
        for rf in regex_findings:
            if (rf["pattern"], rf["line"]) not in ast_lines:
                visitor.findings.append(rf)

        return {
            "file": rel_path,
            "findings": visitor.findings,
            "imports": visitor.imports,
            "future_imports": visitor.future_imports,
            "metrics": visitor.metrics,
            "encoding_declaration": encoding,
            "shebang": shebang,
            "parse_success": True,
            "error": None,
        }

    except SyntaxError:
        # File has Python 2-only syntax — fall back to regex
        regex_findings = analyze_file_regex(rel_path, source)
        # Extract imports via regex as well
        imports = []
        import_re = re.compile(r"^\s*(?:from\s+([\w.]+)\s+)?import\s+(.+)", re.MULTILINE)
        for match in import_re.finditer(source):
            module = match.group(1) or match.group(2).split(",")[0].split(" as ")[0].strip()
            imports.append({
                "module": module,
                "names": [n.strip().split(" as ")[0].strip() for n in match.group(2).split(",")],
                "line": source[:match.start()].count("\n") + 1,
                "is_from_import": match.group(1) is not None,
                "file": rel_path,
            })

        return {
            "file": rel_path,
            "findings": regex_findings,
            "imports": imports,
            "future_imports": [],
            "metrics": {"lines": len(lines), "functions": 0, "classes": 0},
            "encoding_declaration": encoding,
            "shebang": shebang,
            "parse_success": False,
            "error": "SyntaxError — Python 2-only syntax detected (expected for Py2 code)",
        }


# ── Codebase Walking ─────────────────────────────────────────────────────────

def should_exclude(filepath: str, exclude_patterns: List[str]) -> bool:
    """Check if a file should be excluded based on glob patterns."""
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(filepath, pattern):
            return True
    return False


def walk_codebase(root: str, exclude_patterns: List[str]) -> List[str]:
    """Walk the codebase and return all Python file paths."""
    py_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden directories and common non-source directories
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in (
            "__pycache__", "node_modules", ".git", ".hg", ".svn",
            ".tox", ".eggs", "*.egg-info",
        )]
        for fname in filenames:
            if fname.endswith(".py"):
                fullpath = os.path.join(dirpath, fname)
                relpath = os.path.relpath(fullpath, root)
                if not should_exclude(relpath, exclude_patterns):
                    py_files.append(fullpath)
    return sorted(py_files)


# ── Version Compatibility Matrix ─────────────────────────────────────────────

def build_version_matrix(
    all_results: List[Dict], target_versions: List[str]
) -> Dict[str, Any]:
    """Build a compatibility matrix for each target Python version."""
    matrix = {}
    for version in target_versions:
        issues = []
        for result in all_results:
            for finding in result.get("findings", []):
                if finding["pattern"] == "removed_stdlib":
                    removed_in = finding.get("removed_in", "")
                    # Issue applies if the module is removed in this version or earlier
                    if removed_in and _version_le(removed_in, version):
                        issues.append({
                            "file": finding["file"],
                            "line": finding["line"],
                            "module": finding.get("module", ""),
                            "removed_in": removed_in,
                        })
        matrix[version] = {
            "removed_module_usages": len(issues),
            "affected_files": len(set(i["file"] for i in issues)),
            "details": issues,
        }
    return matrix


def _version_le(v1: str, v2: str) -> bool:
    """Check if version v1 <= v2."""
    parts1 = tuple(int(x) for x in v1.split("."))
    parts2 = tuple(int(x) for x in v2.split("."))
    return parts1 <= parts2


# ── Risk Scoring ─────────────────────────────────────────────────────────────

RISK_WEIGHTS = {
    "none": 0,
    "low": 1,
    "medium": 3,
    "high": 5,
}


def compute_risk_score(result: Dict) -> Dict[str, Any]:
    """Compute a composite risk score for a single file."""
    findings = result.get("findings", [])
    metrics = result.get("metrics", {})
    loc = max(metrics.get("lines", 1), 1)

    # Pattern density
    total_issues = len(findings)
    density = total_issues / (loc / 100)

    # Semantic ratio
    semantic_count = sum(1 for f in findings if f.get("category", "").startswith("semantic_"))
    semantic_ratio = semantic_count / max(total_issues, 1)

    # Data layer exposure
    data_layer_count = sum(1 for f in findings if f.get("category") == "data_layer")

    # Weighted risk
    weighted_risk = sum(RISK_WEIGHTS.get(f.get("risk", "low"), 1) for f in findings)

    # Composite score (0-100)
    score = min(100, int(
        (density * 2) +
        (semantic_ratio * 20) +
        (data_layer_count * 10) +
        (weighted_risk / max(loc / 100, 1))
    ))

    # Rating
    if score < 15:
        rating = "low"
    elif score < 35:
        rating = "medium"
    elif score < 60:
        rating = "high"
    else:
        rating = "critical"

    return {
        "score": score,
        "rating": rating,
        "total_issues": total_issues,
        "semantic_issues": semantic_count,
        "data_layer_issues": data_layer_count,
        "density_per_100_loc": round(density, 2),
        "weighted_risk": weighted_risk,
    }


# ── Summary Statistics ───────────────────────────────────────────────────────

def compute_summary(all_results: List[Dict]) -> Dict[str, Any]:
    """Compute aggregate statistics across all files."""
    total_files = len(all_results)
    total_lines = sum(r.get("metrics", {}).get("lines", 0) for r in all_results)
    total_functions = sum(r.get("metrics", {}).get("functions", 0) for r in all_results)
    total_classes = sum(r.get("metrics", {}).get("classes", 0) for r in all_results)
    parse_failures = sum(1 for r in all_results if not r.get("parse_success", True))

    all_findings = []
    for r in all_results:
        all_findings.extend(r.get("findings", []))

    # Categorize findings
    by_category = defaultdict(list)
    by_risk = defaultdict(list)
    by_pattern = defaultdict(list)
    for f in all_findings:
        by_category[f.get("category", "unknown")].append(f)
        by_risk[f.get("risk", "unknown")].append(f)
        by_pattern[f.get("pattern", "unknown")].append(f)

    # Files with future imports already
    files_with_future = sum(1 for r in all_results if r.get("future_imports"))

    # Effort estimation
    syntax_only = sum(1 for f in all_findings if f.get("category") == "syntax")
    semantic = sum(1 for f in all_findings if f.get("category", "").startswith("semantic_"))
    data_layer = sum(1 for f in all_findings if f.get("category") == "data_layer")

    if total_lines < 5000 and data_layer < 10:
        effort = "small"
    elif total_lines < 25000 and data_layer < 50:
        effort = "medium"
    elif total_lines < 100000:
        effort = "large"
    else:
        effort = "very large"

    return {
        "total_files": total_files,
        "total_lines": total_lines,
        "total_functions": total_functions,
        "total_classes": total_classes,
        "parse_failures": parse_failures,
        "files_with_future_imports": files_with_future,
        "total_findings": len(all_findings),
        "findings_by_category": {k: len(v) for k, v in sorted(by_category.items())},
        "findings_by_risk": {k: len(v) for k, v in sorted(by_risk.items())},
        "findings_by_pattern": {k: len(v) for k, v in sorted(by_pattern.items(), key=lambda x: -len(x[1]))},
        "effort_estimate": effort,
        "syntax_only_count": syntax_only,
        "semantic_count": semantic,
        "data_layer_count": data_layer,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Analyze a Python 2 codebase for migration readiness"
    )
    parser.add_argument("codebase_path", help="Root directory of the Python 2 codebase")
    parser.add_argument("--output", "-o", required=True, help="Output directory for analysis results")
    parser.add_argument("--exclude", nargs="*", default=[], help="Glob patterns to exclude")
    parser.add_argument(
        "--target-versions", nargs="*", default=["3.9", "3.11", "3.12", "3.13"],
        help="Python 3 versions to check compatibility against"
    )
    args = parser.parse_args()

    codebase_path = os.path.abspath(args.codebase_path)
    output_dir = os.path.abspath(args.output)

    if not os.path.isdir(codebase_path):
        print(f"Error: {codebase_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    os.makedirs(output_dir, exist_ok=True)

    # Walk and analyze
    print(f"Scanning {codebase_path} ...")
    py_files = walk_codebase(codebase_path, args.exclude)
    print(f"Found {len(py_files)} Python files")

    all_results = []
    for i, filepath in enumerate(py_files, 1):
        if i % 50 == 0 or i == len(py_files):
            print(f"  Analyzing {i}/{len(py_files)}: {os.path.relpath(filepath, codebase_path)}")
        result = analyze_file(filepath, codebase_path)
        result["risk_assessment"] = compute_risk_score(result)
        all_results.append(result)

    # Compute summaries
    summary = compute_summary(all_results)
    version_matrix = build_version_matrix(all_results, args.target_versions)

    # Write outputs
    raw_scan_path = os.path.join(output_dir, "raw-scan.json")
    with open(raw_scan_path, "w") as f:
        json.dump({
            "codebase_root": codebase_path,
            "files_analyzed": len(all_results),
            "summary": summary,
            "results": all_results,
        }, f, indent=2, default=str)
    print(f"Wrote {raw_scan_path}")

    # Py2-ism inventory (flattened list of all findings)
    all_findings = []
    for r in all_results:
        all_findings.extend(r.get("findings", []))
    inventory_path = os.path.join(output_dir, "py2-ism-inventory.json")
    with open(inventory_path, "w") as f:
        json.dump({
            "total_findings": len(all_findings),
            "summary": summary["findings_by_category"],
            "findings": all_findings,
        }, f, indent=2, default=str)
    print(f"Wrote {inventory_path}")

    # Version matrix
    matrix_path = os.path.join(output_dir, "version-matrix.md")
    with open(matrix_path, "w") as f:
        f.write("# Python 3 Target Version Compatibility Matrix\n\n")
        f.write("| Target Version | Removed Module Usages | Affected Files | Incremental Cost |\n")
        f.write("|---|---|---|---|\n")
        prev_count = 0
        for ver in sorted(args.target_versions):
            data = version_matrix.get(ver, {})
            count = data.get("removed_module_usages", 0)
            files = data.get("affected_files", 0)
            incremental = count - prev_count
            f.write(f"| {ver} | {count} | {files} | +{incremental} |\n")
            prev_count = count
        f.write("\n## Details\n\n")
        for ver in sorted(args.target_versions):
            data = version_matrix.get(ver, {})
            details = data.get("details", [])
            if details:
                f.write(f"### Python {ver}\n\n")
                modules_affected = defaultdict(list)
                for d in details:
                    modules_affected[d["module"]].append(f"{d['file']}:{d['line']}")
                for mod, locations in sorted(modules_affected.items()):
                    f.write(f"- **{mod}** (removed in {REMOVED_STDLIB.get(mod, '?')}): {len(locations)} usages\n")
                    for loc in locations[:5]:
                        f.write(f"  - `{loc}`\n")
                    if len(locations) > 5:
                        f.write(f"  - ... and {len(locations) - 5} more\n")
                f.write("\n")
    print(f"Wrote {matrix_path}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"ANALYSIS COMPLETE")
    print(f"{'='*60}")
    print(f"Files analyzed:        {summary['total_files']}")
    print(f"Total lines of code:   {summary['total_lines']}")
    print(f"Parse failures (Py2):  {summary['parse_failures']}")
    print(f"Total Py2 patterns:    {summary['total_findings']}")
    print(f"  Syntax-only:         {summary['syntax_only_count']}")
    print(f"  Semantic:            {summary['semantic_count']}")
    print(f"  Data layer:          {summary['data_layer_count']}")
    print(f"Effort estimate:       {summary['effort_estimate']}")
    print(f"Files with __future__: {summary['files_with_future_imports']}")
    print(f"\nOutputs written to: {output_dir}")


if __name__ == "__main__":
    main()
