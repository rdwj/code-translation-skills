#!/usr/bin/env python3
"""
Automated Converter — Main Script

Applies lib2to3 fixers and custom AST-based transformations to convert a conversion unit
(group of modules) from Python 2 to Python 3. Produces a unified diff and detailed report.

Usage:
    python3 convert.py \
        --codebase <codebase_path> \
        --unit <unit_name> \
        --conversion-plan <plan.json> \
        --target-version 3.12 \
        [--output <output_dir>] \
        [--dry-run] \
        [--state-file <state.json>]

    or:

    python3 convert.py \
        --codebase <codebase_path> \
        --modules file1.py file2.py \
        --target-version 3.12 \
        [--output <output_dir>] \
        [--dry-run]

Output:
    conversion-report.json — Machine-readable results
    conversion-diff.patch — Unified diff of all changes
    (Original files backed up as .py.bak if not --dry-run)

Exit codes:
    0 = All files converted successfully
    1 = One or more files failed
    2 = Nothing to convert
"""

import argparse
import ast
import difflib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime
import tempfile

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


# ── Lib2to3 Integration ──────────────────────────────────────────────────────

try:
    from lib2to3.refactor import RefactoringTool, get_fixers_from_package
    from lib2to3 import pygram, pytree
    LIB2TO3_AVAILABLE = True
except ImportError:
    LIB2TO3_AVAILABLE = False


# ── Configuration ────────────────────────────────────────────────────────────

# lib2to3 fixers to apply
FIXERS = [
    "lib2to3.fixes.fix_apply",
    "lib2to3.fixes.fix_basestring",
    "lib2to3.fixes.fix_buffer",
    "lib2to3.fixes.fix_cmp",
    "lib2to3.fixes.fix_dict",
    "lib2to3.fixes.fix_except",
    "lib2to3.fixes.fix_exec",
    "lib2to3.fixes.fix_execfile",
    "lib2to3.fixes.fix_filter",
    "lib2to3.fixes.fix_funcattrs",
    "lib2to3.fixes.fix_future",
    "lib2to3.fixes.fix_getcwd",
    "lib2to3.fixes.fix_has_key",
    "lib2to3.fixes.fix_idioms",
    "lib2to3.fixes.fix_imports",
    "lib2to3.fixes.fix_input",
    "lib2to3.fixes.fix_intern",
    "lib2to3.fixes.fix_isinstance",
    "lib2to3.fixes.fix_itertools",
    "lib2to3.fixes.fix_long",
    "lib2to3.fixes.fix_map",
    "lib2to3.fixes.fix_metaclass",
    "lib2to3.fixes.fix_ne",
    "lib2to3.fixes.fix_next",
    "lib2to3.fixes.fix_nonlocal",
    "lib2to3.fixes.fix_numliterals",
    "lib2to3.fixes.fix_operator",
    "lib2to3.fixes.fix_paren",
    "lib2to3.fixes.fix_print",
    "lib2to3.fixes.fix_raw_input",
    "lib2to3.fixes.fix_reduce",
    "lib2to3.fixes.fix_reload",
    "lib2to3.fixes.fix_repr",
    "lib2to3.fixes.fix_set_literal",
    "lib2to3.fixes.fix_sorted",
    "lib2to3.fixes.fix_standarderror",
    "lib2to3.fixes.fix_sys_exc_info",
    "lib2to3.fixes.fix_throw",
    "lib2to3.fixes.fix_types",
    "lib2to3.fixes.fix_unicode",
    "lib2to3.fixes.fix_urllib",
    "lib2to3.fixes.fix_ws_comma",
    "lib2to3.fixes.fix_xrange",
    "lib2to3.fixes.fix_zip",
]

STDLIB_REMOVED_3_12 = {
    "aifc", "audioop", "chunk", "cgi", "cgitb", "crypt", "imaplib",
    "mailcap", "nis", "nntplib", "ossaudiodev", "pipes", "smtpd",
    "spwd", "sunau", "telnetlib", "uu", "xdrlib"
}


# ── File Operations ──────────────────────────────────────────────────────────

def read_file_safe(path: Path) -> Tuple[str, str]:
    """Read file with encoding detection. Returns (content, actual_encoding)."""
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            content = path.read_text(encoding=encoding)
            return content, encoding
        except (UnicodeDecodeError, LookupError):
            continue
    # Fallback: read as UTF-8 with errors='replace'
    content = path.read_text(encoding="utf-8", errors="replace")
    return content, "utf-8"


def write_file_safe(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)


def create_backup(path: Path) -> Path:
    """Create a backup of a file (.py.bak) and return backup path."""
    backup_path = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, backup_path)
    return backup_path


# ── Lib2to3 Wrapper ──────────────────────────────────────────────────────────

