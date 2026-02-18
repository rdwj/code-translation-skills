#!/usr/bin/env python3
"""
Bytes/String Boundary Fixer

Main script for fixing bytes/str boundary issues in Python 2→3 migration.
Classifies every bytes/str interaction, auto-fixes high-confidence cases,
and escalates ambiguous boundaries to human review.

Usage:
    python3 fix_boundaries.py <codebase_path> \
        --bytes-str-boundaries <bytes-str-boundaries.json> \
        --data-layer-report <data-layer-report.json> \
        --target-version 3.9 \
        [--state-file <migration-state.json>] \
        [--output <output_dir>] \
        [--dry-run] \
        [--auto-only]

Inputs:
  - codebase_path: Root directory of Python 2 codebase
  - bytes-str-boundaries.json: From Phase 0 Data Format Analyzer (0.2)
  - data-layer-report.json: From Skill 0.2 (layer classifications)
  - target-version: Python 3.x target (e.g., 3.9, 3.12)

Outputs:
  - Modified source files (unless --dry-run)
  - bytes-str-fixes.json: Every fix applied with rationale
  - decisions-needed.json: Ambiguous cases for human review
  - encoding-annotations.json: Every encode/decode call and codec
"""

import argparse
import ast
import json
import os
import re
import sys
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ── Type Definitions ────────────────────────────────────────────────────────

BoundaryType = str  # 'bytes_native', 'text_native', 'ambiguous'
ConfidenceScore = float  # 0.0 to 1.0


class Boundary:
    """Represents a single bytes/str boundary in the code."""

    def __init__(
        self,
        file: str,
        line: int,
        col: int,
        boundary_type: BoundaryType,
        context: str,
        source_code: str,
        confidence_bytes: float,
        confidence_text: float,
    ):
        self.file = file
        self.line = line
        self.col = col
        self.boundary_type = boundary_type
        self.context = context
        self.source_code = source_code
        self.confidence_bytes = confidence_bytes
        self.confidence_text = confidence_text
        self.classification: Optional[BoundaryType] = None
        self.fix_applied: Optional[str] = None
        self.rationale: Optional[str] = None
        self.encoding_codec: Optional[str] = None
        self.risk_level: Optional[str] = None

    def __repr__(self):
        return (
            f"Boundary({self.file}:{self.line}:{self.col} "
            f"type={self.boundary_type} conf_b={self.confidence_bytes:.2f})"
        )


# ── Utility Functions ──────────────────────────────────────────────────────


def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file, exit with error message if missing."""
    p = Path(path)
    if not p.exists():
        print(f"Error: Required file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Dict[str, Any], path: str) -> None:
    """Save JSON file with nice formatting."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Wrote {path}", file=sys.stdout)


