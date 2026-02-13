#!/usr/bin/env python3
"""
C Extension Flagger — Main Detection Script

Identifies C extensions, Cython, ctypes, CFFI, SWIG usage in a Python codebase.
Flags deprecated C API usage per target Python 3 version.

Usage:
    python3 flag_extensions.py <codebase_path> \
        --target-version 3.12 \
        --output ./extension-output/

Output:
    c-extension-report.json — Complete inventory with risk assessment
"""

import ast
import json
import os
import re
import sys
import argparse
import fnmatch
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple


# ── C API Removals by Version ────────────────────────────────────────────────

C_API_REMOVALS = {
    "3.9": {
        "Py_TPFLAGS_HAVE_INDEX": {
            "category": "type_flag",
            "description": "Removed in 3.10, use Py_TPFLAGS_HAVE_GETCHARBUFFERPROC",
            "severity": "HIGH",
        },
    },
    "3.10": {
        "Py_TPFLAGS_HAVE_INDEX": {
            "category": "type_flag",
            "description": "Removed in 3.10",
            "severity": "HIGH",
        },
    },
    "3.12": {
        "PyCObject": {
            "category": "type",
            "description": "Removed in 3.2, use PyCapsule instead",
            "severity": "CRITICAL",
        },
        "Py_UNICODE": {
            "category": "type",
            "description": "Deprecated in 3.3, removed in 3.12",
            "severity": "CRITICAL",
        },
        "wstr": {
            "category": "field",
            "description": "PyUnicodeObject.wstr field removed",
            "severity": "CRITICAL",
        },
        "wstr_length": {
            "category": "field",
            "description": "PyUnicodeObject.wstr_length field removed",
            "severity": "CRITICAL",
        },
        "tp_print": {
            "category": "slot",
            "description": "PyTypeObject.tp_print slot removed",
            "severity": "CRITICAL",
        },
        "PyUnicode_READY": {
            "category": "function",
            "description": "Removed in 3.12, unicode strings auto-ready",
            "severity": "CRITICAL",
        },
        "PyUnicode_AsUCS4": {
            "category": "function",
            "description": "Limited compatibility in 3.12",
            "severity": "HIGH",
        },
        "PyUnicode_AsUCS4Copy": {
            "category": "function",
            "description": "Limited compatibility in 3.12",
            "severity": "HIGH",
        },
    },
    "3.13": {
        "Py_UNICODE": {
            "category": "type",
            "description": "Removed in 3.12+",
            "severity": "CRITICAL",
        },
        "PyUnicode_*": {
            "category": "function_family",
            "description": "Many PyUnicode functions removed, use new API",
            "severity": "HIGH",
        },
    },
}

# Patterns that indicate use of C extensions
C_EXTENSION_PATTERNS = {
    "python_h_include": {
        "pattern": r"#include\s+[<\"]Python\.h[>\"]",
        "description": "Python.h include (C extension)",
        "file_types": [".c", ".h", ".cpp"],
    },
    "module_init": {
        "pattern": r"PyMODINIT_FUNC|PyInit_\w+",
        "description": "Module initialization function",
        "file_types": [".c", ".h"],
    },
    "extension_def": {
        "pattern": r"Extension\s*\(",
        "description": "setuptools Extension definition",
        "file_types": [".py"],
    },
    "ext_modules": {
        "pattern": r"ext_modules\s*=",
        "description": "Extension modules in setup.py",
        "file_types": [".py"],
    },
}

# Patterns for ctypes/CFFI/SWIG
BINDING_PATTERNS = {
    "ctypes_cdll": {
        "pattern": r"(CDLL|WinDLL|WinDLL|PyDLL)\s*\(",
        "category": "ctypes",
        "description": "ctypes.CDLL/WinDLL usage",
    },
    "ctypes_import": {
        "pattern": r"from\s+ctypes\s+import.*(?:CDLL|Structure|POINTER|byref|cast)",
        "category": "ctypes",
        "description": "ctypes import",
    },
    "cffi_ffi": {
        "pattern": r"FFI\s*\(|ffi\.(cdef|dlopen|verify|compile)",
        "category": "cffi",
        "description": "CFFI FFI usage",
    },
    "cffi_import": {
        "pattern": r"from\s+cffi\s+import\s+FFI",
        "category": "cffi",
        "description": "CFFI import",
    },
    "swig_import": {
        "pattern": r"swig_import_helper|SWIG_init",
        "category": "swig",
        "description": "SWIG-generated code",
    },
}

