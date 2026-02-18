#!/usr/bin/env python3
"""
Performance Benchmarker

Compares performance between Python 2 and Python 3 execution. Runs benchmarks
under both interpreters, applies statistical analysis, and flags regressions.

Usage:
    python3 benchmark.py <codebase_path> \
        --py2 /usr/bin/python2.7 \
        --py3 /usr/bin/python3.12 \
        --target-version 3.12 \
        [--benchmark-suite <bench_dir>] \
        [--iterations 5] \
        [--warmup 2] \
        [--threshold 10.0] \
        [--timeout 300] \
        [--output <output_dir>]

Inputs:
    codebase_path             Root directory of the Python codebase
    --py2                     Path to Python 2 interpreter
    --py3                     Path to Python 3 interpreter
    --target-version          Target Python 3.x version (3.9, 3.11, 3.12, 3.13)
    --benchmark-suite         Path to benchmark scripts directory (optional)
    --iterations              Number of timed runs per benchmark (default: 5)
    --warmup                  Number of warmup runs (default: 2)
    --threshold               Regression threshold percentage (default: 10.0)
    --timeout                 Per-benchmark timeout in seconds (default: 300)
    --modules                 Specific modules to benchmark (optional)
    --state-file              Path to migration-state.json (optional)
    --output                  Output directory (default: ./performance-output)

Outputs:
    performance-report.json          Benchmark results with statistics
    optimization-opportunities.json  Py3-specific speedup suggestions
"""

import argparse
import ast
import json
import math
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

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
    """Read file content."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            return f.read()


# ── Benchmark Discovery ──────────────────────────────────────────────────────

def discover_benchmarks(
    codebase_path: str,
    benchmark_suite: Optional[str] = None,
    modules: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Discover benchmark scripts and test files."""
    root = Path(codebase_path)
    benchmarks = []

    # 1. If a benchmark suite is provided, scan it
    if benchmark_suite:
        suite_path = Path(benchmark_suite)
        if suite_path.is_dir():
            for f in sorted(suite_path.rglob("*.py")):
                if _is_benchmark_file(str(f)):
                    benchmarks.append({
                        "id": str(f.relative_to(root)),
                        "path": str(f),
                        "type": "benchmark_file",
                        "source": "benchmark_suite",
                    })
        elif suite_path.is_file():
            benchmarks.append({
                "id": str(suite_path.relative_to(root)),
                "path": str(suite_path),
                "type": "benchmark_file",
                "source": "benchmark_suite",
            })

    # 2. Scan codebase for benchmark files
    skip_dirs = {
        ".git", ".hg", "__pycache__", ".tox", "node_modules",
        "venv", ".venv", "env", ".env", "build", "dist",
    }

    search_dirs = [root]
    if modules:
        search_dirs = [root / m for m in modules]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(search_dir):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                if fn.endswith(".py") and _is_benchmark_file(fn):
                    full_path = os.path.join(dirpath, fn)
                    rel_path = os.path.relpath(full_path, root)
                    # Avoid duplicates from benchmark_suite
                    if not any(b["path"] == full_path for b in benchmarks):
                        benchmarks.append({
                            "id": rel_path,
                            "path": full_path,
                            "type": "benchmark_file",
                            "source": "codebase_scan",
                        })

    # 3. Scan test files for benchmark markers
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(search_dir):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                if fn.startswith("test_") and fn.endswith(".py"):
                    full_path = os.path.join(dirpath, fn)
                    try:
                        content = read_file(full_path)
                        if "benchmark" in content.lower() or "@pytest.mark.benchmark" in content:
                            rel_path = os.path.relpath(full_path, root)
                            benchmarks.append({
                                "id": rel_path,
                                "path": full_path,
                                "type": "test_with_benchmark",
                                "source": "test_scan",
                            })
                    except Exception:
                        pass

    return benchmarks


