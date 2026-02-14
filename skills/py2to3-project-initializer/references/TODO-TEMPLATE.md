# Python 2→3 Migration TODO

**Project**: {project_name}
**Target**: Python {target_version}
**Codebase size**: {file_count} Python files ({size_category})
**Initialized**: {date}

---

## Phase 0 — Discovery
{chunking_note_phase0}

- [ ] Run py2to3-codebase-analyzer → `migration-analysis/phase-0-discovery/`
- [ ] Run py2to3-data-format-analyzer → `migration-analysis/phase-0-discovery/`
- [ ] Run py2to3-serialization-detector → `migration-analysis/phase-0-discovery/`
- [ ] Run py2to3-c-extension-flagger (if applicable) → `migration-analysis/phase-0-discovery/`
- [ ] Run py2to3-lint-baseline-generator → `migration-analysis/phase-0-discovery/`
- [ ] Initialize migration state tracker
- [ ] Run gate checker for Phase 0→1
- [ ] **Write Phase 1 handoff prompt** → `migration-analysis/handoff-prompts/phase1-handoff-prompt.md`

**Gate criteria**: All 5 discovery outputs exist. Risk scores assigned to all modules. Dependency graph complete.

---

## Phase 1 — Foundation

- [ ] Run py2to3-build-system-updater (setup.py, requirements.txt, tox.ini)
- [ ] Run py2to3-future-imports-injector (`--batch-size 10`)
- [ ] Run py2to3-test-scaffold-generator (prioritize high/critical-risk modules)
- [ ] Run py2to3-conversion-unit-planner
- [ ] Run py2to3-custom-lint-rules
- [ ] Run py2to3-ci-dual-interpreter (if CI exists)
- [ ] Update migration state tracker
- [ ] Run gate checker for Phase 1→2
- [ ] **Write Phase 2 handoff prompt** → `migration-analysis/handoff-prompts/phase2-handoff-prompt.md`

**Gate criteria**: Future imports in all files. Characterization tests for high-risk modules. Conversion units defined. Build system updated.

---

## Phase 2 — Mechanical Conversion
_Process one conversion unit at a time. Update state after each unit._

- [ ] Review conversion plan from Phase 1 (wave order, unit sizes)
- [ ] For each conversion unit (in wave order):
  - [ ] Run py2to3-automated-converter on the unit
  - [ ] Run py2to3-build-system-updater if the unit includes setup.py
  - [ ] Verify: all files in unit parse as valid Python 3
  - [ ] Update migration state tracker
  - [ ] _If session is long: write a mid-phase handoff prompt_
- [ ] Run gate checker for Phase 2→3
- [ ] **Write Phase 3 handoff prompt** → `migration-analysis/handoff-prompts/phase3-handoff-prompt.md`

**Gate criteria**: All modules parse as valid Python 3. All conversion units processed. No syntax errors.

---

## Phase 3 — Semantic Fixes
_This is the hardest phase. Process one conversion unit at a time, 5–10 files per batch._

- [ ] For each conversion unit (in risk order, highest first):
  - [ ] Run py2to3-bytes-string-fixer (5–10 files per batch)
  - [ ] Run py2to3-library-replacement
  - [ ] Run py2to3-dynamic-pattern-resolver
  - [ ] Run py2to3-type-annotation-adder (if desired)
  - [ ] Run test suite for the unit
  - [ ] Update migration state tracker
  - [ ] _If session is long: write a mid-phase handoff prompt_
- [ ] Run gate checker for Phase 3→4
- [ ] **Write Phase 4 handoff prompt** → `migration-analysis/handoff-prompts/phase4-handoff-prompt.md`

**Gate criteria**: All tests pass under Python 3. No encoding errors. Bytes/str boundaries resolved.

---

## Phase 4 — Verification

- [ ] Run py2to3-behavioral-diff-generator (per conversion unit)
- [ ] Run py2to3-performance-benchmarker
- [ ] Run py2to3-encoding-stress-tester (critical paths first, then remaining)
- [ ] Run py2to3-completeness-checker (full codebase)
- [ ] Update migration state tracker
- [ ] Run gate checker for Phase 4→5
- [ ] **Write Phase 5 handoff prompt** → `migration-analysis/handoff-prompts/phase5-handoff-prompt.md`

**Gate criteria**: Behavioral equivalence verified. Performance within tolerance. No remaining Py2 artifacts. Encoding stress tests pass.

---

## Phase 5 — Cutover

- [ ] Run py2to3-canary-deployment-planner
- [ ] Run py2to3-rollback-plan-generator
- [ ] Run py2to3-compatibility-shim-remover (`--batch-size 5`)
- [ ] Run py2to3-dead-code-detector
- [ ] Final test suite run
- [ ] Update migration state tracker
- [ ] Run final gate check
- [ ] **Write migration completion summary**

**Gate criteria**: All compatibility shims removed. Dead code cleaned. Full test suite green. Rollback plan documented.

---

## Session Log

_Record each session's scope and handoff prompt location._

| Session | Date | Phase | Work Done | Handoff Prompt |
|---------|------|-------|-----------|----------------|
| 1 | {date} | 0 | Phase 0 Discovery | `handoff-prompts/phase1-handoff-prompt.md` |
| | | | | |
