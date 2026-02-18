#!/usr/bin/env python3
"""
Script: analyze_universal.py
Purpose: Orchestrate full codebase analysis pipeline
Inputs: Project root directory
Outputs: language-map.json, call-graph.json, dependency-graph.json, codebase-summary.json
LLM involvement: NONE
"""

import sys
import json
import argparse
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Set, Optional, Tuple
import os
import re

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# Import the analysis modules
try:
    from language_detect import detect_languages
    HAS_LANG_DETECT = True
except ImportError:
    HAS_LANG_DETECT = False
    logger.warning("language_detect module not available")

try:
    from ts_parser import parse_file
    HAS_TS_PARSER = True
except ImportError:
    HAS_TS_PARSER = False
    logger.warning("ts_parser module not available")

try:
    from universal_extractor import extract_symbols
    HAS_EXTRACTOR = True
except ImportError:
    HAS_EXTRACTOR = False
    logger.warning("universal_extractor module not available")

try:
    from graph_builder import build_dependency_graph
    HAS_GRAPH_BUILDER = True
except ImportError:
    HAS_GRAPH_BUILDER = False
    logger.warning("graph_builder module not available")


def _regex_extract_fallback(filepath: str, language: str) -> Dict[str, List[Dict]]:
    """
    Fallback extraction using regex when tree-sitter isn't available.
    Extracts basic definitions and imports using language-specific patterns.
    """
    definitions = []
    imports = []
    calls = []

    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            lines = content.split('\n')
    except Exception as e:
        logger.debug(f"Error reading {filepath}: {e}")
        return {'definitions': [], 'imports': [], 'calls': []}

    language_lower = language.lower()

    # Python extraction
    if language_lower in ('python', 'py'):
        # Definitions: def name(...) or class name
        def_pattern = r'^\s*(def|class)\s+(\w+)\s*[\(:]'
        # Imports: import x or from x import y
        import_pattern = r'^\s*(import|from)\s+([\w.]+)'
        # Calls: name(...) - simplistic
        call_pattern = r'(\w+)\s*\('

        for i, line in enumerate(lines, 1):
            # Definitions
            match = re.match(def_pattern, line)
            if match:
                def_type = 'class' if match.group(1) == 'class' else 'function'
                definitions.append({
                    'name': match.group(2),
                    'type': def_type,
                    'file': filepath,
                    'line': i,
                    'column': len(line) - len(line.lstrip())
                })

            # Imports
            match = re.search(import_pattern, line)
            if match:
                imports.append({
                    'name': match.group(2),
                    'type': 'import',
                    'file': filepath,
                    'line': i,
                    'column': len(line) - len(line.lstrip())
                })

            # Calls (very basic)
            for match in re.finditer(call_pattern, line):
                calls.append({
                    'name': match.group(1),
                    'type': 'call',
                    'file': filepath,
                    'line': i,
                    'column': match.start()
                })

    # JavaScript/TypeScript extraction
    elif language_lower in ('javascript', 'typescript', 'js', 'ts', 'tsx'):
        # Definitions: function name or const/let name = or class name
        def_pattern_func = r'\b(function|async\s+function)\s+(\w+)\s*\('
        def_pattern_var = r'^\s*(const|let|var)\s+(\w+)\s*='
        def_pattern_class = r'^\s*(class|interface)\s+(\w+)'

        import_pattern = r'^\s*(import|require)\s+.*?(?:from\s+[\'"](.+?)[\'"]|require\([\'"](.+?)[\'"]\))'
        call_pattern = r'(\w+)\s*\('

        for i, line in enumerate(lines, 1):
            # Function definitions
            match = re.search(def_pattern_func, line)
            if match:
                definitions.append({
                    'name': match.group(2),
                    'type': 'function',
                    'file': filepath,
                    'line': i,
                    'column': match.start()
                })

            # Variable/const definitions
            match = re.match(def_pattern_var, line)
            if match:
                definitions.append({
                    'name': match.group(2),
                    'type': 'variable',
                    'file': filepath,
                    'line': i,
                    'column': len(line) - len(line.lstrip())
                })

            # Class/interface definitions
            match = re.match(def_pattern_class, line)
            if match:
                definitions.append({
                    'name': match.group(2),
                    'type': 'class',
                    'file': filepath,
                    'line': i,
                    'column': len(line) - len(line.lstrip())
                })

            # Imports
            match = re.search(import_pattern, line)
            if match:
                module_name = match.group(1) or match.group(2)
                if module_name:
                    imports.append({
                        'name': module_name,
                        'type': 'import',
                        'file': filepath,
                        'line': i,
                        'column': len(line) - len(line.lstrip())
                    })

            # Calls
            for match in re.finditer(call_pattern, line):
                calls.append({
                    'name': match.group(1),
                    'type': 'call',
                    'file': filepath,
                    'line': i,
                    'column': match.start()
                })

    # Java extraction
    elif language_lower in ('java',):
        def_pattern = r'^\s*(public|private|protected)?\s*(class|interface|enum|record)\s+(\w+)'
        method_pattern = r'^\s*(public|private|protected)?\s*\w+\s+(\w+)\s*\('
        import_pattern = r'^\s*import\s+([\w.]+);'

        for i, line in enumerate(lines, 1):
            # Class/interface definitions
            match = re.match(def_pattern, line)
            if match:
                def_type = match.group(2).lower()
                definitions.append({
                    'name': match.group(3),
                    'type': def_type,
                    'file': filepath,
                    'line': i,
                    'column': len(line) - len(line.lstrip())
                })

            # Method definitions
            match = re.match(method_pattern, line)
            if match and not re.match(def_pattern, line):
                definitions.append({
                    'name': match.group(2),
                    'type': 'method',
                    'file': filepath,
                    'line': i,
                    'column': len(line) - len(line.lstrip())
                })

            # Imports
            match = re.match(import_pattern, line)
            if match:
                imports.append({
                    'name': match.group(1),
                    'type': 'import',
                    'file': filepath,
                    'line': i,
                    'column': 0
                })

    # Go extraction
    elif language_lower in ('go',):
        def_pattern = r'^\s*(func|type|const|var)\s+(\w+)'
        import_pattern = r'^\s*import\s+(?:\(|"([^"]+)")'

        for i, line in enumerate(lines, 1):
            match = re.match(def_pattern, line)
            if match:
                def_type = match.group(1).lower()
                definitions.append({
                    'name': match.group(2),
                    'type': def_type,
                    'file': filepath,
                    'line': i,
                    'column': len(line) - len(line.lstrip())
                })

            match = re.match(import_pattern, line)
            if match and match.group(1):
                imports.append({
                    'name': match.group(1),
                    'type': 'import',
                    'file': filepath,
                    'line': i,
                    'column': 0
                })

    # Rust extraction
    elif language_lower in ('rust', 'rs'):
        def_pattern = r'^\s*(fn|struct|enum|trait|impl|mod|const|static)\s+(\w+)'
        import_pattern = r'^\s*use\s+([\w:]+)'

        for i, line in enumerate(lines, 1):
            match = re.match(def_pattern, line)
            if match:
                def_type = match.group(1).lower()
                definitions.append({
                    'name': match.group(2),
                    'type': def_type,
                    'file': filepath,
                    'line': i,
                    'column': len(line) - len(line.lstrip())
                })

            match = re.match(import_pattern, line)
            if match:
                imports.append({
                    'name': match.group(1),
                    'type': 'import',
                    'file': filepath,
                    'line': i,
                    'column': 0
                })

    return {
        'definitions': definitions,
        'imports': imports,
        'calls': calls
    }


