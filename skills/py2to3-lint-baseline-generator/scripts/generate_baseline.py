#!/usr/bin/env python3
"""
Lint Baseline Generator — Main Baseline Script

Runs discovery linters (pylint --py3k, pyupgrade, flake8+flake8-2020) against
a Python 2 codebase and produces a comprehensive baseline report.

Produces:
  - lint-baseline.json — all findings categorized with per-module scores
  - lint-config/       — starter linter configuration files

Usage:
    python3 generate_baseline.py <codebase_path> \
        --output <output_dir> \
        --target-version 3.12 \
        [--exclude "**/vendor/**" "**/test/**"]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Linter Detection
# ═══════════════════════════════════════════════════════════════════════════

def check_linter(name: str, version_flag: str = "--version") -> Optional[str]:
    """Check if a linter is available and return its version string."""
    try:
        result = subprocess.run(
            [name, version_flag],
            capture_output=True, text=True, timeout=10,
        )
        version_text = (result.stdout + result.stderr).strip().split("\n")[0]
        return version_text
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def detect_linters() -> Dict[str, Optional[str]]:
    """Detect which linters are available."""
    linters = {
        "pylint": check_linter("pylint"),
        "pyupgrade": check_linter("pyupgrade"),
        "flake8": check_linter("flake8"),
    }
    return linters


def pyupgrade_flag_for_version(target: str) -> str:
    """Map a target version like '3.12' to a pyupgrade flag like '--py312-plus'."""
    parts = target.split(".")
    if len(parts) >= 2:
        major, minor = parts[0], parts[1]
        return f"--py{major}{minor}-plus"
    return "--py3-plus"


# ═══════════════════════════════════════════════════════════════════════════
# File Discovery
# ═══════════════════════════════════════════════════════════════════════════

def discover_python_files(
    codebase_path: str,
    exclude_patterns: Optional[List[str]] = None,
) -> List[str]:
    """Find all .py files in the codebase, respecting excludes."""
    root = Path(codebase_path).resolve()
    excludes = exclude_patterns or []
    files = []

    for py_file in root.rglob("*.py"):
        rel = str(py_file.relative_to(root))
        skip = False
        for pattern in excludes:
            # Simple glob matching
            import fnmatch
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(str(py_file), pattern):
                skip = True
                break
        if not skip:
            files.append(str(py_file))

    return sorted(files)


def count_lines(filepath: str) -> int:
    """Count non-blank lines in a file."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for line in f if line.strip())
    except IOError:
        return 0


# ═══════════════════════════════════════════════════════════════════════════
# Pylint Runner
# ═══════════════════════════════════════════════════════════════════════════

