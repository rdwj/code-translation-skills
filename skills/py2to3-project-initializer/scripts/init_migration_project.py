#!/usr/bin/env python3
"""
Initialize a Python 2→3 migration project.

Creates the migration-analysis directory structure, generates TODO.md tracking
file, and produces the Phase 0 kickoff prompt for session continuity.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def count_python_files(project_root):
    """Count .py files in the project and categorize by size."""
    project_path = Path(project_root)
    if not project_path.exists():
        raise FileNotFoundError(f"Project root not found: {project_root}")

    py_files = list(project_path.rglob("*.py"))
    count = len(py_files)

    if count < 200:
        category = "small"
    elif count < 500:
        category = "medium"
    else:
        category = "large"

    return count, category


def get_project_name(project_root):
    """Extract project name from the root directory."""
    return Path(project_root).name


def get_chunking_note(file_count):
    """Generate chunking guidance based on codebase size."""
    if file_count < 200:
        return ""
    elif file_count < 500:
        return "This is a medium-sized codebase. Direct your output to migration-analysis/ files and present summaries in the conversation rather than full findings."
    else:
        return f"This is a large codebase ({file_count} Python files). Split Phase 0 analysis by top-level package. See migration-analysis/TODO.md for the chunking strategy."


def get_chunking_note_phase0(file_count):
    """Generate chunking note specifically for Phase 0 in TODO.md."""
    if file_count < 200:
        return ""
    elif file_count < 500:
        return "_Medium-sized codebase. Run analysis tools across the full repo._"
    else:
        return f"_Large codebase ({file_count} files). Consider splitting discovery by top-level package if repo structure permits._"


def create_directory_structure(project_root):
    """Create the migration-analysis directory structure."""
    base = Path(project_root) / "migration-analysis"
    base.mkdir(exist_ok=True)

    subdirs = [
        "handoff-prompts",
        "phase-0-discovery",
        "phase-1-foundation",
        "phase-2-mechanical",
        "phase-3-semantic",
        "phase-4-verification",
        "phase-5-cutover",
        "state",
    ]

    for subdir in subdirs:
        (base / subdir).mkdir(exist_ok=True)

    return base


def create_migration_state(state_dir):
    """Initialize the migration state JSON file."""
    state = {
        "initialized": datetime.now().isoformat(),
        "phase": 0,
        "modules": [],
        "gate_status": {},
    }
    state_file = state_dir / "migration-state.json"
    state_file.write_text(json.dumps(state, indent=2))
    return state_file


def load_todo_template():
    """Load TODO template from the references directory."""
    # The template is embedded below, but this function allows for external loading
    return TODO_TEMPLATE


def generate_todo_md(project_root, file_count, target_version):
    """Generate TODO.md from template."""
    project_name = get_project_name(project_root)
    size_category = "large" if file_count >= 500 else ("medium" if file_count >= 200 else "small")
    chunking_note = get_chunking_note_phase0(file_count)
    date = datetime.now().strftime("%Y-%m-%d")

    template = load_todo_template()
    todo_content = template.format(
        project_name=project_name,
        target_version=target_version,
        file_count=file_count,
        size_category=size_category,
        chunking_note_phase0=chunking_note,
        date=date,
    )

    return todo_content


def generate_kickoff_prompt(project_root, file_count, target_version):
    """Generate the Phase 0 kickoff prompt."""
    chunking_note = get_chunking_note(file_count)

    if chunking_note:
        chunking_section = f"\n{chunking_note}\n"
    else:
        chunking_section = "\n"

    prompt = f"""I need to migrate this Python 2 codebase to Python 3. You have a suite of py2to3 migration skills installed — 26 skills across 6 phases that handle everything from initial analysis through final cutover.

The migration tracking file is at migration-analysis/TODO.md — update it as you complete each step.

Before we start writing any code, let's run Phase 0 (Discovery) to understand what we're working with. Please:

1. Run the **py2to3-codebase-analyzer** to scan the repo, build a dependency graph, and produce a migration readiness report. Pay attention to the risk scores — I want to know which modules are highest-risk before we touch anything.