# Deprecated C API patterns
DEPRECATED_API_PATTERNS = {
    "PyCObject": {
        "pattern": r"\bPyCObject\b",
        "removed_in": "3.2",
        "severity": "CRITICAL",
    },
    "Py_UNICODE": {
        "pattern": r"\bPy_UNICODE\b",
        "removed_in": "3.12",
        "severity": "CRITICAL",
    },
    "PyUnicode_READY": {
        "pattern": r"\bPyUnicode_READY\b",
        "removed_in": "3.12",
        "severity": "CRITICAL",
    },
    "tp_print": {
        "pattern": r"\.tp_print|->tp_print",
        "removed_in": "3.12",
        "severity": "CRITICAL",
    },
    "wstr": {
        "pattern": r"\.wstr|->wstr",
        "removed_in": "3.12",
        "severity": "CRITICAL",
    },
    "PyUnicode_AsUCS4": {
        "pattern": r"\bPyUnicode_AsUCS4\b",
        "removed_in": "3.12",
        "severity": "HIGH",
    },
    "_PyObject": {
        "pattern": r"\b_PyObject_\w+",
        "removed_in": "3.0",
        "severity": "HIGH",
        "description": "Internal API, unstable",
    },
    "Py_TPFLAGS_HAVE_INDEX": {
        "pattern": r"\bPy_TPFLAGS_HAVE_INDEX\b",
        "removed_in": "3.10",
        "severity": "HIGH",
    },
}


# ── Helper Functions ─────────────────────────────────────────────────────────

