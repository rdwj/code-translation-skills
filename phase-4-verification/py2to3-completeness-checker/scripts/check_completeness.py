#!/usr/bin/env python3
"""
Migration Completeness Checker

Scans the entire codebase for remaining Python 2 artifacts, incomplete conversions,
leftover compatibility shims, and unresolved migration debris. Produces a completeness
report with prioritized cleanup tasks.

Usage:
    python3 check_completeness.py <codebase_path> \
        --target-version 3.12 \
        [--state-file <migration-state.json>] \
        [--output <output_dir>] \
        [--modules <module1> <module2> ...] \
        [--strict]

Inputs:
    codebase_path             Root directory of the Python codebase
    --target-version          Target Python 3.x version (3.9, 3.11, 3.12, 3.13)
    --state-file              Path to migration-state.json (optional)
    --output                  Output directory (default: ./completeness-output)
    --modules                 Specific modules to check (default: all .py files)
    --lint-baseline           Path to lint-baseline.json from Skill 0.5 (optional)
    --strict                  Treat all WARNING findings as errors for gate check

Outputs:
    completeness-report.json  Every remaining artifact found, by category
    cleanup-tasks.json        Ordered list of remaining cleanup work
"""

import argparse
import ast
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ── Utility Functions ────────────────────────────────────────────────────────

def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file."""
    p = Path(path)
    if not p.exists():
        print(f"Warning: File not found: {path}", file=sys.stderr)
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: str) -> None:
    """Save data as JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Wrote {p}")


