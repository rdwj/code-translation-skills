#!/usr/bin/env python3
"""
Performance Report Generator

Generates a comprehensive markdown report from performance-report.json
and optimization-opportunities.json.

Usage:
    python3 generate_perf_report.py \
        --perf-report <performance-report.json> \
        [--output <performance-report.md>]

Outputs:
    Markdown report summarizing performance benchmarks with comparison tables,
    regression details, optimization opportunities, and next steps.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List
from collections import Counter
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


def load_json(path: str) -> Any:
    """Load JSON file."""
    p = Path(path)
    if not p.exists():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_header(report: Dict[str, Any]) -> str:
    """Generate report header with summary."""
    summary = report.get("summary", {})
    total = summary.get("total_benchmarks", 0)
    regressions = summary.get("regressions_above_threshold", 0)
    improvements = summary.get("improvements", 0)
    no_regression = summary.get("no_regression", 0)
    inconclusive = summary.get("inconclusive", 0)
    errors = summary.get("errors", 0)
    threshold = report.get("threshold_percent", 10.0)

    if regressions == 0 and errors == 0:
        status = "PASS"
        status_note = f"No performance regressions above {threshold}% threshold."
    elif regressions == 0 and errors > 0:
        status = "PARTIAL"
        status_note = f"No regressions detected, but {errors} benchmark(s) had errors."
    else:
        status = "FAIL"
        status_note = f"{regressions} benchmark(s) show regressions above {threshold}% threshold."

    header = f"""# Performance Benchmark Report

**Generated:** {report.get("timestamp", "unknown")}
**Target Version:** Python {report.get("target_version", "3.x")}
**Status:** {status}
**Threshold:** {threshold}%
**Iterations:** {report.get("iterations", "N/A")} per benchmark

> {status_note}

## Overall Summary

| Metric | Count |
|--------|-------|
| Total benchmarks | {total} |
| No regression | {no_regression} |
| Improvements (Py3 faster) | {improvements} |
| **Regressions** | **{regressions}** |
| Inconclusive | {inconclusive} |
| Errors | {errors} |

