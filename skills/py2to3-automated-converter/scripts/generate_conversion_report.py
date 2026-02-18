#!/usr/bin/env python3
"""
Automated Converter — Markdown Report Generator

Reads conversion-report.json and produces a human-readable markdown report
showing files converted, transforms applied, errors, and next steps.

Usage:
    python3 generate_conversion_report.py <conversion_report.json> \
        --output <output.md> \
        [--unit-name "utils-common"] \
        [--include-diff]

If --output is omitted, prints to stdout.
"""

import argparse
import json
import os
import sys
from typing import Any, Dict, List
from pathlib import Path

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

def load_report(path: str) -> Dict[str, Any]:
    """Load and validate the conversion report JSON."""
    if not os.path.exists(path):
        print(f"Error: Report file not found: {path}", file=sys.stderr)
        sys.exit(1)
    
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Helpers ───────────────────────────────────────────────────────────────

def _status_emoji(status: str) -> str:
    """Return an emoji for a conversion status."""
    emoji_map = {
        "converted": "✓",
        "converted_dry_run": "⊙",
        "skipped": "⊘",
        "error": "✗",
        "unknown": "?",
    }
    return emoji_map.get(status, "?")


def _category_label(category: str) -> str:
    """Human-readable category label."""
    labels = {
        "syntax": "Syntax",
        "semantic_string": "String/Unicode",
        "semantic_import": "Import",
        "semantic_iterator": "Iterator",
        "semantic_comparison": "Comparison",
        "target_version": "Target Version",
    }
    return labels.get(category, category.replace("_", " ").title())


def _effort_estimate(transform_count: int) -> str:
    """Estimate effort based on transform count."""
    if transform_count == 0:
        return "None"
    elif transform_count < 5:
        return "Low"
    elif transform_count < 15:
        return "Medium"
    else:
        return "High"


# ── Report Rendering ─────────────────────────────────────────────────────

