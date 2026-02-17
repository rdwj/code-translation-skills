---
name: py2to3-gate-checker
description: >
  Validate that all gate criteria for a Python 2→3 migration phase have been met before allowing
  modules or conversion units to advance. Use this skill whenever you need to check if a
  module can move to the next phase, enforce quality gates before phase transitions, audit
  compliance across the migration, or generate a gate check report for stakeholders. Also
  trigger when someone says "can this module advance," "is phase 2 complete," "run the gate
  check," "what's blocking promotion," "enforce the gate criteria," or "show me the gate
  report." This is the quality enforcement backbone — no module advances without passing
  its gate checks, and every waiver is tracked with an explicit audit trail. Now includes behavioral contract verification as an additional gate criterion when contracts are available.
---

# Gate Checker

The Gate Checker enforces discipline across the entire migration. Before any module or
conversion unit can advance from one phase to the next, it must pass a defined set of
criteria. The criteria get progressively stricter as modules move through phases — and
they're configurable, because every migration is different.

This skill integrates with the Migration State Tracker (Skill X.1). The state tracker
records where things are; the gate checker decides whether they're allowed to move forward.

## Why Gates Matter

In a large codebase with no original developers, it's tempting to rush modules through
phases to show progress. Gates prevent that. Each gate criterion exists because skipping
it has caused real problems in real migrations:

- Advancing to Phase 2 without adequate test coverage means the mechanical converter breaks
  things silently
- Advancing to Phase 3 without Phase 2 completion means semantic fixes get tangled with
  syntax changes
- Advancing to Phase 5 without encoding stress tests means production data corruption

The gate checker makes these risks visible and forces conscious decisions (via waivers)
rather than accidental oversights.

## Default Gate Criteria

Each phase transition has a default set of criteria. These can be overridden via a
configuration file (`gate-config.json`), but the defaults represent hard-won lessons
from real migrations.

### Phase 0 → 1 (Discovery → Foundation)

| Criterion | Check | Threshold |
|-----------|-------|-----------|
| `analysis_complete` | Phase 0 analysis outputs exist | Required files present |
| `report_reviewed` | Migration report has been marked as reviewed | Boolean flag in state |
| `target_version_selected` | Target Python version is set in project config | Non-empty string |
| `data_layer_analyzed` | Data Format Analyzer has run | data-layer-report.json exists |

### Phase 1 → 2 (Foundation → Mechanical Conversion)

| Criterion | Check | Threshold |
|-----------|-------|-----------|
| `future_imports_added` | All module files have `__future__` imports | 100% of files |
| `test_coverage` | Test coverage on critical-path modules | ≥ 60% (configurable) |
| `lint_baseline_stable` | Lint scores haven't regressed from baseline | No regressions |
| `ci_green_py2` | CI passes under Python 2 with future imports | Boolean |
| `high_risk_triaged` | All high-risk modules from Phase 0 have been triaged | All have decisions or notes |

### Phase 2 → 3 (Mechanical Conversion → Semantic Fixes)

| Criterion | Check | Threshold |
|-----------|-------|-----------|
| `conversion_complete` | Automated converter has processed the module | Conversion report exists |
| `tests_pass_py2` | Tests pass under Python 2 | 100% pass rate |
| `tests_pass_py3` | Tests pass under Python 3 | ≥ 90% pass rate (configurable) |
| `no_lint_regressions` | Lint score at or above baseline | No regressions |
| `conversion_reviewed` | Conversion diff has been reviewed | Review flag set |

### Phase 3 → 4 (Semantic Fixes → Verification)

| Criterion | Check | Threshold |
|-----------|-------|-----------|
| `tests_pass_py3_full` | Full test suite passes under Python 3 | 100% pass rate |
| `no_encoding_errors` | No encoding-related errors in test logs | Zero errors |
| `bytes_str_boundaries_resolved` | All bytes/str boundaries have explicit handling | 100% resolved |
| `type_hints_public` | Public interfaces have type annotations | ≥ 80% (configurable) |
| `semantic_fixes_reviewed` | All semantic fix decisions have rationale recorded | All have rationale |
| `behavioral_contract_verified` | Behavioral contract verification passed with confidence >= threshold | ≥ 0.8 (configurable) |

### Phase 4 → 5 (Verification → Cutover)

| Criterion | Check | Threshold |
|-----------|-------|-----------|
| `zero_behavioral_diffs` | No unexpected behavioral differences between Py2 and Py3 | Zero diffs |
| `performance_acceptable` | No performance regressions beyond threshold | ≤ 10% regression (configurable) |
| `encoding_stress_pass` | Encoding stress tests pass | 100% pass rate |
| `completeness_100` | Migration completeness checker reports done | 100% |
| `stakeholder_signoff` | Stakeholder has signed off on cutover | Boolean |
| `behavioral_contract_verified` | Behavioral contract verification passed with confidence >= threshold | ≥ 0.8 (configurable) |

