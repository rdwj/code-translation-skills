---
name: py2to3-project-initializer
description: >
  Initialize a Python 2→3 migration project. Performs a quick sizing scan to classify
  the project as small/medium/large, then creates appropriately-scaled scaffolding.
  Small projects get a streamlined single-session workflow; large projects get the full
  multi-phase, multi-session pipeline. This is the first skill to run.
---

# Project Initializer

This skill bootstraps a Python 2→3 migration project. Run it once at the very beginning, before any analysis or conversion work.

**Critical design principle: right-size the process to the project.** A 5-file pacman game should not go through the same 6-phase, 30-skill pipeline as a 500-file industrial platform. The initializer's first job is to figure out which workflow fits.

## Step 0: Create the Workspace

**Never modify the source repository directly.** Before any analysis or conversion, create a peer working directory. The source repo stays pristine as a reference; all migration work happens in the workspace.

```
parent-dir/
├── my-project/              ← original source (READ-ONLY during migration)
├── my-project-py3/          ← working copy (all edits happen here)
│   ├── <full source copy>
│   └── migration-analysis/  ← scaffolding, reports, state
```

**Setup steps:**
1. Copy the source tree to `<project-name>-py3/` as a peer directory
2. If the source is a git repo, create a new branch in the workspace: `git checkout -b py3-migration`
3. Run all analysis and conversion against the workspace copy
4. The original source serves as a diff baseline and rollback target

```bash
# Create workspace as peer directory
cp -r /path/to/my-project /path/to/my-project-py3
cd /path/to/my-project-py3
git checkout -b py3-migration  # if git repo
```

**Why peer directory instead of in-place?**
- Original source is always available for `diff` comparison
- No risk of corrupting the production codebase
- Git history stays clean (migration is one branch, not mixed into main)
- Easy rollback: just delete the workspace and start over
- Multiple migration attempts can coexist

**For Express workflow on tiny projects:** The workspace copy is still recommended but optional. If the project is < 10 files with no tests and you're confident, you can work in-place on a git branch.

## Step 1: Quick Size Scan

Before creating any scaffolding, run a fast sizing scan on the workspace. This takes seconds, not minutes:

```bash
python scripts/quick_size_scan.py /path/to/my-project-py3
```

The scan counts Python files, total lines of code, and does a fast pattern grep for high-risk indicators (binary I/O, C extensions, pickle/marshal, EBCDIC, custom codecs). It produces a sizing verdict:

| Category | Files | LOC | Characteristics | Workflow |
|----------|-------|-----|-----------------|----------|
| **Small** | ≤ 20 | ≤ 2,000 | Few or no semantic issues, no data layer complexity | **Express** — single session, minimal scaffolding |
| **Medium** | 21–100 | 2,001–15,000 | Some semantic issues, limited data layer | **Standard** — 2–4 sessions, selective skill use |
| **Large** | 101–500 | 15,001–100,000 | Significant semantic issues, data layer involvement | **Full** — multi-session, all phases, all skills |
| **Very Large** | 500+ | 100,000+ | Complex data layer, C extensions, polyglot | **Full+Parallel** — sub-agent delegation, package-level splits |

**Override:** The scan also checks for complexity escalators that bump a project up one tier regardless of size:

- C extensions or CFFI/ctypes usage → bump up
- Pickle/marshal with cross-version data files → bump up
- EBCDIC, Modbus, or custom binary protocols → bump up
- Zero test files → bump up (no safety net)

The sizing verdict drives everything that follows.

## Express Workflow (Small Projects)

For small projects (≤ 20 files, ≤ 2,000 LOC, no complexity escalators):

**Do not create the full migration-analysis directory structure.** Instead:

1. Run a combined analysis-and-convert pass in a single session
2. Use the codebase-analyzer in summary mode (no separate JSON outputs needed)
3. Apply mechanical fixes directly (future imports, print statements, dict methods, etc.)
4. Run the test suite (if it exists) after conversion
5. Do a quick completeness scan for remaining Py2 artifacts
6. Done. No handoff prompts, no state tracker, no gate checks.

