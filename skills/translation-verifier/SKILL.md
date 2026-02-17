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

```json
{
  "clause": "returns int (count of processed items)",
  "contract_type": "int",
  "source_return": 42,
  "target_return": 42,
  "match": true,
  "status": "pass"
}
```

Type and value must match exactly. If the target returns a different type (e.g., `float`
instead of `int`), flag as failure. If the value differs, check whether it's due to:
- Different test inputs (verify test consistency)
- Different behavior (contract violation)
- Floating-point rounding (acceptable if contract allows tolerance)

### Error Condition Verification

```json
{
  "clause": "raises FileNotFoundError when csv_path does not exist",
  "contract_exception": "FileNotFoundError",
  "test_input": {"csv_path": "/nonexistent/file.csv"},
  "source_exception": "FileNotFoundError",
  "target_exception": "FileNotFoundError",
  "match": true,
  "status": "pass"
}
```

For each error condition in the contract, invoke both source and target with invalid inputs.
Both must raise the same exception type. Message differences are acceptable if the exception
type matches.

### Side Effect Verification

```json
{
  "clause": "logs info message per email sent",
  "side_effect_type": "logging.info",
  "source_logs": ["Sending to alice@example.com", "Sending to bob@example.com"],
  "target_logs": ["Sending to alice@example.com", "Sending to bob@example.com"],
  "match": true,
  "status": "pass"
}
```

Capture stdout, stderr, file system changes, and network calls (via mocks). Both source
and target must produce the same side effects in the same order (unless the contract
explicitly allows reordering).

### Implicit Behavior Verification

```json
{
  "clause": "dict ordering is preserved (Python 3.7+)",
  "behavior": "dict_order",
  "source_behavior": "ordered",
  "target_behavior": "ordered",
  "match": true,
  "status": "pass"
}
```

For implicit behaviors flagged by the contract extractor:
- **Dict ordering**: Verify both source and target preserve insertion order
- **String encoding**: Verify both assume UTF-8 and handle non-ASCII identically
- **Exception message formatting**: Verify exception messages match expected patterns
- **Floating-point precision**: If relevant, verify both use same precision

## Confidence Scoring

The confidence score reflects overall migration quality:

| Confidence | Interpretation | Action |
|------------|-----------------|--------|
| **1.0** | All contract clauses verified by passing tests | Clear for cutover; no further testing needed |
| **0.95–0.99** | All clauses verified; some minor unverifiable edge cases | Clear for cutover with documentation of limitations |
| **0.8–0.94** | High confidence: most clauses verified, acceptable coverage gaps | Clear for cutover with monitoring plan |
| **0.5–0.79** | Moderate confidence: some failures or coverage gaps, requires investigation | **NOT clear for cutover** — fix identified issues or expand test coverage |
| **0.0–0.49** | Low confidence: significant failures or majority unverifiable | **DO NOT proceed** — major rework required before cutover |
| **0.0 (no tests)** | No tests available to verify contract | **Confidence cannot be assessed** — create and run tests before verification |

### Example Scoring Scenarios

**Scenario 1: Perfect verification**
```
Total clauses: 8
Passed: 8, Failed: 0, Unverifiable: 0
Confidence = 1.0 (all passed, all covered)
→ Clear for cutover
```

**Scenario 2: High confidence with some gaps**
```
Total clauses: 8
Passed: 7, Failed: 0, Unverifiable: 1 (edge case: Unicode handling under specific OS locale)
Confidence = 0.875 (7/8 verified, 1 unverifiable but no failures)
→ Clear for cutover with note about Unicode locale edge case
```

**Scenario 3: Moderate confidence with failures**
```
Total clauses: 8
Passed: 5, Failed: 1, Unverifiable: 2
Confidence = 0.625 ((5 / (5 + 1)) * 0.5 = 0.41, boosted by coverage of remaining clauses)
Actually: (5 passed / 8 total) * 0.8 = 0.5
→ NOT clear — must investigate the 1 failure and expand tests for the 2 unverifiable clauses
```

**Scenario 4: Low confidence due to missing tests**
```
Total clauses: 8
Passed: 0, Failed: 0, Unverifiable: 8 (no tests exist)
Confidence = 0.0
→ CRITICAL: Create tests before verification can proceed. Use uncovered-paths.json from contract extractor.
```

