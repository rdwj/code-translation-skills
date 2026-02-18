#!/usr/bin/env python3
"""
Work Item Generator: Decompose migration analysis outputs into atomic, executable work items.

This script is FULLY DETERMINISTIC — zero LLM involvement. It takes migration analysis outputs
and produces atomic work items routed to model tiers based on pattern complexity.

Inputs:
  - raw-scan.json: Pattern inventory from codebase-analyzer
  - dependency-graph.json: Module dependency structure
  - conversion-plan.json: Ordered conversion units (optional)
  - behavioral-contracts.json: Per-function behavioral specs (optional)

Outputs:
  - work-items.json: All work items sorted by wave, file, line
  - work-item-summary.json: Counts by tier, estimated token costs, distribution
  - stdout: JSON summary with item counts and status

Exit codes:
  0: Success
  1: Items flagged for review
  2: Error
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict
import re

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


# ============================================================================
# Pattern Classification: Haiku, Sonnet, Opus
# ============================================================================

HAIKU_PATTERNS = {
    'has_key', 'iteritems', 'itervalues', 'iterkeys', 'xrange', 'raw_input',
    'print_statement', 'except_syntax', 'raise_syntax', 'octal_literal',
    'long_suffix', 'backtick_repr', 'ne_operator', 'exec_statement',
    'stdlib_rename', 'future_import', 'oldstyle_class', 'unicode_call'
}

SONNET_PATTERNS = {
    'metaclass', 'string_bytes_mixing', 'struct_usage', 'pickle_usage',
    'encode_decode', 'dynamic_import', 'division_int', 'dict_keys_index',
    'map_filter_zip_consumption', 'cmp_usage', 'getslice', 'buffer_usage',
    'nonzero_method'
}

OPUS_PATTERNS = {
    'c_extension_usage', 'custom_codec', 'thread_safety', 'monkey_patching'
}

# Token costs per item (rough estimates)
TOKEN_COSTS = {
    'haiku': 200,
    'sonnet': 500,
    'opus': 1000
}

# Time estimates per item (minutes)
TIME_ESTIMATES = {
    'haiku': 1.8,
    'sonnet': 3.2,
    'opus': 6.5
}


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class WorkItem:
    """Atomic work item for pattern conversion."""
    id: str
    type: str  # pattern_fix, semantic_fix, architectural
    model_tier: str  # haiku, sonnet, opus
    pattern: str
    file: str  # relative path
    line: int
    function: Optional[str]
    context: str  # the line of code
    conversion_unit: Optional[str]
    wave: int
    priority: int = 0
    estimated_tokens: int = 0
    tags: List[str] = None

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


# ============================================================================
# Input Parsers
# ============================================================================

def load_json_file(filepath: Path) -> Dict[str, Any]:
    """Load JSON file with error handling."""
    try:
        if not filepath.exists():
            logger.warning(f"File not found: {filepath}")
            return {}
        with open(filepath, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {filepath}: {e}")
        return {}
    except Exception as e:
        logger.error(f"Error reading {filepath}: {e}")
        return {}


def parse_raw_scan(scan_data: Dict[str, Any]) -> Dict[str, List[Dict]]:
    """
    Extract pattern inventory from raw-scan.json.

    Expected structure:
    {
        "summary": {...},
        "patterns": {
            "src/file.py": [
                {"pattern": "print_statement", "line": 42, "severity": "high", "context": "..."}
            ]
        }
    }
    """
    patterns_by_file = defaultdict(list)
    patterns = scan_data.get('patterns', {})

    for filepath, occurrences in patterns.items():
        if isinstance(occurrences, list):
            patterns_by_file[filepath] = occurrences

    return patterns_by_file


def parse_dependency_graph(graph_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract module structure and imports.

    Expected structure:
    {
        "modules": {
            "src/utils/common.py": {
                "imports": ["sys", "os"],
                "functions": ["func1", "func2"],
                "dependencies": []
            }
        }
    }
    """
    return graph_data.get('modules', {})


