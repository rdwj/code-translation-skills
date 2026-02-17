#!/usr/bin/env python3
"""
Behavioral Diff Generator — Main Diff Script

Runs test cases under both Python 2 and Python 3 interpreters, captures all
observable outputs, compares them, and classifies differences as expected
(known safe) or potential bugs (need investigation).

Usage:
    python3 generate_diffs.py <codebase_path> \
        --test-suite tests/ \
        --py2 /usr/bin/python2.7 \
        --py3 /usr/bin/python3.12 \
        --target-version 3.12 \
        --output ./behavioral-diff-output/ \
        [--state-file <migration-state.json>] \
        [--test-runner pytest] \
        [--timeout 60] \
        [--modules mod1.py,mod2.py] \
        [--capture-mode all] \
        [--expected-diffs-config expected.json]

Inputs:
  - codebase_path: Root directory of Python codebase
  - test-suite: Path to test directory or specific test file
  - py2/py3: Paths to Python 2 and Python 3 interpreters
  - target-version: Python 3.x target (e.g., 3.9, 3.12)

Outputs:
  - behavioral-diff-report.json: Every diff found, categorized
  - expected-differences.json: Diffs classified as known/acceptable
  - potential-bugs.json: Diffs that need investigation
  - py2-outputs.json: Raw captured outputs from Py2 runs
  - py3-outputs.json: Raw captured outputs from Py3 runs
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Type Definitions ────────────────────────────────────────────────────────

DiffCategory = str  # 'expected', 'potential_bug', 'unclassified'


# ── Expected Difference Patterns ────────────────────────────────────────────

DEFAULT_EXPECTED_PATTERNS = [
    {
        "name": "repr_unicode_prefix",
        "description": "u'...' prefix removed in Py3 repr output",
        "py2_regex": r"u'([^']*)'",
        "py3_equivalent": r"'\1'",
    },
    {
        "name": "repr_long_suffix",
        "description": "L suffix removed from long integers in Py3",
        "py2_regex": r"(\d+)L\b",
        "py3_equivalent": r"\1",
    },
    {
        "name": "repr_bytes_prefix",
        "description": "Bytes repr gains b'' prefix in Py3",
        "py2_regex": r"'(\\x[0-9a-fA-F]{2}[^']*)'",
        "py3_equivalent": r"b'\1'",
    },
    {
        "name": "dict_ordering",
        "description": "Dict key ordering may differ (Py2 arbitrary, Py3 insertion-ordered)",
        "type": "structural",
    },
    {
        "name": "range_repr",
        "description": "range() returns iterator in Py3 instead of list",
        "py2_regex": r"\[(\d+(?:,\s*\d+)*)\]",
        "type": "range_vs_list",
    },
    {
        "name": "map_filter_repr",
        "description": "map/filter/zip return iterators in Py3",
        "py2_regex": r"\[.*\]",
        "type": "iterator_vs_list",
    },
    {
        "name": "exception_message_wording",
        "description": "Exception message text may differ between Py2 and Py3",
        "type": "exception_text",
    },
    {
        "name": "bankers_rounding",
        "description": "round() uses banker's rounding in Py3 (IEEE 754)",
        "type": "rounding",
    },
    {
        "name": "print_function",
        "description": "print statement vs function output formatting",
        "py2_regex": r"\('([^']*)',\)",
        "py3_equivalent": r"\1",
    },
    {
        "name": "octal_repr",
        "description": "Octal repr changed from 0777 to 0o777",
        "py2_regex": r"\b0(\d{3,})\b",
        "py3_equivalent": r"0o\1",
    },
    {
        "name": "integer_division",
        "description": "Integer division: 7/2 returns 3 in Py2, 3.5 in Py3",
        "type": "division_semantics",
    },
    {
        "name": "mixed_type_sort",
        "description": "sorted() with mixed int/str raises TypeError in Py3 (allowed in Py2)",
        "type": "type_comparison",
    },
    {
        "name": "bytes_str_equality",
        "description": "b'x' == 'x' returns False in Py3 (True in Py2 in some contexts)",
        "type": "bytes_str_boundary",
    },
    {
        "name": "relative_import",
        "description": "Implicit relative imports fail in Py3 (must use explicit relative imports)",
        "type": "import_behavior",
    },
    {
        "name": "true_false_identity",
        "description": "True/False are singleton objects; identity checks work but equality is preferred",
        "type": "boolean_semantics",
    },
]


# ── Utility Functions ──────────────────────────────────────────────────────

def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file, exit with error message if missing."""
    p = Path(path)
    if not p.exists():
        print(f"Error: Required file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: str) -> None:
    """Save JSON file with nice formatting."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"Wrote {path}", file=sys.stdout)


# ── Test Discovery ──────────────────────────────────────────────────────────


def discover_tests(
    test_suite: str,
    test_runner: str,
    py3_interpreter: str,
    modules: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Discover test cases using the test runner's collection mechanism.

    Returns a list of test case descriptors with id, file, and name.
    """
    test_suite_path = Path(test_suite)
    tests = []

    if test_runner == "pytest":
        # Use pytest --collect-only to discover tests
        cmd = [py3_interpreter, "-m", "pytest", "--collect-only", "-q", str(test_suite_path)]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(test_suite_path.parent) if test_suite_path.is_file() else None,
            )
            for line in result.stdout.strip().split("\n"):
                line = line.strip()
                if "::" in line and not line.startswith("="):
                    parts = line.split("::")
                    test_file = parts[0] if parts else ""
                    test_name = "::".join(parts[1:]) if len(parts) > 1 else ""
                    tests.append({
                        "id": line,
                        "file": test_file,
                        "name": test_name,
                        "runner": "pytest",
                    })
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"Warning: pytest collection failed: {e}", file=sys.stderr)

    elif test_runner == "unittest":
        # Use unittest discover
        cmd = [py3_interpreter, "-m", "unittest", "discover", "-s", str(test_suite_path), "-v"]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )
            for line in result.stderr.split("\n"):
                match = re.match(r"(\S+)\s+\((\S+)\)", line)
                if match:
                    test_name = match.group(1)
                    test_module = match.group(2)
                    tests.append({
                        "id": f"{test_module}.{test_name}",
                        "file": test_module.replace(".", "/") + ".py",
                        "name": test_name,
                        "runner": "unittest",
                    })
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"Warning: unittest discovery failed: {e}", file=sys.stderr)

    # If collection failed, fall back to file-based discovery
    if not tests:
        print("Falling back to file-based test discovery...", file=sys.stdout)
        if test_suite_path.is_dir():
            for py_file in test_suite_path.rglob("test_*.py"):
                rel_path = str(py_file.relative_to(test_suite_path))
                tests.append({
                    "id": rel_path,
                    "file": rel_path,
                    "name": rel_path,
                    "runner": "file",
                })
        elif test_suite_path.is_file():
            tests.append({
                "id": str(test_suite_path),
                "file": str(test_suite_path),
                "name": test_suite_path.name,
                "runner": "file",
            })

    # Filter by modules if specified
    if modules:
        tests = [t for t in tests if any(m in t["file"] for m in modules)]

    return tests


