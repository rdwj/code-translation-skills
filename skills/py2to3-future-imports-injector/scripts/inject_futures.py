#!/usr/bin/env python3
"""
Future Imports Injector — Main Injection Script

Safely adds `from __future__ import` statements to Python files in a codebase.
Supports batch processing with test validation between batches, cautious mode
for separating unicode_literals, dry-run mode, and rollback on test failure.

Produces:
  - future-imports-report.json — per-file status with pass/fail details
  - high-risk-modules.json    — files that broke after injection

Usage:
    # Dry run — see what would change
    python3 inject_futures.py <codebase_path> --output <dir> --dry-run

    # Standard mode — all four imports, batch by batch
    python3 inject_futures.py <codebase_path> --output <dir> \
        --batch-size 10 --test-command "python -m pytest -x"

    # Cautious mode — unicode_literals applied separately
    python3 inject_futures.py <codebase_path> --output <dir> \
        --cautious --batch-size 5 --test-command "python -m pytest -x"
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# The four future imports to add
ALL_FUTURE_IMPORTS = [
    "print_function",
    "division",
    "absolute_import",
    "unicode_literals",
]

# The "safe three" — these rarely cause breakage
SAFE_IMPORTS = ["print_function", "division", "absolute_import"]

# Regex to find existing __future__ imports
FUTURE_IMPORT_RE = re.compile(
    r"^from\s+__future__\s+import\s+(.+)$", re.MULTILINE
)

# Encoding declaration patterns (must be in first 2 lines)
ENCODING_RE = re.compile(
    r"^#.*?coding[:=]\s*([-\w.]+)", re.ASCII
)

# Shebang
SHEBANG_RE = re.compile(r"^#!.+$")


# ═══════════════════════════════════════════════════════════════════════════
# File Analysis
# ═══════════════════════════════════════════════════════════════════════════

def parse_existing_futures(content: str) -> Set[str]:
    """Extract the set of future imports already present in a file."""
    existing = set()
    for match in FUTURE_IMPORT_RE.finditer(content):
        imports_text = match.group(1)
        # Handle multi-line imports with parens
        # For now, handle comma-separated on one line
        for name in re.split(r"[,\s]+", imports_text):
            name = name.strip().strip("()")
            if name and name.isidentifier():
                existing.add(name)
    return existing


def find_injection_point(content: str) -> int:
    """Find the line index where the future import should be inserted.

    The injection point is after:
    1. Shebang line (if present, must be line 0)
    2. Encoding declaration (if present, must be in first 2 lines)
    3. Module docstring (if present, right at the top)

    Returns the character offset where the import line should be inserted.
    """
    lines = content.split("\n")
    line_idx = 0

    # Skip shebang
    if lines and SHEBANG_RE.match(lines[0]):
        line_idx = 1

    # Skip encoding declarations (can be in first 2 lines)
    while line_idx < min(len(lines), 2):
        if ENCODING_RE.match(lines[line_idx]):
            line_idx += 1
        else:
            break

    # Skip blank lines after shebang/encoding
    while line_idx < len(lines) and not lines[line_idx].strip():
        line_idx += 1

    # Skip module docstring if present
    if line_idx < len(lines):
        line = lines[line_idx].strip()
        if line.startswith('"""') or line.startswith("'''"):
            quote = line[:3]
            if line.count(quote) >= 2 and len(line) > 3:
                # Single-line docstring
                line_idx += 1
            else:
                # Multi-line docstring — find the closing quotes
                line_idx += 1
                while line_idx < len(lines):
                    if quote in lines[line_idx]:
                        line_idx += 1
                        break
                    line_idx += 1
        elif line.startswith('"') or line.startswith("'"):
            # Single-quoted single-line docstring
            line_idx += 1

    # The injection point is at this line index
    # Convert to character offset
    offset = 0
    for i in range(min(line_idx, len(lines))):
        offset += len(lines[i]) + 1  # +1 for newline
    return offset