def parse_conversion_plan(plan_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract conversion units and wave ordering.

    Expected structure:
    {
        "units": [
            {
                "id": "utils-common",
                "wave": 1,
                "files": ["src/utils/common.py"]
            }
        ]
    }
    """
    return plan_data.get('units', [])


def parse_behavioral_contracts(contracts_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract per-function behavioral specifications."""
    return contracts_data.get('functions', {})


# ============================================================================
# Pattern Classification
# ============================================================================

def classify_pattern(pattern: str) -> str:
    """
    Classify pattern to model tier: haiku, sonnet, or opus.

    Args:
        pattern: Pattern name (e.g., 'print_statement', 'metaclass')

    Returns:
        Model tier: 'haiku', 'sonnet', or 'opus'
    """
    if pattern in HAIKU_PATTERNS:
        return 'haiku'
    elif pattern in SONNET_PATTERNS:
        return 'sonnet'
    elif pattern in OPUS_PATTERNS:
        return 'opus'
    else:
        # Default to Haiku for unknown patterns
        logger.warning(f"Unknown pattern '{pattern}', defaulting to haiku")
        return 'haiku'


def determine_work_item_type(pattern: str) -> str:
    """
    Determine work item type based on pattern.

    Returns:
        'pattern_fix', 'semantic_fix', or 'architectural'
    """
    if pattern in HAIKU_PATTERNS:
        return 'pattern_fix'
    elif pattern in SONNET_PATTERNS:
        return 'semantic_fix'
    else:
        return 'architectural'


# ============================================================================
# Work Item Generation
# ============================================================================

def generate_work_items(
    patterns_by_file: Dict[str, List[Dict]],
    modules: Dict[str, Any],
    units: List[Dict[str, Any]],
    contracts: Dict[str, Any]
) -> List[WorkItem]:
    """
    Generate work items from pattern occurrences.

    Args:
        patterns_by_file: Pattern inventory by file
        modules: Module structure and imports
        units: Conversion unit plan
        contracts: Behavioral contracts

    Returns:
        List of WorkItem objects
    """
    work_items: List[WorkItem] = []
    item_id_counter = 1

    # Build file-to-unit mapping
    file_to_unit: Dict[str, Tuple[str, int]] = {}
    for unit in units:
        unit_id = unit.get('id', f'unit-{len(file_to_unit)}')
        wave = unit.get('wave', 1)
        for filepath in unit.get('files', []):
            file_to_unit[filepath] = (unit_id, wave)

    # Process each file's patterns
    for filepath in sorted(patterns_by_file.keys()):
        occurrences = patterns_by_file[filepath]
        unit_id, wave = file_to_unit.get(filepath, ('unknown', 1))

        # Get module info
        module_info = modules.get(filepath, {})
        imports = module_info.get('imports', [])
        functions_in_file = module_info.get('functions', {})

        # Sort occurrences by line number
        sorted_occurrences = sorted(occurrences, key=lambda x: x.get('line', 0))

        # Create work item for each occurrence
        for occurrence in sorted_occurrences:
            pattern = occurrence.get('pattern', 'unknown')
            line = occurrence.get('line', 0)
            context = occurrence.get('context', '')

            # Determine which function this line is in
            function_name = None
            for func_name, func_info in functions_in_file.items():
                func_start = func_info.get('start_line', 0)
                func_end = func_info.get('end_line', float('inf'))
                if func_start <= line <= func_end:
                    function_name = func_name
                    break

            # Classify pattern
            model_tier = classify_pattern(pattern)
            item_type = determine_work_item_type(pattern)

            # Estimate tokens
            estimated_tokens = TOKEN_COSTS.get(model_tier, 200)

            # Create work item
            item = WorkItem(
                id=f'WI-{item_id_counter:06d}',
                type=item_type,
                model_tier=model_tier,
                pattern=pattern,
                file=filepath,
                line=line,
                function=function_name,
                context=context,
                conversion_unit=unit_id,
                wave=wave,
                estimated_tokens=estimated_tokens,
                tags=[item_type, 'automatable' if model_tier == 'haiku' else 'requires_review']
            )

            work_items.append(item)
            item_id_counter += 1

    return work_items


# ============================================================================
# Work Item Ordering
# ============================================================================

def sort_work_items(items: List[WorkItem]) -> List[WorkItem]:
    """
    Sort work items for optimal context reuse and execution order.

    Order by:
    1. Wave (ascending)
    2. File (to group by file for context reuse)
    3. Type (pattern_fix before semantic_fix before architectural)
    4. Line number (top to bottom within file)
    """
    type_priority = {
        'pattern_fix': 0,
        'semantic_fix': 1,
        'architectural': 2
    }

    sorted_items = sorted(
        items,
        key=lambda x: (
            x.wave,
            x.file,
            type_priority.get(x.type, 99),
            x.line
        )
    )

    # Assign priority numbers
    for idx, item in enumerate(sorted_items, start=1):
        item.priority = idx

    return sorted_items


# ============================================================================
# Summary Generation
# ============================================================================

def generate_summary(work_items: List[WorkItem]) -> Dict[str, Any]:
    """Generate summary statistics from work items."""

    # Count by tier
    by_tier = defaultdict(int)
    tokens_by_tier = defaultdict(int)
    cost_by_tier = defaultdict(float)
    time_by_tier = defaultdict(float)

    # Count by type
    by_type = defaultdict(int)

    # Count by wave
    by_wave = defaultdict(int)

    # Count by pattern
    by_pattern = defaultdict(int)

    haiku_cost_per_mtok = 0.001  # $0.001 per 1M tokens (rough)
    sonnet_cost_per_mtok = 0.003
    opus_cost_per_mtok = 0.015

    cost_multiplier = {
        'haiku': haiku_cost_per_mtok,
        'sonnet': sonnet_cost_per_mtok,
        'opus': opus_cost_per_mtok
    }

    for item in work_items:
        by_tier[item.model_tier] += 1
        tokens_by_tier[item.model_tier] += item.estimated_tokens
        cost_by_tier[item.model_tier] += item.estimated_tokens * cost_multiplier.get(item.model_tier, 0)
        time_by_tier[item.model_tier] += TIME_ESTIMATES.get(item.model_tier, 2.0)

        by_type[item.type] += 1
        by_wave[item.wave] += 1
        by_pattern[item.pattern] += 1

    total_items = len(work_items)
    total_tokens = sum(tokens_by_tier.values())
    total_cost = sum(cost_by_tier.values())

    # Build summary
    summary = {
        'status': 'success',
        'total_work_items': total_items,
        'total_estimated_tokens': total_tokens,
        'total_estimated_cost_usd': round(total_cost, 2),
        'by_tier': {
            tier: {
                'count': by_tier[tier],
                'percent': round(100 * by_tier[tier] / total_items, 1) if total_items > 0 else 0,
                'estimated_tokens': tokens_by_tier[tier],
                'estimated_cost_usd': round(cost_by_tier[tier], 2),
                'avg_tokens_per_item': round(tokens_by_tier[tier] / by_tier[tier], 0) if by_tier[tier] > 0 else 0,
                'avg_time_minutes': round(time_by_tier[tier] / by_tier[tier], 1) if by_tier[tier] > 0 else 0
            }
            for tier in ['haiku', 'sonnet', 'opus']
        },
        'by_type': {
            wtype: {
                'count': by_type[wtype],
                'percent': round(100 * by_type[wtype] / total_items, 1) if total_items > 0 else 0
            }
            for wtype in sorted(by_type.keys())
        },
        'by_wave': {
            wave: by_wave[wave]
            for wave in sorted(by_wave.keys())
        },
        'top_patterns': sorted(
            [(pattern, count) for pattern, count in by_pattern.items()],
            key=lambda x: x[1],
            reverse=True
        )[:10]
    }

    return summary


# ============================================================================
# Output Writing
# ============================================================================

def write_work_items_json(filepath: Path, items: List[WorkItem]) -> None:
    """Write work items to JSON file."""
    try:
        data = {
            'work_items': [item.to_dict() for item in items],
            'metadata': {
                'total': len(items),
                'generated_at': __import__('datetime').datetime.utcnow().isoformat()
            }
        }
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info(f"Wrote {len(items)} work items to {filepath}")
    except Exception as e:
        logger.error(f"Error writing work items: {e}")
        raise


def write_summary_json(filepath: Path, summary: Dict[str, Any]) -> None:
    """Write summary to JSON file."""
    try:
        with open(filepath, 'w') as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Wrote summary to {filepath}")
    except Exception as e:
        logger.error(f"Error writing summary: {e}")
        raise


# ============================================================================
# Main
# ============================================================================

@log_execution
def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Generate atomic work items from migration analysis outputs'
    )

    parser.add_argument(
        '-r', '--raw-scan',
        type=Path,
        required=True,
        help='Path to raw-scan.json (pattern inventory)'
    )
    parser.add_argument(
        '-d', '--dependency-graph',
        type=Path,
        required=True,
        help='Path to dependency-graph.json (module structure)'
    )
    parser.add_argument(
        '-c', '--conversion-plan',
        type=Path,
        default=None,
        help='Path to conversion-plan.json (optional, conversion units)'
    )
    parser.add_argument(
        '-b', '--behavioral-contracts',
        type=Path,
        default=None,
        help='Path to behavioral-contracts.json (optional, function specs)'
    )
    parser.add_argument(
        '-o', '--output',
        type=Path,
        default=Path('.'),
        help='Output directory (default: current directory)'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose logging'
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate inputs
    if not args.raw_scan.exists():
        logger.error(f"raw-scan file not found: {args.raw_scan}")
        return 2

    if not args.dependency_graph.exists():
        logger.error(f"dependency-graph file not found: {args.dependency_graph}")
        return 2

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    try:
        # Load inputs
        logger.info("Loading input files...")
        raw_scan = load_json_file(args.raw_scan)
        dependency_graph = load_json_file(args.dependency_graph)
        conversion_plan = load_json_file(args.conversion_plan) if args.conversion_plan else {}
        behavioral_contracts = load_json_file(args.behavioral_contracts) if args.behavioral_contracts else {}

        # Parse inputs
        logger.info("Parsing input files...")
        patterns_by_file = parse_raw_scan(raw_scan)
        modules = parse_dependency_graph(dependency_graph)
        units = parse_conversion_plan(conversion_plan)
        contracts = parse_behavioral_contracts(behavioral_contracts)

        if not patterns_by_file:
            logger.error("No patterns found in raw-scan.json")
            return 2

        # Generate work items
        logger.info("Generating work items...")
        work_items = generate_work_items(patterns_by_file, modules, units, contracts)

        if not work_items:
            logger.error("No work items generated")
            return 2

        # Sort work items
        logger.info("Sorting work items...")
        work_items = sort_work_items(work_items)

        # Generate summary
        logger.info("Generating summary...")
        summary = generate_summary(work_items)

        # Write outputs
        logger.info("Writing outputs...")
        write_work_items_json(args.output / 'work-items.json', work_items)
        write_summary_json(args.output / 'work-item-summary.json', summary)

        # Print summary to stdout
        print(json.dumps(summary, indent=2))

        return 0

    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 2


if __name__ == '__main__':
    sys.exit(main())