### Phase 5 Done (Cutover Complete)

| Criterion | Check | Threshold |
|-----------|-------|-----------|
| `soak_period_complete` | Production has run on Py3 for soak period | ≥ N days (configurable) |
| `no_rollback_incidents` | No rollback-triggering incidents during soak | Zero incidents |
| `shims_removed` | Compatibility shims have been removed | Boolean |

## Inputs

- **state_file**: Path to `migration-state.json` (from the Migration State Tracker)
- **scope**: What to check — a module path, a conversion unit name, or `--all`
- **phase**: Which phase transition to check (auto-detected from current state if omitted)
- **gate_config** (optional): Path to `gate-config.json` for custom thresholds
- **analysis_dir** (optional): Directory containing Phase 0 outputs (for file-existence checks)
- **evidence_dir** (optional): Directory containing gate evidence files (test results, lint reports, etc.)

## Outputs

All outputs go to `<output_dir>/` (defaults to the analysis directory):

| File | Format | Purpose |
|------|--------|---------|
| `gate-check-report.json` | JSON | Machine-readable pass/fail per criterion with evidence |
| `gate-check-report.md` | Markdown | Human-readable summary for stakeholders |

## Workflow

### Step 1: Check a Module's Gate

```bash
python3 scripts/check_gate.py <state_file> \
    --module "src/scada/modbus_reader.py" \
    --output <output_dir> \
    [--gate-config gate-config.json] \
    [--analysis-dir <analysis_dir>] \
    [--evidence-dir <evidence_dir>]
```

This checks all criteria for the module's next phase transition and produces a pass/fail
report. If all criteria pass, the module can be advanced. If any fail, the report shows
exactly what's missing and what the module needs.

### Step 2: Check a Conversion Unit

```bash
python3 scripts/check_gate.py <state_file> \
    --unit "scada-core" \
    --output <output_dir>
```

Checks all member modules of the unit. The unit can only advance if ALL members pass.

### Step 3: Check All Modules

```bash
python3 scripts/check_gate.py <state_file> \
    --all \
    --output <output_dir>
```

Produces a comprehensive report across the entire codebase. Useful for stakeholder
dashboards and progress reporting.

### Step 4: Generate the Report

```bash
python3 scripts/generate_gate_report.py <output_dir>/gate-check-report.json \
    --output <output_dir>/gate-check-report.md
```

### Step 5: Advance (if passed)

If the gate check passes, use the Migration State Tracker to advance the module:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py <state_file> advance \
    --module "src/scada/modbus_reader.py" \
    --gate-report <output_dir>/gate-check-report.json
```

## Gate Configuration

The default thresholds can be overridden with a `gate-config.json` file:

```json
{
  "thresholds": {
    "phase_1_to_2": {
      "test_coverage": 80,
      "lint_baseline_stable": true
    },
    "phase_2_to_3": {
      "tests_pass_py3": 95
    },
    "phase_3_to_4": {
      "type_hints_public": 90
    },
    "phase_4_to_5": {
      "performance_regression_max_percent": 15,
      "soak_period_days": 14
    }
  },
  "disabled_criteria": [],
  "additional_criteria": {}
}
```

Any criterion not mentioned uses the default threshold. You can disable criteria entirely
with `disabled_criteria` (though this is recorded as equivalent to a waiver).

## Evidence Files

The gate checker looks for evidence in the evidence directory. Evidence files are produced
by other skills in the suite:

| Evidence File | Produced By | Used For |
|---------------|-------------|----------|
| `raw-scan.json` | Skill 0.1 (Codebase Analyzer) | Phase 0 analysis existence |
| `data-layer-report.json` | Skill 0.2 (Data Format Analyzer) | Data layer analysis existence |
| `lint-baseline.json` | Skill 0.5 (Lint Baseline Generator) | Lint baseline checks |
| `future-imports-report.json` | Skill 1.1 (Future Imports Injector) | Future imports coverage |
| `test-coverage-report.json` | Skill 1.2 (Test Scaffold Generator) | Coverage thresholds |
| `conversion-report.json` | Skill 2.2 (Automated Converter) | Conversion completion |
| `bytes-str-fixes.json` | Skill 3.1 (Bytes/String Boundary Fixer) | Boundary resolution |
| `behavioral-diff-report.json` | Skill 4.1 (Behavioral Diff Generator) | Zero behavioral diffs |
| `encoding-stress-report.json` | Skill 4.3 (Encoding Stress Tester) | Encoding stress pass |
| `completeness-report.json` | Skill 4.4 (Migration Completeness Checker) | 100% completeness |
| `verification-result.json` | Skill 4.2 (Translation Verifier) | Behavioral contract verification |

If an evidence file is missing, the corresponding criterion is marked as `not_evaluated`
(which counts as a failure unless waived).

## Waivers

Sometimes a criterion can't be met and the risk is accepted. The gate checker supports
waivers recorded in the migration state:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py <state_file> waiver \
    --phase 2 \
    --criterion "test_coverage >= 80%" \
    --actual-value "62%" \
    --justification "Module handles deprecated hardware no longer available for testing" \
    --approved-by "Wes Jackson"
```

