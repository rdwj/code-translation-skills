#!/usr/bin/env python3
"""
Skill Usage Dashboard Generator

Parses migration-audit.log and skill-invocations.jsonl to produce a
self-contained HTML dashboard showing which skills and scripts actually
ran during a migration, which were skipped (and why), failures, and
execution-time breakdowns.

Usage:
    python generate_skill_usage_dashboard.py <analysis_dir> \
        [--output skill-usage-dashboard.html] \
        [--skills-root <path>]

Where <analysis_dir> is the migration-analysis/ directory containing:
  - logs/migration-audit.log
  - logs/skill-invocations.jsonl
  - state/migration-state.json  (optional, for sizing/workflow context)
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ── Skill Manifest (fallback if filesystem walk fails) ─────────────────────

SKILL_MANIFEST: Dict[str, List[str]] = {
    "behavioral-contract-extractor": ["extract_contracts.py"],
    "haiku-pattern-fixer": ["apply_fix.py"],
    "migration-dashboard": ["generate_dashboard.py", "generate_skill_usage_dashboard.py"],
    "modernization-advisor": ["check_modernization.py"],
    "py2to3-automated-converter": ["convert.py", "generate_conversion_report.py"],
    "py2to3-behavioral-diff-generator": ["generate_diffs.py", "generate_diff_report.py"],
    "py2to3-build-system-updater": ["update_build.py", "generate_build_report.py"],
    "py2to3-bytes-string-fixer": ["fix_boundaries.py", "generate_boundary_report.py"],
    "py2to3-c-extension-flagger": ["flag_extensions.py", "generate_extension_report.py"],
    "py2to3-canary-deployment-planner": ["plan_canary.py", "generate_canary_report.py"],
    "py2to3-ci-dual-interpreter": ["configure_ci.py", "generate_ci_report.py"],
    "py2to3-codebase-analyzer": ["analyze.py", "build_dep_graph.py", "generate_report.py"],
    "py2to3-compatibility-shim-remover": ["remove_shims.py", "generate_shim_report.py"],
    "py2to3-completeness-checker": ["check_completeness.py", "generate_completeness_report.py"],
    "py2to3-conversion-unit-planner": ["plan_conversion.py", "generate_plan_report.py"],
    "py2to3-custom-lint-rules": ["generate_lint_rules.py", "generate_lint_rules_report.py"],
    "py2to3-data-format-analyzer": ["analyze_data_layer.py", "generate_data_report.py"],
    "py2to3-dead-code-detector": ["detect_dead_code.py", "generate_dead_code_report.py"],
    "py2to3-dynamic-pattern-resolver": ["resolve_patterns.py", "generate_pattern_report.py"],
    "py2to3-encoding-stress-tester": ["stress_test.py", "generate_stress_report.py"],
    "py2to3-future-imports-injector": ["inject_futures.py"],
    "py2to3-gate-checker": ["check_gate.py", "generate_gate_report.py"],
    "py2to3-library-replacement": ["advise_replacements.py", "generate_replacement_report.py"],
    "py2to3-lint-baseline-generator": ["generate_baseline.py", "generate_lint_report.py"],
    "py2to3-migration-state-tracker": ["init_state.py", "update_state.py", "query_state.py"],
    "py2to3-performance-benchmarker": ["benchmark.py", "generate_perf_report.py"],
    "py2to3-project-initializer": ["init_migration_project.py", "quick_size_scan.py"],
    "py2to3-rollback-plan-generator": ["generate_rollback.py", "generate_rollback_report.py"],
    "py2to3-security-scanner": ["security_scan.py"],
    "py2to3-serialization-detector": ["detect_serialization.py", "generate_serialization_report.py"],
    "py2to3-test-scaffold-generator": ["generate_tests.py"],
    "py2to3-type-annotation-adder": ["add_annotations.py", "generate_annotation_report.py"],
    "translation-verifier": ["verify_translation.py"],
    "universal-code-graph": [
        "analyze_universal.py", "language_detect.py", "ts_parser.py",
        "universal_extractor.py", "graph_builder.py",
    ],
    "work-item-generator": ["generate_work_items.py"],
}

# Phase runners (tracked separately from skill scripts)
RUNNER_SCRIPTS = [
    "phase0_discovery.py", "phase1_foundation.py", "phase2_mechanical.py",
    "phase3_semantic.py", "phase4_verification.py", "phase5_cutover.py",
    "run_express.py",
]

# Skills that are expected to be skipped under certain conditions
SKIP_RULES: Dict[str, Dict[str, str]] = {
    "py2to3-canary-deployment-planner": {
        "condition": "sizing_small_or_standard",
        "reason": "Canary deployment not needed for small/standard projects",
    },
    "py2to3-c-extension-flagger": {
        "condition": "no_c_extensions",
        "reason": "No C/C++ extension files detected in project",
    },
    "py2to3-ci-dual-interpreter": {
        "condition": "no_ci_config",
        "reason": "No CI configuration files found",
    },
    "py2to3-encoding-stress-tester": {
        "condition": "sizing_small",
        "reason": "Encoding stress testing skipped for small projects",
    },
    "py2to3-performance-benchmarker": {
        "condition": "sizing_small",
        "reason": "Performance benchmarking skipped for small projects",
    },
    "py2to3-serialization-detector": {
        "condition": "no_serialization",
        "reason": "No pickle/shelve/marshal usage detected",
    },
    "py2to3-data-format-analyzer": {
        "condition": "no_data_files",
        "reason": "No data format files (.csv, .json, .xml) detected in project",
    },
}

# ── Log Parsing ────────────────────────────────────────────────────────────

# Regex for migration-audit.log START lines:
# 2026-02-18T19:22:15 | quick_size_scan | INFO  | START | args=[...] cwd=...
_AUDIT_START_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s*\|\s*(\S+)\s*\|\s*INFO\s*\|\s*START\s*\|\s*args=(\[.*?\])\s+cwd=(.*)"
)
# Regex for migration-audit.log END lines:
# 2026-02-18T19:22:15 | quick_size_scan | INFO  | END   | exit=0 duration=0.0s
_AUDIT_END_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\s*\|\s*(\S+)\s*\|\s*INFO\s*\|\s*END\s*\|\s*exit=(\d+)\s+duration=([\d.]+)s"
)


def parse_audit_log(log_path: Path) -> List[Dict[str, Any]]:
    """Parse migration-audit.log into execution records."""
    if not log_path.exists():
        return []

    # Collect START and END entries, then pair them
    starts: Dict[str, List[Dict]] = {}  # script_name -> [start_entries]
    records = []

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip()
                m_start = _AUDIT_START_RE.match(line)
                if m_start:
                    ts, script, args_str, cwd = m_start.groups()
                    starts.setdefault(script, []).append({
                        "timestamp": ts,
                        "script": script,
                        "args_str": args_str,
                        "cwd": cwd.strip(),
                    })
                    continue

                m_end = _AUDIT_END_RE.match(line)
                if m_end:
                    ts, script, exit_code, duration = m_end.groups()
                    # Pair with most recent unmatched START for this script
                    if script in starts and starts[script]:
                        start = starts[script].pop(0)
                        records.append({
                            "timestamp": start["timestamp"],
                            "script": f"{script}.py" if not script.endswith(".py") else script,
                            "skill": "",  # will be resolved later
                            "args": start["args_str"],
                            "exit_code": int(exit_code),
                            "duration_s": float(duration),
                            "source": "audit_log",
                        })
                    else:
                        # END without matching START — still record it
                        records.append({
                            "timestamp": ts,
                            "script": f"{script}.py" if not script.endswith(".py") else script,
                            "skill": "",
                            "args": "[]",
                            "exit_code": int(exit_code),
                            "duration_s": float(duration),
                            "source": "audit_log",
                        })
    except (OSError, UnicodeDecodeError) as e:
        print(f"Warning: Error reading audit log: {e}", file=sys.stderr)

    return records


def parse_invocations_jsonl(jsonl_path: Path) -> List[Dict[str, Any]]:
    """Parse skill-invocations.jsonl into execution records."""
    if not jsonl_path.exists():
        return []

    records = []
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    records.append({
                        "timestamp": entry.get("timestamp", ""),
                        "script": entry.get("script", ""),
                        "skill": entry.get("skill", ""),
                        "args": json.dumps(entry.get("args", [])),
                        "exit_code": entry.get("exit_code", -1),
                        "duration_s": entry.get("duration_s", 0.0),
                        "stdout_bytes": entry.get("stdout_bytes", 0),
                        "stderr_bytes": entry.get("stderr_bytes", 0),
                        "source": "jsonl",
                    })
                except json.JSONDecodeError:
                    print(f"Warning: Invalid JSON on line {line_num} of {jsonl_path}", file=sys.stderr)
    except (OSError, UnicodeDecodeError) as e:
        print(f"Warning: Error reading JSONL: {e}", file=sys.stderr)

    return records


def build_script_to_skill_map(manifest: Dict[str, List[str]]) -> Dict[str, str]:
    """Build reverse lookup: script_name -> skill_name."""
    mapping = {}
    for skill, scripts in manifest.items():
        for script in scripts:
            mapping[script] = skill
    return mapping


def resolve_skill_names(records: List[Dict[str, Any]], script_to_skill: Dict[str, str]) -> None:
    """Fill in missing skill names from manifest."""
    for rec in records:
        if not rec.get("skill"):
            script = rec["script"]
            rec["skill"] = script_to_skill.get(script, "unknown")


def deduplicate_records(audit_records: List[Dict], jsonl_records: List[Dict]) -> List[Dict]:
    """Merge audit_log and jsonl records, deduplicating overlaps.

    JSONL records are preferred (more structured) when they exist for
    the same script+timestamp window.
    """
    # Index JSONL records by (script, timestamp_prefix)
    jsonl_keys: Set[Tuple[str, str]] = set()
    for rec in jsonl_records:
        ts_prefix = rec["timestamp"][:19]  # e.g. "2026-02-18T19:22:15"
        jsonl_keys.add((rec["script"], ts_prefix))

    merged = list(jsonl_records)
    for rec in audit_records:
        ts_prefix = rec["timestamp"][:19]
        key = (rec["script"], ts_prefix)
        if key not in jsonl_keys:
            merged.append(rec)

    merged.sort(key=lambda r: r.get("timestamp", ""))
    return merged


# ── Inventory Discovery ────────────────────────────────────────────────────

def discover_skill_inventory(skills_root: Optional[Path]) -> Dict[str, List[str]]:
    """Walk filesystem to discover skills, fall back to hardcoded manifest."""
    if not skills_root or not skills_root.is_dir():
        return dict(SKILL_MANIFEST)

    discovered: Dict[str, List[str]] = {}
    skills_dir = skills_root / "skills"
    if not skills_dir.is_dir():
        return dict(SKILL_MANIFEST)

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        scripts_dir = skill_dir / "scripts"
        if not scripts_dir.is_dir():
            continue
        scripts = sorted(f.name for f in scripts_dir.glob("*.py"))
        if scripts:
            discovered[skill_dir.name] = scripts

    return discovered if discovered else dict(SKILL_MANIFEST)


# ── Analysis ───────────────────────────────────────────────────────────────

def load_project_context(analysis_dir: Path) -> Dict[str, Any]:
    """Load migration state for project context (sizing, workflow, etc.)."""
    state_path = analysis_dir / "state" / "migration-state.json"
    if not state_path.exists():
        # Try alternate location
        state_path = analysis_dir / "migration-state.json"
    if not state_path.exists():
        return {}
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def determine_project_characteristics(state: Dict[str, Any], analysis_dir: Path) -> Dict[str, bool]:
    """Determine project characteristics for skip analysis."""
    chars: Dict[str, bool] = {
        "sizing_small": False,
        "sizing_small_or_standard": False,
        "no_c_extensions": True,
        "no_ci_config": True,
        "no_serialization": True,
        "no_data_files": True,
    }

    # Check sizing from state
    sizing = state.get("sizing", {})
    if isinstance(sizing, str):
        chars["sizing_small"] = sizing == "small"
        chars["sizing_small_or_standard"] = sizing in ("small", "medium")
    elif isinstance(sizing, dict):
        tier = sizing.get("base_tier", sizing.get("effective_tier", ""))
        chars["sizing_small"] = tier == "small"
        chars["sizing_small_or_standard"] = tier in ("small", "medium")

    workflow = state.get("workflow", "")
    if workflow == "standard":
        chars["sizing_small_or_standard"] = True

    # Check for sizing report
    for phase_dir in ["phase-0-discovery", "."]:
        sizing_path = analysis_dir / phase_dir / "sizing-report.json"
        if sizing_path.exists():
            try:
                with open(sizing_path, "r") as f:
                    sizing_data = json.load(f)
                tier = sizing_data.get("sizing", {}).get("base_tier", "")
                chars["sizing_small"] = tier == "small"
                chars["sizing_small_or_standard"] = tier in ("small", "medium")
            except (json.JSONDecodeError, OSError):
                pass
            break

    # Check for C extensions in scan results
    scan_path = analysis_dir / "phase-0-discovery" / "raw-scan.json"
    if scan_path.exists():
        try:
            with open(scan_path, "r") as f:
                scan = json.load(f)
            files = scan.get("files", {})
            if isinstance(files, dict):
                for fname in files:
                    if fname.endswith((".c", ".cpp", ".pyx", ".so", ".pyd")):
                        chars["no_c_extensions"] = False
                        break
        except (json.JSONDecodeError, OSError):
            pass

    return chars


def categorize_skills(
    manifest: Dict[str, List[str]],
    executed_scripts: Set[str],
    project_chars: Dict[str, bool],
) -> List[Dict[str, Any]]:
    """Categorize each skill as complete, partial, expected_skip, or gap."""
    results = []
    for skill_name, scripts in sorted(manifest.items()):
        ran = [s for s in scripts if s in executed_scripts]
        not_ran = [s for s in scripts if s not in executed_scripts]

        if len(ran) == len(scripts):
            status = "complete"
            reason = ""
        elif ran:
            status = "partial"
            reason = f"{len(not_ran)} of {len(scripts)} scripts not executed"
        else:
            # Nothing ran — check skip rules
            rule = SKIP_RULES.get(skill_name)
            if rule and project_chars.get(rule["condition"], False):
                status = "expected_skip"
                reason = rule["reason"]
            else:
                status = "gap"
                reason = "No execution evidence found"

        results.append({
            "skill": skill_name,
            "scripts": scripts,
            "scripts_ran": ran,
            "scripts_skipped": not_ran,
            "status": status,
            "reason": reason,
        })

    return results


def compute_metrics(
    records: List[Dict],
    skill_categories: List[Dict],
    manifest: Dict[str, List[str]],
) -> Dict[str, Any]:
    """Compute summary metrics from execution records."""
    total_scripts = sum(len(s) for s in manifest.values())
    executed_scripts = set(r["script"] for r in records)
    skill_scripts_executed = executed_scripts & set(
        s for scripts in manifest.values() for s in scripts
    )

    skills_used = set()
    for cat in skill_categories:
        if cat["status"] in ("complete", "partial"):
            skills_used.add(cat["skill"])

    total_duration = sum(r.get("duration_s", 0) for r in records)
    failures = [r for r in records if r.get("exit_code", 0) != 0]

    # Execution count per script
    script_counts: Dict[str, int] = {}
    for r in records:
        script_counts[r["script"]] = script_counts.get(r["script"], 0) + 1

    # Slowest scripts
    script_durations: Dict[str, float] = {}
    for r in records:
        s = r["script"]
        script_durations[s] = script_durations.get(s, 0) + r.get("duration_s", 0)

    slowest = sorted(script_durations.items(), key=lambda x: x[1], reverse=True)[:20]

    return {
        "total_scripts_in_manifest": total_scripts,
        "total_skills": len(manifest),
        "scripts_executed": len(skill_scripts_executed),
        "skills_used": len(skills_used),
        "total_invocations": len(records),
        "total_duration_s": round(total_duration, 1),
        "failure_count": len(failures),
        "script_coverage_pct": round(
            (len(skill_scripts_executed) / total_scripts * 100) if total_scripts else 0, 1
        ),
        "skill_coverage_pct": round(
            (len(skills_used) / len(manifest) * 100) if manifest else 0, 1
        ),
        "slowest_scripts": slowest,
        "script_counts": script_counts,
    }


# ── HTML Generation ────────────────────────────────────────────────────────

def generate_html(
    metrics: Dict[str, Any],
    skill_categories: List[Dict[str, Any]],
    records: List[Dict[str, Any]],
    project_name: str,
    data_quality: Dict[str, int],
) -> str:
    """Generate self-contained HTML dashboard."""

    # Prepare data for embedding
    records_json = json.dumps(records, default=str)
    skills_json = json.dumps(skill_categories, default=str)
    metrics_json = json.dumps(metrics, default=str)

    # Format duration
    total_s = metrics["total_duration_s"]
    hours = int(total_s // 3600)
    minutes = int((total_s % 3600) // 60)
    seconds = int(total_s % 60)
    if hours:
        duration_str = f"{hours}h {minutes}m {seconds}s"
    elif minutes:
        duration_str = f"{minutes}m {seconds}s"
    else:
        duration_str = f"{seconds}s"

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skill Usage Dashboard — {_esc(project_name)}</title>
<style>
  :root {{
    --bg-primary: #0f172a;
    --bg-card: #1e293b;
    --bg-table-row: #334155;
    --text-primary: #f1f5f9;
    --text-secondary: #94a3b8;
    --text-muted: #64748b;
    --border: #475569;
    --green: #22c55e;
    --red: #dc2626;
    --orange: #f97316;
    --yellow: #eab308;
    --blue: #3b82f6;
    --purple: #a855f7;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg-primary);
    color: var(--text-primary);
    padding: 24px;
    line-height: 1.6;
  }}
  .header {{
    text-align: center;
    margin-bottom: 32px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--border);
  }}
  .header h1 {{ font-size: 1.8rem; margin-bottom: 4px; }}
  .header .subtitle {{ color: var(--text-secondary); font-size: 0.9rem; }}
  .cards {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 16px;
    margin-bottom: 32px;
  }}
  .card {{
    background: var(--bg-card);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    border: 1px solid var(--border);
  }}
  .card .value {{
    font-size: 2rem;
    font-weight: 700;
    line-height: 1.2;
  }}
  .card .label {{
    color: var(--text-secondary);
    font-size: 0.85rem;
    margin-top: 4px;
  }}
  .card .sub {{ color: var(--text-muted); font-size: 0.8rem; }}
  .section {{
    background: var(--bg-card);
    border-radius: 12px;
    padding: 24px;
    margin-bottom: 24px;
    border: 1px solid var(--border);
  }}
  .section h2 {{
    font-size: 1.2rem;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
  }}
  th, td {{
    padding: 10px 12px;
    text-align: left;
    border-bottom: 1px solid var(--border);
  }}
  th {{
    color: var(--text-secondary);
    font-weight: 600;
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    cursor: pointer;
    user-select: none;
  }}
  th:hover {{ color: var(--text-primary); }}
  tr:hover td {{ background: rgba(255,255,255,0.03); }}
  .badge {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
  }}
  .badge-complete {{ background: rgba(34,197,94,0.15); color: var(--green); }}
  .badge-partial {{ background: rgba(234,179,8,0.15); color: var(--yellow); }}
  .badge-gap {{ background: rgba(220,38,38,0.15); color: var(--red); }}
  .badge-skip {{ background: rgba(148,163,184,0.15); color: var(--text-secondary); }}
  .badge-fail {{ background: rgba(220,38,38,0.15); color: var(--red); }}
  .badge-ok {{ background: rgba(34,197,94,0.15); color: var(--green); }}
  .filter-bar {{
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
    flex-wrap: wrap;
  }}
  .filter-btn {{
    padding: 6px 14px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    font-size: 0.82rem;
    transition: all 0.15s;
  }}
  .filter-btn:hover {{ border-color: var(--text-primary); color: var(--text-primary); }}
  .filter-btn.active {{
    background: var(--blue);
    color: white;
    border-color: var(--blue);
  }}
  .chart-container {{
    position: relative;
    width: 100%;
    height: 320px;
    margin-top: 12px;
  }}
  canvas {{ width: 100% !important; }}
  .skip-table td:last-child {{ color: var(--text-secondary); font-style: italic; }}
  .data-quality {{
    color: var(--text-muted);
    font-size: 0.8rem;
    text-align: center;
    margin-top: 16px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
  }}
  .args-cell {{
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-family: monospace;
    font-size: 0.8rem;
    color: var(--text-muted);
  }}
  .progress-bar-bg {{
    width: 100%;
    height: 8px;
    background: rgba(255,255,255,0.1);
    border-radius: 4px;
    overflow: hidden;
    margin-top: 6px;
  }}
  .progress-bar-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s; }}
</style>
</head>
<body>

<div class="header">
  <h1>Skill Usage Dashboard</h1>
  <div class="subtitle">{_esc(project_name)} &mdash; Generated {now}</div>
</div>

<!-- Summary Cards -->
<div class="cards">
  <div class="card">
    <div class="value" style="color: var(--blue);">{metrics['scripts_executed']} / {metrics['total_scripts_in_manifest']}</div>
    <div class="label">Scripts Executed</div>
    <div class="sub">{metrics['script_coverage_pct']}% coverage</div>
    <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{metrics['script_coverage_pct']}%;background:var(--blue);"></div></div>
  </div>
  <div class="card">
    <div class="value" style="color: var(--green);">{metrics['skills_used']} / {metrics['total_skills']}</div>
    <div class="label">Skills Used</div>
    <div class="sub">{metrics['skill_coverage_pct']}% coverage</div>
    <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{metrics['skill_coverage_pct']}%;background:var(--green);"></div></div>
  </div>
  <div class="card">
    <div class="value" style="color: {'var(--red)' if metrics['failure_count'] else 'var(--green)'};">{metrics['failure_count']}</div>
    <div class="label">Failures</div>
    <div class="sub">exit code &ne; 0</div>
  </div>
  <div class="card">
    <div class="value" style="color: var(--purple);">{metrics['total_invocations']}</div>
    <div class="label">Total Invocations</div>
    <div class="sub">{duration_str} total runtime</div>
  </div>
</div>

<!-- Skill Coverage Table -->
<div class="section">
  <h2>Skill Coverage</h2>
  <div class="filter-bar">
    <button class="filter-btn active" onclick="filterSkills('all')">All ({len(skill_categories)})</button>
    <button class="filter-btn" onclick="filterSkills('complete')">Complete ({sum(1 for s in skill_categories if s['status']=='complete')})</button>
    <button class="filter-btn" onclick="filterSkills('partial')">Partial ({sum(1 for s in skill_categories if s['status']=='partial')})</button>
    <button class="filter-btn" onclick="filterSkills('expected_skip')">Expected Skip ({sum(1 for s in skill_categories if s['status']=='expected_skip')})</button>
    <button class="filter-btn" onclick="filterSkills('gap')">Potential Gap ({sum(1 for s in skill_categories if s['status']=='gap')})</button>
  </div>
  <table id="skillTable">
    <thead>
      <tr>
        <th onclick="sortTable('skillTable',0)">Skill</th>
        <th onclick="sortTable('skillTable',1)">Scripts</th>
        <th onclick="sortTable('skillTable',2)">Status</th>
        <th onclick="sortTable('skillTable',3)">Reason / Notes</th>
      </tr>
    </thead>
    <tbody>
"""

    for cat in skill_categories:
        status_badge = {
            "complete": '<span class="badge badge-complete">Complete</span>',
            "partial": '<span class="badge badge-partial">Partial</span>',
            "expected_skip": '<span class="badge badge-skip">Expected Skip</span>',
            "gap": '<span class="badge badge-gap">Potential Gap</span>',
        }.get(cat["status"], cat["status"])

        ran_list = ", ".join(cat["scripts_ran"]) if cat["scripts_ran"] else "—"
        skipped_list = ", ".join(cat["scripts_skipped"]) if cat["scripts_skipped"] else ""
        scripts_info = f'{len(cat["scripts_ran"])}/{len(cat["scripts"])}'

        html += f"""      <tr data-status="{cat['status']}">
        <td><strong>{_esc(cat['skill'])}</strong></td>
        <td>{scripts_info}</td>
        <td>{status_badge}</td>
        <td>{_esc(cat['reason']) if cat['reason'] else _esc(ran_list)}</td>
      </tr>
"""

    html += """    </tbody>
  </table>
</div>

<!-- Execution Time Chart -->
<div class="section">
  <h2>Execution Time — Top Scripts</h2>
  <div class="chart-container">
    <canvas id="timeChart"></canvas>
  </div>
</div>

<!-- Error Summary -->
<div class="section">
  <h2>Failures &amp; Errors</h2>
"""
    failures = [r for r in records if r.get("exit_code", 0) != 0]
    if failures:
        html += """  <table>
    <thead>
      <tr><th>Script</th><th>Skill</th><th>Exit Code</th><th>Duration</th><th>Timestamp</th></tr>
    </thead>
    <tbody>
"""
        for f in failures:
            html += f"""      <tr>
        <td>{_esc(f['script'])}</td>
        <td>{_esc(f.get('skill',''))}</td>
        <td><span class="badge badge-fail">exit {f['exit_code']}</span></td>
        <td>{f.get('duration_s',0):.1f}s</td>
        <td style="color:var(--text-muted)">{_esc(f.get('timestamp',''))}</td>
      </tr>
"""
        html += "    </tbody>\n  </table>\n"
    else:
        html += '  <p style="color:var(--green);">No failures recorded.</p>\n'

    html += "</div>\n"

    # All Invocations table
    html += """
<!-- All Invocations -->
<div class="section">
  <h2>All Invocations</h2>
  <table id="invocTable">
    <thead>
      <tr>
        <th onclick="sortTable('invocTable',0)">Timestamp</th>
        <th onclick="sortTable('invocTable',1)">Script</th>
        <th onclick="sortTable('invocTable',2)">Skill</th>
        <th onclick="sortTable('invocTable',3)">Exit</th>
        <th onclick="sortTable('invocTable',4)">Duration</th>
        <th>Args</th>
        <th>Source</th>
      </tr>
    </thead>
    <tbody>
"""
    for r in records:
        exit_badge = (
            '<span class="badge badge-ok">0</span>'
            if r.get("exit_code", 0) == 0
            else f'<span class="badge badge-fail">{r["exit_code"]}</span>'
        )
        html += f"""      <tr>
        <td style="color:var(--text-muted);font-size:0.82rem">{_esc(r.get('timestamp','')[:19])}</td>
        <td>{_esc(r['script'])}</td>
        <td style="color:var(--text-secondary)">{_esc(r.get('skill',''))}</td>
        <td>{exit_badge}</td>
        <td>{r.get('duration_s',0):.1f}s</td>
        <td class="args-cell" title="{_esc(r.get('args',''))}">{_esc(str(r.get('args',''))[:60])}</td>
        <td style="color:var(--text-muted);font-size:0.78rem">{r.get('source','')}</td>
      </tr>
"""

    html += "    </tbody>\n  </table>\n</div>\n"

    # Data quality footer
    html += f"""
<div class="data-quality">
  Parsed {data_quality.get('audit_entries', 0)} entries from migration-audit.log &middot;
  {data_quality.get('jsonl_entries', 0)} entries from skill-invocations.jsonl &middot;
  {data_quality.get('dedup_removed', 0)} duplicates removed &middot;
  {data_quality.get('total_records', 0)} total records
</div>

<!-- Embedded Data -->
<script type="application/json" id="metricsData">{metrics_json}</script>
<script type="application/json" id="skillsData">{skills_json}</script>

<script>
// ── Skill table filter ──
function filterSkills(status) {{
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  event.target.classList.add('active');
  document.querySelectorAll('#skillTable tbody tr').forEach(tr => {{
    if (status === 'all' || tr.dataset.status === status) {{
      tr.style.display = '';
    }} else {{
      tr.style.display = 'none';
    }}
  }});
}}

// ── Table sorting ──
const sortState = {{}};
function sortTable(tableId, colIdx) {{
  const table = document.getElementById(tableId);
  const tbody = table.querySelector('tbody');
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const key = tableId + colIdx;
  sortState[key] = !sortState[key];
  const dir = sortState[key] ? 1 : -1;
  rows.sort((a, b) => {{
    const aText = a.cells[colIdx]?.textContent?.trim() || '';
    const bText = b.cells[colIdx]?.textContent?.trim() || '';
    const aNum = parseFloat(aText);
    const bNum = parseFloat(bText);
    if (!isNaN(aNum) && !isNaN(bNum)) return (aNum - bNum) * dir;
    return aText.localeCompare(bText) * dir;
  }});
  rows.forEach(r => tbody.appendChild(r));
}}

// ── Execution time chart ──
(function() {{
  const metrics = JSON.parse(document.getElementById('metricsData').textContent);
  const canvas = document.getElementById('timeChart');
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.parentElement.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = 320 * dpr;
  canvas.style.height = '320px';
  ctx.scale(dpr, dpr);
  const W = rect.width, H = 320;

  const data = metrics.slowest_scripts || [];
  if (data.length === 0) {{
    ctx.fillStyle = '#94a3b8';
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('No execution data', W/2, H/2);
    return;
  }}

  const maxVal = Math.max(...data.map(d => d[1]));
  const barH = Math.min(24, (H - 40) / data.length - 4);
  const leftPad = 220;
  const rightPad = 60;
  const barArea = W - leftPad - rightPad;

  data.forEach((item, i) => {{
    const y = 20 + i * (barH + 4);
    const barW = maxVal > 0 ? (item[1] / maxVal) * barArea : 0;

    // Label
    ctx.fillStyle = '#e2e8f0';
    ctx.font = '12px monospace';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    const label = item[0].length > 30 ? item[0].slice(0, 27) + '...' : item[0];
    ctx.fillText(label, leftPad - 8, y + barH / 2);

    // Bar
    const grad = ctx.createLinearGradient(leftPad, 0, leftPad + barW, 0);
    grad.addColorStop(0, '#3b82f6');
    grad.addColorStop(1, '#a855f7');
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.roundRect(leftPad, y, barW, barH, 4);
    ctx.fill();

    // Value
    ctx.fillStyle = '#94a3b8';
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(item[1].toFixed(1) + 's', leftPad + barW + 6, y + barH / 2);
  }});
}})();
</script>
</body>
</html>"""

    return html


