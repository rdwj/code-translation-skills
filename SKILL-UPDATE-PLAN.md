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

## Next Steps (Implementation)

All SKILL.md files are now updated/created. The next phase is implementing the actual scripts:

1. **Phase 1 scripts** (universal-code-graph): `language_detect.py`, `ts_parser.py`, `universal_extractor.py`, `analyze_universal.py`, Python `.scm` query files
2. **Phase 2 scripts**: `py2_patterns_ts.py` — tree-sitter queries for all 20+ Python 2 patterns
3. **Phase 3 scripts**: `depends_runner.py` — multilang-depends subprocess integration
4. **Phase 4**: Query files for Java, C, C++, Rust, Ruby, Go (3 files × 7 languages = 21 `.scm` files)
5. **Phase 5**: `graph_builder.py` enhancements, call graph, NetworkX export
6. **Phase 6 scripts**: `behavioral_analyzer.py`, `work_decomposer.py`, `extract_contracts.py`, `haiku_fixer.py`, `verify_translation.py`, `advise_modernization.py`
7. **Phase 7**: `generate_dashboard.py` + `dashboard/index.html` template
8. **Phase 8**: Update existing skill scripts with tree-sitter fallback paths
9. **Phase 9**: Generalize naming, create target-language template skills
