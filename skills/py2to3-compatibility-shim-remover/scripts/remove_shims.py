#!/usr/bin/env python3
"""
Compatibility Shim Remover — Main Removal Script

Removes dual-compatibility code from Python 2/3 mixed codebase after successful
Py3 cutover. Removes __future__ imports, six usage, python-future shims,
version guards, and try-except import patterns.

Usage:
    python3 remove_shims.py <codebase_path> \
        --target-version 3.11 \
        --output ./cleaned/ \
        --dry-run \
        --test-command "pytest -xvs"

Output:
    shim-removal-report.json — Detailed removal statistics
    shim-removal-report.md — Human-readable report
    shim-removal-diff.patch — Unified diff (if dry-run)
    Modified .py files (if not dry-run)
"""

import ast
import json
import os
import re
import sys
import argparse
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from collections import defaultdict

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ── Helper Functions ──────────────────────────────────────────────────────────

def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def save_json(data: Dict[str, Any], path: str) -> None:
    """Save data to JSON file."""
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def read_file(path: str) -> str:
    """Read file contents."""
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return ""


def write_file(path: str, content: str) -> None:
    """Write content to file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


# ── Removal Patterns ──────────────────────────────────────────────────────────

class ShimRemover:
    """Removes compatibility shims from Python code."""

    def __init__(self, target_version: str = "3.11"):
        self.target_version = target_version
        self.removals = defaultdict(int)
        self.changes = []

    def remove_future_imports(self, content: str) -> str:
        """Remove __future__ imports (except annotations for older targets)."""
        lines = content.split('\n')
        result = []
        keep_annotations = self.target_version < "3.14"

        for line in lines:
            # Match: from __future__ import ...
            if re.match(r'\s*from __future__ import', line):
                # If it has annotations and we need to keep it, keep it
                if 'annotations' in line and keep_annotations:
                    result.append(line)
                else:
                    self.removals['future_imports'] += 1
                    self.changes.append({
                        'type': 'remove_future_import',
                        'line': line.strip()
                    })
            else:
                result.append(line)

        return '\n'.join(result)

    def replace_six_types(self, content: str) -> str:
        """Replace six type checks with Py3 equivalents."""
        # six.text_type → str
        content = re.sub(
            r'six\.text_type',
            'str',
            content
        )
        if 'six.text_type' in content:
            self.removals['six_text_type'] += 1

        # six.binary_type → bytes
        content = re.sub(
            r'six\.binary_type',
            'bytes',
            content
        )
        if 'six.binary_type' in content:
            self.removals['six_binary_type'] += 1

        # six.string_types → (str,)
        content = re.sub(
            r'six\.string_types',
            '(str,)',
            content
        )
        if 'six.string_types' in content:
            self.removals['six_string_types'] += 1

        # six.integer_types → (int,)
        content = re.sub(
            r'six\.integer_types',
            '(int,)',
            content
        )
        if 'six.integer_types' in content:
            self.removals['six_integer_types'] += 1

        return content

    def replace_six_iteration(self, content: str) -> str:
        """Replace six iteration methods with Py3 equivalents."""
        # six.iteritems(d) → d.items()
        pattern = r'six\.iteritems\((\w+)\)'
        if re.search(pattern, content):
            content = re.sub(pattern, r'\1.items()', content)
            self.removals['six_iteritems'] += 1

        # six.itervalues(d) → d.values()
        pattern = r'six\.itervalues\((\w+)\)'
        if re.search(pattern, content):
            content = re.sub(pattern, r'\1.values()', content)
            self.removals['six_itervalues'] += 1

        # six.iterkeys(d) → d.keys()
        pattern = r'six\.iterkeys\((\w+)\)'
        if re.search(pattern, content):
            content = re.sub(pattern, r'\1.keys()', content)
            self.removals['six_iterkeys'] += 1

        return content

    def replace_six_moves(self, content: str) -> str:
        """Replace six.moves imports with Py3 equivalents."""
        # from six.moves import range → (delete line)
        lines = content.split('\n')
        result = []

        for line in lines:
            if 'from six.moves import' in line:
                # Extract what's being imported
                match = re.search(r'from six\.moves import (.+)', line)
                if match:
                    imports = match.group(1).split(',')
                    imports = [i.strip() for i in imports]

                    # Built-ins that don't need imports
                    builtins = {'range', 'input', 'zip', 'map', 'filter', 'bytes',
                               'str', 'dict', 'list', 'int', 'float'}

                    # urllib.* stays as is
                    urllib_imports = [i for i in imports if 'urllib' in i]
                    other_imports = [i for i in imports if 'urllib' not in i and i not in builtins]

                    # If there are urllib imports, keep them
                    if urllib_imports:
                        result.append(f"from urllib.parse import {', '.join(urllib_imports)}")
                    # If there are other non-builtin imports, keep them
                    elif other_imports:
                        result.append(f"from {', '.join(other_imports)} import")

                    self.removals['six_moves_imports'] += 1
                else:
                    result.append(line)
            else:
                result.append(line)

        return '\n'.join(result)

    def replace_six_ensure(self, content: str) -> str:
        """Replace six.ensure_* functions with Py3 equivalents."""
        # six.ensure_str(s) → str(s)
        if 'six.ensure_str' in content:
            content = re.sub(
                r'six\.ensure_str\(([^)]+)\)',
                r'str(\1)',
                content
            )
            self.removals['six_ensure_str'] += 1

        # six.ensure_text(s) → str(s)
        if 'six.ensure_text' in content:
            content = re.sub(
                r'six\.ensure_text\(([^)]+)\)',
                r'str(\1)',
                content
            )
            self.removals['six_ensure_text'] += 1

        return content

    def replace_six_version_checks(self, content: str) -> str:
        """Replace six.PY2 / six.PY3 with Py3 equivalents."""
        # six.PY2 → False
        if 'six.PY2' in content:
            content = content.replace('six.PY2', 'False')
            self.removals['six_py2'] += 1

        # six.PY3 → True
        if 'six.PY3' in content:
            content = content.replace('six.PY3', 'True')
            self.removals['six_py3'] += 1

        # Simplify: if False: ... else: ... → remove if block, keep else
        # Simplify: if True: ... else: ... → remove else block, keep if
        lines = content.split('\n')
        result = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Pattern: if False: ... else: ...
            if re.match(r'\s*if False:', line):
                # Skip until else (handle indentation)
                indent = len(line) - len(line.lstrip())
                i += 1
                while i < len(lines):
                    if re.match(rf'^{" " * indent}else:', lines[i]):
                        i += 1
                        break
                    i += 1
                # Keep lines after else
                continue

            # Pattern: if True: ... else: ...
            elif re.match(r'\s*if True:', line):
                # Replace if True: with no indent change
                result.append(line.replace('if True:', '').lstrip())
                i += 1
                while i < len(lines):
                    if re.match(rf'^{" " * indent}else:', lines[i]):
                        i += 1
                        break
                    result.append(lines[i])
                    i += 1
                continue

            else:
                result.append(line)
                i += 1

        return '\n'.join(result)

    def replace_six_metaclass(self, content: str) -> str:
        """Replace six.add_metaclass decorator with Py3 syntax."""
        lines = content.split('\n')
        result = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Match: @six.add_metaclass(MetaClass)
            match = re.match(r'^(\s*)@six\.add_metaclass\((.+?)\)', line)
            if match:
                indent = match.group(1)
                metaclass = match.group(2)
                self.removals['six_metaclass'] += 1

                # Remove decorator line
                i += 1

                # Next line should be: class ClassName:
                if i < len(lines):
                    class_line = lines[i]
                    # Replace: class X: → class X(metaclass=Meta):
                    class_match = re.match(r'(\s*class \w+)\s*(\([^)]*\))?\s*:', class_line)
                    if class_match:
                        class_def = class_match.group(1)
                        bases = class_match.group(2) or ''

                        # Insert metaclass
                        if bases and bases.strip() != '()':
                            # Already has bases
                            new_class = f"{class_def}{bases[:-1]}, metaclass={metaclass}):"
                        else:
                            new_class = f"{class_def}(metaclass={metaclass}):"

                        result.append(new_class)
                        i += 1
                    else:
                        result.append(class_line)
                        i += 1
            else:
                result.append(line)
                i += 1

        return '\n'.join(result)

    def replace_six_unicode_decorator(self, content: str) -> str:
        """Remove @six.python_2_unicode_compatible decorator."""
        if '@six.python_2_unicode_compatible' in content:
            content = re.sub(
                r'@six\.python_2_unicode_compatible\n',
                '',
                content
            )
            self.removals['six_unicode_decorator'] += 1

        return content

    def remove_future_imports_module(self, content: str) -> str:
        """Remove 'from __future__' style imports from future module."""
        lines = content.split('\n')
        result = []

        for line in lines:
            if re.match(r'\s*from (builtins|past|future) import', line):
                self.removals['future_module_imports'] += 1
            else:
                result.append(line)

        return '\n'.join(result)

    def collapse_version_guards(self, content: str) -> str:
        """Collapse sys.version_info guards to Py3 branch."""
        lines = content.split('\n')
        result = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Pattern: if sys.version_info[0] == 2: ... else: ...
            # or: if sys.version_info < (3, ...): ... else: ...
            if re.search(r'if sys\.version_info', line):
                # Check if it's a Py2 check
                if ('== 2' in line or '< (3' in line or '[0] < 3' in line or
                    'version_info < 3' in line):

                    indent = len(line) - len(line.lstrip())
                    self.removals['version_guards'] += 1

                    # Skip Py2 branch (find else)
                    i += 1
                    while i < len(lines):
                        if re.match(rf'^{" " * indent}else:', lines[i]):
                            i += 1
                            break
                        i += 1

                    # Keep Py3 branch (decrease indent)
                    while i < len(lines):
                        next_line = lines[i]
                        next_indent = len(next_line) - len(next_line.lstrip())
                        # Check if still in else block
                        if next_line.strip() and next_indent == indent:
                            break
                        # Remove indentation added by else
                        if next_line.strip():
                            unindented = next_line[indent + 4:]
                            result.append(unindented)
                        else:
                            result.append(next_line)
                        i += 1
                else:
                    result.append(line)
                    i += 1
            else:
                result.append(line)
                i += 1

        return '\n'.join(result)

    def collapse_import_guards(self, content: str) -> str:
        """Collapse try-except import patterns to Py3 imports."""
        lines = content.split('\n')
        result = []
        i = 0

        while i < len(lines):
            line = lines[i]

            # Pattern: try: import X except ImportError: import Y
            if line.strip().startswith('try:'):
                # Look for import
                if i + 1 < len(lines) and 'import' in lines[i + 1]:
                    import_line = lines[i + 1]

                    # Look for except ImportError
                    if i + 2 < len(lines) and 'except ImportError' in lines[i + 2]:
                        # Look for fallback import
                        if i + 3 < len(lines) and 'import' in lines[i + 3]:
                            py3_import = import_line.strip()
                            py2_import = lines[i + 3].strip()

                            # Keep Py3 import, skip Py2
                            result.append(import_line.rstrip())
                            self.removals['import_guards'] += 1
                            i += 4
                            continue

            result.append(line)
            i += 1

        return '\n'.join(result)

    def remove_six_from_imports(self, content: str) -> str:
        """Remove six from import lines if it's only import."""
        lines = content.split('\n')
        result = []

        for line in lines:
            if 'import six' in line and 'from' not in line:
                # Skip plain "import six"
                self.removals['six_imports'] += 1
                continue
            result.append(line)

        return '\n'.join(result)

    def process_file(self, filepath: str) -> Tuple[str, Dict[str, Any]]:
        """Process a single file, remove all shims."""
        content = read_file(filepath)
        original = content

        # Apply removals in order
        content = self.remove_future_imports(content)
        content = self.remove_six_from_imports(content)
        content = self.replace_six_types(content)
        content = self.replace_six_iteration(content)
        content = self.replace_six_moves(content)
        content = self.replace_six_ensure(content)
        content = self.replace_six_version_checks(content)
        content = self.replace_six_metaclass(content)
        content = self.replace_six_unicode_decorator(content)
        content = self.remove_future_imports_module(content)
        content = self.collapse_version_guards(content)
        content = self.collapse_import_guards(content)

        # Count changes
        changes = sum(self.removals.values())

        return content, {
            'filepath': filepath,
            'changes': changes,
            'removals': dict(self.removals)
        }


