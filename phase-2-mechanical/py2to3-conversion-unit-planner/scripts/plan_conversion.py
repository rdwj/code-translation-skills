#!/usr/bin/env python3
"""
Conversion Unit Planner — Main Planning Script

Takes the dependency graph and migration order from Phase 0 and produces
a comprehensive conversion plan: units, waves, risk scores, critical path,
and effort estimates.

Produces:
  - conversion-plan.json — ordered conversion plan
  - critical-path.json   — longest dependency chain

Usage:
    python3 plan_conversion.py \
        --dep-graph <analysis_dir>/dependency-graph.json \
        --migration-order <analysis_dir>/migration-order.json \
        --output <output_dir> \
        --target-version 3.12 \
        [--state-file <analysis_dir>/migration-state.json] \
        [--max-unit-size 10] \
        [--parallelism 3]
"""

import argparse
import json
import os
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# Graph Operations
# ═══════════════════════════════════════════════════════════════════════════

def build_adjacency(dep_graph: Dict[str, Any]) -> Tuple[Dict[str, Set[str]], Dict[str, Set[str]]]:
    """Build forward and reverse adjacency lists from the dependency graph.

    Returns (imports_of, imported_by) where:
      imports_of[A] = {B, C}  means A imports B and C
      imported_by[A] = {D}    means D imports A
    """
    imports_of: Dict[str, Set[str]] = defaultdict(set)
    imported_by: Dict[str, Set[str]] = defaultdict(set)

    nodes = set()
    for node in dep_graph.get("nodes", []):
        name = node if isinstance(node, str) else node.get("id", node.get("path", ""))
        nodes.add(name)

    for edge in dep_graph.get("edges", []):
        source = edge.get("source", edge.get("from", ""))
        target = edge.get("target", edge.get("to", ""))
        if source and target:
            imports_of[source].add(target)
            imported_by[target].add(source)
            nodes.add(source)
            nodes.add(target)

    # Ensure all nodes appear in both dicts
    for n in nodes:
        imports_of.setdefault(n, set())
        imported_by.setdefault(n, set())

    return imports_of, imported_by


def find_sccs(imports_of: Dict[str, Set[str]]) -> List[List[str]]:
    """Find strongly connected components using Tarjan's algorithm.

    Returns a list of SCCs, each being a list of module paths.
    Single-module components are included.
    """
    index_counter = [0]
    stack: List[str] = []
    lowlink: Dict[str, int] = {}
    index: Dict[str, int] = {}
    on_stack: Dict[str, bool] = {}
    sccs: List[List[str]] = []

    def strongconnect(v: str) -> None:
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True

        for w in imports_of.get(v, set()):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])

        if lowlink[v] == index[v]:
            component = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                component.append(w)
                if w == v:
                    break
            sccs.append(sorted(component))

    # Use iterative approach to avoid recursion depth issues on large graphs
    all_nodes = set(imports_of.keys())
    for node in sorted(all_nodes):
        if node not in index:
            # Iterative Tarjan's
            _tarjan_iterative(node, imports_of, index, lowlink, index_counter,
                             stack, on_stack, sccs)

    return sccs


def _tarjan_iterative(
    start: str,
    imports_of: Dict[str, Set[str]],
    index: Dict[str, int],
    lowlink: Dict[str, int],
    index_counter: List[int],
    stack: List[str],
    on_stack: Dict[str, bool],
    sccs: List[List[str]],
) -> None:
    """Iterative version of Tarjan's strongconnect to handle deep graphs."""
    work_stack = [(start, iter(sorted(imports_of.get(start, set()))), False)]
    index[start] = index_counter[0]
    lowlink[start] = index_counter[0]
    index_counter[0] += 1
    stack.append(start)
    on_stack[start] = True

    while work_stack:
        v, neighbors, returning = work_stack[-1]

        try:
            w = next(neighbors)
            if w not in index:
                index[w] = index_counter[0]
                lowlink[w] = index_counter[0]
                index_counter[0] += 1
                stack.append(w)
                on_stack[w] = True
                work_stack.append((w, iter(sorted(imports_of.get(w, set()))), False))
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])
        except StopIteration:
            work_stack.pop()
            if work_stack:
                parent = work_stack[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[v])

            if lowlink[v] == index[v]:
                component = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    component.append(w)
                    if w == v:
                        break
                sccs.append(sorted(component))


# ═══════════════════════════════════════════════════════════════════════════
# Conversion Unit Formation
# ═══════════════════════════════════════════════════════════════════════════