def extract_from_file(
    filepath: str,
    language: str,
    query_dir: Optional[str] = None
) -> Dict[str, List[Dict]]:
    """
    Extract symbols from a file.
    Tries tree-sitter first, falls back to regex-based extraction.
    """
    # Try tree-sitter if available
    if HAS_TS_PARSER:
        try:
            tree_dict = parse_file(filepath, language)
            if tree_dict.get('parse_success'):
                if HAS_EXTRACTOR and query_dir:
                    try:
                        return extract_symbols(tree_dict, language, query_dir)
                    except Exception as e:
                        logger.debug(f"Extraction failed for {filepath}: {e}. Using fallback.")
                        return _regex_extract_fallback(filepath, language)
        except Exception as e:
            logger.debug(f"Tree-sitter parsing failed for {filepath}: {e}. Using fallback.")

    # Fallback to regex-based extraction
    return _regex_extract_fallback(filepath, language)


def analyze_codebase(
    project_root: str,
    output_dir: str,
    languages_filter: Optional[List[str]] = None,
    skip_graph: bool = False,
    query_dir: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Run the complete analysis pipeline.

    Returns:
        Tuple of (exit_code, summary_dict)
        exit_code: 0=success, 1=partial (some files failed), 2=failure
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    project_path = Path(project_root)
    if not project_path.is_dir():
        logger.error(f"Not a directory: {project_root}")
        return 2, {'status': 'error', 'message': f'Not a directory: {project_root}'}

    exit_code = 0
    summary = {
        'status': 'success',
        'project_root': str(project_path.absolute()),
        'output_dir': str(output_path.absolute()),
        'stages': {}
    }

    # Stage 1: Language Detection
    logger.info("Stage 1: Detecting languages...")
    try:
        if HAS_LANG_DETECT:
            detected_languages, language_map = detect_languages(str(project_path))
        else:
            # Fallback: manual extension mapping
            logger.warning("Language detection module not available, using basic extension mapping")
            language_map = {}
            extension_map = {
                '.py': 'python', '.java': 'java', '.js': 'javascript', '.ts': 'typescript',
                '.tsx': 'typescript', '.c': 'c', '.cpp': 'cpp', '.rs': 'rust', '.go': 'go'
            }
            for root, dirs, files in os.walk(project_path):
                dirs[:] = [d for d in dirs if d not in {'.git', '__pycache__', 'node_modules', 'venv'}]
                for file in files:
                    filepath = Path(root) / file
                    rel_path = str(filepath.relative_to(project_path))
                    ext = filepath.suffix.lower()
                    language_map[rel_path] = extension_map.get(ext, 'unknown')

            detected_languages = set(l for l in language_map.values() if l != 'unknown')

        # Filter by languages if specified
        if languages_filter:
            language_map = {
                k: v for k, v in language_map.items()
                if v in languages_filter
            }
            detected_languages = set(v for v in detected_languages if v in languages_filter)

        # Save language map
        lang_map_file = output_path / 'language-map.json'
        with open(lang_map_file, 'w') as f:
            json.dump(language_map, f, indent=2)

        files_by_language = {}
        for lang in language_map.values():
            files_by_language[lang] = files_by_language.get(lang, 0) + 1

        summary['stages']['language_detection'] = {
            'status': 'success',
            'files_detected': len(language_map),
            'languages': sorted(detected_languages),
            'files_by_language': files_by_language
        }
        logger.info(f"Detected {len(language_map)} files in {len(detected_languages)} languages")

    except Exception as e:
        logger.error(f"Language detection failed: {e}")
        summary['stages']['language_detection'] = {'status': 'error', 'error': str(e)}
        return 2, summary

    # Stage 2: Symbol Extraction
    logger.info("Stage 2: Extracting symbols...")
    extracted_symbols = []
    extraction_errors = []

    for i, (rel_filepath, language) in enumerate(language_map.items(), 1):
        full_filepath = project_path / rel_filepath
        try:
            if not full_filepath.exists():
                logger.warning(f"File not found: {full_filepath}")
                continue

            logger.debug(f"Extracting {rel_filepath} ({language})...")
            result = extract_from_file(str(full_filepath), language, query_dir)

            # Add file path and metrics
            result['filepath'] = str(full_filepath)
            result['filepath_relative'] = rel_filepath
            result['language'] = language
            result['metrics'] = {
                'definitions': len(result.get('definitions', [])),
                'imports': len(result.get('imports', [])),
                'calls': len(result.get('calls', []))
            }

            extracted_symbols.append(result)

            if (i % 50) == 0:
                logger.info(f"Processed {i}/{len(language_map)} files")

        except Exception as e:
            logger.warning(f"Extraction failed for {rel_filepath}: {e}")
            extraction_errors.append({'file': rel_filepath, 'error': str(e)})
            if exit_code == 0:
                exit_code = 1

    # Save extraction results
    extraction_file = output_path / 'extracted-symbols.json'
    with open(extraction_file, 'w') as f:
        json.dump(extracted_symbols, f, indent=2)

    total_defs = sum(len(r.get('definitions', [])) for r in extracted_symbols)
    total_imports = sum(len(r.get('imports', [])) for r in extracted_symbols)
    total_calls = sum(len(r.get('calls', [])) for r in extracted_symbols)

    summary['stages']['symbol_extraction'] = {
        'status': 'success',
        'files_processed': len(extracted_symbols),
        'total_definitions': total_defs,
        'total_imports': total_imports,
        'total_calls': total_calls,
        'errors': len(extraction_errors)
    }
    logger.info(
        f"Extracted {total_defs} definitions, {total_imports} imports, {total_calls} calls"
    )

    if skip_graph:
        summary['status'] = 'success' if exit_code == 0 else 'partial'
        summary['stages']['graph_building'] = {'status': 'skipped'}
        return exit_code, summary

    # Stage 3: Graph Building
    logger.info("Stage 3: Building dependency graph...")
    try:
        if HAS_GRAPH_BUILDER:
            graph = build_dependency_graph(extracted_symbols, language_map)

            # Export dependency graph
            dep_graph_file = output_path / 'dependency-graph.json'
            with open(dep_graph_file, 'w') as f:
                json.dump(graph.to_dict(), f, indent=2)

            # Export call graph
            call_graph_file = output_path / 'call-graph.json'
            call_graph_data = {
                'nodes': [n for n in graph.nodes.values() if n.get('type') == 'function'],
                'edges': [e for e in graph.edges if e.get('type') == 'call'],
                'metrics': {
                    'nodes': len([n for n in graph.nodes.values() if n.get('type') == 'function']),
                    'edges': len([e for e in graph.edges if e.get('type') == 'call'])
                }
            }
            with open(call_graph_file, 'w') as f:
                json.dump(call_graph_data, f, indent=2)

            metrics = graph.to_dict()['metrics']
            summary['stages']['graph_building'] = {
                'status': 'success',
                'nodes': metrics.get('nodes', 0),
                'edges': metrics.get('edges', 0),
                'languages': metrics.get('languages', []),
                'is_dag': metrics.get('is_dag', None)
            }
            logger.info(f"Built graph with {metrics.get('nodes', 0)} nodes and {metrics.get('edges', 0)} edges")
        else:
            logger.warning("Graph builder module not available, skipping graph building")
            summary['stages']['graph_building'] = {'status': 'skipped', 'reason': 'module not available'}

    except Exception as e:
        logger.error(f"Graph building failed: {e}")
        summary['stages']['graph_building'] = {'status': 'error', 'error': str(e)}
        if exit_code == 0:
            exit_code = 1

    # Generate final summary
    summary['status'] = 'success' if exit_code == 0 else 'partial'

    return exit_code, summary


@log_execution
def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Orchestrate full codebase analysis pipeline'
    )
    parser.add_argument(
        'project_root',
        help='Root directory of project to analyze'
    )
    parser.add_argument(
        '--output',
        default='codebase-analysis',
        help='Output directory for results (default: codebase-analysis)'
    )
    parser.add_argument(
        '--languages',
        nargs='+',
        help='Filter to specific languages (e.g., python javascript)'
    )
    parser.add_argument(
        '--skip-graph',
        action='store_true',
        help='Stop after extraction, skip graph building'
    )
    parser.add_argument(
        '--query-dir',
        help='Directory containing .scm query files (optional)'
    )

    args = parser.parse_args()

    # Run analysis
    exit_code, summary = analyze_codebase(
        args.project_root,
        args.output,
        languages_filter=args.languages,
        skip_graph=args.skip_graph,
        query_dir=args.query_dir
    )

    # Save comprehensive summary
    output_path = Path(args.output)
    summary_file = output_path / 'codebase-summary.json'
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    # Print concise JSON summary to stdout (< 50 lines)
    concise_summary = {
        'status': summary['status'],
        'project': str(Path(args.project_root).absolute()),
        'output': str(output_path.absolute()),
        'language_detection': summary['stages'].get('language_detection', {}),
        'symbol_extraction': summary['stages'].get('symbol_extraction', {}),
        'graph_building': summary['stages'].get('graph_building', {})
    }

    print(json.dumps(concise_summary, indent=2))

    return exit_code


if __name__ == '__main__':
    sys.exit(main())
