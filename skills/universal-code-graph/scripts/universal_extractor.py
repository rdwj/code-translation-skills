#!/usr/bin/env python3
"""
Tree-sitter query-driven extraction engine.

Runs .scm query files against parsed trees and extracts:
- Definitions (functions, classes, methods)
- Imports (module dependencies)
- Calls (function/method invocations)

Normalizes results into standard format regardless of language.

Usage:
  As library:
    from universal_extractor import extract_symbols
    symbols = extract_symbols(parsed_tree_dict, 'python', 'queries/')

  As CLI:
    python3 universal_extractor.py <parsed_tree.json> <language> [--query-dir queries/]
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


def _load_query(query_file: Path) -> Optional[str]:
    """Load a .scm query file."""
    try:
        with open(query_file, 'r') as f:
            return f.read()
    except Exception as e:
        logger.debug(f"Could not load query {query_file}: {e}")
        return None


def _run_query(tree: Any, language: str, query_str: str) -> List[tuple]:
    """
    Run a tree-sitter query against a parse tree.

    Args:
        tree: tree-sitter Tree object
        language: Language name
        query_str: Query string in .scm format

    Returns:
        List of (node, captures_dict) tuples
    """
    try:
        from tree_sitter import Query

        # Get language object
        try:
            from tree_sitter_language_pack import get_language
            lang_obj = get_language(language)
        except ImportError:
            try:
                import tree_sitter_languages
                lang_obj = tree_sitter_languages.get_language(language)
            except ImportError:
                logger.warning(f"Could not load language object for {language}")
                return []

        # Compile query
        query = Query(lang_obj, query_str)
        # Run query
        captures = query.captures(tree.root_node)
        return captures
    except Exception as e:
        logger.debug(f"Error running query for {language}: {e}")
        return []


def _fallback_extract(tree_dict: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """
    Fallback extraction when no query files are available.

    Walks the tree and looks for specific node types.
    """
    definitions = []
    imports = []
    calls = []

    def walk_tree(node_dict, parent_type='', file_path='', line_offset=0):
        node_type = node_dict.get('type', '')
        start_point = node_dict.get('start_point', [0, 0])
        line = start_point[0] + 1 + line_offset

        # Look for definitions
        if 'definition' in node_type or 'declaration' in node_type:
            name = node_dict.get('name', f'<{node_type}>')
            def_type = 'class' if 'class' in node_type else 'function'
            definitions.append({
                'name': name,
                'type': def_type,
                'file': file_path,
                'line': line,
                'column': start_point[1],
            })

        # Look for imports
        if 'import' in node_type:
            name = node_dict.get('module', node_dict.get('name', ''))
            imports.append({
                'name': name,
                'type': 'import',
                'file': file_path,
                'line': line,
                'column': start_point[1],
            })

        # Look for calls
        if 'call' in node_type:
            name = node_dict.get('function', node_dict.get('name', ''))
            calls.append({
                'name': name,
                'type': 'call',
                'file': file_path,
                'line': line,
                'column': start_point[1],
            })

        # Recurse
        for child in node_dict.get('children', []):
            walk_tree(child, node_type, file_path, line_offset)

    walk_tree(tree_dict.get('root_node', {}), file_path=tree_dict.get('filepath', ''))
    return {
        'definitions': definitions,
        'imports': imports,
        'calls': calls,
    }


def extract_symbols(
    tree_dict: Dict[str, Any],
    language: str,
    query_dir: str = 'queries/'
) -> Dict[str, List[Dict]]:
    """
    Extract symbols from a parsed tree.

    Args:
        tree_dict: Parsed tree dict (output from ts_parser.parse_file)
        language: Language name
        query_dir: Directory containing .scm query files

    Returns:
        Dict with keys:
        - definitions: List of {name, type, file, line, column}
        - imports: List of {name, type, file, line, column}
        - calls: List of {name, type, file, line, column}
    """
    query_dir = Path(query_dir)

    # Check if we have query files for this language
    query_files = {
        'definitions': query_dir / f'{language}_definitions.scm',
        'imports': query_dir / f'{language}_imports.scm',
        'calls': query_dir / f'{language}_calls.scm',
    }

    has_queries = any(f.exists() for f in query_files.values())

    if not has_queries:
        logger.warning(
            f"No query files for {language} in {query_dir}. "
            "Using fallback extraction."
        )
        return _fallback_extract(tree_dict)

    # Try to use query-based extraction
    try:
        import tree_sitter
        from tree_sitter import Parser

        # Reconstruct parser
        try:
            from tree_sitter_language_pack import get_parser
            parser = get_parser(language)
        except ImportError:
            try:
                import tree_sitter_languages
                parser = tree_sitter_languages.get_parser(language)
            except ImportError:
                logger.warning(f"Could not load parser for {language}. Using fallback.")
                return _fallback_extract(tree_dict)

        # Re-parse file if available
        file_path = tree_dict.get('filepath', '')
        if file_path and Path(file_path).exists():
            try:
                with open(file_path, 'rb') as f:
                    content = f.read()
                tree = parser.parse(content)
            except Exception as e:
                logger.debug(f"Could not re-parse file: {e}")
                return _fallback_extract(tree_dict)
        else:
            logger.debug("File not available, using fallback extraction")
            return _fallback_extract(tree_dict)

        # Run queries
        results = {
            'definitions': [],
            'imports': [],
            'calls': [],
        }

        for query_type, query_file in query_files.items():
            if not query_file.exists():
                continue

            query_str = _load_query(query_file)
            if not query_str:
                continue

            captures_list = _run_query(tree, language, query_str)
            for node, capture_names in captures_list:
                for capture_name in capture_names:
                    # Parse capture name like "import.module", "definition.function", etc.
                    parts = capture_name.split('.')
                    symbol_type = parts[-1] if len(parts) > 1 else query_type.rstrip('s')

                    symbol = {
                        'name': node.text.decode('utf-8', errors='ignore') if hasattr(node, 'text') else str(node),
                        'type': symbol_type,
                        'file': file_path,
                        'line': node.start_point[0] + 1,
                        'column': node.start_point[1],
                    }
                    results[query_type].append(symbol)

        return results

    except Exception as e:
        logger.warning(f"Error in query-based extraction: {e}. Using fallback.")
        return _fallback_extract(tree_dict)


@log_execution
def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Extract symbols from a parsed tree'
    )
    parser.add_argument('tree_file', help='Parsed tree JSON file')
    parser.add_argument('language', help='Programming language')
    parser.add_argument(
        '--query-dir',
        default='queries/',
        help='Directory containing .scm query files'
    )
    parser.add_argument(
        '--output',
        help='Output file (default: print to stdout)'
    )

    args = parser.parse_args()

    try:
        # Load tree
        with open(args.tree_file, 'r') as f:
            tree_dict = json.load(f)

        logger.info(f"Extracting symbols from {args.tree_file} ({args.language})...")
        result = extract_symbols(tree_dict, args.language, args.query_dir)

        # Output
        output_str = json.dumps(result, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_str)
            logger.info(f"Wrote output to {args.output}")
        else:
            print(output_str)

        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        print(json.dumps({'error': str(e)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
