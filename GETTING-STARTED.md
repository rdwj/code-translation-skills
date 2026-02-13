# Getting Started: Python 2→3 Migration

After installing the skills (`./scripts/install-skills.sh /path/to/your/project`), start a Claude Code session in your Python 2 repository and use the prompt below.

---

## Suggested Prompt

```
I need to migrate this Python 2 codebase to Python 3. You have a suite of py2to3 migration skills installed — 26 skills across 6 phases that handle everything from initial analysis through final cutover.

Before we start writing any code, let's run Phase 0 (Discovery) to understand what we're working with. Please:

1. Run the **py2to3-codebase-analyzer** to scan the repo, build a dependency graph, and produce a migration readiness report. Pay attention to the risk scores — I want to know which modules are highest-risk before we touch anything.

2. Run the **py2to3-data-format-analyzer** to map bytes/string boundaries, binary protocols, and encoding hotspots. This is critical — the data layer is where most Py2→3 migrations break.

3. Run the **py2to3-serialization-detector** to find pickle, marshal, shelve, and any custom serialization that will break across interpreter versions.

4. Run the **py2to3-c-extension-flagger** if there are any C extensions, Cython, or ctypes usage.

5. Run the **py2to3-lint-baseline-generator** to capture our current lint state.

Our target Python version is 3.12. After each skill, save the outputs — we'll feed them into later phases.

Once Phase 0 is complete, use the **py2to3-migration-state-tracker** to initialize the migration state from the Phase 0 outputs. Then let's review what the **py2to3-gate-checker** says about our readiness to proceed to Phase 1.

Don't move past Phase 0 without my approval.
```

---

## What happens next

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