def read_file(path: str) -> str:
    """Read file content, trying UTF-8 then Latin-1 fallback."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            return f.read()


def discover_python_files(
    codebase_path: str,
    modules: Optional[List[str]] = None,
) -> List[str]:
    """Discover all Python files in the codebase."""
    root = Path(codebase_path)
    if modules:
        files = []
        for mod in modules:
            p = root / mod
            if p.is_file() and p.suffix == ".py":
                files.append(str(p))
            elif p.is_dir():
                files.extend(str(f) for f in p.rglob("*.py"))
        return sorted(files)

    # Discover all .py files, skip common non-source directories
    skip_dirs = {
        ".git", ".hg", ".svn", "__pycache__", ".tox", ".nox",
        "node_modules", ".eggs", "*.egg-info", "venv", ".venv",
        "env", ".env", "build", "dist",
    }
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Filter out skip directories
        dirnames[:] = [
            d for d in dirnames
            if d not in skip_dirs and not d.endswith(".egg-info")
        ]
        for fn in filenames:
            if fn.endswith(".py"):
                files.append(os.path.join(dirpath, fn))
    return sorted(files)


# ── Stdlib Removals by Version ───────────────────────────────────────────────

# Modules removed in each Python 3.x version
STDLIB_REMOVALS: Dict[str, List[str]] = {
    "3.0": [
        "commands", "compiler", "dircache", "fpformat", "htmllib",
        "ihooks", "mhlib", "new", "popen2", "rexec", "sets",
        "sha", "md5", "statvfs", "thread", "user",
    ],
    "3.2": ["cfmfile", "buildtools", "macostools"],
    "3.4": [],
    "3.8": ["macpath", "formatter", "parser"],
    "3.9": [],
    "3.10": [],
    "3.11": [],
    "3.12": [
        "distutils", "aifc", "audioop", "cgi", "cgitb", "chunk",
        "crypt", "imghdr", "mailcap", "msilib", "nis", "nntplib",
        "ossaudiodev", "pipes", "sndhdr", "spwd", "sunau",
        "telnetlib", "uu", "xdrlib",
    ],
    "3.13": [
        # Some finalized removals from 3.12 deprecation cycle
    ],
}


def get_removed_modules(target_version: str) -> Set[str]:
    """Get all modules removed at or before the target version."""
    removed = set()
    target_parts = tuple(int(x) for x in target_version.split("."))
    for ver_str, modules in STDLIB_REMOVALS.items():
        ver_parts = tuple(int(x) for x in ver_str.split("."))
        if ver_parts <= target_parts:
            removed.update(modules)
    return removed


# ── Severity Constants ───────────────────────────────────────────────────────

SEVERITY_ERROR = "ERROR"
SEVERITY_WARNING = "WARNING"
SEVERITY_INFO = "INFO"

EFFORT_TRIVIAL = "trivial"
EFFORT_SMALL = "small"
EFFORT_MEDIUM = "medium"
EFFORT_LARGE = "large"

AUTOMATION_AUTO = "auto"
AUTOMATION_SEMI = "semi-auto"
AUTOMATION_MANUAL = "manual"


# ── Finding Data Structure ───────────────────────────────────────────────────

def make_finding(
    category: int,
    category_name: str,
    file_path: str,
    line: int,
    pattern: str,
    description: str,
    severity: str,
    snippet: str = "",
    effort: str = EFFORT_TRIVIAL,
    automation: str = AUTOMATION_AUTO,
) -> Dict[str, Any]:
    """Create a standardized finding record."""
    return {
        "category": category,
        "category_name": category_name,
        "file": file_path,
        "line": line,
        "pattern": pattern,
        "description": description,
        "severity": severity,
        "snippet": snippet[:200],
        "effort": effort,
        "automation": automation,
    }


# ── Category 1: Remaining Py2 Syntax ────────────────────────────────────────

PY2_SYNTAX_PATTERNS = [
    # (regex_pattern, pattern_name, description)
    (r'\bprint\s+["\']', "print_statement", "Print statement (not function)"),
    (r'\bprint\s+[a-zA-Z_]', "print_statement", "Print statement (not function)"),
    (r'\bexec\s+["\']', "exec_statement", "Exec statement (not function)"),
    (r'\bexec\s+[a-zA-Z_]', "exec_statement", "Exec statement (not function)"),
    (r'[^!<>=]\s*<>\s*[^=]', "diamond_operator", "Diamond (<>) comparison operator"),
    (r'\.has_key\s*\(', "has_key", "dict.has_key() method (use 'in' operator)"),
    (r'\braise\s+["\']', "raise_string", "Raise string exception"),
    (r'\bexcept\s+\w+\s*,\s*\w+\s*:', "old_except", "Old-style except clause (use 'as')"),
    (r'\bxrange\s*\(', "xrange", "xrange() call (use range())"),
    (r'\braw_input\s*\(', "raw_input", "raw_input() call (use input())"),
    (r'\bapply\s*\(', "apply_call", "apply() call (use *args/**kwargs)"),
    (r'\bexecfile\s*\(', "execfile", "execfile() call"),
    (r'\blong\s*\(', "long_type", "long() type constructor"),
    (r'\breload\s*\(', "reload_call", "reload() call (use importlib.reload)"),
    (r'\breduce\s*\(', "reduce_call", "reduce() without functools import"),
    (r'\bunicode\s*\(', "unicode_type", "unicode() type constructor"),
    (r'\bbasestring\b', "basestring", "basestring type reference"),
]


def check_py2_syntax(
    file_path: str, content: str, lines: List[str],
) -> List[Dict[str, Any]]:
    """Check for remaining Python 2 syntax patterns."""
    findings = []

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip comments and strings
        if stripped.startswith("#"):
            continue

        for pattern_re, pattern_name, description in PY2_SYNTAX_PATTERNS:
            if re.search(pattern_re, line):
                # Extra validation for some patterns to reduce false positives
                if pattern_name == "print_statement":
                    # Skip if it's a function call: print(...)
                    if re.match(r'\s*print\s*\(', line):
                        continue
                    # Skip if it's in a comment
                    code_part = line.split("#")[0]
                    if not re.search(pattern_re, code_part):
                        continue
                if pattern_name == "exec_statement":
                    if re.match(r'\s*exec\s*\(', line):
                        continue
                if pattern_name == "reduce_call":
                    # Only flag if functools is not imported
                    if "from functools import" in content and "reduce" in content:
                        continue
                if pattern_name == "apply_call":
                    # Skip if it's a method call on an object
                    if re.match(r'.*\.\s*apply\s*\(', line):
                        continue

                findings.append(make_finding(
                    category=1,
                    category_name="Remaining Py2 Syntax",
                    file_path=file_path,
                    line=line_num,
                    pattern=pattern_name,
                    description=description,
                    severity=SEVERITY_ERROR,
                    snippet=stripped,
                    effort=EFFORT_TRIVIAL,
                    automation=AUTOMATION_AUTO,
                ))

    # AST-based checks for more reliable detection
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        # If we can't parse it, it might still have Py2 syntax
        findings.append(make_finding(
            category=1,
            category_name="Remaining Py2 Syntax",
            file_path=file_path,
            line=0,
            pattern="syntax_error",
            description="File has syntax errors (may contain Py2 syntax)",
            severity=SEVERITY_ERROR,
            effort=EFFORT_MEDIUM,
            automation=AUTOMATION_MANUAL,
        ))

    return findings


# ── Category 2: Compatibility Library Usage ──────────────────────────────────

COMPAT_LIBRARY_PATTERNS = [
    (r'^\s*import\s+six\b', "import_six", "six library import"),
    (r'^\s*from\s+six\b', "from_six", "six library import"),
    (r'^\s*from\s+six\.moves\b', "six_moves", "six.moves import"),
    (r'\bsix\.text_type\b', "six_text_type", "six.text_type (use str)"),
    (r'\bsix\.binary_type\b', "six_binary_type", "six.binary_type (use bytes)"),
    (r'\bsix\.string_types\b', "six_string_types", "six.string_types (use str)"),
    (r'\bsix\.integer_types\b', "six_integer_types", "six.integer_types (use int)"),
    (r'\bsix\.PY2\b', "six_py2", "six.PY2 constant"),
    (r'\bsix\.PY3\b', "six_py3", "six.PY3 constant"),
    (r'\bsix\.ensure_str\b', "six_ensure", "six.ensure_str (no longer needed)"),
    (r'\bsix\.ensure_text\b', "six_ensure", "six.ensure_text (no longer needed)"),
    (r'\bsix\.ensure_binary\b', "six_ensure", "six.ensure_binary (no longer needed)"),
    (r'\bsix\.moves\.\w+', "six_moves_ref", "six.moves reference"),
    (r'^\s*import\s+future\b', "import_future_lib", "future library import"),
    (r'^\s*from\s+future\b', "from_future_lib", "future library import"),
    (r'^\s*from\s+builtins\s+import\b', "builtins_import", "python-future builtins import"),
    (r'^\s*from\s+past\.builtins\b', "past_builtins", "past.builtins import"),
    (r'^\s*from\s+past\b', "from_past", "past library import"),
]


def check_compat_libraries(
    file_path: str, content: str, lines: List[str],
) -> List[Dict[str, Any]]:
    """Check for compatibility library usage."""
    findings = []

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        for pattern_re, pattern_name, description in COMPAT_LIBRARY_PATTERNS:
            if re.search(pattern_re, line):
                findings.append(make_finding(
                    category=2,
                    category_name="Compatibility Library Usage",
                    file_path=file_path,
                    line=line_num,
                    pattern=pattern_name,
                    description=description,
                    severity=SEVERITY_WARNING,
                    snippet=stripped,
                    effort=EFFORT_SMALL,
                    automation=AUTOMATION_SEMI,
                ))

    return findings


# ── Category 3: Unnecessary __future__ Imports ───────────────────────────────

# __future__ imports that are default in Python 3.0+
UNNECESSARY_FUTURES = {
    "print_function",
    "division",
    "absolute_import",
    "unicode_literals",
    "generators",
    "nested_scopes",
    "with_statement",
}

# __future__ imports that are still useful
USEFUL_FUTURES = {
    "annotations",  # Still useful through Python 3.13
}


def check_future_imports(
    file_path: str, content: str, lines: List[str],
) -> List[Dict[str, Any]]:
    """Check for unnecessary __future__ imports."""
    findings = []

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            for alias in node.names:
                name = alias.name
                if name in UNNECESSARY_FUTURES:
                    findings.append(make_finding(
                        category=3,
                        category_name="Unnecessary __future__ Import",
                        file_path=file_path,
                        line=node.lineno,
                        pattern=f"future_{name}",
                        description=f"from __future__ import {name} — default in Py3, can be removed",
                        severity=SEVERITY_INFO,
                        snippet=f"from __future__ import {name}",
                        effort=EFFORT_TRIVIAL,
                        automation=AUTOMATION_AUTO,
                    ))
                elif name not in USEFUL_FUTURES:
                    findings.append(make_finding(
                        category=3,
                        category_name="Unnecessary __future__ Import",
                        file_path=file_path,
                        line=node.lineno,
                        pattern=f"future_{name}",
                        description=f"from __future__ import {name} — unknown future import",
                        severity=SEVERITY_INFO,
                        snippet=f"from __future__ import {name}",
                        effort=EFFORT_TRIVIAL,
                        automation=AUTOMATION_AUTO,
                    ))

    return findings


# ── Category 4: Version Guard Patterns ───────────────────────────────────────

VERSION_GUARD_PATTERNS = [
    (r'sys\.version_info\s*[\[<>=!]', "sys_version_info", "sys.version_info comparison"),
    (r'sys\.version_info\s*\.\s*major', "sys_version_major", "sys.version_info.major check"),
    (r'sys\.version\s*[\[<>=!.]', "sys_version_str", "sys.version string check"),
    (r'sys\.version\.startswith', "sys_version_startswith", "sys.version.startswith() check"),
    (r'platform\.python_version', "platform_version", "platform.python_version() check"),
    (r'\bPY2\b', "py2_constant", "PY2 constant reference"),
    (r'\bPY3\b', "py3_constant", "PY3 constant reference"),
    (r'\bPYTHON2\b', "python2_constant", "PYTHON2 constant reference"),
    (r'\bPYTHON3\b', "python3_constant", "PYTHON3 constant reference"),
    (r'\bis_python2\b', "is_python2", "is_python2 variable reference"),
    (r'\bis_python3\b', "is_python3", "is_python3 variable reference"),
    (r'\bis_py2\b', "is_py2", "is_py2 variable reference"),
    (r'\bis_py3\b', "is_py3", "is_py3 variable reference"),
]


def check_version_guards(
    file_path: str, content: str, lines: List[str],
) -> List[Dict[str, Any]]:
    """Check for version guard patterns."""
    findings = []

    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        for pattern_re, pattern_name, description in VERSION_GUARD_PATTERNS:
            if re.search(pattern_re, line):
                # Determine severity: actual branching is WARNING, constants are INFO
                severity = SEVERITY_WARNING
                effort = EFFORT_MEDIUM
                automation = AUTOMATION_MANUAL

                if pattern_name in ("py2_constant", "py3_constant",
                                    "python2_constant", "python3_constant",
                                    "is_python2", "is_python3",
                                    "is_py2", "is_py3"):
                    severity = SEVERITY_WARNING
                    effort = EFFORT_SMALL
                    automation = AUTOMATION_SEMI

                findings.append(make_finding(
                    category=4,
                    category_name="Version Guard Pattern",
                    file_path=file_path,
                    line=line_num,
                    pattern=pattern_name,
                    description=description,
                    severity=severity,
                    snippet=stripped,
                    effort=effort,
                    automation=automation,
                ))

    return findings


# ── Category 5: Migration TODO/FIXME Comments ────────────────────────────────

MIGRATION_COMMENT_PATTERNS = [
    (r'#\s*TODO\s*[\(:]?\s*migrat', "todo_migration", "Migration-tagged TODO"),
    (r'#\s*TODO\s*[\(:]?\s*py[23]', "todo_py23", "Py2/Py3-tagged TODO"),
    (r'#\s*TODO\s*[\(:]?\s*python\s*[23]', "todo_python23", "Python 2/3-tagged TODO"),
    (r'#\s*FIXME\s*[\(:]?\s*migrat', "fixme_migration", "Migration-tagged FIXME"),
    (r'#\s*FIXME\s*[\(:]?\s*py[23]', "fixme_py23", "Py2/Py3-tagged FIXME"),
    (r'#\s*FIXME\s*[\(:]?\s*python\s*[23]', "fixme_python23", "Python 2/3-tagged FIXME"),
    (r'#\s*FIXME\s*[\(:]?\s*encod', "fixme_encoding", "Encoding-tagged FIXME"),
    (r'#\s*HACK\s*[\(:]?\s*py[23]', "hack_py23", "Py2/Py3-tagged HACK"),
    (r'#\s*HACK\s*[\(:]?\s*compat', "hack_compat", "Compatibility HACK"),
    (r'#\s*XXX\s*[\(:]?\s*encod', "xxx_encoding", "Encoding-flagged XXX"),
    (r'#\s*XXX\s*[\(:]?\s*bytes', "xxx_bytes", "Bytes-flagged XXX"),
    (r'#\s*XXX\s*[\(:]?\s*migrat', "xxx_migration", "Migration-flagged XXX"),
    (r'#\s*TEMPORARY\s*[\(:]?\s*migrat', "temp_migration", "Temporary migration code"),
    (r'#\s*MIGRATION\b', "migration_comment", "Migration comment marker"),
]


def check_migration_comments(
    file_path: str, content: str, lines: List[str],
) -> List[Dict[str, Any]]:
    """Check for migration-related TODO/FIXME/HACK comments."""
    findings = []

    for line_num, line in enumerate(lines, 1):
        for pattern_re, pattern_name, description in MIGRATION_COMMENT_PATTERNS:
            if re.search(pattern_re, line, re.IGNORECASE):
                severity = SEVERITY_WARNING
                if pattern_name.startswith("xxx_") or pattern_name.startswith("temp_"):
                    severity = SEVERITY_INFO

                findings.append(make_finding(
                    category=5,
                    category_name="Migration TODO/FIXME Comment",
                    file_path=file_path,
                    line=line_num,
                    pattern=pattern_name,
                    description=description,
                    severity=severity,
                    snippet=line.strip(),
                    effort=EFFORT_TRIVIAL,
                    automation=AUTOMATION_MANUAL,
                ))

    return findings


# ── Category 6: Type Ignore Comments ────────────────────────────────────────

TYPE_IGNORE_RE = re.compile(r'#\s*type:\s*ignore(?:\[([^\]]*)\])?')


def check_type_ignores(
    file_path: str, content: str, lines: List[str],
) -> List[Dict[str, Any]]:
    """Check for # type: ignore comments."""
    findings = []

    for line_num, line in enumerate(lines, 1):
        match = TYPE_IGNORE_RE.search(line)
        if match:
            error_code = match.group(1) or "bare"
            severity = SEVERITY_WARNING if error_code == "bare" else SEVERITY_INFO

            findings.append(make_finding(
                category=6,
                category_name="Type Ignore Comment",
                file_path=file_path,
                line=line_num,
                pattern=f"type_ignore_{error_code.replace('-', '_').replace(',', '_')}",
                description=f"# type: ignore[{error_code}] — may be resolvable after migration",
                severity=severity,
                snippet=line.strip(),
                effort=EFFORT_SMALL,
                automation=AUTOMATION_MANUAL,
            ))

    return findings