def inject_future_imports(
    content: str,
    imports_to_add: List[str],
) -> Tuple[str, List[str]]:
    """Inject future imports into file content. Returns (new_content, imports_actually_added).

    Merges with existing future imports if present.
    """
    existing = parse_existing_futures(content)
    needed = [imp for imp in imports_to_add if imp not in existing]

    if not needed:
        return content, []

    # Check if there's already a future import line we can extend
    match = FUTURE_IMPORT_RE.search(content)
    if match:
        # Merge into the existing import line
        all_imports = sorted(existing | set(needed))
        import_line = "from __future__ import " + ", ".join(all_imports)
        new_content = content[: match.start()] + import_line + content[match.end() :]
        return new_content, needed

    # No existing future import — insert a new line
    offset = find_injection_point(content)
    import_line = "from __future__ import " + ", ".join(sorted(needed))

    # Add appropriate blank lines
    before = content[:offset]
    after = content[offset:]

    # Ensure blank line before the import if there's content before
    if before.rstrip():
        before = before.rstrip() + "\n\n"

    # Ensure blank line after the import
    new_content = before + import_line + "\n"
    if after.lstrip("\n"):
        new_content += "\n" + after.lstrip("\n")
    else:
        new_content += after

    return new_content, needed


# ═══════════════════════════════════════════════════════════════════════════
# File Processing
# ═══════════════════════════════════════════════════════════════════════════

def should_skip_file(filepath: str, content: str) -> Optional[str]:
    """Check if a file should be skipped. Returns reason or None."""
    if not content.strip():
        return "empty_file"
    # Skip files that are just comments (e.g. empty __init__.py with only a docstring)
    lines = [l for l in content.split("\n") if l.strip() and not l.strip().startswith("#")]
    # A file with only docstrings and no actual code
    if not lines:
        return "no_code"
    return None


def process_file(
    filepath: str,
    imports_to_add: List[str],
    dry_run: bool = False,
    backup: bool = False,
) -> Dict[str, Any]:
    """Process a single file: analyze and optionally inject future imports.

    Returns a status dict for the report.
    """
    rel_path = filepath  # Will be overridden by caller with relative path

    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            original = f.read()
    except IOError as e:
        return {
            "path": rel_path,
            "status": "error",
            "error": str(e),
        }

    # Check if we should skip
    skip_reason = should_skip_file(filepath, original)
    if skip_reason:
        return {
            "path": rel_path,
            "status": "skipped",
            "reason": skip_reason,
        }

    # Check existing imports
    existing = parse_existing_futures(original)
    needed = [imp for imp in imports_to_add if imp not in existing]

    if not needed:
        return {
            "path": rel_path,
            "status": "already_had",
            "imports_existing": sorted(existing),
        }

    # Inject
    new_content, added = inject_future_imports(original, imports_to_add)

    if dry_run:
        return {
            "path": rel_path,
            "status": "would_modify",
            "imports_to_add": added,
            "imports_existing": sorted(existing),
        }

    # Write the modified file
    if backup:
        shutil.copy2(filepath, filepath + ".bak")

    # Atomic write via temp file
    dir_name = os.path.dirname(filepath)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".py.tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_content)
        os.replace(tmp_path, filepath)
    except IOError as e:
        # Clean up temp file on failure
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        return {
            "path": rel_path,
            "status": "error",
            "error": f"Write failed: {e}",
        }

    return {
        "path": rel_path,
        "status": "modified",
        "imports_added": added,
        "imports_existing": sorted(existing),
    }


