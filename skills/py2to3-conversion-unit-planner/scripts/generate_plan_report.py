#!/usr/bin/env python3
"""
Conversion Unit Planner — Markdown Report Generator

Reads conversion-plan.json and produces a human-readable markdown report
showing waves, units, risk scores, gateway modules, critical path, and
effort estimates.

Usage:
    python3 generate_plan_report.py <conversion_plan_json> \
        --output <output_path> \
        [--project-name "Legacy SCADA System"]

If --output is omitted, prints to stdout.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


RISK_EMOJI = {
    "low": "🟢",
    "medium": "🟡",
    "high": "🟠",
    "critical": "🔴",
}


def load_plan(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        print(f"Error: Plan file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Helpers ───────────────────────────────────────────────────────────────

def _bar(value: int, max_value: int, width: int = 20) -> str:
    """Render a simple text bar chart."""
    if max_value <= 0:
        return ""
    filled = round(value / max_value * width)
    return "█" * filled + "░" * (width - filled)


def _risk_badge(risk: str) -> str:
    """Return an emoji + label risk badge."""
    emoji = RISK_EMOJI.get(risk.lower(), "⚪")
    return f"{emoji} {risk.capitalize()}"


def _effort_label(hours: int) -> str:
    """Human-readable effort label."""
    if hours <= 0:
        return "< 1 hour"
    if hours < 8:
        return f"{hours} hours"
    days = round(hours / 8, 1)
    if days == int(days):
        days = int(days)
    return f"{hours}h (~{days} days)"


# ── Report Rendering ─────────────────────────────────────────────────────

def render_report(plan: Dict[str, Any], project_name: str = "") -> str:
    """Render the full conversion plan as markdown."""
    lines: List[str] = []

    timestamp = plan.get("timestamp", "")[:19]
    target = plan.get("target_version", "?")
    total_modules = plan.get("total_modules", 0)
    total_units = plan.get("total_units", 0)
    total_waves = plan.get("total_waves", 0)
    effort_days = plan.get("estimated_effort_days", 0)
    parallelism = plan.get("parallelism", 3)
    waves = plan.get("waves", [])
    critical_path = plan.get("critical_path", {})
    gateway_units = plan.get("gateway_units", [])

    # Title
    title = f"Conversion Plan: {project_name}" if project_name else "Conversion Plan"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Target**: Python {target}  ")
    lines.append(f"**Generated**: {timestamp}  ")
    lines.append(f"**Parallelism**: {parallelism} concurrent units")
    lines.append("")

    # ── Executive Summary ────────────────────────────────────────────────

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        f"| Modules | Units | Waves | Critical Path | Est. Effort |"
    )
    lines.append(
        f"|---------|-------|-------|---------------|-------------|"
    )
    cp_len = critical_path.get("length", 0)
    cp_days = critical_path.get("estimated_days", 0)
    lines.append(
        f"| {total_modules} | {total_units} | {total_waves} "
        f"| {cp_len} units ({cp_days} days) | {effort_days} person-days |"
    )
    lines.append("")

    # Risk distribution across all units
    all_units = []
    for wave in waves:
        all_units.extend(wave.get("units", []))

    risk_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for u in all_units:
        risk = u.get("risk_score", "medium").lower()
        risk_counts[risk] = risk_counts.get(risk, 0) + 1

    lines.append("**Risk distribution:**")
    lines.append("")
    for level in ["critical", "high", "medium", "low"]:
        count = risk_counts.get(level, 0)
        if count > 0:
            emoji = RISK_EMOJI.get(level, "⚪")
            lines.append(f"- {emoji} {level.capitalize()}: {count} units")
    lines.append("")

    # ── Gateway Units ────────────────────────────────────────────────────

    if gateway_units:
        lines.append("## Gateway Units (Bottlenecks)")
        lines.append("")
        lines.append(
            "These units have high fan-in — many downstream units depend on them. "
            "Failure here cascades widely. Budget extra review and testing time."
        )
        lines.append("")
        lines.append("| Unit | Fan-in | Wave | Risk | Notes |")
        lines.append("|------|--------|------|------|-------|")
        for gw in gateway_units:
            risk_badge = _risk_badge(gw.get("risk_score", "medium"))
            lines.append(
                f"| **{gw['name']}** "
                f"| {gw.get('fan_in', 0)} "
                f"| {gw.get('wave', '?')} "
                f"| {risk_badge} "
                f"| {gw.get('notes', '')} |"
            )
        lines.append("")

    # ── Critical Path ────────────────────────────────────────────────────

    if critical_path.get("units"):
        lines.append("## Critical Path")
        lines.append("")
        lines.append(
            f"The critical path is **{cp_len} units** long, "
            f"estimated at **{cp_days} days** minimum regardless of parallelism. "
            "This is the longest dependency chain through the conversion plan."
        )
        lines.append("")
        path_units = critical_path["units"]
        lines.append("```")
        for i, unit_name in enumerate(path_units):
            arrow = " → " if i < len(path_units) - 1 else ""
            lines.append(f"  [{i+1}] {unit_name}{arrow}")
        lines.append("```")
        lines.append("")

    # ── Wave-by-Wave Breakdown ───────────────────────────────────────────

    lines.append("## Wave Schedule")
    lines.append("")

    # Compute max effort across units for bar chart scaling
    max_effort = max(
        (u.get("estimated_effort_hours", 0) for u in all_units),
        default=1,
    ) or 1

    for wave_data in waves:
        wave_num = wave_data.get("wave", "?")
        wave_units = wave_data.get("units", [])

        wave_total_effort = sum(u.get("estimated_effort_hours", 0) for u in wave_units)
        wave_total_loc = sum(u.get("lines_of_code", 0) for u in wave_units)
        wave_total_modules = sum(u.get("module_count", len(u.get("modules", [])))
                                  for u in wave_units)

        lines.append(f"### Wave {wave_num}")
        lines.append("")
        lines.append(
            f"*{len(wave_units)} units, "
            f"{wave_total_modules} modules, "
            f"{wave_total_loc:,} LOC, "
            f"~{_effort_label(wave_total_effort)}*"
        )
        lines.append("")

        lines.append(
            "| Unit | Modules | LOC | Risk | Py2-isms | Effort | Dependencies |"
        )
        lines.append(
            "|------|---------|-----|------|----------|--------|--------------|"
        )

        for u in wave_units:
            name = u.get("name", "?")
            mod_count = u.get("module_count", len(u.get("modules", [])))
            loc = u.get("lines_of_code", 0)
            risk = _risk_badge(u.get("risk_score", "medium"))
            py2_count = u.get("py2_ism_count", 0)
            effort_h = u.get("estimated_effort_hours", 0)
            deps = u.get("dependencies", [])
            dep_str = ", ".join(deps) if deps else "—"
            is_cluster = u.get("is_cluster", False)
            cluster_marker = " 🔄" if is_cluster else ""

            lines.append(
                f"| **{name}**{cluster_marker} "
                f"| {mod_count} "
                f"| {loc:,} "
                f"| {risk} "
                f"| {py2_count} "
                f"| {_effort_label(effort_h)} "
                f"| {dep_str} |"
            )
        lines.append("")

    # ── Unit Details (expand clusters and gateway units) ─────────────────

    clusters = [u for u in all_units if u.get("is_cluster", False)]
    if clusters:
        lines.append("## Circular Dependency Clusters")
        lines.append("")
        lines.append(
            "These units contain modules with mutual imports — they must be "
            "converted together as a single atomic operation."
        )
        lines.append("")
        for u in clusters:
            lines.append(f"### 🔄 {u['name']}")
            lines.append("")
            modules = u.get("modules", [])
            for mod in modules:
                lines.append(f"- `{mod}`")
            lines.append("")

    # ── Effort Summary ───────────────────────────────────────────────────

    lines.append("## Effort Estimates")
    lines.append("")
    total_effort_hours = sum(u.get("estimated_effort_hours", 0) for u in all_units)
    lines.append(f"**Total estimated effort**: {total_effort_hours} hours ({effort_days} person-days)")
    lines.append("")

    # Effort by wave
    lines.append("| Wave | Units | Hours | Effort Bar |")
    lines.append("|------|-------|-------|------------|")

    max_wave_effort = 0
    wave_efforts = []
    for wave_data in waves:
        wave_num = wave_data.get("wave", "?")
        wave_units = wave_data.get("units", [])
        wave_effort = sum(u.get("estimated_effort_hours", 0) for u in wave_units)
        wave_efforts.append((wave_num, len(wave_units), wave_effort))
        max_wave_effort = max(max_wave_effort, wave_effort)

    for wave_num, unit_count, wave_effort in wave_efforts:
        bar = _bar(wave_effort, max_wave_effort or 1, 15)
        lines.append(f"| Wave {wave_num} | {unit_count} | {wave_effort}h | {bar} |")
    lines.append("")

    # ── Timeline Estimate ────────────────────────────────────────────────

    lines.append("## Timeline Estimate")
    lines.append("")
    lines.append(
        f"With **{parallelism} parallel workers**, the estimated wall-clock time is:"
    )
    lines.append("")

    # Compute wall-clock: each wave takes max(unit_efforts) / parallelism
    wall_clock_hours = 0
    for wave_data in waves:
        wave_units = wave_data.get("units", [])
        unit_efforts = sorted(
            [u.get("estimated_effort_hours", 0) for u in wave_units],
            reverse=True,
        )
        # With N parallel workers, wave time ≈ sum of efforts / parallelism
        wave_time = sum(unit_efforts) / parallelism
        wall_clock_hours += wave_time

    wall_clock_days = round(wall_clock_hours / 8, 1)
    lines.append(f"- **Parallel estimate**: ~{wall_clock_days} days wall-clock")
    lines.append(f"- **Sequential estimate**: ~{effort_days} person-days")
    lines.append(f"- **Critical path minimum**: ~{cp_days} days")
    lines.append("")
    lines.append(
        "*Note: These are rough estimates based on LOC and pattern complexity. "
        "Actual effort depends on test coverage, domain complexity, and team familiarity.*"
    )
    lines.append("")

    # ── Recommendations ──────────────────────────────────────────────────

    lines.append("## Recommendations")
    lines.append("")

    if gateway_units:
        lines.append("**Gateway units require extra attention:**")
        lines.append("")
        for gw in gateway_units[:3]:
            lines.append(
                f"- **{gw['name']}** (fan-in {gw.get('fan_in', 0)}): "
                f"Add extra characterization tests before conversion. "
                f"Schedule a focused review session after conversion."
            )
        lines.append("")

    if clusters:
        lines.append("**Circular dependency clusters must convert atomically:**")
        lines.append("")
        for u in clusters:
            lines.append(
                f"- **{u['name']}** ({len(u.get('modules', []))} modules): "
                f"Convert all modules in a single session. "
                f"Run full test suite between each change."
            )
        lines.append("")

    high_risk = [u for u in all_units
                 if u.get("risk_score", "").lower() in ("high", "critical")]
    if high_risk:
        lines.append("**High/critical risk units need semantic review:**")
        lines.append("")
        for u in high_risk[:5]:
            factors = u.get("risk_factors", [])
            factor_str = ", ".join(factors[:3]) if factors else "high complexity"
            lines.append(
                f"- **{u['name']}** ({_risk_badge(u['risk_score'])}): "
                f"{factor_str}"
            )
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate a markdown report from a conversion plan JSON."
    )
    parser.add_argument(
        "plan_file",
        help="Path to conversion-plan.json",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for markdown report (prints to stdout if omitted)",
    )
    parser.add_argument(
        "--project-name",
        default="",
        help="Project name for the report title",
    )

    args = parser.parse_args()
    plan = load_plan(args.plan_file)
    markdown = render_report(plan, args.project_name)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(markdown)
        print(f"Conversion plan report written to {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