# ── File Discovery ───────────────────────────────────────────────────────────

def find_python_files(codebase_path: str, modules: Optional[List[str]] = None) -> List[str]:
    """Find all Python files to process."""
    python_files = []

    for root, dirs, files in os.walk(codebase_path):
        # Skip hidden directories, venv, build artifacts
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in
                  ['__pycache__', 'venv', 'env', 'build', 'dist', '*.egg-info']]

        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)

                # Filter by module if specified
                if modules:
                    if any(m in filepath for m in modules):
                        python_files.append(filepath)
                else:
                    python_files.append(filepath)

    return sorted(python_files)


# ── Requirements File Processing ──────────────────────────────────────────────

def remove_from_requirements(codebase_path: str, output_dir: str, dry_run: bool) -> Dict[str, Any]:
    """Remove six and future from requirements files."""
    results = {
        'requirements_txt': False,
        'setup_py': False,
        'pyproject_toml': False,
        'setup_cfg': False
    }

    # requirements.txt
    req_path = os.path.join(codebase_path, 'requirements.txt')
    if os.path.exists(req_path):
        content = read_file(req_path)
        lines = content.split('\n')
        filtered = [l for l in lines if 'six' not in l.lower() and 'future' not in l.lower()]
        new_content = '\n'.join(filtered)

        if new_content != content:
            if not dry_run:
                write_file(os.path.join(output_dir, 'requirements.txt'), new_content)
            results['requirements_txt'] = True

    # setup.py
    setup_path = os.path.join(codebase_path, 'setup.py')
    if os.path.exists(setup_path):
        content = read_file(setup_path)
        # Remove six and future from install_requires
        content = re.sub(
            r',?\s*["\']six[^"\']*["\']',
            '',
            content,
            flags=re.IGNORECASE
        )
        content = re.sub(
            r',?\s*["\']python-future[^"\']*["\']',
            '',
            content,
            flags=re.IGNORECASE
        )
        content = re.sub(
            r',?\s*["\']future[^"\']*["\']',
            '',
            content,
            flags=re.IGNORECASE
        )
        original = read_file(setup_path)
        if content != original:
            if not dry_run:
                write_file(os.path.join(output_dir, 'setup.py'), content)
            results['setup_py'] = True

    # pyproject.toml
    pyproject_path = os.path.join(codebase_path, 'pyproject.toml')
    if os.path.exists(pyproject_path):
        content = read_file(pyproject_path)
        content = re.sub(
            r',?\s*"six[^"]*"',
            '',
            content,
            flags=re.IGNORECASE
        )
        content = re.sub(
            r',?\s*"python-future[^"]*"',
            '',
            content,
            flags=re.IGNORECASE
        )
        original = read_file(pyproject_path)
        if content != original:
            if not dry_run:
                write_file(os.path.join(output_dir, 'pyproject.toml'), content)
            results['pyproject_toml'] = True

    return results


