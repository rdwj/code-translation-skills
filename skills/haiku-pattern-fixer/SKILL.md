---
name: haiku-pattern-fixer
description: >
  Execute simple, mechanical pattern-level fixes from work items using a Haiku-class model.
  This skill is designed to be called thousands of times with minimal context overhead.
  Use this skill whenever you need to apply atomic pattern transformations, fix
  individual Python 2 idioms at specific line locations, batch-process pattern fixes
  across a file, or verify that fixes are correct. Also trigger when someone says
  "fix this pattern," "apply the haiku fixes," "run mechanical conversion," "fix has_key,"
  "batch pattern fixes," or "apply line-level transforms." This is the high-volume execution
  engine — designed for speed and cost-efficiency with Haiku, running thousands of times per
  large migration.
---

# Haiku Pattern Fixer

The Haiku Pattern Fixer executes mechanical, single-pattern fixes at scale. It is designed
to be called thousands of times per migration (2000+ invocations for a 500-file codebase)
with minimal context overhead. Each invocation is atomic: it receives a single work item,
applies one fix, verifies the result, and reports back. Cost efficiency and reliability are
paramount.

This skill works in concert with the work-item-generator (which decomposes the codebase
into atomic fix tasks) and the migration-state-tracker (which records results). The heavy
reasoning happens upstream in Sonnet (during work item generation); this skill's job is
mechanical execution.

## Design Philosophy

**One invocation = one atomic fix.** The skill processes a single work item per call.
The work item contains all necessary context: the file path, the pattern name, the
expected line number, the source code excerpt to match, replacement text, and a test
command. The model doesn't need to understand the full codebase — only the immediate
surrounding context.

**Reasoning is pre-computed upstream.** During Phase 1.5 (work item generation), Sonnet
analyzes the codebase, identifies conversion opportunities, and generates detailed work
items. Those work items contain the "why" (justification, risk notes, contract details).
Haiku's job is the mechanical "what" and "how" (applying the fix, running tests, reporting
results).

**Batch efficiency is built in.** Multiple work items can be chained together for a single
file, with verification after each fix. The skill can handle sequential batch processing,
reducing per-invocation overhead.

**Cost is the design constraint.** At 2000+ invocations per migration, even a 10% reduction
in average token cost per invocation saves significant money. Context is stripped to essentials.
Prompts are minimal. Decisions are binary (apply fix and test; report success/failure).

## Supported Patterns

The skill supports the following Python 2→3 pattern conversions:

| Pattern | Replacement | Example |
|---------|-------------|---------|
| `has_key` | `in` operator | `d.has_key("x")` → `"x" in d` |
| `iteritems` | `items` | `d.iteritems()` → `d.items()` |
| `itervalues` | `values` | `d.itervalues()` → `d.values()` |
| `iterkeys` | `keys` | `d.iterkeys()` → `d.keys()` |
| `xrange` | `range` | `xrange(n)` → `range(n)` |
| `raw_input` | `input` | `raw_input("x")` → `input("x")` |
| `print_statement` | `print()` | `print "x"` → `print("x")` |
| `unicode` | `str` | `unicode(x)` → `str(x)` |
| `long` | `int` | `long(x)` → `int(x)` |
| `buffer` | `memoryview` | `buffer(x)` → `memoryview(x)` |
| `apply` | direct call | `apply(f, args)` → `f(*args)` |
| `execfile` | `exec(open().read())` | `execfile("x.py")` → `exec(open("x.py").read())` |
| `cmp` | custom comparator | `cmp(a, b)` → custom function |
| `reduce` | `functools.reduce` | `reduce(f, seq)` → `functools.reduce(f, seq)` |
| `except_comma` | `except as` | `except E, e:` → `except E as e:` |
| `raise_string` | `raise Exception` | `raise "Error"` → `raise Exception("Error")` |
| `octal_literal` | `0o` prefix | `0755` → `0o755` |
| `backtick_repr` | `repr()` | `` `x` `` → `repr(x)` |
| `inequality_operator` | `!=` | `x <> y` → `x != y` |
| `configparser_rename` | stdlib rename | `import ConfigParser` → `import configparser` |
| `urllib_rename` | stdlib rename | `import urllib2` → `import urllib.request` |
| `dbm_rename` | stdlib rename | `import anydbm` → `import dbm` |
| `future_import` | `__future__` | Add `from __future__ import ...` |

## Inputs

Each invocation receives:

| Field | Type | Purpose |
|-------|------|---------|
| `work_item` | JSON object | The atomic fix task (see structure below) |
| `source_file_path` | string | Absolute path to the Python 2 source file |

### Work Item Structure

```json
{
  "id": "WI-12345",
  "pattern_name": "has_key",
  "source_file": "src/utils/config.py",
  "target_line": 42,
  "source_excerpt": "  if config.has_key(\"debug\"):",
  "expected_excerpt": "config.has_key(\"debug\")",
  "replacement": "\"debug\" in config",
  "context_lines_before": 2,
  "context_lines_after": 2,
  "test_command": "pytest src/tests/test_config.py -v",
  "behavioral_contract": {
    "description": "Dictionary containment check should work identically",
    "precondition": "config is a dict with string keys",
    "postcondition": "Boolean True/False (containment result unchanged)",
    "notes": "No performance change for small dicts; may be slower for very large dicts but semantically identical"
  },
  "risk_level": "low",
  "batch_id": "BATCH-001",
  "sequence": 1,
  "total_in_batch": 5
}
```

