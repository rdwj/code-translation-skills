#!/usr/bin/env python3
"""
Dependency Graph Builder

Takes the raw-scan.json from analyze.py and constructs:
- A full dependency graph (nodes = modules, edges = imports)
- Topological sort for migration order
- Cluster detection for tightly-coupled modules
- Gateway module identification

Usage:
    python3 build_dep_graph.py <raw-scan.json> --output <output_dir>

Outputs:
    <output_dir>/dependency-graph.json
    <output_dir>/migration-order.json
"""

import json
import os
import sys
import argparse
from collections import defaultdict, deque
from typing import Dict, List, Set, Tuple, Any, Optional


def extract_module_name(filepath: str) -> str:
    """Convert a file path to a module name.
    
    src/scada/modbus_reader.py -> src.scada.modbus_reader
    src/scada/__init__.py -> src.scada
    """
    # Remove .py extension
    if filepath.endswith("/__init__.py"):
        module = filepath[:-12]  # Remove /__init__.py
    elif filepath.endswith(".py"):
        module = filepath[:-3]
    else:
        module = filepath
    return module.replace("/", ".").replace("\\", ".")


def is_internal_import(module_name: str, all_modules: Set[str], codebase_packages: Set[str]) -> bool:
    """Determine if an import refers to an internal (project) module vs external."""
    # Direct match
    if module_name in all_modules:
        return True
    # Check if it's a submodule of a known package
    parts = module_name.split(".")
    for i in range(len(parts), 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in all_modules or prefix in codebase_packages:
            return True
    return False


def build_graph(raw_scan: Dict) -> Dict[str, Any]:
    """Build the dependency graph from raw scan data."""
    results = raw_scan.get("results", [])
    
    # First pass: collect all module names and top-level packages
    all_modules = set()
    file_to_module = {}
    module_to_file = {}
    codebase_packages = set()
    
    for result in results:
        filepath = result["file"]
        module = extract_module_name(filepath)
        all_modules.add(module)
        file_to_module[filepath] = module
        module_to_file[module] = filepath
        # Track packages (directories that contain Python files)
        parts = module.split(".")
        for i in range(1, len(parts)):
            codebase_packages.add(".".join(parts[:i]))
    
    # Second pass: build adjacency lists
    # edges[A] = set of modules that A imports (A depends on them)
    edges: Dict[str, Set[str]] = defaultdict(set)
    # reverse_edges[B] = set of modules that import B (depend on B)
    reverse_edges: Dict[str, Set[str]] = defaultdict(set)
    # Track external dependencies too
    external_deps: Dict[str, Set[str]] = defaultdict(set)
    
    for result in results:
        filepath = result["file"]
        module = file_to_module[filepath]
        
        for imp in result.get("imports", []):
            imp_module = imp.get("module", "")
            if not imp_module:
                continue
            
            if is_internal_import(imp_module, all_modules, codebase_packages):
                # Resolve to the actual module name in our codebase
                resolved = resolve_import(imp_module, all_modules, codebase_packages)
                if resolved and resolved != module:
                    edges[module].add(resolved)
                    reverse_edges[resolved].add(module)
            else:
                external_deps[module].add(imp_module)
    
    # Node metadata
    nodes = {}
    for result in results:
        filepath = result["file"]
        module = file_to_module[filepath]
        metrics = result.get("metrics", {})
        risk = result.get("risk_assessment", {})
        
        nodes[module] = {
            "module": module,
            "file": filepath,
            "lines": metrics.get("lines", 0),
            "functions": metrics.get("functions", 0),
            "classes": metrics.get("classes", 0),
            "risk_score": risk.get("score", 0),
            "risk_rating": risk.get("rating", "unknown"),
            "imports_internal": sorted(edges.get(module, set())),
            "imported_by": sorted(reverse_edges.get(module, set())),
            "imports_external": sorted(external_deps.get(module, set())),
            "fan_out": len(edges.get(module, set())),  # How many modules this depends on
            "fan_in": len(reverse_edges.get(module, set())),  # How many modules depend on this
        }
    
    return {
        "nodes": nodes,
        "edges": {k: sorted(v) for k, v in edges.items()},
        "reverse_edges": {k: sorted(v) for k, v in reverse_edges.items()},
        "module_count": len(nodes),
        "edge_count": sum(len(v) for v in edges.values()),
    }


def resolve_import(imp_module: str, all_modules: Set[str], codebase_packages: Set[str]) -> Optional[str]:
    """Resolve an import name to the actual module in the codebase."""
    if imp_module in all_modules:
        return imp_module
    # Try as a package (might import __init__)
    if imp_module in codebase_packages:
        return imp_module
    # Try partial match (e.g., importing 'foo.bar' when we have 'foo.bar.baz')
    for mod in all_modules:
        if mod.startswith(imp_module + "."):
            return imp_module
    return None


def find_clusters(edges: Dict[str, Set[str]], reverse_edges: Dict[str, Set[str]]) -> List[List[str]]:
    """Find strongly connected components (clusters of mutually-importing modules).
    
    Uses Tarjan's algorithm.
    """
    # Build combined edge set for SCC detection
    all_nodes = set(edges.keys()) | set(reverse_edges.keys())
    for targets in edges.values():
        all_nodes.update(targets)
    for sources in reverse_edges.values():
        all_nodes.update(sources)
    
    index_counter = [0]
    stack = []
    lowlink = {}
    index = {}
    on_stack = {}
    sccs = []
    
    def strongconnect(v):
        index[v] = index_counter[0]
        lowlink[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack[v] = True
        
        for w in edges.get(v, set()):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif on_stack.get(w, False):
                lowlink[v] = min(lowlink[v], index[w])
        
        if lowlink[v] == index[v]:
            scc = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == v:
                    break
            if len(scc) > 1:  # Only report non-trivial SCCs
                sccs.append(sorted(scc))
    
    for v in sorted(all_nodes):
        if v not in index:
            strongconnect(v)
    
    return sccs


def topological_sort(
    edges: Dict[str, Set[str]], 
    all_modules: Set[str],
    clusters: List[List[str]]
) -> List[Dict[str, Any]]:
    """Topological sort with cluster awareness.
    
    Modules in a cluster are grouped together. The sort determines the order
    of clusters and standalone modules.
    """
    # Map each module to its cluster (or itself if standalone)
    module_to_cluster = {}
    cluster_map = {}
    for i, cluster in enumerate(clusters):
        cluster_id = f"cluster_{i}"
        cluster_map[cluster_id] = cluster
        for mod in cluster:
            module_to_cluster[mod] = cluster_id
    
    for mod in all_modules:
        if mod not in module_to_cluster:
            module_to_cluster[mod] = mod
    
    # Build cluster-level edges
    cluster_edges: Dict[str, Set[str]] = defaultdict(set)
    all_units = set(module_to_cluster.values())
    
    for mod, deps in edges.items():
        src_unit = module_to_cluster.get(mod, mod)
        for dep in deps:
            dst_unit = module_to_cluster.get(dep, dep)
            if src_unit != dst_unit:
                cluster_edges[src_unit].add(dst_unit)
    
    # Kahn's algorithm for topological sort
    in_degree = defaultdict(int)
    for unit in all_units:
        if unit not in in_degree:
            in_degree[unit] = 0
    for src, dsts in cluster_edges.items():
        for dst in dsts:
            in_degree[dst] = in_degree.get(dst, 0)
        for dst in dsts:
            # Wait — we want to convert dependencies first.
            # If A depends on B, B should come first in the migration order.
            # So the edge direction for topological sort is reversed:
            # we process nodes with no remaining dependencies first.
            pass
    
    # Recompute: in_degree = how many dependencies a unit has (not how many depend on it)
    in_degree = defaultdict(int)
    for unit in all_units:
        in_degree[unit] = 0
    for src, dsts in cluster_edges.items():
        for dst in dsts:
            in_degree[src] = in_degree.get(src, 0)
            # src depends on dst, so src has higher in-degree in dependency sense
            # But for migration: we want to process dst (the dependency) first
            # So we sort by reverse: nodes with fewest dependencies go first
            pass
    
    # Simpler approach: compute depth (longest chain to a leaf) for each unit
    depth_cache = {}
    
    def compute_depth(unit, visited=None):
        if visited is None:
            visited = set()
        if unit in depth_cache:
            return depth_cache[unit]
        if unit in visited:
            return 0  # Cycle (shouldn't happen at cluster level)
        visited.add(unit)
        deps = cluster_edges.get(unit, set())
        if not deps:
            depth_cache[unit] = 0
            return 0
        max_dep_depth = max(compute_depth(d, visited) for d in deps)
        depth_cache[unit] = max_dep_depth + 1
        return depth_cache[unit]
    
    for unit in all_units:
        compute_depth(unit)
    
    # Sort: lowest depth first (leaf dependencies), then alphabetically
    sorted_units = sorted(all_units, key=lambda u: (depth_cache.get(u, 0), u))
    
    # Build the migration order
    order = []
    for i, unit in enumerate(sorted_units):
        if unit in cluster_map:
            order.append({
                "order": i + 1,
                "type": "cluster",
                "id": unit,
                "modules": cluster_map[unit],
                "depth": depth_cache.get(unit, 0),
                "note": "These modules are mutually dependent and must be converted together",
            })
        else:
            order.append({
                "order": i + 1,
                "type": "module",
                "id": unit,
                "modules": [unit],
                "depth": depth_cache.get(unit, 0),
            })
    
    return order


def identify_special_modules(graph: Dict[str, Any]) -> Dict[str, Any]:
    """Identify leaf modules, gateway modules, and orphans."""
    nodes = graph["nodes"]
    
    leaves = []      # No internal dependencies
    gateways = []    # Many modules depend on them (high fan-in)
    orphans = []     # Nothing imports them and they import nothing
    
    fan_in_values = [n["fan_in"] for n in nodes.values() if n["fan_in"] > 0]
    gateway_threshold = (
        sorted(fan_in_values)[int(len(fan_in_values) * 0.9)] if fan_in_values else 3
    )
    gateway_threshold = max(gateway_threshold, 3)  # At least 3 dependents
    
    for mod, info in nodes.items():
        if info["fan_out"] == 0:
            leaves.append(mod)
        if info["fan_in"] >= gateway_threshold:
            gateways.append({"module": mod, "fan_in": info["fan_in"]})
        if info["fan_in"] == 0 and info["fan_out"] == 0:
            orphans.append(mod)
    
    gateways.sort(key=lambda x: -x["fan_in"])
    
    return {
        "leaves": sorted(leaves),
        "gateways": gateways,
        "orphans": sorted(orphans),
        "gateway_threshold": gateway_threshold,
    }


def main():
    parser = argparse.ArgumentParser(description="Build dependency graph from codebase scan")
    parser.add_argument("raw_scan", help="Path to raw-scan.json from analyze.py")
    parser.add_argument("--output", "-o", required=True, help="Output directory")
    args = parser.parse_args()
    
    with open(args.raw_scan, "r") as f:
        raw_scan = json.load(f)
    
    os.makedirs(args.output, exist_ok=True)
    
    print("Building dependency graph...")
    graph = build_graph(raw_scan)
    
    print("Detecting clusters (strongly connected components)...")
    edge_sets = {k: set(v) for k, v in graph["edges"].items()}
    reverse_sets = {k: set(v) for k, v in graph["reverse_edges"].items()}
    clusters = find_clusters(edge_sets, reverse_sets)
    
    print("Computing migration order...")
    all_modules = set(graph["nodes"].keys())
    migration_order = topological_sort(edge_sets, all_modules, clusters)
    
    print("Identifying special modules...")
    special = identify_special_modules(graph)
    
    # Write dependency graph
    graph_output = {
        "codebase_root": raw_scan.get("codebase_root", ""),
        "module_count": graph["module_count"],
        "edge_count": graph["edge_count"],
        "cluster_count": len(clusters),
        "clusters": clusters,
        "special_modules": special,
        "nodes": graph["nodes"],
    }
    
    graph_path = os.path.join(args.output, "dependency-graph.json")
    with open(graph_path, "w") as f:
        json.dump(graph_output, f, indent=2, default=str)
    print(f"Wrote {graph_path}")
    
    # Write migration order
    order_output = {
        "codebase_root": raw_scan.get("codebase_root", ""),
        "total_conversion_units": len(migration_order),
        "total_modules": len(all_modules),
        "clusters": len(clusters),
        "migration_order": migration_order,
        "summary": {
            "leaf_modules": len(special["leaves"]),
            "gateway_modules": len(special["gateways"]),
            "orphan_modules": len(special["orphans"]),
            "max_depth": max((u["depth"] for u in migration_order), default=0),
        },
    }
    
    order_path = os.path.join(args.output, "migration-order.json")
    with open(order_path, "w") as f:
        json.dump(order_output, f, indent=2, default=str)
    print(f"Wrote {order_path}")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"DEPENDENCY GRAPH BUILT")
    print(f"{'='*60}")
    print(f"Modules:              {graph['module_count']}")
    print(f"Import relationships: {graph['edge_count']}")
    print(f"Clusters (SCCs):      {len(clusters)}")
    print(f"Leaf modules:         {len(special['leaves'])}")
    print(f"Gateway modules:      {len(special['gateways'])}")
    print(f"Orphan modules:       {len(special['orphans'])}")
    print(f"Conversion units:     {len(migration_order)}")
    print(f"Max dependency depth: {max((u['depth'] for u in migration_order), default=0)}")
    if special["gateways"]:
        print(f"\nTop gateway modules (most depended on):")
        for gw in special["gateways"][:5]:
            print(f"  {gw['module']} ({gw['fan_in']} dependents)")


if __name__ == "__main__":
    main()