def load_json(path: str) -> Dict:
    """Load JSON file, return empty dict if not found."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(data: Dict, path: str) -> None:
    """Save data to JSON file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def read_file(path: str) -> str:
    """Read file content safely."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def should_skip(path: str, exclude_patterns: List[str]) -> bool:
    """Check if path matches exclude patterns."""
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(path, pattern):
            return True
    return False


def is_target_version_affected(api_name: str, target_version: str,
                               removal_data: Dict) -> bool:
    """Check if API was removed in or before target version."""
    removed_in = removal_data.get("removed_in", "")
    if not removed_in:
        return False

    removed_parts = tuple(map(int, removed_in.split(".")))
    target_parts = tuple(map(int, target_version.split(".")))

    return target_parts >= removed_parts


# ── Detection Functions ──────────────────────────────────────────────────────

def detect_c_extensions(filepath: str) -> List[Dict[str, Any]]:
    """Detect C extension markers in a file."""
    findings = []
    content = read_file(filepath)
    _, ext = os.path.splitext(filepath)

    for pattern_name, pattern_info in C_EXTENSION_PATTERNS.items():
        if ext in pattern_info["file_types"]:
            if re.search(pattern_info["pattern"], content):
                findings.append({
                    "type": "c_extension_marker",
                    "pattern": pattern_name,
                    "description": pattern_info["description"],
                    "file": filepath,
                    "severity": "HIGH",
                })

    return findings


def detect_cython_files(filepath: str) -> List[Dict[str, Any]]:
    """Detect Cython files."""
    findings = []
    _, ext = os.path.splitext(filepath)

    if ext in (".pyx", ".pxd"):
        findings.append({
            "type": "cython_file",
            "file": filepath,
            "extension": ext,
            "severity": "MEDIUM",
            "description": f"Cython {ext} file (will need regeneration)",
        })

    return findings


def detect_swig_files(filepath: str) -> List[Dict[str, Any]]:
    """Detect SWIG interface files."""
    findings = []
    _, ext = os.path.splitext(filepath)

    if ext == ".i":
        findings.append({
            "type": "swig_file",
            "file": filepath,
            "severity": "MEDIUM",
            "description": "SWIG interface file (will need regeneration)",
        })

    return findings


def detect_binding_usage(filepath: str) -> List[Dict[str, Any]]:
    """Detect ctypes/CFFI/SWIG usage."""
    findings = []
    content = read_file(filepath)
    lines = content.split("\n")

    for pattern_name, pattern_info in BINDING_PATTERNS.items():
        for line_no, line in enumerate(lines, 1):
            if re.search(pattern_info["pattern"], line):
                findings.append({
                    "type": "binding_usage",
                    "pattern": pattern_name,
                    "category": pattern_info["category"],
                    "description": pattern_info["description"],
                    "file": filepath,
                    "line": line_no,
                    "code": line.strip(),
                    "severity": "MEDIUM",
                })

    return findings


def detect_deprecated_api(filepath: str) -> List[Dict[str, Any]]:
    """Detect deprecated/removed C API usage."""
    findings = []
    content = read_file(filepath)
    lines = content.split("\n")

    for api_name, api_info in DEPRECATED_API_PATTERNS.items():
        pattern = api_info["pattern"]
        for line_no, line in enumerate(lines, 1):
            if re.search(pattern, line):
                findings.append({
                    "type": "deprecated_c_api",
                    "api": api_name,
                    "removed_in": api_info.get("removed_in", "unknown"),
                    "severity": api_info.get("severity", "MEDIUM"),
                    "description": api_info.get("description", f"{api_name} removed"),
                    "file": filepath,
                    "line": line_no,
                    "code": line.strip(),
                })

    return findings


def detect_setup_py_extensions(filepath: str) -> List[Dict[str, Any]]:
    """Parse setup.py for Extension definitions."""
    findings = []
    content = read_file(filepath)

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    for node in ast.walk(tree):
        # Look for Call nodes where func is Extension
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "Extension":
                # Extract extension name from first arg
                if node.args:
                    if isinstance(node.args[0], ast.Constant):
                        ext_name = node.args[0].value
                    elif isinstance(node.args[0], ast.Str):  # Python 3.7 compat
                        ext_name = node.args[0].s
                    else:
                        ext_name = "unknown"

                    findings.append({
                        "type": "extension_definition",
                        "name": ext_name,
                        "file": filepath,
                        "line": node.lineno,
                        "severity": "HIGH",
                        "description": f"Extension module: {ext_name}",
                    })

        # Look for setup() calls with ext_modules
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "setup":
                for keyword in node.keywords:
                    if keyword.arg == "ext_modules":
                        findings.append({
                            "type": "ext_modules_setup",
                            "file": filepath,
                            "line": node.lineno,
                            "severity": "HIGH",
                            "description": "setup() with ext_modules parameter",
                        })

    return findings


def check_limited_api(filepath: str) -> Optional[Dict[str, Any]]:
    """Check if file uses Py_LIMITED_API."""
    content = read_file(filepath)

    if re.search(r"#define\s+Py_LIMITED_API", content):
        return {
            "type": "limited_api_guard",
            "file": filepath,
            "description": "Uses Py_LIMITED_API (stable ABI, version-agnostic)",
            "severity": "INFO",
        }

    return None


# ── Main Analysis ────────────────────────────────────────────────────────────

def analyze_codebase(codebase_path: str, target_version: str,
                    exclude_patterns: List[str]) -> Dict[str, Any]:
    """Analyze codebase for C extensions and deprecated C API."""

    report = {
        "codebase": codebase_path,
        "target_version": target_version,
        "files_scanned": 0,
        "findings": [],
        "summary": {
            "total_findings": 0,
            "c_extensions": 0,
            "cython_files": 0,
            "swig_files": 0,
            "binding_usage": 0,
            "deprecated_api_uses": 0,
            "limited_api_usage": 0,
            "risk_summary": {
                "CRITICAL": 0,
                "HIGH": 0,
                "MEDIUM": 0,
                "LOW": 0,
                "INFO": 0,
            },
        },
    }

    # Walk codebase
    for dirpath, dirnames, filenames in os.walk(codebase_path):
        # Skip excluded directories
        dirnames[:] = [
            d for d in dirnames
            if not should_skip(os.path.join(dirpath, d), exclude_patterns)
        ]

        for filename in filenames:
            filepath = os.path.join(dirpath, filename)
            if should_skip(filepath, exclude_patterns):
                continue

            _, ext = os.path.splitext(filename)

            # Process relevant files
            if ext in (".c", ".h", ".cpp", ".cc", ".cxx", ".py", ".pyx", ".pxd", ".i"):
                report["files_scanned"] += 1

                # C extension markers
                findings = detect_c_extensions(filepath)
                for f in findings:
                    report["summary"]["c_extensions"] += 1
                    report["summary"]["total_findings"] += 1
                    report["findings"].append(f)

                # Cython files
                findings = detect_cython_files(filepath)
                for f in findings:
                    report["summary"]["cython_files"] += 1
                    report["summary"]["total_findings"] += 1
                    report["summary"]["risk_summary"][f["severity"]] += 1
                    report["findings"].append(f)

                # SWIG files
                findings = detect_swig_files(filepath)
                for f in findings:
                    report["summary"]["swig_files"] += 1
                    report["summary"]["total_findings"] += 1
                    report["summary"]["risk_summary"][f["severity"]] += 1
                    report["findings"].append(f)

                # Binding usage
                findings = detect_binding_usage(filepath)
                for f in findings:
                    report["summary"]["binding_usage"] += 1
                    report["summary"]["total_findings"] += 1
                    report["summary"]["risk_summary"][f["severity"]] += 1
                    report["findings"].append(f)

                # Deprecated C API
                findings = detect_deprecated_api(filepath)
                for f in findings:
                    # Check if API was removed in target version
                    if is_target_version_affected(f["api"], target_version,
                                                 C_API_REMOVALS.get(target_version, {})):
                        f["affects_target"] = True
                        f["severity"] = "CRITICAL"

                    report["summary"]["deprecated_api_uses"] += 1
                    report["summary"]["total_findings"] += 1
                    report["summary"]["risk_summary"][f["severity"]] += 1
                    report["findings"].append(f)

                # Limited API check (positive signal)
                limited_api = check_limited_api(filepath)
                if limited_api:
                    report["summary"]["limited_api_usage"] += 1
                    report["summary"]["risk_summary"][limited_api["severity"]] += 1
                    report["findings"].append(limited_api)

                # setup.py extension detection
                if filename == "setup.py":
                    findings = detect_setup_py_extensions(filepath)
                    for f in findings:
                        report["summary"]["total_findings"] += 1
                        report["summary"]["risk_summary"][f["severity"]] += 1
                        report["findings"].append(f)

    return report


# ── Main Entry Point ────────────────────────────────────────────────────────

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="C Extension Flagger for Py2→Py3 migration"
    )
    parser.add_argument("codebase_path", help="Root directory of Python 2 codebase")
    parser.add_argument("--target-version", default="3.12",
                       help="Target Python 3.x version (default: 3.12)")
    parser.add_argument("--exclude", nargs="*", default=["**/vendor/**", "**/.git/**"],
                       help="Glob patterns to exclude")
    parser.add_argument("--output", default=".",
                       help="Output directory for reports")
    parser.add_argument("--strict", action="store_true",
                       help="Fail if any deprecated API found")

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
    )

    # Save output
    os.makedirs(args.output, exist_ok=True)

    report_path = os.path.join(args.output, "c-extension-report.json")
    save_json(report, report_path)
    print(f"Wrote: {report_path}")

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files scanned: {report['files_scanned']}")
    print(f"Total findings: {report['summary']['total_findings']}")
    print()
    print("By type:")
    print(f"  C extensions: {report['summary']['c_extensions']}")
    print(f"  Cython files: {report['summary']['cython_files']}")
    print(f"  SWIG files: {report['summary']['swig_files']}")
    print(f"  Binding usage (ctypes/CFFI): {report['summary']['binding_usage']}")
    print(f"  Deprecated C API uses: {report['summary']['deprecated_api_uses']}")
    print(f"  Limited API usage (good): {report['summary']['limited_api_usage']}")
    print()
    print("By severity:")
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = report["summary"]["risk_summary"].get(sev, 0)
        if count > 0:
            print(f"  {sev}: {count}")

    critical = report["summary"]["risk_summary"].get("CRITICAL", 0)
    if args.strict and critical > 0:
        print()
        print(f"FAIL: {critical} critical issues found (--strict mode)")
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
