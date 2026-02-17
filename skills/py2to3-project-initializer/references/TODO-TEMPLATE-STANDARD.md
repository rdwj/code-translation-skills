# Python 2→3 Migration TODO (Standard Workflow)

**Project**: {project_name}
**Target**: Python {target_version}
**Codebase size**: {file_count} Python files, {loc_count} LOC ({size_category})
**Workflow**: Standard (3 phases)
**Complexity flags**: {complexity_flags}
**Initialized**: {date}

---

## Phase 1 — Analyze + Convert
_Combines discovery, foundation, and mechanical conversion into one phase._

- [ ] Run py2to3-codebase-analyzer (summary mode) → `migration-analysis/phase-1-analyze-convert/` [Haiku]
- [ ] Run py2to3-future-imports-injector (`--batch-size 20`) [Haiku]
- [ ] Run py2to3-automated-converter (all files or by conversion unit) [Haiku]
- [ ] Run py2to3-library-replacement (if stdlib renames detected) [Haiku]
{optional_phase1_skills}
- [ ] Verify: all files parse as valid Python 3
- [ ] Run test suite
- [ ] Initialize migration state tracker (if > 50 files) [Haiku]
- [ ] **Write Phase 2 handoff prompt** (if needed)

**Gate criteria**: All files parse as Python 3. Test suite runs (may have failures from semantic issues).

---

## Phase 2 — Semantic Fixes
_Only run skills relevant to detected complexity. Skip everything else._

{semantic_skills}
- [ ] Run test suite after each batch of fixes
- [ ] Update migration state tracker [Haiku]
- [ ] **Write Phase 3 handoff prompt** (if needed)

**Gate criteria**: All tests pass under Python 3. No encoding errors.

---

## Phase 3 — Verify + Cutover
_Combines verification and cutover into one phase._

- [ ] Run py2to3-completeness-checker [Haiku]
- [ ] Run py2to3-dead-code-detector [Haiku]
- [ ] Run py2to3-compatibility-shim-remover (remove six, __future__ if no longer needed) [Haiku]
- [ ] Final test suite run
- [ ] **Write migration completion summary**

**Gate criteria**: No remaining Py2 artifacts. Full test suite green. Dead code removed.

---

## Session Log

| Session | Date | Phase | Work Done | Handoff Prompt |
|---------|------|-------|-----------|----------------|
| 1 | {date} | 1 | Analyze + Convert | |
| | | | | |
