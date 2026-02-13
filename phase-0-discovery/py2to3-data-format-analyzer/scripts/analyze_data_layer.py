#!/usr/bin/env python3
"""
Data Format Analyzer — Main Analysis Script

Walks a Python 2 codebase and identifies every data-layer pattern relevant to
a Python 2→3 migration: file I/O, network I/O, binary protocol handling,
encoding/decoding operations, serialization, database connections, and
hardcoded byte constants.

Produces four JSON output files:
  - data-layer-report.json   — complete inventory of all findings
  - encoding-map.json        — encoding-specific operations only
  - serialization-inventory.json — serialization operations only
  - bytes-str-boundaries.json   — bytes↔text transition points

Usage:
    python3 analyze_data_layer.py <codebase_path> \
        --output <output_dir> \
        [--exclude "**/vendor/**"] \
        [--sample-data <sample_data_dir>]
"""

import ast
import argparse
import json
import os
import re
import sys
import fnmatch
from pathlib import Path
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple, Set


# ═══════════════════════════════════════════════════════════════════════════
# Pattern Definitions
# ═══════════════════════════════════════════════════════════════════════════

# ── File I/O ───────────────────────────────────────────────────────────────

FILE_IO_PATTERNS = {
    "open_no_encoding": {
        "description": "open() without explicit encoding or binary mode",
        "risk": "high",
        "boundary": "ambiguous",
        "direction": "ingestion",
    },
    "open_text_no_encoding": {
        "description": "open() in text mode ('r'/'w') without encoding parameter",
        "risk": "medium",
        "boundary": "ambiguous",
        "direction": "ingestion",
    },
    "open_binary": {
        "description": "open() in binary mode ('rb'/'wb')",
        "risk": "low",
        "boundary": "bytes_only",
        "direction": "ingestion",
    },
    "open_with_encoding": {
        "description": "open() with explicit encoding",
        "risk": "low",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "codecs_open": {
        "description": "codecs.open() — Py2 explicit encoding pattern",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "io_open": {
        "description": "io.open() — forward-compatible file open",
        "risk": "low",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "file_builtin": {
        "description": "file() builtin — removed in Python 3",
        "risk": "high",
        "boundary": "ambiguous",
        "direction": "ingestion",
    },
}

# ── Network / Serial I/O ──────────────────────────────────────────────────

NETWORK_PATTERNS = {
    "socket_recv": {
        "description": "socket.recv() — returns bytes in Py3",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "socket_send": {
        "description": "socket.send/sendall() — requires bytes in Py3",
        "risk": "high",
        "boundary": "text_to_bytes",
        "direction": "egression",
    },
    "serial_read": {
        "description": "serial port read — returns bytes",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "serial_write": {
        "description": "serial port write — requires bytes in Py3",
        "risk": "high",
        "boundary": "text_to_bytes",
        "direction": "egression",
    },
    "urllib_urlopen": {
        "description": "urllib/urllib2 urlopen — response is bytes in Py3",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "http_response_read": {
        "description": "HTTP response .read() — returns bytes in Py3",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
}

# ── Binary Protocol ────────────────────────────────────────────────────────

BINARY_PATTERNS = {
    "struct_pack": {
        "description": "struct.pack() — binary packing",
        "risk": "low",
        "boundary": "bytes_only",
        "direction": "internal",
    },
    "struct_unpack": {
        "description": "struct.unpack() — binary unpacking, check downstream usage",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
    "struct_calcsize": {
        "description": "struct.calcsize() — format string calculation",
        "risk": "low",
        "boundary": "bytes_only",
        "direction": "internal",
    },
    "ctypes_usage": {
        "description": "ctypes data types — C-level byte handling",
        "risk": "medium",
        "boundary": "bytes_only",
        "direction": "internal",
    },
    "byte_indexing": {
        "description": "Indexing into data with [i] — returns int in Py3, char in Py2",
        "risk": "high",
        "boundary": "ambiguous",
        "direction": "internal",
    },
    "modbus_library": {
        "description": "Modbus library usage (pymodbus, minimalmodbus, etc.)",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "opcua_library": {
        "description": "OPC-UA library usage",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "dnp3_library": {
        "description": "DNP3 library usage",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
}

# ── Encoding / Decoding ───────────────────────────────────────────────────

ENCODING_PATTERNS = {
    "str_encode": {
        "description": ".encode() call — text to bytes",
        "risk": "medium",
        "boundary": "text_to_bytes",
        "direction": "internal",
    },
    "str_decode": {
        "description": ".decode() call — bytes to text",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
    "ebcdic_codec": {
        "description": "EBCDIC codec usage (cp500, cp1047, cp037, etc.)",
        "risk": "critical",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
    "codecs_module": {
        "description": "codecs module function call",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
    "unicode_call": {
        "description": "unicode() builtin — becomes str() in Py3",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
    "encoding_declaration": {
        "description": "File encoding declaration (# -*- coding: ...)",
        "risk": "low",
        "boundary": "text_only",
        "direction": "internal",
    },
    "bom_marker": {
        "description": "BOM (Byte Order Mark) handling",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
}

# ── Serialization ─────────────────────────────────────────────────────────

SERIALIZATION_PATTERNS = {
    "pickle_dump": {
        "description": "pickle.dump() — writes serialized data",
        "risk": "high",
        "boundary": "text_to_bytes",
        "direction": "egression",
    },
    "pickle_load": {
        "description": "pickle.load() — Py2 str becomes Py3 bytes on deserialize",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "pickle_dumps_loads": {
        "description": "pickle.dumps()/loads() — in-memory serialization",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
    "cpickle_import": {
        "description": "cPickle import — must become pickle in Py3",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
    "marshal_usage": {
        "description": "marshal.dump()/load() — version-specific, extremely fragile",
        "risk": "critical",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
    "shelve_usage": {
        "description": "shelve.open() — uses pickle internally",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "json_usage": {
        "description": "json.dump()/load()/dumps()/loads()",
        "risk": "low",
        "boundary": "text_only",
        "direction": "internal",
    },
    "yaml_usage": {
        "description": "yaml.dump()/load()/safe_load()",
        "risk": "low",
        "boundary": "text_only",
        "direction": "internal",
    },
    "xml_parse": {
        "description": "XML parsing (ElementTree, minidom, lxml, etc.)",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "msgpack_usage": {
        "description": "msgpack pack/unpack — binary serialization",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
    "custom_getstate": {
        "description": "__getstate__/__setstate__ — custom pickle protocol",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
    "custom_reduce": {
        "description": "__reduce__/__reduce_ex__ — custom pickle protocol",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "internal",
    },
}

# ── Database ───────────────────────────────────────────────────────────────

DATABASE_PATTERNS = {
    "sqlite3_connect": {
        "description": "sqlite3.connect() — check text_factory setting",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "mysqldb_connect": {
        "description": "MySQLdb connection — check charset parameter",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "psycopg2_connect": {
        "description": "psycopg2 connection — check client_encoding",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "cx_oracle_connect": {
        "description": "cx_Oracle connection — check NLS_LANG / encoding",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "pyodbc_connect": {
        "description": "pyodbc connection — check encoding in connection string",
        "risk": "medium",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
    "pymongo_connect": {
        "description": "pymongo connection",
        "risk": "low",
        "boundary": "text_only",
        "direction": "ingestion",
    },
    "dbf_usage": {
        "description": "DBF file handling (dbfread, dbf, etc.)",
        "risk": "high",
        "boundary": "bytes_to_text",
        "direction": "ingestion",
    },
}

# ── Hardcoded Byte Constants ──────────────────────────────────────────────

CONSTANT_PATTERNS = {
    "hex_escape_in_string": {
        "description": "Hex escape (\\xNN) in string literal — may be byte constant",
        "risk": "high",
        "boundary": "ambiguous",
        "direction": "internal",
    },
    "ebcdic_byte_range": {
        "description": "Byte constant in EBCDIC character range",
        "risk": "critical",
        "boundary": "bytes_only",
        "direction": "internal",
    },
    "null_byte": {
        "description": "Null byte (\\x00) — common delimiter/padding in binary protocols",
        "risk": "medium",
        "boundary": "bytes_only",
        "direction": "internal",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# AST-Based Detection
# ═══════════════════════════════════════════════════════════════════════════

class DataLayerVisitor(ast.NodeVisitor):
    """AST visitor that detects data-layer patterns in parsed Python code."""

    def __init__(self, filepath: str, source_lines: List[str]):
        self.filepath = filepath
        self.source_lines = source_lines
        self.findings: List[Dict[str, Any]] = []
        # Track imports so we can resolve module.function() calls
        self.imports: Dict[str, str] = {}  # alias → module

    def _add_finding(
        self,
        line: int,
        category: str,
        pattern: str,
        snippet: str,
        extra: Optional[Dict[str, Any]] = None,
    ):
        # Look up pattern metadata from the pattern dicts
        all_patterns = {
            **FILE_IO_PATTERNS,
            **NETWORK_PATTERNS,
            **BINARY_PATTERNS,
            **ENCODING_PATTERNS,
            **SERIALIZATION_PATTERNS,
            **DATABASE_PATTERNS,
            **CONSTANT_PATTERNS,
        }
        meta = all_patterns.get(pattern, {})

        finding = {
            "file": self.filepath,
            "line": line,
            "category": category,
            "pattern": pattern,
            "description": meta.get("description", pattern),
            "risk": meta.get("risk", "medium"),
            "boundary": meta.get("boundary", "ambiguous"),
            "direction": meta.get("direction", "internal"),
            "snippet": snippet.strip()[:200],
        }
        if extra:
            finding.update(extra)
        self.findings.append(finding)

    def _get_line_snippet(self, node: ast.AST) -> str:
        lineno = getattr(node, "lineno", 0)
        if 0 < lineno <= len(self.source_lines):
            return self.source_lines[lineno - 1]
        return ""

    # ── Import Tracking ────────────────────────────────────────────────

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.asname or alias.name
            self.imports[name] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            local_name = alias.asname or alias.name
            full = f"{module}.{alias.name}" if module else alias.name
            self.imports[local_name] = full

            # Detect specific imports
            if full in ("cPickle", "cPickle.dumps", "cPickle.loads"):
                self._add_finding(
                    node.lineno, "serialization", "cpickle_import",
                    self._get_line_snippet(node),
                )
            if module in ("pymodbus", "pymodbus.client", "minimalmodbus",
                          "modbus_tk", "umodbus"):
                self._add_finding(
                    node.lineno, "binary_protocol", "modbus_library",
                    self._get_line_snippet(node),
                )
            if module and ("opcua" in module or "opcua" in alias.name):
                self._add_finding(
                    node.lineno, "binary_protocol", "opcua_library",
                    self._get_line_snippet(node),
                )
            if module and ("dnp3" in module or "pydnp3" in module):
                self._add_finding(
                    node.lineno, "binary_protocol", "dnp3_library",
                    self._get_line_snippet(node),
                )
        self.generic_visit(node)

    # ── Call Detection ─────────────────────────────────────────────────

    def visit_Call(self, node: ast.Call):
        func_name = self._resolve_call_name(node)
        snippet = self._get_line_snippet(node)
        line = node.lineno

        # ── File I/O ──
        if func_name in ("open", "builtins.open"):
            self._analyze_open_call(node, snippet)
        elif func_name in ("codecs.open",):
            self._add_finding(line, "file_io", "codecs_open", snippet)
        elif func_name in ("io.open",):
            self._add_finding(line, "file_io", "io_open", snippet)
        elif func_name == "file":
            self._add_finding(line, "file_io", "file_builtin", snippet)

        # ── Network I/O ──
        elif func_name.endswith(".recv") or func_name.endswith(".recv_into"):
            self._add_finding(line, "network_io", "socket_recv", snippet)
        elif func_name.endswith((".send", ".sendall")):
            if "socket" in func_name or "sock" in snippet.lower():
                self._add_finding(line, "network_io", "socket_send", snippet)
        elif func_name.endswith((".read",)) and self._looks_like_serial(node):
            self._add_finding(line, "network_io", "serial_read", snippet)
        elif func_name.endswith((".write",)) and self._looks_like_serial(node):
            self._add_finding(line, "network_io", "serial_write", snippet)
        elif func_name in ("urllib.urlopen", "urllib2.urlopen", "urllib.request.urlopen"):
            self._add_finding(line, "network_io", "urllib_urlopen", snippet)

        # ── Struct ──
        elif func_name in ("struct.pack", "struct.pack_into"):
            fmt = self._extract_format_string(node)
            self._add_finding(
                line, "binary_protocol", "struct_pack", snippet,
                {"format_string": fmt},
            )
        elif func_name in ("struct.unpack", "struct.unpack_from"):
            fmt = self._extract_format_string(node)
            self._add_finding(
                line, "binary_protocol", "struct_unpack", snippet,
                {"format_string": fmt},
            )
        elif func_name == "struct.calcsize":
            self._add_finding(line, "binary_protocol", "struct_calcsize", snippet)

        # ── Encoding/Decoding ──
        elif func_name.endswith(".encode"):
            codec = self._extract_codec_arg(node)
            self._check_ebcdic(line, snippet, codec, "str_encode")
            self._add_finding(
                line, "encoding", "str_encode", snippet,
                {"codec": codec},
            )
        elif func_name.endswith(".decode"):
            codec = self._extract_codec_arg(node)
            self._check_ebcdic(line, snippet, codec, "str_decode")
            self._add_finding(
                line, "encoding", "str_decode", snippet,
                {"codec": codec},
            )
        elif func_name.startswith("codecs.") and func_name != "codecs.open":
            self._add_finding(line, "encoding", "codecs_module", snippet)
        elif func_name in ("unicode",):
            self._add_finding(line, "encoding", "unicode_call", snippet)

        # ── Serialization ──
        elif func_name in ("pickle.dump", "cPickle.dump"):
            self._add_finding(line, "serialization", "pickle_dump", snippet)
        elif func_name in ("pickle.load", "cPickle.load"):
            self._add_finding(line, "serialization", "pickle_load", snippet)
        elif func_name in ("pickle.dumps", "pickle.loads",
                           "cPickle.dumps", "cPickle.loads"):
            self._add_finding(line, "serialization", "pickle_dumps_loads", snippet)
        elif func_name in ("marshal.dump", "marshal.dumps",
                           "marshal.load", "marshal.loads"):
            self._add_finding(line, "serialization", "marshal_usage", snippet)
        elif func_name in ("shelve.open",):
            self._add_finding(line, "serialization", "shelve_usage", snippet)
        elif func_name in ("json.dump", "json.dumps", "json.load", "json.loads"):
            self._add_finding(line, "serialization", "json_usage", snippet)
        elif func_name in ("yaml.dump", "yaml.load", "yaml.safe_load",
                           "yaml.safe_dump", "yaml.dump_all", "yaml.load_all"):
            self._add_finding(line, "serialization", "yaml_usage", snippet)
        elif func_name in ("msgpack.pack", "msgpack.unpack",
                           "msgpack.packb", "msgpack.unpackb"):
            self._add_finding(line, "serialization", "msgpack_usage", snippet)

        # ── Database ──
        elif func_name in ("sqlite3.connect",):
            self._add_finding(line, "database", "sqlite3_connect", snippet)
        elif func_name in ("MySQLdb.connect", "mysql.connector.connect"):
            self._add_finding(line, "database", "mysqldb_connect", snippet)
        elif func_name in ("psycopg2.connect",):
            self._add_finding(line, "database", "psycopg2_connect", snippet)
        elif func_name in ("cx_Oracle.connect",):
            self._add_finding(line, "database", "cx_oracle_connect", snippet)
        elif func_name in ("pyodbc.connect",):
            self._add_finding(line, "database", "pyodbc_connect", snippet)
        elif func_name in ("pymongo.MongoClient",):
            self._add_finding(line, "database", "pymongo_connect", snippet)

        # ── XML ──
        elif func_name in ("ET.parse", "ET.fromstring", "ElementTree.parse",
                           "etree.parse", "etree.fromstring",
                           "minidom.parse", "minidom.parseString",
                           "lxml.etree.parse", "lxml.etree.fromstring"):
            self._add_finding(line, "serialization", "xml_parse", snippet)

        self.generic_visit(node)

    # ── Function/Method Definitions ────────────────────────────────────

    def visit_FunctionDef(self, node: ast.FunctionDef):
        snippet = self._get_line_snippet(node)
        if node.name in ("__getstate__", "__setstate__"):
            self._add_finding(
                node.lineno, "serialization", "custom_getstate", snippet,
            )
        elif node.name in ("__reduce__", "__reduce_ex__"):
            self._add_finding(
                node.lineno, "serialization", "custom_reduce", snippet,
            )
        self.generic_visit(node)

    # ── Helpers ────────────────────────────────────────────────────────

    def _resolve_call_name(self, node: ast.Call) -> str:
        """Best-effort resolution of the function being called."""
        func = node.func
        if isinstance(func, ast.Name):
            resolved = self.imports.get(func.id, func.id)
            return resolved
        elif isinstance(func, ast.Attribute):
            # obj.method
            if isinstance(func.value, ast.Name):
                obj_name = func.value.id
                resolved_obj = self.imports.get(obj_name, obj_name)
                return f"{resolved_obj}.{func.attr}"
            elif isinstance(func.value, ast.Attribute):
                # obj.sub.method — flatten to best effort
                parts = []
                node_inner = func.value
                while isinstance(node_inner, ast.Attribute):
                    parts.append(node_inner.attr)
                    node_inner = node_inner.value
                if isinstance(node_inner, ast.Name):
                    parts.append(node_inner.id)
                parts.reverse()
                parts.append(func.attr)
                return ".".join(parts)
            return f"?.{func.attr}"
        return "?"

    def _analyze_open_call(self, node: ast.Call, snippet: str):
        """Classify an open() call by its mode and encoding arguments."""
        mode = None
        has_encoding = False

        # Check positional args
        if len(node.args) >= 2:
            mode_arg = node.args[1]
            if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
                mode = mode_arg.value

        # Check keyword args
        for kw in node.keywords:
            if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                mode = kw.value.value
            if kw.arg == "encoding":
                has_encoding = True

        if mode and "b" in mode:
            self._add_finding(node.lineno, "file_io", "open_binary", snippet)
        elif has_encoding:
            self._add_finding(node.lineno, "file_io", "open_with_encoding", snippet)
        elif mode:
            self._add_finding(
                node.lineno, "file_io", "open_text_no_encoding", snippet,
            )
        else:
            self._add_finding(
                node.lineno, "file_io", "open_no_encoding", snippet,
            )

    def _looks_like_serial(self, node: ast.Call) -> bool:
        """Heuristic: does this .read()/.write() call look like serial port I/O?"""
        snippet = self._get_line_snippet(node).lower()
        return any(
            kw in snippet
            for kw in ("serial", "ser.", "port.", "com", "tty", "/dev/tty")
        )

    def _extract_format_string(self, node: ast.Call) -> Optional[str]:
        """Extract the format string from a struct.pack/unpack call."""
        if node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return first.value
        return None

    def _extract_codec_arg(self, node: ast.Call) -> Optional[str]:
        """Extract the codec name from an .encode()/.decode() call."""
        if node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                return first.value
        for kw in node.keywords:
            if kw.arg == "encoding" and isinstance(kw.value, ast.Constant):
                return kw.value.value
        return None

    def _check_ebcdic(
        self, line: int, snippet: str, codec: Optional[str], base_pattern: str
    ):
        """If the codec is EBCDIC, add a separate critical finding."""
        if codec and any(
            eb in codec.lower()
            for eb in ("cp500", "cp1047", "cp037", "cp273", "cp1140", "ebcdic")
        ):
            self._add_finding(line, "encoding", "ebcdic_codec", snippet, {"codec": codec})


# ═══════════════════════════════════════════════════════════════════════════
# Regex-Based Detection (fallback + supplements AST)
# ═══════════════════════════════════════════════════════════════════════════

REGEX_RULES: List[Dict[str, Any]] = [
    # ── Encoding declarations ──
    {
        "pattern": r"^#\s*-\*-\s*coding:\s*(\S+)",
        "category": "encoding",
        "name": "encoding_declaration",
        "group": 1,  # capture the codec name
    },
    # BOM markers
    {
        "pattern": r"\\xef\\xbb\\xbf|\\xfe\\xff|\\xff\\xfe|codecs\.BOM",
        "category": "encoding",
        "name": "bom_marker",
    },
    # Hex escape sequences in strings (potential hardcoded byte constants)
    {
        "pattern": r"""(?:['"])(?:[^'"]*\\x[0-9a-fA-F]{2}[^'"]*)+(?:['"])""",
        "category": "constants",
        "name": "hex_escape_in_string",
    },
    # EBCDIC byte ranges: uppercase A-I = \xC1-\xC9, digits 0-9 = \xF0-\xF9
    {
        "pattern": r"\\x[cC][1-9]|\\x[fF][0-9]",
        "category": "constants",
        "name": "ebcdic_byte_range",
    },
    # Null bytes
    {
        "pattern": r"\\x00",
        "category": "constants",
        "name": "null_byte",
    },
    # DBF file handling
    {
        "pattern": r"(?:import|from)\s+(?:dbfread|dbf|dbfpy)",
        "category": "database",
        "name": "dbf_usage",
    },
    # file() builtin (regex fallback for Py2 syntax)
    {
        "pattern": r"\bfile\s*\(",
        "category": "file_io",
        "name": "file_builtin",
    },
    # ctypes usage
    {
        "pattern": r"ctypes\.(?:c_char|c_byte|c_ubyte|c_char_p|c_wchar_p|Structure|Union|POINTER)",
        "category": "binary_protocol",
        "name": "ctypes_usage",
    },
    # ── Regex fallbacks for Py2 files that fail AST parsing ──
    # These ensure data-layer patterns are still detected in files with Py2-only syntax.

    # struct.pack / struct.unpack
    {
        "pattern": r"struct\.pack\s*\(",
        "category": "binary_protocol",
        "name": "struct_pack",
    },
    {
        "pattern": r"struct\.unpack\s*\(",
        "category": "binary_protocol",
        "name": "struct_unpack",
    },
    # socket.recv / socket.send
    {
        "pattern": r"\.recv\s*\(",
        "category": "network_io",
        "name": "socket_recv",
    },
    {
        "pattern": r"\.send(?:all)?\s*\(",
        "category": "network_io",
        "name": "socket_send",
    },
    # serial port I/O
    {
        "pattern": r"(?:serial|ser|port)\.\s*(?:read|readline)\s*\(",
        "category": "network_io",
        "name": "serial_read",
    },
    {
        "pattern": r"(?:serial|ser|port)\.\s*write\s*\(",
        "category": "network_io",
        "name": "serial_write",
    },
    # pickle / cPickle
    {
        "pattern": r"(?:c?[Pp]ickle)\.dump\s*\(",
        "category": "serialization",
        "name": "pickle_dump",
    },
    {
        "pattern": r"(?:c?[Pp]ickle)\.load\s*\(",
        "category": "serialization",
        "name": "pickle_load",
    },
    {
        "pattern": r"(?:c?[Pp]ickle)\.(?:dumps|loads)\s*\(",
        "category": "serialization",
        "name": "pickle_dumps_loads",
    },
    {
        "pattern": r"(?:import|from)\s+cPickle",
        "category": "serialization",
        "name": "cpickle_import",
    },
    # marshal
    {
        "pattern": r"marshal\.(?:dump|load|dumps|loads)\s*\(",
        "category": "serialization",
        "name": "marshal_usage",
    },
    # shelve
    {
        "pattern": r"shelve\.open\s*\(",
        "category": "serialization",
        "name": "shelve_usage",
    },
    # open() without encoding (basic regex fallback)
    {
        "pattern": r"(?<!\w)open\s*\([^)]*\)\s*$",
        "category": "file_io",
        "name": "open_no_encoding",
    },
    # .encode() / .decode()
    {
        "pattern": r"\.encode\s*\(",
        "category": "encoding",
        "name": "str_encode",
    },
    {
        "pattern": r"\.decode\s*\(",
        "category": "encoding",
        "name": "str_decode",
    },
    # EBCDIC codecs in strings
    {
        "pattern": r"(?:cp500|cp1047|cp037|cp273|cp1140|ebcdic)",
        "category": "encoding",
        "name": "ebcdic_codec",
    },
    # Database connections
    {
        "pattern": r"sqlite3\.connect\s*\(",
        "category": "database",
        "name": "sqlite3_connect",
    },
    {
        "pattern": r"(?:MySQLdb|mysql\.connector)\.connect\s*\(",
        "category": "database",
        "name": "mysqldb_connect",
    },
    {
        "pattern": r"psycopg2\.connect\s*\(",
        "category": "database",
        "name": "psycopg2_connect",
    },
    {
        "pattern": r"cx_Oracle\.connect\s*\(",
        "category": "database",
        "name": "cx_oracle_connect",
    },
    # Modbus / SCADA library imports
    {
        "pattern": r"(?:import|from)\s+(?:pymodbus|minimalmodbus|modbus_tk|umodbus)",
        "category": "binary_protocol",
        "name": "modbus_library",
    },
    {
        "pattern": r"(?:import|from)\s+(?:opcua|asyncua)",
        "category": "binary_protocol",
        "name": "opcua_library",
    },
    {
        "pattern": r"(?:import|from)\s+(?:pydnp3|dnp3)",
        "category": "binary_protocol",
        "name": "dnp3_library",
    },
]


def regex_scan(filepath: str, source: str) -> List[Dict[str, Any]]:
    """Scan source code with regex patterns as a supplement to AST detection."""
    findings = []
    lines = source.splitlines()

    all_patterns = {
        **FILE_IO_PATTERNS,
        **NETWORK_PATTERNS,
        **BINARY_PATTERNS,
        **ENCODING_PATTERNS,
        **SERIALIZATION_PATTERNS,
        **DATABASE_PATTERNS,
        **CONSTANT_PATTERNS,
    }

    for rule in REGEX_RULES:
        regex = re.compile(rule["pattern"])
        for i, line_text in enumerate(lines, start=1):
            if regex.search(line_text):
                name = rule["name"]
                meta = all_patterns.get(name, {})
                extra = {}
                # Extract codec from encoding declaration
                if rule.get("group"):
                    m = regex.search(line_text)
                    if m:
                        extra["codec"] = m.group(rule["group"])

                findings.append({
                    "file": filepath,
                    "line": i,
                    "category": rule["category"],
                    "pattern": name,
                    "description": meta.get("description", name),
                    "risk": meta.get("risk", "medium"),
                    "boundary": meta.get("boundary", "ambiguous"),
                    "direction": meta.get("direction", "internal"),
                    "snippet": line_text.strip()[:200],
                    **extra,
                })
    return findings


# ═══════════════════════════════════════════════════════════════════════════
# Sample Data Analysis
# ═══════════════════════════════════════════════════════════════════════════

def analyze_sample_data(sample_dir: str) -> List[Dict[str, Any]]:
    """Detect encoding of sample data files using heuristics."""
    findings = []
    if not sample_dir or not os.path.isdir(sample_dir):
        return findings

    for root, _dirs, files in os.walk(sample_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "rb") as f:
                    header = f.read(4096)
            except (IOError, OSError):
                continue

            relpath = os.path.relpath(fpath, sample_dir)

            # Check for BOM
            if header[:3] == b"\xef\xbb\xbf":
                findings.append({
                    "file": relpath,
                    "type": "sample_data",
                    "detected_encoding": "utf-8-sig",
                    "confidence": "high",
                })
            elif header[:2] in (b"\xff\xfe", b"\xfe\xff"):
                findings.append({
                    "file": relpath,
                    "type": "sample_data",
                    "detected_encoding": "utf-16",
                    "confidence": "high",
                })

            # EBCDIC heuristic: high concentration of bytes in 0x40-0xF9 range
            # (EBCDIC space is 0x40, printable chars are mostly 0x40-0xF9)
            if len(header) > 100:
                ebcdic_range_count = sum(
                    1 for b in header if 0x40 <= b <= 0xF9
                )
                ratio = ebcdic_range_count / len(header)
                if ratio > 0.85:
                    findings.append({
                        "file": relpath,
                        "type": "sample_data",
                        "detected_encoding": "ebcdic (probable cp500/cp1047)",
                        "confidence": "medium",
                        "ebcdic_byte_ratio": round(ratio, 3),
                    })

            # Binary heuristic: high-byte content
            if len(header) > 100:
                non_printable = sum(
                    1 for b in header
                    if b < 0x20 and b not in (0x09, 0x0A, 0x0D)
                )
                ratio = non_printable / len(header)
                if ratio > 0.1:
                    findings.append({
                        "file": relpath,
                        "type": "sample_data",
                        "detected_encoding": "binary",
                        "confidence": "high" if ratio > 0.3 else "medium",
                        "non_printable_ratio": round(ratio, 3),
                    })

    return findings


# ═══════════════════════════════════════════════════════════════════════════
# Main Analysis Pipeline
# ═══════════════════════════════════════════════════════════════════════════

def should_exclude(filepath: str, exclude_patterns: List[str]) -> bool:
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(filepath, pattern):
            return True
    return False


def analyze_file(filepath: str, relpath: str) -> List[Dict[str, Any]]:
    """Analyze a single Python file with AST + regex."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
    except (IOError, OSError) as e:
        return [{
            "file": relpath,
            "line": 0,
            "category": "error",
            "pattern": "read_error",
            "description": f"Could not read file: {e}",
            "risk": "medium",
            "boundary": "ambiguous",
            "direction": "internal",
            "snippet": "",
        }]

    source_lines = source.splitlines()
    findings = []

    # AST pass
    try:
        tree = ast.parse(source, filename=relpath)
        visitor = DataLayerVisitor(relpath, source_lines)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    except SyntaxError:
        # Py2-only syntax — fall through to regex only
        pass

    # Regex pass (supplements AST, catches what AST misses)
    regex_findings = regex_scan(relpath, source)

    # Deduplicate: don't add regex finding if AST already caught same line+pattern
    existing = {(f["line"], f["pattern"]) for f in findings}
    for rf in regex_findings:
        if (rf["line"], rf["pattern"]) not in existing:
            findings.append(rf)

    return findings


def run_analysis(
    codebase_path: str,
    output_dir: str,
    exclude_patterns: List[str],
    sample_data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Run the full data layer analysis."""
    codebase = Path(codebase_path).resolve()
    outdir = Path(output_dir)
    outdir.mkdir(parents=True, exist_ok=True)

    all_findings: List[Dict[str, Any]] = []
    files_scanned = 0
    files_with_findings = 0

    for root, dirs, files in os.walk(codebase):
        # Skip hidden directories and common non-source dirs
        dirs[:] = [
            d for d in dirs
            if not d.startswith(".") and d not in ("__pycache__", "node_modules", ".git")
        ]

        for fname in files:
            if not fname.endswith(".py"):
                continue

            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, codebase)

            if should_exclude(relpath, exclude_patterns):
                continue

            file_findings = analyze_file(fpath, relpath)
            files_scanned += 1
            if file_findings:
                files_with_findings += 1
                all_findings.extend(file_findings)

    # Sample data analysis
    sample_findings = []
    if sample_data_dir:
        sample_findings = analyze_sample_data(sample_data_dir)

    # ── Build output structures ──

    # Compute per-file summaries
    by_file: Dict[str, List[Dict]] = defaultdict(list)
    for f in all_findings:
        by_file[f["file"]].append(f)

    # Compute category summaries
    by_category: Dict[str, int] = defaultdict(int)
    by_risk: Dict[str, int] = defaultdict(int)
    by_boundary: Dict[str, int] = defaultdict(int)
    for f in all_findings:
        by_category[f["category"]] += 1
        by_risk[f["risk"]] += 1
        by_boundary[f["boundary"]] += 1

    # ── data-layer-report.json ──
    report = {
        "codebase_path": str(codebase),
        "files_scanned": files_scanned,
        "files_with_findings": files_with_findings,
        "total_findings": len(all_findings),
        "summary": {
            "by_category": dict(by_category),
            "by_risk": dict(by_risk),
            "by_boundary": dict(by_boundary),
        },
        "findings": all_findings,
        "sample_data_analysis": sample_findings,
    }
    with open(outdir / "data-layer-report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # ── encoding-map.json ──
    encoding_findings = [
        f for f in all_findings if f["category"] == "encoding"
    ]
    encoding_map = {
        "total": len(encoding_findings),
        "codecs_found": list({
            f.get("codec", "unknown")
            for f in encoding_findings
            if f.get("codec")
        }),
        "findings": encoding_findings,
    }
    with open(outdir / "encoding-map.json", "w", encoding="utf-8") as f:
        json.dump(encoding_map, f, indent=2, ensure_ascii=False)

    # ── serialization-inventory.json ──
    ser_findings = [
        f for f in all_findings if f["category"] == "serialization"
    ]
    serialization_inv = {
        "total": len(ser_findings),
        "formats_found": list({f["pattern"] for f in ser_findings}),
        "findings": ser_findings,
    }
    with open(outdir / "serialization-inventory.json", "w", encoding="utf-8") as f:
        json.dump(serialization_inv, f, indent=2, ensure_ascii=False)

    # ── bytes-str-boundaries.json ──
    boundary_findings = [
        f for f in all_findings
        if f["boundary"] in ("bytes_to_text", "text_to_bytes", "ambiguous")
    ]
    boundaries = {
        "total": len(boundary_findings),
        "by_type": {
            "bytes_to_text": len([
                f for f in boundary_findings if f["boundary"] == "bytes_to_text"
            ]),
            "text_to_bytes": len([
                f for f in boundary_findings if f["boundary"] == "text_to_bytes"
            ]),
            "ambiguous": len([
                f for f in boundary_findings if f["boundary"] == "ambiguous"
            ]),
        },
        "findings": boundary_findings,
    }
    with open(outdir / "bytes-str-boundaries.json", "w", encoding="utf-8") as f:
        json.dump(boundaries, f, indent=2, ensure_ascii=False)

    return report


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Analyze the data layer of a Python 2 codebase for migration risks."
    )
    parser.add_argument("codebase_path", help="Root directory of the Python 2 codebase")
    parser.add_argument("--output", required=True, help="Output directory for analysis results")
    parser.add_argument(
        "--exclude", nargs="*", default=[],
        help="Glob patterns for files/directories to exclude",
    )
    parser.add_argument(
        "--sample-data", default=None,
        help="Directory containing sample data files for encoding detection",
    )

    args = parser.parse_args()

    report = run_analysis(
        codebase_path=args.codebase_path,
        output_dir=args.output,
        exclude_patterns=args.exclude,
        sample_data_dir=args.sample_data,
    )

    summary = report["summary"]
    print(f"Data layer analysis complete: {args.output}")
    print(f"  Files scanned: {report['files_scanned']}")
    print(f"  Files with findings: {report['files_with_findings']}")
    print(f"  Total findings: {report['total_findings']}")
    print(f"  By risk: {summary['by_risk']}")
    print(f"  By boundary: {summary['by_boundary']}")
    print(f"\nOutputs:")
    print(f"  data-layer-report.json")
    print(f"  encoding-map.json")
    print(f"  serialization-inventory.json")
    print(f"  bytes-str-boundaries.json")


if __name__ == "__main__":
    main()
