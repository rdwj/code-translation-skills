# Skill Update Plan — Universal Code Graph Integration

This document tracks the work needed to update existing skills and create new skills
based on the architecture in `ARCHITECTURE-universal-code-graph.md`. It's designed to
survive context window boundaries — any session can pick up where the last left off.

## Reference Documents

- `ARCHITECTURE-universal-code-graph.md` — Full architecture with component details, code sketches, and design decisions
- Each skill's `SKILL.md` — The source of truth for that skill's behavior

## Status Key

- [ ] Not started
- [~] In progress
- [x] Complete

---

## Part A: Update Existing Skills (7 skills)

### A1. py2to3-codebase-analyzer [STATUS: COMPLETE]

**Why:** Foundation skill. Currently describes ast-only pipeline with regex fallback. Needs to reflect tree-sitter path, language detection, universal extraction, multi-language support, and new output files.

**Changes to SKILL.md:**

1. **Description/frontmatter:** Broaden from "Python 2 codebase" to "codebase analysis" that handles Python 2, Python 3, and polyglot codebases. Keep py2to3 focus as primary but acknowledge multi-language.

2. **When to Use:** Add: "When analyzing a polyglot codebase," "When Python ast.parse() fails on legacy code," "When you need a language-agnostic dependency graph."

3. **Inputs:** Add `--languages` (optional, auto-detect if omitted). Note that language detection is automatic via identify + pygments.

4. **Outputs table:** Add new outputs: `call-graph.json`, `codebase-graph.graphml`, `behavioral-contracts.json`, `work-items.json`. Note `language` field added to existing outputs.

5. **Workflow Step 1 (Discover):** Add tree-sitter as fallback when ast fails. Describe the two-pipeline approach: ast-first for Python files, tree-sitter for everything else. Reference `analyze_universal.py`.

6. **Workflow — new step: Language Detection.** Describe the two-pass detection (identify + pygments) and lazy grammar loading.

7. **Workflow — new step: Depends Enrichment.** Optional step when JRE available.

8. **Scripts Reference:** Add `analyze_universal.py`, `ts_parser.py`, `universal_extractor.py`, `language_detect.py`, `depends_runner.py`, `py2_patterns_ts.py`. Keep existing scripts as-is (they still work).

9. **Pattern Categories:** Keep all existing categories. Add note that tree-sitter detects the same patterns when ast fails, producing identical findings format.

10. **New section: Multi-Language Support.** List supported languages. Explain that `.scm` query files drive extraction. Note that adding a language = writing 3 query files.

11. **New section: Atomic Work Decomposition.** Explain that the analyzer now produces work items tagged with model tiers (Haiku/Sonnet/Opus). Reference `work-items.json` output.

---

### A2. py2to3-conversion-unit-planner [STATUS: COMPLETE]

**Why:** Currently plans waves of Python-only modules. Needs multi-language awareness, work item integration, and behavioral contract input.

**Changes to SKILL.md:**

1. **Inputs:** Add `behavioral-contracts.json` (optional), `work-items.json` (optional). Note that nodes in dependency graph now have `language` property.

2. **What the Planner Does:** Add new subsection: "7. Work Item Integration" — the planner can now produce not just wave/unit plans but atomic work items with model-tier routing. Each unit's work is decomposed into Haiku-executable items for mechanical fixes and Sonnet-executable items for complex changes.

3. **Conversion Plan Structure:** Add `model_tier_breakdown` per unit showing estimated Haiku/Sonnet/Opus split. Add `behavioral_contracts_available: boolean` field.

4. **Integration with Other Skills:** Add references to new skills: behavioral-contract-extractor, work-item-generator, haiku-pattern-fixer.

5. **New section: Cross-Language Planning.** When the dependency graph contains non-Python nodes, the planner treats them equally — wave ordering respects cross-language dependencies. Note that conversion approach differs by language (ast-transform for Python, LLM-driven for others).

---

### A3. py2to3-behavioral-diff-generator [STATUS: COMPLETE]

**Why:** Currently compares Py2 vs Py3 interpreter outputs. Gains behavioral contracts as additional comparison source and expanded verification role.

**Changes to SKILL.md:**

1. **Description:** Broaden to include contract-based verification, not just interpreter comparison.

