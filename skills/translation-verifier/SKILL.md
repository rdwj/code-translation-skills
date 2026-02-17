---
name: translation-verifier
description: >
  Verify that translated or migrated code satisfies the same behavioral contract as the source code
  by comparing observable outputs against contract clauses. Use this skill whenever you need to
  validate that code migration preserved behavior, run comprehensive behavioral equivalence checks,
  measure confidence that a translation is correct, identify where behavior diverged, or generate
  a verification report before cutover. Also trigger when someone says "verify the translation,"
  "check behavioral equivalence," "does the migrated code work the same," "run contract verification,"
  "what's the confidence score," or "prove this migration is correct." This skill is the behavioral
  verification bridge — it proves that the translated code does what the source code did.
---

# Translation Verifier

After code translation or migration, verify that the target code behaves identically to the source
code by running tests against the behavioral contract. This skill compares actual outputs from both
source and target implementations against the abstract behavioral contract, producing a confidence
score and a detailed discrepancy report.

The confidence score (0.0–1.0) indicates how certain we are that the migration preserved behavior:
- **1.0** = all contract clauses verified by passing tests
- **0.8+** = high confidence (some clauses unverifiable but no test failures)
- **0.5–0.8** = moderate confidence (some test failures or unverifiable clauses)
- **<0.5** = low confidence (significant behavioral drift detected)

## Why Verification Matters

Translation is more than syntax conversion. A Python 2 function might rely on dict ordering,
integer division truncation, implicit string encoding, or exception types that differ in Python 3.
A Go port might not preserve logging patterns or side effect timing. Only by running both codebases
and comparing outputs can we prove equivalence.

This skill operates on three layers:
1. **Return values** — does the target function return the same value for the same inputs?
2. **Error conditions** — does the target raise the same exceptions for the same invalid inputs?
3. **Side effects** — does the target produce the same logs, file writes, network calls, etc.?

All three must align with the behavioral contract extracted by the `behavioral-contract-extractor`
skill before code cutover.

## When to Use

- After running the `behavioral-contract-extractor` skill
- After completing code translation or migration of a module
- Before advancing a module to the Verification phase (Phase 4)
- When you need to confirm behavioral equivalence before production cutover
- When debugging why a migration is producing different behavior
- When measuring migration quality across multiple modules
- When the gate checker requires `zero_behavioral_diffs` or `behavioral_contract_verified`

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| **behavioral_contract** | behavioral-contract-extractor | Contract file (`behavioral-contracts.json`) or individual contract JSON |
| **source_file** | User / file system | Path to original source code file(s) |
| **target_file** | User / file system | Path to translated/migrated target code file(s) |
| **test_commands** | Work item / test suite | Commands to run tests (e.g., `pytest src/io/csv_mailer.py::test_*` or custom runner scripts) |
| **baseline_outputs** (optional) | Previous run | Expected outputs from source code (if already captured) |
| **output_dir** | User | Where to write verification results (defaults to `./verification-output/`) |

## Outputs

All outputs go to `<output_dir>/`:

| File | Format | Purpose |
|------|--------|---------|
| `verification-result.json` | JSON | Machine-readable verification report with confidence score, per-clause results, discrepancies |
| `verification-report.md` | Markdown | Human-readable summary for review and stakeholder communication |
| `source-baseline.json` | JSON | Captured outputs from running source code tests (for audit trail) |
| `target-outputs.json` | JSON | Captured outputs from running target code tests |
| `discrepancy-analysis.json` | JSON | Detailed analysis of each discrepancy (what differed and why) |

## Verification Workflow

### Step 1: Parse the Behavioral Contract

Load the contract produced by the `behavioral-contract-extractor` skill. The contract defines:
- Input parameters and their semantics
- Expected return types and values
- Error conditions (which exceptions should be raised when)
- Side effects (logging, file writes, network calls)
- Implicit behaviors (dict ordering, encoding defaults, etc.)

```bash
python3 scripts/verify_translation.py \
    --source <source_file> \
    --target <target_file> \
    --contract <behavioral_contract.json> \
    --test-command "pytest {file} -v" \
    --output <output_dir>
```

### Step 2: Run Source Code Tests to Establish Baseline

Execute the test suite against the source code. Capture:
- Return values for each test case
- Exceptions raised (type and message)
- Side effects (stdout, stderr, file system changes, network calls if mocked)
- Execution time and resource usage

The baseline establishes ground truth: "this is what the source code does."