# ── Test Execution ──────────────────────────────────────────────────────────


def execute_test(
    test: Dict[str, Any],
    interpreter: str,
    codebase_path: str,
    test_suite: str,
    test_runner: str,
    timeout: int = 60,
    capture_mode: str = "all",
) -> Dict[str, Any]:
    """
    Execute a single test case under the given interpreter.

    Returns captured output: returncode, stdout, stderr, duration, files.
    """
    result = {
        "test_id": test["id"],
        "interpreter": interpreter,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "duration_seconds": 0.0,
        "error": None,
        "files_written": [],
    }

    # Build command based on runner
    if test["runner"] == "pytest":
        cmd = [interpreter, "-m", "pytest", "-xvs", test["id"]]
    elif test["runner"] == "unittest":
        cmd = [interpreter, "-m", "unittest", test["id"]]
    else:
        # File-based: run the test file directly
        cmd = [interpreter, "-m", "pytest", "-xvs", test["file"]]

    # Create temp directory for file output capture
    with tempfile.TemporaryDirectory(prefix="behavdiff_") as tmpdir:
        env = os.environ.copy()
        env["BEHAVIORAL_DIFF_TMPDIR"] = tmpdir
        env["PYTHONPATH"] = codebase_path + os.pathsep + env.get("PYTHONPATH", "")
        # Ensure consistent encoding behavior
        env["PYTHONIOENCODING"] = "utf-8"
        # Disable hash randomization for reproducible dict ordering in Py3
        env["PYTHONHASHSEED"] = "0"

        start_time = time.monotonic()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=codebase_path,
                env=env,
            )
            elapsed = time.monotonic() - start_time

            result["returncode"] = proc.returncode
            result["duration_seconds"] = round(elapsed, 3)

            if capture_mode in ("stdout", "all"):
                result["stdout"] = proc.stdout
            if capture_mode in ("stderr", "all"):
                result["stderr"] = proc.stderr

            # Capture any files written to tmpdir
            if capture_mode in ("files", "all"):
                for root, dirs, files in os.walk(tmpdir):
                    for fname in files:
                        fpath = os.path.join(root, fname)
                        try:
                            with open(fpath, "r", encoding="utf-8") as f:
                                content = f.read()
                            result["files_written"].append({
                                "name": fname,
                                "content": content,
                                "binary": False,
                            })
                        except UnicodeDecodeError:
                            with open(fpath, "rb") as f:
                                content = f.read().hex()
                            result["files_written"].append({
                                "name": fname,
                                "content": content,
                                "binary": True,
                            })

        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start_time
            result["error"] = f"Timeout after {timeout}s"
            result["returncode"] = -1
            result["duration_seconds"] = round(elapsed, 3)
        except FileNotFoundError:
            result["error"] = f"Interpreter not found: {interpreter}"
            result["returncode"] = -2
        except Exception as e:
            result["error"] = str(e)
            result["returncode"] = -3

    return result