# ── Category 7: Encoding Declarations ────────────────────────────────────────

ENCODING_DECL_RE = re.compile(
    r'#.*?(?:coding[:=])\s*([-\w.]+)', re.ASCII
)


def check_encoding_declarations(
    file_path: str, content: str, lines: List[str],
) -> List[Dict[str, Any]]:
    """Check for encoding declarations that may need updating."""
    findings = []

    # Only check first 2 lines (PEP 263)
    for line_num in range(min(2, len(lines))):
        line = lines[line_num]
        match = ENCODING_DECL_RE.search(line)
        if match:
            encoding = match.group(1).lower()

            if encoding == "ascii":
                findings.append(make_finding(
                    category=7,
                    category_name="Encoding Declaration",
                    file_path=file_path,
                    line=line_num + 1,
                    pattern="encoding_ascii",
                    description="Encoding declaration: ascii — should be utf-8 or removed",
                    severity=SEVERITY_WARNING,
                    snippet=line.strip(),
                    effort=EFFORT_TRIVIAL,
                    automation=AUTOMATION_AUTO,
                ))
            elif encoding in ("latin-1", "latin1", "iso-8859-1", "iso8859-1"):
                findings.append(make_finding(
                    category=7,
                    category_name="Encoding Declaration",
                    file_path=file_path,
                    line=line_num + 1,
                    pattern="encoding_latin1",
                    description=f"Encoding declaration: {encoding} — consider updating to utf-8",
                    severity=SEVERITY_INFO,
                    snippet=line.strip(),
                    effort=EFFORT_TRIVIAL,
                    automation=AUTOMATION_SEMI,
                ))
            elif encoding == "utf-8":
                # Redundant in Py3 but harmless — very low priority
                findings.append(make_finding(
                    category=7,
                    category_name="Encoding Declaration",
                    file_path=file_path,
                    line=line_num + 1,
                    pattern="encoding_utf8_redundant",
                    description="Encoding declaration: utf-8 — redundant in Py3 (default), but harmless",
                    severity=SEVERITY_INFO,
                    snippet=line.strip(),
                    effort=EFFORT_TRIVIAL,
                    automation=AUTOMATION_AUTO,
                ))

    return findings