2. **Inputs:** Add `--behavioral-contracts` (optional path to contracts JSON). When provided, generates targeted test cases for uncovered code paths.

3. **Workflow — new step: Contract-Based Verification.** When behavioral contracts are available, the diff generator can: (a) generate test cases from contract specifications, (b) verify that both Py2 and Py3 satisfy the contract, (c) flag contract violations separately from interpreter diffs.

4. **Outputs:** Add `contract-violations.json` — cases where code doesn't match its behavioral contract (separate from interpreter diffs).

5. **Integration:** Add role in verification cascade: Haiku runs individual function tests → behavioral-diff-generator runs module-level verification → gate-checker reads results.

---

### A4. py2to3-migration-state-tracker [STATUS: COMPLETE]

**Why:** State schema needs new fields for behavioral confidence, modernization opportunities, model tier tracking, and language property.

**Changes to SKILL.md:**

1. **Data Model — Module State:** Add fields: `language` (string, detected language), `behavioral_equivalence_confidence` (float 0-1 or null), `modernization_opportunities` (list of opportunity objects), `model_tier_used` (string: haiku/sonnet/opus), `behavioral_contract` (object or null, summary of contract).

2. **Data Model — Conversion Units:** Add `languages` field (set of languages in unit).

3. **Data Model — Summary:** Add `by_language` breakdown alongside existing `by_phase` and `by_risk`.

4. **Update commands:** Add new update_state.py subcommands: `set-behavioral-confidence`, `add-modernization-opportunity`, `set-model-tier`.

5. **Query commands:** Add: `by-language --language python`, `modernization-opportunities`, `behavioral-confidence --threshold 0.8`.

6. **Dashboard Output:** Add language breakdown, behavioral confidence summary, modernization opportunities count, model tier cost tracking.

---

### A5. py2to3-gate-checker [STATUS: COMPLETE]

**Why:** Needs new gate criterion: behavioral contract verification.

**Changes to SKILL.md:**

1. **Gate Criteria table:** Add new criterion for applicable phases: `behavioral_contract_verified` — "Behavioral contract verification passed with confidence >= threshold." Default threshold: 0.8.

