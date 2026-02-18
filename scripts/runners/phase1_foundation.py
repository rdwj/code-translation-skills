#!/usr/bin/env python3
"""
Script: phase1_foundation.py
Purpose: Execute foundation phase - inject __future__ imports, capture lint baseline, generate test scaffolds
Inputs: project root, raw-scan.json from phase 0, output directory
Outputs: injection report, lint baseline, test scaffolds
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


def phase1_foundation(project_root, raw_scan_path, output_dir):
    """Execute foundation phase."""
    print(f"\n[PHASE 1] Foundation - Prepare codebase for migration", file=sys.stderr)
    print(f"  Project root: {project_root}", file=sys.stderr)
    print(f"  Raw scan: {raw_scan_path}", file=sys.stderr)
    print(f"  Output dir: {output_dir}", file=sys.stderr)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Step 1: Inject __future__ imports
    script_path = SKILLS_DIR / "py2to3-future-imports-injector" / "scripts" / "inject_futures.py"
    injection = run_script(
        script_path, [str(project_root), str(output_dir)], "Injecting __future__ imports"
    )
    results["future_injection"] = injection
    if injection["status"] in ["complete", "partial"]:
        injection_output = injection.get("output", {})
        if isinstance(injection_output, dict):
            with open(output_dir / "injection-report.json", "w") as f:
                json.dump(injection_output, f, indent=2)

    # Step 2: Capture lint baseline (optional)
    script_path = SKILLS_DIR / "py2to3-lint-baseline-generator" / "scripts" / "run_lint.py"
    lint = run_script(
        script_path, [str(project_root), str(output_dir)], "Capturing lint baseline"
    )
    results["lint_baseline"] = lint
    if lint["status"] in ["complete", "partial"]:
        lint_output = lint.get("output", {})
        if isinstance(lint_output, dict):
            with open(output_dir / "lint-baseline.json", "w") as f:
                json.dump(lint_output, f, indent=2)

    # Step 3: Generate test scaffolds (optional)
    script_path = SKILLS_DIR / "py2to3-test-scaffold-generator" / "scripts" / "generate_tests.py"
    tests = run_script(
        script_path, [str(project_root), str(output_dir)], "Generating test scaffolds"
    )
    results["test_scaffolds"] = tests
    if tests["status"] in ["complete", "partial"]:
        tests_output = tests.get("output", {})
        if isinstance(tests_output, dict):
            with open(output_dir / "test-scaffolds.json", "w") as f:
                json.dump(tests_output, f, indent=2)

    # Generate foundation summary
    summary = {
        "phase": "foundation",
        "project_root": str(project_root),
        "output_dir": str(output_dir),
        "steps": {
            "future_injection": injection.get("status", "unknown"),
            "lint_baseline": lint.get("status", "unknown"),
            "test_scaffolds": tests.get("status", "unknown"),
        },
    }

    # Extract metrics if available
    if injection["status"] in ["complete", "partial"] and isinstance(injection.get("output"), dict):
        inj_data = injection["output"]
        if "files_modified" in inj_data:
            summary["files_with_future_imports"] = inj_data["files_modified"]

    if tests["status"] in ["complete", "partial"] and isinstance(tests.get("output"), dict):
        tests_data = tests["output"]
        if "test_files_created" in tests_data:
            summary["test_files_created"] = tests_data["test_files_created"]

    with open(output_dir / "foundation-summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"\n[PHASE 1 SUMMARY]", file=sys.stderr)
    print(f"  Future imports: {injection['status']}", file=sys.stderr)
    print(f"  Lint baseline: {lint['status']}", file=sys.stderr)
    print(f"  Test scaffolds: {tests['status']}", file=sys.stderr)

    if "files_with_future_imports" in summary:
        print(f"  Files modified: {summary['files_with_future_imports']}", file=sys.stderr)

    # Determine overall status
    statuses = [injection["status"], lint["status"], tests["status"]]
    if all(s in ["complete", "partial"] for s in statuses):
        overall_status = 0
    elif any(s == "error" for s in statuses):
        overall_status = 2
    else:
        overall_status = 1

    print(f"\n  Output files: {list(output_dir.glob('*.json'))}", file=sys.stderr)
    print(f"\nPhase 1 ready for Phase 2 (mechanical fixes)", file=sys.stderr)

    # Output JSON summary
    print(json.dumps(summary, indent=2))

    return overall_status


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Phase 1: Foundation - Prepare codebase for migration"
    )
    parser.add_argument("project_root", help="Root directory of the project")
    parser.add_argument(
        "-s",
        "--raw-scan",
        help="Path to raw-scan.json from phase 0",
    )
    parser.add_argument(
        "-o", "--output", default="./migration_output", help="Output directory for phase results"
    )

    args = parser.parse_args()

    exit_code = phase1_foundation(args.project_root, args.raw_scan, args.output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