# ── Category 8: Dual-Compatibility Patterns ──────────────────────────────────

COMPAT_PATTERN_CHECKS = [
    # (regex, pattern_name, description, severity, effort, automation)
    (
        r'try:\s*\n\s*unicode\b',
        "try_unicode", "try/except for unicode type detection",
        SEVERITY_WARNING, EFFORT_SMALL, AUTOMATION_SEMI,
    ),
    (
        r'try:\s*\n\s*from\s+StringIO\b',
        "try_stringio", "try/except for StringIO import fallback",
        SEVERITY_WARNING, EFFORT_SMALL, AUTOMATION_SEMI,
    ),
    (
        r'try:\s*\n\s*from\s+cStringIO\b',
        "try_cstringio", "try/except for cStringIO import fallback",
        SEVERITY_WARNING, EFFORT_SMALL, AUTOMATION_SEMI,
    ),
    (
        r'try:\s*\n\s*from\s+configparser\b',
        "try_configparser", "try/except for configparser import fallback",
        SEVERITY_WARNING, EFFORT_SMALL, AUTOMATION_SEMI,
    ),
    (
        r'try:\s*\n\s*from\s+queue\b',
        "try_queue", "try/except for queue import fallback",
        SEVERITY_WARNING, EFFORT_SMALL, AUTOMATION_SEMI,
    ),
    (
        r'try:\s*\n\s*from\s+urllib\b',
        "try_urllib", "try/except for urllib import fallback",
        SEVERITY_WARNING, EFFORT_SMALL, AUTOMATION_SEMI,
    ),
    (
        r'getattr\s*\(\s*str\s*,\s*[\'"]decode[\'"]\s*,',
        "getattr_str_decode", "getattr(str, 'decode', ...) — Py2/Py3 detection",
        SEVERITY_WARNING, EFFORT_SMALL, AUTOMATION_SEMI,
    ),
    (
        r'getattr\s*\(\s*bytes\s*,\s*[\'"]encode[\'"]\s*,',
        "getattr_bytes_encode", "getattr(bytes, 'encode', ...) — Py2/Py3 detection",
        SEVERITY_WARNING, EFFORT_SMALL, AUTOMATION_SEMI,
    ),
]