class Py2To3Converter:
    """Wrapper around lib2to3 refactoring tool."""

    def __init__(self, target_version: str = "3.9"):
        if not LIB2TO3_AVAILABLE:
            raise RuntimeError("lib2to3 not available")
        self.target_version = target_version
        self.tool = RefactoringTool(FIXERS, options={"print_function": True})
        self.transforms_applied: List[Dict[str, Any]] = []

    def refactor_string(self, source: str, filename: str = "<unknown>") -> Tuple[str, List[Dict[str, Any]]]:
        """Refactor a string of Python 2 code. Returns (refactored_code, list_of_transforms)."""
        try:
            refactored = self.tool.refactor_string(source, filename)
            # tool.refactor_string returns a RefactoringTool.RefactoredString (which is pytree.Base)
            # Convert back to string
            result = str(refactored)
            return result, self._extract_transforms(source, result, filename)
        except Exception as e:
            print(f"Warning: lib2to3 failed on {filename}: {e}", file=sys.stderr)
            return source, [{"type": "lib2to3_error", "error": str(e)}]

    def _extract_transforms(self, old: str, new: str, filename: str) -> List[Dict[str, Any]]:
        """Compare old and new to extract what lib2to3 changed."""
        if old == new:
            return []
        transforms = []
        # Simple heuristics: look for common patterns
        if "print(" in new and "print " in old:
            transforms.append({"type": "print_statement", "description": "print statement → function"})
        if "except" in old and "as" in new and "except" in new:
            transforms.append({"type": "except_syntax", "description": "except comma → as"})
        if "range(" in new and "xrange(" in old:
            transforms.append({"type": "xrange", "description": "xrange → range"})
        return transforms or [{"type": "lib2to3_refactor", "description": f"Refactored by lib2to3"}]


# ── Custom AST Transformations ───────────────────────────────────────────────

class CustomAstTransformer(ast.NodeTransformer):
    """Apply custom transformations that lib2to3 misses."""

    def __init__(self, filename: str = "<unknown>"):
        self.filename = filename
        self.transforms_applied: List[Dict[str, Any]] = []
        self.lines: List[str] = []

    def visit_Call(self, node: ast.Call) -> ast.AST:
        """Handle function calls: unicode(), raw_input(), long(), reduce(), etc."""
        self.generic_visit(node)
        
        # unicode(x) → str(x)
        if isinstance(node.func, ast.Name) and node.func.id == "unicode":
            node.func.id = "str"
            self.transforms_applied.append({
                "type": "unicode_builtin",
                "description": "unicode() → str()",
                "lineno": node.lineno
            })
        
        # raw_input() → input()
        elif isinstance(node.func, ast.Name) and node.func.id == "raw_input":
            node.func.id = "input"
            self.transforms_applied.append({
                "type": "raw_input",
                "description": "raw_input() → input()",
                "lineno": node.lineno
            })
        
        # long(x) → int(x)
        elif isinstance(node.func, ast.Name) and node.func.id == "long":
            node.func.id = "int"
            self.transforms_applied.append({
                "type": "long_builtin",
                "description": "long() → int()",
                "lineno": node.lineno
            })
        
        return node

    def visit_Name(self, node: ast.Name) -> ast.AST:
        """Handle builtin names that no longer exist."""
        self.generic_visit(node)
        
        # basestring → str (with fallback for compat)
        if node.id == "basestring" and isinstance(node.ctx, ast.Load):
            node.id = "str"
            self.transforms_applied.append({
                "type": "basestring",
                "description": "basestring → str",
                "lineno": node.lineno
            })
        
        return node


def apply_custom_transforms(source: str, filename: str = "<unknown>") -> Tuple[str, List[Dict[str, Any]]]:
    """Apply custom AST-based transformations."""
    try:
        tree = ast.parse(source, filename)
    except SyntaxError:
        # Source has syntax errors, skip AST transforms
        return source, []
    
    transformer = CustomAstTransformer(filename)
    try:
        new_tree = transformer.visit(tree)
        result = ast.unparse(new_tree) if hasattr(ast, "unparse") else source
        return result, transformer.transforms_applied
    except Exception as e:
        print(f"Warning: Custom transforms failed on {filename}: {e}", file=sys.stderr)
        return source, []


# ── Target Version Aware Transforms ──────────────────────────────────────────

def apply_version_aware_transforms(
    source: str, target_version: str, filename: str = "<unknown>"
) -> Tuple[str, List[Dict[str, Any]]]:
    """Apply target-version-specific transformations."""
    transforms: List[Dict[str, Any]] = []
    result = source
    
    # 3.12+: distutils → setuptools
    if target_version >= "3.12":
        if "distutils" in result:
            result = re.sub(r"from distutils\b", "from setuptools", result)
            result = re.sub(r"import distutils\b", "import setuptools", result)
            transforms.append({
                "type": "distutils_migration",
                "description": "distutils → setuptools (3.12+)",
                "category": "target_version"
            })
        
        # Flag removed stdlib modules
        for module in STDLIB_REMOVED_3_12:
            pattern = rf"\b{module}\b"
            if re.search(pattern, result):
                transforms.append({
                    "type": "stdlib_removal_3_12",
                    "description": f"Module '{module}' removed in 3.12+",
                    "category": "target_version",
                    "needs_review": True
                })
    
    return result, transforms