# pylint --py3k message codes and their categories
PYLINT_PY3K_CATEGORIES = {
    "W1601": ("syntax", True),       # print statement
    "W1602": ("syntax", True),        # backtick repr
    "W1603": ("semantic", False),     # __cmp__ method
    "W1604": ("semantic", False),     # __nonzero__ method
    "W1605": ("semantic", False),     # __getslice__ method
    "W1606": ("syntax", True),        # exec statement
    "W1607": ("syntax", True),        # <> operator
    "W1608": ("syntax", True),        # long builtin
    "W1609": ("syntax", True),        # raw_input
    "W1610": ("syntax", True),        # reduce to functools
    "W1611": ("syntax", True),        # xrange
    "W1612": ("semantic", True),      # dict.has_key
    "W1613": ("semantic", True),      # dict.iteritems
    "W1614": ("semantic", True),      # dict.iterkeys
    "W1615": ("semantic", True),      # dict.itervalues
    "W1616": ("semantic", True),      # dict.viewitems
    "W1617": ("semantic", True),      # dict.viewkeys
    "W1618": ("semantic", True),      # dict.viewvalues
    "W1619": ("semantic", False),     # division
    "W1620": ("import", True),        # relative import
    "W1621": ("stdlib", True),        # renamed module
    "W1622": ("stdlib", True),        # removed module
    "W1623": ("semantic", False),     # __unicode__ method
    "W1624": ("semantic", False),     # metaclass
    "W1625": ("syntax", True),        # exception comma syntax
    "W1626": ("syntax", True),        # long suffix
    "W1627": ("syntax", True),        # octal literal
    "W1628": ("semantic", True),      # sort cmp
    "W1629": ("semantic", True),      # map/filter/zip
    "W1630": ("semantic", True),      # old-style raise
    "W1631": ("semantic", True),      # apply
    "W1632": ("import", True),        # input renamed
    "W1633": ("semantic", False),     # round builtin changed
    "W1634": ("import", True),        # intern moved
    "W1635": ("import", True),        # coerce removed
    "W1636": ("import", True),        # execfile removed
    "W1637": ("import", True),        # file removed
    "W1638": ("import", True),        # reload moved
    "W1639": ("semantic", True),      # dict.items returns view
    "W1640": ("semantic", True),      # unpacking in list comp
    "W1641": ("semantic", False),     # eq without hash
    "W1642": ("semantic", False),     # div method
    "W1643": ("semantic", False),     # idiv method
    "W1644": ("semantic", False),     # rdiv method
    "W1645": ("semantic", False),     # exception message attr
    "W1646": ("semantic", True),      # invalid encoded data
    "W1647": ("compat", True),        # sys.maxint
    "W1648": ("import", True),        # module moved
    "W1649": ("import", True),        # string renamed
    "W1650": ("import", True),        # unichr renamed
    "W1651": ("import", True),        # StandardError removed
    "W1652": ("import", True),        # unicode builtin
    "W1653": ("import", True),        # buffer removed
    "W1654": ("syntax", True),        # raising not implemented
    "W1655": ("syntax", True),        # parameter unpacking
    "W1656": ("import", True),        # cmp function removed
    "W1657": ("import", True),        # deprecated string functions
    "W1658": ("semantic", False),     # comparison method
    "W1659": ("semantic", False),     # object.__init__ changes
    "W1660": ("semantic", False),     # next method
    "W1661": ("syntax", True),        # non-ASCII in import
    "W1662": ("semantic", False),     # exception chaining
}


def run_pylint_py3k(
    files: List[str],
    codebase_path: str,
) -> List[Dict[str, Any]]:
    """Run pylint --py3k and parse findings."""
    findings = []

    # Run in batches to avoid command-line length limits
    batch_size = 50
    for i in range(0, len(files), batch_size):
        batch = files[i : i + batch_size]
        try:
            result = subprocess.run(
                ["pylint", "--py3k", "--output-format=json"] + batch,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=codebase_path,
            )
            # pylint returns non-zero on findings (which is expected)
            output = result.stdout.strip()
            if output:
                try:
                    raw_findings = json.loads(output)
                except json.JSONDecodeError:
                    # Try to extract JSON array from mixed output
                    match = re.search(r"\[.*\]", output, re.DOTALL)
                    if match:
                        raw_findings = json.loads(match.group())
                    else:
                        continue

                for f in raw_findings:
                    code = f.get("message-id", f.get("symbol", ""))
                    cat_info = PYLINT_PY3K_CATEGORIES.get(code, ("compat", False))
                    findings.append({
                        "linter": "pylint",
                        "code": code,
                        "symbol": f.get("symbol", ""),
                        "category": cat_info[0],
                        "automatable": cat_info[1],
                        "severity": _pylint_severity(f.get("type", "warning")),
                        "file": f.get("path", f.get("module", "")),
                        "line": f.get("line", 0),
                        "column": f.get("column", 0),
                        "message": f.get("message", ""),
                    })
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"  Warning: pylint batch failed: {e}", file=sys.stderr)

    return findings


def _pylint_severity(pylint_type: str) -> str:
    """Map pylint message types to our severity levels."""
    return {
        "error": "error",
        "fatal": "error",
        "warning": "warning",
        "convention": "convention",
        "refactor": "convention",
        "information": "info",
    }.get(pylint_type.lower(), "warning")


# ═══════════════════════════════════════════════════════════════════════════
# Pyupgrade Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_pyupgrade(
    files: List[str],
    target_version: str,
) -> List[Dict[str, Any]]:
    """Run pyupgrade in dry-run mode and parse findings."""
    findings = []
    flag = pyupgrade_flag_for_version(target_version)

    for filepath in files:
        try:
            result = subprocess.run(
                ["pyupgrade", flag, filepath],
                capture_output=True,
                text=True,
                timeout=30,
            )
            # pyupgrade prints diffs to stdout when it would change something
            if result.returncode != 0 and result.stdout.strip():
                # Parse the diff output to extract findings
                diff_lines = result.stdout.strip().split("\n")
                for line in diff_lines:
                    if line.startswith("-") and not line.startswith("---"):
                        findings.append({
                            "linter": "pyupgrade",
                            "code": "UP000",
                            "category": "syntax",
                            "automatable": True,
                            "severity": "convention",
                            "file": filepath,
                            "line": 0,
                            "message": f"pyupgrade would rewrite: {line[1:].strip()[:120]}",
                        })
            elif result.returncode != 0 and result.stderr.strip():
                # Some versions output to stderr
                pass
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    return findings


