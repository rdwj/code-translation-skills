#!/usr/bin/env python3
"""
Behavioral Contract Extractor - Infrastructure Layer

Extracts behavioral contracts from Python source code using only AST analysis.
No LLM reasoning — focuses on what can be determined from static code analysis:
  - Function signatures and type annotations
  - Return statements and types
  - Raised exceptions
  - I/O and side effects
  - Docstring extraction
  - Test coverage hints

Contracts with confidence < 0.5 are flagged for LLM review.

Usage:
  extract_contracts.py --raw-scan raw-scan.json \\
                       --call-graph call-graph.json \\
                       --source-dir /path/to/src \\
                       --output /path/to/output
"""

import argparse
import ast
import json
import logging
import os
import re
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class InputParam:
    """Function input parameter."""
    name: str
    type: Optional[str] = None
    default: Any = None
    required: bool = True
    annotation_source: str = "none"  # "annotation", "default", "none"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OutputSpec:
    """Function output specification."""
    type: Optional[str] = None
    nullable: bool = False
    multiple_return_paths: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ErrorCondition:
    """Error condition raised by function."""
    exception: str
    condition: str = "code raises this exception"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BehavioralContract:
    """Complete behavioral contract for a function."""
    function: str
    file: str
    line: int
    language: str = "python"
    confidence: float = 0.3
    inputs: List[InputParam] = field(default_factory=list)
    outputs: Optional[OutputSpec] = None
    side_effects: List[str] = field(default_factory=list)
    error_conditions: List[ErrorCondition] = field(default_factory=list)
    implicit_behaviors: List[str] = field(default_factory=list)
    pure: bool = True
    verification_hints: List[str] = field(default_factory=list)
    needs_llm_review: bool = False
    review_reason: Optional[str] = None
    docstring_summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "function": self.function,
            "file": self.file,
            "line": self.line,
            "language": self.language,
            "confidence": self.confidence,
            "contract": {
                "inputs": [p.to_dict() for p in self.inputs],
                "outputs": self.outputs.to_dict() if self.outputs else None,
                "side_effects": self.side_effects,
                "error_conditions": [e.to_dict() for e in self.error_conditions],
                "implicit_behaviors": self.implicit_behaviors,
                "pure": self.pure,
                "verification_hints": self.verification_hints,
            },
            "needs_llm_review": self.needs_llm_review,
            "review_reason": self.review_reason,
            "docstring_summary": self.docstring_summary,
        }


class DocstringExtractor(ast.NodeVisitor):
    """Extract RST and Google-style docstring information."""

    def __init__(self):
        self.summary = None
        self.param_docs = {}
        self.return_doc = None
        self.raises_docs = {}

    def extract(self, docstring: Optional[str]) -> None:
        """Parse docstring and extract structured info."""
        if not docstring:
            return

        lines = docstring.split("\n")
        self.summary = lines[0].strip() if lines else None

        # Try RST-style first
        if ":param" in docstring or ":returns:" in docstring or ":raises:" in docstring:
            self._parse_rst(docstring)
        # Try Google-style
        elif "Args:" in docstring or "Returns:" in docstring or "Raises:" in docstring:
            self._parse_google(docstring)

    def _parse_rst(self, docstring: str) -> None:
        """Parse RST-style docstring (Sphinx format)."""
        # :param type name: description
        param_pattern = r":param\s+(?:(\w+)\s+)?(\w+):\s*(.+)"
        for match in re.finditer(param_pattern, docstring):
            param_type, param_name, param_desc = match.groups()
            self.param_docs[param_name] = {
                "type": param_type,
                "description": param_desc,
            }

        # :returns: description
        returns_match = re.search(r":returns?:\s*(.+?)(?=:\w+:|$)", docstring, re.DOTALL)
        if returns_match:
            self.return_doc = returns_match.group(1).strip()

        # :raises ExceptionType: description
        raises_pattern = r":raises\s+(\w+):\s*(.+?)(?=:\w+:|$)"
        for match in re.finditer(raises_pattern, docstring, re.DOTALL):
            exc_type, exc_desc = match.groups()
            self.raises_docs[exc_type] = exc_desc.strip()

    def _parse_google(self, docstring: str) -> None:
        """Parse Google-style docstring."""
        # Args: section
        args_match = re.search(
            r"Args:\s*\n((?:\s{4}\w+.+\n?)+)", docstring
        )
        if args_match:
            args_section = args_match.group(1)
            # Each line: "    name (type): description"
            for line in args_section.split("\n"):
                if not line.strip():
                    continue
                match = re.match(
                    r"\s{4}(\w+)\s*(?:\(([^)]+)\))?\s*:\s*(.+)",
                    line
                )
                if match:
                    name, type_, desc = match.groups()
                    self.param_docs[name] = {
                        "type": type_,
                        "description": desc,
                    }

        # Returns: section
        returns_match = re.search(
            r"Returns:\s*\n((?:\s{4}.+\n?)+?)\n\s{0,3}\S",
            docstring + "\n\nX"
        )
        if returns_match:
            self.return_doc = returns_match.group(1).strip()

        # Raises: section
        raises_match = re.search(
            r"Raises:\s*\n((?:\s{4}\w+.+\n?)+)",
            docstring
        )
        if raises_match:
            raises_section = raises_match.group(1)
            for line in raises_section.split("\n"):
                if not line.strip():
                    continue
                match = re.match(r"\s{4}(\w+)\s*:\s*(.+)", line)
                if match:
                    exc_type, exc_desc = match.groups()
                    self.raises_docs[exc_type] = exc_desc