The Express workflow creates a minimal output:

```
migration-analysis/
├── migration-summary.md      # What was found and fixed
└── remaining-issues.md       # Anything that needs manual attention
```

**Model tier:** The entire Express workflow runs on Haiku. Small projects with simple patterns don't need Sonnet-level reasoning.

**Skills used (Express):**

| Skill | How it's used | Model |
|-------|--------------|-------|
| py2to3-codebase-analyzer | Summary mode — inline findings, no separate output files | Haiku |
| py2to3-automated-converter | Direct conversion, all files at once | Haiku |
| py2to3-library-replacement | If stdlib renames detected | Haiku |
| py2to3-future-imports-injector | All files in one pass | Haiku |

That's it. Four skills maximum. Most small projects need only the first two.

**What gets skipped (Express):**
- No data-format-analyzer, serialization-detector, c-extension-flagger (scan found no complexity escalators)
- No conversion-unit-planner (no need to group files — do them all)
- No behavioral-diff-generator, encoding-stress-tester, performance-benchmarker (overkill for small projects)
- No migration-state-tracker, gate-checker (no phases to gate)
- No handoff prompts (single session)
- No build-system-updater (review manually — it's one file)
- No canary-deployment-planner, rollback-plan-generator (not needed at this scale)

## Standard Workflow (Medium Projects)

For medium projects (21–100 files, or small projects with complexity escalators):

Create a streamlined directory structure:

```
migration-analysis/
├── TODO.md                   # Condensed — 3 phases, not 6
├── handoff-prompts/
├── phase-1-analyze-convert/  # Combines Phase 0+1+2
├── phase-2-semantic/         # Phase 3 equivalent
├── phase-3-verify-cutover/   # Combines Phase 4+5
└── state/
    └── migration-state.json
```

**Key differences from Full workflow:**

- **3 phases instead of 6.** Discovery, foundation, and mechanical conversion merge into Phase 1. Verification and cutover merge into Phase 3.
- **Selective skill use.** Only run specialized skills when the sizing scan flagged relevant complexity (e.g., skip bytes-string-fixer if no binary I/O detected, skip c-extension-flagger if no .so/.pyd files).
- **1–2 handoff prompts maximum.** Medium projects typically need 2–4 sessions.
- **Gate checks are simplified.** Use a lightweight pass/fail on test results rather than the full multi-criterion gate-checker.

**Model tier:** Haiku for mechanical work (~70%), Sonnet for semantic fixes if needed (~30%). No Opus.

**Skills used (Standard):**

| Phase | Skills | Model |
|-------|--------|-------|
| 1: Analyze+Convert | codebase-analyzer, future-imports-injector, automated-converter, library-replacement | Haiku |
| 1: Analyze+Convert | conversion-unit-planner (if > 50 files) | Haiku |
| 2: Semantic | bytes-string-fixer (if flagged), dynamic-pattern-resolver (if flagged) | Sonnet |
| 2: Semantic | type-annotation-adder (optional, user request only) | Sonnet |
| 3: Verify+Cutover | behavioral-diff-generator (run test suite, compare), completeness-checker | Haiku |
| 3: Verify+Cutover | compatibility-shim-remover, dead-code-detector | Haiku |

## Full Workflow (Large Projects)

For large projects (101+ files, or medium projects with complexity escalators):

This is the original 6-phase workflow. Create the full directory structure:

```
migration-analysis/
├── TODO.md
├── handoff-prompts/
├── phase-0-discovery/
├── phase-1-foundation/
├── phase-2-mechanical/
├── phase-3-semantic/
├── phase-4-verification/
├── phase-5-cutover/
└── state/
    └── migration-state.json
```

All skills are available. Use the TODO template from `references/TODO-TEMPLATE.md`.

**Model tier routing:**

| Work type | Model | % of token spend |
|-----------|-------|-----------------|
| Pattern scanning, file inventory, lint, config | Haiku | ~50% |
| Mechanical conversion, imports, lib replacement | Haiku | ~20% |
| Bytes/string, dynamic patterns, type inference | Sonnet | ~25% |
| Architectural decisions, C extensions, novel patterns | Opus | ~5% |

**For Very Large projects** (500+ files): Split by top-level package and use sub-agent delegation per the SUB-AGENT-GUIDE. Run analysis in parallel across packages, merge results.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| Source project root | Yes | Path to the original Python 2 codebase (used as read-only reference) |
| `--workspace` | No | Path for the working copy (default: `<project-name>-py3` as peer directory) |
| `--in-place` | No | Skip workspace creation, work directly on source (not recommended) |
| `--target-version` | No | Default: 3.12 |
| `--workflow` | No | Force a specific workflow (express/standard/full/auto) regardless of sizing |

## Outputs

| Output | Location | Description |
|--------|----------|-------------|
| **Workspace directory** | `<project-name>-py3/` (peer to source) | Full copy of source tree, all edits happen here |
| Sizing report | stdout (or `migration-analysis/sizing-report.json` for standard/full) | Project size, complexity flags, recommended workflow |
| Directory structure | `<workspace>/migration-analysis/` | Scaled to workflow tier |
| TODO.md | `<workspace>/migration-analysis/TODO.md` | Scaled to workflow tier (not created for Express) |
| Kickoff prompt | `<workspace>/migration-analysis/handoff-prompts/phase0-kickoff-prompt.md` | Not created for Express |
| Migration state | `<workspace>/migration-analysis/state/migration-state.json` | Includes `source_root` and `workspace` paths |

## The Handoff Prompt Pattern (Standard and Full only)

Every session in a multi-session migration should end with a handoff prompt. See `references/HANDOFF-PROMPT-GUIDE.md` for the complete guide.

The pattern: **do work → update TODO → update migration state → write handoff prompt → start new session with that prompt.**

Each handoff prompt must be self-contained: what's done, what's next, where the artifacts are, what risks exist. A new session with zero history should be able to pick up from the handoff prompt alone.

## Model Tier

This skill itself runs on **Haiku**. It creates directories and generates text from templates — no reasoning required.

When generating the TODO.md and kickoff prompt, embed model-tier hints for each skill invocation so the executing agent knows which model to use for sub-agent delegation. See `references/MODEL-TIER-GUIDE.md` for the complete routing table.

## Scripts Reference

### `scripts/quick_size_scan.py`
Fast sizing scan. Counts files, LOC, greps for complexity escalators. Returns sizing category and recommended workflow. Runs in < 5 seconds on any project.

```bash
python3 scripts/quick_size_scan.py /path/to/project [--output sizing-report.json]
```

### `scripts/init_migration_project.py`
Creates the workspace, directory structure, TODO.md, and kickoff prompt. Handles workspace copy and git branch setup.

```bash
# Typical usage — creates peer workspace automatically
python3 scripts/init_migration_project.py /path/to/source-project \
    --target-version 3.12

# Custom workspace location
python3 scripts/init_migration_project.py /path/to/source-project \
    --workspace /path/to/my-workspace

# In-place (not recommended — skips workspace copy)
python3 scripts/init_migration_project.py /path/to/project --in-place
```

`--workflow auto` (default) uses the sizing scan result. Override with explicit workflow if you know better.

## References

- `references/TODO-TEMPLATE.md` — Template for the Full workflow TODO.md
- `references/TODO-TEMPLATE-STANDARD.md` — Template for the Standard workflow TODO.md
- `references/HANDOFF-PROMPT-GUIDE.md` — Detailed guide for writing effective handoff prompts
- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents
- `references/MODEL-TIER-GUIDE.md` — Which model tier to use for each skill and task type
