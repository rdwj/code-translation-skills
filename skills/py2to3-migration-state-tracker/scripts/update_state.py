#!/usr/bin/env python3
"""
Migration State Tracker — State Update Script

Provides subcommands for modifying the migration state: advancing modules
through phases, recording decisions, managing blockers, logging rollbacks,
and assigning conversion units.

Usage:
    python3 update_state.py <state_file> <command> [options]

Commands:
    advance          — Advance a module to the next phase
    decision         — Record a migration decision for a module or globally
    blocker          — Add a blocker to a module
    resolve-blocker  — Resolve an existing blocker
    rollback         — Record a phase rollback for a module
    note             — Add a free-form note to a module
    set-unit         — Assign a module to a conversion unit
    waiver           — Record a gate criterion waiver
    set-risk         — Override a module's risk score
    record-output    — Record a skill output file for a module's current phase
"""

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ── Helpers ────────────────────────────────────────────────────────────────

def load_state(path: str) -> Dict[str, Any]:
    """Load the migration state file."""
    if not os.path.exists(path):
        print(f"Error: State file not found: {path}", file=sys.stderr)
        print("Run init_state.py first to create the state file.", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: Dict[str, Any], path: str) -> None:
    """Save the migration state file, updating the last_updated timestamp."""
    state["project"]["last_updated"] = now_iso()

    # Recompute summary
    state["summary"] = compute_summary(state["modules"])

    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def short_id() -> str:
    """Generate a short unique ID for blockers etc."""
    return uuid.uuid4().hex[:8]


def get_module(state: Dict[str, Any], module_path: str) -> Dict[str, Any]:
    """Get a module entry, exiting with error if not found."""
    modules = state.get("modules", {})
    if module_path not in modules:
        print(f"Error: Module not found in state: {module_path}", file=sys.stderr)
        print(f"Known modules: {len(modules)}", file=sys.stderr)
        # Show close matches
        candidates = [m for m in modules if module_path in m or m in module_path]
        if candidates:
            print(f"Did you mean one of: {candidates[:5]}", file=sys.stderr)
        sys.exit(1)
    return modules[module_path]