Waivers don't make criteria pass — they let the gate checker report a "pass with waivers"
result that distinguishes intentional risk acceptance from actual compliance.

## Report Structure

The gate check report is structured as:

```json
{
  "scope": "module|unit|all",
  "scope_name": "src/scada/modbus_reader.py",
  "timestamp": "ISO-8601",
  "current_phase": 2,
  "target_phase": 3,
  "result": "pass|fail|pass_with_waivers",
  "criteria": [
    {
      "name": "tests_pass_py3",
      "description": "Tests pass under Python 3",
      "threshold": "≥ 90%",
      "actual": "94%",
      "status": "pass|fail|waived|not_evaluated",
      "evidence_file": "path/to/evidence.json",
      "details": "Optional additional context"
    }
  ],
  "waivers_applied": [...],
  "summary": {
    "total_criteria": 5,
    "passed": 4,
    "failed": 0,
    "waived": 1,
    "not_evaluated": 0
  }
}
```

## Integration with Other Skills

The gate checker is the bridge between skill work and phase advancement:

1. **Skills do work** → produce evidence files
2. **Gate checker validates** → reads evidence, checks criteria
3. **State tracker advances** → records the gate report and moves the module forward

After running a gate check, update the state tracker regardless of the result:

```bash
# Record the gate check output
python3 ../py2to3-migration-state-tracker/scripts/update_state.py <state_file> record-output \
    --module "src/scada/modbus_reader.py" \
    --output-path <output_dir>/gate-check-report.json
```

## Important Design Choices

**Why not auto-advance?** The gate checker reports pass/fail but doesn't automatically
advance modules. This is deliberate — phase advancement should be a conscious human
decision, even when all criteria pass. The gate checker provides the evidence; the human
(or an orchestration script) makes the call.

**Why configurable thresholds?** Every codebase is different. A 60% coverage threshold
might be aspirational for one project and embarrassingly low for another. The defaults
are sensible starting points but shouldn't be sacred.

**Why track "not_evaluated" separately from "fail"?** A missing evidence file is different
from a failed check. "Not evaluated" means the prerequisite skill hasn't run yet; "fail"
means it ran and the result didn't meet the threshold. This distinction helps diagnose
what work is actually needed.

## Behavioral Contract Verification Gate

When behavioral contracts are available (from the behavioral-contract-extractor skill),
the gate checker adds an additional criterion: `behavioral_contract_verified`.

### How it works

The translation-verifier skill produces a confidence score (0.0-1.0) for each module
by testing the translated code against its behavioral contract. The gate checker reads
these scores and requires them to meet a configurable threshold.

### Configuration

```json
{
  "behavioral_contract_gate": {
    "enabled": true,
    "confidence_threshold": 0.8,
    "applies_to_phases": [3, 4],
    "skip_if_no_contracts": true
  }
}
```

- **enabled**: Whether to enforce the behavioral contract gate. Default: `true`.
- **confidence_threshold**: Minimum confidence score required. Default: `0.8`.
- **applies_to_phases**: Which phase transitions require this gate. Default: `[3, 4]`.
- **skip_if_no_contracts**: If `true`, the gate is skipped (not failed) when no contracts
  exist for a module. Default: `true`. Set to `false` to require contracts for all modules.

### Integration

The behavioral contract gate reads from:
- `verification-result.json` produced by the translation-verifier skill
- `behavioral-contracts.json` produced by the behavioral-contract-extractor skill
- `migration-state.json` for the module's `behavioral_equivalence_confidence` field

When a module fails this gate, the gate report includes:
- Current confidence score vs threshold
- List of contract clauses that failed verification
- Suggested remediation (re-run translation-verifier after fixing issues)

## Model Tier

**Haiku.** Gate checking is threshold comparison — reading evidence files and checking values against criteria. No semantic reasoning required. Always delegate to Haiku when using sub-agents.

## References

- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