# ── Diff Comparison ─────────────────────────────────────────────────────────


def normalize_output(output: str) -> str:
    """
    Normalize output for comparison.

    Strips ANSI escape codes, normalizes whitespace, and removes
    non-deterministic elements (timestamps, memory addresses, PIDs).
    """
    # Strip ANSI escape codes
    output = re.sub(r"\x1b\[[0-9;]*m", "", output)
    # Normalize memory addresses (0x7f...)
    output = re.sub(r"0x[0-9a-fA-F]{6,16}", "0xADDRESS", output)
    # Normalize PIDs
    output = re.sub(r"pid[= ]+\d+", "pid=PID", output, flags=re.IGNORECASE)
    # Normalize timestamps (ISO format)
    output = re.sub(
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?",
        "TIMESTAMP",
        output,
    )
    # Normalize trailing whitespace per line
    output = "\n".join(line.rstrip() for line in output.split("\n"))
    # Normalize multiple blank lines
    output = re.sub(r"\n{3,}", "\n\n", output)
    return output.strip()


def apply_expected_patterns(
    py2_output: str,
    py3_output: str,
    patterns: List[Dict[str, Any]],
) -> Tuple[str, str, List[str]]:
    """
    Apply expected difference patterns to normalize both outputs.

    Returns (normalized_py2, normalized_py3, list of patterns applied).
    """
    patterns_applied = []

    for pattern in patterns:
        pattern_type = pattern.get("type", "regex")

        if pattern_type in ("structural", "range_vs_list", "iterator_vs_list",
                            "exception_text", "rounding"):
            # These patterns require structural comparison, not regex
            continue

        py2_regex = pattern.get("py2_regex")
        py3_equiv = pattern.get("py3_equivalent")

        if py2_regex and py3_equiv:
            # Normalize Py2 output to match Py3 format
            normalized = re.sub(py2_regex, py3_equiv, py2_output)
            if normalized != py2_output:
                py2_output = normalized
                patterns_applied.append(pattern["name"])

    return py2_output, py3_output, patterns_applied


