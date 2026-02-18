#!/usr/bin/env python3
"""
Script: phase5_cutover.py
Purpose: Execute cutover phase - remove compatibility shims, update build configs, generate CI, create dashboard
Inputs: project root, migration state, output directory
Outputs: cutover report, CI config, final dashboard HTML
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


def phase5_cutover(project_root, output_dir):
    """Execute cutover phase."""
    print(f"\n[PHASE 5] Cutover - Finalize Python 3 migration", file=sys.stderr)
    print(f"  Project root: {project_root}", file=sys.stderr)
    print(f"  Output dir: {output_dir}", file=sys.stderr)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Step 1: Remove compatibility shims (optional)
    script_path = (
        SKILLS_DIR / "py2to3-compatibility-shim-remover" / "scripts" / "remove_shims.py"
    )
    shim_removal = run_script(
        script_path, [str(project_root), str(output_dir)], "Removing compatibility shims"
    )
    results["shim_removal"] = shim_removal
    if shim_removal["status"] in ["complete", "partial"]:
        shim_output = shim_removal.get("output", {})
        if isinstance(shim_output, dict):
            with open(output_dir / "shim-removal-report.json", "w") as f:
                json.dump(shim_output, f, indent=2)

    # Step 2: Update build system configs (optional)
    script_path = SKILLS_DIR / "py2to3-build-system-updater" / "scripts" / "update_build.py"
    build_update = run_script(
        script_path, [str(project_root), str(output_dir)], "Updating build system configs"
    )
    results["build_update"] = build_update
    if build_update["status"] in ["complete", "partial"]:
        build_output = build_update.get("output", {})
        if isinstance(build_output, dict):
            with open(output_dir / "build-update-report.json", "w") as f:
                json.dump(build_output, f, indent=2)

    # Step 3: Generate CI config (optional)
    script_path = SKILLS_DIR / "py2to3-ci-dual-interpreter" / "scripts" / "generate_ci.py"
    ci_generation = run_script(
        script_path, [str(project_root), str(output_dir)], "Generating CI configuration"
    )
    results["ci_generation"] = ci_generation
    if ci_generation["status"] in ["complete", "partial"]:
        ci_output = ci_generation.get("output", {})
        if isinstance(ci_output, dict):
            with open(output_dir / "ci-config-report.json", "w") as f:
                json.dump(ci_output, f, indent=2)

    # Step 4: Generate final dashboard (optional)
    script_path = SKILLS_DIR / "migration-dashboard" / "scripts" / "generate_dashboard.py"
    dashboard = run_script(
        script_path, [str(project_root), str(output_dir)], "Generating final migration dashboard"
    )
    results["dashboard"] = dashboard
    if dashboard["status"] in ["complete", "partial"]:
        dashboard_output = dashboard.get("output", {})
        if isinstance(dashboard_output, dict):
            with open(output_dir / "dashboard-report.json", "w") as f:
                json.dump(dashboard_output, f, indent=2)

    # Generate cutover summary
    summary = {
        "phase": "cutover",
        "project_root": str(project_root),
        "output_dir": str(output_dir),
        "steps": {
            "shim_removal": shim_removal.get("status", "unknown"),
            "build_update": build_update.get("status", "unknown"),
            "ci_generation": ci_generation.get("status", "unknown"),
            "dashboard_generation": dashboard.get("status", "unknown"),
        },
    }

    # Extract metrics if available
    if shim_removal["status"] in ["complete", "partial"] and isinstance(shim_removal.get("output"), dict):
        shim_data = shim_removal["output"]
        if "shims_removed" in shim_data:
            summary["shims_removed"] = shim_data["shims_removed"]
        if "files_modified" in shim_data:
            summary["files_with_shim_removal"] = shim_data["files_modified"]

    if build_update["status"] in ["complete", "partial"] and isinstance(build_update.get("output"), dict):
        build_data = build_update["output"]
        if "configs_updated" in build_data:
            summary["build_configs_updated"] = build_data["configs_updated"]

    if ci_generation["status"] in ["complete", "partial"] and isinstance(ci_generation.get("output"), dict):
        ci_data = ci_generation["output"]
        if "ci_files_generated" in ci_data:
            summary["ci_files_generated"] = ci_data["ci_files_generated"]

    if dashboard["status"] in ["complete", "partial"] and isinstance(dashboard.get("output"), dict):
        dash_data = dashboard["output"]
        if "dashboard_file" in dash_data:
            summary["dashboard_file"] = dash_data["dashboard_file"]

    # Step 5: Final security audit + SBOM
    security_dir = output_dir / "security"
    security_dir.mkdir(parents=True, exist_ok=True)
    script_path = SKILLS_DIR / "py2to3-security-scanner" / "scripts" / "security_scan.py"
    baseline_report = output_dir.parent / "phase-0-discovery" / "security" / "security-report.json"
    security_args = [str(project_root), "--mode", "final", "-o", str(security_dir)]
    if baseline_report.exists():
        security_args += ["--baseline-report", str(baseline_report)]
    security = run_script(script_path, security_args, "Final security audit + SBOM")
    results["security"] = security
    summary["security_audit"] = security.get("status", "unknown")

    # Check for critical security findings
    if security["status"] in ["complete", "partial"] and isinstance(security.get("output"), dict):
        sec_data = security["output"]
        summary["security_critical"] = sec_data.get("critical", 0)
        summary["security_high"] = sec_data.get("high", 0)
        summary["sbom_generated"] = sec_data.get("sbom_generated", False)

    with open(output_dir / "cutover-summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"\n[PHASE 5 SUMMARY]", file=sys.stderr)
    print(f"  Shim removal: {shim_removal['status']}", file=sys.stderr)
    print(f"  Build update: {build_update['status']}", file=sys.stderr)
    print(f"  CI generation: {ci_generation['status']}", file=sys.stderr)
    print(f"  Dashboard: {dashboard['status']}", file=sys.stderr)
    print(f"  Security audit: {security['status']}", file=sys.stderr)
    if summary.get("sbom_generated"):
        print(f"  SBOM: {security_dir / 'sbom.json'}", file=sys.stderr)

    if "shims_removed" in summary:
        print(f"  Shims removed: {summary['shims_removed']}", file=sys.stderr)
    if "build_configs_updated" in summary:
        print(f"  Build configs updated: {summary['build_configs_updated']}", file=sys.stderr)
    if "ci_files_generated" in summary:
        print(f"  CI files generated: {summary['ci_files_generated']}", file=sys.stderr)

    # Determine overall status
    statuses = [
        shim_removal["status"],
        build_update["status"],
        ci_generation["status"],
        dashboard["status"],
    ]

    if all(s in ["complete", "partial"] for s in statuses):
        overall_status = 0
    elif any(s == "error" for s in statuses):
        overall_status = 2
    else:
        overall_status = 1

    print(f"\n  Output files: {list(output_dir.glob('*.json'))}", file=sys.stderr)

    if overall_status == 0:
        print(f"\nCutover complete! Migration to Python 3 is finalized.", file=sys.stderr)
        if "dashboard_file" in summary:
            print(f"  Review dashboard: {summary['dashboard_file']}", file=sys.stderr)
    else:
        print(f"\nCutover partial or failed. Review reports for next steps.", file=sys.stderr)

    # Output JSON summary
    print(json.dumps(summary, indent=2))

    return overall_status


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Phase 5: Cutover - Finalize Python 3 migration and deploy"
    )
    parser.add_argument("project_root", help="Root directory of the project")
    parser.add_argument(
        "-o", "--output", default="./migration_output", help="Output directory for phase results"
    )

    args = parser.parse_args()

    exit_code = phase5_cutover(args.project_root, args.output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