# Single-line patterns for dual-compat
COMPAT_LINE_PATTERNS = [
    (
        r'isinstance\s*\(\s*\w+\s*,\s*\(\s*str\s*,\s*bytes\s*\)\s*\)',
        "isinstance_str_bytes",
        "isinstance(x, (str, bytes)) — may indicate unclear type expectation",
        SEVERITY_INFO, EFFORT_SMALL, AUTOMATION_MANUAL,
    ),
    (
        r'isinstance\s*\(\s*\w+\s*,\s*\(\s*bytes\s*,\s*str\s*\)\s*\)',
        "isinstance_bytes_str",
        "isinstance(x, (bytes, str)) — may indicate unclear type expectation",
        SEVERITY_INFO, EFFORT_SMALL, AUTOMATION_MANUAL,
    ),
    (
        r'\.encode\s*\(\s*[\'"]utf-?8[\'"]\s*\)\s*if\s+',
        "conditional_encode",
        "Conditional .encode('utf-8') — may be Py2/Py3 compat pattern",
        SEVERITY_INFO, EFFORT_SMALL, AUTOMATION_MANUAL,
    ),
    (
        r'\.decode\s*\(\s*[\'"]utf-?8[\'"]\s*\)\s*if\s+',
        "conditional_decode",
        "Conditional .decode('utf-8') — may be Py2/Py3 compat pattern",
        SEVERITY_INFO, EFFORT_SMALL, AUTOMATION_MANUAL,
    ),
]