# ═══════════════════════════════════════════════════════════════════════════
# Flake8 Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_flake8(
    files: List[str],
    codebase_path: str,
) -> List[Dict[str, Any]]:
    """Run flake8 and parse findings."""
    findings = []

    batch_size = 50
    for i in range(0, len(files), batch_size):
        batch = files[i : i + batch_size]
        try:
            result = subprocess.run(
                [
                    "flake8",
                    "--format=json",
                    "--select=YTT",  # flake8-2020 codes
                    "--max-line-length=120",
                ] + batch,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=codebase_path,
            )
            output = result.stdout.strip()
            if output:
                try:
                    raw = json.loads(output)
                    # flake8 JSON output varies by formatter
                    if isinstance(raw, dict):
                        for filepath, file_findings in raw.items():
                            for f in file_findings:
                                findings.append({
                                    "linter": "flake8",
                                    "code": f.get("code", ""),
                                    "category": "compat",
                                    "automatable": False,
                                    "severity": "warning",
                                    "file": filepath,
                                    "line": f.get("line_number", f.get("line", 0)),
                                    "column": f.get("column_number", f.get("col", 0)),
                                    "message": f.get("text", f.get("message", "")),
                                })
                except json.JSONDecodeError:
                    # Fall back to parsing default output format
                    _parse_flake8_text(output, findings)
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            print(f"  Warning: flake8 batch failed: {e}", file=sys.stderr)

    return findings


def _parse_flake8_text(output: str, findings: List[Dict[str, Any]]) -> None:
    """Parse flake8 default text output: path:line:col: CODE message."""
    pattern = re.compile(r"^(.+?):(\d+):(\d+): (\w+) (.+)$", re.MULTILINE)
    for match in pattern.finditer(output):
        findings.append({
            "linter": "flake8",
            "code": match.group(4),
            "category": "compat",
            "automatable": False,
            "severity": "warning",
            "file": match.group(1),
            "line": int(match.group(2)),
            "column": int(match.group(3)),
            "message": match.group(5),
        })


# ═══════════════════════════════════════════════════════════════════════════
# Scoring and Analysis
# ═══════════════════════════════════════════════════════════════════════════

SEVERITY_WEIGHTS = {
    "error": 4,
    "warning": 2,
    "convention": 1,
    "info": 0.5,
}


def compute_module_scores(
    findings: List[Dict[str, Any]],
    file_line_counts: Dict[str, int],
    codebase_path: str,
) -> Dict[str, Dict[str, Any]]:
    """Compute per-module lint scores."""
    # Group findings by file
    by_file: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for f in findings:
        filepath = f.get("file", "")
        # Normalize to relative path
        try:
            rel = str(Path(filepath).relative_to(Path(codebase_path).resolve()))
        except ValueError:
            rel = filepath
        by_file[rel].append(f)

    scores = {}
    for rel_path, loc in file_line_counts.items():
        file_findings = by_file.get(rel_path, [])
        total_findings = len(file_findings)
        loc = max(loc, 1)  # avoid division by zero

        # Weighted penalty
        penalty = 0
        automatable_count = 0
        by_severity = defaultdict(int)
        by_category = defaultdict(int)

        for f in file_findings:
            sev = f.get("severity", "warning")
            weight = SEVERITY_WEIGHTS.get(sev, 1)
            penalty += weight
            by_severity[sev] += 1
            by_category[f.get("category", "other")] += 1
            if f.get("automatable"):
                automatable_count += 1

        # Score: 100 minus penalty-per-100-lines, floored at 0
        raw_penalty = (penalty / loc) * 100
        score = max(0, round(100 - raw_penalty))

        automatable_pct = (
            round(automatable_count / total_findings * 100) if total_findings > 0 else 100
        )

        scores[rel_path] = {
            "score": score,
            "total_findings": total_findings,
            "lines_of_code": loc,
            "findings_per_100_loc": round(total_findings / loc * 100, 1),
            "automatable_count": automatable_count,
            "automatable_percent": automatable_pct,
            "by_severity": dict(by_severity),
            "by_category": dict(by_category),
        }

    return scores