def _is_benchmark_file(filename: str) -> bool:
    """Check if a filename looks like a benchmark script."""
    name = os.path.basename(filename).lower()
    return (
        name.startswith("bench_")
        or name.startswith("benchmark_")
        or name.endswith("_benchmark.py")
        or name.endswith("_bench.py")
        or name == "benchmarks.py"
    )


# ── Benchmark Execution ─────────────────────────────────────────────────────

# Wrapper script template that times execution and reports JSON
TIMING_WRAPPER = '''
import json
import sys
import time
import os

# The actual benchmark script path
benchmark_path = {benchmark_path!r}

# Warmup flag
is_warmup = {is_warmup!r}

# Capture timing
start_wall = time.time()
try:
    start_cpu = time.process_time() if hasattr(time, 'process_time') else time.clock()
except AttributeError:
    start_cpu = time.time()

# Memory tracking (best effort)
try:
    import resource
    mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
except ImportError:
    mem_before = 0

# Execute the benchmark
exit_code = 0
error_msg = ""
try:
    # Add benchmark directory to path
    sys.path.insert(0, os.path.dirname(benchmark_path))
    with open(benchmark_path, 'r') as f:
        code = f.read()
    exec(compile(code, benchmark_path, 'exec'))
except SystemExit as e:
    exit_code = e.code if isinstance(e.code, int) else 1
except Exception as e:
    exit_code = 1
    error_msg = str(e)[:500]

end_wall = time.time()
try:
    end_cpu = time.process_time() if hasattr(time, 'process_time') else time.clock()
except AttributeError:
    end_cpu = time.time()

try:
    import resource
    mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
except ImportError:
    mem_after = 0

result = {{
    "wall_seconds": end_wall - start_wall,
    "cpu_seconds": end_cpu - start_cpu,
    "peak_memory_kb": mem_after,
    "memory_delta_kb": mem_after - mem_before,
    "exit_code": exit_code,
    "error": error_msg,
    "is_warmup": is_warmup,
}}

# Write result as JSON to a temp file
result_path = {result_path!r}
with open(result_path, 'w') as f:
    json.dump(result, f)
'''


def execute_benchmark(
    benchmark: Dict[str, Any],
    interpreter: str,
    interpreter_label: str,
    iterations: int,
    warmup: int,
    timeout: int,
    codebase_path: str,
) -> Dict[str, Any]:
    """Execute a benchmark under the given interpreter."""
    benchmark_path = benchmark["path"]
    benchmark_id = benchmark["id"]

    results = {
        "benchmark_id": benchmark_id,
        "interpreter": interpreter,
        "interpreter_label": interpreter_label,
        "iterations": iterations,
        "warmup_runs": warmup,
        "measurements": [],
        "errors": [],
    }

    total_runs = warmup + iterations

    for run_idx in range(total_runs):
        is_warmup = run_idx < warmup

        # Create temp file for result JSON
        import tempfile
        result_fd, result_path = tempfile.mkstemp(suffix=".json", prefix="bench_result_")
        os.close(result_fd)

        try:
            # Generate wrapper script
            wrapper_code = TIMING_WRAPPER.format(
                benchmark_path=benchmark_path,
                is_warmup=is_warmup,
                result_path=result_path,
            )

            # Write wrapper to temp file
            wrapper_fd, wrapper_path = tempfile.mkstemp(suffix=".py", prefix="bench_wrapper_")
            with os.fdopen(wrapper_fd, "w") as wf:
                wf.write(wrapper_code)

            # Execute
            env = os.environ.copy()
            env["PYTHONPATH"] = codebase_path
            env["PYTHONHASHSEED"] = "0"
            env.pop("PYTHONDONTWRITEBYTECODE", None)

            proc = subprocess.run(
                [interpreter, wrapper_path],
                capture_output=True,
                timeout=timeout,
                env=env,
                cwd=codebase_path,
            )

            # Read result
            try:
                with open(result_path, "r") as rf:
                    measurement = json.load(rf)
                measurement["run_index"] = run_idx
                measurement["stdout_len"] = len(proc.stdout)
                measurement["stderr_len"] = len(proc.stderr)

                if not is_warmup:
                    results["measurements"].append(measurement)
            except (FileNotFoundError, json.JSONDecodeError):
                # Wrapper didn't produce output — interpreter error
                error_info = {
                    "run_index": run_idx,
                    "is_warmup": is_warmup,
                    "returncode": proc.returncode,
                    "stderr": proc.stderr.decode("utf-8", errors="replace")[:500],
                }
                results["errors"].append(error_info)
                if not is_warmup:
                    results["measurements"].append({
                        "run_index": run_idx,
                        "wall_seconds": None,
                        "cpu_seconds": None,
                        "peak_memory_kb": None,
                        "exit_code": proc.returncode,
                        "error": proc.stderr.decode("utf-8", errors="replace")[:200],
                        "is_warmup": False,
                    })

        except subprocess.TimeoutExpired:
            results["errors"].append({
                "run_index": run_idx,
                "is_warmup": is_warmup,
                "error": f"Timeout after {timeout}s",
            })
            if not is_warmup:
                results["measurements"].append({
                    "run_index": run_idx,
                    "wall_seconds": None,
                    "cpu_seconds": None,
                    "peak_memory_kb": None,
                    "exit_code": -1,
                    "error": f"Timeout after {timeout}s",
                    "is_warmup": False,
                })

        finally:
            # Cleanup temp files
            for tmp in [result_path, wrapper_path]:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    return results


