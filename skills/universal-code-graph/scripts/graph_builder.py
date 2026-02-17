#!/usr/bin/env python3
"""
Build a unified NetworkX graph from extracted symbols and imports.

Creates:
- dependency-graph.json: Module-level dependencies
- call-graph.json: Function-level call relationships
- codebase-graph.graphml: Full graph in GraphML format (optional)

Computes:
- Topological sort
- Strongly connected components (SCC clusters)
- Fan-in/fan-out metrics per node
- Module risk/complexity scoring

Usage:
  As CLI:
    python3 graph_builder.py <symbols_dir> --language-map <file> --output <dir>
    python3 graph_builder.py --merge raw-scan*.json --output <dir>

  As library:
    from graph_builder import build_dependency_graph
    graph = build_dependency_graph(symbols_list, language_map)
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    logger.warning("networkx not available. Graph algorithms will be limited.")


class CodebaseGraph:
    """Builds and analyzes a code dependency graph."""

    def __init__(self):
        """Initialize graph structures."""
        if HAS_NETWORKX:
            self.dep_graph = nx.DiGraph()
            self.call_graph = nx.DiGraph()
        else:
            self.dep_graph = None
            self.call_graph = None

        self.nodes = {}  # node_id -> node_data
        self.edges = []  # List of edge dicts
        self.file_to_language = {}

    def add_module_node(
        self,
        filepath: str,
        language: str,
        loc: int = 0,
        definitions: Optional[List[Dict]] = None
    ) -> None:
        """
        Add a module (file) node to the graph.

        Args:
            filepath: File path
            language: Programming language
            loc: Lines of code estimate
            definitions: List of definitions (functions, classes)
        """
        node_id = filepath
        self.nodes[node_id] = {
            'id': node_id,
            'type': 'module',
            'language': language,
            'loc': loc,
            'definitions': definitions or [],
        }
        self.file_to_language[filepath] = language

        if HAS_NETWORKX:
            self.dep_graph.add_node(node_id, language=language, loc=loc)

    def add_function_node(
        self,
        func_id: str,
        func_name: str,
        module: str,
        language: str,
        line: int = 0
    ) -> None:
        """
        Add a function node to the call graph.

        Args:
            func_id: Unique function identifier (e.g., "file:function_name")
            func_name: Function name
            module: Module (file) containing function
            language: Programming language
            line: Line number
        """
        self.nodes[func_id] = {
            'id': func_id,
            'type': 'function',
            'name': func_name,
            'module': module,
            'language': language,
            'line': line,
        }

        if HAS_NETWORKX:
            self.call_graph.add_node(func_id, module=module, language=language)

    def add_import_edge(
        self,
        source: str,
        target: str,
        imported_name: Optional[str] = None
    ) -> None:
        """
        Add an import edge (module → module dependency).

        Args:
            source: Importing module path
            target: Imported module path
            imported_name: Name of imported symbol
        """
        edge = {
            'source': source,
            'target': target,
            'type': 'import',
            'imported_name': imported_name,
        }
        self.edges.append(edge)

        if HAS_NETWORKX and source in self.dep_graph and target in self.dep_graph:
            if not self.dep_graph.has_edge(source, target):
                self.dep_graph.add_edge(source, target, type='import')

    def add_call_edge(
        self,
        source: str,
        target: str,
        context: Optional[str] = None
    ) -> None:
        """
        Add a call edge (function → function).

        Args:
            source: Calling function ID
            target: Called function ID
            context: Context (e.g., "direct", "indirect")
        """
        edge = {
            'source': source,
            'target': target,
            'type': 'call',
            'context': context or 'direct',
        }
        self.edges.append(edge)

        if HAS_NETWORKX and source in self.call_graph and target in self.call_graph:
            if not self.call_graph.has_edge(source, target):
                self.call_graph.add_edge(source, target, type='call')

    def compute_metrics(self) -> Dict[str, Any]:
        """
        Compute graph metrics.

        Returns:
            Dict with metrics:
            - nodes: count
            - edges: count
            - languages: set of detected languages
            - clusters: SCC clusters (if networkx available)
            - topological_order: sorted node list (if acyclic)
        """
        metrics = {
            'nodes': len(self.nodes),
            'edges': len(self.edges),
            'languages': list(set(self.file_to_language.values())),
        }

        if HAS_NETWORKX and self.dep_graph:
            # Strongly connected components
            sccs = list(nx.strongly_connected_components(self.dep_graph))
            metrics['clusters'] = [
                {
                    'size': len(scc),
                    'nodes': sorted(scc),
                }
                for scc in sccs
            ]

            # Topological sort (if DAG)
            try:
                topo_sort = list(nx.topological_sort(self.dep_graph))
                metrics['topological_order'] = topo_sort
                metrics['is_dag'] = True
            except nx.NetworkXError:
                metrics['is_dag'] = False
                metrics['topological_order'] = []

            # Fan-in / fan-out
            fan_in = {}
            fan_out = {}
            for node in self.dep_graph.nodes():
                fan_in[node] = self.dep_graph.in_degree(node)
                fan_out[node] = self.dep_graph.out_degree(node)

            metrics['fan_in'] = fan_in
            metrics['fan_out'] = fan_out

        return metrics

    def to_dict(self) -> Dict[str, Any]:
        """Export graph as dict."""
        return {
            'nodes': list(self.nodes.values()),
            'edges': self.edges,
            'metrics': self.compute_metrics(),
        }

    def to_graphml(self, filepath: str) -> None:
        """Export graph as GraphML."""
        if not HAS_NETWORKX:
            logger.warning("networkx not available, cannot export GraphML")
            return

        # Create combined graph with all nodes
        combined = nx.DiGraph()
        for node_id, node_data in self.nodes.items():
            combined.add_node(
                node_id,
                type=node_data['type'],
                language=node_data.get('language', 'unknown')
            )

        for edge in self.edges:
            combined.add_edge(
                edge['source'],
                edge['target'],
                edge_type=edge['type']
            )

        nx.write_graphml(combined, filepath)
        logger.info(f"Wrote GraphML to {filepath}")


def build_dependency_graph(
    extracted_symbols: List[Dict[str, Any]],
    language_map: Dict[str, str]
) -> CodebaseGraph:
    """
    Build a dependency graph from extracted symbols.

    Args:
        extracted_symbols: List of extraction results, one per file
        language_map: Mapping from filepath to language

    Returns:
        CodebaseGraph instance
    """
    graph = CodebaseGraph()

    # Track all definitions for later call matching
    all_definitions = {}  # name -> {filepath, line, type}
    all_imports = {}  # (filepath) -> [imports]

    # Pass 1: Add module nodes and collect definitions
    for result in extracted_symbols:
        filepath = result.get('filepath', '')
        language = language_map.get(filepath, 'unknown')
        definitions = result.get('definitions', [])

        loc = result.get('metrics', {}).get('loc', 0)
        graph.add_module_node(filepath, language, loc, definitions)

        # Collect definitions
        for defn in definitions:
            name = defn.get('name', '')
            if name:
                all_definitions[name] = {
                    'filepath': filepath,
                    'line': defn.get('line', 0),
                    'type': defn.get('type', 'unknown'),
                }

        # Collect imports for this file
        if filepath not in all_imports:
            all_imports[filepath] = []
        all_imports[filepath].extend(result.get('imports', []))

    # Pass 2: Add import edges
    for filepath, imports in all_imports.items():
        for imp in imports:
            import_name = imp.get('name', '')
            # Try to resolve import to a file
            # Simple heuristic: look for a file with matching module name
            target_file = None
            for other_file in language_map.keys():
                if import_name in other_file or other_file.endswith(import_name + '.py'):
                    target_file = other_file
                    break

            if target_file:
                graph.add_import_edge(filepath, target_file, import_name)

    # Pass 3: Build function nodes and call graph
    for result in extracted_symbols:
        filepath = result.get('filepath', '')
        calls = result.get('calls', [])

        # Add function nodes from definitions
        for defn in result.get('definitions', []):
            func_name = defn.get('name', '')
            if func_name:
                func_id = f"{filepath}:{func_name}"
                language = language_map.get(filepath, 'unknown')
                graph.add_function_node(
                    func_id,
                    func_name,
                    filepath,
                    language,
                    defn.get('line', 0)
                )

        # Add call edges
        for call in calls:
            call_name = call.get('name', '')
            if call_name:
                source_id = f"{filepath}:call"  # Simplification
                # Try to match call to a known definition
                if call_name in all_definitions:
                    target_info = all_definitions[call_name]
                    target_id = f"{target_info['filepath']}:{call_name}"
                    graph.add_call_edge(source_id, target_id)

    return graph


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Build dependency graph from extracted symbols'
    )

    # Mutually exclusive: either symbols directory or merge mode
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        'symbols_dir',
        nargs='?',
        help='Directory containing extracted symbol files'
    )
    input_group.add_argument(
        '--merge',
        nargs='+',
        help='List of raw-scan.json files to merge'
    )

    parser.add_argument(
        '--language-map',
        help='Language map JSON file (required if not using --merge)'
    )
    parser.add_argument(
        '--output',
        required=True,
        help='Output directory'
    )
    parser.add_argument(
        '--graphml',
        action='store_true',
        help='Also export as GraphML'
    )

    args = parser.parse_args()

    try:
        output_dir = Path(args.output)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load symbol data
        symbol_results = []
        language_map = {}

        if args.merge:
            # Merge mode: load from raw-scan files
            for scan_file in args.merge:
                with open(scan_file, 'r') as f:
                    data = json.load(f)
                    # Merge results
                    if isinstance(data, list):
                        symbol_results.extend(data)
                    elif 'results' in data:
                        symbol_results.extend(data['results'])
                    else:
                        symbol_results.append(data)
        else:
            # Directory mode
            symbols_dir = Path(args.symbols_dir)
            if not symbols_dir.is_dir():
                raise ValueError(f"Not a directory: {symbols_dir}")

            # Load language map
            if args.language_map:
                with open(args.language_map, 'r') as f:
                    language_map = json.load(f)
            else:
                raise ValueError(
                    "--language-map required when not using --merge"
                )

            # Load symbol files
            for json_file in symbols_dir.glob('*.json'):
                if json_file.name.startswith('raw-scan'):
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            symbol_results.extend(data)
                        elif 'results' in data:
                            symbol_results.extend(data['results'])

        logger.info(f"Building graph from {len(symbol_results)} files...")
        graph = build_dependency_graph(symbol_results, language_map)

        # Export results
        dep_graph_data = graph.to_dict()
        with open(output_dir / 'dependency-graph.json', 'w') as f:
            json.dump(dep_graph_data, f, indent=2)
        logger.info(f"Wrote dependency-graph.json")

        # Call graph (simplified - just function nodes/edges)
        call_graph_data = {
            'nodes': [n for n in graph.nodes.values() if n['type'] == 'function'],
            'edges': [e for e in graph.edges if e['type'] == 'call'],
            'metrics': {'nodes': len([n for n in graph.nodes.values() if n['type'] == 'function']),
                       'edges': len([e for e in graph.edges if e['type'] == 'call'])},
        }
        with open(output_dir / 'call-graph.json', 'w') as f:
            json.dump(call_graph_data, f, indent=2)
        logger.info(f"Wrote call-graph.json")

        # GraphML export
        if args.graphml:
            graph.to_graphml(str(output_dir / 'codebase-graph.graphml'))

        # Print summary
        summary = {
            'status': 'success',
            'output_dir': str(output_dir),
            'nodes': graph.to_dict()['metrics']['nodes'],
            'edges': len(graph.edges),
            'languages': graph.to_dict()['metrics']['languages'],
        }
        print(json.dumps(summary, indent=2))

        return 0

    except Exception as e:
        logger.error(f"Error: {e}")
        print(json.dumps({'status': 'error', 'message': str(e)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
