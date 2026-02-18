#!/usr/bin/env python3
"""
Script: phase4_verification.py
Purpose: Execute verification phase - run tests, check completeness, find dead code, verify gates
Inputs: project root, migration state, output directory
Outputs: verification report, gate check results, dead code analysis
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


def phase4_verification(project_root, output_dir):
    """Execute verification phase."""
    print(f"\n[PHASE 4] Verification - Test and validate migration", file=sys.stderr)
    print(f"  Project root: {project_root}", file=sys.stderr)
    print(f"  Output dir: {output_dir}", file=sys.stderr)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Step 1: Run tests and verify translation (optional)
    script_path = SKILLS_DIR / "translation-verifier" / "scripts" / "verify_translation.py"
    verification = run_script(
        script_path, [str(project_root), str(output_dir)], "Running translation verification"
    )
    results["verification"] = verification
    if verification["status"] in ["complete", "partial"]:
        verify_output = verification.get("output", {})
        if isinstance(verify_output, dict):
            with open(output_dir / "verification-report.json", "w") as f:
                json.dump(verify_output, f, indent=2)

    # Step 2: Check for remaining Py2 artifacts (optional)
    script_path = SKILLS_DIR / "py2to3-completeness-checker" / "scripts" / "check_completeness.py"
    completeness = run_script(
        script_path, [str(project_root), str(output_dir)], "Checking migration completeness"
    )
    results["completeness"] = completeness
    if completeness["status"] in ["complete", "partial"]:
        comp_output = completeness.get("output", {})
        if isinstance(comp_output, dict):
            with open(output_dir / "completeness-report.json", "w") as f:
                json.dump(comp_output, f, indent=2)

    # Step 3: Detect dead code (optional)
    script_path = SKILLS_DIR / "py2to3-dead-code-detector" / "scripts" / "detect_dead_code.py"
    dead_code = run_script(
        script_path, [str(project_root), str(output_dir)], "Detecting dead code"
    )
    results["dead_code"] = dead_code
    if dead_code["status"] in ["complete", "partial"]:
        dead_output = dead_code.get("output", {})
        if isinstance(dead_output, dict):
            with open(output_dir / "dead-code-report.json", "w") as f:
                json.dump(dead_output, f, indent=2)

    # Step 4: Check phase gates (optional)
    script_path = SKILLS_DIR / "py2to3-gate-checker" / "scripts" / "check_gate.py"
    gate_check = run_script(
        script_path, [str(project_root), str(output_dir)], "Checking migration gates"
    )
    results["gate_check"] = gate_check
    if gate_check["status"] in ["complete", "partial"]:
        gate_output = gate_check.get("output", {})
        if isinstance(gate_output, dict):
            with open(output_dir / "gate-check-report.json", "w") as f:
                json.dump(gate_output, f, indent=2)

    # Generate verification summary
    summary = {
        "phase": "verification",
        "project_root": str(project_root),
        "output_dir": str(output_dir),
        "steps": {
            "translation_verification": verification.get("status", "unknown"),
            "completeness_check": completeness.get("status", "unknown"),
            "dead_code_detection": dead_code.get("status", "unknown"),
            "gate_check": gate_check.get("status", "unknown"),
        },
    }

    # Extract metrics if available
    if verification["status"] in ["complete", "partial"] and isinstance(verification.get("output"), dict):
        verify_data = verification["output"]
        if "test_results" in verify_data:
            summary["tests_run"] = verify_data.get("tests_run", 0)
            summary["tests_passed"] = verify_data.get("tests_passed", 0)
        if "confidence_score" in verify_data:
            summary["confidence_score"] = verify_data["confidence_score"]

    if completeness["status"] in ["complete", "partial"] and isinstance(completeness.get("output"), dict):
        comp_data = completeness["output"]
        if "py2_artifacts_found" in comp_data:
            summary["remaining_py2_artifacts"] = comp_data["py2_artifacts_found"]

    if dead_code["status"] in ["complete", "partial"] and isinstance(dead_code.get("output"), dict):
        dead_data = dead_code["output"]
        if "dead_code_items" in dead_data:
            summary["dead_code_found"] = len(dead_data["dead_code_items"])

    if gate_check["status"] in ["complete", "partial"] and isinstance(gate_check.get("output"), dict):
        gate_data = gate_check["output"]
        if "gates_passed" in gate_data:
            summary["gates_passed"] = gate_data["gates_passed"]
        if "gates_failed" in gate_data:
            summary["gates_failed"] = gate_data.get("gates_failed", [])

    with open(output_dir / "verification-summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"\n[PHASE 4 SUMMARY]", file=sys.stderr)
    print(f"  Verification: {verification['status']}", file=sys.stderr)
    print(f"  Completeness: {completeness['status']}", file=sys.stderr)
    print(f"  Dead code: {dead_code['status']}", file=sys.stderr)
    print(f"  Gate check: {gate_check['status']}", file=sys.stderr)

    if "tests_run" in summary:
        print(
            f"  Tests: {summary.get('tests_passed', 0)}/{summary.get('tests_run', 0)} passed",
            file=sys.stderr,
        )
    if "confidence_score" in summary:
        print(f"  Confidence: {summary['confidence_score']}", file=sys.stderr)
    if "remaining_py2_artifacts" in summary and summary["remaining_py2_artifacts"] > 0:
        print(f"  Py2 artifacts remaining: {summary['remaining_py2_artifacts']}", file=sys.stderr)
    if "dead_code_found" in summary and summary["dead_code_found"] > 0:
        print(f"  Dead code found: {summary['dead_code_found']}", file=sys.stderr)

    # Determine overall status based on gate check and tests
    statuses = [verification["status"], completeness["status"], dead_code["status"], gate_check["status"]]

    if gate_check["status"] == "complete" and all(s in ["complete", "partial"] for s in statuses):
        overall_status = 0
    elif gate_check["status"] == "error" or any(s == "error" for s in statuses):
        overall_status = 2
    else:
        overall_status = 1

    print(f"\n  Output files: {list(output_dir.glob('*.json'))}", file=sys.stderr)

    if overall_status == 0:
        print(f"\nVerification passed. Ready for Phase 5 (cutover)", file=sys.stderr)
    elif overall_status == 1:
        print(f"\nVerification partial. Review reports before proceeding.", file=sys.stderr)
    else:
        print(f"\nVerification failed. Review errors and retry.", file=sys.stderr)

    # Output JSON summary
    print(json.dumps(summary, indent=2))

    return overall_status


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Phase 4: Verification - Test and validate migration"
    )
    parser.add_argument("project_root", help="Root directory of the project")
    parser.add_argument(
        "-o", "--output", default="./migration_output", help="Output directory for phase results"
    )

    args = parser.parse_args()

    exit_code = phase4_verification(args.project_root, args.output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
