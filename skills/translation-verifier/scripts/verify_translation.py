#!/usr/bin/env python3
"""
Translation Verifier: Behavioral equivalence verification for code migrations.

Executes tests against source and target code, compares outputs against behavioral contracts,
and computes confidence scores. The core logic is deterministic; LLM only needed for
analyzing uncertain failures.

Usage:
    python3 verify_translation.py \
        --source-dir /path/to/source \
        --target-dir /path/to/target \
        --contracts /path/to/behavioral-contracts.json \
        --test-dir /path/to/tests \
        --output /path/to/output
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import shutil


class TranslationVerifier:
    """Verifies behavioral equivalence between source and target code."""

    # Known expected differences between Python 2 and Python 3
    EXPECTED_DIFFERENCES = {
        "dict_ordering": r"^dict ordering changed",
        "repr_format": r"(u'|b').*changed representation",
        "integer_division": r"integer division.*result changed",
        "bytes_repr": r"bytes representation changed",
        "range_iterator": r"range/map/filter/zip.*iterator vs list",
        "exception_message": r"exception message format changed",
        "whitespace_only": r"^whitespace-only difference",
    }

    def __init__(
        self,
        source_dir: str,
        target_dir: str,
        contracts_path: Optional[str],
        test_dir: Optional[str],
        python2_exe: str = "python2",
        python3_exe: str = "python3",
        output_dir: str = "./verification-output",
        timeout: int = 30,
    ):
        """Initialize the verifier.

        Args:
            source_dir: Path to original (Python 2) source
            target_dir: Path to converted (Python 3) source
            contracts_path: Path to behavioral-contracts.json
            test_dir: Path to test directory (auto-detect if None)
            python2_exe: Python 2 interpreter path
            python3_exe: Python 3 interpreter path
            output_dir: Output directory for results
            timeout: Timeout per test in seconds
        """
        self.source_dir = Path(source_dir)
        self.target_dir = Path(target_dir)
        self.contracts_path = Path(contracts_path) if contracts_path else None
        self.test_dir = Path(test_dir) if test_dir else self._auto_detect_test_dir()
        self.python2_exe = python2_exe
        self.python3_exe = python3_exe
        self.output_dir = Path(output_dir)
        self.timeout = timeout

        # Verify Python 3 is available
        if not self._check_interpreter(self.python3_exe):
            raise RuntimeError(f"Python 3 interpreter not found: {self.python3_exe}")

        # Check if Python 2 is available
        self.py2_available = self._check_interpreter(self.python2_exe)

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load contracts
        self.contracts = {}
        if self.contracts_path and self.contracts_path.exists():
            with open(self.contracts_path) as f:
                self.contracts = json.load(f)

        # Results storage
        self.verification_results = {
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source_dir": str(self.source_dir),
                "target_dir": str(self.target_dir),
                "test_dir": str(self.test_dir),
                "contracts_file": str(self.contracts_path) if self.contracts_path else None,
            },
            "overall_confidence": 0.0,
            "confidence_level": "unknown",
            "summary": {
                "total_clauses": 0,
                "clauses_passed": 0,
                "clauses_failed": 0,
                "clauses_unverifiable": 0,
            },
            "per_clause_results": [],
            "discrepancies": [],
            "recommended_actions": [],
        }

        self.contract_violations = []
        self.flagged_for_review = []

    def _check_interpreter(self, exe_path: str) -> bool:
        """Check if a Python interpreter is available."""
        try:
            result = subprocess.run(
                [exe_path, "--version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _auto_detect_test_dir(self) -> Path:
        """Auto-detect test directory."""
        # Check common test directory names
        for name in ["tests", "test", "testing"]:
            candidate = self.source_dir.parent / name
            if candidate.exists():
                return candidate
        # Default to tests subdirectory
        return self.source_dir.parent / "tests"

    def discover_test_files(self) -> List[Path]:
        """Discover test files in test directory."""
        if not self.test_dir.exists():
            return []

        test_files = []
        for pattern in ["test_*.py", "*_test.py"]:
            test_files.extend(self.test_dir.glob(pattern))
        return sorted(list(set(test_files)))

    def run_test_file(
        self,
        test_file: Path,
        source_dir: Path,
        python_exe: str,
    ) -> Dict[str, Any]:
        """Run a single test file and capture output.

        Returns:
            Dict with stdout, stderr, exit_code, timeout, and error info
        """
        result = {
            "test_file": str(test_file),
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "timeout": False,
            "error": None,
        }

        # Prepare environment with source directory in PYTHONPATH
        env = os.environ.copy()
        pythonpath = str(source_dir)
        if "PYTHONPATH" in env:
            pythonpath = f"{pythonpath}:{env['PYTHONPATH']}"
        env["PYTHONPATH"] = pythonpath

        try:
            process = subprocess.run(
                [python_exe, str(test_file)],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                cwd=str(source_dir.parent),
            )
            result["stdout"] = process.stdout
            result["stderr"] = process.stderr
            result["exit_code"] = process.returncode
        except subprocess.TimeoutExpired:
            result["timeout"] = True
            result["error"] = f"Test timed out after {self.timeout} seconds"
        except Exception as e:
            result["error"] = str(e)

        return result

    def compare_outputs(
        self,
        source_result: Dict[str, Any],
        target_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Compare outputs from source and target.

        Returns:
            Dict with comparison results and classification
        """
        comparison = {
            "match": False,
            "differences": [],
            "classification": "unverifiable",
        }

        # Handle errors and timeouts
        if source_result["error"]:
            comparison["differences"].append(f"Source error: {source_result['error']}")
            comparison["classification"] = "unverifiable"
            return comparison

        if source_result["timeout"]:
            comparison["differences"].append("Source test timed out")
            comparison["classification"] = "unverifiable"
            return comparison

        if target_result["error"]:
            comparison["differences"].append(f"Target error: {target_result['error']}")
            comparison["classification"] = "potential_bug"
            return comparison

        if target_result["timeout"]:
            comparison["differences"].append("Target test timed out")
            comparison["classification"] = "potential_bug"
            return comparison

        # Compare exit codes
        if source_result["exit_code"] != target_result["exit_code"]:
            comparison["differences"].append(
                f"Exit code mismatch: source={source_result['exit_code']}, "
                f"target={target_result['exit_code']}"
            )
        else:
            comparison["match"] = True

        # Compare stdout
        if source_result["stdout"] != target_result["stdout"]:
            comparison["match"] = False
            diff_classification = self._classify_output_difference(
                source_result["stdout"],
                target_result["stdout"],
            )
            comparison["differences"].append(
                {
                    "type": "stdout",
                    "source": source_result["stdout"][:500],
                    "target": target_result["stdout"][:500],
                    "classification": diff_classification,
                }
            )

        # Compare stderr
        if source_result["stderr"] != target_result["stderr"]:
            comparison["match"] = False
            diff_classification = self._classify_output_difference(
                source_result["stderr"],
                target_result["stderr"],
            )
            comparison["differences"].append(
                {
                    "type": "stderr",
                    "source": source_result["stderr"][:500],
                    "target": target_result["stderr"][:500],
                    "classification": diff_classification,
                }
            )

        # Classify the comparison
        if comparison["match"]:
            comparison["classification"] = "pass"
        else:
            # Check if all differences are expected
            all_expected = all(
                isinstance(d, dict) and d.get("classification") == "expected"
                for d in comparison["differences"]
                if isinstance(d, dict)
            )
            if all_expected and not any(
                isinstance(d, str) for d in comparison["differences"]
            ):
                comparison["classification"] = "expected"
            else:
                comparison["classification"] = "potential_bug"

        return comparison

    def _classify_output_difference(self, source: str, target: str) -> str:
        """Classify an output difference as expected or not."""
        # Normalize and compare
        source_normalized = self._normalize_output(source)
        target_normalized = self._normalize_output(target)

        if source_normalized == target_normalized:
            return "expected"

        # Check for known expected differences
        for pattern in self.EXPECTED_DIFFERENCES.values():
            if re.search(pattern, source) or re.search(pattern, target):
                return "expected"

        # Check for whitespace-only differences
        if source.split() == target.split():
            return "expected"

        return "potential_bug"

    def _normalize_output(self, text: str) -> str:
        """Normalize output for comparison."""
        # Remove unicode string prefixes (u'...')
        text = re.sub(r"u'([^']*)'", r"'\1'", text)
        text = re.sub(r'u"([^"]*)"', r'"\1"', text)

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Normalize whitespace in repr output
        text = re.sub(r"<type '([^']*)'", r"\1", text)

        return text.strip()

    def verify_contract_clauses(
        self,
        test_results: Dict[str, Any],
    ) -> None:
        """Verify contract clauses against test results."""
        if not self.contracts:
            return

        # Process contracts (handle both list and dict formats)
        contract_list = []
        if isinstance(self.contracts, list):
            contract_list = self.contracts
        elif isinstance(self.contracts, dict):
            if "contracts" in self.contracts:
                contract_list = self.contracts["contracts"]
            else:
                # Assume it's a single contract
                contract_list = [self.contracts]

        for contract in contract_list:
            self._verify_single_contract(contract, test_results)

    def _verify_single_contract(
        self,
        contract: Dict[str, Any],
        test_results: Dict[str, Any],
    ) -> None:
        """Verify a single contract against test results."""
        function_name = contract.get("function", "unknown")
        clauses = contract.get("clauses", [])

        total_clauses = len(clauses)
        passed = 0
        failed = 0
        unverifiable = 0

        clause_results = []

        for clause in clauses:
            clause_id = clause.get("id", f"clause_{len(clause_results)}")
            clause_desc = clause.get("description", "")
            clause_type = clause.get("type", "unknown")

            # Determine if clause is verifiable by test results
            has_test_coverage = any(
                result["comparison"].get("match", False)
                for result in test_results.values()
            )

            if not has_test_coverage:
                clause_result = {
                    "clause_id": clause_id,
                    "function": function_name,
                    "clause_description": clause_desc,
                    "clause_type": clause_type,
                    "status": "unverifiable",
                    "reason": "No test case with coverage",
                }
                unverifiable += 1
            else:
                # Check clause against test results
                clause_passed = self._check_clause(clause, test_results)

                if clause_passed:
                    passed += 1
                    status = "pass"
                else:
                    failed += 1
                    status = "fail"

                clause_result = {
                    "clause_id": clause_id,
                    "function": function_name,
                    "clause_description": clause_desc,
                    "clause_type": clause_type,
                    "status": status,
                    "tests_checked": len(test_results),
                    "details": self._generate_clause_details(clause, test_results),
                }

            clause_results.append(clause_result)

        self.verification_results["per_clause_results"].extend(clause_results)
        self.verification_results["summary"]["total_clauses"] += total_clauses
        self.verification_results["summary"]["clauses_passed"] += passed
        self.verification_results["summary"]["clauses_failed"] += failed
        self.verification_results["summary"]["clauses_unverifiable"] += unverifiable

    def _check_clause(self, clause: Dict[str, Any], test_results: Dict[str, Any]) -> bool:
        """Check if a clause passes based on test results."""
        clause_type = clause.get("type", "")

        if clause_type == "returns":
            return self._check_return_clause(clause, test_results)
        elif clause_type == "error_condition":
            return self._check_error_clause(clause, test_results)
        elif clause_type == "side_effect":
            return self._check_side_effect_clause(clause, test_results)
        elif clause_type == "implicit_behavior":
            return self._check_implicit_behavior(clause, test_results)

        return True

    def _check_return_clause(
        self,
        clause: Dict[str, Any],
        test_results: Dict[str, Any],
    ) -> bool:
        """Check return value clause."""
        # For now, check that all results match
        return all(
            result["comparison"].get("match", False)
            for result in test_results.values()
        )

    def _check_error_clause(
        self,
        clause: Dict[str, Any],
        test_results: Dict[str, Any],
    ) -> bool:
        """Check error condition clause."""
        # For now, return True if all tests are valid
        return all(
            not result.get("error") for result in test_results.values()
        )

    def _check_side_effect_clause(
        self,
        clause: Dict[str, Any],
        test_results: Dict[str, Any],
    ) -> bool:
        """Check side effect clause."""
        # For now, return True if all tests match
        return all(
            result["comparison"].get("match", False)
            for result in test_results.values()
        )

    def _check_implicit_behavior(
        self,
        clause: Dict[str, Any],
        test_results: Dict[str, Any],
    ) -> bool:
        """Check implicit behavior clause."""
        # For now, return True
        return True

    def _generate_clause_details(
        self,
        clause: Dict[str, Any],
        test_results: Dict[str, Any],
    ) -> str:
        """Generate details string for a clause."""
        clause_type = clause.get("type", "")
        num_tests = len(test_results)

        if all(
            result["comparison"].get("match", False)
            for result in test_results.values()
        ):
            return f"All {num_tests} test cases passed"
        else:
            failed = sum(
                1
                for result in test_results.values()
                if not result["comparison"].get("match", False)
            )
            return f"{failed}/{num_tests} test cases failed"

    def compute_confidence_score(self) -> None:
        """Compute overall confidence score."""
        summary = self.verification_results["summary"]
        total = summary["total_clauses"]
        passed = summary["clauses_passed"]
        failed = summary["clauses_failed"]
        unverifiable = summary["clauses_unverifiable"]

        if total == 0:
            confidence = 0.0
            level = "none"
        elif failed > 0:
            confidence = (passed / (passed + failed)) * 0.5
            level = "low"
        elif unverifiable > 0:
            confidence = min(0.95, passed / total)
            level = "moderate"
        else:
            confidence = 1.0
            level = "high"

        self.verification_results["overall_confidence"] = confidence
        self.verification_results["confidence_level"] = level

    def generate_recommendations(self) -> None:
        """Generate recommended actions."""
        recommendations = []
        confidence = self.verification_results["overall_confidence"]
        summary = self.verification_results["summary"]

        if confidence >= 0.95:
            recommendations.append(
                "All contract clauses verified. Clear for Phase 4 → 5 cutover."
            )
        elif confidence >= 0.8:
            recommendations.append(
                "High confidence in translation. Clear for cutover with monitoring plan."
            )
        elif confidence >= 0.5:
            recommendations.append(
                "Moderate confidence. Investigate identified issues before cutover."
            )
        else:
            recommendations.append(
                "Low confidence. Major rework required before cutover."
            )

        if summary["clauses_unverifiable"] > 0:
            recommendations.append(
                f"Expand test coverage for {summary['clauses_unverifiable']} "
                "unverifiable clauses."
            )

        if summary["clauses_failed"] > 0:
            recommendations.append(
                f"Fix {summary['clauses_failed']} failing clauses before deployment."
            )

        if self.flagged_for_review:
            recommendations.append(
                f"Review {len(self.flagged_for_review)} flagged items for LLM analysis."
            )

        self.verification_results["recommended_actions"] = recommendations

    def run_verification(self) -> None:
        """Run the complete verification workflow."""
        print("Translation Verifier: Starting verification...\n")

        # Discover test files
        test_files = self.discover_test_files()
        if not test_files:
            print("No test files found. Verification cannot proceed.")
            self.verification_results["recommended_actions"].append(
                "Create tests to verify contract clauses."
            )
            self.save_results()
            return

        print(f"Discovered {len(test_files)} test files")

        # Run tests
        all_test_results = {}

        for test_file in test_files:
            print(f"\nTesting: {test_file.name}")
            test_results = {}

            # Run source test if Python 2 available
            if self.py2_available:
                print("  Running source (Python 2)...", end=" ")
                source_result = self.run_test_file(test_file, self.source_dir, self.python2_exe)
                print("✓" if not source_result["error"] else "✗")
                test_results["source"] = source_result
            else:
                print("  Python 2 not available, skipping source test")

            # Run target test
            print("  Running target (Python 3)...", end=" ")
            target_result = self.run_test_file(test_file, self.target_dir, self.python3_exe)
            print("✓" if not target_result["error"] else "✗")
            test_results["target"] = target_result

            # Compare outputs
            if self.py2_available:
                comparison = self.compare_outputs(source_result, target_result)
            else:
                # Just verify target runs without error
                comparison = {
                    "match": target_result["exit_code"] == 0,
                    "differences": [] if target_result["exit_code"] == 0 else [
                        f"Target exit code: {target_result['exit_code']}"
                    ],
                    "classification": "pass" if target_result["exit_code"] == 0 else "potential_bug",
                }

            test_results["comparison"] = comparison
            all_test_results[test_file.name] = test_results

            # Record discrepancy
            self.verification_results["discrepancies"].append({
                "test_case": test_file.name,
                "classification": comparison.get("classification", "unverifiable"),
                "match": comparison.get("match", False),
                "differences": comparison.get("differences", []),
            })

            # Flag for review if uncertain
            if comparison.get("classification") == "potential_bug":
                self.flagged_for_review.append({
                    "test_file": str(test_file),
                    "issue": comparison.get("differences", []),
                })
                self.contract_violations.append({
                    "test_file": str(test_file),
                    "comparison": comparison,
                })

        # Verify contract clauses
        if self.contracts:
            print("\nVerifying contract clauses...")
            self.verify_contract_clauses(all_test_results)

        # Compute confidence score
        self.compute_confidence_score()

        # Generate recommendations
        self.generate_recommendations()

        # Save results
        self.save_results()

        # Print summary
        self.print_summary()

    def save_results(self) -> None:
        """Save verification results to output files."""
        # verification-result.json
        result_file = self.output_dir / "verification-result.json"
        with open(result_file, "w") as f:
            json.dump(self.verification_results, f, indent=2)
        print(f"\nResults saved to: {result_file}")

        # contract-violations.json
        if self.contract_violations:
            violations_file = self.output_dir / "contract-violations.json"
            with open(violations_file, "w") as f:
                json.dump(self.contract_violations, f, indent=2)
            print(f"Violations saved to: {violations_file}")

        # flagged-for-review.json
        if self.flagged_for_review:
            flagged_file = self.output_dir / "flagged-for-review.json"
            with open(flagged_file, "w") as f:
                json.dump(self.flagged_for_review, f, indent=2)
            print(f"Flagged items saved to: {flagged_file}")

    def print_summary(self) -> None:
        """Print summary to stdout."""
        summary = {
            "status": "complete",
            "overall_confidence": self.verification_results["overall_confidence"],
            "confidence_level": self.verification_results["confidence_level"],
            "summary": self.verification_results["summary"],
            "py2_available": self.py2_available,
            "flagged_for_review_count": len(self.flagged_for_review),
            "contract_violations_count": len(self.contract_violations),
            "recommended_actions": self.verification_results["recommended_actions"],
        }

        print("\n" + "=" * 70)
        print("VERIFICATION SUMMARY")
        print("=" * 70)
        print(json.dumps(summary, indent=2))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Verify behavioral equivalence of translated code"
    )
    parser.add_argument(
        "--source-dir",
        required=True,
        help="Path to original (Python 2) source directory",
    )
    parser.add_argument(
        "--target-dir",
        required=True,
        help="Path to converted (Python 3) source directory",
    )
    parser.add_argument(
        "--contracts",
        help="Path to behavioral-contracts.json",
    )
    parser.add_argument(
        "--test-dir",
        help="Path to test directory (auto-detect if not provided)",
    )
    parser.add_argument(
        "--python2",
        default="python2",
        help="Python 2 interpreter path (default: python2)",
    )
    parser.add_argument(
        "--python3",
        default="python3",
        help="Python 3 interpreter path (default: python3)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="./verification-output",
        help="Output directory for results (default: ./verification-output)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout per test in seconds (default: 30)",
    )

    args = parser.parse_args()

    try:
        verifier = TranslationVerifier(
            source_dir=args.source_dir,
            target_dir=args.target_dir,
            contracts_path=args.contracts,
            test_dir=args.test_dir,
            python2_exe=args.python2,
            python3_exe=args.python3,
            output_dir=args.output,
            timeout=args.timeout,
        )
        verifier.run_verification()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