def check_dual_compat_patterns(
    file_path: str, content: str, lines: List[str],
) -> List[Dict[str, Any]]:
    """Check for dual Py2/Py3 compatibility patterns."""
    findings = []

    # Multi-line patterns (check against full content)
    for pattern_re, pattern_name, description, severity, effort, automation in COMPAT_PATTERN_CHECKS:
        for match in re.finditer(pattern_re, content, re.MULTILINE):
            # Approximate line number from match position
            line_num = content[:match.start()].count("\n") + 1
            snippet = content[match.start():match.end()].strip()

            findings.append(make_finding(
                category=8,
                category_name="Dual-Compatibility Pattern",
                file_path=file_path,
                line=line_num,
                pattern=pattern_name,
                description=description,
                severity=severity,
                snippet=snippet,
                effort=effort,
                automation=automation,
            ))

    # Single-line patterns
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue

        for pattern_re, pattern_name, description, severity, effort, automation in COMPAT_LINE_PATTERNS:
            if re.search(pattern_re, line):
                findings.append(make_finding(
                    category=8,
                    category_name="Dual-Compatibility Pattern",
                    file_path=file_path,
                    line=line_num,
                    pattern=pattern_name,
                    description=description,
                    severity=severity,
                    snippet=stripped,
                    effort=effort,
                    automation=automation,
                ))

    return findings


# ── Category 9: Deprecated Standard Library Usage ────────────────────────────

def check_deprecated_stdlib(
    file_path: str, content: str, lines: List[str],
    removed_modules: Set[str],
) -> List[Dict[str, Any]]:
    """Check for usage of stdlib modules removed in the target version."""
    findings = []

    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError:
        return findings

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_module = alias.name.split(".")[0]
                if top_module in removed_modules:
                    findings.append(make_finding(
                        category=9,
                        category_name="Deprecated Stdlib Usage",
                        file_path=file_path,
                        line=node.lineno,
                        pattern=f"removed_{top_module}",
                        description=f"import {alias.name} — module removed in target version",
                        severity=SEVERITY_ERROR,
                        snippet=f"import {alias.name}",
                        effort=EFFORT_MEDIUM,
                        automation=AUTOMATION_SEMI,
                    ))

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top_module = node.module.split(".")[0]
                if top_module in removed_modules:
                    names = ", ".join(a.name for a in node.names)
                    findings.append(make_finding(
                        category=9,
                        category_name="Deprecated Stdlib Usage",
                        file_path=file_path,
                        line=node.lineno,
                        pattern=f"removed_{top_module}",
                        description=f"from {node.module} import {names} — module removed in target version",
                        severity=SEVERITY_ERROR,
                        snippet=f"from {node.module} import {names}",
                        effort=EFFORT_MEDIUM,
                        automation=AUTOMATION_SEMI,
                    ))

    return findings


# ── Category 10: Lint and Type Check Compliance ──────────────────────────────

