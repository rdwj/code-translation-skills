#!/usr/bin/env python3
"""
Tree-sitter parsing wrapper with lazy grammar loading.

Provides parse_file(filepath, language) function for use as a library.
Also provides CLI mode for testing: python ts_parser.py <file> <language>

Handles missing dependencies gracefully with clear error messages.
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Global parser cache to avoid reloading grammars
_parser_cache: Dict[str, Any] = {}


def _get_parser(language: str) -> Optional[Any]:
    """
    Lazily load a tree-sitter parser for the given language.

    Args:
        language: Language name (e.g., 'python', 'java', 'javascript')

    Returns:
        Parser object or None if grammar not available
    """
    # Check cache first
    if language in _parser_cache:
        return _parser_cache[language]

    try:
        # Try tree-sitter-language-pack first (preferred, pre-compiled)
        try:
            from tree_sitter_language_pack import get_parser
            parser = get_parser(language)
            _parser_cache[language] = parser
            return parser
        except ImportError:
            pass

        # Fallback: try tree-sitter direct API
        try:
            import tree_sitter
            import tree_sitter_languages
            parser = tree_sitter_languages.get_parser(language)
            _parser_cache[language] = parser
            return parser
        except ImportError:
            pass

        # Last resort: try direct tree-sitter with Language
        try:
            from tree_sitter import Language, Parser
            lang_obj = Language('tree-sitter-' + language, language)
            parser = Parser()
            parser.set_language(lang_obj)
            _parser_cache[language] = parser
            return parser
        except Exception:
            return None

    except Exception as e:
        logger.warning(f"Error loading parser for {language}: {e}")
        return None


def _node_to_dict(node: Any) -> Dict[str, Any]:
    """
    Convert a tree-sitter node to a JSON-serializable dict.

    Args:
        node: tree-sitter Node object

    Returns:
        Dict with node metadata
    """
    result = {
        'type': node.type,
        'start_point': list(node.start_point),
        'end_point': list(node.end_point),
        'start_byte': node.start_byte,
        'end_byte': node.end_byte,
    }

    # Add child nodes (limited depth to avoid huge trees)
    if node.child_count > 0:
        result['children'] = [_node_to_dict(child) for child in node.children]
    else:
        result['children'] = []

    return result


def parse_file(filepath: str, language: str) -> Dict[str, Any]:
    """
    Parse a file with tree-sitter.

    Args:
        filepath: Path to file to parse
        language: Programming language name

    Returns:
        Dict with keys:
        - filepath: str (absolute path)
        - language: str
        - root_node: dict (AST structure)
        - error_nodes: list (locations of parse errors)
        - parse_success: bool

    Raises:
        FileNotFoundError: If file not found
        ValueError: If language not supported
    """
    filepath_obj = Path(filepath)
    if not filepath_obj.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    language = language.lower().strip()

    # Get parser
    parser = _get_parser(language)
    if parser is None:
        raise ValueError(
            f"Language '{language}' not supported. "
            "Install tree-sitter-language-pack or tree_sitter_languages."
        )

    # Read file
    try:
        with open(filepath_obj, 'rb') as f:
            file_content = f.read()
    except Exception as e:
        raise IOError(f"Error reading {filepath}: {e}")

    # Parse
    try:
        tree = parser.parse(file_content)
    except Exception as e:
        logger.warning(f"Error parsing {filepath}: {e}")
        return {
            'filepath': str(filepath_obj.absolute()),
            'language': language,
            'root_node': None,
            'error_nodes': [],
            'parse_success': False,
            'error': str(e)
        }

    # Extract error nodes (nodes with type 'ERROR')
    error_nodes = []

    def collect_errors(node: Any):
        if node.type == 'ERROR':
            error_nodes.append({
                'type': 'ERROR',
                'start_point': list(node.start_point),
                'end_point': list(node.end_point),
                'start_byte': node.start_byte,
                'end_byte': node.end_byte,
            })
        for child in node.children:
            collect_errors(child)

    collect_errors(tree.root_node)

    # Build result
    result = {
        'filepath': str(filepath_obj.absolute()),
        'language': language,
        'root_node': _node_to_dict(tree.root_node),
        'error_nodes': error_nodes,
        'parse_success': len(error_nodes) == 0,
    }

    return result


def main():
    """CLI entry point for testing."""
    parser = argparse.ArgumentParser(
        description='Parse a file with tree-sitter'
    )
    parser.add_argument('filepath', help='Path to file to parse')
    parser.add_argument('language', help='Programming language (e.g., python, java)')
    parser.add_argument(
        '--output',
        help='Output file (default: print to stdout)'
    )

    args = parser.parse_args()

    try:
        logger.info(f"Parsing {args.filepath} as {args.language}...")
        result = parse_file(args.filepath, args.language)

        # Output result
        output_str = json.dumps(result, indent=2)
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output_str)
            logger.info(f"Wrote output to {args.output}")
        else:
            print(output_str)

        return 0 if result['parse_success'] else 1

    except Exception as e:
        logger.error(f"Error: {e}")
        print(json.dumps({'error': str(e), 'parse_success': False}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