def revert_file(filepath: str, original_content: str) -> None:
    """Revert a file to its original content."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(original_content)


# ═══════════════════════════════════════════════════════════════════════════
# Test Runner
# ═══════════════════════════════════════════════════════════════════════════

def run_tests(
    test_command: str,
    codebase_path: str,
    timeout: int = 300,
) -> Tuple[bool, str]:
    """Run the test command and return (passed, output)."""
    try:
        result = subprocess.run(
            test_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=codebase_path,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output[-2000:]  # Limit output size
    except subprocess.TimeoutExpired:
        return False, "Test command timed out"
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════════════════════════════════
# Batch Orchestration
# ═══════════════════════════════════════════════════════════════════════════

def discover_files(
    codebase_path: str,
    exclude_patterns: Optional[List[str]] = None,
) -> List[str]:
    """Find all .py files, respecting excludes."""
    import fnmatch

    root = Path(codebase_path).resolve()
    excludes = exclude_patterns or []
    files = []

    for py_file in sorted(root.rglob("*.py")):
        rel = str(py_file.relative_to(root))
        skip = False
        for pattern in excludes:
            if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(str(py_file), pattern):
                skip = True
                break
        if not skip:
            files.append(str(py_file))
    return files


def run_injection(
    codebase_path: str,
    output_dir: str,
    imports_to_add: List[str],
    batch_size: int = 10,
    test_command: Optional[str] = None,
    dry_run: bool = False,
    backup: bool = False,
    rollback_on_failure: bool = True,
    exclude_patterns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run the injection process across all files."""
    root = Path(codebase_path).resolve()
    files = discover_files(codebase_path, exclude_patterns)

    all_results = []
    high_risk = []
    batches_run = 0
    batches_passed = 0
    batches_failed = 0
    total_test_time = 0

    # Process in batches
    for batch_start in range(0, len(files), batch_size):
        batch = files[batch_start : batch_start + batch_size]
        batch_num = batch_start // batch_size + 1
        batch_results = []
        batch_originals = {}  # For rollback

        if not dry_run:
            print(f"  Batch {batch_num}: processing {len(batch)} files...")

        for filepath in batch:
            rel = str(Path(filepath).relative_to(root))

            # Save original for potential rollback
            if not dry_run and rollback_on_failure:
                try:
                    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                        batch_originals[filepath] = f.read()
                except IOError:
                    pass

            result = process_file(filepath, imports_to_add, dry_run, backup)
            result["path"] = rel
            result["batch_number"] = batch_num
            batch_results.append(result)

        all_results.extend(batch_results)

        # Run tests after this batch (if not dry run)
        if test_command and not dry_run:
            modified_in_batch = [
                r for r in batch_results if r.get("status") == "modified"
            ]
            if modified_in_batch:
                batches_run += 1
                import time
                start = time.time()
                passed, output = run_tests(test_command, codebase_path)
                elapsed = time.time() - start
                total_test_time += elapsed

                if passed:
                    batches_passed += 1
                    print(f"    Tests passed ({elapsed:.1f}s)")
                else:
                    batches_failed += 1
                    print(f"    Tests FAILED ({elapsed:.1f}s)")

                    # Mark modified files in this batch as failed
                    for r in batch_results:
                        if r.get("status") == "modified":
                            r["status"] = "failed"
                            r["failure_output"] = output[:500]
                            high_risk.append(r["path"])

                    # Rollback if requested
                    if rollback_on_failure:
                        print(f"    Rolling back batch {batch_num}...")
                        for filepath, original in batch_originals.items():
                            revert_file(filepath, original)
                        for r in batch_results:
                            if r.get("status") == "failed":
                                r["rolled_back"] = True

    # Build the report
    modified = sum(1 for r in all_results if r.get("status") == "modified")
    skipped = sum(1 for r in all_results if r.get("status") == "skipped")
    already_had = sum(1 for r in all_results if r.get("status") == "already_had")
    failed = sum(1 for r in all_results if r.get("status") == "failed")
    would_modify = sum(1 for r in all_results if r.get("status") == "would_modify")
    errors = sum(1 for r in all_results if r.get("status") == "error")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "codebase_path": str(root),
        "imports_injected": imports_to_add,
        "mode": "dry_run" if dry_run else "injection",
        "total_files": len(files),
        "modified": modified if not dry_run else would_modify,
        "skipped": skipped,
        "already_had_imports": already_had,
        "empty_files": sum(
            1 for r in all_results
            if r.get("status") == "skipped" and r.get("reason") == "empty_file"
        ),
        "failed_after_injection": failed,
        "errors": errors,
        "files": all_results,
        "high_risk_modules": high_risk,
        "test_results": {
            "batches_run": batches_run,
            "batches_passed": batches_passed,
            "batches_failed": batches_failed,
            "total_test_time_seconds": round(total_test_time, 1),
        },
    }

    return report


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Inject __future__ imports into a Python 2 codebase."
    )
    parser.add_argument("codebase_path", help="Root directory of the codebase")
    parser.add_argument("--output", required=True, help="Output directory for reports")
    parser.add_argument(
        "--imports",
        nargs="*",
        default=None,
        help=f"Which imports to add (default: all four). Choose from: {ALL_FUTURE_IMPORTS}",
    )
    parser.add_argument("--batch-size", type=int, default=10, help="Files per batch")
    parser.add_argument("--test-command", default=None, help="Test command to run after each batch")
    parser.add_argument("--dry-run", action="store_true", help="Report without modifying files")
    parser.add_argument("--cautious", action="store_true", help="Apply unicode_literals separately")
    parser.add_argument("--backup", action="store_true", help="Create .bak files before modifying")
    parser.add_argument(
        "--no-rollback", action="store_true",
        help="Don't rollback on test failure (default: rollback)",
    )
    parser.add_argument("--exclude", nargs="*", default=None, help="Glob patterns to exclude")

    args = parser.parse_args()

    if not os.path.isdir(args.codebase_path):
        print(f"Error: Not a directory: {args.codebase_path}", file=sys.stderr)
        sys.exit(1)

    imports = args.imports or ALL_FUTURE_IMPORTS

    # Validate imports
    for imp in imports:
        if imp not in ALL_FUTURE_IMPORTS:
            print(f"Error: Unknown import: {imp}", file=sys.stderr)
            print(f"Valid imports: {ALL_FUTURE_IMPORTS}", file=sys.stderr)
            sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    if args.cautious and not args.dry_run:
        print("=== Cautious Mode: Phase 1 — Safe imports ===")
        safe = [i for i in imports if i != "unicode_literals"]
        report1 = run_injection(
            args.codebase_path, args.output, safe,
            batch_size=args.batch_size,
            test_command=args.test_command,
            dry_run=args.dry_run,
            backup=args.backup,
            rollback_on_failure=not args.no_rollback,
            exclude_patterns=args.exclude,
        )

        print("\n=== Cautious Mode: Phase 2 — unicode_literals ===")
        # Only inject unicode_literals into files that didn't fail
        failed_files = set(report1.get("high_risk_modules", []))
        print(f"  Skipping {len(failed_files)} files that failed in Phase 1")

        # Add failed files to exclude
        extra_excludes = list(args.exclude or []) + list(failed_files)
        report2 = run_injection(
            args.codebase_path, args.output, ["unicode_literals"],
            batch_size=args.batch_size,
            test_command=args.test_command,
            dry_run=args.dry_run,
            backup=args.backup,
            rollback_on_failure=not args.no_rollback,
            exclude_patterns=extra_excludes,
        )

        # Merge reports
        report = report1
        report["mode"] = "cautious"
        report["imports_injected"] = imports
        report["cautious_phase1"] = {
            "imports": safe,
            "modified": report1["modified"],
            "failed": report1["failed_after_injection"],
        }
        report["cautious_phase2"] = {
            "imports": ["unicode_literals"],
            "modified": report2["modified"],
            "failed": report2["failed_after_injection"],
        }
        report["high_risk_modules"] = list(
            set(report1.get("high_risk_modules", []))
            | set(report2.get("high_risk_modules", []))
        )
        report["failed_after_injection"] = (
            report1["failed_after_injection"] + report2["failed_after_injection"]
        )
        # Merge file lists
        report["files"].extend(report2.get("files", []))
    else:
        report = run_injection(
            args.codebase_path, args.output, imports,
            batch_size=args.batch_size,
            test_command=args.test_command,
            dry_run=args.dry_run,
            backup=args.backup,
            rollback_on_failure=not args.no_rollback,
            exclude_patterns=args.exclude,
        )

    # Write reports
    report_path = os.path.join(args.output, "future-imports-report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    high_risk_path = os.path.join(args.output, "high-risk-modules.json")
    with open(high_risk_path, "w", encoding="utf-8") as f:
        json.dump(report.get("high_risk_modules", []), f, indent=2)

    # Print summary
    mode = "DRY RUN" if args.dry_run else report.get("mode", "standard").upper()
    print(f"\n{'='*60}")
    print(f"Future Imports Injection — {mode}")
    print(f"{'='*60}")
    print(f"Total files:     {report['total_files']}")
    print(f"Modified:        {report['modified']}")
    print(f"Skipped:         {report['skipped']}")
    print(f"Already had:     {report['already_had_imports']}")
    print(f"Failed:          {report['failed_after_injection']}")
    if report.get("high_risk_modules"):
        print(f"\nHigh-risk modules ({len(report['high_risk_modules'])}):")
        for m in report["high_risk_modules"][:10]:
            print(f"  - {m}")
        if len(report["high_risk_modules"]) > 10:
            print(f"  ... and {len(report['high_risk_modules']) - 10} more")
    print(f"\nReport: {report_path}")
    print(f"High-risk: {high_risk_path}")


if __name__ == "__main__":
    main()
