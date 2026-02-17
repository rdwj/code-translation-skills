#!/usr/bin/env python3
"""
Two-pass language detection for polyglot codebases.

Pass 1: File extension mapping (.py→Python, .java→Java, etc.)
Pass 2: For ambiguous files (no extension, .h headers), try shebang → identify → pygments

Usage:
  As CLI:
    python3 language_detect.py <codebase_path> [--exclude <patterns>]

  As library:
    from language_detect import detect_languages
    languages, language_map = detect_languages(codebase_path)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Set, Tuple, List
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Extension to language mapping (Pass 1)
EXTENSION_MAP = {
    '.py': 'python',
    '.java': 'java',
    '.js': 'javascript',
    '.ts': 'typescript',
    '.tsx': 'typescript',
    '.c': 'c',
    '.h': 'c',  # Ambiguous, but start with C
    '.cpp': 'cpp',
    '.cc': 'cpp',
    '.cxx': 'cpp',
    '.hpp': 'cpp',
    '.rs': 'rust',
    '.go': 'go',
    '.rb': 'ruby',
    '.sh': 'bash',
    '.pl': 'perl',
    '.php': 'php',
    '.swift': 'swift',
    '.kt': 'kotlin',
    '.scala': 'scala',
    '.groovy': 'groovy',
}

# Directories to skip
SKIP_DIRS = {
    '.git',
    '__pycache__',
    'node_modules',
    'venv',
    '.venv',
    'env',
    '.env',
    'dist',
    'build',
    'eggs',
    '.eggs',
    '*.egg-info',
    '.pytest_cache',
    '.tox',
    'vendor',
    'target',
    'bin',
    'obj',
}


def _should_skip_dir(dir_name: str) -> bool:
    """Check if directory should be skipped."""
    return dir_name in SKIP_DIRS or dir_name.endswith('.egg-info')


def _detect_shebang(filepath: Path) -> str | None:
    """
    Detect language from shebang line.
    Returns language name or None if not detected.
    """
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            first_line = f.readline(256)
            if not first_line.startswith('#!'):
                return None

            shebang = first_line.lower()

            # Map shebang patterns to languages
            if 'python3' in shebang or 'python' in shebang:
                return 'python'
            elif 'node' in shebang or 'js' in shebang:
                return 'javascript'
            elif 'ruby' in shebang:
                return 'ruby'
            elif 'perl' in shebang:
                return 'perl'
            elif 'bash' in shebang or 'sh' in shebang:
                return 'bash'
            elif 'php' in shebang:
                return 'php'
    except Exception as e:
        logger.debug(f"Error reading shebang from {filepath}: {e}")

    return None


def _detect_with_identify(filepath: Path) -> str | None:
    """
    Use 'identify' library for shebang and header detection.
    Returns language name or None if not detected.
    """
    try:
        import identify
        tags = identify.tags_from_path(str(filepath))
        if not tags:
            return None

        # Map identify tags to our language names
        tag = tags[0] if tags else None
        mapping = {
            'python': 'python',
            'java': 'java',
            'javascript': 'javascript',
            'typescript': 'typescript',
            'c': 'c',
            'cpp': 'cpp',
            'rust': 'rust',
            'go': 'go',
            'ruby': 'ruby',
            'perl': 'perl',
            'php': 'php',
            'bash': 'bash',
        }
        return mapping.get(tag)
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"Error with identify for {filepath}: {e}")
        return None


def _detect_with_pygments(filepath: Path) -> str | None:
    """
    Use pygments to guess language from filename and content.
    Last resort for truly ambiguous files.
    """
    try:
        from pygments.lexers import guess_lexer_for_filename
        from pygments.util import ClassNotFound

        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(8192)  # First 8KB

            lexer = guess_lexer_for_filename(str(filepath), content)
            lang_name = lexer.name.lower()

            # Map pygments lexer names to our language names
            mapping = {
                'python': 'python',
                'java': 'java',
                'javascript': 'javascript',
                'typescript': 'typescript',
                'c': 'c',
                'c++': 'cpp',
                'rust': 'rust',
                'go': 'go',
                'ruby': 'ruby',
                'perl': 'perl',
                'php': 'php',
                'bash': 'bash',
            }
            return mapping.get(lang_name)
        except ClassNotFound:
            return None
    except ImportError:
        return None
    except Exception as e:
        logger.debug(f"Error with pygments for {filepath}: {e}")
        return None


def detect_languages(
    codebase_path: str,
    exclude_patterns: List[str] | None = None
) -> Tuple[Set[str], Dict[str, str]]:
    """
    Detect programming languages in codebase.

    Args:
        codebase_path: Root directory to scan
        exclude_patterns: List of glob patterns to exclude

    Returns:
        Tuple of:
        - Set of detected language names
        - Dict mapping filepath → language name
    """
    codebase_path = Path(codebase_path)
    if not codebase_path.is_dir():
        raise ValueError(f"Not a directory: {codebase_path}")

    language_map = {}
    detected_languages = set()
    unknown_count = 0

    # Walk the directory tree
    for root, dirs, files in os.walk(codebase_path):
        # Remove directories to skip (modifies dirs in-place to affect walk)
        dirs[:] = [d for d in dirs if not _should_skip_dir(d)]

        for file in files:
            filepath = Path(root) / file
            rel_path = str(filepath.relative_to(codebase_path))

            # Pass 1: Extension mapping
            ext = filepath.suffix.lower()
            if ext in EXTENSION_MAP:
                lang = EXTENSION_MAP[ext]
                language_map[rel_path] = lang
                detected_languages.add(lang)
                continue

            # Pass 2: Ambiguous files
            detected_lang = None

            # Try shebang first
            detected_lang = _detect_shebang(filepath)
            if detected_lang:
                language_map[rel_path] = detected_lang
                detected_languages.add(detected_lang)
                continue

            # Try identify library
            detected_lang = _detect_with_identify(filepath)
            if detected_lang:
                language_map[rel_path] = detected_lang
                detected_languages.add(detected_lang)
                continue

            # Try pygments as last resort
            detected_lang = _detect_with_pygments(filepath)
            if detected_lang:
                language_map[rel_path] = detected_lang
                detected_languages.add(detected_lang)
                continue

            # Mark as unknown
            language_map[rel_path] = 'unknown'
            unknown_count += 1

    return detected_languages, language_map


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Detect programming languages in a codebase'
    )
    parser.add_argument('codebase_path', help='Root directory of codebase to analyze')
    parser.add_argument(
        '--exclude',
        nargs='+',
        default=[],
        help='Glob patterns to exclude (e.g., "**/vendor/**")'
    )
    parser.add_argument(
        '--output',
        default='language-map.json',
        help='Output file for language map (default: language-map.json)'
    )

    args = parser.parse_args()

    try:
        logger.info(f"Scanning {args.codebase_path}...")
        detected_languages, language_map = detect_languages(
            args.codebase_path,
            exclude_patterns=args.exclude if args.exclude else None
        )

        # Write language map file
        with open(args.output, 'w') as f:
            json.dump(language_map, f, indent=2)
        logger.info(f"Wrote language map to {args.output}")

        # Compute summary statistics
        files_by_language = {}
        for lang in language_map.values():
            files_by_language[lang] = files_by_language.get(lang, 0) + 1

        unknown_count = files_by_language.pop('unknown', 0)

        # Print JSON summary to stdout
        summary = {
            'status': 'success',
            'files_by_language': files_by_language,
            'total_files': len(language_map),
            'unknown_count': unknown_count,
            'detected_languages': sorted(detected_languages)
        }
        print(json.dumps(summary, indent=2))

        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        print(json.dumps({'status': 'error', 'message': str(e)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