def compute_summary(modules: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute summary statistics."""
    total = len(modules)
    by_phase = {"0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
    by_risk = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    for mod in modules.values():
        phase_key = str(mod.get("current_phase", 0))
        by_phase[phase_key] = by_phase.get(phase_key, 0) + 1
        risk = mod.get("risk_score", "medium").lower()
        by_risk[risk] = by_risk.get(risk, 0) + 1
    return {"total_modules": total, "by_phase": by_phase, "by_risk": by_risk}


PHASE_NAMES = {
    0: "Discovery",
    1: "Foundation",
    2: "Mechanical Conversion",
    3: "Semantic Fixes",
    4: "Verification",
    5: "Cutover",
}


# ── Commands ───────────────────────────────────────────────────────────────

def cmd_advance(state: Dict[str, Any], args) -> str:
    """Advance a module to the next phase."""
    mod = get_module(state, args.module)
    current = mod["current_phase"]
    next_phase = current + 1

    if next_phase > 5:
        return f"Module {args.module} is already at phase 5 (Cutover). Cannot advance further."

    # Check for unresolved blockers
    unresolved = [b for b in mod.get("blockers", []) if b.get("resolved") is None]
    if unresolved and not args.force:
        blocker_list = "\n".join(f"  - {b['description']}" for b in unresolved)
        return (
            f"Cannot advance {args.module}: {len(unresolved)} unresolved blocker(s):\n"
            f"{blocker_list}\n"
            f"Resolve blockers first, or use --force to override."
        )

    # Check conversion unit dependencies
    unit_name = mod.get("conversion_unit")
    if unit_name and not args.force:
        unit = state.get("conversion_units", {}).get(unit_name, {})
        dep_units = unit.get("dependencies", [])
        for dep_unit_name in dep_units:
            dep_unit = state.get("conversion_units", {}).get(dep_unit_name)
            if dep_unit and dep_unit.get("current_phase", 0) < next_phase:
                return (
                    f"Cannot advance {args.module}: conversion unit '{unit_name}' "
                    f"depends on '{dep_unit_name}' which is at phase "
                    f"{dep_unit.get('current_phase', 0)} (need phase {next_phase}).\n"
                    f"Use --force to override."
                )

    now = now_iso()

    # Complete the current phase
    if mod["phase_history"]:
        mod["phase_history"][-1]["completed"] = now
        mod["phase_history"][-1]["gate_passed"] = True
        if args.gate_report:
            mod["phase_history"][-1]["gate_report"] = args.gate_report

    # Start the next phase
    mod["current_phase"] = next_phase
    mod["phase_history"].append(
        {
            "phase": next_phase,
            "started": now,
            "completed": None,
            "gate_passed": False,
            "gate_report": None,
            "skill_outputs": [],
        }
    )

    # Update conversion unit phase if all members are at or past this phase
    if unit_name:
        unit = state.get("conversion_units", {}).get(unit_name, {})
        member_phases = []
        for member_path in unit.get("modules", []):
            member = state["modules"].get(member_path)
            if member:
                member_phases.append(member["current_phase"])
        if member_phases:
            unit["current_phase"] = min(member_phases)

    return (
        f"Advanced {args.module}: phase {current} ({PHASE_NAMES.get(current, '?')}) "
        f"→ phase {next_phase} ({PHASE_NAMES.get(next_phase, '?')})"
    )


def cmd_decision(state: Dict[str, Any], args) -> str:
    """Record a decision, either per-module or global."""
    entry = {
        "date": now_iso(),
        "decision": args.decision,
        "rationale": args.rationale or "",
        "made_by": args.made_by or "human",
        "skill_name": args.skill_name,
        "reversible": not args.irreversible,
    }

    if args.module:
        mod = get_module(state, args.module)
        mod.setdefault("decisions", []).append(entry)
        return f"Decision recorded for {args.module}: {args.decision}"
    else:
        state.setdefault("global_decisions", []).append(entry)
        return f"Global decision recorded: {args.decision}"


def cmd_blocker(state: Dict[str, Any], args) -> str:
    """Add a blocker to a module."""
    mod = get_module(state, args.module)
    blocker_id = f"blocker-{short_id()}"
    blocker = {
        "id": blocker_id,
        "description": args.description,
        "blocking_since": now_iso(),
        "resolved": None,
        "resolution": None,
    }
    mod.setdefault("blockers", []).append(blocker)
    return f"Blocker added to {args.module}: [{blocker_id}] {args.description}"


def cmd_resolve_blocker(state: Dict[str, Any], args) -> str:
    """Resolve an existing blocker."""
    mod = get_module(state, args.module)
    for blocker in mod.get("blockers", []):
        if blocker["id"] == args.blocker_id:
            if blocker.get("resolved"):
                return f"Blocker {args.blocker_id} is already resolved."
            blocker["resolved"] = now_iso()
            blocker["resolution"] = args.resolution
            return f"Blocker {args.blocker_id} resolved: {args.resolution}"
    return f"Error: Blocker {args.blocker_id} not found on {args.module}"


def cmd_rollback(state: Dict[str, Any], args) -> str:
    """Record a phase rollback."""
    mod = get_module(state, args.module)
    current = mod["current_phase"]
    target = args.to_phase

    if target >= current:
        return f"Error: Target phase {target} is not earlier than current phase {current}."

    now = now_iso()

    # Record in the module's history
    mod["current_phase"] = target
    if mod["phase_history"]:
        mod["phase_history"][-1]["completed"] = now
        mod["phase_history"][-1]["gate_passed"] = False

    mod["phase_history"].append(
        {
            "phase": target,
            "started": now,
            "completed": None,
            "gate_passed": False,
            "gate_report": None,
            "skill_outputs": [],
        }
    )

    # Record in the global rollbacks list
    rollback_entry = {
        "id": f"rollback-{short_id()}",
        "module": args.module,
        "from_phase": current,
        "to_phase": target,
        "reason": args.reason,
        "timestamp": now,
    }
    state.setdefault("rollbacks", []).append(rollback_entry)

    return (
        f"Rolled back {args.module}: phase {current} → phase {target}. "
        f"Reason: {args.reason}"
    )


def cmd_note(state: Dict[str, Any], args) -> str:
    """Add a free-form note to a module."""
    mod = get_module(state, args.module)
    note_entry = {
        "timestamp": now_iso(),
        "text": args.text,
    }
    mod.setdefault("notes", []).append(note_entry)
    return f"Note added to {args.module}"


def cmd_set_unit(state: Dict[str, Any], args) -> str:
    """Assign a module to a conversion unit."""
    mod = get_module(state, args.module)
    old_unit = mod.get("conversion_unit")
    mod["conversion_unit"] = args.unit

    # Add module to the unit's member list if it exists
    units = state.setdefault("conversion_units", {})
    if args.unit not in units:
        units[args.unit] = {
            "modules": [],
            "current_phase": 0,
            "dependencies": [],
            "risk_score": "medium",
            "assigned_to": None,
            "notes": [],
        }

    if args.module not in units[args.unit]["modules"]:
        units[args.unit]["modules"].append(args.module)

    # Remove from old unit if different
    if old_unit and old_unit != args.unit and old_unit in units:
        old_members = units[old_unit]["modules"]
        if args.module in old_members:
            old_members.remove(args.module)

    return f"Module {args.module} assigned to unit '{args.unit}'"


def cmd_waiver(state: Dict[str, Any], args) -> str:
    """Record a gate criterion waiver."""
    waiver = {
        "id": f"waiver-{short_id()}",
        "phase": args.phase,
        "criterion": args.criterion,
        "actual_value": args.actual_value,
        "justification": args.justification,
        "approved_by": args.approved_by,
        "timestamp": now_iso(),
        "module": args.module,
    }
    state.setdefault("waivers", []).append(waiver)
    scope = f"module {args.module}" if args.module else "global"
    return f"Waiver recorded ({scope}): {args.criterion} — {args.justification}"


def cmd_set_risk(state: Dict[str, Any], args) -> str:
    """Override a module's risk score."""
    mod = get_module(state, args.module)
    old_risk = mod.get("risk_score", "unknown")
    mod["risk_score"] = args.risk
    if args.reason:
        mod.setdefault("notes", []).append(
            {
                "timestamp": now_iso(),
                "text": f"Risk score changed from {old_risk} to {args.risk}: {args.reason}",
            }
        )
    return f"Risk score for {args.module}: {old_risk} → {args.risk}"


def cmd_record_output(state: Dict[str, Any], args) -> str:
    """Record a skill output file for a module's current phase."""
    mod = get_module(state, args.module)
    if mod["phase_history"]:
        mod["phase_history"][-1].setdefault("skill_outputs", []).append(args.output_path)
    return f"Output recorded for {args.module} (phase {mod['current_phase']}): {args.output_path}"


# ── CLI Setup ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Update migration state for a Python 2→3 migration."
    )
    parser.add_argument("state_file", help="Path to migration-state.json")

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # advance
    p_advance = subparsers.add_parser("advance", help="Advance a module to the next phase")
    p_advance.add_argument("--module", required=True, help="Module path")
    p_advance.add_argument("--gate-report", default=None, help="Path to gate check report")
    p_advance.add_argument(
        "--force", action="store_true",
        help="Override blocker and dependency checks"
    )

    # decision
    p_decision = subparsers.add_parser("decision", help="Record a decision")
    p_decision.add_argument("--module", default=None, help="Module path (omit for global)")
    p_decision.add_argument("--decision", required=True, help="Decision text")
    p_decision.add_argument("--rationale", default=None, help="Why this decision was made")
    p_decision.add_argument("--made-by", default="human", choices=["human", "skill"])
    p_decision.add_argument("--skill-name", default=None, help="Skill that made the decision")
    p_decision.add_argument(
        "--irreversible", action="store_true",
        help="Mark as irreversible"
    )

    # blocker
    p_blocker = subparsers.add_parser("blocker", help="Add a blocker")
    p_blocker.add_argument("--module", required=True, help="Module path")
    p_blocker.add_argument("--description", required=True, help="Blocker description")

    # resolve-blocker
    p_resolve = subparsers.add_parser("resolve-blocker", help="Resolve a blocker")
    p_resolve.add_argument("--module", required=True, help="Module path")
    p_resolve.add_argument("--blocker-id", required=True, help="Blocker ID to resolve")
    p_resolve.add_argument("--resolution", required=True, help="How the blocker was resolved")

    # rollback
    p_rollback = subparsers.add_parser("rollback", help="Record a rollback")
    p_rollback.add_argument("--module", required=True, help="Module path")
    p_rollback.add_argument("--from-phase", type=int, required=True, help="Phase rolling back from")
    p_rollback.add_argument("--to-phase", type=int, required=True, help="Phase rolling back to")
    p_rollback.add_argument("--reason", required=True, help="Reason for rollback")

    # note
    p_note = subparsers.add_parser("note", help="Add a note")
    p_note.add_argument("--module", required=True, help="Module path")
    p_note.add_argument("--text", required=True, help="Note text")

    # set-unit
    p_unit = subparsers.add_parser("set-unit", help="Assign module to conversion unit")
    p_unit.add_argument("--module", required=True, help="Module path")
    p_unit.add_argument("--unit", required=True, help="Conversion unit name")

    # waiver
    p_waiver = subparsers.add_parser("waiver", help="Record a gate criterion waiver")
    p_waiver.add_argument("--phase", type=int, required=True, help="Phase number")
    p_waiver.add_argument("--criterion", required=True, help="Gate criterion being waived")
    p_waiver.add_argument("--actual-value", required=True, help="Actual value that missed")
    p_waiver.add_argument("--justification", required=True, help="Why this is acceptable")
    p_waiver.add_argument("--approved-by", required=True, help="Who approved the waiver")
    p_waiver.add_argument("--module", default=None, help="Module path (omit for global)")

    # set-risk
    p_risk = subparsers.add_parser("set-risk", help="Override a module's risk score")
    p_risk.add_argument("--module", required=True, help="Module path")
    p_risk.add_argument(
        "--risk", required=True,
        choices=["low", "medium", "high", "critical"],
        help="New risk score"
    )
    p_risk.add_argument("--reason", default=None, help="Reason for the change")

    # record-output
    p_output = subparsers.add_parser("record-output", help="Record a skill output")
    p_output.add_argument("--module", required=True, help="Module path")
    p_output.add_argument("--output-path", required=True, help="Path to the output file")

    return parser


@log_execution
def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    state = load_state(args.state_file)

    command_map = {
        "advance": cmd_advance,
        "decision": cmd_decision,
        "blocker": cmd_blocker,
        "resolve-blocker": cmd_resolve_blocker,
        "rollback": cmd_rollback,
        "note": cmd_note,
        "set-unit": cmd_set_unit,
        "waiver": cmd_waiver,
        "set-risk": cmd_set_risk,
        "record-output": cmd_record_output,
    }

    handler = command_map.get(args.command)
    if not handler:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)

    result = handler(state, args)

    # Save updated state
    save_state(state, args.state_file)

    print(result)


if __name__ == "__main__":
    main()
