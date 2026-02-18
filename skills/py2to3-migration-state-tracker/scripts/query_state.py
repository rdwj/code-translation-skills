#!/usr/bin/env python3
"""
Migration State Tracker — Query & Dashboard Script

Read-only queries against the migration state. Produces human-readable
output for the terminal or generates a markdown dashboard file.

Usage:
    python3 query_state.py <state_file> <command> [options]

Commands:
    dashboard       — Overall progress summary (prints to stdout or writes markdown)
    module          — Show a specific module's state
    by-phase        — List modules at a given phase
    by-risk         — List modules at a given risk level
    blockers        — Show all unresolved blockers
    can-advance     — Check if a module can advance to the next phase
    decisions       — Show decisions (per-module or global)
    timeline        — Estimate completion based on velocity
    units           — Show conversion unit summary
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

PHASE_NAMES = {
    0: "Discovery",
    1: "Foundation",
    2: "Mechanical Conversion",
    3: "Semantic Fixes",
    4: "Verification",
    5: "Cutover",
}


def load_state(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        print(f"Error: State file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Dashboard ──────────────────────────────────────────────────────────────

def cmd_dashboard(state: Dict[str, Any], args) -> str:
    """Generate the migration progress dashboard."""
    project = state["project"]
    summary = state.get("summary", {})
    modules = state.get("modules", {})
    rollbacks = state.get("rollbacks", [])
    waivers = state.get("waivers", [])

    total = summary.get("total_modules", len(modules))
    by_phase = summary.get("by_phase", {})
    by_risk = summary.get("by_risk", {})

    # Compute percentage complete (phase 5 = done)
    done = int(by_phase.get("5", 0))
    pct_done = (done / total * 100) if total > 0 else 0

    # Weighted progress: each phase contributes proportionally
    weighted = 0
    for phase_str, count in by_phase.items():
        weighted += int(phase_str) * int(count)
    max_weighted = total * 5
    weighted_pct = (weighted / max_weighted * 100) if max_weighted > 0 else 0

    lines = []
    lines.append(f"# Migration Dashboard — {project['name']}")
    lines.append("")
    lines.append(f"**Target**: Python {project['target_version']}  ")
    lines.append(f"**Last updated**: {project.get('last_updated', 'unknown')}  ")
    lines.append(f"**Weighted progress**: {weighted_pct:.1f}%")
    lines.append("")

    # Phase breakdown
    lines.append("## Phase Breakdown")
    lines.append("")
    for phase_num in range(6):
        count = int(by_phase.get(str(phase_num), 0))
        pct = (count / total * 100) if total > 0 else 0
        bar_len = int(pct / 2)
        bar = "█" * bar_len + "░" * (50 - bar_len)
        lines.append(
            f"| Phase {phase_num}: {PHASE_NAMES[phase_num]:<24s} | "
            f"{count:>4d} ({pct:>5.1f}%) | `{bar}` |"
        )
    lines.append(f"| {'**Total**':<33s} | {total:>4d}        |{'':>53s}|")
    lines.append("")

    # Risk summary
    lines.append("## Risk Summary")
    lines.append("")
    for risk_level in ["critical", "high", "medium", "low"]:
        count = int(by_risk.get(risk_level, 0))
        marker = "🔴" if risk_level == "critical" else (
            "🟠" if risk_level == "high" else (
                "🟡" if risk_level == "medium" else "🟢"
            )
        )
        lines.append(f"- {marker} **{risk_level.capitalize()}**: {count} modules")
    lines.append("")

    # Active blockers
    all_blockers = []
    for mod_path, mod in modules.items():
        for b in mod.get("blockers", []):
            if b.get("resolved") is None:
                all_blockers.append((mod_path, b))

    if all_blockers:
        lines.append(f"## Active Blockers ({len(all_blockers)})")
        lines.append("")
        for mod_path, b in all_blockers:
            lines.append(f"- **{mod_path}** [{b['id']}]: {b['description']}")
            lines.append(f"  (since {b.get('blocking_since', 'unknown')})")
        lines.append("")
    else:
        lines.append("## Active Blockers: None")
        lines.append("")

    # Recent rollbacks
    if rollbacks:
        recent = sorted(rollbacks, key=lambda r: r.get("timestamp", ""), reverse=True)[:5]
        lines.append(f"## Recent Rollbacks (last {len(recent)})")
        lines.append("")
        for rb in recent:
            lines.append(
                f"- **{rb['module']}**: Phase {rb['from_phase']} → {rb['to_phase']} "
                f"— {rb['reason']} ({rb.get('timestamp', '')[:10]})"
            )
        lines.append("")

    # Waivers
    if waivers:
        lines.append(f"## Waivers ({len(waivers)})")
        lines.append("")
        for w in waivers:
            scope = f"module {w['module']}" if w.get("module") else "global"
            lines.append(
                f"- Phase {w['phase']} ({scope}): **{w['criterion']}** "
                f"(actual: {w['actual_value']}) — {w['justification']}"
            )
        lines.append("")

    # Recent decisions
    all_decisions = list(state.get("global_decisions", []))
    for mod_path, mod in modules.items():
        for d in mod.get("decisions", []):
            d_with_module = dict(d)
            d_with_module["_module"] = mod_path
            all_decisions.append(d_with_module)

    if all_decisions:
        recent_decisions = sorted(
            all_decisions, key=lambda d: d.get("date", ""), reverse=True
        )[:10]
        lines.append(f"## Recent Decisions (last {len(recent_decisions)})")
        lines.append("")
        for d in recent_decisions:
            scope = d.get("_module", "GLOBAL")
            lines.append(f"- [{scope}] **{d['decision']}**")
            if d.get("rationale"):
                lines.append(f"  Rationale: {d['rationale']}")
        lines.append("")

    output = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        return f"Dashboard written to {args.output}"
    return output


# ── Module Detail ──────────────────────────────────────────────────────────

def cmd_module(state: Dict[str, Any], args) -> str:
    """Show detailed state for a specific module."""
    mod_path = args.path
    modules = state.get("modules", {})
    if mod_path not in modules:
        # Try partial match
        matches = [m for m in modules if mod_path in m]
        if len(matches) == 1:
            mod_path = matches[0]
        elif matches:
            return f"Ambiguous module path. Matches:\n" + "\n".join(f"  - {m}" for m in matches)
        else:
            return f"Module not found: {mod_path}"

    mod = modules[mod_path]
    lines = []
    lines.append(f"# {mod_path}")
    lines.append(f"**Phase**: {mod['current_phase']} ({PHASE_NAMES.get(mod['current_phase'], '?')})")
    lines.append(f"**Risk**: {mod.get('risk_score', 'unknown')}")
    if mod.get("conversion_unit"):
        lines.append(f"**Conversion Unit**: {mod['conversion_unit']}")
    if mod.get("risk_factors"):
        lines.append(f"**Risk Factors**: {', '.join(mod['risk_factors'])}")

    # Metrics
    metrics = mod.get("metrics", {})
    if metrics:
        lines.append(f"\n**Metrics**: {metrics.get('lines_of_code', '?')} LOC, "
                      f"{metrics.get('num_functions', '?')} functions, "
                      f"{metrics.get('num_classes', '?')} classes, "
                      f"fan-in: {metrics.get('dependency_fan_in', '?')}, "
                      f"fan-out: {metrics.get('dependency_fan_out', '?')}")

    # Py2-ism counts
    counts = mod.get("py2_ism_counts", {})
    if any(v > 0 for v in counts.values()):
        lines.append(f"\n**Py2 patterns**: " + ", ".join(
            f"{k}: {v}" for k, v in counts.items() if v > 0
        ))

    # Phase history
    if mod.get("phase_history"):
        lines.append("\n**Phase History**:")
        for ph in mod["phase_history"]:
            status = "✓" if ph.get("gate_passed") else "…"
            completed = ph.get("completed", "in progress")
            lines.append(
                f"  {status} Phase {ph['phase']}: started {ph['started'][:10]}, "
                f"{'completed ' + completed[:10] if completed and completed != 'in progress' else 'in progress'}"
            )

    # Blockers
    blockers = mod.get("blockers", [])
    if blockers:
        lines.append(f"\n**Blockers** ({len(blockers)}):")
        for b in blockers:
            status = "RESOLVED" if b.get("resolved") else "ACTIVE"
            lines.append(f"  [{status}] {b['id']}: {b['description']}")
            if b.get("resolution"):
                lines.append(f"    Resolution: {b['resolution']}")

    # Decisions
    decisions = mod.get("decisions", [])
    if decisions:
        lines.append(f"\n**Decisions** ({len(decisions)}):")
        for d in decisions:
            lines.append(f"  - [{d.get('date', '?')[:10]}] {d['decision']}")
            if d.get("rationale"):
                lines.append(f"    Why: {d['rationale']}")

    # Notes
    notes = mod.get("notes", [])
    if notes:
        lines.append(f"\n**Notes** ({len(notes)}):")
        for n in notes:
            if isinstance(n, dict):
                lines.append(f"  - [{n.get('timestamp', '?')[:10]}] {n.get('text', str(n))}")
            else:
                lines.append(f"  - {n}")

    return "\n".join(lines)


# ── Filtering ──────────────────────────────────────────────────────────────

def cmd_by_phase(state: Dict[str, Any], args) -> str:
    """List modules at a given phase."""
    target = args.phase
    modules = state.get("modules", {})
    matches = {p: m for p, m in modules.items() if m.get("current_phase") == target}

    if not matches:
        return f"No modules at phase {target} ({PHASE_NAMES.get(target, '?')})"

    lines = [f"## Modules at Phase {target}: {PHASE_NAMES.get(target, '?')} ({len(matches)})", ""]
    for path, mod in sorted(matches.items()):
        risk = mod.get("risk_score", "?")
        unit = mod.get("conversion_unit", "—")
        lines.append(f"- {path}  (risk: {risk}, unit: {unit})")
    return "\n".join(lines)


def cmd_by_risk(state: Dict[str, Any], args) -> str:
    """List modules by risk level."""
    target = args.risk.lower()
    modules = state.get("modules", {})
    matches = {p: m for p, m in modules.items() if m.get("risk_score", "").lower() == target}

    if not matches:
        return f"No modules with risk level '{target}'"

    lines = [f"## {target.capitalize()} Risk Modules ({len(matches)})", ""]
    for path, mod in sorted(matches.items()):
        phase = mod.get("current_phase", 0)
        factors = ", ".join(mod.get("risk_factors", [])) or "none specified"
        lines.append(f"- {path}  (phase {phase}, factors: {factors})")
    return "\n".join(lines)


# ── Blockers ───────────────────────────────────────────────────────────────

def cmd_blockers(state: Dict[str, Any], args) -> str:
    """Show all unresolved blockers across the project."""
    modules = state.get("modules", {})
    active = []
    for mod_path, mod in modules.items():
        for b in mod.get("blockers", []):
            if b.get("resolved") is None:
                active.append((mod_path, b))

    if not active:
        return "No active blockers."

    lines = [f"## Active Blockers ({len(active)})", ""]
    for mod_path, b in sorted(active, key=lambda x: x[1].get("blocking_since", "")):
        lines.append(f"**{mod_path}** [{b['id']}]")
        lines.append(f"  {b['description']}")
        lines.append(f"  Since: {b.get('blocking_since', 'unknown')}")
        lines.append("")
    return "\n".join(lines)


# ── Can Advance ────────────────────────────────────────────────────────────

def cmd_can_advance(state: Dict[str, Any], args) -> str:
    """Check whether a module can advance to the next phase."""
    mod_path = args.module
    modules = state.get("modules", {})
    if mod_path not in modules:
        return f"Module not found: {mod_path}"

    mod = modules[mod_path]
    current = mod["current_phase"]
    next_phase = current + 1

    if next_phase > 5:
        return f"{mod_path} is at phase 5 — already at final phase."

    issues = []

    # Check unresolved blockers
    unresolved = [b for b in mod.get("blockers", []) if b.get("resolved") is None]
    if unresolved:
        issues.append(f"{len(unresolved)} unresolved blocker(s):")
        for b in unresolved:
            issues.append(f"  - [{b['id']}] {b['description']}")

    # Check conversion unit dependency constraints
    unit_name = mod.get("conversion_unit")
    if unit_name:
        unit = state.get("conversion_units", {}).get(unit_name, {})

        # Check that all unit members are at the same phase
        for member_path in unit.get("modules", []):
            if member_path == mod_path:
                continue
            member = modules.get(member_path)
            if member and member.get("current_phase", 0) < current:
                issues.append(
                    f"Unit member {member_path} is at phase {member['current_phase']} "
                    f"(must be at least {current})"
                )

        # Check dependency units
        for dep_unit_name in unit.get("dependencies", []):
            dep_unit = state.get("conversion_units", {}).get(dep_unit_name)
            if dep_unit and dep_unit.get("current_phase", 0) < next_phase:
                issues.append(
                    f"Dependent unit '{dep_unit_name}' is at phase "
                    f"{dep_unit['current_phase']} (need {next_phase})"
                )

    if issues:
        return (
            f"❌ {mod_path} CANNOT advance to phase {next_phase} "
            f"({PHASE_NAMES.get(next_phase, '?')}):\n" + "\n".join(issues)
        )
    return (
        f"✅ {mod_path} CAN advance to phase {next_phase} "
        f"({PHASE_NAMES.get(next_phase, '?')})"
    )


# ── Decisions ──────────────────────────────────────────────────────────────

def cmd_decisions(state: Dict[str, Any], args) -> str:
    """Show decisions, per-module or global."""
    lines = []

    if args.module:
        modules = state.get("modules", {})
        if args.module not in modules:
            return f"Module not found: {args.module}"
        decisions = modules[args.module].get("decisions", [])
        if not decisions:
            return f"No decisions recorded for {args.module}"
        lines.append(f"## Decisions for {args.module} ({len(decisions)})")
        lines.append("")
        for d in decisions:
            lines.append(f"**[{d.get('date', '?')[:10]}]** {d['decision']}")
            if d.get("rationale"):
                lines.append(f"  Rationale: {d['rationale']}")
            lines.append(f"  Made by: {d.get('made_by', '?')}")
            if d.get("skill_name"):
                lines.append(f"  Skill: {d['skill_name']}")
            lines.append("")
    elif args.show_global:
        decisions = state.get("global_decisions", [])
        if not decisions:
            return "No global decisions recorded."
        lines.append(f"## Global Decisions ({len(decisions)})")
        lines.append("")
        for d in decisions:
            lines.append(f"**[{d.get('date', '?')[:10]}]** {d['decision']}")
            if d.get("rationale"):
                lines.append(f"  Rationale: {d['rationale']}")
            lines.append("")
    else:
        return "Specify --module <path> or --global"

    return "\n".join(lines)


# ── Timeline ───────────────────────────────────────────────────────────────

def cmd_timeline(state: Dict[str, Any], args) -> str:
    """Estimate completion timeline based on observed velocity."""
    modules = state.get("modules", {})
    total = len(modules)

    if total == 0:
        return "No modules tracked."

    # Calculate how many phase-transitions have happened and when
    transitions = []
    for mod_path, mod in modules.items():
        for ph in mod.get("phase_history", []):
            if ph.get("completed") and ph.get("gate_passed"):
                try:
                    ts = datetime.fromisoformat(ph["completed"].replace("Z", "+00:00"))
                    transitions.append(ts)
                except (ValueError, TypeError):
                    pass

    if len(transitions) < 2:
        return (
            "Not enough data for timeline projection. "
            f"Only {len(transitions)} phase transition(s) recorded so far."
        )

    transitions.sort()
    first = transitions[0]
    last = transitions[-1]
    elapsed = (last - first).total_seconds()
    if elapsed <= 0:
        return "Timeline data is too compressed to project."

    transitions_per_day = len(transitions) / (elapsed / 86400)

    # How many transitions remain: each module needs to reach phase 5
    remaining = 0
    for mod in modules.values():
        remaining += 5 - mod.get("current_phase", 0)

    if transitions_per_day > 0:
        days_remaining = remaining / transitions_per_day
        est_completion = datetime.now(timezone.utc) + timedelta(days=days_remaining)
    else:
        days_remaining = float("inf")
        est_completion = None

    lines = [
        "## Timeline Projection",
        "",
        f"- Total modules: {total}",
        f"- Phase transitions completed: {len(transitions)}",
        f"- Phase transitions remaining: {remaining}",
        f"- Velocity: {transitions_per_day:.1f} transitions/day",
        f"- Estimated days remaining: {days_remaining:.0f}",
    ]
    if est_completion:
        lines.append(f"- Estimated completion: {est_completion.strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append(
        "*Note: This is a rough projection based on observed velocity. "
        "Later phases typically take longer than earlier ones.*"
    )
    return "\n".join(lines)


# ── Conversion Units ──────────────────────────────────────────────────────

def cmd_units(state: Dict[str, Any], args) -> str:
    """Show conversion unit summary."""
    units = state.get("conversion_units", {})
    if not units:
        return "No conversion units defined yet."

    lines = [f"## Conversion Units ({len(units)})", ""]
    for name, unit in sorted(units.items()):
        members = unit.get("modules", [])
        phase = unit.get("current_phase", 0)
        risk = unit.get("risk_score", "?")
        deps = unit.get("dependencies", [])
        lines.append(f"### {name}")
        lines.append(f"- Phase: {phase} ({PHASE_NAMES.get(phase, '?')})")
        lines.append(f"- Risk: {risk}")
        lines.append(f"- Members ({len(members)}):")
        for m in members:
            lines.append(f"  - {m}")
        if deps:
            lines.append(f"- Depends on: {', '.join(deps)}")
        lines.append("")
    return "\n".join(lines)


# ── CLI Setup ──────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query migration state for a Python 2→3 migration."
    )
    parser.add_argument("state_file", help="Path to migration-state.json")

    subparsers = parser.add_subparsers(dest="command", help="Query to run")

    # dashboard
    p_dash = subparsers.add_parser("dashboard", help="Overall progress dashboard")
    p_dash.add_argument("--output", default=None, help="Write dashboard to file")

    # module
    p_mod = subparsers.add_parser("module", help="Show module detail")
    p_mod.add_argument("--path", required=True, help="Module path")

    # by-phase
    p_phase = subparsers.add_parser("by-phase", help="List modules by phase")
    p_phase.add_argument("--phase", type=int, required=True, help="Phase number")

    # by-risk
    p_risk = subparsers.add_parser("by-risk", help="List modules by risk")
    p_risk.add_argument(
        "--risk", required=True,
        choices=["low", "medium", "high", "critical"],
        help="Risk level"
    )

    # blockers
    subparsers.add_parser("blockers", help="Show all active blockers")

    # can-advance
    p_adv = subparsers.add_parser("can-advance", help="Check if module can advance")
    p_adv.add_argument("--module", required=True, help="Module path")

    # decisions
    p_dec = subparsers.add_parser("decisions", help="Show decisions")
    p_dec.add_argument("--module", default=None, help="Module path")
    p_dec.add_argument("--global", dest="show_global", action="store_true", help="Show global decisions")

    # timeline
    subparsers.add_parser("timeline", help="Project completion timeline")

    # units
    subparsers.add_parser("units", help="Show conversion units")

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
        "dashboard": cmd_dashboard,
        "module": cmd_module,
        "by-phase": cmd_by_phase,
        "by-risk": cmd_by_risk,
        "blockers": cmd_blockers,
        "can-advance": cmd_can_advance,
        "decisions": cmd_decisions,
        "timeline": cmd_timeline,
        "units": cmd_units,
    }

    handler = command_map.get(args.command)
    if not handler:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)

    result = handler(state, args)
    print(result)


if __name__ == "__main__":
    main()
