# Prompt for Full Suite Review

Copy and paste this into a new chat:

---

I have a complete Python 2→3 migration skill suite at `/Users/wjackson/Developer/code-translation-skills/`. All 26 skills have been built across 5 tiers. I need you to do a thorough review to make sure nothing was missed, nothing is broken, and the suite is internally consistent.

Please read these files first:

1. `PLAN.md` — the authoritative spec for all 26 skills (inputs, outputs, capabilities)
2. `BUILD-TRACKER.md` — tracks what was built and implementation details

Then perform all of the following checks:

---

## Check 1: Scaffolding Completeness

For every directory under these top-level folders, verify that each skill directory contains a `SKILL.md` and at least one script in `scripts/`:

- `orchestration/` (expect: py2to3-migration-state-tracker, py2to3-rollback-plan-generator, py2to3-gate-checker)
- `phase-0-discovery/` (expect: py2to3-codebase-analyzer, py2to3-data-format-analyzer, py2to3-serialization-detector, py2to3-c-extension-flagger, py2to3-lint-baseline-generator)
- `phase-1-foundation/` (expect: py2to3-future-imports-injector, py2to3-test-scaffold-generator, py2to3-ci-dual-interpreter, py2to3-custom-lint-rules)
- `phase-2-mechanical/` (expect: py2to3-conversion-unit-planner, py2to3-automated-converter, py2to3-build-system-updater)
- `phase-3-semantic/` (expect: py2to3-bytes-string-fixer, py2to3-library-replacement, py2to3-dynamic-pattern-resolver, py2to3-type-annotation-adder)
- `phase-4-verification/` (expect: py2to3-behavioral-diff-generator, py2to3-performance-benchmarker, py2to3-encoding-stress-tester, py2to3-completeness-checker)
- `phase-5-cutover/` (expect: py2to3-canary-deployment-planner, py2to3-compatibility-shim-remover, py2to3-dead-code-detector)

Report any directories that are missing files, any unexpected directories, or any empty scripts/ folders.

---

## Check 2: PLAN.md vs. Implementation Gap Analysis

For each of the 26 skills described in PLAN.md, verify:

1. **Inputs match**: Does the SKILL.md accept the inputs specified in PLAN.md? Flag any missing parameters (especially `target_version` for code-generating skills).
2. **Outputs match**: Does the SKILL.md promise the output files listed in PLAN.md? Flag any missing outputs.
3. **Key capabilities covered**: Read each skill's "Key capabilities" section in PLAN.md and check whether the corresponding scripts implement those capabilities. This doesn't mean reading every line — spot-check by looking for the relevant function names, pattern lists, or data structures.
4. **References used**: PLAN.md specifies which shared references each skill needs. Verify the SKILL.md mentions them and the scripts could plausibly use them.

Produce a gap table:

| Skill | Missing Inputs | Missing Outputs | Missing Capabilities | Missing References |
|-------|---------------|-----------------|---------------------|--------------------|

---

## Check 3: Shared References Completeness

Verify all 12 reference documents exist bundled in the relevant skills' `references/` directories and are non-empty:

1. `py2-py3-syntax-changes.md`
2. `py2-py3-semantic-changes.md`
3. `stdlib-removals-by-version.md`
4. `encoding-patterns.md`
5. `scada-protocol-patterns.md`
6. `serialization-migration.md`
7. `encoding-test-vectors.md`
8. `hypothesis-strategies.md`
9. `bytes-str-patterns.md`
10. `industrial-data-encodings.md`
11. `encoding-edge-cases.md`
12. `adversarial-encoding-inputs.md`

For each, report the line count and a one-sentence summary of what it covers.

---

## Check 4: Script Syntax Validation

Run `python3 -c "import py_compile; py_compile.compile('<path>', doraise=True)"` on every `.py` file across all 26 skills. Report any syntax errors with the file path and error message.

---

## Check 5: Convention Consistency

Sample 3 Tier 1-4 skills and 3 Tier 5 skills. For each, check:

1. **SKILL.md format**: Has YAML frontmatter with `name` and `description`? Has sections for inputs, outputs, workflow?
2. **Script format**: Has `#!/usr/bin/env python3` shebang? Has module docstring with usage? Uses argparse? Has type hints? Uses `# ──` section separators? Has `main()` entry point?
3. **Helper functions**: Uses `load_json()`, `save_json()`, `read_file()` pattern?
4. **Output pattern**: Main script produces JSON, separate `generate_*_report.py` produces markdown?

Report any skills that deviate from conventions.

---

## Check 6: Cross-Skill Integration Points

Verify these critical integration paths exist:

1. **Skill 0.1 → X.1**: Codebase Analyzer outputs (`raw-scan.json`, `dependency-graph.json`, `migration-order.json`) are consumed by Migration State Tracker's `init_state.py`
2. **Skill 0.2 → 3.1**: Data Format Analyzer outputs (`bytes-str-boundaries.json`, `data-layer-report.json`) are referenced by Bytes/String Boundary Fixer
3. **Skill X.1 → X.3**: Migration State Tracker's `migration-state.json` is read by Gate Checker
4. **Skill 2.1 → 2.2**: Conversion Unit Planner's output feeds Automated Converter
5. **Skill 4.4 → X.3**: Completeness Checker's `completeness-report.json` is consumed by Gate Checker for Phase 4→5 gate
6. **Skill 0.5 → 1.4**: Lint Baseline feeds Custom Lint Rule Generator
7. **Phase 0 outputs → Phase 1+ skills**: Check that Phase 1+ skills reference Phase 0 outputs in their SKILL.md inputs

For each integration point, report whether the producing skill's output format matches what the consuming skill expects.

---

## Check 7: Gate Checker Coverage

Read Skill X.3's `check_gate.py` and verify it has gate criteria for all 5 phase transitions described in PLAN.md:

- Phase 0 → 1: Assessment reviewed, plan approved, target version selected
- Phase 1 → 2: CI green with future imports, test coverage threshold, lint baseline stable
- Phase 2 → 3: Conversion units pass under both Py2 and Py3, no lint regressions
- Phase 3 → 4: Full test suite on Py3, no encoding errors, type hints on public interfaces
- Phase 4 → 5: Zero behavioral diffs, no perf regressions, encoding stress pass, completeness 100%

---

## Deliverable

Produce a single review report with:

1. **Overall status**: PASS / PASS WITH ISSUES / NEEDS WORK
2. **Issues found**: Numbered list, each with severity (CRITICAL / MODERATE / MINOR) and recommended fix
3. **Gap table** from Check 2
4. **Convention deviations** from Check 5
5. **Integration issues** from Check 6
6. **Recommendations** for hardening the suite before using it on a real codebase

---
