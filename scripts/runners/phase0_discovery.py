#!/usr/bin/env python3
"""
Script: phase0_discovery.py
Purpose: Execute discovery phase - project sizing, codebase analysis, Py2 pattern detection
Inputs: project root path, output directory
Outputs: sizing-report.json, dependency-graph.json, raw-scan.json, discovery-summary.json
LLM involvement: NONE
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# ── Logging ──────────────────────────────────────────────────────────────────
import sys as _sys; _sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'lib'))
from migration_logger import setup_logging, log_execution, log_invocation
logger = setup_logging(__name__)

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


def run_script(script_path, args, description):
    """Run a script, capture output, handle errors."""
    if not script_path.exists():
        logger.warning(f"Script not found, skipping: {script_path}")
        return {"status": "skipped", "reason": f"Script not found: {script_path}"}

    cmd = [sys.executable, str(script_path)] + args
    print(f"  → {description}...", file=sys.stderr)
    logger.info(f"Invoking: {description} ({script_path.name})")
    start_time = __import__('time').monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        duration = __import__('time').monotonic() - start_time
        log_invocation(script_path, args, result.returncode, duration,
                      len(result.stdout.encode()), len(result.stderr.encode()))
        if result.returncode == 0:
            try:
                return {"status": "complete", "output": json.loads(result.stdout)}
            except json.JSONDecodeError:
                return {"status": "complete", "output": result.stdout[:500]}
        elif result.returncode == 1:
            try:
                return {"status": "partial", "output": json.loads(result.stdout)}
            except json.JSONDecodeError:
                return {"status": "partial", "output": result.stdout[:500]}
        else:
            return {"status": "error", "stderr": result.stderr[:500]}
    except subprocess.TimeoutExpired:
        logger.error("Script execution timed out")
        return {"status": "timeout"}
    except Exception as e:
        logger.error(f"Script execution error: {e}")
        return {"status": "error", "error": str(e)}


def phase0_discovery(project_root, output_dir):
    """Execute discovery phase."""
    print(f"\n[PHASE 0] Discovery - Analyzing project structure", file=sys.stderr)
    print(f"  Project root: {project_root}", file=sys.stderr)
    print(f"  Output dir: {output_dir}", file=sys.stderr)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Step 1: Project sizing
    script_path = SKILLS_DIR / "py2to3-project-initializer" / "scripts" / "quick_size_scan.py"
    sizing = run_script(script_path, [str(project_root), str(output_dir)], "Project sizing")
    results["sizing"] = sizing
    if sizing["status"] in ["complete", "partial"]:
        sizing_output = sizing.get("output", {})
        if isinstance(sizing_output, dict):
            with open(output_dir / "sizing-report.json", "w") as f:
                json.dump(sizing_output, f, indent=2)

    # Step 2: Codebase graph analysis (optional)
    script_path = SKILLS_DIR / "universal-code-graph" / "scripts" / "analyze_universal.py"
    graph = run_script(script_path, [str(project_root), str(output_dir)], "Codebase graph analysis")
    results["codebase_graph"] = graph
    if graph["status"] in ["complete", "partial"]:
        graph_output = graph.get("output", {})
        if isinstance(graph_output, dict):
            with open(output_dir / "dependency-graph.json", "w") as f:
                json.dump(graph_output, f, indent=2)

    # Step 3: Py2 pattern analysis (optional)
    script_path = SKILLS_DIR / "py2to3-codebase-analyzer" / "scripts" / "analyze.py"
    patterns = run_script(
        script_path, [str(project_root), str(output_dir)], "Python 2 pattern analysis"
    )
    results["py2_patterns"] = patterns
    if patterns["status"] in ["complete", "partial"]:
        patterns_output = patterns.get("output", {})
        if isinstance(patterns_output, dict):
            with open(output_dir / "raw-scan.json", "w") as f:
                json.dump(patterns_output, f, indent=2)

    # Step 4: Baseline security scan + SBOM
    security_dir = output_dir / "security"
    security_dir.mkdir(parents=True, exist_ok=True)
    script_path = SKILLS_DIR / "py2to3-security-scanner" / "scripts" / "security_scan.py"
    security = run_script(
        script_path,
        [str(project_root), "--mode", "baseline", "-o", str(security_dir)],
        "Baseline security scan + SBOM"
    )
    results["security"] = security

    # Generate discovery summary
    summary = {
        "phase": "discovery",
        "project_root": str(project_root),
        "output_dir": str(output_dir),
        "steps": {
            "sizing": sizing.get("status", "unknown"),
            "codebase_graph": graph.get("status", "unknown"),
            "py2_patterns": patterns.get("status", "unknown"),
            "security_scan": security.get("status", "unknown"),
        },
    }

    # Extract sizing verdict if available
    if sizing["status"] in ["complete", "partial"] and isinstance(sizing.get("output"), dict):
        sizing_data = sizing["output"]
        if "verdict" in sizing_data:
            summary["sizing_verdict"] = sizing_data["verdict"]
        if "total_files" in sizing_data:
            summary["total_files"] = sizing_data["total_files"]
        if "python_files" in sizing_data:
            summary["python_files"] = sizing_data["python_files"]

    with open(output_dir / "discovery-summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"\n[PHASE 0 SUMMARY]", file=sys.stderr)
    print(f"  Sizing: {sizing['status']}", file=sys.stderr)
    print(f"  Graph analysis: {graph['status']}", file=sys.stderr)
    print(f"  Pattern analysis: {patterns['status']}", file=sys.stderr)

    if "sizing_verdict" in summary:
        print(f"  Sizing verdict: {summary['sizing_verdict']}", file=sys.stderr)
    if "python_files" in summary:
        print(f"  Python files found: {summary['python_files']}", file=sys.stderr)

    print(f"  Security scan: {security['status']}", file=sys.stderr)

    # Determine overall status
    statuses = [sizing["status"], graph["status"], patterns["status"], security["status"]]
    if all(s in ["complete", "partial"] for s in statuses):
        overall_status = 0
    elif any(s == "error" for s in statuses):
        overall_status = 2
    else:
        overall_status = 1

    print(f"\n  Output files: {list(output_dir.glob('*.json'))}", file=sys.stderr)

    # Output JSON summary
    print(json.dumps(summary, indent=2))

    return overall_status


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Phase 0: Discovery - Analyze project structure and identify Python 2 patterns"
    )
    parser.add_argument("project_root", help="Root directory of the project to analyze")
    parser.add_argument(
        "-o", "--output", default="./migration_output", help="Output directory for phase results"
    )

    args = parser.parse_args()

    exit_code = phase0_discovery(args.project_root, args.output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
