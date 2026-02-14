# Getting Started: Python 2→3 Migration

## Quick Start

1. Install the skills:
   ```bash
   ./scripts/install-skills.sh /path/to/your/project
   ```

2. Start a Claude Code session in your Python 2 repository.

3. Run the **py2to3-project-initializer** first:
   ```
   Run the py2to3-project-initializer skill to set up the migration project. Target Python version is 3.12.
   ```
   This creates the `migration-analysis/` directory structure, a TODO.md tracking file, and a Phase 0 kickoff prompt.

4. Use the generated kickoff prompt at `migration-analysis/handoff-prompts/phase0-kickoff-prompt.md` to start Phase 0 — either in the current session or by pasting it into a new session.

---

## The Handoff Prompt Pattern

Migrations span multiple sessions. No agent context window can hold an entire multi-phase migration. The solution is **handoff prompts** — self-contained documents that pass full context between sessions.

The pattern:

1. **Start a session** with a handoff prompt (or the initial kickoff prompt)
2. **Do the work** — run skills, save outputs, update the TODO.md and migration state
3. **Write the next handoff prompt** — summarize what was done, reference output files, list next steps
4. **Start a new session** with the handoff prompt from step 3

Each handoff prompt contains everything the next session needs: what's been completed, where the outputs are, what risks were found, and exactly what to do next. No conversation history required.

The project initializer generates the first prompt in this chain. Every subsequent session continues it by writing the next handoff prompt before finishing.

See `skills/py2to3-project-initializer/references/HANDOFF-PROMPT-GUIDE.md` for detailed guidance on writing effective handoff prompts.

---

## Manual Start (without the project initializer)

If you prefer to skip the initializer and jump straight in, use this prompt:

```
I need to migrate this Python 2 codebase to Python 3. You have a suite of py2to3 migration skills installed — 27 skills across 6 phases that handle everything from initial analysis through final cutover.

Before we start writing any code, let's run Phase 0 (Discovery) to understand what we're working with. Please:

1. Run the **py2to3-codebase-analyzer** to scan the repo, build a dependency graph, and produce a migration readiness report. Pay attention to the risk scores — I want to know which modules are highest-risk before we touch anything.

2. Run the **py2to3-data-format-analyzer** to map bytes/string boundaries, binary protocols, and encoding hotspots. This is critical — the data layer is where most Py2→3 migrations break.

3. Run the **py2to3-serialization-detector** to find pickle, marshal, shelve, and any custom serialization that will break across interpreter versions.

4. Run the **py2to3-c-extension-flagger** if there are any C extensions, Cython, or ctypes usage.

5. Run the **py2to3-lint-baseline-generator** to capture our current lint state.

Our target Python version is 3.12. After each skill, save the outputs — we'll feed them into later phases.

Once Phase 0 is complete, use the **py2to3-migration-state-tracker** to initialize the migration state from the Phase 0 outputs. Then let's review what the **py2to3-gate-checker** says about our readiness to proceed to Phase 1.

Don't move past Phase 0 without my approval.

When finished, write a handoff prompt for Phase 1 that I can use to start the next session. It should summarize what was accomplished, reference the key output files, call out risks or blockers discovered, and list the specific skills and steps for the next phase. The goal is that someone starting a fresh session with only that prompt has full context to continue the migration.
```

---

## Codebase Size Considerations

The migration workflow stays the same regardless of codebase size — what changes is how much work fits in a single session and where to create handoff points.

| Size | File Count | Guidance |
|------|-----------|---------|
| Small | < 100 files | One session per phase is usually fine |
| Medium | 100–500 files | One session per phase with summary-mode output |
| Large | 500+ files | Multiple sessions per phase, split analysis by package |

**For codebases over 200 files**, add this to the kickoff prompt:
> Direct your output to files on disk and present summaries in the conversation rather than full findings. Reference output files by path.

**For codebases over 500 files**, add this:
> This is a large codebase. Split Phase 0 analysis by top-level package directory. See the Scale Playbook (`docs/SCALE-PLAYBOOK.md`) for the chunking strategy.

The project initializer handles this automatically — it counts your Python files and adjusts the generated kickoff prompt accordingly.

See [docs/SCALE-PLAYBOOK.md](docs/SCALE-PLAYBOOK.md) for the full guide on running migrations at different scales.

---

## What happens after Phase 0

After Phase 0, you'll have a clear picture of the codebase: risk scores per module, a dependency graph with migration order, a map of every bytes/string boundary and encoding hotspot, and a lint baseline. The gate checker will tell you whether the prerequisites for Phase 1 are met.

From there, the migration proceeds phase by phase:

- **Phase 1 (Foundation)**: Inject `__future__` imports, generate characterization tests, set up dual-interpreter CI, create custom lint rules
- **Phase 2 (Mechanical)**: Plan conversion units, run automated syntax transforms, update build systems
- **Phase 3 (Semantic)**: Fix bytes/string boundaries, replace removed libraries, resolve dynamic patterns, add type annotations
- **Phase 4 (Verification)**: Generate behavioral diffs, benchmark performance, stress-test encodings, check completeness
- **Phase 5 (Cutover)**: Plan canary deployment, remove compatibility shims, detect dead code

Each phase transition requires passing gate criteria. The **py2to3-gate-checker** enforces these — you can't skip ahead. The **py2to3-migration-state-tracker** maintains per-module state throughout, and the **py2to3-rollback-plan-generator** produces rollback runbooks for each phase in case you need to unwind.

## Adjusting the target version

Change `3.12` in the prompt to your desired target. The skills adjust their output for version-specific breaking changes:

- **3.9**: Minimum recommended. Generic type syntax available (`list[str]` instead of `List[str]`)
- **3.11**: Significant performance improvements, useful for benchmarking phase
- **3.12**: `distutils` removed entirely, many deprecated modules gone — the biggest jump in breaking changes
- **3.13**: Free-threaded mode available, more module removals finalized