def check_lint_compliance(
    file_path: str, content: str, lines: List[str],
    lint_baseline: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Check for lint compliance indicators.
    Note: This does not run external tools — it checks for patterns that
    indicate lint/type-check issues remain.
    """
    findings = []

    # Check for noqa comments that suppress Py3 compatibility warnings
    noqa_re = re.compile(r'#\s*noqa\s*:\s*([\w,\s]+)')
    for line_num, line in enumerate(lines, 1):
        match = noqa_re.search(line)
        if match:
            codes = match.group(1).strip()
            # Flag noqa comments that suppress encoding or compatibility warnings
            if any(c in codes for c in ["E501", "W503", "W504"]):
                continue  # Style-only, not migration-related
            findings.append(make_finding(
                category=10,
                category_name="Lint Compliance",
                file_path=file_path,
                line=line_num,
                pattern="noqa_suppression",
                description=f"# noqa: {codes} — lint suppression may hide migration issues",
                severity=SEVERITY_INFO,
                snippet=line.strip(),
                effort=EFFORT_SMALL,
                automation=AUTOMATION_MANUAL,
            ))

    # Check for pylint disable comments related to Py2/Py3
    pylint_disable_re = re.compile(r'#\s*pylint:\s*disable\s*=\s*([\w,-]+)')
    for line_num, line in enumerate(lines, 1):
        match = pylint_disable_re.search(line)
        if match:
            codes = match.group(1)
            migration_related = [
                "no-member", "import-error", "undefined-variable",
                "not-callable", "unexpected-keyword-arg",
            ]
            if any(c in codes for c in migration_related):
                findings.append(make_finding(
                    category=10,
                    category_name="Lint Compliance",
                    file_path=file_path,
                    line=line_num,
                    pattern="pylint_disable_migration",
                    description=f"pylint: disable={codes} — may hide migration issues",
                    severity=SEVERITY_INFO,
                    snippet=line.strip(),
                    effort=EFFORT_SMALL,
                    automation=AUTOMATION_MANUAL,
                ))

    return findings


# ── Main Scanner ─────────────────────────────────────────────────────────────

def scan_file(
    file_path: str,
    target_version: str,
    removed_modules: Set[str],
    lint_baseline: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Run all check categories on a single file."""
    content = read_file(file_path)
    lines = content.splitlines()

    findings = []
    findings.extend(check_py2_syntax(file_path, content, lines))
    findings.extend(check_compat_libraries(file_path, content, lines))
    findings.extend(check_future_imports(file_path, content, lines))
    findings.extend(check_version_guards(file_path, content, lines))
    findings.extend(check_migration_comments(file_path, content, lines))
    findings.extend(check_type_ignores(file_path, content, lines))
    findings.extend(check_encoding_declarations(file_path, content, lines))
    findings.extend(check_dual_compat_patterns(file_path, content, lines))
    findings.extend(check_deprecated_stdlib(file_path, content, lines, removed_modules))
    findings.extend(check_lint_compliance(file_path, content, lines, lint_baseline))

    return findings


# ── Report Generation ────────────────────────────────────────────────────────

CATEGORY_NAMES = {
    1: "Remaining Py2 Syntax",
    2: "Compatibility Library Usage",
    3: "Unnecessary __future__ Import",
    4: "Version Guard Pattern",
    5: "Migration TODO/FIXME Comment",
    6: "Type Ignore Comment",
    7: "Encoding Declaration",
    8: "Dual-Compatibility Pattern",
    9: "Deprecated Stdlib Usage",
    10: "Lint Compliance",
}


def generate_completeness_report(
    findings: List[Dict[str, Any]],
    files_scanned: int,
    codebase_path: str,
    target_version: str,
    strict: bool = False,
) -> Dict[str, Any]:
    """Generate the completeness report from all findings."""
    # Count by severity
    error_count = sum(1 for f in findings if f["severity"] == SEVERITY_ERROR)
    warning_count = sum(1 for f in findings if f["severity"] == SEVERITY_WARNING)
    info_count = sum(1 for f in findings if f["severity"] == SEVERITY_INFO)

    # In strict mode, warnings count as errors for gate purposes
    gate_blocking = error_count
    if strict:
        gate_blocking += warning_count

    # Count by category
    category_counts: Dict[int, Dict[str, int]] = {}
    for f in findings:
        cat = f["category"]
        if cat not in category_counts:
            category_counts[cat] = {"total": 0, "error": 0, "warning": 0, "info": 0}
        category_counts[cat]["total"] += 1
        category_counts[cat][f["severity"].lower()] += 1

    # Completeness score: 100 - (weighted findings / files_scanned)
    # Errors: 10 points, Warnings: 3 points, Info: 1 point
    if files_scanned > 0:
        weighted = (error_count * 10 + warning_count * 3 + info_count * 1)
        raw_score = max(0, 100 - (weighted / files_scanned) * 10)
        completeness_score = round(raw_score, 1)
    else:
        completeness_score = 100.0

    # Count files with findings
    files_with_findings = len(set(f["file"] for f in findings))
    files_clean = files_scanned - files_with_findings

    # Unique patterns found
    patterns_found = Counter(f["pattern"] for f in findings)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "codebase_path": codebase_path,
        "target_version": target_version,
        "strict_mode": strict,
        "summary": {
            "files_scanned": files_scanned,
            "files_with_findings": files_with_findings,
            "files_clean": files_clean,
            "total_findings": len(findings),
            "error_count": error_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "gate_blocking_count": gate_blocking,
            "completeness_score": completeness_score,
        },
        "category_summary": {
            cat: {
                "name": CATEGORY_NAMES.get(cat, f"Category {cat}"),
                **counts,
            }
            for cat, counts in sorted(category_counts.items())
        },
        "top_patterns": [
            {"pattern": p, "count": c}
            for p, c in patterns_found.most_common(20)
        ],
        "findings": findings,
    }

    return report