# ── Statistical Analysis ─────────────────────────────────────────────────────

def compute_statistics(measurements: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute statistical summary of benchmark measurements."""
    # Extract wall times (skip failed measurements)
    wall_times = [
        m["wall_seconds"] for m in measurements
        if m.get("wall_seconds") is not None
    ]
    cpu_times = [
        m["cpu_seconds"] for m in measurements
        if m.get("cpu_seconds") is not None
    ]
    memory_values = [
        m["peak_memory_kb"] for m in measurements
        if m.get("peak_memory_kb") is not None and m["peak_memory_kb"] > 0
    ]

    if not wall_times:
        return {
            "valid_runs": 0,
            "total_runs": len(measurements),
            "wall": None,
            "cpu": None,
            "memory": None,
        }

    def _stats(values: List[float]) -> Dict[str, float]:
        """Compute descriptive statistics for a list of values."""
        n = len(values)
        if n == 0:
            return {}

        sorted_vals = sorted(values)
        mean = sum(values) / n
        median = sorted_vals[n // 2] if n % 2 == 1 else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2

        if n > 1:
            variance = sum((x - mean) ** 2 for x in values) / (n - 1)
            std_dev = math.sqrt(variance)
        else:
            variance = 0.0
            std_dev = 0.0

        cv = (std_dev / mean * 100) if mean > 0 else 0.0

        # IQR for outlier detection
        q1_idx = n // 4
        q3_idx = 3 * n // 4
        q1 = sorted_vals[q1_idx]
        q3 = sorted_vals[q3_idx]
        iqr = q3 - q1

        # 95% confidence interval using t-distribution approximation
        # For small samples, use t-value ≈ 2.0 (reasonable for n >= 5)
        t_value = 2.776 if n <= 4 else (2.571 if n <= 5 else (2.447 if n <= 6 else 2.0))
        ci_half = t_value * std_dev / math.sqrt(n) if n > 0 else 0
        ci_lower = mean - ci_half
        ci_upper = mean + ci_half

        # Count outliers
        lower_fence = q1 - 1.5 * iqr
        upper_fence = q3 + 1.5 * iqr
        outliers = sum(1 for v in values if v < lower_fence or v > upper_fence)

        return {
            "n": n,
            "mean": round(mean, 6),
            "median": round(median, 6),
            "std_dev": round(std_dev, 6),
            "cv_percent": round(cv, 2),
            "min": round(sorted_vals[0], 6),
            "max": round(sorted_vals[-1], 6),
            "q1": round(q1, 6),
            "q3": round(q3, 6),
            "iqr": round(iqr, 6),
            "ci_95_lower": round(ci_lower, 6),
            "ci_95_upper": round(ci_upper, 6),
            "outliers": outliers,
        }

    result = {
        "valid_runs": len(wall_times),
        "total_runs": len(measurements),
        "wall": _stats(wall_times),
        "cpu": _stats(cpu_times) if cpu_times else None,
        "memory": _stats(memory_values) if memory_values else None,
    }

    return result


def compare_results(
    py2_stats: Dict[str, Any],
    py3_stats: Dict[str, Any],
    threshold: float,
) -> Dict[str, Any]:
    """Compare Py2 and Py3 benchmark results."""
    comparison = {
        "classification": "error",
        "wall_time_change_percent": None,
        "cpu_time_change_percent": None,
        "memory_change_percent": None,
        "details": "",
    }

    py2_wall = py2_stats.get("wall")
    py3_wall = py3_stats.get("wall")

    if not py2_wall or not py3_wall:
        comparison["details"] = "One or both interpreters failed to produce measurements"
        return comparison

    py2_valid = py2_stats.get("valid_runs", 0)
    py3_valid = py3_stats.get("valid_runs", 0)

    if py2_valid == 0 or py3_valid == 0:
        comparison["details"] = "One or both interpreters had zero valid runs"
        return comparison

    # Wall time comparison
    py2_mean = py2_wall["mean"]
    py3_mean = py3_wall["mean"]

    if py2_mean > 0:
        change_pct = ((py3_mean - py2_mean) / py2_mean) * 100
    else:
        change_pct = 0.0

    comparison["wall_time_change_percent"] = round(change_pct, 2)

    # CPU time comparison
    py2_cpu = py2_stats.get("cpu")
    py3_cpu = py3_stats.get("cpu")
    if py2_cpu and py3_cpu and py2_cpu["mean"] > 0:
        cpu_change = ((py3_cpu["mean"] - py2_cpu["mean"]) / py2_cpu["mean"]) * 100
        comparison["cpu_time_change_percent"] = round(cpu_change, 2)

    # Memory comparison
    py2_mem = py2_stats.get("memory")
    py3_mem = py3_stats.get("memory")
    if py2_mem and py3_mem and py2_mem["mean"] > 0:
        mem_change = ((py3_mem["mean"] - py2_mem["mean"]) / py2_mem["mean"]) * 100
        comparison["memory_change_percent"] = round(mem_change, 2)

    # Classification based on CI overlap and threshold
    py2_ci_upper = py2_wall.get("ci_95_upper", py2_mean)
    py2_ci_lower = py2_wall.get("ci_95_lower", py2_mean)
    py3_ci_upper = py3_wall.get("ci_95_upper", py3_mean)
    py3_ci_lower = py3_wall.get("ci_95_lower", py3_mean)

    # Check if confidence intervals overlap
    ci_overlap = py3_ci_lower <= py2_ci_upper and py2_ci_lower <= py3_ci_upper

    if abs(change_pct) <= threshold:
        comparison["classification"] = "no_regression"
        comparison["details"] = f"Within threshold ({change_pct:+.1f}%, threshold: ±{threshold}%)"
    elif change_pct > threshold:
        if ci_overlap:
            comparison["classification"] = "inconclusive"
            comparison["details"] = (
                f"Py3 is {change_pct:.1f}% slower but CIs overlap — "
                f"increase iterations for confidence"
            )
        else:
            comparison["classification"] = "regression"
            comparison["details"] = (
                f"Py3 is {change_pct:.1f}% slower (above {threshold}% threshold)"
            )
    elif change_pct < -threshold:
        comparison["classification"] = "improvement"
        comparison["details"] = f"Py3 is {abs(change_pct):.1f}% faster"
    else:
        comparison["classification"] = "no_regression"
        comparison["details"] = f"Change within threshold ({change_pct:+.1f}%)"

    return comparison


# ── Optimization Opportunity Scanner ─────────────────────────────────────────

OPTIMIZATION_PATTERNS = [
    {
        "pattern_name": "percent_formatting",
        "regex": r'["\'].*%[sd].*["\']\s*%\s*[\(]',
        "description": "% string formatting — f-strings are ~30% faster",
        "py3_alternative": "f-string: f'{value}'",
        "min_version": "3.6",
        "speedup_estimate": "~30% for string formatting operations",
    },
    {
        "pattern_name": "format_method",
        "regex": r'["\'].*\{\}.*["\']\.format\(',
        "description": ".format() method — f-strings are faster",
        "py3_alternative": "f-string: f'{value}'",
        "min_version": "3.6",
        "speedup_estimate": "~20% for string formatting operations",
    },
    {
        "pattern_name": "dict_constructor_from_list",
        "regex": r'dict\s*\(\s*\[',
        "description": "dict() from list of tuples — dict comprehension is faster",
        "py3_alternative": "{k: v for k, v in iterable}",
        "min_version": "3.0",
        "speedup_estimate": "~10-20% for dict construction",
    },
    {
        "pattern_name": "manual_key_function",
        "regex": r'sorted\s*\(.*,\s*key\s*=\s*lambda',
        "description": "Lambda key function — consider operator.itemgetter/attrgetter",
        "py3_alternative": "operator.itemgetter() or operator.attrgetter()",
        "min_version": "3.0",
        "speedup_estimate": "~10% for sort operations",
    },
    {
        "pattern_name": "manual_memoization",
        "regex": r'_cache\s*=\s*\{\}|_memo\s*=\s*\{\}|_results\s*=\s*\{\}',
        "description": "Manual memoization dict — use @functools.lru_cache",
        "py3_alternative": "@functools.lru_cache(maxsize=None)",
        "min_version": "3.2",
        "speedup_estimate": "Cleaner code, often comparable or faster",
    },
    {
        "pattern_name": "manual_init_boilerplate",
        "regex": r'def\s+__init__\s*\(\s*self\s*,(?:\s*\w+\s*,){3,}',
        "description": "Boilerplate __init__ with many params — consider @dataclass",
        "py3_alternative": "@dataclasses.dataclass",
        "min_version": "3.7",
        "speedup_estimate": "Less code, slightly faster __init__",
    },
    {
        "pattern_name": "isinstance_str_check",
        "regex": r'type\s*\(\s*\w+\s*\)\s*==\s*str',
        "description": "type() == str check — isinstance() is faster for subclasses",
        "py3_alternative": "isinstance(x, str)",
        "min_version": "3.0",
        "speedup_estimate": "Minor, but more correct for subclasses",
    },
    {
        "pattern_name": "list_comprehension_to_set",
        "regex": r'set\s*\(\s*\[.*for\s+.*in\s+',
        "description": "set(list comprehension) — use set comprehension",
        "py3_alternative": "{x for x in iterable}",
        "min_version": "3.0",
        "speedup_estimate": "~10% for set construction (avoids intermediate list)",
    },
    {
        "pattern_name": "contextlib_suppress",
        "regex": r'try:\s*\n\s*.*\n\s*except\s+\w+:\s*\n\s*pass',
        "description": "try/except/pass — consider contextlib.suppress",
        "py3_alternative": "with contextlib.suppress(ExceptionType):",
        "min_version": "3.4",
        "speedup_estimate": "Cleaner code (performance neutral)",
    },
]


def scan_optimization_opportunities(
    codebase_path: str,
    target_version: str,
    modules: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Scan for Py3-specific optimization opportunities."""
    root = Path(codebase_path)
    target_parts = tuple(int(x) for x in target_version.split("."))
    opportunities = []

    # Discover files
    skip_dirs = {".git", "__pycache__", ".tox", "venv", ".venv", "build", "dist"}
    py_files = []

    search_dirs = [root / m for m in modules] if modules else [root]
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(search_dir):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for fn in filenames:
                if fn.endswith(".py"):
                    py_files.append(os.path.join(dirpath, fn))

    for file_path in py_files:
        try:
            content = read_file(file_path)
        except Exception:
            continue

        lines = content.splitlines()
        rel_path = os.path.relpath(file_path, root)

        for opt in OPTIMIZATION_PATTERNS:
            min_ver = tuple(int(x) for x in opt["min_version"].split("."))
            if target_parts < min_ver:
                continue

            for line_num, line in enumerate(lines, 1):
                if re.search(opt["regex"], line, re.MULTILINE):
                    opportunities.append({
                        "file": rel_path,
                        "line": line_num,
                        "pattern": opt["pattern_name"],
                        "description": opt["description"],
                        "alternative": opt["py3_alternative"],
                        "min_version": opt["min_version"],
                        "speedup_estimate": opt["speedup_estimate"],
                        "snippet": line.strip()[:150],
                    })

    return opportunities


# ── Report Generation ────────────────────────────────────────────────────────

def generate_report(
    benchmark_results: List[Dict[str, Any]],
    comparisons: List[Dict[str, Any]],
    optimization_opportunities: List[Dict[str, Any]],
    codebase_path: str,
    target_version: str,
    threshold: float,
    iterations: int,
) -> Dict[str, Any]:
    """Generate the performance report."""
    # Summarize comparisons
    classifications = [c.get("comparison", {}).get("classification", "error") for c in comparisons]
    regressions = classifications.count("regression")
    improvements = classifications.count("improvement")
    no_regression = classifications.count("no_regression")
    inconclusive = classifications.count("inconclusive")
    errors = classifications.count("error")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "codebase_path": codebase_path,
        "target_version": target_version,
        "threshold_percent": threshold,
        "iterations": iterations,
        "summary": {
            "total_benchmarks": len(comparisons),
            "regressions_above_threshold": regressions,
            "improvements": improvements,
            "no_regression": no_regression,
            "inconclusive": inconclusive,
            "errors": errors,
            "optimization_opportunities": len(optimization_opportunities),
        },
        "benchmarks": comparisons,
        "raw_results": benchmark_results,
    }

    return report