2. Run the **py2to3-data-format-analyzer** to map bytes/string boundaries, binary protocols, and encoding hotspots. This is critical — the data layer is where most Py2→3 migrations break.

3. Run the **py2to3-serialization-detector** to find pickle, marshal, shelve, and any custom serialization that will break across interpreter versions.

4. Run the **py2to3-c-extension-flagger** if there are any C extensions, Cython, or ctypes usage.

5. Run the **py2to3-lint-baseline-generator** to capture our current lint state.

Our target Python version is {target_version}. Save all outputs to migration-analysis/phase-0-discovery/.{chunking_section}
Once Phase 0 is complete, use the **py2to3-migration-state-tracker** to initialize the migration state from the Phase 0 outputs. Then let's review what the **py2to3-gate-checker** says about our readiness to proceed to Phase 1.

Don't move past Phase 0 without my approval.

When finished, write a handoff prompt for the next phase and save it to migration-analysis/handoff-prompts/phase1-handoff-prompt.md. The handoff prompt should:
- Summarize what was accomplished in Phase 0
- Reference all output files by path
- Call out risks, blockers, or decisions discovered
- List the specific skills and steps for Phase 1
- Include this same instruction to write a handoff prompt at the end of Phase 1

The goal is that someone starting a fresh session with only that prompt has full context to continue the migration."""

    return prompt


def main():
    parser = argparse.ArgumentParser(
        description="Initialize a Python 2→3 migration project"
    )
    parser.add_argument("project_root", help="Path to the Python 2 codebase")
    parser.add_argument(
        "--target-version",
        default="3.12",
        help="Target Python version (default: 3.12)",
    )

    args = parser.parse_args()

    try:
        # Count Python files and categorize
        file_count, size_category = count_python_files(args.project_root)
        print(f"Found {file_count} Python files ({size_category} codebase)")

        # Create directory structure
        base_dir = create_directory_structure(args.project_root)
        print(f"Created migration-analysis directory at: {base_dir}")

        # Initialize migration state
        state_file = create_migration_state(base_dir / "state")
        print(f"Initialized migration state: {state_file}")

        # Generate TODO.md
        todo_content = generate_todo_md(args.project_root, file_count, args.target_version)
        todo_file = base_dir / "TODO.md"
        todo_file.write_text(todo_content)
        print(f"Generated TODO.md: {todo_file}")

        # Generate Phase 0 kickoff prompt
        kickoff_prompt = generate_kickoff_prompt(
            args.project_root, file_count, args.target_version
        )
        kickoff_file = base_dir / "handoff-prompts" / "phase0-kickoff-prompt.md"
        kickoff_file.write_text(kickoff_prompt)
        print(f"Generated Phase 0 kickoff prompt: {kickoff_file}")

        # Summary
        print("\n" + "=" * 70)
        print("MIGRATION PROJECT INITIALIZED")
        print("=" * 70)
        print(f"Project: {get_project_name(args.project_root)}")
        print(f"Target Python: {args.target_version}")
        print(f"Codebase: {file_count} files ({size_category})")
        print(f"\nDirectory structure created:")
        print(f"  {base_dir}/")
        print(f"  ├── TODO.md (phase-by-phase tracking)")
        print(f"  ├── migration-state.json (current progress)")
        print(f"  ├── handoff-prompts/")
        print(f"  │   └── phase0-kickoff-prompt.md (ready to use)")
        print(f"  ├── phase-0-discovery/")
        print(f"  ├── phase-1-foundation/")
        print(f"  ├── phase-2-mechanical/")
        print(f"  ├── phase-3-semantic/")
        print(f"  ├── phase-4-verification/")
        print(f"  └── phase-5-cutover/")
        print(f"\nNext steps:")
        print(f"  1. Review migration-analysis/TODO.md")
        print(f"  2. Use the kickoff prompt to start Phase 0:")
        print(f"     → {kickoff_file}")
        print(f"  3. Update TODO.md as you complete each skill")
        print(f"  4. Write handoff prompts to continue across sessions")
        print("=" * 70)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


# Embedded TODO template
TODO_TEMPLATE = """# Python 2→3 Migration TODO

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
"""

if __name__ == "__main__":
    main()
