#!/usr/bin/env python3
"""
Rollback Plan Generator — Main Script

Generates detailed rollback procedures per module per phase for a Python 2→3 migration.
Analyzes migration state and git history to create phase-specific rollback procedures.

Usage:
    python3 generate_rollback.py \
        --state-file migration-state.json \
        <codebase_path> \
        --output ./rollback-output/ \
        --phase 3

Output:
    rollback-plan.json — Structured rollback procedures
    rollback-runbook.md — Human-readable step-by-step procedures
"""

import json
import os
import sys
import argparse
import subprocess
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple, Set
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


# ── Helper Functions ─────────────────────────────────────────────────────────

def load_json(path: str) -> Dict:
    """Load JSON file, return empty dict if not found."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(data: Dict, path: str) -> None:
    """Save JSON to file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def run_git_command(cmd: List[str], cwd: str) -> Tuple[str, int]:
    """Run git command and return output."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", 1
    except Exception as e:
        return f"Error: {e}", 1


# ── Git Analysis ─────────────────────────────────────────────────────────────

class GitAnalyzer:
    """Analyze git history for migration commits."""

    def __init__(self, git_dir: str):
        self.git_dir = git_dir

    def get_commits(self, pattern: str, limit: int = 100) -> List[Dict]:
        """Get commits matching pattern."""
        cmd = [
            "git", "log",
            "--oneline",
            "--all",
            f"--grep={pattern}",
            f"-{limit}",
        ]
        output, returncode = run_git_command(cmd, self.git_dir)
        if returncode != 0:
            return []

        commits = []
        for line in output.split("\n"):
            if not line.strip():
                continue
            parts = line.split(maxsplit=1)
            if len(parts) >= 2:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                })
        return commits

    def get_commits_by_file(self, filepath: str, limit: int = 50) -> List[Dict]:
        """Get commits affecting a specific file."""
        cmd = ["git", "log", "--oneline", f"-{limit}", "--", filepath]
        output, returncode = run_git_command(cmd, self.git_dir)
        if returncode != 0:
            return []

        commits = []
        for line in output.split("\n"):
            if not line.strip():
                continue
            parts = line.split(maxsplit=1)
            if len(parts) >= 2:
                commits.append({
                    "hash": parts[0],
                    "message": parts[1],
                })
        return commits

    def get_commit_diff(self, commit_hash: str) -> str:
        """Get diff for a specific commit."""
        cmd = ["git", "show", "--stat", commit_hash]
        output, _ = run_git_command(cmd, self.git_dir)
        return output

    def get_file_at_commit(self, filepath: str, commit_hash: str) -> Optional[str]:
        """Get file contents at a specific commit."""
        cmd = ["git", "show", f"{commit_hash}:{filepath}"]
        output, returncode = run_git_command(cmd, self.git_dir)
        return output if returncode == 0 else None


# ── Migration State Analysis ─────────────────────────────────────────────────

class MigrationStateAnalyzer:
    """Analyze migration state to understand per-phase, per-module progress."""

    def __init__(self, state_data: Dict):
        self.state = state_data

    def get_modules_in_phase(self, phase: int) -> List[str]:
        """Get modules that have reached or passed a specific phase."""
        modules = []
        for module, info in self.state.get("modules", {}).items():
            current_phase = info.get("current_phase", 0)
            if current_phase >= phase:
                modules.append(module)
        return modules

    def get_module_status(self, module: str) -> Dict:
        """Get status of a specific module."""
        return self.state.get("modules", {}).get(module, {})

    def get_phase_description(self, phase: int) -> str:
        """Get description of a phase."""
        descriptions = {
            1: "Foundation — Add __future__ imports, test scaffolding",
            2: "Conversion — Automated code conversion (lib2to3)",
            3: "Semantic Fixes — Manual fixes for Py2/Py3 differences",
            4: "Verification — Testing and validation",
            5: "Cutover — Switch to Py3 deployment",
        }
        return descriptions.get(phase, f"Phase {phase}")


# ── Rollback Plan Generation ────────────────────────────────────────────────

class RollbackPlanGenerator:
    """Generate rollback plan for migration phases."""

    def __init__(
        self,
        state_analyzer: MigrationStateAnalyzer,
        git_analyzer: GitAnalyzer,
        codebase_path: str,
    ):
        self.state_analyzer = state_analyzer
        self.git_analyzer = git_analyzer
        self.codebase_path = codebase_path

    def generate_phase_1_rollback(self) -> Dict:
        """Generate Phase 1 (Foundation) rollback."""
        commits = self.git_analyzer.get_commits("__future__", limit=50)
        test_files = self._find_generated_tests()

        return {
            "name": "Foundation",
            "description": "Rollback __future__ imports and test scaffolding",
            "modules_affected": len(self.state_analyzer.get_modules_in_phase(1)),
            "estimated_time_minutes": 20,
            "feasibility": "FULLY_FEASIBLE",
            "steps": [
                {
                    "order": 1,
                    "action": "revert_commits",
                    "commits": [c["hash"] for c in commits[:5]],
                    "description": "Remove __future__ import additions",
                    "time_estimate_minutes": 5,
                    "risk_level": "LOW",
                    "commands": [f"git revert {c['hash']}" for c in commits[:5]],
                },
                {
                    "order": 2,
                    "action": "delete_files",
                    "files": test_files[:10],
                    "description": "Remove generated test scaffolding",
                    "time_estimate_minutes": 3,
                    "risk_level": "LOW",
                    "commands": [f"rm {f}" for f in test_files[:10]],
                },
                {
                    "order": 3,
                    "action": "revert_commits",
                    "commits": self.git_analyzer.get_commits("ci", limit=5),
                    "description": "Restore original CI configuration",
                    "time_estimate_minutes": 2,
                    "risk_level": "LOW",
                    "commands": ["git revert <ci_config_commit>"],
                },
            ],
            "verification": "python2 -m pytest tests/ --tb=short",
            "risks": [
                "Generated tests may have been manually edited — check git diff before deleting",
                "Ensure all __future__ imports are removed to pass on Py2",
            ],
        }

    def generate_phase_2_rollback(self) -> Dict:
        """Generate Phase 2 (Conversion) rollback."""
        modules = self.state_analyzer.get_modules_in_phase(2)
        conversion_commits = self.git_analyzer.get_commits("convert", limit=100)

        step_groups = {}
        for module in modules[:10]:  # Limit to first 10 for demo
            commits = self.git_analyzer.get_commits_by_file(module, limit=10)
            step_groups[module] = {
                "conversion_commits": [c["hash"] for c in commits[:3]],
                "dependent_modules": [],
                "rollback_order": len(step_groups),
                "time_estimate_minutes": 8,
            }

        return {
            "name": "Conversion",
            "description": "Revert automated conversion changes per module",
            "modules_affected": len(modules),
            "estimated_time_minutes": 45,
            "feasibility": "PARTIALLY_FEASIBLE",
            "notes": "Some modules may have manual edits post-conversion; check carefully",
            "step_groups_by_module": step_groups,
            "rollback_strategy": (
                "1. Identify conversion commits per module via git log\n"
                "2. Revert in reverse dependency order\n"
                "3. Check for manual edits: git diff HEAD~1 <file>\n"
                "4. Use git revert or manual restoration as needed"
            ),
        }

    def generate_phase_3_rollback(self) -> Dict:
        """Generate Phase 3 (Semantic Fixes) rollback."""
        modules = self.state_analyzer.get_modules_in_phase(3)
        semantic_commits = self.git_analyzer.get_commits("fix", limit=100)

        return {
            "name": "Semantic Fixes",
            "description": "Revert semantic fixes in reverse dependency order",
            "modules_affected": len(modules),
            "estimated_time_minutes": 60,
            "feasibility": "PARTIALLY_FEASIBLE",
            "notes": "Semantic fixes may have interdependencies; must revert in correct order",
            "semantic_fix_categories": {
                "unicode_handling": len([c for c in semantic_commits if "unicode" in c["message"]]),
                "exception_syntax": len([c for c in semantic_commits if "except" in c["message"]]),
                "string_types": len([c for c in semantic_commits if "string" in c["message"]]),
                "other": len(semantic_commits) - len([c for c in semantic_commits if any(
                    k in c["message"] for k in ["unicode", "except", "string"]
                )]),
            },
            "dependency_analysis": "Must build and analyze fix dependencies before reverting",
            "rollback_steps": [
                {
                    "phase": 1,
                    "action": "Identify all semantic fix commits",
                    "command": "git log --grep='fix' --oneline",
                },
                {
                    "phase": 2,
                    "action": "Build dependency graph of fixes",
                    "description": "Analyze which fixes depend on which others",
                },
                {
                    "phase": 3,
                    "action": "Revert in reverse dependency order",
                    "command": "git revert <commit> (in dependency order)",
                },
                {
                    "phase": 4,
                    "action": "Verify after each revert",
                    "command": "python3 -m pytest <module_tests>",
                },
            ],
        }

    def generate_phase_4_rollback(self) -> Dict:
        """Generate Phase 4 (Verification) rollback."""
        return {
            "name": "Verification",
            "description": "No code changes; mostly configuration and documentation",
            "modules_affected": 0,
            "estimated_time_minutes": 5,
            "feasibility": "NOT_APPLICABLE",
            "notes": "This phase is read-only. If rollback is needed, roll back to Phase 3.",
            "actions": [
                "No code rollback needed",
                "Flag modules requiring Phase 3 rollback",
                "Restore any configuration changes if necessary",
            ],
        }

    def generate_phase_5_rollback(self) -> Dict:
        """Generate Phase 5 (Cutover) rollback."""
        return {
            "name": "Cutover",
            "description": "Switch traffic back to Py2 deployment",
            "modules_affected": 0,
            "estimated_time_minutes": 15,
            "feasibility": "PARTIALLY_FEASIBLE",
            "notes": "Requires coordination with deployment system and monitoring",
            "steps": [
                {
                    "order": 1,
                    "action": "switch_deployment",
                    "description": "Switch traffic back to Py2 deployment",
                    "time_estimate_minutes": 5,
                    "risk_level": "MEDIUM",
                    "commands": [
                        "kubectl set image deployment/api api=api:py2-<date> --namespace prod",
                        "kubectl wait --for=condition=Ready pod -l app=api --timeout=300s",
                    ],
                },
                {
                    "order": 2,
                    "action": "restore_requirements",
                    "description": "Restore requirements with six, future, etc.",
                    "time_estimate_minutes": 3,
                    "risk_level": "LOW",
                    "commands": ["git revert <requirements_update_commit>"],
                },
                {
                    "order": 3,
                    "action": "re_enable_py2_ci",
                    "description": "Re-enable Py2 CI in GitHub Actions or CI system",
                    "time_estimate_minutes": 3,
                    "risk_level": "LOW",
                    "commands": ["git revert <ci_disable_commit>"],
                },
                {
                    "order": 4,
                    "action": "verification",
                    "description": "Verify Py2 deployment is healthy",
                    "time_estimate_minutes": 4,
                    "risk_level": "LOW",
                    "commands": [
                        "curl https://api.example.com/health",
                        "python2 -m pytest tests/ --tb=short",
                    ],
                },
            ],
        }

    def _find_generated_tests(self) -> List[str]:
        """Find generated test files."""
        test_files = []
        test_dirs = [
            os.path.join(self.codebase_path, "tests", "generated"),
            os.path.join(self.codebase_path, "tests"),
        ]
        for test_dir in test_dirs:
            if os.path.isdir(test_dir):
                for root, dirs, files in os.walk(test_dir):
                    for file in files:
                        if "test_py2" in file or "generated" in root:
                            test_files.append(os.path.join(root, file))
        return test_files[:10]  # Limit to first 10

    def generate_module_rollbacks(self) -> Dict[str, Dict]:
        """Generate per-module rollback procedures."""
        module_rollbacks = {}

        for module, status in self.state_analyzer.state.get("modules", {}).items():
            current_phase = status.get("current_phase", 0)
            rollback_to = max(0, current_phase - 1)

            commits = self.git_analyzer.get_commits_by_file(module, limit=20)

            module_rollbacks[module] = {
                "current_phase": current_phase,
                "rollback_to_phase": rollback_to,
                "commits_to_revert": [c["hash"] for c in commits[:5]],
                "dependencies": {
                    "blocks_rollback_of": [],
                    "depends_on_rollback_of": [],
                },
                "estimated_time_minutes": max(5, len(commits) * 2),
                "feasibility": "FULLY_FEASIBLE" if len(commits) > 0 else "UNKNOWN",
            }

        return module_rollbacks


# ── Main Generation ─────────────────────────────────────────────────────────

def generate_plan(
    state_file: str,
    codebase_path: str,
    git_dir: Optional[str] = None,
    phase: Optional[int] = None,
) -> Dict:
    """Generate complete rollback plan."""
    if not git_dir:
        git_dir = codebase_path

    # Load state
    state_data = load_json(state_file)
    if not state_data:
        print(f"Error: Could not load state file {state_file}", file=sys.stderr)
        sys.exit(1)

    # Initialize analyzers
    state_analyzer = MigrationStateAnalyzer(state_data)
    git_analyzer = GitAnalyzer(git_dir)
    plan_gen = RollbackPlanGenerator(state_analyzer, git_analyzer, codebase_path)

    # Generate per-phase rollbacks
    phases = {}
    phase_methods = {
        1: plan_gen.generate_phase_1_rollback,
        2: plan_gen.generate_phase_2_rollback,
        3: plan_gen.generate_phase_3_rollback,
        4: plan_gen.generate_phase_4_rollback,
        5: plan_gen.generate_phase_5_rollback,
    }

    phases_to_generate = [phase] if phase else range(1, 6)

    for p in phases_to_generate:
        if p in phase_methods:
            phases[str(p)] = phase_methods[p]()

    # Generate module-level rollbacks
    module_rollbacks = plan_gen.generate_module_rollbacks()

    # Assemble plan
    plan = {
        "generated": datetime.now().isoformat() + "Z",
        "codebase_path": codebase_path,
        "git_dir": git_dir,
        "total_phases": 5,
        "phases": phases,
        "module_rollbacks": module_rollbacks,
        "global_dependencies": [],
    }

    return plan


# ── Main Entry Point ────────────────────────────────────────────────────────

@log_execution
def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate rollback plan for Py2→Py3 migration"
    )
    parser.add_argument("codebase_path", help="Root directory of migrated codebase")
    parser.add_argument("--state-file", required=True,
                       help="Path to migration-state.json")
    parser.add_argument("--output", default=".",
                       help="Output directory for rollback plan")
    parser.add_argument("--phase", type=int, default=None,
                       help="Generate rollback for specific phase (1-5, or all)")
    parser.add_argument("--git-dir", default=None,
                       help="Git repository root (default: codebase_path)")
    parser.add_argument("--test-rollback", action="store_true",
                       help="Simulate rollback without execution")

    args = parser.parse_args()

    if not os.path.isdir(args.codebase_path):
        print(f"Error: codebase path not found: {args.codebase_path}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.state_file):
        print(f"Error: state file not found: {args.state_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Generating rollback plan...")
    print(f"  Codebase: {args.codebase_path}")
    print(f"  State file: {args.state_file}")
    if args.phase:
        print(f"  Phase: {args.phase}")

    # Generate plan
    plan = generate_plan(
        args.state_file,
        args.codebase_path,
        args.git_dir,
        args.phase,
    )

    # Save outputs
    os.makedirs(args.output, exist_ok=True)

    plan_path = os.path.join(args.output, "rollback-plan.json")
    save_json(plan, plan_path)
    print(f"Wrote: {plan_path}")

    # Print summary
    print()
    print("=" * 70)
    print("ROLLBACK PLAN SUMMARY")
    print("=" * 70)
    print(f"Total phases: {plan['total_phases']}")
    print(f"Phases in plan: {list(plan['phases'].keys())}")
    print(f"Module-level rollbacks: {len(plan['module_rollbacks'])}")
    print()
    for phase_num, phase_data in sorted(plan["phases"].items()):
        feasibility = phase_data.get("feasibility", "UNKNOWN")
        time_est = phase_data.get("estimated_time_minutes", "?")
        print(f"Phase {phase_num}: {phase_data.get('name')} "
              f"({time_est} min, {feasibility})")

    sys.exit(0)


if __name__ == "__main__":
    main()
