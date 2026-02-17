---
name: py2to3-future-imports-injector
description: >
  Safely inject `from __future__ import` statements into every Python file in a codebase
  as the first step of a Python 2→3 migration. Use this skill whenever you need to add
  future imports to prepare for migration, make Python 2 code behave more like Python 3,
  or flush out hidden compatibility issues. Also trigger when someone says "add future
  imports," "inject __future__," "prepare for migration," "add print_function import,"
  "add unicode_literals," or "make Py2 code forward-compatible." This is the first code
  change in the migration — the most important thing is that it doesn't break the existing
  Python 2 tests. Files that break after injection are the highest-risk modules.
---

# Future Imports Injector

The first real code change in the migration pipeline. Adding `from __future__ import`
statements to Python 2 files causes Python 2 to adopt Python 3 behaviors for specific
features. This is backward-compatible (the code still runs on Python 2) but surfaces
hidden issues early.

The four future imports and their effects:

| Import | Effect in Python 2 | Why It Matters |
|--------|-------------------|----------------|
| `print_function` | `print` becomes a function, not a statement | Least disruptive. Catch-all for print usage. |
| `division` | `/` does true division (returns float) | Medium risk. Integer math may break. |
| `absolute_import` | Imports are absolute by default | Low risk. Catches implicit relative imports. |
| `unicode_literals` | String literals become `unicode` instead of `str` | **Highest risk.** Surfaces every bytes/str confusion. |

## Why `unicode_literals` Is Special

`unicode_literals` changes every unqualified string literal from `str` (bytes) to
`unicode` (text). This is exactly what Python 3 does by default, so it's the most
valuable import for surfacing migration issues. But it's also the most dangerous in
Python 2 because:

- Code that passes string literals to C extensions may break
- Code that passes string literals to `socket.send()` or file I/O may break
- Code that uses string literals as dictionary keys where bytes are expected may break
- Code that concatenates string literals with bytes from external sources may break

For this reason, the skill offers a **cautious mode** where `unicode_literals` is applied
separately from the other three imports, with an extra testing step in between.

## Inputs

- **codebase_path**: Root directory of the codebase
- **output_dir**: Where to write reports
- **imports**: Which future imports to add (default: all four)
- **exclude_patterns**: Glob patterns for files to skip
- **batch_size**: How many files to modify per batch (default: 10)
- **cautious_mode**: If true, add `unicode_literals` as a separate batch with extra testing
- **dry_run**: If true, report what would change without modifying files
- **test_command**: Command to run tests after each batch (e.g. `python -m pytest`)

## Outputs

| File | Format | Purpose |
|------|--------|---------|
| `future-imports-report.json` | JSON | Which files modified, which broke, which skipped |
| `high-risk-modules.json` | JSON | Files that failed after future import injection |
| `future-imports-report.md` | Markdown | Human-readable summary |

## Workflow

### Step 1: Dry Run (Recommended First)

```bash
python3 scripts/inject_futures.py <codebase_path> \
    --output <output_dir> \
    --dry-run \
    [--exclude "**/vendor/**"]
```

This scans all files and reports what would change without touching anything.

### Step 2: Inject Safely

```bash
# Standard mode: all four imports at once, batch by batch
python3 scripts/inject_futures.py <codebase_path> \
    --output <output_dir> \
    --batch-size 10 \
    [--test-command "python -m pytest -x"] \
    [--exclude "**/vendor/**"]

# Cautious mode: unicode_literals applied separately
python3 scripts/inject_futures.py <codebase_path> \
    --output <output_dir> \
    --cautious \
    --batch-size 5 \
    --test-command "python -m pytest -x"
```

In cautious mode:
1. First pass: inject `print_function`, `division`, `absolute_import` into all files
2. Run tests — record any failures
3. Second pass: inject `unicode_literals` into files that passed step 2
4. Run tests — record new failures (these are the bytes/str boundary modules)

### Step 3: Generate the Report

```bash
python3 scripts/generate_futures_report.py <output_dir>/future-imports-report.json \
    --output <output_dir>/future-imports-report.md
```

## Injection Rules

The script follows these rules for placing the `from __future__` import:

1. **After the module docstring** (if present). The docstring must stay at the top.
2. **After encoding declarations** (`# -*- coding: ... -*-` or `# coding: ...`).
   These must be in the first two lines.
3. **After shebang lines** (`#!/usr/bin/env python`). Must be line 1.
4. **Before all other imports and code.**
5. **Merge with existing future imports.** If the file already has
   `from __future__ import print_function`, add the missing ones to the same line.
6. **Skip empty files and `__init__.py` files that are empty** (no code to affect).
7. **Skip files that already have all requested future imports.**

## File Modification Safety

The script takes care to be safe:

- **Atomic writes**: Changes are written to a temp file first, then renamed
- **Backup**: Original files can be backed up with `--backup` flag
- **Rollback on test failure**: If `--rollback-on-failure` is set and tests fail,
  the batch is reverted automatically
- **Git-friendly**: Changes are designed to produce clean, reviewable diffs

## Report Structure

```json
{
  "timestamp": "ISO-8601",
  "codebase_path": "/path/to/codebase",
  "imports_injected": ["print_function", "division", "absolute_import", "unicode_literals"],
  "mode": "standard|cautious",
  "total_files": 150,
  "modified": 142,
  "skipped": 8,
  "already_had_imports": 5,
  "empty_files": 3,
  "failed_after_injection": 7,
  "files": [
    {
      "path": "relative/path.py",
      "status": "modified|skipped|failed|already_had",
      "imports_added": ["print_function", "division"],
      "imports_existing": ["absolute_import"],
      "failure_output": "traceback text if failed",
      "batch_number": 1
    }
  ],
  "high_risk_modules": ["list of paths that broke after injection"],
  "test_results": {
    "batches_run": 15,
    "batches_passed": 14,
    "batches_failed": 1,
    "total_test_time_seconds": 245
  }
}
```

## Integration with Other Skills

This skill's outputs feed into:
- **Skill X.1 (Migration State Tracker)**: Update module phase history
- **Skill X.3 (Gate Checker)**: `future-imports-report.json` is evidence for Phase 1→2 gate
- **Skill 1.2 (Test Scaffold Generator)**: `high-risk-modules.json` identifies modules that
  need extra characterization tests (especially for bytes/str boundaries)

After running, update the migration state:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py \
    <state_file> record-output \
    --module <module_path> \
    --output-path <output_dir>/future-imports-report.json
```

## Important Notes

**`unicode_literals` failures are features, not bugs.** When a file breaks after adding
`unicode_literals`, it's telling you exactly where the bytes/str boundary problems are.
These are the same issues that will surface in Python 3. The sooner they're found, the
better. The `high-risk-modules.json` output is one of the most valuable artifacts this
skill produces.

**Test after every batch.** Don't inject into all files at once and then test. Batch
processing with testing between batches identifies exactly which files cause failures.
This makes debugging much easier.

**Don't force unicode_literals everywhere.** Some files legitimately work with byte strings
(SCADA protocol handlers, binary file parsers). For those, `unicode_literals` may need
to be skipped or the file may need `b''` prefixes added to byte string literals. The
cautious mode handles this by treating `unicode_literals` separately.

## Model Tier

**Haiku.** Injecting `__future__` imports is mechanical AST manipulation — find the insertion point, add the import line. No reasoning about code semantics. Always use Haiku.

## References

- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
