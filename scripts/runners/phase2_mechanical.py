#!/usr/bin/env python3
"""
Script: phase2_mechanical.py
Purpose: Execute mechanical phase - generate work items, apply Haiku-tier fixes, replace stdlib imports
Inputs: project root, raw-scan.json, output directory
Outputs: fixed files, conversion report, work items status
LLM involvement: NONE
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent / "skills"


def run_script(script_path, args, description):
    """Run a script, capture output, handle errors."""
    if not script_path.exists():
        return {"status": "skipped", "reason": f"Script not found: {script_path}"}

    cmd = [sys.executable, str(script_path)] + args
    print(f"  → {description}...", file=sys.stderr)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
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
        return {"status": "timeout"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def phase2_mechanical(project_root, raw_scan_path, output_dir):
    """Execute mechanical phase."""
    print(f"\n[PHASE 2] Mechanical - Apply automated fixes", file=sys.stderr)
    print(f"  Project root: {project_root}", file=sys.stderr)
    print(f"  Raw scan: {raw_scan_path}", file=sys.stderr)
    print(f"  Output dir: {output_dir}", file=sys.stderr)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {}

    # Step 1: Generate work items
    script_path = SKILLS_DIR / "work-item-generator" / "scripts" / "generate_work_items.py"
    work_items = run_script(
        script_path, [str(raw_scan_path), str(output_dir)], "Generating work items"
    )
    results["work_items"] = work_items

    work_items_list = []
    if work_items["status"] in ["complete", "partial"]:
        work_items_output = work_items.get("output", {})
        if isinstance(work_items_output, dict):
            with open(output_dir / "work-items.json", "w") as f:
                json.dump(work_items_output, f, indent=2)
            # Extract work items for processing
            if "items" in work_items_output:
                work_items_list = work_items_output["items"]

    # Step 2: Apply Haiku-tier fixes (loop over work items)
    haiku_fixed = 0
    haiku_errors = 0
    script_path = SKILLS_DIR / "haiku-pattern-fixer" / "scripts" / "apply_fix.py"

    for item in work_items_list:
        if item.get("tier") == "HAIKU" or item.get("tier") == "haiku":
            item_id = item.get("id", "unknown")
            item_file = item.get("file", "unknown")
            fix_result = run_script(
                script_path,
                [str(item_id), str(item_file), str(output_dir)],
                f"Applying Haiku fix to {item_file}",
            )
            if fix_result["status"] in ["complete", "partial"]:
                haiku_fixed += 1
            else:
                haiku_errors += 1

    results["haiku_fixes"] = {
        "status": "complete" if haiku_errors == 0 else "partial",
        "fixed": haiku_fixed,
        "errors": haiku_errors,
    }

    # Step 3: Replace Py2 stdlib imports (optional)
    script_path = SKILLS_DIR / "py2to3-library-replacement" / "scripts" / "replace_libs.py"
    lib_replacement = run_script(
        script_path, [str(project_root), str(output_dir)], "Replacing Python 2 stdlib imports"
    )
    results["library_replacement"] = lib_replacement
    if lib_replacement["status"] in ["complete", "partial"]:
        lib_output = lib_replacement.get("output", {})
        if isinstance(lib_output, dict):
            with open(output_dir / "library-replacement-report.json", "w") as f:
                json.dump(lib_output, f, indent=2)

    # Generate mechanical summary
    summary = {
        "phase": "mechanical",
        "project_root": str(project_root),
        "output_dir": str(output_dir),
        "steps": {
            "work_items_generation": work_items.get("status", "unknown"),
            "haiku_fixes": results["haiku_fixes"]["status"],
            "library_replacement": lib_replacement.get("status", "unknown"),
        },
        "work_items_processed": len(work_items_list),
        "haiku_tier_fixed": haiku_fixed,
        "haiku_tier_errors": haiku_errors,
    }

    # Extract metrics if available
    if isinstance(work_items.get("output"), dict):
        work_data = work_items["output"]
        if "total_items" in work_data:
            summary["total_work_items"] = work_data["total_items"]
        if "haiku_count" in work_data:
            summary["haiku_tier_items"] = work_data["haiku_count"]

    with open(output_dir / "mechanical-summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    # Print summary
    print(f"\n[PHASE 2 SUMMARY]", file=sys.stderr)
    print(f"  Work items generated: {work_items['status']}", file=sys.stderr)
    print(f"  Haiku fixes applied: {haiku_fixed}", file=sys.stderr)
    if haiku_errors > 0:
        print(f"  Haiku fix errors: {haiku_errors}", file=sys.stderr)
    print(f"  Library replacement: {lib_replacement['status']}", file=sys.stderr)

    if "total_work_items" in summary:
        print(f"  Total work items: {summary['total_work_items']}", file=sys.stderr)

    # Determine overall status
    statuses = [work_items["status"], lib_replacement["status"]]
    haiku_status = results["haiku_fixes"]["status"]
    statuses.append(haiku_status)

    if all(s in ["complete", "partial"] for s in statuses):
        overall_status = 0
    elif any(s == "error" for s in statuses):
        overall_status = 2
    else:
        overall_status = 1

    print(f"\n  Output files: {list(output_dir.glob('*.json'))}", file=sys.stderr)
    if haiku_errors == 0:
        print(f"\nAll Haiku-tier work items completed. Ready for Phase 3 (semantic review)", file=sys.stderr)
    else:
        print(f"\nSome Haiku fixes failed. Review errors before proceeding.", file=sys.stderr)

    # Output JSON summary
    print(json.dumps(summary, indent=2))

    return overall_status


def main():
    parser = argparse.ArgumentParser(
        description="Phase 2: Mechanical - Apply automated fixes to codebase"
    )
    parser.add_argument("project_root", help="Root directory of the project")
    parser.add_argument(
        "-s", "--raw-scan", help="Path to raw-scan.json from phase 0", default="raw-scan.json"
    )
    parser.add_argument(
        "-o", "--output", default="./migration_output", help="Output directory for phase results"
    )

    args = parser.parse_args()

    exit_code = phase2_mechanical(args.project_root, args.raw_scan, args.output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