def _esc(s: str) -> str:
    """HTML-escape a string."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ── Main ───────────────────────────────────────────────────────────────────

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate a skill usage dashboard from migration logs."
    )
    parser.add_argument(
        "analysis_dir",
        help="Path to migration-analysis/ directory",
    )
    parser.add_argument(
        "--output", "-o",
        default=None,
        help="Output HTML path (default: <analysis_dir>/skill-usage-dashboard.html)",
    )
    parser.add_argument(
        "--skills-root",
        default=None,
        help="Path to skills repo root for dynamic inventory (default: auto-detect)",
    )
    parser.add_argument(
        "--project-name",
        default="Migration Project",
        help="Project name for dashboard title",
    )
    args = parser.parse_args()

    analysis_dir = Path(args.analysis_dir).resolve()
    if not analysis_dir.is_dir():
        print(f"Error: analysis directory not found: {analysis_dir}", file=sys.stderr)
        return 1

    # Resolve skills root
    skills_root = None
    if args.skills_root:
        skills_root = Path(args.skills_root).resolve()
    else:
        # Auto-detect: walk up from this script to find 'skills/' dir
        candidate = Path(__file__).resolve().parents[3]
        if (candidate / "skills").is_dir():
            skills_root = candidate

    # Build inventory
    manifest = discover_skill_inventory(skills_root)
    script_to_skill = build_script_to_skill_map(manifest)

    # Parse logs
    audit_log = analysis_dir / "logs" / "migration-audit.log"
    jsonl_log = analysis_dir / "logs" / "skill-invocations.jsonl"

    audit_records = parse_audit_log(audit_log)
    jsonl_records = parse_invocations_jsonl(jsonl_log)

    # Resolve skill names and merge
    resolve_skill_names(audit_records, script_to_skill)
    resolve_skill_names(jsonl_records, script_to_skill)
    records = deduplicate_records(audit_records, jsonl_records)

    data_quality = {
        "audit_entries": len(audit_records),
        "jsonl_entries": len(jsonl_records),
        "dedup_removed": len(audit_records) + len(jsonl_records) - len(records),
        "total_records": len(records),
    }

    # Analyze
    state = load_project_context(analysis_dir)
    project_chars = determine_project_characteristics(state, analysis_dir)
    executed_scripts = set(r["script"] for r in records)
    skill_categories = categorize_skills(manifest, executed_scripts, project_chars)
    metrics = compute_metrics(records, skill_categories, manifest)

    # Extract project name from state if available
    project_name = args.project_name
    if state.get("project_name"):
        project_name = state["project_name"]

    # Generate HTML
    html = generate_html(metrics, skill_categories, records, project_name, data_quality)

    # Write output
    output_path = Path(args.output) if args.output else analysis_dir / "skill-usage-dashboard.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Summary to stdout (JSON)
    summary = {
        "status": "complete",
        "output": str(output_path),
        "metrics": {
            "scripts_executed": metrics["scripts_executed"],
            "total_scripts": metrics["total_scripts_in_manifest"],
            "skills_used": metrics["skills_used"],
            "total_skills": metrics["total_skills"],
            "failures": metrics["failure_count"],
            "total_duration_s": metrics["total_duration_s"],
        },
        "categories": {
            "complete": sum(1 for s in skill_categories if s["status"] == "complete"),
            "partial": sum(1 for s in skill_categories if s["status"] == "partial"),
            "expected_skip": sum(1 for s in skill_categories if s["status"] == "expected_skip"),
            "gap": sum(1 for s in skill_categories if s["status"] == "gap"),
        },
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
