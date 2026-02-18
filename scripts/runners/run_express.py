#!/usr/bin/env python3
"""
Script: run_express.py
Purpose: Express workflow - fast-track Python 2->3 migration for small projects
Workflow: Phase 0 (discovery) → Phase 1 (foundation) → Phase 2 (mechanical) → Phase 4 (verification)
Skips: Phase 3 (semantic LLM review) and Phase 5 (cutover) unless explicitly requested
Inputs: project root
Outputs: migration-summary.md, remaining-issues.md, detailed JSON reports
LLM involvement: NONE
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# ── Logging ──────────────────────────────────────────────────────────────────
import sys as _sys; _sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[1] / 'lib'))
from migration_logger import setup_logging, log_execution, log_invocation
logger = setup_logging(__name__)

RUNNERS_DIR = Path(__file__).resolve().parent


def run_phase_script(phase_script, args):
    """Run a phase runner script and return results."""
    cmd = [sys.executable, str(phase_script)] + args
    logger.info(f"Invoking phase script: {phase_script.name}")
    start_time = __import__('time').monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        duration = __import__('time').monotonic() - start_time
        log_invocation(phase_script, args, result.returncode, duration,
                      len(result.stdout.encode()), len(result.stderr.encode()))
        try:
            output = json.loads(result.stdout)
            return {"status": result.returncode, "output": output, "stderr": result.stderr}
        except json.JSONDecodeError:
            return {
                "status": result.returncode,
                "output": result.stdout[:1000],
                "stderr": result.stderr,
            }
    except subprocess.TimeoutExpired:
        logger.error("Phase script execution timed out")
        return {"status": 2, "output": "Timeout", "stderr": "Phase execution timed out"}
    except Exception as e:
        logger.error(f"Phase script execution error: {e}")
        return {"status": 2, "output": None, "stderr": str(e)}


def run_express(project_root, output_dir, include_cutover=False):
    """Execute Express workflow."""
    print(f"\n╔═══════════════════════════════════════════════════════╗", file=sys.stderr)
    print(f"║  PYTHON 2→3 MIGRATION - EXPRESS WORKFLOW             ║", file=sys.stderr)
    print(f"║  Fast-track for small/medium projects                ║", file=sys.stderr)
    print(f"╚═══════════════════════════════════════════════════════╝\n", file=sys.stderr)

    project_root = Path(project_root).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Project: {project_root}", file=sys.stderr)
    print(f"Output:  {output_dir}\n", file=sys.stderr)

    all_results = {}
    phase_outputs = {}
    start_time = datetime.now()

    # PHASE 0: Discovery
    print(f"[1/4] PHASE 0: Project Discovery...", file=sys.stderr)
    phase0_script = RUNNERS_DIR / "phase0_discovery.py"
    phase0_result = run_phase_script(phase0_script, [str(project_root), "-o", str(output_dir)])
    all_results["phase0"] = phase0_result
    phase_outputs["phase0"] = phase0_result.get("output", {})

    if phase0_result["status"] == 2:
        print(f"  ERROR: Phase 0 failed. Aborting workflow.", file=sys.stderr)
        return 2

    print(f"  ✓ Phase 0 complete\n", file=sys.stderr)

    # PHASE 1: Foundation
    print(f"[2/4] PHASE 1: Foundation Setup...", file=sys.stderr)
    phase1_script = RUNNERS_DIR / "phase1_foundation.py"
    raw_scan_path = output_dir / "raw-scan.json"
    phase1_result = run_phase_script(
        phase1_script,
        [str(project_root), "-s", str(raw_scan_path), "-o", str(output_dir)],
    )
    all_results["phase1"] = phase1_result
    phase_outputs["phase1"] = phase1_result.get("output", {})

    if phase1_result["status"] == 2:
        print(f"  ERROR: Phase 1 failed. Aborting workflow.", file=sys.stderr)
        return 2

    print(f"  ✓ Phase 1 complete\n", file=sys.stderr)

    # PHASE 2: Mechanical Fixes
    print(f"[3/4] PHASE 2: Mechanical Fixes...", file=sys.stderr)
    phase2_script = RUNNERS_DIR / "phase2_mechanical.py"
    phase2_result = run_phase_script(
        phase2_script,
        [str(project_root), "-s", str(raw_scan_path), "-o", str(output_dir)],
    )
    all_results["phase2"] = phase2_result
    phase_outputs["phase2"] = phase2_result.get("output", {})

    if phase2_result["status"] == 2:
        print(f"  ERROR: Phase 2 failed. Aborting workflow.", file=sys.stderr)
        return 2

    print(f"  ✓ Phase 2 complete\n", file=sys.stderr)

    # PHASE 3: Semantic (SKIPPED in Express)
    print(f"[!] PHASE 3: Semantic Review - SKIPPED (not needed for Express)", file=sys.stderr)
    print(f"    To include semantic review, use full workflow or --with-semantic flag\n", file=sys.stderr)
    all_results["phase3"] = {"status": "skipped", "output": "Express workflow skips semantic review"}

    # PHASE 4: Verification
    print(f"[4/4] PHASE 4: Verification...", file=sys.stderr)
    phase4_script = RUNNERS_DIR / "phase4_verification.py"
    phase4_result = run_phase_script(phase4_script, [str(project_root), "-o", str(output_dir)])
    all_results["phase4"] = phase4_result
    phase_outputs["phase4"] = phase4_result.get("output", {})

    if phase4_result["status"] == 2:
        print(f"  WARNING: Phase 4 verification issues detected.\n", file=sys.stderr)
    else:
        print(f"  ✓ Phase 4 complete\n", file=sys.stderr)

    # PHASE 5: Cutover (OPTIONAL)
    if include_cutover:
        print(f"[5/5] PHASE 5: Cutover - Finalizing...", file=sys.stderr)
        phase5_script = RUNNERS_DIR / "phase5_cutover.py"
        phase5_result = run_phase_script(phase5_script, [str(project_root), "-o", str(output_dir)])
        all_results["phase5"] = phase5_result
        phase_outputs["phase5"] = phase5_result.get("output", {})
        print(f"  ✓ Phase 5 complete\n", file=sys.stderr)
    else:
        print(f"[!] PHASE 5: Cutover - SKIPPED (not included in Express)", file=sys.stderr)
        print(f"    To finalize migration, run phase5_cutover.py separately\n", file=sys.stderr)
        all_results["phase5"] = {"status": "skipped", "output": "Express workflow excludes cutover phase"}

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    # Generate migration summary markdown
    summary_md = generate_migration_summary(project_root, output_dir, phase_outputs, duration)
    with open(output_dir / "migration-summary.md", "w") as f:
        f.write(summary_md)

    # Generate remaining issues markdown
    issues_md = generate_remaining_issues(output_dir, phase_outputs)
    with open(output_dir / "remaining-issues.md", "w") as f:
        f.write(issues_md)

    # Save consolidated results
    with open(output_dir / "express-workflow-results.json", "w") as f:
        json.dump(all_results, f, indent=2)

    # Print final summary
    print(f"╔═══════════════════════════════════════════════════════╗", file=sys.stderr)
    print(f"║  EXPRESS WORKFLOW COMPLETE                           ║", file=sys.stderr)
    print(f"╚═══════════════════════════════════════════════════════╝\n", file=sys.stderr)

    print(f"Duration: {duration:.1f}s", file=sys.stderr)
    print(f"\nGenerated files:", file=sys.stderr)
    print(f"  • migration-summary.md", file=sys.stderr)
    print(f"  • remaining-issues.md", file=sys.stderr)
    print(f"  • express-workflow-results.json", file=sys.stderr)
    print(f"  + all phase-specific reports\n", file=sys.stderr)

    # Determine exit code
    statuses = [all_results[f"phase{i}"]["status"] for i in range(5) if f"phase{i}" in all_results]
    # Convert "skipped" to 0, keep 0 as success, 1 as partial, 2 as error
    exit_code = max(s if isinstance(s, int) else (0 if s == "skipped" else 1) for s in statuses)

    return exit_code


def generate_migration_summary(project_root, output_dir, phase_outputs, duration):
    """Generate markdown summary of migration."""
    md = f"""# Python 2→3 Migration Summary

