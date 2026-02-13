#!/usr/bin/env python3
"""
Data Format Analyzer — Report Generator

Reads the JSON outputs from analyze_data_layer.py and produces a human-readable
markdown report with risk ratings, category breakdowns, and per-file summaries.

Usage:
    python3 generate_data_report.py <analysis_dir> \
        --project-name "Legacy SCADA System" \
        [--output <analysis_dir>/data-layer-report.md]
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


RISK_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
RISK_EMOJI = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}

CATEGORY_NAMES = {
    "file_io": "File I/O",
    "network_io": "Network / Serial I/O",
    "binary_protocol": "Binary Protocol Handling",
    "encoding": "Encoding / Decoding",
    "serialization": "Serialization",
    "database": "Database Connections",
    "constants": "Hardcoded Byte Constants",
    "error": "Scan Errors",
}

BOUNDARY_NAMES = {
    "bytes_to_text": "Bytes → Text",
    "text_to_bytes": "Text → Bytes",
    "bytes_only": "Bytes Only",
    "text_only": "Text Only",
    "ambiguous": "Ambiguous (needs manual review)",
}


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_report(
    analysis_dir: str,
    project_name: str,
) -> str:
    """Generate the markdown data layer report."""
    analysis = Path(analysis_dir)

    report = load_json(analysis / "data-layer-report.json")
    boundaries = load_json(analysis / "bytes-str-boundaries.json")
    encoding_map = load_json(analysis / "encoding-map.json")
    ser_inv = load_json(analysis / "serialization-inventory.json")

    findings = report["findings"]
    summary = report["summary"]

    lines: List[str] = []

    # ── Header ──
    lines.append(f"# Data Layer Analysis: {project_name}")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"- **Files scanned**: {report['files_scanned']}")
    lines.append(f"- **Files with data layer findings**: {report['files_with_findings']}")
    lines.append(f"- **Total findings**: {report['total_findings']}")
    lines.append(f"- **Bytes/str boundaries identified**: {boundaries['total']}")
    lines.append(f"- **Encoding operations found**: {encoding_map['total']}")
    lines.append(f"- **Serialization points found**: {ser_inv['total']}")
    lines.append("")

    # Risk breakdown
    by_risk = summary.get("by_risk", {})
    critical = by_risk.get("critical", 0)
    high = by_risk.get("high", 0)
    lines.append(f"**Risk profile**: {critical} critical, {high} high, "
                 f"{by_risk.get('medium', 0)} medium, {by_risk.get('low', 0)} low")
    lines.append("")

    if critical > 0 or high > 0:
        lines.append(
            "> ⚠️ **This codebase has significant data layer complexity.** "
            "The bytes/str boundary handling will require careful manual review "
            "during Phase 3 (Semantic Fixes). Do not rely on automated conversion alone."
        )
        lines.append("")

    # ── Boundary Summary ──
    lines.append("## Bytes/Str Boundary Summary")
    lines.append("")
    lines.append("These are the points where data transitions between bytes and text. "
                 "Every one of these needs explicit handling in Python 3.")
    lines.append("")
    bt = boundaries.get("by_type", {})
    lines.append(f"| Direction | Count |")
    lines.append(f"|-----------|-------|")
    for btype, bname in BOUNDARY_NAMES.items():
        count = bt.get(btype, 0)
        if count > 0 or btype in ("bytes_to_text", "text_to_bytes", "ambiguous"):
            lines.append(f"| {bname} | {count} |")
    lines.append("")

    # ── Category Breakdown ──
    lines.append("## Findings by Category")
    lines.append("")
    by_cat = summary.get("by_category", {})
    for cat_key in ["file_io", "network_io", "binary_protocol", "encoding",
                    "serialization", "database", "constants"]:
        count = by_cat.get(cat_key, 0)
        if count == 0:
            continue

        cat_name = CATEGORY_NAMES.get(cat_key, cat_key)
        cat_findings = [f for f in findings if f["category"] == cat_key]

        lines.append(f"### {cat_name} ({count} findings)")
        lines.append("")

        # Group by risk within category
        by_risk_in_cat = defaultdict(list)
        for f in cat_findings:
            by_risk_in_cat[f["risk"]].append(f)

        for risk_level in ["critical", "high", "medium", "low"]:
            risk_findings = by_risk_in_cat.get(risk_level, [])
            if not risk_findings:
                continue

            emoji = RISK_EMOJI.get(risk_level, "")
            lines.append(f"**{emoji} {risk_level.capitalize()} Risk** ({len(risk_findings)}):")
            lines.append("")

            # Group by pattern within risk level
            by_pattern = defaultdict(list)
            for f in risk_findings:
                by_pattern[f["pattern"]].append(f)

            for pattern, pfindings in by_pattern.items():
                desc = pfindings[0].get("description", pattern)
                lines.append(f"- **{desc}** — {len(pfindings)} occurrence(s)")

                # Show up to 3 examples
                for pf in pfindings[:3]:
                    snippet = pf["snippet"][:120]
                    lines.append(f"  - `{pf['file']}:{pf['line']}` — `{snippet}`")
                if len(pfindings) > 3:
                    lines.append(f"  - ... and {len(pfindings) - 3} more")
            lines.append("")

    # ── Encoding Map ──
    if encoding_map.get("codecs_found"):
        lines.append("## Encodings Detected")
        lines.append("")
        lines.append("Codec names found in the codebase:")
        lines.append("")
        for codec in sorted(encoding_map["codecs_found"]):
            is_ebcdic = any(
                eb in codec.lower()
                for eb in ("cp500", "cp1047", "cp037", "cp273", "cp1140", "ebcdic")
            )
            marker = " 🔴 **EBCDIC**" if is_ebcdic else ""
            lines.append(f"- `{codec}`{marker}")
        lines.append("")

    # ── Serialization Summary ──
    if ser_inv.get("formats_found"):
        lines.append("## Serialization Formats")
        lines.append("")
        lines.append("Serialization patterns found in the codebase:")
        lines.append("")
        for fmt in sorted(ser_inv["formats_found"]):
            ser_findings_for_fmt = [
                f for f in ser_inv["findings"] if f["pattern"] == fmt
            ]
            risk = ser_findings_for_fmt[0]["risk"] if ser_findings_for_fmt else "medium"
            emoji = RISK_EMOJI.get(risk, "")
            lines.append(f"- {emoji} `{fmt}` — {len(ser_findings_for_fmt)} occurrence(s)")
        lines.append("")

    # ── Highest-Risk Files ──
    lines.append("## Highest-Risk Files")
    lines.append("")
    lines.append("Files ranked by number of critical + high risk findings:")
    lines.append("")

    by_file: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for f in findings:
        by_file[f["file"]][f["risk"]] += 1

    file_scores = []
    for fpath, risk_counts in by_file.items():
        score = risk_counts.get("critical", 0) * 4 + risk_counts.get("high", 0) * 2 + risk_counts.get("medium", 0)
        file_scores.append((fpath, score, risk_counts))

    file_scores.sort(key=lambda x: x[1], reverse=True)

    lines.append("| File | Critical | High | Medium | Low | Score |")
    lines.append("|------|----------|------|--------|-----|-------|")
    for fpath, score, risk_counts in file_scores[:20]:
        lines.append(
            f"| `{fpath}` | {risk_counts.get('critical', 0)} | "
            f"{risk_counts.get('high', 0)} | {risk_counts.get('medium', 0)} | "
            f"{risk_counts.get('low', 0)} | {score} |"
        )
    lines.append("")

    # ── Sample Data Analysis ──
    sample_data = report.get("sample_data_analysis", [])
    if sample_data:
        lines.append("## Sample Data Encoding Detection")
        lines.append("")
        for sd in sample_data:
            conf = sd.get("confidence", "?")
            enc = sd.get("detected_encoding", "unknown")
            lines.append(
                f"- `{sd['file']}` — detected as **{enc}** (confidence: {conf})"
            )
        lines.append("")

    # ── Recommendations ──
    lines.append("## Recommendations for Phase 3")
    lines.append("")

    if critical > 0:
        lines.append(
            "1. **EBCDIC and binary protocol handlers need dedicated review.** "
            "These cannot be auto-converted. A developer who understands the data "
            "formats must manually verify each encode/decode decision."
        )

    boundary_ambiguous = bt.get("ambiguous", 0)
    if boundary_ambiguous > 0:
        lines.append(
            f"2. **{boundary_ambiguous} ambiguous boundary crossings need classification.** "
            "Run the code with non-ASCII test data to determine if each boundary "
            "is bytes or text. See the Encoding Stress Tester (Skill 4.3)."
        )

    pickle_count = len([f for f in findings if "pickle" in f["pattern"]])
    if pickle_count > 0:
        lines.append(
            f"3. **{pickle_count} pickle/serialization points found.** "
            "Any data pickled under Python 2 will deserialize differently under "
            "Python 3 (Py2 `str` → Py3 `bytes`). Test with actual serialized data."
        )

    struct_count = len([f for f in findings if "struct" in f["pattern"]])
    if struct_count > 0:
        lines.append(
            f"4. **{struct_count} struct.pack/unpack calls found.** "
            "These are generally safe if the data stays as bytes, but check "
            "every point where unpacked values enter string operations."
        )

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by Data Format Analyzer (Skill 0.2)*")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate markdown data layer report from analysis outputs."
    )
    parser.add_argument(
        "analysis_dir",
        help="Directory containing data layer analysis JSON outputs",
    )
    parser.add_argument(
        "--project-name",
        default="Unknown Project",
        help="Project name for the report header",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path for the markdown report (default: <analysis_dir>/data-layer-report.md)",
    )

    args = parser.parse_args()
    output_path = args.output or os.path.join(args.analysis_dir, "data-layer-report.md")

    report_md = generate_report(args.analysis_dir, args.project_name)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    print(f"Report written to {output_path}")


if __name__ == "__main__":
    main()