def compare_outputs(
    py2_result: Dict[str, Any],
    py3_result: Dict[str, Any],
    expected_patterns: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Compare Py2 and Py3 outputs and classify differences.

    Returns a diff record with category, details, and evidence.
    """
    diffs = []
    test_id = py2_result["test_id"]

    # ── Return code comparison ──────────────────────────────────────────
    py2_rc = py2_result["returncode"]
    py3_rc = py3_result["returncode"]

    if py2_rc != py3_rc:
        if py2_rc == 0 and py3_rc != 0:
            category = "potential_bug"
            description = f"Py2 passes (rc={py2_rc}) but Py3 fails (rc={py3_rc})"
        elif py2_rc != 0 and py3_rc == 0:
            category = "expected"
            description = f"Py3 passes (rc={py3_rc}) but Py2 failed (rc={py2_rc})"
        else:
            category = "potential_bug"
            description = f"Both fail with different codes: Py2={py2_rc}, Py3={py3_rc}"

        diffs.append({
            "type": "returncode",
            "category": category,
            "description": description,
            "py2_value": py2_rc,
            "py3_value": py3_rc,
        })

    # ── Stdout comparison ───────────────────────────────────────────────
    py2_stdout = normalize_output(py2_result.get("stdout", ""))
    py3_stdout = normalize_output(py3_result.get("stdout", ""))

    if py2_stdout != py3_stdout:
        # Apply expected patterns to see if diff is known
        norm_py2, norm_py3, patterns_applied = apply_expected_patterns(
            py2_stdout, py3_stdout, expected_patterns
        )

        if norm_py2 == norm_py3:
            diffs.append({
                "type": "stdout",
                "category": "expected",
                "description": "Stdout differs only in known Py2/Py3 representation patterns",
                "patterns_matched": patterns_applied,
                "py2_length": len(py2_stdout),
                "py3_length": len(py3_stdout),
            })
        else:
            # Try structural comparison for dict/JSON output
            if _is_structural_diff(py2_stdout, py3_stdout):
                diffs.append({
                    "type": "stdout",
                    "category": "expected",
                    "description": "Stdout differs in dict/collection ordering (structural match)",
                    "py2_snippet": py2_stdout[:500],
                    "py3_snippet": py3_stdout[:500],
                })
            else:
                diffs.append({
                    "type": "stdout",
                    "category": "potential_bug",
                    "description": "Stdout differs between Py2 and Py3",
                    "py2_snippet": py2_stdout[:1000],
                    "py3_snippet": py3_stdout[:1000],
                    "patterns_checked": [p["name"] for p in expected_patterns],
                })

    # ── Stderr comparison ───────────────────────────────────────────────
    py2_stderr = normalize_output(py2_result.get("stderr", ""))
    py3_stderr = normalize_output(py3_result.get("stderr", ""))

    if py2_stderr != py3_stderr:
        # Stderr differences are often expected (deprecation warnings, etc.)
        if _is_warning_only_diff(py2_stderr, py3_stderr):
            diffs.append({
                "type": "stderr",
                "category": "expected",
                "description": "Stderr differs only in warning messages",
                "py2_snippet": py2_stderr[:500],
                "py3_snippet": py3_stderr[:500],
            })
        else:
            diffs.append({
                "type": "stderr",
                "category": "potential_bug",
                "description": "Stderr differs between Py2 and Py3",
                "py2_snippet": py2_stderr[:1000],
                "py3_snippet": py3_stderr[:1000],
            })

    # ── File output comparison ──────────────────────────────────────────
    py2_files = {f["name"]: f for f in py2_result.get("files_written", [])}
    py3_files = {f["name"]: f for f in py3_result.get("files_written", [])}

    all_files = set(py2_files.keys()) | set(py3_files.keys())
    for fname in sorted(all_files):
        if fname not in py2_files:
            diffs.append({
                "type": "file_output",
                "category": "potential_bug",
                "description": f"File '{fname}' written by Py3 but not Py2",
                "file": fname,
            })
        elif fname not in py3_files:
            diffs.append({
                "type": "file_output",
                "category": "potential_bug",
                "description": f"File '{fname}' written by Py2 but not Py3",
                "file": fname,
            })
        else:
            py2_content = py2_files[fname]["content"]
            py3_content = py3_files[fname]["content"]
            if py2_content != py3_content:
                # Check if it's a JSON file — compare structurally
                if fname.endswith(".json"):
                    try:
                        py2_parsed = json.loads(py2_content)
                        py3_parsed = json.loads(py3_content)
                        if py2_parsed == py3_parsed:
                            diffs.append({
                                "type": "file_output",
                                "category": "expected",
                                "description": f"File '{fname}' differs in formatting but semantically equal",
                                "file": fname,
                            })
                            continue
                    except (json.JSONDecodeError, TypeError):
                        pass

                diffs.append({
                    "type": "file_output",
                    "category": "potential_bug",
                    "description": f"File '{fname}' content differs between Py2 and Py3",
                    "file": fname,
                    "py2_size": len(py2_content),
                    "py3_size": len(py3_content),
                })

    # ── Duration comparison ─────────────────────────────────────────────
    py2_time = py2_result.get("duration_seconds", 0)
    py3_time = py3_result.get("duration_seconds", 0)

    if py2_time > 0 and py3_time > py2_time * 2:
        diffs.append({
            "type": "performance",
            "category": "potential_bug",
            "description": f"Py3 is {py3_time/py2_time:.1f}x slower than Py2",
            "py2_seconds": py2_time,
            "py3_seconds": py3_time,
        })

    return {
        "test_id": test_id,
        "diffs": diffs,
        "total_diffs": len(diffs),
        "expected_count": sum(1 for d in diffs if d["category"] == "expected"),
        "potential_bug_count": sum(1 for d in diffs if d["category"] == "potential_bug"),
        "has_unexpected_diffs": any(d["category"] == "potential_bug" for d in diffs),
    }


def _is_structural_diff(py2: str, py3: str) -> bool:
    """
    Check if two strings differ only in dict/set ordering.

    Tries to parse both as Python literals or JSON and compare structurally.
    """
    # Try JSON comparison
    try:
        py2_parsed = json.loads(py2)
        py3_parsed = json.loads(py3)
        return py2_parsed == py3_parsed
    except (json.JSONDecodeError, TypeError):
        pass

    # Try comparing sorted lines (catches dict repr differences)
    py2_lines = sorted(py2.split("\n"))
    py3_lines = sorted(py3.split("\n"))
    if py2_lines == py3_lines:
        return True

    return False


def _is_warning_only_diff(py2_stderr: str, py3_stderr: str) -> bool:
    """Check if stderr diff is only due to warning messages."""
    warning_patterns = [
        r"DeprecationWarning",
        r"FutureWarning",
        r"PendingDeprecationWarning",
        r"SyntaxWarning",
        r"RuntimeWarning",
        r"UserWarning",
        r"ResourceWarning",
    ]

    # Remove all warning lines and compare
    def strip_warnings(text: str) -> str:
        lines = text.split("\n")
        return "\n".join(
            line for line in lines
            if not any(re.search(p, line) for p in warning_patterns)
        )

    return strip_warnings(py2_stderr) == strip_warnings(py3_stderr)


# ── Report Generation ──────────────────────────────────────────────────────


def generate_report(
    test_comparisons: List[Dict[str, Any]],
    py2_outputs: List[Dict[str, Any]],
    py3_outputs: List[Dict[str, Any]],
    target_version: str,
    output_dir: Path,
) -> Dict[str, Any]:
    """Generate the full behavioral diff report."""
    total_tests = len(test_comparisons)
    tests_with_diffs = sum(1 for tc in test_comparisons if tc["total_diffs"] > 0)
    tests_with_bugs = sum(1 for tc in test_comparisons if tc["has_unexpected_diffs"])
    total_expected = sum(tc["expected_count"] for tc in test_comparisons)
    total_potential_bugs = sum(tc["potential_bug_count"] for tc in test_comparisons)

    # Categorize diffs by type
    diff_types = Counter()
    bug_types = Counter()
    unclassified_diffs = []

    for tc in test_comparisons:
        for diff in tc["diffs"]:
            diff_types[diff["type"]] += 1
            if diff["category"] == "potential_bug":
                bug_types[diff["type"]] += 1
            elif diff["category"] == "unclassified":
                unclassified_diffs.append({
                    "test_id": tc["test_id"],
                    "diff": diff,
                })

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_version": target_version,
        "summary": {
            "total_tests": total_tests,
            "tests_no_diffs": total_tests - tests_with_diffs,
            "tests_expected_diffs_only": tests_with_diffs - tests_with_bugs,
            "tests_with_potential_bugs": tests_with_bugs,
            "total_expected_diffs": total_expected,
            "total_potential_bugs": total_potential_bugs,
            "total_unclassified": len(unclassified_diffs),
            "pass_rate": (
                (total_tests - tests_with_bugs) / total_tests * 100
                if total_tests > 0
                else 0
            ),
        },
        "diff_types": dict(diff_types),
        "bug_types": dict(bug_types),
        "test_results": test_comparisons,
    }

    # Write main report
    save_json(report, str(output_dir / "behavioral-diff-report.json"))

    # Write expected differences
    expected = {
        "timestamp": report["timestamp"],
        "total": total_expected,
        "differences": [
            {
                "test_id": tc["test_id"],
                "diffs": [d for d in tc["diffs"] if d["category"] == "expected"],
            }
            for tc in test_comparisons
            if tc["expected_count"] > 0
        ],
    }
    save_json(expected, str(output_dir / "expected-differences.json"))

    # Write potential bugs
    bugs = {
        "timestamp": report["timestamp"],
        "total": total_potential_bugs,
        "bugs": [
            {
                "test_id": tc["test_id"],
                "diffs": [d for d in tc["diffs"] if d["category"] == "potential_bug"],
            }
            for tc in test_comparisons
            if tc["potential_bug_count"] > 0
        ],
    }
    save_json(bugs, str(output_dir / "potential-bugs.json"))

    # Write flagged for review (unclassified diffs for Sonnet analysis)
    if unclassified_diffs:
        flagged = {
            "timestamp": report["timestamp"],
            "total": len(unclassified_diffs),
            "note": "These diffs could not be automatically classified. Review needed.",
            "diffs": unclassified_diffs,
        }
        save_json(flagged, str(output_dir / "flagged-for-review.json"))

    # Write raw outputs
    save_json(py2_outputs, str(output_dir / "py2-outputs.json"))
    save_json(py3_outputs, str(output_dir / "py3-outputs.json"))

    return report


# ── Main ────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Behavioral Diff Generator for Python 2→3 migration verification"
    )
    parser.add_argument("codebase_path", help="Root directory of Python codebase")
    parser.add_argument(
        "--test-suite", required=True,
        help="Path to test suite directory or test file",
    )
    parser.add_argument(
        "--py2", required=True,
        help="Path to Python 2 interpreter",
    )
    parser.add_argument(
        "--py3", required=True,
        help="Path to Python 3 interpreter",
    )
    parser.add_argument(
        "--target-version", default="3.9",
        help="Target Python 3.x version (default: 3.9)",
    )
    parser.add_argument(
        "--state-file",
        help="Path to migration-state.json for recording results",
    )
    parser.add_argument(
        "--output", default="./behavioral-diff-output",
        help="Output directory for reports (default: ./behavioral-diff-output)",
    )
    parser.add_argument(
        "--test-runner", default="pytest",
        choices=["pytest", "unittest"],
        help="Test runner to use (default: pytest)",
    )
    parser.add_argument(
        "--timeout", type=int, default=60,
        help="Per-test timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--modules",
        help="Comma-separated list of specific modules to test",
    )
    parser.add_argument(
        "--capture-mode", default="all",
        choices=["stdout", "stderr", "returncode", "files", "all"],
        help="What to capture (default: all)",
    )
    parser.add_argument(
        "--expected-diffs-config",
        help="Path to JSON config listing known expected differences",
    )

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    modules = args.modules.split(",") if args.modules else None

    # Load expected patterns
    expected_patterns = DEFAULT_EXPECTED_PATTERNS.copy()
    if args.expected_diffs_config:
        user_config = load_json(args.expected_diffs_config)
        expected_patterns.extend(user_config.get("expected_patterns", []))

    # ── Step 1: Discover Tests ──────────────────────────────────────────
    print("\n# ── Discovering Tests ─────────────────────────────────────────", file=sys.stdout)

    tests = discover_tests(args.test_suite, args.test_runner, args.py3, modules)
    print(f"Discovered {len(tests)} test cases", file=sys.stdout)

    if not tests:
        print("Error: No tests discovered. Check test suite path and runner.", file=sys.stderr)
        sys.exit(1)

    # ── Step 2: Execute Under Both Interpreters ─────────────────────────
    print("\n# ── Executing Tests Under Both Interpreters ────────────────────", file=sys.stdout)

    py2_outputs = []
    py3_outputs = []
    comparisons = []

    for i, test in enumerate(tests, 1):
        test_id = test["id"]
        print(f"  [{i}/{len(tests)}] {test_id}", file=sys.stdout, end="", flush=True)

        # Execute under Py2
        py2_result = execute_test(
            test, args.py2, args.codebase_path, args.test_suite,
            args.test_runner, args.timeout, args.capture_mode,
        )
        py2_outputs.append(py2_result)

        # Execute under Py3
        py3_result = execute_test(
            test, args.py3, args.codebase_path, args.test_suite,
            args.test_runner, args.timeout, args.capture_mode,
        )
        py3_outputs.append(py3_result)

        # Compare
        comparison = compare_outputs(py2_result, py3_result, expected_patterns)
        comparisons.append(comparison)

        # Print status
        if comparison["has_unexpected_diffs"]:
            print(f" — ⚠ {comparison['potential_bug_count']} potential bug(s)", file=sys.stdout)
        elif comparison["total_diffs"] > 0:
            print(f" — ✓ {comparison['expected_count']} expected diff(s)", file=sys.stdout)
        else:
            print(" — ✓ identical", file=sys.stdout)

    # ── Step 3: Generate Reports ────────────────────────────────────────
    print("\n# ── Generating Reports ───────────────────────────────────────", file=sys.stdout)

    report = generate_report(
        comparisons, py2_outputs, py3_outputs,
        args.target_version, output_dir,
    )

    # ── Step 4: Update State File ───────────────────────────────────────
    if args.state_file and Path(args.state_file).exists():
        print("\n# ── Updating State File ──────────────────────────────────────", file=sys.stdout)
        try:
            state = load_json(args.state_file)
            state.setdefault("skill_outputs", {})
            state["skill_outputs"]["behavioral_diff_generator"] = {
                "timestamp": report["timestamp"],
                "total_tests": report["summary"]["total_tests"],
                "potential_bugs": report["summary"]["total_potential_bugs"],
                "expected_diffs": report["summary"]["total_expected_diffs"],
                "pass_rate": report["summary"]["pass_rate"],
                "report_path": str(output_dir / "behavioral-diff-report.json"),
            }
            save_json(state, args.state_file)
        except Exception as e:
            print(f"Warning: Could not update state file: {e}", file=sys.stderr)

    # ── Summary ─────────────────────────────────────────────────────────
    summary = report["summary"]
    print("\n# ── Summary ─────────────────────────────────────────────────", file=sys.stdout)
    print(f"Total tests:           {summary['total_tests']}", file=sys.stdout)
    print(f"No diffs:              {summary['tests_no_diffs']}", file=sys.stdout)
    print(f"Expected diffs only:   {summary['tests_expected_diffs_only']}", file=sys.stdout)
    print(f"Potential bugs:        {summary['tests_with_potential_bugs']}", file=sys.stdout)
    print(f"Pass rate:             {summary['pass_rate']:.1f}%", file=sys.stdout)
    print(f"\nReports written to {output_dir}", file=sys.stdout)

    if summary["total_potential_bugs"] > 0:
        print(
            f"\n⚠ {summary['total_potential_bugs']} potential bugs found — "
            "review potential-bugs.json",
            file=sys.stdout,
        )

    print("\nDone.", file=sys.stdout)


if __name__ == "__main__":
    main()