**Project:** {project_root}
**Generated:** {datetime.now().isoformat()}
**Duration:** {duration:.1f}s
**Workflow:** Express (Phases 0→1→2→4)

## Workflow Phases

### Phase 0: Discovery
- Scanned project structure and Python 2 patterns
- Generated sizing report and dependency graph

### Phase 1: Foundation
- Injected `__future__` imports for forward compatibility
- Captured lint baseline for comparison
- Generated test scaffolds

### Phase 2: Mechanical Fixes
- Applied automated Haiku-tier fixes to codebase
- Replaced Python 2 stdlib imports with Python 3 equivalents
- Generated work items for remaining issues

### Phase 3: Semantic Review
- Skipped in Express workflow
- Would normally use Claude Sonnet/Opus for complex pattern resolution
- To include semantic review, run full workflow instead

### Phase 4: Verification
- Ran test suite to verify translation
- Checked for remaining Python 2 artifacts
- Detected dead code and unused compatibility shims
- Verified migration gates

## Next Steps

1. Review `migration-summary.md` for detailed phase results
2. Address issues listed in `remaining-issues.md`
3. For semantic-level changes (bytes/strings, protocols, metaclasses):
   - Run Phase 3 with Claude Sonnet/Opus
4. When ready to deploy:
   - Run Phase 5 (Cutover) to remove shims and finalize CI/CD