def form_units(
    sccs: List[List[str]],
    imports_of: Dict[str, Set[str]],
    max_unit_size: int = 10,
) -> List[Dict[str, Any]]:
    """Form conversion units from SCCs and singleton modules.

    Multi-module SCCs become units directly (they have circular deps, must convert together).
    Singleton modules are grouped by directory/package.
    """
    units = []
    singletons: Dict[str, List[str]] = defaultdict(list)

    for scc in sccs:
        if len(scc) > 1:
            # Multi-module SCC → one unit (or split if too large)
            if len(scc) <= max_unit_size:
                name = _unit_name_from_paths(scc)
                units.append({
                    "name": name,
                    "modules": scc,
                    "is_cluster": True,
                })
            else:
                # Split large SCCs by sub-package (best-effort)
                sub_groups = _split_by_package(scc, max_unit_size)
                for i, group in enumerate(sub_groups):
                    name = f"{_unit_name_from_paths(group)}-part{i+1}"
                    units.append({
                        "name": name,
                        "modules": group,
                        "is_cluster": True,
                    })
        else:
            # Singleton — group by directory
            module = scc[0]
            pkg = _package_name(module)
            singletons[pkg].append(module)

    # Group singletons into units by package
    for pkg, modules in sorted(singletons.items()):
        if len(modules) <= max_unit_size:
            units.append({
                "name": pkg or "root",
                "modules": sorted(modules),
                "is_cluster": False,
            })
        else:
            # Split large packages
            for i in range(0, len(modules), max_unit_size):
                batch = sorted(modules[i : i + max_unit_size])
                suffix = f"-part{i // max_unit_size + 1}" if len(modules) > max_unit_size else ""
                units.append({
                    "name": f"{pkg or 'root'}{suffix}",
                    "modules": batch,
                    "is_cluster": False,
                })

    return units


def _unit_name_from_paths(paths: List[str]) -> str:
    """Derive a unit name from a list of module paths."""
    if not paths:
        return "unknown"
    # Find common prefix
    parts_list = [Path(p).parts for p in paths]
    common = []
    for parts in zip(*parts_list):
        if len(set(parts)) == 1:
            common.append(parts[0])
        else:
            break
    if common:
        name = "-".join(common[-2:])  # Last 2 parts of common prefix
    else:
        name = Path(paths[0]).stem
    # Clean up
    name = name.replace("/", "-").replace("\\", "-").replace(".", "-").replace("_", "-")
    return name.lower().strip("-") or "unit"


def _package_name(module_path: str) -> str:
    """Get the package name for a module path."""
    parent = str(Path(module_path).parent)
    return parent.replace("/", "-").replace("\\", "-").replace(".", "-").strip("-").lower() or "root"


def _split_by_package(modules: List[str], max_size: int) -> List[List[str]]:
    """Split a list of modules into groups by sub-package, respecting max_size."""
    by_pkg: Dict[str, List[str]] = defaultdict(list)
    for m in modules:
        pkg = _package_name(m)
        by_pkg[pkg].append(m)

    groups = []
    for modules_in_pkg in by_pkg.values():
        for i in range(0, len(modules_in_pkg), max_size):
            groups.append(sorted(modules_in_pkg[i : i + max_size]))
    return groups


# ═══════════════════════════════════════════════════════════════════════════
# Unit Dependencies and Scheduling
# ═══════════════════════════════════════════════════════════════════════════

def compute_unit_dependencies(
    units: List[Dict[str, Any]],
    imports_of: Dict[str, Set[str]],
) -> None:
    """Compute inter-unit dependencies and add them to each unit."""
    # Build module → unit mapping
    module_to_unit: Dict[str, str] = {}
    for unit in units:
        for mod in unit["modules"]:
            module_to_unit[mod] = unit["name"]

    for unit in units:
        deps = set()
        for mod in unit["modules"]:
            for imported in imports_of.get(mod, set()):
                dep_unit = module_to_unit.get(imported)
                if dep_unit and dep_unit != unit["name"]:
                    deps.add(dep_unit)
        unit["dependencies"] = sorted(deps)


