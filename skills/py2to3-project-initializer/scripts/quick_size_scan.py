#!/usr/bin/env python3
"""
Script: quick_size_scan.py
Purpose: Fast project sizing scan to determine Express/Standard/Full workflow.
         Runs in seconds, not minutes. Zero LLM tokens.
Inputs:  Project root directory
Outputs: Sizing report (JSON to stdout, optional file)
LLM involvement: NONE
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# Complexity escalators — patterns that bump a project up one tier
COMPLEXITY_ESCALATORS = {
    "c_extensions": {
        "file_patterns": ["*.so", "*.pyd", "*.c", "*.h", "*.pyx"],
        "code_patterns": [
            r"from\s+ctypes\s+import",
            r"import\s+ctypes",
            r"from\s+cffi\s+import",
            r"import\s+cffi",
            r"from\s+Cython",
            r"import\s+swig",
        ],
        "build_patterns": [
            r"ext_modules",
            r"Extension\(",
            r"cythonize\(",
        ],
        "description": "C extensions, ctypes, CFFI, or Cython usage",
    },
    "binary_protocols": {
        "file_patterns": [],
        "code_patterns": [
            r"struct\.pack",
            r"struct\.unpack",
            r"socket\.recv",
            r"socket\.send",
            r"serial\.Serial",
            r"modbus",
            r"EBCDIC|cp500|cp1047",
        ],
        "build_patterns": [],
        "description": "Binary protocols, Modbus, EBCDIC, or socket I/O",
    },
    "pickle_marshal": {
        "file_patterns": ["*.pkl", "*.pickle", "*.marshal"],
        "code_patterns": [
            r"pickle\.dump",
            r"pickle\.load",
            r"cPickle",
            r"marshal\.dump",
            r"marshal\.load",
            r"shelve\.open",
        ],
        "build_patterns": [],
        "description": "Pickle, marshal, or shelve with persisted data files",
    },
    "zero_tests": {
        "file_patterns": [],
        "code_patterns": [],
        "build_patterns": [],
        "description": "No test files found (no safety net for migration)",
    },
}

# High-risk Py2 pattern quick-detect (not exhaustive, just for sizing)
PY2_QUICK_PATTERNS = {
    "print_statement": r'^\s*print\s+["\']',
    "except_comma": r"except\s+\w+\s*,\s*\w+",
    "has_key": r"\.has_key\s*\(",
    "xrange": r"\bxrange\s*\(",
    "raw_input": r"\braw_input\s*\(",
    "unicode_call": r"\bunicode\s*\(",
    "long_suffix": r"\b\d+[lL]\b",
    "iteritems": r"\.(iteritems|itervalues|iterkeys)\s*\(",
    "dict_keys_index": r"\.keys\(\)\s*\[",
    "exec_statement": r"^\s*exec\s+",
    "raise_string": r'raise\s+["\']',
    "backtick_repr": r"`[^`]+`",
    "oldstyle_class": r"^class\s+\w+\s*:",
    "metaclass_attr": r"__metaclass__\s*=",
    "division_int": r"__div__\s*\(",
    "encode_decode": r"\.(encode|decode)\s*\(",
    "bytes_str_mix": r'b["\'].*?["\'].*?["\']|["\'].*?b["\']',
}


def count_files_and_loc(project_root, exclude_patterns=None):
    """Count Python files and lines of code."""
    exclude_patterns = exclude_patterns or []
    py_files = []
    total_loc = 0
    all_files = []

    for root, dirs, files in os.walk(project_root):
        # Skip hidden dirs, __pycache__, venv, node_modules
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d != "__pycache__"
            and d not in ("venv", "env", ".venv", "node_modules", ".git")
        ]

        rel_root = os.path.relpath(root, project_root)
        skip = False
        for pattern in exclude_patterns:
            if re.match(pattern.replace("**/", ".*").replace("*", ".*"), rel_root):
                skip = True
                break
        if skip:
            continue

        for f in files:
            filepath = os.path.join(root, f)
            all_files.append(filepath)

            if f.endswith(".py"):
                py_files.append(filepath)
                try:
                    with open(filepath, "r", errors="replace") as fh:
                        total_loc += sum(
                            1
                            for line in fh
                            if line.strip() and not line.strip().startswith("#")
                        )
                except (IOError, OSError):
                    pass

    return py_files, total_loc, all_files


def detect_test_files(py_files):
    """Find test files."""
    test_files = []
    for f in py_files:
        basename = os.path.basename(f)
        dirname = os.path.basename(os.path.dirname(f))
        if (
            basename.startswith("test_")
            or basename.endswith("_test.py")
            or basename == "conftest.py"
            or dirname in ("tests", "test")
        ):
            test_files.append(f)
    return test_files


def check_complexity_escalators(project_root, py_files, all_files, test_files):
    """Check for complexity escalators that bump project up one tier."""
    escalators_found = []

    for name, config in COMPLEXITY_ESCALATORS.items():
        if name == "zero_tests":
            if len(test_files) == 0:
                escalators_found.append(
                    {"name": name, "description": config["description"], "evidence": "No test files found"}
                )
            continue

        evidence = []

        # Check file patterns
        for pattern in config["file_patterns"]:
            for f in all_files:
                if Path(f).match(pattern):
                    evidence.append(f"File: {os.path.relpath(f, project_root)}")
                    if len(evidence) >= 3:
                        break
            if len(evidence) >= 3:
                break

        # Check code patterns in Python files
        for f in py_files:
            try:
                with open(f, "r", errors="replace") as fh:
                    content = fh.read()
                for pat in config["code_patterns"]:
                    if re.search(pat, content, re.IGNORECASE):
                        evidence.append(
                            f"Pattern '{pat}' in {os.path.relpath(f, project_root)}"
                        )
                        if len(evidence) >= 5:
                            break
            except (IOError, OSError):
                pass
            if len(evidence) >= 5:
                break

        # Check build file patterns
        build_files = [
            f
            for f in all_files
            if os.path.basename(f)
            in ("setup.py", "setup.cfg", "pyproject.toml", "Makefile", "CMakeLists.txt")
        ]
        for f in build_files:
            try:
                with open(f, "r", errors="replace") as fh:
                    content = fh.read()
                for pat in config["build_patterns"]:
                    if re.search(pat, content):
                        evidence.append(
                            f"Build pattern '{pat}' in {os.path.relpath(f, project_root)}"
                        )
            except (IOError, OSError):
                pass

        if evidence:
            escalators_found.append(
                {
                    "name": name,
                    "description": config["description"],
                    "evidence": evidence[:5],
                }
            )

    return escalators_found


def quick_pattern_scan(py_files, project_root):
    """Fast pattern scan for Py2-isms. Not exhaustive — just for sizing."""
    pattern_counts = {name: 0 for name in PY2_QUICK_PATTERNS}
    files_with_patterns = set()
    semantic_count = 0
    syntax_count = 0

    semantic_patterns = {
        "encode_decode", "bytes_str_mix", "dict_keys_index",
        "unicode_call", "metaclass_attr", "division_int",
    }

    for f in py_files:
        try:
            with open(f, "r", errors="replace") as fh:
                content = fh.read()
            file_had_pattern = False
            for name, pattern in PY2_QUICK_PATTERNS.items():
                matches = len(re.findall(pattern, content, re.MULTILINE))
                if matches > 0:
                    pattern_counts[name] += matches
                    file_had_pattern = True
                    if name in semantic_patterns:
                        semantic_count += matches
                    else:
                        syntax_count += matches
            if file_had_pattern:
                files_with_patterns.add(os.path.relpath(f, project_root))
        except (IOError, OSError):
            pass

    return pattern_counts, files_with_patterns, syntax_count, semantic_count


def determine_sizing(py_file_count, total_loc, escalators, semantic_count):
    """Determine project sizing category and recommended workflow."""
    # Base tier from file count and LOC
    if py_file_count <= 20 and total_loc <= 2000:
        base_tier = "small"
    elif py_file_count <= 100 and total_loc <= 15000:
        base_tier = "medium"
    elif py_file_count <= 500 and total_loc <= 100000:
        base_tier = "large"
    else:
        base_tier = "very_large"

    # Apply escalators
    effective_tier = base_tier
    escalator_bump = False
    tier_order = ["small", "medium", "large", "very_large"]

    if escalators:
        current_idx = tier_order.index(base_tier)
        bumped_idx = min(current_idx + 1, len(tier_order) - 1)
        if bumped_idx > current_idx:
            effective_tier = tier_order[bumped_idx]
            escalator_bump = True

    # Map tier to workflow
    workflow_map = {
        "small": "express",
        "medium": "standard",
        "large": "full",
        "very_large": "full_parallel",
    }

    return {
        "base_tier": base_tier,
        "effective_tier": effective_tier,
        "workflow": workflow_map[effective_tier],
        "escalator_bump": escalator_bump,
    }


def detect_non_python_languages(all_files, project_root):
    """Quick check for non-Python languages (polyglot indicator)."""
    lang_extensions = {
        ".java": "Java",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".c": "C",
        ".cpp": "C++",
        ".h": "C/C++ Header",
        ".rs": "Rust",
        ".go": "Go",
        ".rb": "Ruby",
    }
    languages = {}
    for f in all_files:
        ext = os.path.splitext(f)[1].lower()
        if ext in lang_extensions:
            lang = lang_extensions[ext]
            if lang not in languages:
                languages[lang] = 0
            languages[lang] += 1
    return languages


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Quick project sizing scan for migration workflow selection"
    )
    parser.add_argument("project_root", help="Path to the project root directory")
    parser.add_argument(
        "--output", "-o", help="Write sizing report to this JSON file", default=None
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Glob patterns to exclude (e.g., '**/vendor/**')",
    )
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)
    if not os.path.isdir(project_root):
        print(json.dumps({"status": "error", "message": f"Not a directory: {project_root}"}))
        sys.exit(2)

    # Step 1: Count files and LOC
    py_files, total_loc, all_files = count_files_and_loc(project_root, args.exclude)
    test_files = detect_test_files(py_files)
    non_python = detect_non_python_languages(all_files, project_root)

    # Step 2: Check complexity escalators
    escalators = check_complexity_escalators(project_root, py_files, all_files, test_files)

    # Step 3: Quick pattern scan
    pattern_counts, files_with_patterns, syntax_count, semantic_count = quick_pattern_scan(
        py_files, project_root
    )

    # Step 4: Determine sizing
    sizing = determine_sizing(len(py_files), total_loc, escalators, semantic_count)

    # Build report
    report = {
        "status": "complete",
        "project_root": project_root,
        "scan_date": datetime.now().isoformat(),
        "metrics": {
            "python_files": len(py_files),
            "total_loc": total_loc,
            "test_files": len(test_files),
            "files_with_py2_patterns": len(files_with_patterns),
            "total_py2_patterns": syntax_count + semantic_count,
            "syntax_only_patterns": syntax_count,
            "semantic_patterns": semantic_count,
        },
        "sizing": sizing,
        "complexity_escalators": escalators,
        "pattern_summary": {
            name: count for name, count in pattern_counts.items() if count > 0
        },
        "non_python_languages": non_python,
        "recommendations": {
            "workflow": sizing["workflow"],
            "estimated_sessions": {
                "express": 1,
                "standard": "2-4",
                "full": "5-15",
                "full_parallel": "10-30",
            }[sizing["workflow"]],
            "model_tier": {
                "express": "Haiku only",
                "standard": "Haiku 70%, Sonnet 30%",
                "full": "Haiku 50%, Sonnet 25%, Opus 5%",
                "full_parallel": "Haiku 50%, Sonnet 25%, Opus 5%",
            }[sizing["workflow"]],
            "skills_needed": _recommend_skills(sizing["workflow"], escalators, semantic_count),
        },
    }

    # Output
    output_json = json.dumps(report, indent=2)
    print(output_json)

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w") as f:
            f.write(output_json)

    sys.exit(0)


def _recommend_skills(workflow, escalators, semantic_count):
    """Return list of skills recommended for this workflow."""
    escalator_names = {e["name"] for e in escalators}

    if workflow == "express":
        skills = ["codebase-analyzer (summary mode)", "automated-converter", "future-imports-injector"]
        if semantic_count > 0:
            skills.append("library-replacement")
        return skills

    if workflow == "standard":
        skills = [
            "codebase-analyzer",
            "future-imports-injector",
            "automated-converter",
            "library-replacement",
            "completeness-checker",
            "dead-code-detector",
            "compatibility-shim-remover",
        ]
        if "binary_protocols" in escalator_names or semantic_count > 10:
            skills.append("bytes-string-fixer")
        if "pickle_marshal" in escalator_names:
            skills.append("serialization-detector")
        if "c_extensions" in escalator_names:
            skills.append("c-extension-flagger")
        return skills

    # full or full_parallel
    return ["all skills available"]


if __name__ == "__main__":
    main()