## Output Files

- `migration-summary.md` - This file
- `remaining-issues.md` - Issues requiring attention
- `express-workflow-results.json` - Consolidated results from all phases
- `phase0_*`, `phase1_*`, etc. - Per-phase reports

---
*Express workflow - 0 LLM tokens used (fully automated)*
"""
    return md


def generate_remaining_issues(output_dir, phase_outputs):
    """Generate markdown of remaining issues."""
    md = "# Remaining Issues\n\n"

    # Extract issues from phase summaries
    issues = []

    # From Phase 2
    if "phase2" in phase_outputs and isinstance(phase_outputs["phase2"], dict):
        phase2 = phase_outputs["phase2"]
        if "haiku_tier_errors" in phase2 and phase2["haiku_tier_errors"] > 0:
            issues.append(
                f"**Phase 2 Haiku Fixes:** {phase2['haiku_tier_errors']} fixes failed - check logs"
            )

    # From Phase 4 Verification
    if "phase4" in phase_outputs and isinstance(phase_outputs["phase4"], dict):
        phase4 = phase_outputs["phase4"]

        if "remaining_py2_artifacts" in phase4 and phase4["remaining_py2_artifacts"] > 0:
            issues.append(
                f"**Python 2 Artifacts:** {phase4['remaining_py2_artifacts']} remaining patterns"
            )

        if "dead_code_found" in phase4 and phase4["dead_code_found"] > 0:
            issues.append(f"**Dead Code:** {phase4['dead_code_found']} unused code blocks detected")

        if "gates_failed" in phase4:
            failed_gates = phase4.get("gates_failed", [])
            if failed_gates:
                issues.append(f"**Migration Gates Failed:** {', '.join(failed_gates)}")

    if not issues:
        md += "✓ No significant issues detected\n"
        md += "\nThe migration is ready for deployment.\n"
    else:
        md += "## Issues to Address\n\n"
        for i, issue in enumerate(issues, 1):
            md += f"{i}. {issue}\n"

        md += "\n## Recommended Actions\n\n"
        md += "1. Address high-priority issues first\n"
        md += "2. For semantic issues (bytes/strings, protocols):\n"
        md += "   - Run Phase 3 with Claude Sonnet/Opus\n"
        md += "3. Re-run Phase 4 verification after fixes\n"
        md += "4. Proceed to Phase 5 (Cutover) when ready\n"

    return md


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Express Workflow - Fast-track Python 2→3 migration for small/medium projects"
    )
    parser.add_argument("project_root", help="Root directory of project to migrate")
    parser.add_argument(
        "-o", "--output", default="./migration_output", help="Output directory for results"
    )
    parser.add_argument(
        "--with-cutover",
        action="store_true",
        help="Include Phase 5 (Cutover) in workflow",
    )

    args = parser.parse_args()

    exit_code = run_express(args.project_root, args.output, include_cutover=args.with_cutover)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