## Outputs

After processing a work item, the skill produces:

| File | Format | Purpose |
|------|--------|---------|
| Modified source file | Python | The file with the fix applied (in place) |
| `verification-result.json` | JSON | Pass/fail status and test output |
| `fix-report.json` | JSON | What changed, verification status, rollback command |

### Verification Result Structure

```json
{
  "work_item_id": "WI-12345",
  "pattern_name": "has_key",
  "status": "pass|fail|stale|error",
  "timestamp": "ISO-8601",
  "verification": {
    "pattern_matched": true,
    "replacement_applied": true,
    "test_command": "pytest src/tests/test_config.py -v",
    "test_exit_code": 0,
    "test_output": "...",
    "test_passed": true,
    "contract_verified": true,
    "contract_notes": "Containment semantics verified; return type unchanged"
  },
  "error_details": null
}
```

### Fix Report Structure

```json
{
  "work_item_id": "WI-12345",
  "pattern_name": "has_key",
  "source_file": "src/utils/config.py",
  "target_line": 42,
  "status": "pass|fail|stale|error",
  "changes": {
    "before_line": "  if config.has_key(\"debug\"):",
    "after_line": "  if \"debug\" in config:",
    "change_type": "pattern_replacement"
  },
  "verification_status": "pass",
  "rollback_command": "git checkout src/utils/config.py",
  "batch_id": "BATCH-001",
  "sequence": 1,
  "notes": "Pattern matched and replaced. Test suite passed. Semantic contract verified."
}
```

## Workflow Per Invocation

### Step 1: Receive and Parse Work Item

Read the work item. It contains everything needed to execute the fix:
- File path, target line, expected source excerpt, replacement text
- Test command, behavioral contract, risk level
- Batch context (batch ID, sequence number, total in batch)

### Step 2: Read Source File

Read the source file into memory. Locate the target line (expected line number, accounting
for off-by-one from editor conventions). Extract the actual line and surrounding context.

### Step 3: Match Pattern

Compare the actual line against the expected excerpt. The match must be exact (or nearly so
— whitespace variations are OK). If the pattern doesn't match, report "stale work item" and
don't apply the fix.

### Step 4: Apply Replacement

If the pattern matches, apply the replacement text. Update the line in memory. Do NOT write
to disk yet.

### Step 5: Verify Fix

Run the test command from the work item. Capture exit code and output.

- If test passes: verify behavioral contract (if provided) and continue to Step 6.
- If test fails: decide whether to rollback or report failure (see Step 6).

### Step 6: Write Result

Write the modified source file to disk (whether fix passed or failed — orchestrator decides
rollback). Write verification-result.json and fix-report.json.

If the fix failed and the file was modified, include the rollback command (git checkout,
or equivalent) in the fix-report.json so the orchestrator can undo it if needed.

## Verification Cascade

The skill performs verification in a specific order:

1. **Pattern Match**: Does the code at the target line match the expected pattern?
   - Yes → Continue to Step 2
   - No → Report "stale work item" and stop (don't apply fix)

2. **Test Pass**: Do the tests pass after the fix?
   - Yes → Continue to Step 3
   - No → Apply fix but report "test_failed". Orchestrator decides rollback.

3. **Behavioral Contract**: If the work item includes a behavioral contract, does the fix
   satisfy it?
   - Satisfied → Report "pass"
   - Not satisfied → Report "contract_violation"

4. **Final Status**:
   - All checks passed → `status: pass`
   - Pattern didn't match → `status: stale`
   - Test failed → `status: fail` (file modified, needs rollback)
   - Unexpected error → `status: error`

## Error Handling

### Stale Work Item

If the pattern at the target line doesn't match the expected excerpt (code has changed):

```json
{
  "status": "stale",
  "error_details": {
    "reason": "pattern_mismatch",
    "expected": "config.has_key(\"debug\")",
    "actual": "config.get(\"debug\", False)",
    "line": 42,
    "notes": "Code appears to have been modified since work item was generated"
  }
}
```

Report this clearly so the orchestrator can re-run the work-item-generator to refresh.

### Test Failure

If the test command fails (non-zero exit code):

```json
{
  "status": "fail",
  "verification": {
    "test_exit_code": 1,
    "test_output": "FAILED test_config.py::test_debug_flag - AssertionError: ...",
    "test_passed": false
  },
  "rollback_command": "git checkout src/utils/config.py"
}
```

The file IS modified on disk (the fix was applied). The orchestrator gets the rollback
command and can undo if needed. It can also inspect the test output to diagnose the issue.

### Unexpected Error

If something goes wrong (file not found, malformed work item, etc.):

```json
{
  "status": "error",
  "error_details": {
    "type": "file_not_found",
    "path": "/absolute/path/to/src/utils/config.py",
    "message": "File does not exist"
  }
}
```

Do NOT modify the source file in this case.

## Batch Mode

The skill can process multiple work items sequentially for a single file, verifying after
each fix:

```bash
python3 scripts/apply_fixes.py \
    --batch-file batch-001.json \
    --output-dir results/
```

Where batch-001.json contains:

```json
{
  "batch_id": "BATCH-001",
  "file_path": "src/utils/config.py",
  "work_items": [
    { "id": "WI-1", "pattern_name": "has_key", ... },
    { "id": "WI-2", "pattern_name": "iteritems", ... },
    { "id": "WI-3", "pattern_name": "print_statement", ... }
  ]
}
```

For each work item:
1. Read the current state of the file (which may have been modified by previous fixes in the batch)
2. Apply the fix
3. Verify
4. Report result
5. Move to the next work item

This way, fixes can depend on each other (e.g., if WI-2 changes a line, WI-3 is still
executed correctly because we re-read the file before locating the target line).

## Model Tier and Token Budget

**Model**: Haiku (claude-haiku-4-5 or similar)
**Context strategy**: Minimal. Each invocation receives only the work item and immediately
surrounding code (2-3 lines before/after). No full-file analysis.
**Prompt style**: Mechanical, directive. "Apply this exact fix to this exact line. Run this test.
Report success/failure."
**Expected token cost per invocation**: 400–800 tokens (including response).

Haiku is chosen because:
- Pattern matching and application is straightforward (not reasoning-heavy)
- The work item contains all decision context
- Volume (2000+ invocations) makes speed and cost critical
- Reliability is high because tasks are atomic and well-scoped

## Integration with Other Skills

**Upstream (work item generation)**:
- **Skill 1.5 (Work-Item-Generator)**: Analyzes the codebase, decomposes fixes into atomic
  work items, and writes them to a work queue. It decides WHAT to fix and WHERE; the Haiku
  fixer executes the fix.

**During (execution)**:
- **Skill 1.6 (Migration State Tracker)**: Records the result of each fix invocation. If
  a fix fails, the state tracker can trigger re-analysis or manual intervention.

**After (verification)**:
- **Skill 2.1 (Translation Verifier)**: Runs comprehensive verification across the whole
  file after a batch of fixes. Can detect failures that unit tests missed.
- **Skill 4.1 (Behavioral Diff Generator)**: Compares Python 2 and Python 3 behavior at
  the semantic level to catch subtle differences the unit tests missed.

## Important Design Choices

**Why read the file fresh for each work item in a batch?** Because fixes can change line
numbers (adding/removing lines). If we cache the line numbers from the first fix, the
second fix might target the wrong location. Re-reading before each fix ensures correctness.

**Why not auto-rollback on test failure?** Because the test failure might be a false
negative (environmental issue) or might require human judgment (the fix is correct but the
test is outdated). The orchestrator should make the rollback decision after inspecting
the output. The rollback command is always provided for convenience.

**Why track "stale work item" separately from other errors?** Because stale work items
indicate that the codebase has changed since work item generation. This is normal and
expected; the solution is to re-run the work-item-generator. Other errors are genuine
problems that need investigation.

**Why Haiku and not Claude 3.5 Sonnet?** Cost at scale. Sonnet would give higher quality
for a few fixes; Haiku gives adequate quality for thousands of fixes at 1/10 the cost.
The model choice reflects the operational reality: volume beats quality here because we
have 2000+ fixes to apply and a fixed budget.

## Example Invocation

```bash
# Single work item
python3 scripts/apply_fix.py \
    --work-item '{"id":"WI-42", "pattern_name":"has_key", ...}' \
    --source-file /absolute/path/src/utils/config.py \
    --output-dir /absolute/path/results/

# Batch processing
python3 scripts/apply_fixes.py \
    --batch-file /absolute/path/batch-001.json \
    --output-dir /absolute/path/results/
```

## Important Notes

**This skill is called thousands of times.** Small inefficiencies compound. Every aspect
(model choice, context size, prompt length, output format) is optimized for volume and cost.

**Each invocation is independent in concept but sequential in practice.** The work items
are generated upstream (with Sonnet, which costs more but runs fewer times). The Haiku
fixer just executes them (cheaply, many times).

**Failures are expected and handled gracefully.** In a 2000-fix migration, expect ~5–10%
of fixes to fail (stale work items, environmental issues, edge cases the work-item-generator
missed). The orchestrator must be prepared to triage, re-analyze, and retry.

**Rollback is cheap.** Because the skill always provides a rollback command, the
orchestrator can easily undo failed fixes and re-analyze. This is safer than trying to get
every fix perfect the first time.

## References

- `references/WORK-ITEM-GENERATOR.md` — How work items are created upstream
- `references/MIGRATION-STATE-TRACKER.md` — How state is recorded and advanced
- `references/BEHAVIORAL-DIFF-GENERATOR.md` — Semantic-level verification of fixes