"""
    return header


def generate_results_table(report: Dict[str, Any]) -> str:
    """Generate benchmark results comparison table."""
    benchmarks = report.get("benchmarks", [])

    if not benchmarks:
        return "## Benchmark Results\n\nNo benchmarks executed.\n\n"

    section = "## Benchmark Results\n\n"
    section += "| Benchmark | Py2 Mean (s) | Py3 Mean (s) | Change | Classification |\n"
    section += "|-----------|-------------|-------------|--------|----------------|\n"

    for b in benchmarks:
        bench_id = b.get("benchmark_id", "unknown")
        py2_stats = b.get("py2_stats", {})
        py3_stats = b.get("py3_stats", {})
        comparison = b.get("comparison", {})

        py2_wall = py2_stats.get("wall", {})
        py3_wall = py3_stats.get("wall", {})

        py2_mean = py2_wall.get("mean", "N/A")
        py3_mean = py3_wall.get("mean", "N/A")
        change = comparison.get("wall_time_change_percent")
        classification = comparison.get("classification", "error")

        py2_str = f"{py2_mean:.4f}" if isinstance(py2_mean, (int, float)) else str(py2_mean)
        py3_str = f"{py3_mean:.4f}" if isinstance(py3_mean, (int, float)) else str(py3_mean)
        change_str = f"{change:+.1f}%" if change is not None else "N/A"

        marker = ""
        if classification == "regression":
            marker = " **!!**"
        elif classification == "improvement":
            marker = " ✓"
        elif classification == "inconclusive":
            marker = " ?"

        section += f"| `{bench_id}` | {py2_str} | {py3_str} | {change_str} | {classification}{marker} |\n"

    section += "\n"
    return section


def generate_regression_details(report: Dict[str, Any]) -> str:
    """Generate detailed section for regressions."""
    benchmarks = report.get("benchmarks", [])
    regressions = [b for b in benchmarks if b.get("comparison", {}).get("classification") == "regression"]

    if not regressions:
        return "## Regressions\n\nNo regressions detected.\n\n"

    section = f"## Regressions ({len(regressions)} total)\n\n"
    section += "These benchmarks show statistically significant performance degradation.\n\n"

    for b in regressions:
        bench_id = b.get("benchmark_id", "unknown")
        comparison = b.get("comparison", {})
        py2_stats = b.get("py2_stats", {})
        py3_stats = b.get("py3_stats", {})

        py2_wall = py2_stats.get("wall", {})
        py3_wall = py3_stats.get("wall", {})

        section += f"### `{bench_id}`\n\n"
        section += f"**Change:** {comparison.get('wall_time_change_percent', 'N/A'):+.1f}%\n\n"
        section += f"**Details:** {comparison.get('details', '')}\n\n"

        # Show detailed stats
        section += "| Metric | Py2 | Py3 |\n"
        section += "|--------|-----|-----|\n"

        for metric_name, py2_metric, py3_metric in [
            ("Wall time", py2_wall, py3_wall),
            ("CPU time", py2_stats.get("cpu", {}), py3_stats.get("cpu", {})),
        ]:
            if not py2_metric or not py3_metric:
                continue
            py2_mean = py2_metric.get("mean", "N/A")
            py3_mean = py3_metric.get("mean", "N/A")
            py2_std = py2_metric.get("std_dev", "N/A")
            py3_std = py3_metric.get("std_dev", "N/A")
            py2_ci_l = py2_metric.get("ci_95_lower", "N/A")
            py2_ci_u = py2_metric.get("ci_95_upper", "N/A")
            py3_ci_l = py3_metric.get("ci_95_lower", "N/A")
            py3_ci_u = py3_metric.get("ci_95_upper", "N/A")

            section += f"| {metric_name} mean (s) | {_fmt(py2_mean)} | {_fmt(py3_mean)} |\n"
            section += f"| {metric_name} std dev | {_fmt(py2_std)} | {_fmt(py3_std)} |\n"
            section += f"| {metric_name} 95% CI | [{_fmt(py2_ci_l)}, {_fmt(py2_ci_u)}] | [{_fmt(py3_ci_l)}, {_fmt(py3_ci_u)}] |\n"

        # Memory comparison
        py2_mem = py2_stats.get("memory")
        py3_mem = py3_stats.get("memory")
        if py2_mem and py3_mem:
            section += f"| Peak memory (KB) | {_fmt(py2_mem.get('mean'))} | {_fmt(py3_mem.get('mean'))} |\n"
            mem_change = comparison.get("memory_change_percent")
            if mem_change is not None:
                section += f"| Memory change | — | {mem_change:+.1f}% |\n"

        section += "\n"

    return section


def _fmt(value: Any) -> str:
    """Format a numeric value for display."""
    if value is None or value == "N/A":
        return "N/A"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def generate_improvements(report: Dict[str, Any]) -> str:
    """Generate section for Py3 improvements."""
    benchmarks = report.get("benchmarks", [])
    improvements = [b for b in benchmarks if b.get("comparison", {}).get("classification") == "improvement"]

    if not improvements:
        return ""

    section = f"## Py3 Improvements ({len(improvements)} benchmarks)\n\n"
    section += "These benchmarks run faster under Python 3.\n\n"

    section += "| Benchmark | Change | Py2 Mean (s) | Py3 Mean (s) |\n"
    section += "|-----------|--------|-------------|-------------|\n"

    for b in improvements:
        bench_id = b.get("benchmark_id", "unknown")
        change = b.get("comparison", {}).get("wall_time_change_percent", 0)
        py2_mean = b.get("py2_stats", {}).get("wall", {}).get("mean", "N/A")
        py3_mean = b.get("py3_stats", {}).get("wall", {}).get("mean", "N/A")

        section += f"| `{bench_id}` | {change:+.1f}% | {_fmt(py2_mean)} | {_fmt(py3_mean)} |\n"

    section += "\n"
    return section


def generate_optimization_opportunities(report: Dict[str, Any]) -> str:
    """Generate optimization opportunities section."""
    # Try to load from same directory
    report_path = report.get("_report_path", "")
    opp_path = str(Path(report_path).parent / "optimization-opportunities.json") if report_path else ""

    opportunities = report.get("_opportunities", [])

    if not opportunities:
        return ""

    section = f"## Optimization Opportunities ({len(opportunities)} found)\n\n"
    section += "These patterns can be optimized using Python 3-specific features.\n\n"

    # Group by pattern
    by_pattern: Dict[str, List[Dict[str, Any]]] = {}
    for opp in opportunities:
        pattern = opp.get("pattern", "unknown")
        by_pattern.setdefault(pattern, []).append(opp)

    for pattern, items in sorted(by_pattern.items(), key=lambda x: -len(x[1])):
        first = items[0]
        count = len(items)
        section += f"### {first.get('description', pattern)} ({count} occurrence(s))\n\n"
        section += f"- **Alternative:** `{first.get('alternative', 'N/A')}`\n"
        section += f"- **Estimated speedup:** {first.get('speedup_estimate', 'unknown')}\n"
        section += f"- **Min version:** Python {first.get('min_version', '3.0')}\n\n"

        # Show a few examples
        for opp in items[:5]:
            section += f"  - `{opp.get('file', 'unknown')}:{opp.get('line', 0)}` — `{opp.get('snippet', '')}`\n"
        if count > 5:
            section += f"  - ... and {count - 5} more\n"
        section += "\n"

    return section


def generate_investigation_guide(report: Dict[str, Any]) -> str:
    """Generate investigation guide for regressions."""
    summary = report.get("summary", {})
    regressions = summary.get("regressions_above_threshold", 0)

    if regressions == 0:
        return ""

    section = """## Investigation Guide