# ── Test Execution ───────────────────────────────────────────────────────────

def run_tests(test_command: str) -> Tuple[bool, str]:
    """Run test command, return success and output."""
    try:
        result = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            timeout=300,
            text=True
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


# ── Main Processing ──────────────────────────────────────────────────────────

def process_codebase(
    codebase_path: str,
    target_version: str,
    output_dir: str,
    dry_run: bool = False,
    modules: Optional[List[str]] = None,
    test_command: Optional[str] = None,
    batch_size: int = 10
) -> Dict[str, Any]:
    """Main processing function."""

    os.makedirs(output_dir, exist_ok=True)

    # Find all Python files
    python_files = find_python_files(codebase_path, modules)

    if not python_files:
        print("Error: No Python files found", file=sys.stderr)
        return {}

    print(f"Found {len(python_files)} Python files to process")

    # Process files
    all_removals = defaultdict(int)
    file_reports = []
    batch_results = []
    failed_files = []

    for batch_num, i in enumerate(range(0, len(python_files), batch_size), 1):
        batch = python_files[i:i + batch_size]
        print(f"\nBatch {batch_num}: Processing {len(batch)} files...")

        batch_removals = 0

        for filepath in batch:
            remover = ShimRemover(target_version)
            new_content, report = remover.process_file(filepath)

            file_reports.append(report)
            batch_removals += report['changes']

            # Accumulate removals
            for key, val in report['removals'].items():
                all_removals[key] += val

            # Write output file (if not dry run)
            if not dry_run and new_content != read_file(filepath):
                rel_path = os.path.relpath(filepath, codebase_path)
                output_path = os.path.join(output_dir, rel_path)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                write_file(output_path, new_content)

        # Run tests after batch
        if test_command:
            print(f"  Running tests...")
            success, output = run_tests(test_command)
            batch_results.append({
                'batch': batch_num,
                'success': success,
                'output': output[-500:] if len(output) > 500 else output
            })

            if not success:
                print(f"  ✗ Tests FAILED in batch {batch_num}")
                failed_files.extend(batch)
            else:
                print(f"  ✓ Tests passed")

    # Remove from requirements
    req_results = remove_from_requirements(codebase_path, output_dir, dry_run)

    report = {
        'metadata': {
            'codebase_path': codebase_path,
            'target_version': target_version,
            'dry_run': dry_run,
            'python_files_processed': len(python_files),
            'files_modified': len([r for r in file_reports if r['changes'] > 0])
        },
        'removal_summary': dict(all_removals),
        'total_removals': sum(all_removals.values()),
        'per_file_changes': file_reports,
        'batch_test_results': batch_results,
        'failed_files': failed_files,
        'requirements_cleanup': req_results
    }

    return report