2. **Phase advancement rules:** Note that behavioral contract verification is optional (degrades gracefully when contracts aren't available). When available, it's an additional gate criterion, not a replacement for existing ones.

3. **Integration:** Reference translation-verifier skill as the source of behavioral verification results.

---

### A6. py2to3-dead-code-detector [STATUS: COMPLETE]

**Why:** Gains tree-sitter queries for detecting unused code in files ast can't parse. Enables dead code detection in non-Python files.

**Changes to SKILL.md:**

1. **Description:** Add that it can now detect dead code in files that fail ast.parse() and in non-Python files (when tree-sitter is available).

2. **How it Works:** Add tree-sitter fallback path. When ast fails, tree-sitter queries extract function/class definitions and call relationships. Cross-reference against the universal graph to identify unreachable code.

3. **Multi-Language dead code:** For non-Python files, the same graph-based reachability analysis works: if no path in the call graph reaches a function, it's dead. Language-specific query files provide the definition/call extraction.

4. **Dependencies:** Note optional dependency on tree-sitter and universal-code-graph skill outputs.

---

### A7. py2to3-automated-converter [STATUS: COMPLETE]

**Why:** Stays ast-only for Python tree transforms, but needs to acknowledge LLM-driven translation for non-Python and the behavioral contract integration.

**Changes to SKILL.md:**

1. **Description:** Clarify that this skill handles Python-specific ast transformations. For non-Python translation, the work-item-generator + haiku-pattern-fixer + modernization-advisor skills handle the work.

2. **New section: Integration with Universal Code Graph.** When behavioral contracts are available, the converter can: (a) validate that its transformations preserve the contract, (b) use contract-derived test cases for post-conversion verification.

3. **New section: Model-Tier Awareness.** The converter can receive work items from the work-item-generator. Simple pattern fixes (HAIKU_PATTERNS) can be applied with minimal context. Complex transformations still require the full ast pipeline.

4. **Limitations:** Explicitly note that ast.NodeTransformer cannot be used for non-Python files. For cross-language migration, the translation is LLM-driven using behavioral contracts as the specification.

---

## Part B: Create New Skills (7 skills)

### B1. universal-code-graph [STATUS: COMPLETE]

**Purpose:** Core infrastructure skill. Tree-sitter parsing, language detection, universal extraction, graph building. The foundation everything else builds on.

**SKILL.md should cover:**
- When to use (first step in any codebase analysis, especially polyglot or Python 2)
- Inputs: codebase path, exclude patterns, optional language filter
- Outputs: raw-scan.json (enhanced), dependency-graph.json (language-aware), call-graph.json, codebase-graph.graphml
- Workflow: language detection → grammar loading → file-by-file extraction → graph building → optional depends enrichment
- Scripts: analyze_universal.py, ts_parser.py, universal_extractor.py, language_detect.py, depends_runner.py, py2_patterns_ts.py, graph_builder.py
- Query files: explain the .scm pattern, how to add new languages
- Dependencies: tree-sitter, tree-sitter-language-pack, identify, networkx, optional pygments and depends
- Integration: produces outputs consumed by all downstream skills

**Directory structure to create:**
```
skills/universal-code-graph/
  SKILL.md
  scripts/       (empty for now, populated during implementation)
  queries/       (empty for now)
  dashboard/     (empty for now)
  assets/
  tools/
  references/
```

---

### B2. behavioral-contract-extractor [STATUS: COMPLETE]

**Purpose:** Extract behavioral contracts for functions/modules. Uses tree-sitter structural data + LLM reasoning (Sonnet) to produce contracts.

**SKILL.md should cover:**
- When to use (after codebase analysis, before translation or verification)
- Inputs: raw-scan.json, call-graph.json, codebase source files
- Outputs: behavioral-contracts.json (per-function contracts)
- Workflow: for each function in topological order, extract contract using structural data + LLM
- Contract format: inputs, outputs, side effects, error conditions, implicit behaviors, complexity, purity
- Model tier: Sonnet for extraction (needs to infer intent from code)
- Scope: processes one function at a time with call-graph neighborhood as context
- Integration: feeds into work-item-generator, translation-verifier, behavioral-diff-generator, migration dashboard

---

### B3. work-item-generator [STATUS: COMPLETE]

**Purpose:** Takes raw scan + dependency graph + contracts + conversion plan → produces atomic work items with model-tier routing.

**SKILL.md should cover:**
- When to use (after analysis and optional contract extraction, before actual migration work)
- Inputs: raw-scan.json, dependency-graph.json, conversion-plan.json, behavioral-contracts.json (optional)
- Outputs: work-items.json (ordered list of atomic work items with model tier, context, verification)
- Model routing logic: HAIKU_PATTERNS, SONNET_PATTERNS, OPUS_PATTERNS classification
- Work item format: id, type, model_tier, context (file, function, source, dependencies), task (pattern, line, fix), verification (contract, test command, rollback)
- Estimated cost impact: ~70% Haiku, ~25% Sonnet, ~5% Opus
- Integration: produces items consumed by haiku-pattern-fixer, automated-converter, modernization-advisor

---

### B4. haiku-pattern-fixer [STATUS: COMPLETE]

**Purpose:** Executes simple pattern-level fixes from work items. Designed to be called thousands of times with Haiku.

**SKILL.md should cover:**
- When to use (when work items with model_tier=haiku exist)
- Inputs: single work item (JSON), source file
- Outputs: modified source file, verification result, status report
- Design: completely self-contained. Receives work item, applies fix, runs verification, reports result
- Supported patterns: full list of HAIKU_PATTERNS (has_key, xrange, print, except syntax, etc.)
- Verification cascade: apply fix → run function test → check behavioral contract → report
- Rollback: each work item includes rollback command
- Error handling: if fix fails verification, report failure without rollback (let orchestrator decide)
- Model: explicitly Haiku — prompts are designed for small-model execution with maximum context

---

### B5. translation-verifier [STATUS: COMPLETE]

**Purpose:** Runs behavioral contract verification after translation. Compares source behavior vs target behavior, reports confidence score.

**SKILL.md should cover:**
- When to use (after any translation/conversion work, before gate check)
- Inputs: behavioral contract, source file, target file, test commands
- Outputs: verification-result.json (confidence score, pass/fail per contract clause, discrepancies)
- Workflow: run source tests → capture baseline → run target tests → compare against contract → score
- Confidence scoring: 1.0 = all contract clauses verified, 0.0 = no verification possible
- Integration: feeds into gate-checker (behavioral_contract_verified criterion), migration-state-tracker (confidence field), dashboard
- Model: Haiku for test execution and comparison, Sonnet for analyzing discrepancies

---

### B6. modernization-advisor [STATUS: COMPLETE]

**Purpose:** Given a behavioral contract and target language, suggests idiomatic alternatives. "This 40-line function could be 8 lines with serde."

**SKILL.md should cover:**
- When to use (during or after migration planning, when exploring target language options)
- Inputs: behavioral contract for a function/module, target language, source code
- Outputs: modernization-opportunities.json (per-function suggestions with estimated reduction, risk, target-language specifics)
- Approach: compare contract against target language ecosystem — standard library, popular crates/packages, idiomatic patterns
- Model: Sonnet (needs language ecosystem knowledge and judgment)
- Integration: feeds into dashboard (opportunities panel), migration-state-tracker (opportunities field)
- NOT a replacement for structural translation — this is advisory. Suggestions go to human review.

---

### B7. migration-dashboard [STATUS: COMPLETE]

**Purpose:** Standalone skill that generates/serves the HTML dashboard. Reads all JSON outputs, renders split-pane graph with status colors.

**SKILL.md should cover:**
- When to use (after any migration work, for progress tracking and stakeholder communication)
- Inputs: migration-state.json, dependency-graph.json, behavioral-contracts.json (optional), work-items.json (optional)
- Outputs: dashboard/index.html (self-contained HTML file with embedded data)
- Features: split-pane force-directed graphs (source/target), status color coding, progress bar, cluster view, risk heatmap, blockers list, timeline projection, modernization opportunities panel, behavioral confidence indicators, model-tier cost tracking
- Based on existing dependency-graph-template.html Canvas rendering
- No backend required — client-side JS reading JSON files via file:// or tiny local server
- Color scheme: gray (not started), yellow (in progress), red (blocked), blue (migrated), green (tested), dark green (evaluated), purple (deployed)

---

## Execution Order

The recommended order for working through these:

1. **B1: universal-code-graph** — Foundation, everything depends on it
2. **A1: py2to3-codebase-analyzer** — Primary consumer, most extensive changes
3. **B2: behavioral-contract-extractor** — Needed by verification and planning skills
4. **B3: work-item-generator** — Needed by execution skills
5. **A2: py2to3-conversion-unit-planner** — Consumes new outputs
6. **B4: haiku-pattern-fixer** — Main execution engine
7. **B5: translation-verifier** — Verification layer
8. **A3: py2to3-behavioral-diff-generator** — Extended verification
9. **A4: py2to3-migration-state-tracker** — Schema updates
10. **A5: py2to3-gate-checker** — New gate criteria
11. **B6: modernization-advisor** — Advisory layer
12. **B7: migration-dashboard** — Visualization
13. **A6: py2to3-dead-code-detector** — Tree-sitter fallback
14. **A7: py2to3-automated-converter** — Integration notes

## Progress Log

Use this section to track what's been completed across context windows.

| # | Skill | Status | Date | Notes |
|---|-------|--------|------|-------|
| B1 | universal-code-graph | COMPLETE | 2026-02-17 | New skill created with full SKILL.md, directory structure |
| A1 | codebase-analyzer | COMPLETE | 2026-02-17 | Added tree-sitter fallback, polyglot awareness, work decomposition, new outputs |
| B2 | behavioral-contract-extractor | COMPLETE | 2026-02-17 | New skill created with full SKILL.md, directory structure |
| B3 | work-item-generator | COMPLETE | 2026-02-17 | New skill created with full SKILL.md, directory structure |
| A2 | conversion-unit-planner | COMPLETE | 2026-02-17 | Added work item integration, cross-language planning, behavioral contracts input |
| B4 | haiku-pattern-fixer | COMPLETE | 2026-02-17 | New skill created with full SKILL.md, directory structure |
| B5 | translation-verifier | COMPLETE | 2026-02-17 | New skill created with full SKILL.md, directory structure |
| A3 | behavioral-diff-generator | COMPLETE | 2026-02-17 | Added contract-based verification, targeted test generation, verification cascade |
| A4 | migration-state-tracker | COMPLETE | 2026-02-17 | Added language, behavioral confidence, modernization, model-tier fields + commands |
| A5 | gate-checker | COMPLETE | 2026-02-17 | Added behavioral_contract_verified gate criterion with configuration |
| B6 | modernization-advisor | COMPLETE | 2026-02-17 | New skill created with full SKILL.md, directory structure |
| B7 | migration-dashboard | COMPLETE | 2026-02-17 | New skill created with full SKILL.md, directory structure |
| A6 | dead-code-detector | COMPLETE | 2026-02-17 | Added tree-sitter fallback, multi-language dead code via call graph |
| A7 | automated-converter | COMPLETE | 2026-02-17 | Added behavioral contract validation, model-tier awareness, non-Python limitations |

## Round 2: Adaptive Sizing + Model Tier Optimization (2026-02-17)

Motivated by testing on a small project where Phase 0 alone took 30 minutes — the same time a competitor finished the entire migration. The suite was treating every project the same regardless of size.

### Changes Made

| # | What | Status | Notes |
|---|------|--------|-------|
| R2-1 | Rewrote py2to3-project-initializer SKILL.md | COMPLETE | Added quick_size_scan, Express/Standard/Full workflows, sizing thresholds |
| R2-2 | Created references/TODO-TEMPLATE-STANDARD.md | COMPLETE | 3-phase condensed template for medium projects |
| R2-3 | Created references/MODEL-TIER-GUIDE.md | COMPLETE | Central reference: per-skill model tier table, decomposition patterns, cost estimates |
| R2-4 | Added "## Model Tier" to all 34 skills | COMPLETE | 15 Haiku-only, 10 Haiku+Sonnet decomposable, 7 Sonnet with Haiku preprocessing, 2 Sonnet-only |

### Key Design Decisions

- **Express workflow** for ≤20 files: 4 skills max, single session, all Haiku, no scaffolding overhead
- **Standard workflow** for 21-100 files: 3 phases instead of 6, selective skill use, 2-4 sessions
- **Full workflow** for 100+ files: unchanged 6-phase pipeline
- **Complexity escalators** can bump a project up a tier (C extensions, binary protocols, zero tests)
- **Every skill now has explicit model-tier guidance** with decomposition strategies where applicable

## Round 3: Script Offload Analysis (2026-02-17)

Motivated by hitting API usage limits. Identified that many skills describe deterministic work that the LLM does at token cost when scripts could do it for free.

### Changes Made

| # | What | Status | Notes |
|---|------|--------|-------|
| R3-1 | Created SCRIPT-OFFLOAD-PLAN.md | COMPLETE | Comprehensive audit of all 34 skills, categorized offload opportunities |

### Key Findings

- **7 skills had no scripts at all** despite describing fully/mostly deterministic work
- **5 skills had scripts that punted logic to the LLM** that should be in-script
- **11 skills already had complete scripts** — no changes needed
- Estimated 73-80% token savings from implementing all script offloads

## Round 4: Script Implementation (2026-02-17)

Implemented all P0 (new scripts) and P1 (enhanced existing scripts) from the offload plan.

### P0: New Scripts Created (11 scripts, ~5,813 lines total)

| # | Script | Skill | Lines | Status |
|---|--------|-------|-------|--------|
| 1 | quick_size_scan.py | py2to3-project-initializer | 447 | COMPLETE ✓ |
| 2 | generate_work_items.py | work-item-generator | 594 | COMPLETE ✓ |
| 3 | language_detect.py | universal-code-graph | 321 | COMPLETE ✓ |
| 4 | ts_parser.py | universal-code-graph | 225 | COMPLETE ✓ |
| 5 | universal_extractor.py | universal-code-graph | 293 | COMPLETE ✓ |
| 6 | graph_builder.py | universal-code-graph | 474 | COMPLETE ✓ |
| 7 | verify_translation.py | translation-verifier | 759 | COMPLETE ✓ |
| 8 | extract_contracts.py | behavioral-contract-extractor | 849 | COMPLETE ✓ |
| 9 | apply_fix.py | haiku-pattern-fixer | 517 | COMPLETE ✓ |
| 10 | check_modernization.py | modernization-advisor | 462 | COMPLETE ✓ |
| 11 | generate_dashboard.py | migration-dashboard | 872 | COMPLETE ✓ |

### P1: Enhanced Existing Scripts (3 scripts enhanced, 2 verified complete)

| # | Script | Enhancement | Status |
|---|--------|------------|--------|
| 1 | generate_diffs.py | Added 5 missing expected-diff patterns + flagged-for-review.json output | ENHANCED ✓ |
| 2 | detect_dead_code.py | Added unreachable code detection + flagged-for-review.json output | ENHANCED ✓ |
| 3 | check_completeness.py | Audited — all 10 categories already implemented | VERIFIED ✓ |
| 4 | generate_tests.py | Added property-based test generation (Hypothesis) | ENHANCED ✓ |
| 5 | detect_serialization.py | Audited — all 10 categories + risk rules already implemented | VERIFIED ✓ |

### Verification

- All 11 new scripts pass Python 3 syntax check (py_compile)
- All 3 enhanced scripts pass Python 3 syntax check
- quick_size_scan.py functionally tested on sample project — correctly identifies small project, applies complexity escalators, recommends workflow

## Round 5: Second-Pass Review — Infrastructure & Optimization (2026-02-17)

Deep review of all scripts and skills identified 5 additional optimization opportunities. All implemented.

### Changes Made

| # | What | Status | Notes |
|---|------|--------|-------|
| R5-1 | Reference file deduplication | COMPLETE | Consolidated 47 duplicate copies of 11 files to `docs/references/shared/`, created 27 INDEX.md pointers, removed 22,946 lines |
| R5-2 | analyze_universal.py orchestrator | COMPLETE | Chains language_detect → ts_parser → universal_extractor → graph_builder into single CLI call with regex fallback |
| R5-3 | Phase runner scripts (7 scripts) | COMPLETE | phase0-phase5 runners + run_express.py eliminate LLM orchestration between skills |
| R5-4 | Trim oversized SKILL.md files | COMPLETE | Top 5 files trimmed from avg 595 → avg 257 lines; examples extracted to references/EXAMPLES.md |
| R5-5 | Tree-sitter .scm query files | COMPLETE | 8 query files for Python, JavaScript, Java (definitions, imports, calls) |

### R5-1: Reference Deduplication Details

11 unique reference files were duplicated across 27 skills (47 total copies, 22,946 redundant lines):

| File | Copies Found | Shared Location |
|------|-------------|-----------------|
| SUB-AGENT-GUIDE.md | 8 | docs/references/shared/ |
| py2-py3-semantic-changes.md | 6 | docs/references/shared/ |
| py2-py3-syntax-changes.md | 5 | docs/references/shared/ |
| bytes-str-patterns.md | 4 | docs/references/shared/ |
| + 7 more files | various | docs/references/shared/ |

### R5-3: Phase Runner Scripts

| Script | Skills Chained | Workflow |
|--------|---------------|----------|
| phase0_discovery.py | quick_size_scan → analyze_universal → analyze | Full/Standard |
| phase1_foundation.py | inject_futures → run_lint → generate_tests | Full/Standard |
| phase2_mechanical.py | generate_work_items → apply_fix (loop) → replace_libs | Full/Standard |
| phase3_semantic.py | Prepares semantic-review-brief.json for LLM | Full only |
| phase4_verification.py | verify_translation → check_completeness → detect_dead_code → check_gate | Full/Standard |
| phase5_cutover.py | remove_shims → update_build → generate_ci → generate_dashboard | Full/Standard |
| run_express.py | Chains phases 0→1→2→4 in single command | Express |

### R5-4: SKILL.md Trimming

| Skill | Before | After | Reduction |
|-------|--------|-------|-----------|
| modernization-advisor | 638 | 269 | 58% |
| py2to3-bytes-string-fixer | 593 | 270 | 55% |
| py2to3-dynamic-pattern-resolver | 585 | 151 | 74% |
| py2to3-compatibility-shim-remover | 584 | 289 | 50% |
| translation-verifier | 577 | 306 | 47% |

### R5-5: Tree-sitter Query Files

Created in `skills/universal-code-graph/queries/`:
- python-definitions.scm, python-imports.scm, python-calls.scm
- javascript-definitions.scm, javascript-imports.scm, javascript-calls.scm
- java-definitions.scm, java-imports.scm

## Round 6: Workspace Strategy (2026-02-17)

Previously, the skill suite assumed in-place modification of the source tree. This was risky — one bad conversion could corrupt the production codebase, and rollback depended entirely on git revert. Round 6 adds a peer-directory workspace strategy.

### Changes Made

| # | What | Status | Notes |
|---|------|--------|-------|
| R6-1 | Added "Step 0: Create the Workspace" to project-initializer SKILL.md | COMPLETE | Peer directory strategy, git branch setup, rationale |
| R6-2 | Updated init_migration_project.py | COMPLETE | Added `--workspace`, `--in-place`, `--workflow` flags; auto-creates `<project>-py3/` copy; creates git branch; records source_root + workspace in migration-state.json |
| R6-3 | Updated Inputs/Outputs in project-initializer SKILL.md | COMPLETE | New inputs table, workspace output row, migration-state includes paths |
| R6-4 | Added "Workspace Assumption" section to automated-converter SKILL.md | COMPLETE | Clarifies that codebase_path should be the workspace, not original source |
| R6-5 | Updated HANDOFF-PROMPT-GUIDE.md context block | COMPLETE | Handoff prompts now include both workspace and original source paths |

### Key Design Decision

```
parent-dir/
├── my-project/              ← original source (READ-ONLY during migration)
├── my-project-py3/          ← working copy (all edits happen here)
│   ├── <full source copy>
│   └── migration-analysis/  ← scaffolding, reports, state
```

**Why peer directory, not in-place?**
- Original source always available for diff comparison
- No risk of corrupting production codebase
- Git history stays clean (migration is one branch)
- Easy rollback: delete workspace and start over
- Multiple migration attempts can coexist

## Round 7: Security Scanner + SBOM (2026-02-18)

Motivated by the need to ensure migration output is secure and auditable. Py2→3 migrations introduce security risk: dependency upgrades can pull vulnerable versions, mechanical transformations can introduce anti-patterns, and pickle protocol changes widen deserialization surfaces.

### Changes Made

| # | What | Status | Notes |
|---|------|--------|-------|
| R7-1 | Created py2to3-security-scanner skill | COMPLETE | New skill with SKILL.md — covers SBOM, vuln scanning, static analysis, secrets, migration-specific checks |
| R7-2 | Created security_scan.py (935 lines) | COMPLETE | CycloneDX SBOM generation, pip-audit/OSV vuln scanning, Bandit/regex static analysis, secret detection, migration-specific checks, delta comparison |
| R7-3 | Wired into Full workflow TODO template | COMPLETE | Phase 0 (baseline), Phase 2 (regression), Phase 5 (final audit) |
| R7-4 | Wired into Standard workflow TODO template | COMPLETE | Phase 1 (baseline), Phase 3 (final audit) |
| R7-5 | Wired into phase runner scripts | COMPLETE | phase0_discovery.py, phase2_mechanical.py, phase5_cutover.py all invoke security_scan.py |
| R7-6 | Added security gate criteria | COMPLETE | Phase 0→1: baseline recorded. Phase 2→3: no new critical/high. Phase 5 Done: audit complete + SBOM |

### Key Design Decisions

- **Woven, not a separate phase.** Security scanning runs at three points in the existing phase structure: discovery (baseline), post-mechanical (regression delta), and pre-cutover (final audit + SBOM deliverable).
- **SBOM is a first-class output.** CycloneDX 1.5 JSON format. Generated at baseline and updated at final. The final SBOM is the deliverable for security review.
- **Script does all scanning, LLM reviews flags.** The 935-line script handles Bandit, pip-audit, OSV API, secret detection, and migration-specific patterns. Low-confidence findings go to `flagged-for-review.json` for Sonnet triage.
- **Graceful degradation.** If Bandit isn't installed, falls back to regex. If pip-audit isn't installed, calls OSV API directly. If offline, skips vuln DB with warning. The scan always produces output.
- **Delta comparison is the key metric.** The regression and final scans compare against the baseline to answer "did the migration make security worse?" Pre-existing findings are noted but don't block.
- **Migration-specific checks.** Beyond generic SAST, the scanner checks for Py2→3 specific risks: `input()` eval injection, pickle protocol changes, `exec(open())` patterns, hash randomization, SSL default changes.

### Scan Components

| Component | Tool | Fallback |
|-----------|------|----------|
| SBOM generation | Custom parser (requirements, setup.py, pyproject.toml, Pipfile, vendored) | Always works |
| Vulnerability scan | `pip-audit` subprocess | OSV API → offline skip |
| Static analysis | `bandit -f json` subprocess | 13-pattern regex scan |
| Secret detection | Custom regex (AWS, GitHub, Slack, PEM, passwords, conn strings) | Always works |
| Migration-specific | Custom checks (6 patterns) | Always works |
| Dependency pinning | Custom parser | Always works |

## Round 7.5: Script Logging (2026-02-18)

Added observability to all 73 scripts so post-migration analysis can verify whether the LLM agent actually used our scripts.

### Changes Made

| # | What | Status | Notes |
|---|------|--------|-------|
| R7.5-1 | Created `scripts/lib/migration_logger.py` | COMPLETE | Shared logging module (~246 lines): `setup_logging()`, `@log_execution` decorator, `log_invocation()` for JSONL |
| R7.5-2 | Created `scripts/lib/__init__.py` | COMPLETE | Package marker |
| R7.5-3 | Added logging to 7 phase runner scripts | COMPLETE | Import block + `@log_execution` + `log_invocation()` in `run_script()` |
| R7.5-4 | Updated 8 existing-logging scripts | COMPLETE | Replaced `logging.basicConfig` with shared `setup_logging()` |
| R7.5-5 | Added logging to 58 non-logging scripts | COMPLETE | 3-line import block + `@log_execution` decorator |
| R7.5-6 | Added `logs/` to init directory structure | COMPLETE | `create_directory_structure()` in init_migration_project.py |

### Log Outputs

- `migration-analysis/logs/migration-audit.log` — chronological text log (all scripts write START/END entries)
- `migration-analysis/logs/skill-invocations.jsonl` — structured JSONL from phase runners (script, skill, args, exit_code, duration_s, stdout/stderr bytes)

## Round 8: Skill Usage Dashboard (2026-02-18)

Post-migration dashboard answering "Which skills ran? Which were skipped? Is the agent using our scripts?"

### Changes Made

| # | What | Status | Notes |
|---|------|--------|-------|
| R8-1 | Created `generate_skill_usage_dashboard.py` | COMPLETE | ~650 lines: parses audit.log + JSONL, builds inventory, categorizes skips, generates self-contained HTML |
| R8-2 | Updated migration-dashboard SKILL.md | COMPLETE | Added Skill Usage Dashboard section with docs, usage, data sources |
| R8-3 | Updated SKILL-UPDATE-PLAN.md | COMPLETE | Rounds 7.5 and 8 |

### Dashboard Features

- **Summary cards**: script coverage, skill coverage, failures, total runtime
- **Skill coverage table**: sortable, filterable by status (Complete / Partial / Expected Skip / Potential Gap)
- **Execution time chart**: canvas bar chart of top-20 slowest scripts
- **Failure summary**: scripts with exit_code != 0
- **All invocations table**: every execution record, sortable
- **Skip analysis**: expected skips (project too small, no C extensions, etc.) vs potential gaps

### Key Design Decisions

- **Dual-source parsing**: reads both `migration-audit.log` (from @log_execution on all 66 scripts) and `skill-invocations.jsonl` (from phase runner log_invocation()). Deduplicates by script+timestamp.
- **Dynamic inventory discovery**: walks `skills/*/scripts/*.py` at runtime with hardcoded fallback manifest of all 35 skills / 66 scripts.
- **Skip categorization**: uses project sizing, workflow type, and scan results to distinguish "expected skip" from "potential gap".
- **Self-contained HTML**: dark theme, embedded JSON, client-side sorting/filtering, canvas charts — same pattern as migration progress dashboard.

## Next Steps (Remaining Work)

### P2: Additional Tree-sitter Queries

1. `py2_patterns_ts.py` — Tree-sitter queries for all 20+ Python 2 patterns
2. Query files for Go, Rust, Ruby, C/C++ (3 queries × 5 languages = 15 `.scm` files)

### P3: Integration and Polish

3. `depends_runner.py` — multilang-depends subprocess integration
4. Update existing skill scripts with tree-sitter fallback paths
5. Generalize naming, create target-language template skills
6. End-to-end integration test of run_express.py on a real Python 2 project