def read_file(path: str) -> str:
    """Read file content as string."""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path: str, content: str) -> None:
    """Write file content."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


# ── Boundary Detection ───────────────────────────────────────────────────────


class BoundaryDetector(ast.NodeVisitor):
    """AST visitor that detects bytes/str boundaries."""

    def __init__(self, source_code: str, filename: str):
        self.source_code = source_code
        self.filename = filename
        self.boundaries: List[Boundary] = []
        self.lines = source_code.split("\n")

    def get_source_line(self, lineno: int) -> str:
        """Get source code line by number (1-indexed)."""
        if 1 <= lineno <= len(self.lines):
            return self.lines[lineno - 1].strip()
        return ""

    def visit_Call(self, node: ast.Call) -> None:
        """Detect calls to socket.recv, struct.unpack, etc."""
        # socket.recv() — bytes native
        if self._is_method_call(node, "recv"):
            self.boundaries.append(
                Boundary(
                    file=self.filename,
                    line=node.lineno,
                    col=node.col_offset,
                    boundary_type="socket_recv",
                    context="network I/O",
                    source_code=self.get_source_line(node.lineno),
                    confidence_bytes=0.95,
                    confidence_text=0.05,
                )
            )

        # socket.send() — bytes native
        elif self._is_method_call(node, "send"):
            self.boundaries.append(
                Boundary(
                    file=self.filename,
                    line=node.lineno,
                    col=node.col_offset,
                    boundary_type="socket_send",
                    context="network I/O",
                    source_code=self.get_source_line(node.lineno),
                    confidence_bytes=0.95,
                    confidence_text=0.05,
                )
            )

        # struct.unpack() — bytes native
        elif self._is_function_call(node, "struct", "unpack"):
            self.boundaries.append(
                Boundary(
                    file=self.filename,
                    line=node.lineno,
                    col=node.col_offset,
                    boundary_type="struct_unpack",
                    context="binary parsing",
                    source_code=self.get_source_line(node.lineno),
                    confidence_bytes=0.90,
                    confidence_text=0.10,
                )
            )

        # struct.pack() — bytes native (output)
        elif self._is_function_call(node, "struct", "pack"):
            self.boundaries.append(
                Boundary(
                    file=self.filename,
                    line=node.lineno,
                    col=node.col_offset,
                    boundary_type="struct_pack",
                    context="binary formatting",
                    source_code=self.get_source_line(node.lineno),
                    confidence_bytes=0.90,
                    confidence_text=0.10,
                )
            )

        # open() with 'rb' mode — bytes native
        elif self._is_builtin_call(node, "open"):
            mode = self._get_open_mode(node)
            if mode and "b" in mode:
                self.boundaries.append(
                    Boundary(
                        file=self.filename,
                        line=node.lineno,
                        col=node.col_offset,
                        boundary_type="file_binary",
                        context="file I/O",
                        source_code=self.get_source_line(node.lineno),
                        confidence_bytes=0.95,
                        confidence_text=0.05,
                    )
                )
            elif mode and "r" in mode and "b" not in mode:
                self.boundaries.append(
                    Boundary(
                        file=self.filename,
                        line=node.lineno,
                        col=node.col_offset,
                        boundary_type="file_text",
                        context="file I/O",
                        source_code=self.get_source_line(node.lineno),
                        confidence_bytes=0.05,
                        confidence_text=0.95,
                    )
                )

        # .decode() call — text native (result)
        elif self._is_method_call(node, "decode"):
            codec = self._get_string_literal_arg(node, 0, "utf-8")
            self.boundaries.append(
                Boundary(
                    file=self.filename,
                    line=node.lineno,
                    col=node.col_offset,
                    boundary_type="decode",
                    context=f"encoding to {codec}",
                    source_code=self.get_source_line(node.lineno),
                    confidence_bytes=0.05,
                    confidence_text=0.95,
                )
            )

        # .encode() call — bytes native (result)
        elif self._is_method_call(node, "encode"):
            codec = self._get_string_literal_arg(node, 0, "utf-8")
            self.boundaries.append(
                Boundary(
                    file=self.filename,
                    line=node.lineno,
                    col=node.col_offset,
                    boundary_type="encode",
                    context=f"encoding from {codec}",
                    source_code=self.get_source_line(node.lineno),
                    confidence_bytes=0.95,
                    confidence_text=0.05,
                )
            )

        # print() / logging — text native
        elif self._is_builtin_call(node, "print"):
            self.boundaries.append(
                Boundary(
                    file=self.filename,
                    line=node.lineno,
                    col=node.col_offset,
                    boundary_type="print_output",
                    context="display/logging",
                    source_code=self.get_source_line(node.lineno),
                    confidence_bytes=0.05,
                    confidence_text=0.95,
                )
            )

        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        """Detect bytes/str comparisons that might be ambiguous."""
        # Check for comparisons like: data[i] == 'X' where data might be bytes
        # These are ambiguous and need human review
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant):
                if isinstance(comparator.value, str):
                    # Comparing with str literal — could be ambiguous if LHS is bytes
                    self.boundaries.append(
                        Boundary(
                            file=self.filename,
                            line=node.lineno,
                            col=node.col_offset,
                            boundary_type="ambiguous_comparison",
                            context="bytes/str comparison",
                            source_code=self.get_source_line(node.lineno),
                            confidence_bytes=0.50,
                            confidence_text=0.50,
                        )
                    )

        self.generic_visit(node)

    def _is_method_call(self, node: ast.Call, method_name: str) -> bool:
        """Check if node is a method call like obj.method()."""
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == method_name
        )

    def _is_function_call(
        self, node: ast.Call, module_name: str, func_name: str
    ) -> bool:
        """Check if node is a module function call like module.function()."""
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == func_name
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == module_name
        )

    def _is_builtin_call(self, node: ast.Call, func_name: str) -> bool:
        """Check if node is a builtin function call."""
        return isinstance(node.func, ast.Name) and node.func.id == func_name

    def _get_open_mode(self, node: ast.Call) -> Optional[str]:
        """Extract mode from open(..., mode='...') call."""
        if len(node.args) >= 2:
            if isinstance(node.args[1], ast.Constant):
                return node.args[1].value
        for keyword in node.keywords:
            if keyword.arg == "mode":
                if isinstance(keyword.value, ast.Constant):
                    return keyword.value.value
        return None

    def _get_string_literal_arg(
        self, node: ast.Call, index: int, default: str
    ) -> str:
        """Extract string literal argument or return default."""
        if index < len(node.args):
            arg = node.args[index]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return arg.value
        return default


# ── Classification Logic ────────────────────────────────────────────────────


def classify_boundary(
    boundary: Boundary, data_layer_report: Dict[str, Any]
) -> BoundaryType:
    """
    Classify a boundary as bytes_native, text_native, or ambiguous.
    
    Returns the classification with highest confidence.
    """
    if boundary.confidence_bytes >= 0.85:
        return "bytes_native"
    elif boundary.confidence_text >= 0.85:
        return "text_native"
    else:
        return "ambiguous"


# ── Fix Application ────────────────────────────────────────────────────────


def apply_fixes(
    file_path: str,
    boundaries: List[Boundary],
    auto_only: bool = False,
    dry_run: bool = False,
) -> Tuple[int, List[Dict[str, Any]]]:
    """
    Apply fixes to a single file.
    
    Returns: (number of fixes applied, list of fix records for JSON)
    """
    fixes_applied = []
    source_code = read_file(file_path)
    lines = source_code.split("\n")
    modified_lines = lines.copy()

    # Sort boundaries by line descending so we can modify from bottom-up
    sorted_boundaries = sorted(boundaries, key=lambda b: b.line, reverse=True)

    for boundary in sorted_boundaries:
        classification = classify_boundary(boundary, {})
        boundary.classification = classification

        # Skip ambiguous if auto_only
        if auto_only and classification == "ambiguous":
            continue

        # Generate fix if high confidence
        if classification == "bytes_native":
            fix_record = _generate_bytes_native_fix(
                boundary, modified_lines, dry_run
            )
        elif classification == "text_native":
            fix_record = _generate_text_native_fix(
                boundary, modified_lines, dry_run
            )
        else:
            # Ambiguous — no fix
            continue

        if fix_record:
            fixes_applied.append(fix_record)

    # Write file if not dry-run and fixes were applied
    if not dry_run and fixes_applied:
        write_file(file_path, "\n".join(modified_lines))

    return len(fixes_applied), fixes_applied


def _generate_bytes_native_fix(
    boundary: Boundary,
    lines: List[str],
    dry_run: bool,
) -> Optional[Dict[str, Any]]:
    """Generate and apply fix for bytes-native boundary."""
    line_idx = boundary.line - 1  # Convert to 0-indexed

    if boundary.boundary_type == "file_binary":
        # Ensure 'rb' mode
        line = lines[line_idx]
        if "open(" in line and "'r'" in line and "'rb'" not in line:
            lines[line_idx] = line.replace("'r'", "'rb'")
            return {
                "file": boundary.file,
                "line": boundary.line,
                "type": boundary.boundary_type,
                "fix": "Changed mode from 'r' to 'rb' for binary file",
                "confidence": 0.95,
                "rationale": "Binary data must use 'rb' mode in Python 3",
                "source_before": boundary.source_code,
                "source_after": lines[line_idx].strip(),
            }

    return None


def _generate_text_native_fix(
    boundary: Boundary,
    lines: List[str],
    dry_run: bool,
) -> Optional[Dict[str, Any]]:
    """Generate and apply fix for text-native boundary."""
    line_idx = boundary.line - 1  # Convert to 0-indexed

    if boundary.boundary_type == "file_text":
        # Ensure encoding parameter
        line = lines[line_idx]
        if "open(" in line and "encoding=" not in line:
            # Add encoding parameter
            if line.rstrip().endswith(")"):
                lines[line_idx] = line.rstrip()[:-1] + ", encoding='utf-8')"
            return {
                "file": boundary.file,
                "line": boundary.line,
                "type": boundary.boundary_type,
                "fix": "Added encoding='utf-8' parameter to open()",
                "confidence": 0.90,
                "rationale": "Text files should specify encoding for cross-platform compatibility",
                "source_before": boundary.source_code,
                "source_after": lines[line_idx].strip(),
            }

    return None


# ── Report Generation ──────────────────────────────────────────────────────


def generate_fixes_report(fixes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate summary report of all fixes applied."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_fixes": len(fixes),
        "fixes_by_type": Counter(f["type"] for f in fixes),
        "fixes": fixes,
    }


def generate_decisions_report(boundaries: List[Boundary]) -> Dict[str, Any]:
    """Generate report of ambiguous boundaries needing human review."""
    ambiguous = [b for b in boundaries if b.classification == "ambiguous"]

    decisions = []
    for boundary in ambiguous:
        decisions.append(
            {
                "file": boundary.file,
                "line": boundary.line,
                "boundary_type": boundary.boundary_type,
                "source_code": boundary.source_code,
                "context": boundary.context,
                "confidence_bytes": boundary.confidence_bytes,
                "confidence_text": boundary.confidence_text,
                "options": _generate_decision_options(boundary),
                "impact": _describe_impact(boundary),
                "next_step": "Review with domain expert to confirm data format",
            }
        )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_ambiguous": len(ambiguous),
        "decisions": decisions,
    }


def _generate_decision_options(boundary: Boundary) -> List[Dict[str, str]]:
    """Generate options for ambiguous boundary decision."""
    if boundary.boundary_type == "ambiguous_comparison":
        return [
            {
                "option": 1,
                "description": "Keep as bytes, use b'...' comparison",
                "rationale": "Data is binary; comparison should use bytes literals",
            },
            {
                "option": 2,
                "description": "Decode to str with appropriate codec",
                "rationale": "Data is text; decode before comparison",
            },
            {
                "option": 3,
                "description": "Review code context and clarify with developer",
                "rationale": "Function purpose is unclear; needs documentation",
            },
        ]
    return []


def _describe_impact(boundary: Boundary) -> str:
    """Describe the impact of wrong classification."""
    if boundary.boundary_type == "ambiguous_comparison":
        return "TypeError at runtime (bytes == str); or silent data corruption if comparison succeeds but semantics are wrong"
    return "Potential type mismatch at runtime"


def generate_encoding_report(boundaries: List[Boundary]) -> Dict[str, Any]:
    """Generate report of all encoding operations."""
    encoding_ops = [
        b for b in boundaries if b.boundary_type in ("encode", "decode")
    ]

    annotations = []
    for boundary in encoding_ops:
        codec = boundary.encoding_codec or (
            "utf-8" if "decode" in boundary.boundary_type else "utf-8"
        )
        annotations.append(
            {
                "file": boundary.file,
                "line": boundary.line,
                "operation": boundary.boundary_type,
                "codec": codec,
                "context": boundary.context,
                "confidence": boundary.confidence_text
                if boundary.boundary_type == "decode"
                else boundary.confidence_bytes,
                "risk": "low"
                if codec == "utf-8"
                else "medium" if codec.startswith("cp") else "low",
                "note": f"Verify codec is appropriate for this data source",
            }
        )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_encoding_ops": len(annotations),
        "annotations": annotations,
    }


# ── Main ────────────────────────────────────────────────────────────────────


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description="Bytes/String Boundary Fixer for Python 2→3 migration"
    )
    parser.add_argument("codebase_path", help="Root directory of Python codebase")
    parser.add_argument(
        "--bytes-str-boundaries",
        required=True,
        help="Path to bytes-str-boundaries.json from Phase 0 Data Format Analyzer",
    )
    parser.add_argument(
        "--data-layer-report",
        required=False,
        help="Path to data-layer-report.json (optional)",
    )
    parser.add_argument(
        "--target-version",
        default="3.9",
        help="Target Python 3.x version (default: 3.9)",
    )
    parser.add_argument(
        "--state-file",
        help="Path to migration-state.json for decision tracking",
    )
    parser.add_argument(
        "--output",
        default="./",
        help="Output directory for reports (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying files",
    )
    parser.add_argument(
        "--auto-only",
        action="store_true",
        help="Only apply high-confidence auto-fixes; skip ambiguous cases",
    )

    args = parser.parse_args()

    # ── Step 1: Load Phase 0 boundary map ──────────────────────────────────

    print("\n# ── Loading Phase 0 Boundary Map ──────────────────────────", file=sys.stdout)
    boundary_map = load_json(args.bytes_str_boundaries)
    print(f"Loaded {len(boundary_map.get('boundaries', []))} boundaries", file=sys.stdout)

    # Load data layer report if provided
    data_layer_report = {}
    if args.data_layer_report:
        data_layer_report = load_json(args.data_layer_report)

    # ── Step 2: Detect boundaries in codebase ──────────────────────────────

    print("\n# ── Detecting Boundaries in Codebase ──────────────────────────", file=sys.stdout)

    codebase_path = Path(args.codebase_path)
    all_boundaries: List[Boundary] = []
    files_scanned = 0

    for py_file in codebase_path.rglob("*.py"):
        if "venv" in py_file.parts or "__pycache__" in py_file.parts:
            continue

        try:
            source_code = read_file(str(py_file))
            tree = ast.parse(source_code)
            detector = BoundaryDetector(source_code, str(py_file.relative_to(codebase_path)))
            detector.visit(tree)
            all_boundaries.extend(detector.boundaries)
            files_scanned += 1
        except SyntaxError as e:
            print(f"Warning: Syntax error in {py_file}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Error processing {py_file}: {e}", file=sys.stderr)

    print(f"Scanned {files_scanned} Python files", file=sys.stdout)
    print(f"Detected {len(all_boundaries)} boundaries", file=sys.stdout)

    # ── Step 3: Classify boundaries ──────────────────────────────────────────

    print("\n# ── Classifying Boundaries ──────────────────────────────────", file=sys.stdout)

    for boundary in all_boundaries:
        boundary.classification = classify_boundary(boundary, data_layer_report)

    bytes_native = sum(1 for b in all_boundaries if b.classification == "bytes_native")
    text_native = sum(1 for b in all_boundaries if b.classification == "text_native")
    ambiguous = sum(1 for b in all_boundaries if b.classification == "ambiguous")

    print(f"Bytes-native: {bytes_native}", file=sys.stdout)
    print(f"Text-native: {text_native}", file=sys.stdout)
    print(f"Ambiguous: {ambiguous}", file=sys.stdout)

    # ── Step 4: Apply automatic fixes ──────────────────────────────────────

    print("\n# ── Applying Automatic Fixes ──────────────────────────────────", file=sys.stdout)

    total_fixes = 0
    all_fix_records = []
    files_by_path: Dict[str, List[Boundary]] = defaultdict(list)

    for boundary in all_boundaries:
        files_by_path[boundary.file].append(boundary)

    for file_path, boundaries in files_by_path.items():
        full_path = codebase_path / file_path
        if full_path.exists():
            num_fixes, fix_records = apply_fixes(
                str(full_path),
                boundaries,
                auto_only=args.auto_only,
                dry_run=args.dry_run,
            )
            total_fixes += num_fixes
            all_fix_records.extend(fix_records)
            if num_fixes > 0:
                print(f"  {file_path}: {num_fixes} fixes", file=sys.stdout)

    print(f"Applied {total_fixes} fixes", file=sys.stdout)

    # ── Step 5: Generate reports ───────────────────────────────────────────

    print("\n# ── Generating Reports ───────────────────────────────────────", file=sys.stdout)

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # bytes-str-fixes.json
    fixes_report = generate_fixes_report(all_fix_records)
    fixes_path = output_dir / "bytes-str-fixes.json"
    save_json(fixes_report, str(fixes_path))

    # decisions-needed.json
    decisions_report = generate_decisions_report(all_boundaries)
    decisions_path = output_dir / "decisions-needed.json"
    save_json(decisions_report, str(decisions_path))

    # encoding-annotations.json
    encoding_report = generate_encoding_report(all_boundaries)
    encoding_path = output_dir / "encoding-annotations.json"
    save_json(encoding_report, str(encoding_path))

    print(f"\nReports written to {output_dir}", file=sys.stdout)

    # ── Dry-run summary ────────────────────────────────────────────────────

    if args.dry_run:
        print("\n[DRY RUN] No files modified", file=sys.stdout)

    print("\nDone.", file=sys.stdout)


if __name__ == "__main__":
    main()
