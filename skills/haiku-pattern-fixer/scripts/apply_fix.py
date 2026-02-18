#!/usr/bin/env python3
"""
apply_fix.py — Apply a single mechanical Python 2→3 pattern fix.

This script is designed to be called thousands of times by Haiku, each time
with one work item. The fix itself is deterministic — a script could do many
of them without any LLM at all.

Inputs:
  --work-item (-w): Path to work-item JSON, or inline JSON string
  --source-file (-s): Path to source file (overrides work item's file field)
  --dry-run: Print diff without applying
  --output (-o): Output directory for result JSON

Output:
  - Modified source file (unless --dry-run)
  - result.json with status, pattern, file, original/fixed lines, diff
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


# Define all supported pattern transformations
PATTERN_FIXES = {
    "has_key": {
        # d.has_key(k) → k in d
        "find": r"(\w+)\.has_key\((.+?)\)",
        "replace": r"\2 in \1"
    },
    "xrange": {
        # xrange(...) → range(...)
        "find": r"\bxrange\b",
        "replace": "range"
    },
    "raw_input": {
        # raw_input(...) → input(...)
        "find": r"\braw_input\b",
        "replace": "input"
    },
    "print_statement": {
        # print "hello" → print("hello")
        # Requires special handling
        "handler": "fix_print_statement"
    },
    "except_syntax": {
        # except Error, e: → except Error as e:
        "find": r"except\s+(\w+(?:\.\w+)*)\s*,\s*(\w+)\s*:",
        "replace": r"except \1 as \2:"
    },
    "raise_syntax": {
        # raise Error, msg → raise Error(msg)
        "find": r"raise\s+(\w+(?:\.\w+)*)\s*,\s*(.+)",
        "replace": r"raise \1(\2)"
    },
    "octal_literal": {
        # 0777 → 0o777
        "find": r"\b0(\d{2,})\b",
        "replace": r"0o\1"
    },
    "long_suffix": {
        # 123L → 123
        "find": r"\b(\d+)[lL]\b",
        "replace": r"\1"
    },
    "ne_operator": {
        # a <> b → a != b
        "find": r"<>",
        "replace": "!="
    },
    "backtick_repr": {
        # `x` → repr(x)
        "find": r"`([^`]+)`",
        "replace": r"repr(\1)"
    },
    "iteritems": {
        # .iteritems() → .items()
        "find": r"\.iteritems\(\)",
        "replace": ".items()"
    },
    "itervalues": {
        # .itervalues() → .values()
        "find": r"\.itervalues\(\)",
        "replace": ".values()"
    },
    "iterkeys": {
        # .iterkeys() → .keys()
        "find": r"\.iterkeys\(\)",
        "replace": ".keys()"
    },
    "exec_statement": {
        # exec code → exec(code)
        # Requires special handling
        "handler": "fix_exec_statement"
    },
    "unicode_builtin": {
        # unicode(x) → str(x)
        "find": r"\bunicode\(",
        "replace": "str("
    },
    "long_builtin": {
        # long(x) → int(x)
        "find": r"\blong\(",
        "replace": "int("
    },
    "buffer_builtin": {
        # buffer(x) → memoryview(x)
        "find": r"\bbuffer\(",
        "replace": "memoryview("
    },
    "inequality_operator": {
        # x <> y → x != y
        "find": r"<>",
        "replace": "!="
    },
}


def fix_print_statement(line: str) -> Optional[str]:
    """
    Convert print statements to function calls.

    Handle:
      print "hello"                 → print("hello")
      print "a", "b"                → print("a", "b")
      print >> sys.stderr, "msg"    → print("msg", file=sys.stderr)
      print "a",  (trailing comma)  → print("a", end="")
    """
    # Skip lines that are already print functions (have parenthesis after print)
    if re.match(r"\s*print\s*\(", line):
        return None

    # Match print >> file, args
    file_output = re.match(r"^(\s*)print\s*>>\s*([^,]+),\s*(.+)$", line)
    if file_output:
        indent, file_obj, args = file_output.groups()
        # Convert to print(..., file=file_obj)
        return f'{indent}print({args}, file={file_obj})'

    # Match print with trailing comma (no newline)
    trailing_comma = re.match(r"^(\s*)print\s+(.+),\s*$", line)
    if trailing_comma:
        indent, args = trailing_comma.groups()
        return f'{indent}print({args}, end=" ")'

    # Match print args (no trailing comma)
    regular_print = re.match(r"^(\s*)print\s+(.+)$", line)
    if regular_print:
        indent, args = regular_print.groups()
        return f'{indent}print({args})'

    return None


def fix_exec_statement(line: str) -> Optional[str]:
    """
    Convert exec statements to function calls.

    Handle:
      exec code                      → exec(code)
      exec code in globals           → exec(code, globals)
      exec code in globals, locals   → exec(code, globals, locals)
    """
    # Skip lines that are already exec functions
    if re.match(r"\s*exec\s*\(", line):
        return None

    # Match exec code in globals, locals
    with_both = re.match(r"^(\s*)exec\s+(.+?)\s+in\s+(.+?),\s*(.+)$", line)
    if with_both:
        indent, code, globals_obj, locals_obj = with_both.groups()
        return f'{indent}exec({code}, {globals_obj}, {locals_obj})'

    # Match exec code in globals
    with_globals = re.match(r"^(\s*)exec\s+(.+?)\s+in\s+(.+)$", line)
    if with_globals:
        indent, code, globals_obj = with_globals.groups()
        return f'{indent}exec({code}, {globals_obj})'

    # Match exec code
    regular_exec = re.match(r"^(\s*)exec\s+(.+)$", line)
    if regular_exec:
        indent, code = regular_exec.groups()
        return f'{indent}exec({code})'

    return None


def load_work_item(work_item_arg: str) -> Dict[str, Any]:
    """Load work item from file path or inline JSON string."""
    # Try as file path first
    if os.path.isfile(work_item_arg):
        with open(work_item_arg, 'r') as f:
            return json.load(f)

    # Try as JSON string
    try:
        return json.loads(work_item_arg)
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse work item as file or JSON: {work_item_arg}", file=sys.stderr)
        sys.exit(2)


def apply_regex_fix(line: str, pattern_config: Dict[str, str]) -> Optional[str]:
    """Apply a regex-based fix. Returns modified line or None if no match."""
    find = pattern_config.get("find")
    replace = pattern_config.get("replace")

    if not find or not replace:
        return None

    try:
        if re.search(find, line):
            return re.sub(find, replace, line)
    except re.error as e:
        print(f"ERROR: Invalid regex pattern: {e}", file=sys.stderr)
        return None

    return None


def apply_fix_to_line(line: str, pattern_name: str) -> Optional[str]:
    """Apply the specified pattern fix to a line. Returns modified line or None if no change."""
    if pattern_name not in PATTERN_FIXES:
        return None

    pattern_config = PATTERN_FIXES[pattern_name]

    # Check if pattern has a handler function
    if "handler" in pattern_config:
        handler_name = pattern_config["handler"]
        handler = globals().get(handler_name)
        if handler:
            return handler(line)
        else:
            print(f"ERROR: Handler '{handler_name}' not found", file=sys.stderr)
            return None

    # Otherwise use regex fix
    return apply_regex_fix(line, pattern_config)


def find_target_line(
    lines: List[str],
    target_line_num: int,
    expected_excerpt: str
) -> Tuple[int, bool]:
    """
    Find the target line, searching nearby lines if exact match fails.

    Returns:
      (actual_line_index, found) where found=True if line matches expected excerpt
    """
    # Convert to 0-based index
    target_idx = target_line_num - 1

    # Try exact match first
    if 0 <= target_idx < len(lines):
        actual_line = lines[target_idx].rstrip('\n')
        if expected_excerpt in actual_line or actual_line.strip() == expected_excerpt.strip():
            return target_idx, True

    # Search nearby lines (±2)
    for offset in [-2, -1, 1, 2]:
        candidate_idx = target_idx + offset
        if 0 <= candidate_idx < len(lines):
            actual_line = lines[candidate_idx].rstrip('\n')
            if expected_excerpt in actual_line or actual_line.strip() == expected_excerpt.strip():
                return candidate_idx, True

    # Not found
    return target_idx, False


def generate_diff(
    original_line: str,
    fixed_line: str,
    line_num: int,
    context_before: List[str] = None,
    context_after: List[str] = None
) -> str:
    """Generate a unified diff snippet for the change."""
    context_before = context_before or []
    context_after = context_after or []

    diff_lines = []

    # Context before
    for i, ctx_line in enumerate(context_before):
        diff_lines.append(f" {ctx_line.rstrip()}")

    # The change
    diff_lines.append(f"-{original_line.rstrip()}")
    diff_lines.append(f"+{fixed_line.rstrip()}")

    # Context after
    for ctx_line in context_after:
        diff_lines.append(f" {ctx_line.rstrip()}")

    return "\n".join(diff_lines)


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Apply a single mechanical Python 2→3 pattern fix"
    )
    parser.add_argument(
        "-w", "--work-item",
        required=True,
        help="Path to work-item JSON file, or inline JSON string"
    )
    parser.add_argument(
        "-s", "--source-file",
        help="Path to source file (overrides work item's file field)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print diff without applying changes"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory for result JSON"
    )

    args = parser.parse_args()

    # Load work item
    try:
        work_item = load_work_item(args.work_item)
    except Exception as e:
        print(f"ERROR: Failed to load work item: {e}", file=sys.stderr)
        sys.exit(2)

    # Determine source file path
    source_file = args.source_file or work_item.get("source_file")
    if not source_file:
        result = {
            "status": "error",
            "work_item_id": work_item.get("id", "unknown"),
            "pattern": work_item.get("pattern_name", "unknown"),
            "error_details": {
                "type": "missing_source_file",
                "message": "No source file specified and not found in work item"
            }
        }
        print(json.dumps(result, indent=2))
        sys.exit(2)

    # Ensure source file path is absolute
    source_file = os.path.abspath(source_file)

    # Read source file
    if not os.path.isfile(source_file):
        result = {
            "status": "error",
            "work_item_id": work_item.get("id", "unknown"),
            "pattern": work_item.get("pattern_name", "unknown"),
            "file": source_file,
            "error_details": {
                "type": "file_not_found",
                "path": source_file,
                "message": f"File does not exist: {source_file}"
            }
        }
        print(json.dumps(result, indent=2))
        sys.exit(2)

    try:
        with open(source_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        result = {
            "status": "error",
            "work_item_id": work_item.get("id", "unknown"),
            "pattern": work_item.get("pattern_name", "unknown"),
            "file": source_file,
            "error_details": {
                "type": "read_error",
                "path": source_file,
                "message": str(e)
            }
        }
        print(json.dumps(result, indent=2))
        sys.exit(2)

    # Extract work item fields
    pattern_name = work_item.get("pattern_name")
    target_line_num = work_item.get("target_line", 1)
    expected_excerpt = work_item.get("expected_excerpt", "")

    # Validate pattern
    if pattern_name not in PATTERN_FIXES:
        result = {
            "status": "error",
            "work_item_id": work_item.get("id", "unknown"),
            "pattern": pattern_name,
            "file": source_file,
            "error_details": {
                "type": "unsupported_pattern",
                "pattern": pattern_name,
                "message": f"Pattern '{pattern_name}' is not supported"
            }
        }
        print(json.dumps(result, indent=2))
        sys.exit(2)

    # Find target line (search nearby if exact match fails)
    actual_line_idx, found = find_target_line(lines, target_line_num, expected_excerpt)

    if not found:
        # Pattern didn't match — stale work item
        actual_line = lines[actual_line_idx].rstrip('\n') if 0 <= actual_line_idx < len(lines) else ""
        result = {
            "status": "skipped",
            "work_item_id": work_item.get("id", "unknown"),
            "pattern": pattern_name,
            "file": source_file,
            "line": actual_line_idx + 1,
            "error_details": {
                "reason": "pattern_mismatch",
                "expected": expected_excerpt,
                "actual": actual_line,
                "message": "Expected pattern not found at target line or nearby. Work item may be stale."
            }
        }
        print(json.dumps(result, indent=2))
        sys.exit(0)

    # Apply the fix
    original_line = lines[actual_line_idx]
    fixed_line = apply_fix_to_line(original_line, pattern_name)

    if fixed_line is None or fixed_line == original_line:
        # Fix didn't apply
        result = {
            "status": "skipped",
            "work_item_id": work_item.get("id", "unknown"),
            "pattern": pattern_name,
            "file": source_file,
            "line": actual_line_idx + 1,
            "original_line": original_line.rstrip('\n'),
            "error_details": {
                "reason": "fix_not_applicable",
                "message": f"Pattern '{pattern_name}' could not be applied to the line"
            }
        }
        print(json.dumps(result, indent=2))
        sys.exit(0)

    # Get context for diff
    context_before = []
    context_after = []
    if actual_line_idx > 0:
        context_before = lines[max(0, actual_line_idx - 2):actual_line_idx]
    if actual_line_idx < len(lines) - 1:
        context_after = lines[actual_line_idx + 1:min(len(lines), actual_line_idx + 3)]

    diff = generate_diff(
        original_line,
        fixed_line,
        actual_line_idx + 1,
        context_before,
        context_after
    )

    # Prepare result
    result = {
        "status": "fixed",
        "work_item_id": work_item.get("id", "unknown"),
        "pattern": pattern_name,
        "file": source_file,
        "line": actual_line_idx + 1,
        "original_line": original_line.rstrip('\n'),
        "fixed_line": fixed_line.rstrip('\n'),
        "diff": diff
    }

    # Apply fix to file (unless dry-run)
    if not args.dry_run:
        lines[actual_line_idx] = fixed_line
        try:
            with open(source_file, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        except Exception as e:
            result["status"] = "error"
            result["error_details"] = {
                "type": "write_error",
                "path": source_file,
                "message": str(e)
            }
            print(json.dumps(result, indent=2))
            sys.exit(2)

    # Write result JSON if output directory specified
    if args.output:
        output_dir = os.path.abspath(args.output)
        os.makedirs(output_dir, exist_ok=True)
        result_file = os.path.join(output_dir, "result.json")
        try:
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2)
        except Exception as e:
            print(f"WARNING: Could not write result file: {e}", file=sys.stderr)

    # Print result to stdout
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