@log_execution
def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Remove compatibility shims from Py2/Py3 dual-compatible codebase"
    )
    parser.add_argument('codebase_path', help='Root directory of codebase')
    parser.add_argument('--target-version', default='3.11',
                       help='Python 3 target version (3.9, 3.11, 3.12, 3.13)')
    parser.add_argument('--output', default='.',
                       help='Output directory for modified files')
    parser.add_argument('--dry-run', action='store_true',
                       help='Show what would be changed without modifying files')
    parser.add_argument('--modules', help='Comma-separated modules to process')
    parser.add_argument('--test-command', help='Command to run tests after each batch')
    parser.add_argument('--batch-size', type=int, default=10,
                       help='Number of files per batch before testing')

    args = parser.parse_args()

    if not os.path.isdir(args.codebase_path):
        print(f"Error: {args.codebase_path} is not a valid directory", file=sys.stderr)
        sys.exit(1)

    modules = args.modules.split(',') if args.modules else None

    print(f"Removing compatibility shims from {args.codebase_path}...")
    print(f"Target Python version: {args.target_version}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'PRODUCTION'}")

    report = process_codebase(
        args.codebase_path,
        args.target_version,
        args.output,
        args.dry_run,
        modules,
        args.test_command,
        args.batch_size
    )

    # Save report
    save_json(report, os.path.join(args.output, 'shim-removal-report.json'))
    print(f"\n✓ Processed {report['metadata']['python_files_processed']} Python files")
    print(f"✓ Total removals: {report['total_removals']}")
    print(f"✓ Report saved to {args.output}/shim-removal-report.json")


if __name__ == '__main__':
    main()
