#!/usr/bin/env python3
"""
Script: phase3_semantic.py
Purpose: Prepare semantic review brief for LLM - no execution, just curation
Inputs: work-items.json from phase 2, raw-scan.json from phase 0
Outputs: semantic-review-brief.json (focused list for Sonnet/Opus review)
LLM involvement: PREPARES brief for LLM review (zero orchestration cost)
"""

import argparse
import json
import sys
from pathlib import Path


def phase3_semantic(work_items_path, raw_scan_path, output_dir):
    """Prepare semantic review brief."""
    print(f"\n[PHASE 3] Semantic - Prepare LLM review brief", file=sys.stderr)
    print(f"  Work items: {work_items_path}", file=sys.stderr)
    print(f"  Raw scan: {raw_scan_path}", file=sys.stderr)
    print(f"  Output dir: {output_dir}", file=sys.stderr)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load work items
    work_items = []
    work_items_path = Path(work_items_path)
    if work_items_path.exists():
        try:
            with open(work_items_path) as f:
                data = json.load(f)
                work_items = data.get("items", [])
                print(f"  Loaded {len(work_items)} work items", file=sys.stderr)
        except Exception as e:
            print(f"  Warning: Could not load work items: {e}", file=sys.stderr)
            work_items = []
    else:
        print(f"  Warning: work-items.json not found at {work_items_path}", file=sys.stderr)

    # Load raw scan for pattern reference
    patterns = {}
    raw_scan_path = Path(raw_scan_path)
    if raw_scan_path.exists():
        try:
            with open(raw_scan_path) as f:
                data = json.load(f)
                patterns = data.get("patterns", {})
                print(f"  Loaded scan patterns", file=sys.stderr)
        except Exception as e:
            print(f"  Warning: Could not load raw scan: {e}", file=sys.stderr)

    # Filter to items requiring LLM review
    # SONNET_PATTERNS and OPUS_PATTERNS require semantic analysis
    sonnet_items = []
    opus_items = []
    skipped_items = 0

    sonnet_pattern_types = [
        "bytes_string_handling",
        "dynamic_type_checking",
        "protocol_definitions",
        "metaclass_usage",
    ]

    opus_pattern_types = [
        "complex_bytes_string_transitions",
        "reflection_serialization",
        "c_extension_adaptation",
        "pickle_format_migration",
    ]

    for item in work_items:
        item_type = item.get("type", "").lower()
        tier = item.get("tier", "").upper()

        if tier == "SONNET":
            sonnet_items.append(item)
        elif tier == "OPUS":
            opus_items.append(item)
        else:
            skipped_items += 1

    # Build review brief
    brief = {
        "phase": "semantic",
        "purpose": "Curated work items requiring LLM reasoning for bytes/string analysis and dynamic patterns",
        "total_items_in_project": len(work_items),
        "items_requiring_llm": len(sonnet_items) + len(opus_items),
        "sonnet_tier": {
            "count": len(sonnet_items),
            "description": "Medium-complexity semantic patterns requiring Sonnet-level reasoning",
            "items": sonnet_items[:20],  # Limit to first 20 for brevity
            "note": f"Total {len(sonnet_items)} items; showing first 20",
        },
        "opus_tier": {
            "count": len(opus_items),
            "description": "High-complexity patterns requiring Opus-level reasoning (reflection, serialization, C extensions)",
            "items": opus_items[:20],  # Limit to first 20 for brevity
            "note": f"Total {len(opus_items)} items; showing first 20",
        },
        "summary": {
            "automated_items": skipped_items,
            "llm_review_items": len(sonnet_items) + len(opus_items),
            "estimated_llm_tokens": (len(sonnet_items) * 300) + (len(opus_items) * 500),
            "recommendation": (
                "Run Sonnet tier first for efficient cost, then escalate remaining Opus items "
                "if Sonnet classification is uncertain"
            ),
        },
    }

    # Write brief to file
    with open(output_dir / "semantic-review-brief.json", "w") as f:
        json.dump(brief, f, indent=2)

    # Print summary
    print(f"\n[PHASE 3 SUMMARY]", file=sys.stderr)
    print(f"  Total work items: {len(work_items)}", file=sys.stderr)
    print(f"  Sonnet-tier items: {len(sonnet_items)}", file=sys.stderr)
    print(f"  Opus-tier items: {len(opus_items)}", file=sys.stderr)
    print(f"  Automated (non-LLM) items: {skipped_items}", file=sys.stderr)
    print(f"\n  Estimated LLM tokens: {brief['summary']['estimated_llm_tokens']}", file=sys.stderr)
    print(f"\nPhase 3 brief prepared. Next: Use brief with Claude Sonnet/Opus for semantic fixes", file=sys.stderr)

    # Output JSON summary
    summary_output = {
        "phase": "semantic",
        "status": "brief_prepared",
        "sonnet_items": len(sonnet_items),
        "opus_items": len(opus_items),
        "automated_items": skipped_items,
        "brief_file": str(output_dir / "semantic-review-brief.json"),
        "next_action": "Review brief-prepared items with Sonnet/Opus and apply fixes",
    }
    print(json.dumps(summary_output, indent=2))

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Phase 3: Semantic - Prepare work items for LLM review (no execution, just curation)"
    )
    parser.add_argument(
        "-w", "--work-items", default="work-items.json", help="Path to work-items.json from phase 2"
    )
    parser.add_argument(
        "-s", "--raw-scan", default="raw-scan.json", help="Path to raw-scan.json from phase 0"
    )
    parser.add_argument(
        "-o", "--output", default="./migration_output", help="Output directory for phase results"
    )

    args = parser.parse_args()

    exit_code = phase3_semantic(args.work_items, args.raw_scan, args.output)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
