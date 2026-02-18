#!/usr/bin/env python3
"""
Migration Report Generator

Takes the outputs from analyze.py and build_dep_graph.py and produces a
human-readable migration readiness report in Markdown.

Usage:
    python3 generate_report.py <analysis_dir> \
        --project-name "My Project" \
        --output <output_dir>/migration-report.md

Inputs (from <analysis_dir>):
    raw-scan.json
    dependency-graph.json
    migration-order.json
    version-matrix.md
    py2-ism-inventory.json
"""

import json
import os
import sys
import argparse
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


def load_json(path: str) -> Dict:
    """Load a JSON file, return empty dict if not found."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Warning: {path} not found", file=sys.stderr)
        return {}


def format_number(n: int) -> str:
    """Format a number with comma separators."""
    return f"{n:,}"


def generate_report(
    raw_scan: Dict,
    dep_graph: Dict,
    migration_order: Dict,
    inventory: Dict,
    project_name: str,
) -> str:
    """Generate the full migration readiness report."""

    summary = raw_scan.get("summary", {})
    special = dep_graph.get("special_modules", {})
    nodes = dep_graph.get("nodes", {})

    lines = []

    def w(text=""):
        lines.append(text)

    # ── Header ───────────────────────────────────────────────────────────

    w(f"# Migration Readiness Report: {project_name}")
    w()
    w(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    w()

    # ── Executive Summary ────────────────────────────────────────────────

    w("## Executive Summary")
    w()
    w(f"| Metric | Value |")
    w(f"|--------|-------|")
    w(f"| Total Python files | {format_number(summary.get('total_files', 0))} |")
    w(f"| Total lines of code | {format_number(summary.get('total_lines', 0))} |")
    w(f"| Functions | {format_number(summary.get('total_functions', 0))} |")
    w(f"| Classes | {format_number(summary.get('total_classes', 0))} |")
    w(f"| Estimated migration effort | **{summary.get('effort_estimate', 'unknown')}** |")
    w(f"| Files with `__future__` imports | {summary.get('files_with_future_imports', 0)} |")
    w(f"| Parse failures (Py2-only syntax) | {summary.get('parse_failures', 0)} |")
    w()

    total_findings = summary.get("total_findings", 0)
    syntax_count = summary.get("syntax_only_count", 0)
    semantic_count = summary.get("semantic_count", 0)
    data_layer_count = summary.get("data_layer_count", 0)

    w(f"**Total Python 2 patterns found: {format_number(total_findings)}**")
    w()
    w(f"- Syntax-only (automatable): {format_number(syntax_count)}")
    w(f"- Semantic (manual review needed): {format_number(semantic_count)}")
    w(f"- Data layer (highest risk): {format_number(data_layer_count)}")
    w()

    # Effort context
    if summary.get("effort_estimate") == "very large":
        w("> **This is a major migration project.** The combination of codebase size, "
          "semantic complexity, and data layer risk means this will require careful "
          "phasing, dedicated resources, and thorough testing. Plan for months, not weeks.")
    elif summary.get("effort_estimate") == "large":
        w("> **This is a significant migration effort.** Phased execution with proper "
          "gating is recommended. Plan for several weeks of focused work.")
    w()

    # ── Dependency Analysis ──────────────────────────────────────────────

    w("## Dependency Analysis")
    w()
    w(f"| Metric | Value |")
    w(f"|--------|-------|")
    w(f"| Total modules | {dep_graph.get('module_count', 0)} |")
    w(f"| Import relationships | {dep_graph.get('edge_count', 0)} |")
    w(f"| Tightly-coupled clusters | {dep_graph.get('cluster_count', 0)} |")
    w(f"| Conversion units | {migration_order.get('total_conversion_units', 0)} |")
    w(f"| Leaf modules (convert first) | {len(special.get('leaves', []))} |")
    w(f"| Gateway modules (high impact) | {len(special.get('gateways', []))} |")
    w(f"| Orphan modules (possibly dead) | {len(special.get('orphans', []))} |")
    order_summary = migration_order.get("summary", {})
    w(f"| Max dependency depth | {order_summary.get('max_depth', 0)} |")
    w()

    # Gateway modules
    gateways = special.get("gateways", [])
    if gateways:
        w("### Gateway Modules")
        w()
        w("These modules have the most dependents. Changes to them affect the most code. "
          "Convert them carefully and test thoroughly.")
        w()
        w("| Module | Dependents | Risk Rating |")
        w("|--------|-----------|-------------|")
        for gw in gateways[:10]:
            mod = gw["module"]
            node_info = nodes.get(mod, {})
            rating = node_info.get("risk_rating", "unknown")
            w(f"| `{mod}` | {gw['fan_in']} | {rating} |")
        w()

    # Clusters
    clusters = dep_graph.get("clusters", [])
    if clusters:
        w("### Module Clusters")
        w()
        w("These groups of modules import each other and must be converted together "
          "as a single unit.")
        w()
        for i, cluster in enumerate(clusters):
            w(f"**Cluster {i+1}** ({len(cluster)} modules):")
            for mod in cluster:
                w(f"- `{mod}`")
            w()

    # ── Pattern Inventory ────────────────────────────────────────────────

    w("## Python 2 Pattern Inventory")
    w()

    by_category = summary.get("findings_by_category", {})
    if by_category:
        w("### By Category")
        w()
        w("| Category | Count | Description |")
        w("|----------|-------|-------------|")
        category_descriptions = {
            "syntax": "Mechanical syntax changes (automatable)",
            "semantic_string": "String/bytes semantic changes (high risk)",
            "semantic_iterator": "Iterator/view return type changes",
            "semantic_import": "Import path and module name changes",
            "semantic_comparison": "Comparison and ordering changes",
            "semantic_numeric": "Division and numeric type changes",
            "semantic_class": "Class definition and metaclass changes",
            "semantic_other": "Other semantic changes",
            "data_layer": "Binary data, serialization, encoding (highest risk)",
            "info": "Informational (positive signals like __future__ imports)",
        }
        for cat, count in sorted(by_category.items(), key=lambda x: -x[1]):
            desc = category_descriptions.get(cat, cat)
            w(f"| {cat} | {format_number(count)} | {desc} |")
        w()

    by_pattern = summary.get("findings_by_pattern", {})
    if by_pattern:
        w("### Top 20 Patterns")
        w()
        w("| Pattern | Count | Risk |")
        w("|---------|-------|------|")
        for pattern, count in list(by_pattern.items())[:20]:
            # Look up risk from pattern definitions (imported from analyze.py logic)
            risk = "—"
            w(f"| {pattern} | {format_number(count)} | {risk} |")
        w()

    # ── Risk Assessment ──────────────────────────────────────────────────

    w("## Risk Assessment")
    w()

    # Top 10 highest-risk modules
    risk_sorted = sorted(
        nodes.items(),
        key=lambda x: -x[1].get("risk_score", 0)
    )

    if risk_sorted:
        w("### Highest-Risk Modules")
        w()
        w("| Module | Risk Score | Rating | Issues | Data Layer | Lines |")
        w("|--------|-----------|--------|--------|------------|-------|")
        for mod, info in risk_sorted[:15]:
            score = info.get("risk_score", 0)
            rating = info.get("risk_rating", "unknown")
            # Count issues from raw scan
            file_result = next(
                (r for r in raw_scan.get("results", []) if r["file"] == info.get("file")),
                {}
            )
            total_issues = len(file_result.get("findings", []))
            data_issues = sum(
                1 for f in file_result.get("findings", [])
                if f.get("category") == "data_layer"
            )
            loc = info.get("lines", 0)
            w(f"| `{mod}` | {score} | **{rating}** | {total_issues} | {data_issues} | {format_number(loc)} |")
        w()

    # Risk distribution
    risk_dist = defaultdict(int)
    for mod, info in nodes.items():
        risk_dist[info.get("risk_rating", "unknown")] += 1
    
    if risk_dist:
        w("### Risk Distribution")
        w()
        w("| Rating | Module Count |")
        w("|--------|-------------|")
        for rating in ["critical", "high", "medium", "low", "unknown"]:
            if rating in risk_dist:
                w(f"| {rating} | {risk_dist[rating]} |")
        w()

    # ── Migration Order Preview ──────────────────────────────────────────

    w("## Migration Order Preview")
    w()
    w("The recommended conversion order, based on dependency analysis "
      "(leaf dependencies first, tightly-coupled clusters together):")
    w()

    order = migration_order.get("migration_order", [])
    if order:
        # Show first 20 and last 5
        show_count = min(20, len(order))
        w("### First Conversion Units (start here)")
        w()
        w("| Order | Type | Module(s) | Depth |")
        w("|-------|------|-----------|-------|")
        for unit in order[:show_count]:
            modules = ", ".join(f"`{m}`" for m in unit.get("modules", []))
            utype = unit.get("type", "module")
            depth = unit.get("depth", 0)
            w(f"| {unit['order']} | {utype} | {modules} | {depth} |")
        
        if len(order) > show_count:
            w(f"| ... | ... | *{len(order) - show_count} more units* | ... |")
        w()

    # ── Recommendations ──────────────────────────────────────────────────

    w("## Recommended Next Steps")
    w()
    w("Based on this analysis:")
    w()
    
    steps = []
    
    if data_layer_count > 0:
        steps.append(
            f"1. **Run the Data Format Analyzer** (Skill 0.2) — this codebase has "
            f"{data_layer_count} data layer findings that need deep analysis before "
            f"any conversion begins"
        )
    
    future_pct = (
        summary.get("files_with_future_imports", 0) / max(summary.get("total_files", 1), 1)
    ) * 100
    if future_pct < 50:
        steps.append(
            f"2. **Add `__future__` imports** (Skill 1.1) — only "
            f"{future_pct:.0f}% of files have them. This will surface issues early."
        )
    
    if summary.get("parse_failures", 0) > 0:
        steps.append(
            f"3. **Address parse failures first** — {summary['parse_failures']} files "
            f"have Python 2-only syntax that couldn't be fully analyzed. These need "
            f"the Automated Converter (Skill 2.2) to handle basic syntax fixes."
        )
    
    if gateways:
        steps.append(
            f"4. **Prioritize gateway module testing** — the top gateway module "
            f"(`{gateways[0]['module']}`) has {gateways[0]['fan_in']} dependents. "
            f"Build thorough test coverage here before converting anything."
        )
    
    steps.append(
        f"5. **Run the Lint Baseline Generator** (Skill 0.5) to establish the "
        f"starting point for tracking migration progress."
    )
    
    for step in steps:
        w(step)
    w()

    # ── Footer ───────────────────────────────────────────────────────────

    w("---")
    w()
    w("*This report was generated by the Codebase Analyzer (Skill 0.1) of the "
      "Python 2→3 Migration Skill Suite. See PLAN.md for the full migration methodology.*")

    return "\n".join(lines)


@log_execution
def main():
    parser = argparse.ArgumentParser(description="Generate migration readiness report")
    parser.add_argument("analysis_dir", help="Directory containing analysis outputs")
    parser.add_argument("--project-name", default="Python 2 Codebase", help="Project name for report header")
    parser.add_argument("--output", "-o", help="Output file path (default: <analysis_dir>/migration-report.md)")
    args = parser.parse_args()

    analysis_dir = os.path.abspath(args.analysis_dir)
    output_path = args.output or os.path.join(analysis_dir, "migration-report.md")

    raw_scan = load_json(os.path.join(analysis_dir, "raw-scan.json"))
    dep_graph = load_json(os.path.join(analysis_dir, "dependency-graph.json"))
    migration_order = load_json(os.path.join(analysis_dir, "migration-order.json"))
    inventory = load_json(os.path.join(analysis_dir, "py2-ism-inventory.json"))

    if not raw_scan:
        print("Error: raw-scan.json is required. Run analyze.py first.", file=sys.stderr)
        sys.exit(1)

    report = generate_report(raw_scan, dep_graph, migration_order, inventory, args.project_name)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report)
    print(f"Wrote migration report to {output_path}")


if __name__ == "__main__":
    main()
