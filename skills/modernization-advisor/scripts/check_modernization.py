#!/usr/bin/env python3
"""
Modernization Advisor - Deterministic Checker Script

Scans Python 3 source code for known modernization opportunities using a lookup table
of regex-based detectors. No LLM needed for simple pattern matching. Complex architectural
suggestions are flagged for Sonnet review.

Inputs:
  --source-dir / -s: Path to source directory (post-migration Python 3 code)
  --raw-scan / -r: Path to raw-scan.json (optional, for richer analysis)
  --target-version / -v: Target Python version (default: "3.12")
  --output / -o: Output directory

Outputs:
  - modernization-opportunities.json: All found opportunities with file, line, rule, effort, risk
  - flagged-for-review.json: Complex opportunities needing Sonnet analysis
  - stdout: JSON summary with counts by category, effort distribution, flagged items
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ============================================================================
# Modernization Rules Lookup Table (Deterministic)
# ============================================================================

MODERNIZATION_RULES = {
    "six_removal": {
        "detect": r"import\s+six|from\s+six",
        "category": "library",
        "effort": "low",
        "description": "Remove six compatibility library (no longer needed post-migration)",
        "risk": "low",
    },
    "future_removal": {
        "detect": r"from\s+__future__\s+import",
        "category": "cleanup",
        "effort": "low",
        "description": "Remove __future__ imports (all are default in Python 3)",
        "risk": "low",
    },
    "os_path_to_pathlib": {
        "detect": r"os\.path\.(join|exists|isdir|isfile|basename|dirname|splitext|abspath|realpath)",
        "category": "idiom",
        "effort": "medium",
        "description": "Replace os.path calls with pathlib.Path methods",
        "risk": "low",
        "min_version": "3.4",
    },
    "format_to_fstring": {
        "detect": r'["\'].*?\{.*?\}.*?["\']\.format\(|%\s*["\(]',
        "category": "idiom",
        "effort": "medium",
        "description": "Replace .format() and % formatting with f-strings",
        "risk": "low",
        "min_version": "3.6",
    },
    "type_hints_builtin": {
        "detect": r"from\s+typing\s+import\s+(List|Dict|Tuple|Set|Optional|Union)",
        "category": "idiom",
        "effort": "low",
        "description": "Use built-in generics (list[str]) instead of typing.List[str]",
        "risk": "low",
        "min_version": "3.9",
    },
    "walrus_operator": {
        "detect": r"(\w+)\s*=\s*(.+)\n\s*if\s+\1",
        "category": "idiom",
        "effort": "low",
        "description": "Use walrus operator (:=) for assign-and-test patterns",
        "risk": "low",
        "min_version": "3.8",
    },
    "dataclass": {
        "detect": r"class\s+\w+.*?:\s*\n\s+def\s+__init__\(self,\s*(?:\w+,?\s*){3,}",
        "category": "pattern",
        "effort": "medium",
        "description": "Convert data-holder classes to @dataclass",
        "risk": "medium",
        "min_version": "3.7",
    },
    "contextmanager": {
        "detect": r"\.open\(.*?\)(?!.*\bwith\b)",
        "category": "pattern",
        "effort": "low",
        "description": "Use 'with' statement for resource management",
        "risk": "low",
    },
    "enumerate_usage": {
        "detect": r"range\(len\(",
        "category": "idiom",
        "effort": "low",
        "description": "Replace range(len(x)) with enumerate(x)",
        "risk": "low",
    },
    "dict_comprehension": {
        "detect": r"dict\(\s*\[?\s*\(",
        "category": "idiom",
        "effort": "low",
        "description": "Use dict comprehension instead of dict() constructor with list",
        "risk": "low",
    },
    "match_statement": {
        "detect": r"if\s+\w+\s*==\s*.+?:\s*\n(?:\s+elif\s+\w+\s*==\s*.+?:\s*\n){3,}",
        "category": "pattern",
        "effort": "high",
        "description": "Consider match/case statement for long if/elif chains",
        "risk": "medium",
        "min_version": "3.10",
        "needs_review": True,
    },
    "exception_groups": {
        "detect": r"except\s+\(.*?,.*?,.*?\)",
        "category": "pattern",
        "effort": "medium",
        "description": "Consider ExceptionGroup for multiple exception handling",
        "risk": "medium",
        "min_version": "3.11",
        "needs_review": True,
    },
    "urllib2_to_requests": {
        "detect": r"urllib\.request\.(urlopen|Request)",
        "category": "library",
        "effort": "medium",
        "description": "Consider replacing urllib with requests library for cleaner HTTP",
        "risk": "low",
        "needs_review": True,
    },
}

# ============================================================================
# Version Comparison Utility
# ============================================================================


def parse_version(version_str: str) -> Tuple[int, ...]:
    """Parse version string like '3.12' into tuple (3, 12)."""
    return tuple(int(x) for x in version_str.split("."))


def meets_min_version(target_version: str, min_version: Optional[str]) -> bool:
    """Check if target_version >= min_version."""
    if min_version is None:
        return True
    return parse_version(target_version) >= parse_version(min_version)


# ============================================================================
# Data Models
# ============================================================================


@dataclass
class Opportunity:
    """Represents a single modernization opportunity."""

    id: str
    rule: str
    category: str
    file: str
    line: int
    context: str
    description: str
    effort: str
    risk: str
    needs_review: bool = False


# ============================================================================
# File Scanning Logic
# ============================================================================


def read_python_files(source_dir: Path) -> List[Tuple[Path, str]]:
    """
    Walk source directory and yield (file_path, content) for all .py files.
    """
    files = []
    for py_file in source_dir.rglob("*.py"):
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
            files.append((py_file, content))
        except Exception as e:
            logging.warning(f"Failed to read {py_file}: {e}")
    return files


def find_line_and_context(
    content: str, file_path: Path, line_num: int, context_width: int = 60
) -> str:
    """Extract line context for a match."""
    lines = content.split("\n")
    if line_num < 1 or line_num > len(lines):
        return ""
    line = lines[line_num - 1]
    # Truncate long lines
    if len(line) > context_width:
        return line[:context_width] + "..."
    return line


def detect_modernization_opportunities(
    file_path: Path,
    content: str,
    target_version: str,
    rule_id_counter: Dict[str, int],
) -> List[Opportunity]:
    """
    Scan a single file for modernization opportunities using regex-based rules.
    Returns a list of Opportunity objects.
    """
    opportunities = []
    lines = content.split("\n")

    for rule_name, rule_config in MODERNIZATION_RULES.items():
        # Check if target version meets minimum requirement
        min_version = rule_config.get("min_version")
        if not meets_min_version(target_version, min_version):
            continue

        pattern = rule_config["detect"]
        try:
            regex = re.compile(pattern, re.MULTILINE | re.DOTALL)
        except re.error as e:
            logging.warning(f"Invalid regex in rule {rule_name}: {e}")
            continue

        # Find all matches
        for match in regex.finditer(content):
            # Determine line number from match position
            line_num = content[:match.start()].count("\n") + 1

            # Extract context
            context = find_line_and_context(content, file_path, line_num)

            # Generate unique ID
            rule_id_counter[rule_name] = rule_id_counter.get(rule_name, 0) + 1
            opp_id = f"MOD-{len(opportunities):04d}"

            opp = Opportunity(
                id=opp_id,
                rule=rule_name,
                category=rule_config["category"],
                file=str(file_path.relative_to(file_path.parent.parent.parent)),
                line=line_num,
                context=context,
                description=rule_config["description"],
                effort=rule_config["effort"],
                risk=rule_config["risk"],
                needs_review=rule_config.get("needs_review", False),
            )
            opportunities.append(opp)

    return opportunities


# ============================================================================
# Analysis and Summary
# ============================================================================


def compute_summary_stats(opportunities: List[Opportunity]) -> Dict[str, Any]:
    """Compute summary statistics from opportunities list."""
    stats = {
        "total_opportunities": len(opportunities),
        "by_category": defaultdict(int),
        "by_effort": defaultdict(int),
        "by_risk": defaultdict(int),
        "by_rule": defaultdict(int),
        "flagged_for_review": 0,
    }

    for opp in opportunities:
        stats["by_category"][opp.category] += 1
        stats["by_effort"][opp.effort] += 1
        stats["by_risk"][opp.risk] += 1
        stats["by_rule"][opp.rule] += 1
        if opp.needs_review:
            stats["flagged_for_review"] += 1

    # Convert defaultdicts to regular dicts for JSON serialization
    return {
        "total_opportunities": stats["total_opportunities"],
        "by_category": dict(stats["by_category"]),
        "by_effort": dict(stats["by_effort"]),
        "by_risk": dict(stats["by_risk"]),
        "by_rule": dict(stats["by_rule"]),
        "flagged_for_review": stats["flagged_for_review"],
    }


def sort_opportunities(opportunities: List[Opportunity]) -> List[Opportunity]:
    """
    Sort opportunities by: effort (low first), then risk (low first), then file, then line.
    This prioritizes easy, low-risk wins.
    """
    effort_order = {"low": 0, "medium": 1, "high": 2}
    risk_order = {"low": 0, "medium": 1, "high": 2}

    return sorted(
        opportunities,
        key=lambda x: (
            effort_order.get(x.effort, 999),
            risk_order.get(x.risk, 999),
            x.file,
            x.line,
        ),
    )


# ============================================================================
# Output Generation
# ============================================================================


def write_opportunities_json(
    output_dir: Path, opportunities: List[Opportunity]
) -> None:
    """Write all opportunities to modernization-opportunities.json."""
    output_file = output_dir / "modernization-opportunities.json"
    data = {
        "opportunities": [asdict(opp) for opp in opportunities],
        "count": len(opportunities),
    }
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)
    logging.info(f"Wrote {len(opportunities)} opportunities to {output_file}")


def write_flagged_for_review_json(
    output_dir: Path, opportunities: List[Opportunity]
) -> None:
    """Write opportunities flagged for Sonnet review."""
    flagged = [opp for opp in opportunities if opp.needs_review]
    output_file = output_dir / "flagged-for-review.json"
    data = {
        "flagged_opportunities": [asdict(opp) for opp in flagged],
        "count": len(flagged),
        "note": "These opportunities require deeper analysis by Sonnet model",
    }
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)
    logging.info(f"Wrote {len(flagged)} flagged items to {output_file}")


def write_summary_to_stdout(summary: Dict[str, Any]) -> None:
    """Print summary as JSON to stdout."""
    print(json.dumps(summary, indent=2))


# ============================================================================
# Main Entry Point
# ============================================================================


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Scan Python code for modernization opportunities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python check_modernization.py -s ./src -o ./output
  python check_modernization.py -s ./src -v 3.11 -o ./output
  python check_modernization.py -s ./src -r ./raw-scan.json -o ./output
        """,
    )

    parser.add_argument(
        "-s",
        "--source-dir",
        required=True,
        type=Path,
        help="Path to source directory (post-migration Python 3 code)",
    )
    parser.add_argument(
        "-r",
        "--raw-scan",
        type=Path,
        help="Path to raw-scan.json (optional, for richer analysis)",
    )
    parser.add_argument(
        "-v",
        "--target-version",
        default="3.12",
        help="Target Python version (default: 3.12)",
    )
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        type=Path,
        help="Output directory for results",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.source_dir.exists():
        logging.error(f"Source directory does not exist: {args.source_dir}")
        sys.exit(1)

    if not args.source_dir.is_dir():
        logging.error(f"Source path is not a directory: {args.source_dir}")
        sys.exit(1)

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    logging.info(f"Scanning source directory: {args.source_dir}")
    logging.info(f"Target Python version: {args.target_version}")

    # Read all Python files
    py_files = read_python_files(args.source_dir)
    logging.info(f"Found {len(py_files)} Python files")

    # Scan for opportunities
    all_opportunities = []
    rule_id_counter = {}

    for file_path, content in py_files:
        opps = detect_modernization_opportunities(
            file_path, content, args.target_version, rule_id_counter
        )
        all_opportunities.extend(opps)
        if opps:
            logging.info(f"  {file_path.name}: {len(opps)} opportunity(ies) found")

    # Sort opportunities
    all_opportunities = sort_opportunities(all_opportunities)

    # Rewrite IDs after sorting
    for idx, opp in enumerate(all_opportunities):
        opp.id = f"MOD-{idx:04d}"

    # Compute summary
    summary = compute_summary_stats(all_opportunities)

    # Write outputs
    write_opportunities_json(args.output, all_opportunities)
    write_flagged_for_review_json(args.output, all_opportunities)
    write_summary_to_stdout(summary)

    logging.info("Modernization check complete")


if __name__ == "__main__":
    main()
