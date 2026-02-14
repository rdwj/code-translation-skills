---
name: py2to3-project-initializer
description: >
  Initialize a Python 2→3 migration project. Creates the migration-analysis directory structure,
  generates a TODO.md tracking file, and produces the Phase 0 kickoff prompt. This is the first
  skill to run — it sets up the scaffolding that all other skills depend on.
---

# Project Initializer

This skill bootstraps a Python 2→3 migration project. Run it once at the very beginning, before any analysis or conversion work.

It does three things:

1. **Creates the migration directory structure** — a `migration-analysis/` directory with subdirectories for each phase's outputs, plus a `handoff-prompts/` directory for session continuity.

2. **Generates a TODO.md** — a phase-by-phase tracking document that serves as the migration's table of contents. It lists every skill invocation needed, tracks completion status, and links to output files. The agent updates this file as work progresses.

3. **Produces a Phase 0 kickoff prompt** — a ready-to-use prompt that starts the actual migration work in the current or next session.

## Why This Skill Exists

Large-scale migrations span multiple sessions. An agent's context window is finite, and a migration that touches hundreds of files across 6 phases will exceed it. The solution is to work in sessions, with each session focused on a specific chunk of work, and to pass context between sessions via **handoff prompts**.

A handoff prompt is a self-contained document that gives the next session everything it needs to continue:
- What has been completed (with references to output files on disk)
- What the current migration state is
- What specific work the next session should do
- Which skills to use and in what order
- What risks or blockers were discovered

The pattern is: **run a phase (or part of a phase) → update the TODO → update the migration state → write a handoff prompt → start a new session with that prompt.**

This skill sets up that entire workflow from the beginning.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| Project root | Yes | Path to the Python 2 codebase |
| Target Python version | No | Default: 3.12. Used in the kickoff prompt |
| Codebase size estimate | No | If known, adjusts the chunking guidance in the TODO |

## Outputs

| Output | Location | Description |
|--------|----------|-------------|
| Directory structure | `migration-analysis/` | Phase output directories, handoff prompt directory |
| TODO.md | `migration-analysis/TODO.md` | Phase-by-phase tracking with all skill invocations |
| Kickoff prompt | `migration-analysis/handoff-prompts/phase0-kickoff-prompt.md` | Ready-to-use prompt for Phase 0 |

## Scope and Chunking

This skill runs once and produces a small, bounded output. No chunking needed.

## Workflow

### Step 1: Create the Directory Structure

```bash
python scripts/init_migration_project.py /path/to/project --target-version 3.12
```

This creates:

```
migration-analysis/
├── TODO.md
├── handoff-prompts/
│   └── phase0-kickoff-prompt.md
├── phase-0-discovery/
├── phase-1-foundation/
├── phase-2-mechanical/
├── phase-3-semantic/
├── phase-4-verification/
├── phase-5-cutover/
└── state/
    └── migration-state.json (initialized, empty)
```

### Step 2: Review the TODO.md

The generated TODO.md is a living document. It lists every skill invocation across all 6 phases, with checkboxes for tracking. The agent should update it after each skill completes.

The TODO.md is organized by phase and includes:
- Estimated session count based on codebase size
- Which skills to run in each phase
- Expected outputs from each skill
- Gate criteria for phase transitions
- Handoff prompt reminders at natural break points

### Step 3: Review and Use the Kickoff Prompt

The Phase 0 kickoff prompt is saved to `migration-analysis/handoff-prompts/phase0-kickoff-prompt.md`. It includes:
- Context about the migration (target version, codebase size)
- Specific skills to run for Phase 0
- Instructions to save outputs and update state
- The critical instruction: **write a handoff prompt for the next session when done**

Use this prompt to start Phase 0 in the current session or paste it into a new session.

### Step 4: The Handoff Prompt Pattern

Every session should end with the agent writing a handoff prompt. The pattern the agent should follow:

1. **Summarize what was accomplished** — which skills ran, what they found, key metrics
2. **Reference output files by path** — the next session reads these from disk, not from conversation history
3. **Call out risks and blockers** — anything that needs human decision or that downstream phases need to know about
4. **List the specific next steps** — which skills to run, in what order, with any special parameters
5. **Include the handoff instruction** — tell the next agent to write a handoff prompt too, continuing the chain

Save each handoff prompt to `migration-analysis/handoff-prompts/phaseN-handoff-prompt.md`.

The chain of handoff prompts becomes the migration's narrative history — each one is a snapshot of the project's state at a transition point.

## References

- `references/TODO-TEMPLATE.md` — Template for the generated TODO.md
- `references/HANDOFF-PROMPT-GUIDE.md` — Detailed guide for writing effective handoff prompts
- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
