#!/usr/bin/env python3
"""
Serialization Boundary Detector — Main Detection Script

Scans a Python 2 codebase to identify all serialization/deserialization points
(pickle, marshal, shelve, json, yaml, msgpack, protobuf, struct, custom classes).
Assesses Py2→Py3 data compatibility risk. Scans filesystem for persisted data files.

Usage:
    python3 detect_serialization.py <codebase_path> \
        --target-version 3.12 \
        --data-dirs /var/data /tmp/cache \
        --output ./serialization-output/

Output:
    serialization-report.json — Complete inventory with risk assessment
    data-migration-plan.json — Step-by-step migration plan
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
from typing import Dict, List, Any, Optional, Tuple, Set

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ── Pattern Definitions ──────────────────────────────────────────────────────

SERIALIZATION_PATTERNS = {
    "pickle_import": {
        "patterns": [r"^import\s+pickle$", r"^from\s+pickle\s+import"],
        "category": "pickle",
        "description": "pickle module import",
    },
    "cpickle_import": {
        "patterns": [r"^import\s+cPickle$", r"^from\s+cPickle\s+import"],
        "category": "pickle",
        "description": "cPickle import (Py2 only, must become pickle)",
    },
    "pickle_load": {
        "patterns": [r"pickle\.(load|loads|Unpickler|load_compat)"],
        "category": "pickle",
        "description": "pickle.load() or pickle.loads() call",
    },
    "pickle_dump": {
        "patterns": [r"pickle\.(dump|dumps|Pickler)"],
        "category": "pickle",
        "description": "pickle.dump() or pickle.dumps() call",
    },
    "marshal_import": {
        "patterns": [r"^import\s+marshal$"],
        "category": "marshal",
        "description": "marshal module import",
    },
    "marshal_usage": {
        "patterns": [r"marshal\.(load|loads|dump|dumps)"],
        "category": "marshal",
        "description": "marshal load/dump operation",
    },
    "shelve_import": {
        "patterns": [r"^import\s+shelve$", r"^from\s+shelve\s+import"],
        "category": "shelve",
        "description": "shelve module import",
    },
    "shelve_usage": {
        "patterns": [r"shelve\.open"],
        "category": "shelve",
        "description": "shelve.open() call",
    },
    "json_import": {
        "patterns": [r"^import\s+json$", r"^from\s+json\s+import"],
        "category": "json",
        "description": "json module import",
    },
    "json_usage": {
        "patterns": [r"json\.(load|loads|dump|dumps)"],
        "category": "json",
        "description": "json load/dump operation",
    },
    "yaml_import": {
        "patterns": [r"^import\s+yaml$", r"^from\s+yaml\s+import"],
        "category": "yaml",
        "description": "yaml module import",
    },
    "yaml_load_unsafe": {
        "patterns": [r"yaml\.load\s*\((?!.*Loader)"],
        "category": "yaml",
        "description": "yaml.load() without Loader (unsafe)",
    },
    "yaml_safe_load": {
        "patterns": [r"yaml\.(safe_load|safe_dump)"],
        "category": "yaml",
        "description": "yaml.safe_load() or yaml.safe_dump() (safe)",
    },
    "msgpack_import": {
        "patterns": [r"^import\s+msgpack$", r"^from\s+msgpack\s+import"],
        "category": "msgpack",
        "description": "msgpack module import",
    },
    "msgpack_usage": {
        "patterns": [r"msgpack\.(packb|unpackb|pack|unpack)"],
        "category": "msgpack",
        "description": "msgpack pack/unpack operation",
    },
    "protobuf_import": {
        "patterns": [r"^from\s+google\.protobuf\s+import", r"^import\s+google\.protobuf"],
        "category": "protobuf",
        "description": "protobuf import",
    },
    "protobuf_serialize": {
        "patterns": [r"\.(SerializeToString|ParseFromString)"],
        "category": "protobuf",
        "description": "protobuf serialization call",
    },
    "struct_import": {
        "patterns": [r"^import\s+struct$", r"^from\s+struct\s+import"],
        "category": "struct",
        "description": "struct module import",
    },
    "struct_pack": {
        "patterns": [r"struct\.(pack|unpack|pack_into|unpack_from)"],
        "category": "struct",
        "description": "struct pack/unpack operation",
    },
    "getstate": {
        "patterns": [r"def\s+__getstate__\s*\("],
        "category": "custom_serialization",
        "description": "__getstate__() method",
    },
    "setstate": {
        "patterns": [r"def\s+__setstate__\s*\("],
        "category": "custom_serialization",
        "description": "__setstate__() method",
    },
    "reduce": {
        "patterns": [r"def\s+__reduce__(_ex)?\s*\("],
        "category": "custom_serialization",
        "description": "__reduce__() method",
    },
    "binary_file_read": {
        "patterns": [r"open\s*\([^)]*['\"]rb['\"]"],
        "category": "binary_io",
        "description": "open() for binary read",
    },
    "binary_file_write": {
        "patterns": [r"open\s*\([^)]*['\"]wb['\"]"],
        "category": "binary_io",
        "description": "open() for binary write",
    },
}

DATA_FILE_PATTERNS = [
    "*.pkl",
    "*.pickle",
    "*.marshal",
    "*.shelve",
    "*.db",
    "*.dat",
]


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


def classify_risk(category: str, context: Dict[str, Any]) -> str:
    """Classify risk level for a finding."""
    if category == "marshal":
        return "CRITICAL"

    if category == "pickle":
        if "cPickle" in str(context.get("text", "")):
            return "CRITICAL"
        if "without_encoding" in context and context["without_encoding"]:
            return "CRITICAL"
        return "HIGH"

    if category == "shelve":
        return "HIGH"

    if category == "yaml":
        if "unsafe" in context and context.get("unsafe"):
            return "CRITICAL"
        return "LOW"

    if category == "json":
        return "LOW"

    if category == "protobuf":
        return "LOW"

    if category == "msgpack":
        return "MEDIUM"

    if category == "struct":
        return "MEDIUM"

    if category == "custom_serialization":
        return "HIGH"

    if category == "binary_io":
        return "MEDIUM"

    return "MEDIUM"


# ── Detection Functions ──────────────────────────────────────────────────────

def detect_patterns_in_file(filepath: str) -> List[Dict[str, Any]]:
    """Scan file for serialization patterns using regex."""
    findings = []
    content = read_file(filepath)
    lines = content.split("\n")

    for pattern_name, pattern_info in SERIALIZATION_PATTERNS.items():
        for pattern_regex in pattern_info["patterns"]:
            for line_no, line in enumerate(lines, 1):
                if re.search(pattern_regex, line):
                    context = {
                        "text": line.strip(),
                        "line_number": line_no,
                    }

                    # Check for encoding parameter in pickle calls
                    if "pickle" in pattern_info["category"]:
                        if "load" in pattern_regex:
                            if "encoding=" not in line:
                                context["without_encoding"] = True

                    # Check for unsafe yaml.load
                    if "yaml" in pattern_name and "unsafe" in pattern_name:
                        context["unsafe"] = True

                    risk = classify_risk(pattern_info["category"], context)

                    findings.append({
                        "pattern": pattern_name,
                        "category": pattern_info["category"],
                        "description": pattern_info["description"],
                        "file": filepath,
                        "line": line_no,
                        "code": line.strip(),
                        "risk": risk,
                        "context": context,
                    })

    return findings


def detect_custom_serialization_ast(filepath: str) -> List[Dict[str, Any]]:
    """Use AST to detect custom __getstate__/__setstate__/__reduce__ methods."""
    findings = []
    content = read_file(filepath)

    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Fall back to regex (file has Py2-only syntax)
        return []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    if item.name in ("__getstate__", "__setstate__", "__reduce__", "__reduce_ex__"):
                        findings.append({
                            "pattern": item.name,
                            "category": "custom_serialization",
                            "description": f"{item.name}() method in class {node.name}",
                            "file": filepath,
                            "line": item.lineno,
                            "class_name": node.name,
                            "risk": "HIGH",
                        })

    return findings


def scan_filesystem(data_dirs: List[str]) -> List[Dict[str, Any]]:
    """Scan filesystem for persisted data files."""
    files = []

    for data_dir in data_dirs:
        if not os.path.isdir(data_dir):
            continue

        for root, dirs, filenames in os.walk(data_dir):
            for filename in filenames:
                for pattern in DATA_FILE_PATTERNS:
                    if fnmatch.fnmatch(filename, pattern):
                        filepath = os.path.join(root, filename)
                        try:
                            stat = os.stat(filepath)
                            files.append({
                                "path": filepath,
                                "filename": filename,
                                "size": stat.st_size,
                                "format": filename.split(".")[-1],
                            })
                        except OSError:
                            pass

    return files


def walk_codebase(root: str, exclude_patterns: List[str]) -> List[str]:
    """Walk codebase and find all .py files."""
    py_files = []

    for dirpath, dirnames, filenames in os.walk(root):
        # Skip excluded directories
        dirnames[:] = [
            d for d in dirnames
            if not should_skip(os.path.join(dirpath, d), exclude_patterns)
        ]

        for filename in filenames:
            if filename.endswith(".py"):
                filepath = os.path.join(dirpath, filename)
                if not should_skip(filepath, exclude_patterns):
                    py_files.append(filepath)

    return py_files


# ── Main Analysis ────────────────────────────────────────────────────────────

def analyze_codebase(codebase_path: str, target_version: str,
                    exclude_patterns: List[str],
                    data_dirs: Optional[List[str]] = None) -> Tuple[Dict, Dict]:
    """Analyze codebase for serialization patterns."""

    report = {
        "codebase": codebase_path,
        "target_version": target_version,
        "files_scanned": 0,
        "findings": [],
        "summary": {
            "total_findings": 0,
            "by_category": defaultdict(int),
            "by_risk": defaultdict(int),
            "critical_count": 0,
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
        },
        "data_files_found": [],
    }

    # Scan Python source files
    py_files = walk_codebase(codebase_path, exclude_patterns)

    for py_file in py_files:
        # Regex-based detection
        findings = detect_patterns_in_file(py_file)

        # AST-based detection for custom serialization
        findings.extend(detect_custom_serialization_ast(py_file))

        report["findings"].extend(findings)
        report["files_scanned"] += 1

        # Update summary
        for finding in findings:
            report["summary"]["total_findings"] += 1
            report["summary"]["by_category"][finding["category"]] += 1
            report["summary"]["by_risk"][finding["risk"]] += 1

            risk = finding["risk"]
            if risk == "CRITICAL":
                report["summary"]["critical_count"] += 1
            elif risk == "HIGH":
                report["summary"]["high_count"] += 1
            elif risk == "MEDIUM":
                report["summary"]["medium_count"] += 1
            else:
                report["summary"]["low_count"] += 1

    # Scan filesystem for data files if requested
    data_migration = {"steps": []}
    if data_dirs:
        data_files = scan_filesystem(data_dirs)
        report["data_files_found"] = data_files

        # Build data migration plan
        if data_files:
            data_migration["steps"].append({
                "step_number": 1,
                "action": "Audit pickle loading for encoding parameter",
                "affected_files": [
                    f["file"] for f in report["findings"]
                    if f["category"] == "pickle" and f["risk"] == "CRITICAL"
                ],
                "data_files": [f["path"] for f in data_files if f["format"] in ("pkl", "pickle")],
                "effort": "low",
            })

            if any(f["format"] == "shelve" for f in data_files):
                data_migration["steps"].append({
                    "step_number": 2,
                    "action": "Test shelve database compatibility with Py3",
                    "affected_files": [
                        f["file"] for f in report["findings"]
                        if f["category"] == "shelve"
                    ],
                    "data_files": [f["path"] for f in data_files if f["format"] == "shelve"],
                    "effort": "medium",
                })

    return report, data_migration


# ── Main Entry Point ────────────────────────────────────────────────────────

@log_execution
def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Serialization Boundary Detector for Py2→Py3 migration"
    )
    parser.add_argument("codebase_path", help="Root directory of Python 2 codebase")
    parser.add_argument("--target-version", default="3.12",
                       help="Target Python 3.x version (default: 3.12)")
    parser.add_argument("--exclude", nargs="*", default=["**/vendor/**", "**/.git/**"],
                       help="Glob patterns to exclude")
    parser.add_argument("--data-dirs", nargs="*",
                       help="Directories to scan for persisted data files")
    parser.add_argument("--output", default=".",
                       help="Output directory for reports")
    parser.add_argument("--state-file",
                       help="Path to migration-state.json for integration")

    args = parser.parse_args()

    if not os.path.isdir(args.codebase_path):
        print(f"Error: codebase path not found: {args.codebase_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning codebase: {args.codebase_path}")
    print(f"Target version: {args.target_version}")

    # Run analysis
    report, data_migration = analyze_codebase(
        args.codebase_path,
        args.target_version,
        args.exclude,
        args.data_dirs,
    )

    # Save outputs
    os.makedirs(args.output, exist_ok=True)

    report_path = os.path.join(args.output, "serialization-report.json")
    save_json(report, report_path)
    print(f"Wrote: {report_path}")

    migration_path = os.path.join(args.output, "data-migration-plan.json")
    save_json(data_migration, migration_path)
    print(f"Wrote: {migration_path}")

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Files scanned: {report['files_scanned']}")
    print(f"Total findings: {report['summary']['total_findings']}")
    print(f"  CRITICAL: {report['summary']['critical_count']}")
    print(f"  HIGH:     {report['summary']['high_count']}")
    print(f"  MEDIUM:   {report['summary']['medium_count']}")
    print(f"  LOW:      {report['summary']['low_count']}")

    if report["data_files_found"]:
        print(f"Data files found: {len(report['data_files_found'])}")
        for f in report["data_files_found"][:5]:
            print(f"  - {f['path']} ({f['size']} bytes)")
        if len(report["data_files_found"]) > 5:
            print(f"  ... and {len(report['data_files_found']) - 5} more")

    # Print findings by category
    if report["summary"]["by_category"]:
        print()
        print("Findings by category:")
        for cat in sorted(report["summary"]["by_category"].keys()):
            count = report["summary"]["by_category"][cat]
            print(f"  {cat}: {count}")

    sys.exit(0 if report["summary"]["critical_count"] == 0 else 1)


if __name__ == "__main__":
    main()