### Step 3: Run Target Code Tests with Same Inputs

Execute the same test commands against the translated/migrated target code using identical
inputs. Capture the same observations as Step 2.

### Step 4: Compare Outputs Against Contract Clauses

For each contract clause, check:
- **Return values match** — type and value match the contract specification
- **Error conditions match** — same exceptions raised for same invalid inputs
- **Side effects present** — logging, file writes, network calls match the contract
- **Implicit behaviors preserved** — dict ordering (if specified), encoding handling, etc.

### Step 5: Per-Clause Verification

For each clause in the behavioral contract, evaluate:

```
For clause = {
  inputs: [{name, type, semantics, constraints}],
  outputs: {returns, writes, mutations},
  error_conditions: [{exception, when}],
  implicit_behaviors: [{behavior, risk}]
}

Check:
1. Does target(inputs) return same type as contract specifies?
2. Does target(inputs) produce same return value as source(inputs)?
3. For invalid inputs, does target raise same exception as contract specifies?
4. Do side effects (logs, writes) match contract expectations?
5. Are implicit behaviors preserved (ordering, encoding, etc.)?
```

### Step 6: Compute Confidence Score

Aggregate per-clause results into an overall confidence score:

```
clauses_passed = count(clauses where all checks pass)
clauses_failed = count(clauses where any check fails)
clauses_unverifiable = count(clauses with no test coverage)

if clauses_failed > 0:
    confidence = (clauses_passed / (clauses_passed + clauses_failed)) * 0.5
elif clauses_unverifiable > 0:
    confidence = min(0.95, clauses_passed / total_clauses)
else:
    confidence = 1.0
```

Guidelines:
- **1.0**: All clauses passed, all clauses covered by tests
- **0.8+**: Most clauses passed or verified, few or no unverifiable clauses
- **0.5–0.8**: Some clauses failed or unverifiable, migration has risk
- **<0.5**: Significant failures or majority unverifiable, migration not ready

### Step 7: Generate Discrepancy Report

For each test case where source and target differ:
- Describe the discrepancy (what was different)
- Analyze the root cause (why did it differ — implementation detail vs. contract violation?)
- Flag severity (is this a contract violation or acceptable variation?)
- Recommend action (fix, waive, or investigate further)

## Per-Clause Checks

The verification examines each contract clause against test execution:

### Return Value Verification
Type and value must match exactly. If different types or values, check whether due to test inconsistency, actual behavior difference, or acceptable variation (e.g., floating-point rounding).

### Error Condition Verification
For each error condition in the contract, invoke both source and target with invalid inputs. Both must raise the same exception type. Message differences are acceptable if exception type matches.

### Side Effect Verification
Capture stdout, stderr, file system changes, and network calls (via mocks). Both source and target must produce the same side effects in the same order (unless contract explicitly allows reordering).

### Implicit Behavior Verification
For implicit behaviors flagged by contract extractor (dict ordering, string encoding, exception message formatting, floating-point precision), verify both source and target preserve the behavior identically.

See `references/EXAMPLES.md` for complete per-clause verification examples with JSON structure for all check types.

## Confidence Scoring

The confidence score (0.0–1.0) reflects overall migration quality:

- **1.0**: All contract clauses verified by passing tests
- **0.95–0.99**: All clauses verified; some minor unverifiable edge cases
- **0.8–0.94**: High confidence; most clauses verified, acceptable coverage gaps
- **0.5–0.79**: Moderate confidence; some failures or coverage gaps, requires investigation
- **0.0–0.49**: Low confidence; significant failures or majority unverifiable
- **0.0 (no tests)**: No tests available to verify contract

See `references/EXAMPLES.md` for four detailed scoring scenarios (perfect, high confidence with gaps, moderate with failures, low due to missing tests).

## Model Tier Assignment

This skill uses two model tiers for different tasks:

| Task | Model | Rationale |
|------|-------|-----------|
| Test execution, output capture, basic comparison | Haiku | Fast, reliable execution; straightforward output diff |
| Discrepancy analysis, root cause investigation | Sonnet | Deeper reasoning: why did output differ? Is it expected? Contract violation or acceptable variation? |

Haiku runs the tests and produces raw `source-baseline.json` and `target-outputs.json`.
Sonnet reads both and produces `discrepancy-analysis.json` with detailed reasoning.

## Verification Result Structure

The JSON result file (verification-result.json) contains:

- **metadata**: timestamp, source file, target file, contract ID, test count
- **overall_confidence**: aggregated confidence score (0.0–1.0)
- **confidence_level**: categorical level (low/moderate/high)
- **summary**: total clauses, passed, failed, unverifiable counts
- **per_clause_results**: array of clause evaluation results (clause_id, description, status, tests_passed/failed, details)
- **discrepancies**: array of test cases where source and target differed
- **recommended_actions**: list of next steps based on confidence and results

See `references/EXAMPLES.md` for complete verification-result.json example with all fields.

## Integration with Other Skills

### Integration with behavioral-contract-extractor

Uses contracts (behavioral-contracts.json) as verification specification. References uncovered-paths.json to identify code paths lacking test coverage. For unverifiable clauses, suggests test cases from uncovered paths.

### Integration with gate-checker

Gate checker uses the verification result:
- **Phase 4 → 5 criterion**: `zero_behavioral_diffs` — requires confidence ≥ 0.8
- **Phase 4 → 5 criterion**: `behavioral_contract_verified` — requires all contract clauses passed or documented as acceptable

### Integration with migration-state-tracker

After verification, update state file with verification-result.json as output evidence.

See `references/EXAMPLES.md` for gate checker criterion example and state tracker update commands.

### Complementary with behavioral-diff-generator

**Key distinction**: This skill and the `behavioral-diff-generator` skill serve different purposes:

- **behavioral-diff-generator**: Compares Python 2 vs Python 3 interpreter outputs *directly* by running both interpreters on the same bytecode or AST. Catches subtle differences in built-in behavior (e.g., `dict.keys()` returns list vs view, `range()` returns list vs iterator).

- **translation-verifier** (this skill): Compares against an abstract behavioral contract. Verifies that the translated code satisfies the contract specification, not just that source and target behave identically.

Both are needed:
- behavioral-diff-generator catches interpreter-level drift (low-level)
- translation-verifier catches contract-level violations (high-level semantic intent)

A migration might pass behavioral-diff tests but fail contract verification if the contract
specifies a behavior that wasn't tested by the diff generator. Conversely, a migration might
pass contract verification but fail diff tests if it uses language idioms that preserve intent
but produce slightly different outputs (e.g., returning a tuple instead of a list, acceptable
if the contract doesn't specify the exact container type).

## Important Considerations

### Tests Must Exist

Meaningful verification requires a test suite. If no tests exist, confidence is 0.0 and verification cannot proceed. Use uncovered-paths.json from behavioral-contract-extractor to create targeted test cases.

### Uncovered Paths

The behavioral-contract-extractor produces uncovered-paths.json identifying code paths with no test coverage. Use this to:
1. Identify clauses that cannot be verified with existing tests
2. Generate targeted test cases for those paths
3. Re-run verification after adding tests

### Test Consistency

Both source and target must be tested with identical inputs. Discrepancies may be due to test inconsistency, not behavioral drift. Always verify same test invocation is used.

### Encoding and String Handling

When comparing string outputs, be aware of byte strings vs unicode strings, encoding defaults, and exception message format differences. Flag these as acceptable variations unless contract specifies exact format.

### Performance and Timeout

Verification captures execution time. If target is significantly slower, flag in discrepancy report and cross-reference with gate checker's performance_acceptable criterion.

### Mocking and Side Effects

For functions with external dependencies: tests must use mocks, both source and target must use identical mocks, verify sequence and arguments of mock calls match.

See `references/EXAMPLES.md` for test consistency examples, uncovered paths example, and mocking example.

## Workflow Example

### End-to-End Verification

1. **Extract contracts**: behavioral-contract-extractor produces behavioral-contracts.json and uncovered-paths.json
2. **Translate code**: Use automated converter or manual translation
3. **Run verification**: Execute verify_translation.py with source, target, contract, test command, and output directory
4. **Review results**: Examine verification-report.md and verification-result.json
5. **Update state**: Record verification output in migration-state-tracker
6. **Gate check**: Verify behavioral_contract_verified criterion passes before cutover

See `references/EXAMPLES.md` for complete end-to-end workflow with all bash commands.

## References

- `behavioral-contract-extractor` — Extract behavioral contracts from source code
- `behavioral-diff-generator` — Compare Python 2 vs Python 3 outputs directly
- `py2to3-gate-checker` — Enforce gate criteria before phase advancement (consumes verification result)
- `py2to3-migration-state-tracker` — Track module state and gate evidence
- `references/SUB-AGENT-GUIDE.md` — Delegation strategy for test execution and comparison tasks