# ── Main ─────────────────────────────────────────────────────────────────────

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Performance benchmarker — compare Py2 vs Py3 execution speed"
    )
    parser.add_argument(
        "codebase_path",
        help="Root directory of the Python codebase",
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
        "--target-version", required=True,
        help="Target Python 3.x version (e.g., 3.9, 3.12)",
    )
    parser.add_argument(
        "--benchmark-suite",
        help="Path to benchmark scripts directory (optional)",
    )
    parser.add_argument(
        "--iterations", type=int, default=5,
        help="Number of timed runs per benchmark (default: 5)",
    )
    parser.add_argument(
        "--warmup", type=int, default=2,
        help="Number of warmup runs (default: 2)",
    )
    parser.add_argument(
        "--threshold", type=float, default=10.0,
        help="Regression threshold percentage (default: 10.0)",
    )
    parser.add_argument(
        "--timeout", type=int, default=300,
        help="Per-benchmark timeout in seconds (default: 300)",
    )
    parser.add_argument(
        "--modules", nargs="*",
        help="Specific modules to benchmark (optional)",
    )
    parser.add_argument(
        "--state-file",
        help="Path to migration-state.json (optional)",
    )
    parser.add_argument(
        "--output", default="./performance-output",
        help="Output directory (default: ./performance-output)",
    )

    args = parser.parse_args()

    codebase_path = os.path.abspath(args.codebase_path)
    if not os.path.isdir(codebase_path):
        print(f"Error: Not a directory: {codebase_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Discover Benchmarks ──────────────────────────────────────────────
    print("# ── Discovering Benchmarks ───────────────────────────────────────")
    benchmarks = discover_benchmarks(
        codebase_path, args.benchmark_suite, args.modules,
    )
    print(f"  Found {len(benchmarks)} benchmark(s)")

    if not benchmarks:
        print("  No benchmarks found. Create bench_*.py files or use --benchmark-suite.")
        print("  Generating optimization scan only.")

    # ── Execute Benchmarks ───────────────────────────────────────────────
    print("# ── Running Benchmarks ───────────────────────────────────────────")
    all_results = []
    comparisons = []

    for idx, bench in enumerate(benchmarks):
        bench_id = bench["id"]
        print(f"  [{idx + 1}/{len(benchmarks)}] {bench_id}")

        # Run under Py2
        print(f"    Py2 ({args.warmup} warmup + {args.iterations} measured)...")
        py2_result = execute_benchmark(
            bench, args.py2, "py2", args.iterations, args.warmup,
            args.timeout, codebase_path,
        )

        # Run under Py3
        print(f"    Py3 ({args.warmup} warmup + {args.iterations} measured)...")
        py3_result = execute_benchmark(
            bench, args.py3, "py3", args.iterations, args.warmup,
            args.timeout, codebase_path,
        )

        # Statistical analysis
        py2_stats = compute_statistics(py2_result["measurements"])
        py3_stats = compute_statistics(py3_result["measurements"])

        # Compare
        comparison = compare_results(py2_stats, py3_stats, args.threshold)

        bench_comparison = {
            "benchmark_id": bench_id,
            "benchmark_type": bench["type"],
            "py2_stats": py2_stats,
            "py3_stats": py3_stats,
            "comparison": comparison,
        }

        all_results.append({"py2": py2_result, "py3": py3_result})
        comparisons.append(bench_comparison)

        # Print summary line
        classification = comparison["classification"]
        change = comparison.get("wall_time_change_percent")
        if change is not None:
            print(f"    → {classification} ({change:+.1f}%)")
        else:
            print(f"    → {classification}")

    # ── Scan for Optimization Opportunities ──────────────────────────────
    print("# ── Scanning for Optimization Opportunities ──────────────────────")
    opportunities = scan_optimization_opportunities(
        codebase_path, args.target_version, args.modules,
    )
    print(f"  Found {len(opportunities)} optimization opportunity(ies)")

    # ── Generate Reports ─────────────────────────────────────────────────
    print("# ── Generating Reports ───────────────────────────────────────────")

    report = generate_report(
        all_results, comparisons, opportunities,
        codebase_path, args.target_version,
        args.threshold, args.iterations,
    )
    report_path = str(output_dir / "performance-report.json")
    save_json(report, report_path)

    opp_path = str(output_dir / "optimization-opportunities.json")
    save_json(opportunities, opp_path)

    # ── Print Summary ────────────────────────────────────────────────────
    print("# ── Summary ──────────────────────────────────────────────────────")
    summary = report["summary"]
    print(f"  Total benchmarks:   {summary['total_benchmarks']}")
    print(f"  No regression:      {summary['no_regression']}")
    print(f"  Improvements:       {summary['improvements']}")
    print(f"  Regressions:        {summary['regressions_above_threshold']}")
    print(f"  Inconclusive:       {summary['inconclusive']}")
    print(f"  Errors:             {summary['errors']}")
    print(f"  Optimizations:      {summary['optimization_opportunities']}")

    if summary["regressions_above_threshold"] == 0:
        print(f"\n  ✓ GATE CHECK: PASS — no regressions above {args.threshold}% threshold")
    else:
        print(f"\n  ✗ GATE CHECK: FAIL — {summary['regressions_above_threshold']} regression(s) above threshold")

    print("\nDone.")


if __name__ == "__main__":
    main()
