# Code Examples and Pattern Tables

**This file supports:** `/sessions/stoic-practical-faraday/mnt/code-translation-skills/skills/translation-verifier/SKILL.md`

## Per-Clause Verification Examples

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

Type and value must match exactly. If the target returns a different type (e.g., `float` instead of `int`), flag as failure. If the value differs, check whether it's due to:
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

For each error condition in the contract, invoke both source and target with invalid inputs. Both must raise the same exception type. Message differences are acceptable if the exception type matches.

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

Capture stdout, stderr, file system changes, and network calls (via mocks). Both source and target must produce the same side effects in the same order (unless the contract explicitly allows reordering).

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

## Confidence Scoring Scenarios

### Scenario 1: Perfect verification

```
Total clauses: 8
Passed: 8, Failed: 0, Unverifiable: 0
Confidence = 1.0 (all passed, all covered)
→ Clear for cutover
```

### Scenario 2: High confidence with some gaps

```
Total clauses: 8
Passed: 7, Failed: 0, Unverifiable: 1 (edge case: Unicode handling under specific OS locale)
Confidence = 0.875 (7/8 verified, 1 unverifiable but no failures)
→ Clear for cutover with note about Unicode locale edge case
```

### Scenario 3: Moderate confidence with failures

```
Total clauses: 8
Passed: 5, Failed: 1, Unverifiable: 2
Confidence = 0.625 ((5 / (5 + 1)) * 0.5 = 0.41, boosted by coverage of remaining clauses)
Actually: (5 passed / 8 total) * 0.8 = 0.5
→ NOT clear — must investigate the 1 failure and expand tests for the 2 unverifiable clauses
```

### Scenario 4: Low confidence due to missing tests

```
Total clauses: 8
Passed: 0, Failed: 0, Unverifiable: 8 (no tests exist)
Confidence = 0.0
→ CRITICAL: Create tests before verification can proceed. Use uncovered-paths.json from contract extractor.
```

## Verification Result JSON Example

```json
{
  "metadata": {
    "timestamp": "2025-02-12T10:30:00Z",
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

## Confidence Interpretation Table

| Confidence | Interpretation | Action |
|------------|-----------------|--------|
| **1.0** | All contract clauses verified by passing tests | Clear for cutover; no further testing needed |
| **0.95–0.99** | All clauses verified; some minor unverifiable edge cases | Clear for cutover with documentation of limitations |
| **0.8–0.94** | High confidence: most clauses verified, acceptable coverage gaps | Clear for cutover with monitoring plan |
| **0.5–0.79** | Moderate confidence: some failures or coverage gaps, requires investigation | **NOT clear for cutover** — fix identified issues or expand test coverage |
| **0.0–0.49** | Low confidence: significant failures or majority unverifiable | **DO NOT proceed** — major rework required before cutover |
| **0.0 (no tests)** | No tests available to verify contract | **Confidence cannot be assessed** — create and run tests before verification |

## Integration Examples

### Gate Checker Criterion

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

### Migration State Tracker Update

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py <state_file> \
    record-output \
    --module "src/io/csv_mailer.py" \
    --output-path <output_dir>/verification-result.json
```

### End-to-End Verification Workflow

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

## Test Consistency Example

Both source and target must be tested with identical inputs:

```bash
# Confirm both use same test invocation
pytest <contract_function> -v
# vs
pytest <contract_function> -v  # identical
```

## Encoding and String Handling Notes

When comparing string outputs, be aware of:
- **Byte strings vs Unicode strings** (Python 2 vs 3)
- **Encoding defaults** (UTF-8 assumed)
- **Exception messages** may differ slightly (e.g., `<type 'FileNotFoundError'>` vs `FileNotFoundError`)

Flag these as acceptable variations unless the contract specifies exact string format.

## Mocking and Side Effects Example

For functions with external dependencies:

```python
# Both source and target must mock SMTP identically
with mock.patch('smtplib.SMTP') as mock_smtp:
    mock_smtp.return_value.sendmail.return_value = None
    # Run test
    # Assert mock_smtp.sendmail called with same arguments
```

## Uncovered Paths Example

From behavioral-contract-extractor's uncovered-paths.json:

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

Use this to identify which code paths lack test coverage and generate targeted test cases.
