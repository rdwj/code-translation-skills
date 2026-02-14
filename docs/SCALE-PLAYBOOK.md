# Scale Playbook: Running Migrations at Different Codebase Sizes

This guide adjusts the migration workflow based on codebase size. The six-phase structure stays the same — what changes is how much work the agent takes on per invocation and where to create handoff points between sessions.

## Sizing Your Codebase

Count Python files (not lines — file count is what drives context pressure):

```bash
find . -name "*.py" -not -path "./.venv/*" -not -path "./vendor/*" | wc -l
```

| Size | File Count | Session Strategy |
|------|-----------|-----------------|
| Small | < 100 files | Single session per phase is usually fine |
| Medium | 100–500 files | One session per phase, with checkpoints within phases |
| Large | 500–2000 files | Multiple sessions per phase, chunk by package |
| Very Large | 2000+ files | Multiple sessions per phase, chunk by package, consider parallel workstreams |

## Small Codebases (< 100 files)

Run each phase end-to-end in a single session. The full output from each skill will fit comfortably in context.

**Phase 0**: Run all 5 discovery skills sequentially. Review the full output.
**Phases 1–5**: Follow the standard workflow. One session per phase is typically sufficient.

No special chunking needed. The main risk is not context exhaustion but rather the agent trying to do too many phases in one session. Stick to one phase per session.

## Medium Codebases (100–500 files)

Each phase fits in a single session, but the agent needs to manage what it puts into the conversation.

**Phase 0 adjustments**:
- Codebase Analyzer: Run on full codebase. Direct the agent to summarize (top-20 riskiest modules, aggregate statistics) rather than listing every finding.
- Data Format Analyzer: Run on full codebase. Focus conversation on critical and high-risk findings only.
- Lint Baseline: Save full output to disk. Present category-level summary only.

**Phase 2 adjustments**:
- Process one conversion unit per session section. After each unit: save outputs, update state tracker, summarize status.
- If the Conversion Unit Planner produces 10+ units, plan for 2–3 sessions to complete Phase 2.

**Phase 3 adjustments**:
- Bytes/String Fixer: Process one conversion unit at a time. This is the most context-intensive skill.
- Budget 1–2 sessions per high-risk conversion unit.

**Phase 4 adjustments**:
- Run verification skills per conversion unit, not per codebase.
- Completeness Checker is the exception — it should run on the full codebase but present summary output.

**Handoff cadence**: Write a handoff prompt after completing each conversion unit in Phases 2–3, and after each verification pass in Phase 4.

## Large Codebases (500–2000 files)

Multiple sessions per phase. The primary chunking boundary is the top-level package.

**Phase 0 adjustments**:
- Split all Phase 0 skills by top-level package directory
- Run Codebase Analyzer per package, then merge dependency graphs
- Run Data Format Analyzer per package (results are additive)
- Run Lint Baseline per package (results are additive)
- Serialization Detector and C Extension Flagger can run on the full codebase (their output is bounded by the number of serialization/extension points, not file count)

**Phase 1 adjustments**:
- Future Imports Injector: Use `--batch-size 5` and process in batches with testing between batches
- Test Scaffold Generator: Generate tests per package, prioritizing by risk score from Phase 0

**Phase 2 adjustments**:
- Expect 15–30 conversion units. Plan for 5–10 sessions.
- Process 2–3 conversion units per session maximum.
- Between units: update state, run lint, confirm no regressions.

**Phase 3 adjustments**:
- Bytes/String Fixer: 5–10 files per invocation for heavy I/O modules, 10–20 for text-mode modules.
- Budget one session per high-risk conversion unit, 2–3 low-risk units per session.
- Human review checkpoint after I/O boundary decisions.

**Phase 4 adjustments**:
- Behavioral Diff Generator: Per conversion unit, split by test category if 200+ tests.
- Encoding Stress Tester: Two-pass strategy — critical paths first, remaining paths second.
- Completeness Checker: Run per package, present category-level summary.

**Phase 5 adjustments**:
- Compatibility Shim Remover: `--batch-size 5`, one package at a time.
- Dead Code Detector: Full codebase scan is necessary for accurate call graph, but present findings by confidence tier.

**Handoff cadence**: Write a handoff prompt after every 2–3 conversion units, and between each Phase 0 package analysis.

## Very Large Codebases (2000+ files)

Everything from "Large" applies, plus:

**Parallel workstreams**: After Phase 0 produces the dependency graph, identify packages that have no cross-package data dependencies. These can be migrated in parallel by different team members (or separate agent sessions), each following the full Phase 1–5 pipeline independently. Cross-package integration testing happens after individual packages complete Phase 4.

**Dedicated sessions per skill**: For Phase 0, each discovery skill may need its own session per package. Don't try to run all 5 Phase 0 skills in one session if the package has 200+ files.

**State tracker as coordination point**: The Migration State Tracker becomes critical for coordinating parallel workstreams. Each session should update it before writing the handoff prompt, and each new session should read it before starting work.

**Handoff cadence**: Write a handoff prompt after every conversion unit. The handoff prompt is the primary coordination mechanism.

## General Principles

**The agent should never dump raw JSON into the conversation.** All structured output goes to disk. The conversation gets summaries, risk highlights, and decision points.

**One phase per session, maximum.** Even on small codebases, don't let the agent run through multiple phases in a single session. The gate check between phases is a natural handoff point.

**Handoff prompts are the primary context management tool.** When a session is getting long, write a handoff prompt and start fresh. The handoff prompt should contain everything the next session needs to continue — no reliance on conversation history.

**Update the state tracker before every handoff.** The state tracker is the source of truth. If the state tracker and the handoff prompt disagree, the state tracker wins.

**Err on the side of smaller chunks.** A session that processes 3 conversion units cleanly is better than one that processes 8 and runs out of context on the 7th. The cost of starting a new session is low; the cost of losing context mid-task is high.