class FunctionAnalyzer(ast.NodeVisitor):
    """AST visitor to extract function signature, returns, raises, and side effects."""

    def __init__(self, source: str, filename: str):
        self.source = source
        self.filename = filename
        self.functions = {}
        self.current_function = None
        self.current_scope = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition."""
        prev_function = self.current_function
        self.current_function = node

        # Extract basic info
        func_name = node.name
        func_info = {
            "name": func_name,
            "lineno": node.lineno,
            "docstring": ast.get_docstring(node),
            "args": self._extract_arguments(node),
            "returns": self._extract_returns(node),
            "raises": self._extract_raises(node),
            "side_effects": self._extract_side_effects(node),
            "is_async": False,
        }

        self.functions[func_name] = func_info

        # Continue visiting nested functions
        self.generic_visit(node)

        self.current_function = prev_function

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definition."""
        # Treat async same as regular for now, just mark it
        prev_function = self.current_function
        self.current_function = node

        func_name = node.name
        func_info = {
            "name": func_name,
            "lineno": node.lineno,
            "docstring": ast.get_docstring(node),
            "args": self._extract_arguments(node),
            "returns": self._extract_returns(node),
            "raises": self._extract_raises(node),
            "side_effects": self._extract_side_effects(node),
            "is_async": True,
        }

        self.functions[func_name] = func_info
        self.generic_visit(node)
        self.current_function = prev_function

    def _extract_arguments(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> List[Dict[str, Any]]:
        """Extract function arguments with type annotations and defaults."""
        args_list = []
        args = node.args

        # Regular positional arguments
        num_defaults = len(args.defaults)
        num_args = len(args.args)
        num_no_defaults = num_args - num_defaults

        for i, arg in enumerate(args.args):
            param_type = None
            default = None
            required = True

            # Check for type annotation
            if arg.annotation:
                param_type = self._annotation_to_string(arg.annotation)

            # Check for default value
            if i >= num_no_defaults:
                default_idx = i - num_no_defaults
                default = self._value_to_string(args.defaults[default_idx])
                required = False

            args_list.append({
                "name": arg.arg,
                "type": param_type,
                "default": default,
                "required": required,
            })

        # *args
        if args.vararg:
            param_type = None
            if args.vararg.annotation:
                param_type = self._annotation_to_string(args.vararg.annotation)
            args_list.append({
                "name": f"*{args.vararg.arg}",
                "type": param_type,
                "default": None,
                "required": False,
            })

        # Keyword-only arguments
        for i, arg in enumerate(args.kwonlyargs):
            param_type = None
            default = None
            required = True

            if arg.annotation:
                param_type = self._annotation_to_string(arg.annotation)

            if i < len(args.kw_defaults) and args.kw_defaults[i]:
                default = self._value_to_string(args.kw_defaults[i])
                required = False

            args_list.append({
                "name": arg.arg,
                "type": param_type,
                "default": default,
                "required": required,
            })

        # **kwargs
        if args.kwarg:
            param_type = None
            if args.kwarg.annotation:
                param_type = self._annotation_to_string(args.kwarg.annotation)
            args_list.append({
                "name": f"**{args.kwarg.arg}",
                "type": param_type,
                "default": None,
                "required": False,
            })

        return args_list

    def _extract_returns(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> Dict[str, Any]:
        """Extract return type and determine if multiple return paths exist."""
        return_type = None
        return_paths = []

        if node.returns:
            return_type = self._annotation_to_string(node.returns)

        # Find all return statements
        for child in ast.walk(node):
            if isinstance(child, ast.Return):
                if child.value:
                    return_paths.append("explicit")
                else:
                    return_paths.append("none")

        multiple_returns = len(return_paths) > 1
        has_none_return = "none" in return_paths
        nullable = has_none_return or len(return_paths) == 0

        return {
            "type": return_type,
            "nullable": nullable,
            "multiple_return_paths": multiple_returns,
            "num_return_statements": len(return_paths),
        }

    def _extract_raises(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> List[Dict[str, str]]:
        """Extract raised exceptions from Raise statements."""
        raises = []
        seen = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Raise):
                if child.exc:
                    exc_name = self._exception_to_string(child.exc)
                    if exc_name and exc_name not in seen:
                        raises.append({
                            "exception": exc_name,
                            "condition": "raised in function body",
                        })
                        seen.add(exc_name)

        return raises

    def _extract_side_effects(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> List[str]:
        """Extract side effects from I/O, process, and network calls."""
        side_effects = set()

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func_name = self._call_to_string(child.func)

                # File operations
                if func_name in ("open", "read", "write"):
                    side_effects.add("file_io")
                elif func_name in ("os.remove", "os.unlink", "os.rmdir"):
                    side_effects.add("file_delete")
                elif func_name in ("os.rename", "shutil.move"):
                    side_effects.add("file_move")
                elif func_name in (
                    "print", "builtins.print"
                ):
                    side_effects.add("stdout")

                # Logging
                elif func_name.startswith("logging."):
                    side_effects.add("logging")

                # Network
                elif func_name.startswith("requests."):
                    side_effects.add("network")
                elif func_name.startswith("socket."):
                    side_effects.add("network_socket")
                elif func_name.startswith("urllib"):
                    side_effects.add("network_urllib")

                # Process spawning
                elif func_name in (
                    "subprocess.run", "subprocess.call", "subprocess.Popen",
                    "os.system", "os.popen"
                ):
                    side_effects.add("process_spawn")

        return sorted(side_effects)

    def _annotation_to_string(self, node: ast.expr) -> str:
        """Convert annotation AST node to string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Attribute):
            value = self._annotation_to_string(node.value)
            return f"{value}.{node.attr}"
        elif isinstance(node, ast.Subscript):
            value = self._annotation_to_string(node.value)
            slice_str = self._annotation_to_string(node.slice)
            return f"{value}[{slice_str}]"
        elif isinstance(node, ast.Tuple):
            elements = [self._annotation_to_string(e) for e in node.elts]
            return f"({', '.join(elements)})"
        elif isinstance(node, ast.Index):  # Python < 3.9
            return self._annotation_to_string(node.value)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = self._annotation_to_string(node.left)
            right = self._annotation_to_string(node.right)
            return f"{left} | {right}"
        else:
            return ast.unparse(node) if hasattr(ast, 'unparse') else "unknown"

    def _value_to_string(self, node: ast.expr) -> str:
        """Convert value AST node to string."""
        if isinstance(node, ast.Constant):
            return repr(node.value)
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.List):
            elements = [self._value_to_string(e) for e in node.elts]
            return f"[{', '.join(elements)}]"
        elif isinstance(node, ast.Dict):
            return "{...}"
        else:
            return "..."

    def _exception_to_string(self, node: ast.expr) -> str:
        """Convert exception AST node to string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return node.func.id
            elif isinstance(node.func, ast.Attribute):
                value = self._annotation_to_string(node.func.value)
                return f"{value}.{node.func.attr}"
        elif isinstance(node, ast.Attribute):
            value = self._annotation_to_string(node.value)
            return f"{value}.{node.attr}"
        return "Exception"

    def _call_to_string(self, node: ast.expr) -> str:
        """Convert call target AST node to string."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            value = self._call_to_string(node.value)
            return f"{value}.{node.attr}"
        return ""


class ContractExtractor:
    """Main contract extraction engine."""

    def __init__(
        self,
        source_dir: str,
        test_dir: Optional[str] = None,
        raw_scan_path: Optional[str] = None,
        call_graph_path: Optional[str] = None,
    ):
        self.source_dir = Path(source_dir)
        self.test_dir = Path(test_dir) if test_dir else None
        self.raw_scan = {}
        self.call_graph = {}
        self.test_functions = defaultdict(list)

        # Load analysis data if provided
        if raw_scan_path:
            self.raw_scan = self._load_json(raw_scan_path)
        if call_graph_path:
            self.call_graph = self._load_json(call_graph_path)

        # Extract test functions
        if self.test_dir and self.test_dir.exists():
            self._index_tests()

    def _load_json(self, path: str) -> Dict[str, Any]:
        """Load JSON file safely."""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load {path}: {e}")
            return {}

    def _index_tests(self) -> None:
        """Index test files to find functions under test."""
        for test_file in self.test_dir.rglob("test_*.py"):
            try:
                source = test_file.read_text(encoding="utf-8")
                tree = ast.parse(source)
                analyzer = FunctionAnalyzer(source, str(test_file))
                analyzer.visit(tree)

                # Extract tested functions from test names and assertions
                for func_name in analyzer.functions:
                    if func_name.startswith("test_"):
                        target = func_name[5:]  # Remove "test_" prefix
                        self.test_functions[target].append({
                            "test_file": str(test_file),
                            "test_func": func_name,
                        })
            except Exception as e:
                logger.warning(f"Failed to parse test file {test_file}: {e}")

    def extract_contract(
        self,
        source_file: str,
        function_name: str,
    ) -> Optional[BehavioralContract]:
        """Extract behavioral contract for a single function."""
        source_path = self.source_dir / source_file

        if not source_path.exists():
            logger.warning(f"Source file not found: {source_path}")
            return None

        try:
            source = source_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to read {source_path}: {e}")
            return None

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {source_path}: {e}")
            return None

        analyzer = FunctionAnalyzer(source, str(source_path))
        analyzer.visit(tree)

        if function_name not in analyzer.functions:
            logger.warning(f"Function {function_name} not found in {source_file}")
            return None

        func_info = analyzer.functions[function_name]
        return self._build_contract(
            source_file,
            function_name,
            func_info,
        )

    def extract_all_contracts(self) -> List[BehavioralContract]:
        """Extract contracts for all Python files in source directory."""
        contracts = []

        for py_file in self.source_dir.rglob("*.py"):
            try:
                source = py_file.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Failed to read {py_file}: {e}")
                continue

            try:
                tree = ast.parse(source)
            except SyntaxError as e:
                logger.warning(f"Syntax error in {py_file}: {e}")
                continue

            analyzer = FunctionAnalyzer(source, str(py_file))
            analyzer.visit(tree)

            relative_path = py_file.relative_to(self.source_dir)

            for func_name, func_info in analyzer.functions.items():
                contract = self._build_contract(
                    str(relative_path),
                    func_name,
                    func_info,
                )
                if contract:
                    contracts.append(contract)

        return contracts

    def _build_contract(
        self,
        source_file: str,
        function_name: str,
        func_info: Dict[str, Any],
    ) -> BehavioralContract:
        """Build contract from function info."""
        # Extract docstring info
        docstring = func_info.get("docstring")
        docstring_extractor = DocstringExtractor()
        docstring_extractor.extract(docstring)

        # Build inputs
        inputs = []
        has_annotations = False
        for arg_info in func_info.get("args", []):
            param_type = arg_info.get("type")
            if param_type:
                has_annotations = True

            inputs.append(InputParam(
                name=arg_info["name"],
                type=param_type,
                default=arg_info.get("default"),
                required=arg_info.get("required", True),
                annotation_source="annotation" if param_type else "none",
            ))

        # Build outputs
        returns_info = func_info.get("returns", {})
        outputs = OutputSpec(
            type=returns_info.get("type"),
            nullable=returns_info.get("nullable", False),
            multiple_return_paths=returns_info.get("multiple_return_paths", False),
        )

        # Error conditions
        error_conditions = [
            ErrorCondition(
                exception=e["exception"],
                condition=e.get("condition", ""),
            )
            for e in func_info.get("raises", [])
        ]

        # Side effects
        side_effects = func_info.get("side_effects", [])
        pure = len(side_effects) == 0 and len(error_conditions) == 0

        # Confidence scoring
        confidence = self._calculate_confidence(
            has_annotations,
            bool(docstring),
            len(self.test_functions.get(function_name, [])) > 0,
        )

        # Build verification hints
        verification_hints = []
        if len(error_conditions) > 0:
            exc_types = [e.exception for e in error_conditions]
            verification_hints.append(f"test error handling: {', '.join(exc_types)}")
        if outputs.multiple_return_paths:
            verification_hints.append("test multiple return paths")
        if self.test_functions.get(function_name):
            verification_hints.append(f"has {len(self.test_functions[function_name])} test(s)")

        # Determine if LLM review needed
        needs_review = confidence < 0.5
        review_reason = None
        if needs_review:
            reasons = []
            if not has_annotations:
                reasons.append("no type annotations")
            if not docstring:
                reasons.append("no docstring")
            if not self.test_functions.get(function_name):
                reasons.append("no test coverage")
            review_reason = "; ".join(reasons)

        # Build contract
        contract = BehavioralContract(
            function=function_name,
            file=source_file,
            line=func_info.get("lineno", 0),
            confidence=confidence,
            inputs=inputs,
            outputs=outputs,
            side_effects=side_effects,
            error_conditions=error_conditions,
            pure=pure,
            verification_hints=verification_hints,
            needs_llm_review=needs_review,
            review_reason=review_reason,
            docstring_summary=docstring_extractor.summary,
        )

        return contract

    def _calculate_confidence(
        self,
        has_annotations: bool,
        has_docstring: bool,
        has_tests: bool,
    ) -> float:
        """Calculate confidence score for contract."""
        score = 0.3  # Base

        if has_annotations:
            score += 0.25
        if has_docstring:
            score += 0.25
        if has_tests:
            score += 0.2

        return min(score, 0.95)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract behavioral contracts from Python source code"
    )
    parser.add_argument(
        "--raw-scan", "-r",
        help="Path to raw-scan.json from codebase analysis"
    )
    parser.add_argument(
        "--call-graph", "-c",
        help="Path to call-graph.json from code graph analysis"
    )
    parser.add_argument(
        "--source-dir", "-s",
        required=True,
        help="Path to source code directory"
    )
    parser.add_argument(
        "--test-dir", "-t",
        help="Path to test directory (optional)"
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="Output directory for contracts"
    )

    args = parser.parse_args()

    # Validate inputs
    source_dir = Path(args.source_dir)
    if not source_dir.exists():
        logger.error(f"Source directory not found: {source_dir}")
        return 1

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Create extractor
        extractor = ContractExtractor(
            source_dir=str(source_dir),
            test_dir=args.test_dir,
            raw_scan_path=args.raw_scan,
            call_graph_path=args.call_graph,
        )

        # Extract all contracts
        logger.info(f"Extracting contracts from {source_dir}...")
        contracts = extractor.extract_all_contracts()

        # Separate contracts and flagged items
        flagged = [c for c in contracts if c.needs_llm_review]
        approved = [c for c in contracts if not c.needs_llm_review]

        # Write output
        contracts_file = output_dir / "behavioral-contracts.json"
        with open(contracts_file, "w") as f:
            json.dump(
                [c.to_dict() for c in contracts],
                f,
                indent=2,
            )
        logger.info(f"Wrote {len(contracts)} contracts to {contracts_file}")

        if flagged:
            flagged_file = output_dir / "flagged-for-review.json"
            with open(flagged_file, "w") as f:
                json.dump(
                    [c.to_dict() for c in flagged],
                    f,
                    indent=2,
                )
            logger.info(f"Flagged {len(flagged)} contracts for LLM review: {flagged_file}")

        # Write summary to stdout
        summary = {
            "status": "success",
            "functions_analyzed": len(contracts),
            "contracts_generated": len(approved),
            "flagged_for_review": len(flagged),
            "output_files": {
                "contracts": str(contracts_file),
                "flagged": str(flagged_file) if flagged else None,
            },
        }

        print(json.dumps(summary, indent=2))

        return 0

    except Exception as e:
        logger.exception(f"Extraction failed: {e}")
        print(json.dumps({
            "status": "error",
            "error": str(e),
        }))
        return 2


if __name__ == "__main__":
    sys.exit(main())