def schedule_waves(units: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Schedule units into waves using topological ordering.

    Wave 1 = units with no dependencies
    Wave N = units whose dependencies are all in waves < N
    """
    unit_map = {u["name"]: u for u in units}
    scheduled: Set[str] = set()
    waves: List[List[Dict[str, Any]]] = []

    remaining = set(u["name"] for u in units)

    while remaining:
        # Find units whose dependencies are all scheduled
        wave = []
        for name in sorted(remaining):
            unit = unit_map[name]
            deps = set(unit.get("dependencies", []))
            if deps.issubset(scheduled):
                wave.append(unit)

        if not wave:
            # Circular dependency at the unit level — shouldn't happen if SCCs are handled
            # but fall back to scheduling remaining units together
            wave = [unit_map[n] for n in sorted(remaining)]
            for u in wave:
                u["_forced"] = True

        for u in wave:
            scheduled.add(u["name"])
            remaining.discard(u["name"])

        waves.append(wave)

    return waves


def compute_critical_path(
    units: List[Dict[str, Any]],
    waves: List[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Compute the critical path through the conversion unit DAG.

    The critical path is the longest dependency chain, which determines
    the minimum possible migration time.
    """
    unit_map = {u["name"]: u for u in units}
    unit_wave = {}
    for wave_idx, wave in enumerate(waves):
        for u in wave:
            unit_wave[u["name"]] = wave_idx

    # Compute longest path from each unit using dynamic programming
    longest: Dict[str, int] = {}
    path_next: Dict[str, Optional[str]] = {}

    def _longest_from(name: str) -> int:
        if name in longest:
            return longest[name]
        unit = unit_map.get(name)
        if not unit:
            return 0
        deps = unit.get("dependencies", [])
        if not deps:
            longest[name] = 1
            path_next[name] = None
            return 1
        best = 0
        best_dep = None
        for dep in deps:
            dep_len = _longest_from(dep)
            if dep_len > best:
                best = dep_len
                best_dep = dep
        longest[name] = best + 1
        path_next[name] = best_dep
        return longest[name]

    for unit in units:
        _longest_from(unit["name"])

    if not longest:
        return {"length": 0, "units": [], "estimated_days": 0}

    # Find the starting unit of the critical path
    start = max(longest, key=longest.get)
    path = []
    current = start
    while current:
        path.append(current)
        current = path_next.get(current)

    return {
        "length": len(path),
        "units": path,
        "estimated_days": len(path) * 3,  # Rough: 3 days per unit on critical path
    }


# ═══════════════════════════════════════════════════════════════════════════
# Risk Scoring and Effort Estimation
# ═══════════════════════════════════════════════════════════════════════════

RISK_LEVELS = {"low": 1, "medium": 2, "high": 3, "critical": 4}
RISK_NAMES = {1: "low", 2: "medium", 3: "high", 4: "critical"}


def score_units(
    units: List[Dict[str, Any]],
    imported_by: Dict[str, Set[str]],
    state: Optional[Dict[str, Any]] = None,
) -> None:
    """Add risk scores, effort estimates, and metrics to each unit."""
    # Module → unit mapping
    module_to_unit: Dict[str, str] = {}
    for unit in units:
        for mod in unit["modules"]:
            module_to_unit[mod] = unit["name"]

    modules_state = state.get("modules", {}) if state else {}

    for unit in units:
        total_loc = 0
        total_py2_isms = 0
        max_risk = 1
        risk_factors_set: Set[str] = set()
        automatable_total = 0
        total_findings = 0

        for mod in unit["modules"]:
            mod_state = modules_state.get(mod, {})

            # LOC
            metrics = mod_state.get("metrics", {})
            loc = metrics.get("lines_of_code", 0)
            total_loc += loc

            # Risk
            risk = mod_state.get("risk_score", "medium").lower()
            risk_val = RISK_LEVELS.get(risk, 2)
            max_risk = max(max_risk, risk_val)

            # Risk factors
            for rf in mod_state.get("risk_factors", []):
                risk_factors_set.add(rf)

            # Py2-ism counts
            counts = mod_state.get("py2_ism_counts", {})
            total_py2_isms += sum(counts.values())

        # Fan-in: how many units depend on this one
        unit_fan_in = 0
        for mod in unit["modules"]:
            for importer in imported_by.get(mod, set()):
                if module_to_unit.get(importer) != unit["name"]:
                    unit_fan_in += 1

        # Boost risk for high fan-in
        if unit_fan_in >= 10:
            max_risk = max(max_risk, 3)
        if unit_fan_in >= 20:
            max_risk = max(max_risk, 4)

        # Effort estimation (rough hours)
        base_hours = total_loc / 200  # ~200 LOC per hour for mechanical conversion
        semantic_multiplier = 1.5 if any(
            rf in risk_factors_set
            for rf in ["binary_protocol_handling", "ebcdic_decoding",
                       "encoding_operations", "serialization"]
        ) else 1.0
        effort_hours = max(1, round(base_hours * semantic_multiplier))

        unit["risk_score"] = RISK_NAMES.get(max_risk, "medium")
        unit["risk_factors"] = sorted(risk_factors_set)
        unit["py2_ism_count"] = total_py2_isms
        unit["lines_of_code"] = total_loc
        unit["fan_in"] = unit_fan_in
        unit["estimated_effort_hours"] = effort_hours
        unit["module_count"] = len(unit["modules"])


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Plan the conversion order for a Python 2→3 migration."
    )
    parser.add_argument(
        "--dep-graph", required=True,
        help="Path to dependency-graph.json from Skill 0.1",
    )
    parser.add_argument(
        "--migration-order", required=True,
        help="Path to migration-order.json from Skill 0.1",
    )
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--target-version", default="3.12", help="Target Python 3 version")
    parser.add_argument("--state-file", default=None, help="Path to migration-state.json")
    parser.add_argument("--max-unit-size", type=int, default=10, help="Max modules per unit")
    parser.add_argument("--parallelism", type=int, default=3, help="Max parallel units")

    args = parser.parse_args()

    # Load inputs
    print("Loading dependency graph...")
    with open(args.dep_graph, "r") as f:
        dep_graph = json.load(f)

    print("Loading migration order...")
    with open(args.migration_order, "r") as f:
        migration_order = json.load(f)

    state = None
    if args.state_file and os.path.exists(args.state_file):
        print("Loading migration state...")
        with open(args.state_file, "r") as f:
            state = json.load(f)

    # Build adjacency
    print("Building adjacency lists...")
    imports_of, imported_by = build_adjacency(dep_graph)
    all_modules = set(imports_of.keys()) | set(imported_by.keys())
    print(f"  {len(all_modules)} modules, {sum(len(v) for v in imports_of.values())} edges")

    # Find SCCs
    print("Finding strongly connected components...")
    sccs = find_sccs(imports_of)
    multi_sccs = [s for s in sccs if len(s) > 1]
    print(f"  {len(sccs)} components, {len(multi_sccs)} multi-module clusters")

    # Form units
    print("Forming conversion units...")
    units = form_units(sccs, imports_of, args.max_unit_size)
    print(f"  {len(units)} conversion units")

    # Compute unit dependencies
    print("Computing unit dependencies...")
    compute_unit_dependencies(units, imports_of)

    # Schedule waves
    print("Scheduling waves...")
    waves = schedule_waves(units)
    print(f"  {len(waves)} waves")

    # Score units
    print("Scoring and estimating effort...")
    score_units(units, imported_by, state)

    # Critical path
    print("Computing critical path...")
    critical_path = compute_critical_path(units, waves)
    print(f"  Critical path length: {critical_path['length']} units")

    # Identify gateway units
    gateway_units = []
    for unit in units:
        if unit.get("fan_in", 0) >= 5:
            wave_num = None
            for i, wave in enumerate(waves, 1):
                if any(u["name"] == unit["name"] for u in wave):
                    wave_num = i
                    break
            gateway_units.append({
                "name": unit["name"],
                "fan_in": unit["fan_in"],
                "wave": wave_num,
                "risk_score": unit["risk_score"],
                "notes": f"Blocks {unit['fan_in']} downstream dependencies. Convert with extra care.",
            })
    gateway_units.sort(key=lambda g: g["fan_in"], reverse=True)

    # Build the plan
    plan = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "target_version": args.target_version,
        "total_modules": len(all_modules),
        "total_units": len(units),
        "total_waves": len(waves),
        "estimated_effort_days": round(
            sum(u.get("estimated_effort_hours", 0) for u in units) / 8
        ),
        "parallelism": args.parallelism,
        "waves": [
            {
                "wave": i + 1,
                "units": [
                    {k: v for k, v in u.items() if k != "_forced"}
                    for u in wave
                ],
            }
            for i, wave in enumerate(waves)
        ],
        "critical_path": critical_path,
        "gateway_units": gateway_units,
    }

    # Write outputs
    os.makedirs(args.output, exist_ok=True)

    plan_path = os.path.join(args.output, "conversion-plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)

    cp_path = os.path.join(args.output, "critical-path.json")
    with open(cp_path, "w", encoding="utf-8") as f:
        json.dump(critical_path, f, indent=2, ensure_ascii=False)

    # Summary
    print(f"\n{'='*60}")
    print(f"Conversion Plan Summary")
    print(f"{'='*60}")
    print(f"Target version:     Python {args.target_version}")
    print(f"Total modules:      {len(all_modules)}")
    print(f"Conversion units:   {len(units)}")
    print(f"Waves:              {len(waves)}")
    print(f"Critical path:      {critical_path['length']} units ({critical_path['estimated_days']} days est.)")
    print(f"Total effort est:   {plan['estimated_effort_days']} person-days")
    if gateway_units:
        print(f"\nGateway units (high fan-in):")
        for gw in gateway_units[:5]:
            print(f"  {gw['name']}: fan-in {gw['fan_in']}, risk {gw['risk_score']}")
    print(f"\nPlan: {plan_path}")
    print(f"Critical path: {cp_path}")


if __name__ == "__main__":
    main()