## Verification Result Structure

The JSON result file contains:

```json
{
  "metadata": {
    "timestamp": "ISO-8601",
    "source_file": "path/to/source.py",
    "target_file": "path/to/target.py",
    "contract_id": "src.io.csv_mailer.send_csv_emails",
    "test_count": 12
  },
  "overall_confidence": 0.95,
  "confidence_level": "high",
  "summary": {
    "total_clauses": 8,
    "clauses_passed": 7,
    "clauses_failed": 0,
    "clauses_unverifiable": 1
  },
  "per_clause_results": [
    {
      "clause_id": "returns_type",
      "clause_description": "returns int (count of successfully sent emails)",
      "status": "pass",
      "tests_passed": 3,
      "tests_failed": 0,
      "details": "All test cases returned int matching contract specification"
    },
    {
      "clause_id": "error_filenotfound",
      "clause_description": "raises FileNotFoundError when csv_path does not exist",
      "status": "pass",
      "tests_passed": 1,
      "tests_failed": 0,
      "details": "Both source and target raise FileNotFoundError for missing file"
    },
    {
      "clause_id": "side_effects_logging",
      "clause_description": "logs info message per email sent",
      "status": "pass",
      "tests_passed": 2,
      "tests_failed": 0,
      "details": "Both implementations log identical messages for 1, 5, and 100 emails"
    },
    {
      "clause_id": "implicit_unicode_handling",
      "clause_description": "handles UTF-8 correctly in email addresses",
      "status": "unverifiable",
      "reason": "No test case with non-ASCII email addresses in suite"
    }
  ],
  "discrepancies": [
    {
      "test_case": "test_send_1_email",
      "clause": "returns_type",
      "source_value": 1,
      "target_value": 1,
      "match": true
    }
  ],
  "recommended_actions": [
    "All contract clauses verified. Clear for Phase 4 → 5 cutover.",
    "Document untested Unicode edge case in runbook."
  ]
}
```

## Integration with Other Skills

### Integration with behavioral-contract-extractor

The behavioral-contract-extractor produces `behavioral-contracts.json` and `uncovered-paths.json`.
This skill consumes those files:
- Uses contracts as the verification specification
- References `uncovered-paths.json` to identify which code paths lack test coverage
- For unverifiable clauses, suggests test cases from the uncovered paths

### Integration with gate-checker

The gate checker (Skill X.3) uses the verification result:
- **Phase 4 → 5 criterion**: `zero_behavioral_diffs` — requires confidence ≥ 0.8
- **Phase 4 → 5 criterion**: `behavioral_contract_verified` — requires all contract clauses passed or documented as acceptable

Example gate criterion check:
```json
{
  "name": "behavioral_contract_verified",
  "description": "Target code satisfies behavioral contract",
  "threshold": "confidence >= 0.8 AND no critical discrepancies",
  "actual": "confidence = 0.95, discrepancies = 0",
  "status": "pass",
  "evidence_file": "verification-result.json"
}
```

### Integration with migration-state-tracker

After verification, update the state file:
```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py <state_file> \
    record-output \
    --module "src/io/csv_mailer.py" \
    --output-path <output_dir>/verification-result.json
```

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

Meaningful verification requires a test suite. If no tests exist:
```json
{
  "overall_confidence": 0.0,
  "summary": {
    "total_clauses": 8,
    "clauses_passed": 0,
    "clauses_failed": 0,
    "clauses_unverifiable": 8
  },
  "note": "No tests available to verify contract. Test coverage is required before verification can proceed.",
  "recommended_actions": [
    "Create tests using uncovered-paths.json from behavioral-contract-extractor",
    "At minimum, test: input parameter boundaries, error conditions, side effects",
    "Run verification again after tests are added"
  ]
}
```

### Uncovered Paths

The `behavioral-contract-extractor` produces `uncovered-paths.json` identifying which code paths
have no test coverage. Use this to:
1. Identify clauses that cannot be verified with existing tests
2. Generate targeted test cases for those paths
3. Re-run verification after adding tests