def render_report(
    report: Dict[str, Any],
    unit_name: str = "",
    include_diff: bool = False
) -> str:
    """Render the conversion report as markdown."""
    
    lines: List[str] = []
    
    timestamp = report.get("timestamp", "")[:19]
    target = report.get("target_version", "?")
    files_total = report.get("files_total", 0)
    files_converted = report.get("files_converted", 0)
    files_skipped = report.get("files_skipped", 0)
    files_failed = report.get("files_failed", 0)
    transforms = report.get("transforms_applied", [])
    transform_summary = report.get("transform_summary", {})
    results = report.get("results", [])
    
    # ── Title ────────────────────────────────────────────────────────────
    
    title = f"Conversion Report: {unit_name}" if unit_name else "Conversion Report"
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"**Target**: Python {target}  ")
    lines.append(f"**Generated**: {timestamp}  ")
    lines.append("")
    
    # ── Executive Summary ────────────────────────────────────────────────
    
    lines.append("## Executive Summary")
    lines.append("")
    
    # Status table
    lines.append(
        "| Status | Count | Percentage |"
    )
    lines.append(
        "|--------|-------|-----------|"
    )
    
    lines.append(
        f"| {_status_emoji('converted')} Converted | {files_converted} | "
        f"{round(100 * files_converted / files_total) if files_total > 0 else 0}% |"
    )
    lines.append(
        f"| {_status_emoji('skipped')} Skipped | {files_skipped} | "
        f"{round(100 * files_skipped / files_total) if files_total > 0 else 0}% |"
    )
    lines.append(
        f"| {_status_emoji('error')} Failed | {files_failed} | "
        f"{round(100 * files_failed / files_total) if files_total > 0 else 0}% |"
    )
    lines.append("")
    
    # Overall effort
    total_transforms = len(transforms)
    effort = _effort_estimate(total_transforms)
    lines.append(f"**Total transformations**: {total_transforms}  ")
    lines.append(f"**Review effort**: {effort}  ")
    lines.append("")
    
    # ── Transform Summary ────────────────────────────────────────────────
    
    if transform_summary:
        lines.append("## Transformation Summary")
        lines.append("")
        lines.append(
            "| Transform Type | Count | Description |"
        )
        lines.append(
            "|---|---|---|"
        )
        
        # Sort by count (descending)
        for transform_type, count in sorted(
            transform_summary.items(), key=lambda x: -x[1]
        ):
            desc = _transform_description(transform_type)
            lines.append(f"| `{transform_type}` | {count} | {desc} |")
        
        lines.append("")
    
    # ── Per-File Breakdown ───────────────────────────────────────────────
    
    if results:
        lines.append("## Files Processed")
        lines.append("")
        
        # Converted files
        converted = [r for r in results if r["status"] in ("converted", "converted_dry_run")]
        if converted:
            lines.append("### Converted Files")
            lines.append("")
            lines.append(
                "| File | Transforms | Changes | Status |"
            )
            lines.append(
                "|------|-----------|---------|--------|"
            )
            
            for result in converted:
                file_path = Path(result["file"]).name
                tx_count = len(result.get("transforms", []))
                original = result.get("original_content", "")
                converted_content = result.get("converted_content", "")
                lines_changed = len(set(original.splitlines()) ^ set(converted_content.splitlines()))
                status = result["status"]
                status_emoji = _status_emoji(status)
                
                lines.append(
                    f"| `{file_path}` | {tx_count} | {lines_changed} | {status_emoji} |"
                )
            
            lines.append("")
        
        # Skipped files
        skipped = [r for r in results if r["status"] == "skipped"]
        if skipped:
            lines.append("### Skipped Files")
            lines.append("")
            lines.append("| File | Reason |")
            lines.append("|------|--------|")
            
            for result in skipped:
                file_path = Path(result["file"]).name
                reason = result.get("reason", "no reason")
                lines.append(f"| `{file_path}` | {reason} |")
            
            lines.append("")
        
        # Failed files
        failed = [r for r in results if r["status"] == "error"]
        if failed:
            lines.append("### Failed Files")
            lines.append("")
            lines.append("| File | Error |")
            lines.append("|------|-------|")
            
            for result in failed:
                file_path = Path(result["file"]).name
                errors = result.get("errors", ["Unknown error"])
                error_str = "; ".join(errors)
                lines.append(f"| `{file_path}` | {error_str} |")
            
            lines.append("")
    
    # ── Transforms Needing Review ───────────────────────────────────────
    
    needs_review = [
        t for t in transforms if t.get("needs_review", False)
    ]
    if needs_review:
        lines.append("## Transforms Requiring Manual Review")
        lines.append("")
        lines.append(
            "These transformations may require context-aware adjustments:"
        )
        lines.append("")
        
        for transform in needs_review:
            file_path = Path(transform.get("file", "?")).name
            desc = transform.get("description", "?")
            lines.append(f"- **{file_path}**: {desc}")
        
        lines.append("")
    
    # ── Next Steps ───────────────────────────────────────────────────────
    
    lines.append("## Next Steps")
    lines.append("")
    
    if files_failed > 0:
        lines.append("### 1. Resolve Errors")
        lines.append("")
        lines.append(
            "The following files failed to convert. Review the errors above and fix them:"
        )
        for result in results:
            if result["status"] == "error":
                lines.append(f"- `{result['file']}`")
        lines.append("")
    
    if needs_review:
        lines.append(f"### {2 if files_failed > 0 else 1}. Manual Review")
        lines.append("")
        lines.append(
            "The following transformations need human judgment to ensure correctness:"
        )
        for transform in needs_review:
            lines.append(f"- {transform.get('description', '?')}")
        lines.append("")
    
    step_num = 3 if (files_failed > 0 or needs_review) else 1
    lines.append(f"### {step_num}. Run Tests")
    lines.append("")
    lines.append(
        "Run the converted code through your test suite to verify correctness:"
    )
    lines.append("")
    lines.append("```bash")
    lines.append("python3 -m pytest <converted_dir>")
    lines.append("python3 -m pylint <converted_dir>")
    lines.append("```")
    lines.append("")
    
    step_num += 1
    lines.append(f"### {step_num}. Validate Diff")
    lines.append("")
    lines.append(
        "Review `conversion-diff.patch` to ensure all changes are as expected:"
    )
    lines.append("")
    lines.append("```bash")
    lines.append("diff -u <original> <converted> | head -100")
    lines.append("```")
    lines.append("")
    
    step_num += 1
    lines.append(f"### {step_num}. Advance to Phase 3")
    lines.append("")
    lines.append(
        "Once validated, the converted code is ready for semantic analysis and testing "
        "(Phase 3: Semantic Validator)."
    )
    lines.append("")
    
    return "\n".join(lines)


def _transform_description(transform_type: str) -> str:
    """Get a human-readable description for a transform type."""
    descriptions = {
        "print_statement": "Print statement → function",
        "except_syntax": "Except comma → as",
        "xrange": "xrange() → range()",
        "lib2to3_error": "lib2to3 error (needs manual fix)",
        "lib2to3_refactor": "lib2to3 refactoring",
        "unicode_builtin": "unicode() → str()",
        "raw_input": "raw_input() → input()",
        "long_builtin": "long() → int()",
        "basestring": "basestring → str",
        "distutils_migration": "distutils → setuptools",
        "stdlib_removal_3_12": "stdlib module removed in 3.12+",
    }
    return descriptions.get(transform_type, transform_type.replace("_", " ").title())


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Generate a markdown report from a conversion report JSON."
    )
    parser.add_argument(
        "report_file",
        help="Path to conversion-report.json",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for markdown report (prints to stdout if omitted)",
    )
    parser.add_argument(
        "--unit-name",
        default="",
        help="Unit name for the report title",
    )
    parser.add_argument(
        "--include-diff",
        action="store_true",
        help="Include diffs in the report (creates a large report)",
    )
    
    args = parser.parse_args()
    
    report = load_report(args.report_file)
    markdown = render_report(report, args.unit_name, args.include_diff)
    
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown, encoding="utf-8")
        print(f"Conversion report written to {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