# ── Conversion Engine ────────────────────────────────────────────────────────

def convert_file(
    source_path: Path,
    target_version: str = "3.9",
    output_path: Optional[Path] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """Convert a single Python file. Returns conversion result dict."""
    
    result: Dict[str, Any] = {
        "file": str(source_path),
        "status": "unknown",
        "transforms": [],
        "errors": [],
        "original_content": None,
        "converted_content": None,
    }
    
    try:
        # Read original
        original_content, encoding = read_file_safe(source_path)
        result["original_content"] = original_content
        
        # Skip if too small or empty
        if not original_content.strip():
            result["status"] = "skipped"
            result["reason"] = "empty file"
            return result
        
        converted_content = original_content
        all_transforms: List[Dict[str, Any]] = []
        
        # Step 1: lib2to3 refactoring
        if LIB2TO3_AVAILABLE:
            converter = Py2To3Converter(target_version)
            converted_content, lib2to3_transforms = converter.refactor_string(
                converted_content, str(source_path)
            )
            all_transforms.extend(lib2to3_transforms)
        
        # Step 2: Custom AST transforms (on top of lib2to3 output)
        converted_content, custom_transforms = apply_custom_transforms(
            converted_content, str(source_path)
        )
        all_transforms.extend(custom_transforms)
        
        # Step 3: Target version aware transforms
        converted_content, version_transforms = apply_version_aware_transforms(
            converted_content, target_version, str(source_path)
        )
        all_transforms.extend(version_transforms)
        
        result["converted_content"] = converted_content
        result["transforms"] = all_transforms
        
        # If nothing changed, mark as skipped
        if converted_content == original_content:
            result["status"] = "skipped"
            result["reason"] = "no transformations needed"
            return result
        
        # If --dry-run, don't write
        if dry_run:
            result["status"] = "converted_dry_run"
            return result
        
        # Determine output path
        if output_path is None:
            output_path = source_path
        
        # Create backup
        backup_path = create_backup(source_path)
        result["backup_path"] = str(backup_path)
        
        # Write converted file
        write_file_safe(output_path, converted_content, encoding)
        result["status"] = "converted"
        result["output_path"] = str(output_path)
        
    except Exception as e:
        result["status"] = "error"
        result["errors"] = [str(e)]
    
    return result


# ── Diff Generation ──────────────────────────────────────────────────────────

def generate_diff(
    original_path: str,
    converted_content: str,
    filename: str = "file.py"
) -> str:
    """Generate a unified diff between original and converted content."""
    # Read original for diff
    try:
        original_lines = Path(original_path).read_text().splitlines(keepends=True)
    except Exception:
        original_lines = []
    
    converted_lines = converted_content.splitlines(keepends=True)
    
    diff = difflib.unified_diff(
        original_lines,
        converted_lines,
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
        lineterm=""
    )
    
    return "\n".join(diff)


def generate_patch_file(results: List[Dict[str, Any]], output_path: Path) -> None:
    """Generate a unified patch file from all conversion results."""
    patches: List[str] = []
    
    for result in results:
        if result["status"] in ("converted", "converted_dry_run"):
            if result["original_content"] and result["converted_content"]:
                diff = generate_diff(
                    result["file"],
                    result["converted_content"],
                    Path(result["file"]).name
                )
                if diff.strip():
                    patches.append(diff)
    
    patch_content = "\n".join(patches) if patches else "# No changes\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(patch_content)


# ── Report Generation ────────────────────────────────────────────────────────

def generate_report(
    results: List[Dict[str, Any]],
    target_version: str,
    output_path: Path,
) -> Dict[str, Any]:
    """Generate a conversion report and return as dict."""
    
    total_files = len(results)
    converted_files = [r for r in results if r["status"] in ("converted", "converted_dry_run")]
    failed_files = [r for r in results if r["status"] == "error"]
    skipped_files = [r for r in results if r["status"] == "skipped"]
    
    # Aggregate transforms
    all_transforms: List[Dict[str, Any]] = []
    transform_categories = defaultdict(int)
    
    for result in converted_files:
        for transform in result.get("transforms", []):
            all_transforms.append({
                "file": result["file"],
                **transform
            })
            transform_categories[transform.get("type", "unknown")] += 1
    
    report = {
        "timestamp": datetime.utcnow().isoformat(),
        "target_version": target_version,
        "files_total": total_files,
        "files_converted": len(converted_files),
        "files_skipped": len(skipped_files),
        "files_failed": len(failed_files),
        "transforms_applied": all_transforms,
        "transform_summary": dict(transform_categories),
        "results": results,
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    
    return report


# ── Unit Resolution ──────────────────────────────────────────────────────────

def resolve_unit(
    unit_name: str,
    codebase_path: Path,
    conversion_plan: Dict[str, Any]
) -> List[Path]:
    """Resolve a unit name from the conversion plan to a list of module paths."""
    
    # Find the unit in the plan
    for wave in conversion_plan.get("waves", []):
        for unit in wave.get("units", []):
            if unit.get("name") == unit_name:
                # Found it! Get the modules
                module_paths = []
                for module_name in unit.get("modules", []):
                    # Convert module name to file path
                    # e.g., "src.utils.common" -> "src/utils/common.py"
                    parts = module_name.split(".")
                    file_path = codebase_path / "/".join(parts[:-1]) / f"{parts[-1]}.py"
                    if file_path.exists():
                        module_paths.append(file_path)
                    else:
                        # Try without the last part as module part
                        alt_path = codebase_path / "/".join(parts) / "__init__.py"
                        if alt_path.exists():
                            module_paths.append(alt_path)
                return module_paths
    
    raise ValueError(f"Unit '{unit_name}' not found in conversion plan")


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Convert a conversion unit from Python 2 to Python 3"
    )
    
    parser.add_argument(
        "--codebase",
        required=True,
        type=Path,
        help="Root directory of the codebase"
    )
    
    # Module specification: either --unit or --modules
    unit_group = parser.add_mutually_exclusive_group(required=True)
    unit_group.add_argument(
        "--unit",
        help="Conversion unit name (requires --conversion-plan)"
    )
    unit_group.add_argument(
        "--modules",
        nargs="+",
        type=Path,
        help="Module files to convert (relative to --codebase)"
    )
    
    parser.add_argument(
        "--conversion-plan",
        type=Path,
        help="Path to conversion-plan.json (required if --unit is used)"
    )
    
    parser.add_argument(
        "--target-version",
        default="3.9",
        choices=["3.9", "3.11", "3.12", "3.13"],
        help="Target Python 3 version"
    )
    
    parser.add_argument(
        "--output",
        type=Path,
        help="Output directory for converted files (default: modify in place)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying files"
    )
    
    parser.add_argument(
        "--state-file",
        type=Path,
        help="Path to migration-state.json for tracking progress"
    )
    
    args = parser.parse_args()
    
    # Validate arguments
    if args.unit and not args.conversion_plan:
        print("Error: --conversion-plan is required when using --unit", file=sys.stderr)
        sys.exit(1)
    
    # Resolve module list
    if args.unit:
        plan_data = json.loads(args.conversion_plan.read_text())
        try:
            modules = resolve_unit(args.unit, args.codebase, plan_data)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        modules = [args.codebase / m for m in args.modules]
    
    # Verify modules exist
    modules = [m for m in modules if m.exists()]
    if not modules:
        print("Error: No valid modules to convert", file=sys.stderr)
        sys.exit(2)
    
    print(f"Converting {len(modules)} modules to Python {args.target_version}...")
    if args.dry_run:
        print("(DRY RUN — no files will be modified)")
    print()
    
    # Convert each module
    results: List[Dict[str, Any]] = []
    for module_path in modules:
        output_path = None
        if args.output:
            rel_path = module_path.relative_to(args.codebase)
            output_path = args.output / rel_path
        
        print(f"Converting {module_path.relative_to(args.codebase)}...", end=" ")
        result = convert_file(module_path, args.target_version, output_path, args.dry_run)
        results.append(result)
        print(result["status"])
    
    print()
    
    # Generate report
    report_path = args.output / "conversion-report.json" if args.output else Path("conversion-report.json")
    report = generate_report(results, args.target_version, report_path)
    print(f"Conversion report: {report_path}")
    
    # Generate patch
    patch_path = args.output / "conversion-diff.patch" if args.output else Path("conversion-diff.patch")
    generate_patch_file(results, patch_path)
    print(f"Unified diff: {patch_path}")
    
    # Print summary
    print()
    print(f"Summary:")
    print(f"  Converted: {report['files_converted']}/{report['files_total']}")
    print(f"  Skipped: {report['files_skipped']}")
    print(f"  Failed: {report['files_failed']}")
    print(f"  Transforms: {len(report['transforms_applied'])}")
    
    if report["files_failed"] > 0:
        print()
        print("Failed files:")
        for result in results:
            if result["status"] == "error":
                print(f"  {result['file']}: {', '.join(result['errors'])}")
    
    # Exit code
    if report["files_failed"] > 0:
        sys.exit(1)
    elif report["files_converted"] == 0:
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