Example from uncovered-paths.json:
```json
{
  "function": "send_csv_emails",
  "uncovered": [
    {
      "path_id": "path_2a",
      "description": "CSV file with Unicode characters in field values",
      "test_suggestion": "test with CSV containing emails with non-ASCII domains"
    },
    {
      "path_id": "path_3f",
      "description": "SMTP connection timeout after 3 retries",
      "test_suggestion": "mock SMTP server that times out, verify exception is raised"
    }
  ]
}
```

### Test Consistency

Both source and target must be tested with identical inputs. If test inputs differ:
- Source tests use `pytest -v`
- Target tests use different arguments

Then discrepancies may be due to test inconsistency, not behavioral drift. Always verify:
```bash
# Confirm both use same test invocation
pytest <contract_function> -v
# vs
pytest <contract_function> -v  # identical
```

### Encoding and String Handling

When comparing string outputs, be aware of:
- **Byte strings vs Unicode strings** (Python 2 vs 3)
- **Encoding defaults** (UTF-8 assumed)
- **Exception messages** may differ slightly (e.g., `<type 'FileNotFoundError'>` vs `FileNotFoundError`)

Flag these as acceptable variations unless the contract specifies exact string format.

### Performance and Timeout

The verification captures execution time. If target is significantly slower:
- Flag in discrepancy report
- Cross-reference with gate checker's `performance_acceptable` criterion
- May be acceptable if behavior is preserved and performance is within threshold

### Mocking and Side Effects

For functions with external dependencies (file I/O, network, database):
- Tests must use mocks to isolate behavior
- Both source and target must use identical mocks
- Verify the sequence and arguments of mock calls match

Example:
```python
# Both source and target must mock SMTP identically
with mock.patch('smtplib.SMTP') as mock_smtp:
    mock_smtp.return_value.sendmail.return_value = None
    # Run test
    # Assert mock_smtp.sendmail called with same arguments
```

## Workflow Example

### End-to-End Verification

1. **Extract contracts** (behavioral-contract-extractor):
   ```bash
   python3 skills/behavioral-contract-extractor/scripts/extract_contracts.py \
       src/ --output analysis/
   # Produces: behavioral-contracts.json, uncovered-paths.json
   ```

2. **Translate code** (e.g., Py2→Py3 automated converter):
   ```bash
   python3 skills/py2to3-automated-converter/scripts/convert.py \
       src/ --output translated/
   ```

3. **Run verification** (this skill):
   ```bash
   python3 scripts/verify_translation.py \
       --source src/io/csv_mailer.py \
       --target translated/io/csv_mailer.py \
       --contract analysis/behavioral-contracts.json \
       --test-command "pytest src/io/test_csv_mailer.py -v" \
       --output verification/
   # Produces: verification-result.json, discrepancy-analysis.json
   ```

4. **Review results**:
   ```bash
   cat verification/verification-report.md
   ```

5. **Update state** (if confident):
   ```bash
   python3 skills/py2to3-migration-state-tracker/scripts/update_state.py \
       migration-state.json record-output \
       --module "src/io/csv_mailer.py" \
       --output-path verification/verification-result.json
   ```

6. **Gate check** (before cutover):
   ```bash
   python3 skills/py2to3-gate-checker/scripts/check_gate.py \
       migration-state.json \
       --module "src/io/csv_mailer.py" \
       --output gate-report/
   # Will verify: behavioral_contract_verified criterion
   ```

## Model Tier

**Haiku (60%) + Sonnet (40%).** Running tests and checking return values against contract clauses is mechanical — use Haiku. Analyzing why a verification failed and determining whether the failure is a real regression or an expected behavioral change requires Sonnet.

Decomposition: Haiku executes all verification checks and flags failures. Sonnet analyzes only the failed checks to classify them as real bugs vs. expected changes.

## References

- `behavioral-contract-extractor` — Extract behavioral contracts from source code
- `behavioral-diff-generator` — Compare Python 2 vs Python 3 outputs directly
- `py2to3-gate-checker` — Enforce gate criteria before phase advancement (consumes verification result)
- `py2to3-migration-state-tracker` — Track module state and gate evidence
- `references/SUB-AGENT-GUIDE.md` — Delegation strategy for test execution and comparison tasks