def generate_priority_list(
    scores: Dict[str, Dict[str, Any]],
    dep_graph: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Generate a prioritized fix list, gateway modules first."""
    # Compute fan-in from dependency graph if available
    fan_in: Dict[str, int] = {}
    if dep_graph:
        edges = dep_graph.get("edges", [])
        for edge in edges:
            target = edge.get("target", edge.get("to", ""))
            fan_in[target] = fan_in.get(target, 0) + 1

    priority_list = []
    for path, score_data in scores.items():
        if score_data["total_findings"] == 0:
            continue
        priority_list.append({
            "module": path,
            "score": score_data["score"],
            "total_findings": score_data["total_findings"],
            "automatable_percent": score_data["automatable_percent"],
            "fan_in": fan_in.get(path, 0),
            "priority_score": _compute_priority(score_data, fan_in.get(path, 0)),
        })

    # Sort by priority score (higher = fix first)
    priority_list.sort(key=lambda x: x["priority_score"], reverse=True)
    return priority_list


def _compute_priority(score_data: Dict[str, Any], fan_in: int) -> float:
    """Compute a priority score: gateway modules with many fixable issues rank highest."""
    findings = score_data["total_findings"]
    automatable_pct = score_data["automatable_percent"]
    # Blend: high fan-in (gateway), many findings, high automatable fraction
    return (fan_in + 1) * findings * (automatable_pct / 100 + 0.5)


# ═══════════════════════════════════════════════════════════════════════════
# Config Generation
# ═══════════════════════════════════════════════════════════════════════════

def generate_lint_configs(
    output_dir: str,
    exclude_patterns: Optional[List[str]] = None,
    target_version: str = "3.9",
) -> None:
    """Generate starter linter configuration files."""
    config_dir = os.path.join(output_dir, "lint-config")
    os.makedirs(config_dir, exist_ok=True)

    excludes = exclude_patterns or ["vendor", "third_party", ".git", "__pycache__"]
    exclude_str = ",".join(excludes)

    # pylintrc
    pylintrc = f"""[MASTER]
ignore-patterns={exclude_str}
load-plugins=

[MESSAGES CONTROL]
# Start with py3k checks enabled
enable=py3k

[FORMAT]
max-line-length=120
"""
    with open(os.path.join(config_dir, "pylintrc"), "w") as f:
        f.write(pylintrc)

    # setup.cfg (flake8)
    setup_cfg = f"""[flake8]
max-line-length = 120
exclude = {exclude_str}
select = YTT
# Add more flake8 plugins as migration progresses:
# extend-select = UP  (pyupgrade via flake8)
"""
    with open(os.path.join(config_dir, "setup.cfg"), "w") as f:
        f.write(setup_cfg)

    # pyproject.toml
    py_flag = pyupgrade_flag_for_version(target_version)
    pyproject = f"""[tool.pyupgrade]
# Run with: pyupgrade {py_flag} <file>
# This is a reference config; pyupgrade is primarily CLI-driven.

[tool.pylint."messages control"]
enable = "py3k"

[tool.pylint.format]
max-line-length = 120
"""
    with open(os.path.join(config_dir, "pyproject.toml"), "w") as f:
        f.write(pyproject)


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate a lint baseline for a Python 2→3 migration."
    )
    parser.add_argument("codebase_path", help="Root directory of the Python 2 codebase")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument(
        "--target-version", default="3.9",
        help="Target Python 3 version (default: 3.9)",
    )
    parser.add_argument(
        "--exclude", nargs="*", default=None,
        help="Glob patterns for files/directories to exclude",
    )
    parser.add_argument(
        "--dep-graph", default=None,
        help="Path to dependency-graph.json (for priority scoring)",
    )

    args = parser.parse_args()
    codebase_path = os.path.abspath(args.codebase_path)

    if not os.path.isdir(codebase_path):
        print(f"Error: Not a directory: {codebase_path}", file=sys.stderr)
        sys.exit(1)

    # Detect available linters
    print("Detecting linters...")
    available = detect_linters()
    for name, version in available.items():
        if version:
            print(f"  {name}: {version}")
        else:
            print(f"  {name}: NOT FOUND (will be skipped)")

    if not any(available.values()):
        print("Error: No linters found. Install at least one:", file=sys.stderr)
        print("  pip install pylint pyupgrade flake8 flake8-2020", file=sys.stderr)
        sys.exit(1)

    # Discover files
    print(f"\nDiscovering Python files in {codebase_path}...")
    files = discover_python_files(codebase_path, args.exclude)
    print(f"  Found {len(files)} .py files")

    if not files:
        print("No Python files found. Check the path and exclude patterns.", file=sys.stderr)
        sys.exit(1)

    # Count lines per file (for scoring)
    file_line_counts: Dict[str, int] = {}
    for filepath in files:
        try:
            rel = str(Path(filepath).relative_to(Path(codebase_path).resolve()))
        except ValueError:
            rel = filepath
        file_line_counts[rel] = count_lines(filepath)

    # Run linters
    all_findings: List[Dict[str, Any]] = []

    if available.get("pylint"):
        print("\nRunning pylint --py3k...")
        pylint_findings = run_pylint_py3k(files, codebase_path)
        print(f"  {len(pylint_findings)} findings")
        all_findings.extend(pylint_findings)

    if available.get("pyupgrade"):
        print(f"\nRunning pyupgrade {pyupgrade_flag_for_version(args.target_version)}...")
        pyupgrade_findings = run_pyupgrade(files, args.target_version)
        print(f"  {len(pyupgrade_findings)} findings")
        all_findings.extend(pyupgrade_findings)

    if available.get("flake8"):
        print("\nRunning flake8 (YTT checks)...")
        flake8_findings = run_flake8(files, codebase_path)
        print(f"  {len(flake8_findings)} findings")
        all_findings.extend(flake8_findings)

    # Compute scores
    print("\nComputing per-module scores...")
    scores = compute_module_scores(all_findings, file_line_counts, codebase_path)

    # Generate priority list
    dep_graph = None
    if args.dep_graph:
        dep_graph_path = args.dep_graph
        if os.path.exists(dep_graph_path):
            with open(dep_graph_path, "r") as f:
                dep_graph = json.load(f)

    priority_list = generate_priority_list(scores, dep_graph)

    # Aggregate statistics
    total_findings = len(all_findings)
    by_linter = defaultdict(int)
    by_category = defaultdict(int)
    by_severity = defaultdict(int)
    automatable_total = 0
    for f in all_findings:
        by_linter[f.get("linter", "unknown")] += 1
        by_category[f.get("category", "other")] += 1
        by_severity[f.get("severity", "unknown")] += 1
        if f.get("automatable"):
            automatable_total += 1

    # Build the baseline report
    baseline = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "codebase_path": codebase_path,
        "target_version": args.target_version,
        "files_scanned": len(files),
        "total_lines": sum(file_line_counts.values()),
        "linters_used": {k: v for k, v in available.items() if v},
        "total_findings": total_findings,
        "automatable_count": automatable_total,
        "automatable_percent": (
            round(automatable_total / total_findings * 100, 1)
            if total_findings > 0
            else 100
        ),
        "by_linter": dict(by_linter),
        "by_category": dict(by_category),
        "by_severity": dict(by_severity),
        "module_scores": scores,
        "priority_list": priority_list,
        "findings": all_findings,
    }

    # Write outputs
    os.makedirs(args.output, exist_ok=True)
    output_path = os.path.join(args.output, "lint-baseline.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)
    print(f"\nBaseline written to {output_path}")

    # Generate configs
    generate_lint_configs(args.output, args.exclude, args.target_version)
    print(f"Lint configs written to {os.path.join(args.output, 'lint-config/')}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Lint Baseline Summary")
    print(f"{'='*60}")
    print(f"Files scanned:  {len(files)}")
    print(f"Total findings: {total_findings}")
    print(f"Automatable:    {automatable_total} ({baseline['automatable_percent']}%)")
    print(f"By linter:      {dict(by_linter)}")
    print(f"By severity:    {dict(by_severity)}")
    print(f"By category:    {dict(by_category)}")
    if priority_list:
        print(f"\nTop 5 priority modules:")
        for item in priority_list[:5]:
            print(
                f"  {item['module']}: score {item['score']}, "
                f"{item['total_findings']} findings, "
                f"fan-in {item['fan_in']}"
            )


if __name__ == "__main__":
    main()
