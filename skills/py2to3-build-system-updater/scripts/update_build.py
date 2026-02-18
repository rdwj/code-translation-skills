#!/usr/bin/env python3
"""
Build System Updater: Updates build/packaging infrastructure for Python 3 compatibility.

Scans codebase for setup.py, setup.cfg, pyproject.toml, Dockerfile, Makefile, shell scripts,
and requirements files. Updates distutils→setuptools, version constraints, shebangs, and flags
incompatible dependencies.

Usage:
    python3 update_build.py --codebase-path /path/to/project --target-version 3.12
    python3 update_build.py --codebase-path /path --target-version 3.9 --dry-run
    python3 update_build.py --codebase-path /path --target-version 3.11 --migrate-to-pyproject
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
import ast
from datetime import datetime

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ── JSON Helpers ──
def load_json(filepath: str) -> Dict[str, Any]:
    """Load JSON from file, return empty dict if file doesn't exist."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print(f"Warning: JSON decode error in {filepath}", file=sys.stderr)
        return {}


def save_json(data: Dict[str, Any], filepath: str) -> None:
    """Save dict to JSON file."""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, default=str)


def read_file(filepath: str) -> str:
    """Read file as string."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            return f.read()
    except Exception as e:
        print(f"Warning: Failed to read {filepath}: {e}", file=sys.stderr)
        return ""


def write_file(filepath: str, content: str) -> None:
    """Write string to file, create directories as needed."""
    os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


# ── Build File Discovery ──
def discover_build_files(codebase_path: str) -> Dict[str, List[str]]:
    """Discover all build-related files in codebase."""
    build_files = {
        'setup_py': [],
        'setup_cfg': [],
        'pyproject_toml': [],
        'dockerfile': [],
        'docker_compose': [],
        'makefile': [],
        'shell_scripts': [],
        'requirements': [],
        'pipfile': [],
        'tox_ini': [],
    }

    root = Path(codebase_path)
    if not root.exists():
        print(f"Error: Codebase path {codebase_path} does not exist", file=sys.stderr)
        return build_files

    for item in root.rglob('*'):
        if not item.is_file():
            continue

        name = item.name.lower()
        rel_path = str(item.relative_to(root))

        if name == 'setup.py':
            build_files['setup_py'].append(rel_path)
        elif name == 'setup.cfg':
            build_files['setup_cfg'].append(rel_path)
        elif name == 'pyproject.toml':
            build_files['pyproject_toml'].append(rel_path)
        elif name in ('dockerfile', 'dockerfile.dev', 'dockerfile.prod'):
            build_files['dockerfile'].append(rel_path)
        elif name in ('docker-compose.yml', 'docker-compose.yaml'):
            build_files['docker_compose'].append(rel_path)
        elif name in ('makefile', 'gnumakefile'):
            build_files['makefile'].append(rel_path)
        elif name.endswith('.sh'):
            build_files['shell_scripts'].append(rel_path)
        elif name.startswith('requirements') and name.endswith('.txt'):
            build_files['requirements'].append(rel_path)
        elif name == 'pipfile':
            build_files['pipfile'].append(rel_path)
        elif name == 'tox.ini':
            build_files['tox_ini'].append(rel_path)

    return build_files


# ── setup.py Analysis and Update ──
def analyze_setup_py(filepath: str) -> Dict[str, Any]:
    """Analyze setup.py for distutils usage, version constraints, classifiers."""
    content = read_file(filepath)
    analysis = {
        'filepath': filepath,
        'uses_distutils': False,
        'distutils_imports': [],
        'python_requires': None,
        'classifiers': [],
        'entry_points': {},
        'install_requires': [],
        'issues': [],
    }

    # Check for distutils imports
    distutils_patterns = [
        (r'from\s+distutils\.core\s+import', 'distutils.core'),
        (r'from\s+distutils\.extension\s+import', 'distutils.extension'),
        (r'from\s+distutils\.command', 'distutils.command'),
        (r'import\s+distutils', 'distutils'),
    ]

    for pattern, name in distutils_patterns:
        if re.search(pattern, content):
            analysis['uses_distutils'] = True
            analysis['distutils_imports'].append(name)

    # Parse setup() call arguments using regex (safe approach)
    python_requires_match = re.search(r"python_requires\s*=\s*['\"]([^'\"]+)['\"]", content)
    if python_requires_match:
        analysis['python_requires'] = python_requires_match.group(1)

    # Find classifiers
    classifiers_match = re.search(
        r"classifiers\s*=\s*\[(.*?)\]",
        content,
        re.DOTALL
    )
    if classifiers_match:
        classifier_text = classifiers_match.group(1)
        classifiers = re.findall(r"['\"]([^'\"]+)['\"]", classifier_text)
        analysis['classifiers'] = classifiers

    # Extract install_requires
    install_requires_match = re.search(
        r"install_requires\s*=\s*\[(.*?)\]",
        content,
        re.DOTALL
    )
    if install_requires_match:
        requires_text = install_requires_match.group(1)
        requires = re.findall(r"['\"]([^'\"]+)['\"]", requires_text)
        analysis['install_requires'] = requires

    # Warnings
    if analysis['uses_distutils']:
        analysis['issues'].append({
            'severity': 'critical',
            'message': 'Uses distutils (incompatible with Python 3.12+)',
            'fix': 'Replace with setuptools imports',
        })

    if analysis['python_requires']:
        if '2' in analysis['python_requires']:
            analysis['issues'].append({
                'severity': 'high',
                'message': f'python_requires includes Python 2: {analysis["python_requires"]}',
                'fix': 'Update to Python 3-only constraint',
            })

    py2_classifiers = [c for c in analysis['classifiers'] if 'Python :: 2' in c]
    if py2_classifiers:
        analysis['issues'].append({
            'severity': 'medium',
            'message': f'Contains {len(py2_classifiers)} Python 2 classifiers',
            'fix': 'Remove Python 2.x classifiers, add target version',
        })

    return analysis


def update_setup_py(filepath: str, target_version: str, dry_run: bool = False) -> Tuple[str, List[str]]:
    """Update setup.py for Python 3 compatibility."""
    content = read_file(filepath)
    original = content
    changes = []

    # Replace distutils.core → setuptools
    if 'from distutils.core import setup' in content:
        content = content.replace(
            'from distutils.core import setup',
            'from setuptools import setup'
        )
        changes.append('Replaced distutils.core → setuptools')

    # Replace distutils.extension → setuptools
    if 'from distutils.extension import Extension' in content:
        content = content.replace(
            'from distutils.extension import Extension',
            'from setuptools import Extension'
        )
        changes.append('Replaced distutils.extension → setuptools')

    # Replace distutils.command → setuptools.command
    distutils_cmd_patterns = [
        (r'from distutils\.command\.build_ext import build_ext', 'from setuptools.command.build_ext import build_ext'),
        (r'from distutils\.command\.build import build', 'from setuptools.command.build import build'),
    ]
    for pattern, replacement in distutils_cmd_patterns:
        if re.search(pattern, content):
            content = re.sub(pattern, replacement, content)
            changes.append(f'Updated distutils.command import')

    # Update python_requires
    py_ver_short = target_version.replace('.', '')[:2]  # e.g., '3.12' → '31'
    min_ver = target_version.split('.')[0] + '.' + target_version.split('.')[1]

    old_requires = re.search(r"python_requires\s*=\s*['\"]([^'\"]+)['\"]", content)
    if old_requires:
        old_val = old_requires.group(1)
        if '2' in old_val or old_val != f'>={min_ver}':
            new_requires = f'python_requires=">={min_ver}"'
            content = re.sub(
                r"python_requires\s*=\s*['\"][^'\"]+['\"]",
                new_requires,
                content
            )
            changes.append(f'Updated python_requires to {new_requires}')
    else:
        # Add python_requires if missing
        setup_match = re.search(r'setup\s*\(', content)
        if setup_match:
            insert_pos = setup_match.end()
            indent = '    '
            new_line = f'\n{indent}python_requires=">={min_ver}",'
            content = content[:insert_pos] + new_line + content[insert_pos:]
            changes.append(f'Added python_requires=">={min_ver}"')

    # Update classifiers (remove Py2, add target version)
    if 'classifiers' in content:
        # Remove Python 2.x classifiers
        content = re.sub(r"\s*['\"]Programming Language :: Python :: 2[^\]]*['\"],?\n?", '', content)
        changes.append('Removed Python 2.x classifiers')

        # Add target version classifier if missing
        target_classifier = f'Programming Language :: Python :: {target_version}'
        if target_classifier not in content:
            # Find classifiers list and add before closing bracket
            classifiers_end = re.search(r"(\s+\]\s*,?)\s*\n", content)
            if classifiers_end:
                insert_text = f',\n        "{target_classifier}"'
                content = content[:classifiers_end.start()] + insert_text + content[classifiers_end.start():]
                changes.append(f'Added {target_classifier} classifier')

    if not dry_run and content != original:
        write_file(filepath, content)

    return (content if dry_run else original, changes)


# ── Dockerfile Updates ──
def update_dockerfile(filepath: str, target_version: str, dry_run: bool = False) -> Tuple[str, List[str]]:
    """Update Dockerfile FROM python:X to python3.X."""
    content = read_file(filepath)
    original = content
    changes = []

    # FROM python:2 → FROM python:3.X
    py2_pattern = r'FROM\s+python:2'
    if re.search(py2_pattern, content):
        # Extract just major.minor version
        ver_digits = target_version.replace('.', '')
        new_from = f'FROM python:{target_version}'
        content = re.sub(py2_pattern, new_from, content, flags=re.IGNORECASE)
        changes.append(f'Updated FROM python:2 → {new_from}')

    # Also handle python:latest that might be intended for Py2
    # (only update if python_requires explicitly stated as Py2)

    if not dry_run and content != original:
        write_file(filepath, content)

    return (content if dry_run else original, changes)


# ── Shebang and CLI Updates ──
def update_shebangs_and_cli(filepath: str, dry_run: bool = False) -> Tuple[str, List[str]]:
    """Update shebang lines and python CLI references."""
    content = read_file(filepath)
    original = content
    changes = []

    # Update shebangs
    shebang_patterns = [
        (r'^#!/usr/bin/env python$', '#!/usr/bin/env python3'),
        (r'^#!/usr/bin/python$', '#!/usr/bin/python3'),
        (r'^#!/usr/bin/python2', '#!/usr/bin/python3'),
    ]

    for pattern, replacement in shebang_patterns:
        if re.search(pattern, content, re.MULTILINE):
            content = re.sub(pattern, replacement, content, flags=re.MULTILINE)
            changes.append(f'Updated shebang {pattern} → {replacement}')

    # In Makefiles: python → python3 (if not variable)
    if filepath.lower().endswith('makefile') or filepath.lower().endswith('gnumakefile'):
        # Replace 'python ' with 'python3 ' (not in variable assignments)
        makefile_patterns = [
            (r'\b(?<![\"\'$])python\s+', 'python3 '),  # standalone python command
        ]
        for pattern, replacement in makefile_patterns:
            if re.search(pattern, content):
                content = re.sub(pattern, replacement, content)
                changes.append(f'Updated Makefile python → python3')

    if not dry_run and content != original:
        write_file(filepath, content)

    return (content if dry_run else original, changes)


# ── Dependency Version Analysis ──
def analyze_requirements(filepath: str) -> List[Dict[str, str]]:
    """Analyze requirements.txt for version concerns."""
    content = read_file(filepath)
    concerns = []

    for line in content.split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue

        # Parse package specification
        pkg_match = re.match(r'^([a-zA-Z0-9_-]+)(.*)$', line)
        if not pkg_match:
            continue

        pkg_name = pkg_match.group(1)
        version_spec = pkg_match.group(2).strip()

        # Flag pinned versions that may have Python 3 issues
        if '==' in version_spec or ('>=' in version_spec and '<=' in version_spec):
            concerns.append({
                'package': pkg_name,
                'spec': version_spec,
                'concern': 'Pinned version - verify Python 3 compatibility manually',
            })

    return concerns


# ── Main Orchestration ──
@log_execution
def main():
    parser = argparse.ArgumentParser(
        description='Update build infrastructure for Python 3 compatibility',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--codebase-path',
        required=True,
        help='Root directory of Python project'
    )
    parser.add_argument(
        '--target-version',
        required=True,
        choices=['3.9', '3.10', '3.11', '3.12', '3.13'],
        help='Target Python version'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying files'
    )
    parser.add_argument(
        '--migrate-to-pyproject',
        action='store_true',
        help='Generate pyproject.toml from setup.py'
    )
    parser.add_argument(
        '--output-dir',
        default=None,
        help='Output directory for reports (default: codebase root)'
    )

    args = parser.parse_args()

    codebase_path = os.path.abspath(args.codebase_path)
    output_dir = os.path.abspath(args.output_dir or codebase_path)
    target_version = args.target_version
    dry_run = args.dry_run

    # Initialize report structure
    report = {
        'timestamp': datetime.now().isoformat(),
        'codebase_path': codebase_path,
        'target_version': target_version,
        'dry_run': dry_run,
        'discovered_files': {},
        'updates': {},
        'dependency_concerns': [],
        'summary': {},
    }

    print(f"Scanning {codebase_path} for build files...", file=sys.stderr)

    # Discover build files
    build_files = discover_build_files(codebase_path)
    report['discovered_files'] = {
        k: len(v) for k, v in build_files.items() if v
    }

    modified_files = []

    # Process setup.py files
    for rel_path in build_files['setup_py']:
        abs_path = os.path.join(codebase_path, rel_path)
        print(f"Analyzing {rel_path}...", file=sys.stderr)

        analysis = analyze_setup_py(abs_path)
        updated_content, changes = update_setup_py(abs_path, target_version, dry_run)

        if changes:
            report['updates'][rel_path] = {
                'type': 'setup.py',
                'analysis': analysis,
                'changes': changes,
            }
            if not dry_run:
                modified_files.append(rel_path)

    # Process Dockerfiles
    for rel_path in build_files['dockerfile']:
        abs_path = os.path.join(codebase_path, rel_path)
        print(f"Analyzing {rel_path}...", file=sys.stderr)

        updated_content, changes = update_dockerfile(abs_path, target_version, dry_run)
        if changes:
            report['updates'][rel_path] = {
                'type': 'dockerfile',
                'changes': changes,
            }
            if not dry_run:
                modified_files.append(rel_path)

    # Process shell scripts and Makefiles (shebangs)
    for rel_path in build_files['shell_scripts'] + build_files['makefile']:
        abs_path = os.path.join(codebase_path, rel_path)
        print(f"Analyzing {rel_path}...", file=sys.stderr)

        updated_content, changes = update_shebangs_and_cli(abs_path, dry_run)
        if changes:
            report['updates'][rel_path] = {
                'type': 'script' if rel_path.endswith('.sh') else 'makefile',
                'changes': changes,
            }
            if not dry_run:
                modified_files.append(rel_path)

    # Analyze requirements files
    for rel_path in build_files['requirements']:
        abs_path = os.path.join(codebase_path, rel_path)
        print(f"Analyzing {rel_path}...", file=sys.stderr)

        concerns = analyze_requirements(abs_path)
        if concerns:
            report['dependency_concerns'].extend([
                {
                    'file': rel_path,
                    **concern
                }
                for concern in concerns
            ])

    # Generate reports
    report['summary'] = {
        'total_build_files': sum(len(v) for v in build_files.values()),
        'files_updated': len(report['updates']),
        'dependency_concerns': len(report['dependency_concerns']),
        'dry_run_mode': dry_run,
    }

    # Save JSON report
    report_path = os.path.join(output_dir, 'build-system-report.json')
    save_json(report, report_path)
    print(f"Report saved to {report_path}", file=sys.stderr)

    # Save dependency report
    dep_report = {
        'timestamp': report['timestamp'],
        'target_version': target_version,
        'concerns': report['dependency_concerns'],
    }
    dep_path = os.path.join(output_dir, 'dependency-compatibility.json')
    save_json(dep_report, dep_path)
    print(f"Dependency report saved to {dep_path}", file=sys.stderr)

    print(f"Processed {report['summary']['total_build_files']} build files", file=sys.stderr)
    print(f"Updates: {report['summary']['files_updated']}", file=sys.stderr)

    return 0