def generate_cleanup_tasks(
    findings: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Generate ordered cleanup task list from findings."""
    # Group findings by (file, category, pattern) to create tasks
    task_groups: Dict[Tuple[str, int, str], List[Dict[str, Any]]] = {}
    for f in findings:
        key = (f["file"], f["category"], f["pattern"])
        task_groups.setdefault(key, []).append(f)

    tasks = []
    for (file_path, category, pattern), group_findings in task_groups.items():
        # Determine priority from highest severity in group
        severities = [f["severity"] for f in group_findings]
        if SEVERITY_ERROR in severities:
            priority = "critical"
        elif SEVERITY_WARNING in severities:
            priority = "high"
        else:
            priority = "low"

        # Get effort and automation from first finding (same pattern = same effort)
        effort = group_findings[0]["effort"]
        automation = group_findings[0]["automation"]
        description = group_findings[0]["description"]

        lines = sorted(set(f["line"] for f in group_findings))

        tasks.append({
            "file": file_path,
            "category": category,
            "category_name": CATEGORY_NAMES.get(category, f"Category {category}"),
            "pattern": pattern,
            "description": description,
            "priority": priority,
            "effort": effort,
            "automation": automation,
            "occurrences": len(group_findings),
            "lines": lines[:20],  # Cap line list for readability
        })

    # Sort: critical first, then high, then low; within each, trivial effort first
    priority_order = {"critical": 0, "high": 1, "low": 2}
    effort_order = {"trivial": 0, "small": 1, "medium": 2, "large": 3}
    tasks.sort(key=lambda t: (
        priority_order.get(t["priority"], 9),
        effort_order.get(t["effort"], 9),
        t["file"],
    ))

    return tasks


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Check migration completeness — find remaining Py2 artifacts"
    )
    parser.add_argument(
        "codebase_path",
        help="Root directory of the Python codebase",
    )
    parser.add_argument(
        "--target-version", required=True,
        help="Target Python 3.x version (e.g., 3.9, 3.12)",
    )
    parser.add_argument(
        "--state-file",
        help="Path to migration-state.json (optional)",
    )
    parser.add_argument(
        "--output", default="./completeness-output",
        help="Output directory (default: ./completeness-output)",
    )
    parser.add_argument(
        "--modules", nargs="*",
        help="Specific modules to check (default: all .py files)",
    )
    parser.add_argument(
        "--lint-baseline",
        help="Path to lint-baseline.json from Skill 0.5 (optional)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat WARNING findings as errors for gate check",
    )

    args = parser.parse_args()

    codebase_path = os.path.abspath(args.codebase_path)
    if not os.path.isdir(codebase_path):
        print(f"Error: Not a directory: {codebase_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Discover Files ───────────────────────────────────────────────────
    print("# ── Discovering Python Files ─────────────────────────────────────")
    py_files = discover_python_files(codebase_path, args.modules)
    print(f"  Found {len(py_files)} Python files")

    if not py_files:
        print("  No Python files found. Nothing to check.", file=sys.stderr)
        sys.exit(0)

    # ── Load References ──────────────────────────────────────────────────
    removed_modules = get_removed_modules(args.target_version)
    print(f"  Target version: {args.target_version}")
    print(f"  Removed modules to check: {len(removed_modules)}")

    lint_baseline = None
    if args.lint_baseline:
        lint_baseline = load_json(args.lint_baseline)
        print(f"  Loaded lint baseline: {args.lint_baseline}")

    # ── Scan Files ───────────────────────────────────────────────────────
    print("# ── Scanning for Migration Artifacts ─────────────────────────────")
    all_findings: List[Dict[str, Any]] = []
    files_with_errors = 0

    for i, file_path in enumerate(py_files):
        if (i + 1) % 100 == 0 or (i + 1) == len(py_files):
            print(f"  Scanned {i + 1}/{len(py_files)} files...")

        try:
            file_findings = scan_file(
                file_path, args.target_version, removed_modules, lint_baseline,
            )
            # Make paths relative to codebase
            for f in file_findings:
                f["file"] = os.path.relpath(f["file"], codebase_path)
            all_findings.extend(file_findings)
        except Exception as e:
            files_with_errors += 1
            if files_with_errors <= 10:
                print(f"  Warning: Error scanning {file_path}: {e}", file=sys.stderr)

    print(f"  Total findings: {len(all_findings)}")
    if files_with_errors:
        print(f"  Files with scan errors: {files_with_errors}")

    # ── Generate Report ──────────────────────────────────────────────────
    print("# ── Generating Completeness Report ───────────────────────────────")
    report = generate_completeness_report(
        all_findings, len(py_files), codebase_path,
        args.target_version, args.strict,
    )

    report_path = str(output_dir / "completeness-report.json")
    save_json(report, report_path)

    # ── Generate Cleanup Tasks ───────────────────────────────────────────
    print("# ── Generating Cleanup Tasks ─────────────────────────────────────")
    tasks = generate_cleanup_tasks(all_findings)
    tasks_path = str(output_dir / "cleanup-tasks.json")
    save_json(tasks, tasks_path)

    # ── Print Summary ────────────────────────────────────────────────────
    print("# ── Summary ──────────────────────────────────────────────────────")
    summary = report["summary"]
    print(f"  Files scanned:      {summary['files_scanned']}")
    print(f"  Files with findings: {summary['files_with_findings']}")
    print(f"  Files clean:         {summary['files_clean']}")
    print(f"  Total findings:      {summary['total_findings']}")
    print(f"    ERROR:   {summary['error_count']}")
    print(f"    WARNING: {summary['warning_count']}")
    print(f"    INFO:    {summary['info_count']}")
    print(f"  Gate-blocking:       {summary['gate_blocking_count']}")
    print(f"  Completeness score:  {summary['completeness_score']}%")
    print(f"  Cleanup tasks:       {len(tasks)}")

    if summary["gate_blocking_count"] == 0:
        print("\n  ✓ GATE CHECK: PASS — zero gate-blocking findings")
    else:
        print(f"\n  ✗ GATE CHECK: FAIL — {summary['gate_blocking_count']} gate-blocking findings")

    print("\nDone.")


if __name__ == "__main__":
    main()