For each regression, follow these steps:

### 1. Profile the Benchmark

```bash
# Py2 profiling
python2.7 -m cProfile -o py2_profile.prof benchmark_script.py

# Py3 profiling
python3 -m cProfile -o py3_profile.prof benchmark_script.py

# Compare (using snakeviz or pstats)
python3 -m pstats py3_profile.prof
```

### 2. Common Regression Causes

| Cause | How to Identify | Fix |
|-------|----------------|-----|
| Added encode/decode | Profile shows time in codec functions | Cache encoded/decoded values |
| str vs bytes overhead | String operations show up in profile | Ensure data stays as bytes where appropriate |
| Iterator materialization | `.keys()`, `.values()`, `.items()` | Use iteration directly, don't call `list()` unnecessarily |
| Integer division overhead | `//` slower than old `/` for large ints | Usually negligible; profile to confirm |
| Dict ordering guarantee | Insertion-order maintenance | Negligible; unlikely cause |

### 3. When to Accept a Regression

- If the regression is < 5% and the benchmark is not on a critical path
- If the regression is caused by correct encoding handling (safety > speed)
- If the regression is in startup time only (Py3 imports are slower)
- If the regression disappears at higher iteration counts (noise)

"""
    return section


def generate_next_steps(report: Dict[str, Any]) -> str:
    """Generate next steps section."""
    summary = report.get("summary", {})
    regressions = summary.get("regressions_above_threshold", 0)

    section = "## Next Steps\n\n"

    if regressions == 0:
        section += "No performance regressions detected. The codebase is ready for:\n\n"
        section += "1. Apply optimization opportunities for additional Py3 speedups\n"
        section += "2. Run the Phase 4→5 gate check (Skill X.3)\n"
        section += "3. Consider target Python 3.11+ for best performance\n"
    else:
        section += f"**{regressions} regression(s) must be investigated:**\n\n"
        section += "1. Profile each regressed benchmark under both interpreters\n"
        section += "2. Identify root cause (encoding overhead, iterator changes, etc.)\n"
        section += "3. Apply fix or document as acceptable regression\n"
        section += "4. Re-run benchmarks to verify fix\n"
        section += "5. Repeat until zero regressions above threshold\n"

    section += "\n"
    return section


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate markdown performance benchmark report"
    )
    parser.add_argument(
        "--perf-report", required=True,
        help="Path to performance-report.json",
    )
    parser.add_argument(
        "--output", default="performance-report.md",
        help="Output markdown file (default: performance-report.md)",
    )

    args = parser.parse_args()

    print("# ── Loading JSON Report ──────────────────────────────────────", file=sys.stdout)
    report = load_json(args.perf_report)

    # Try to load optimization opportunities from same directory
    opp_path = Path(args.perf_report).parent / "optimization-opportunities.json"
    if opp_path.exists():
        report["_opportunities"] = load_json(str(opp_path))
    else:
        report["_opportunities"] = []

    report["_report_path"] = args.perf_report

    print("# ── Generating Markdown Report ───────────────────────────────", file=sys.stdout)

    md = ""
    md += generate_header(report)
    md += generate_results_table(report)
    md += generate_regression_details(report)
    md += generate_improvements(report)
    md += generate_optimization_opportunities(report)
    md += generate_investigation_guide(report)
    md += generate_next_steps(report)

    output_path = Path(args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"Wrote report to {output_path}", file=sys.stdout)
    print("Done.", file=sys.stdout)


if __name__ == "__main__":
    main()
