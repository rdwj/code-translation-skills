---
name: py2to3-lint-baseline-generator
description: >
  Run discovery linters against a Python 2 codebase as part of Python 2→3 migration and produce a baseline report that
  becomes the reference point for measuring migration progress. Use this skill whenever you
  need to establish a lint baseline before migration begins, measure how many Py2-isms exist
  and where, generate per-module lint scores, produce a prioritized fix list, or create
  initial linter configuration files. Also trigger when someone says "run the linters,"
  "what's the lint score," "generate a baseline," "show me the lint findings," "how clean
  is this codebase," or "set up linting for migration." This is a quick win that provides
  immediate visibility into migration scope and progress.
---

# Lint Baseline Generator

Before changing any code, establish a baseline. This skill runs discovery linters against
the codebase and produces a comprehensive report of all Python 2 compatibility findings.
This baseline serves three purposes:

1. **Scope visibility** — stakeholders can see the full extent of Py2-isms in the codebase
2. **Progress measurement** — as migration proceeds, lint scores improve against the baseline
3. **Prioritization** — the findings are categorized and ranked so the team works on the
   highest-impact items first

## Linters Used

The skill runs three complementary linters, each catching different patterns:

### pylint --py3k
Purpose-built Python 2→3 compatibility checker. Catches:
- `print` statements, `exec` statements, backtick repr
- `has_key()`, `<>` operator, old `except` syntax
- Relative imports, renamed stdlib modules
- `unicode()`, `long`, `buffer()`, `xrange()`
- `__cmp__`, `__nonzero__`, `__getslice__`, `__coerce__`
- String formatting with `%` on non-string types

### pyupgrade --py3-plus (dry run)
Shows what automated rewrites are possible. Catches:
- Type comment annotations → inline annotations
- `typing.Dict`/`typing.List` → `dict`/`list` (for target >= 3.9)
- Old-style classes, `super()` calls
- `six` usage that can be simplified
- `encode('utf-8')` → `encode()` (default encoding)
- Native string constructors

### flake8 with flake8-2020
Catches forward-incompatibility patterns:
- `sys.version[0]` comparisons (unreliable in Py3.10+)
- `sys.version_info` comparisons with wrong tuple length
- `platform.python_version()` string comparisons
- `six.PY2`/`six.PY3` usage patterns

## Inputs

- **codebase_path**: Root directory of the Python 2 codebase
- **output_dir**: Where to write analysis results (defaults to `<codebase_path>/migration-analysis/`)
- **target_version** (optional): Target Python 3 version for pyupgrade flags. Defaults to 3.9.
- **exclude_patterns** (optional): Glob patterns for files/directories to skip

## Outputs

All outputs go to `<output_dir>/`:

| File | Format | Purpose |
|------|--------|---------|
| `lint-baseline.json` | JSON | All findings categorized, with per-module scores |
| `lint-baseline.md` | Markdown | Human-readable summary with prioritized fix list |
| `lint-config/pylintrc` | INI | Initial pylint configuration |
| `lint-config/setup.cfg` | INI | Initial flake8 configuration |
| `lint-config/pyproject.toml` | TOML | pyupgrade configuration |

## Workflow

### Step 1: Generate the Baseline

```bash
python3 scripts/generate_baseline.py <codebase_path> \
    --output <output_dir> \
    --target-version 3.12 \
    [--exclude "**/vendor/**" "**/test/**"]
```

This script:
1. Discovers all `.py` files in the codebase
2. Runs `pylint --py3k` on each file (or in batch)
3. Runs `pyupgrade --py3X-plus` in dry-run mode
4. Runs `flake8` with the `flake8-2020` plugin
5. Collects and deduplicates all findings
6. Categorizes by type, severity, and module
7. Computes per-module lint scores
8. Generates the prioritized fix list
9. Writes `lint-baseline.json`

If a linter isn't installed, the script warns and skips it (partial results are still
valuable). The script checks for linter availability at startup and reports which
linters will run.

### Step 2: Generate the Report

```bash
python3 scripts/generate_lint_report.py <output_dir>/lint-baseline.json \
    --output <output_dir>/lint-baseline.md
```

### Step 3: Generate Linter Configs

The baseline script also produces starter configuration files in `lint-config/`.
These configs are tuned to the project — they exclude patterns that aren't relevant,
set appropriate severity levels, and configure paths.

## Finding Categories

Each finding is tagged with:

| Field | Values | Purpose |
|-------|--------|---------|
| `linter` | `pylint`, `pyupgrade`, `flake8` | Which tool found it |
| `code` | e.g. `W1601`, `UP001` | Linter-specific code |
| `category` | `syntax`, `semantic`, `import`, `stdlib`, `compat` | Migration category |
| `severity` | `error`, `warning`, `convention`, `info` | How serious |
| `automatable` | `true`, `false` | Can be fixed mechanically |
| `file` | Relative path | Which file |
| `line` | Line number | Where in the file |
| `message` | Description | What the finding is |

## Lint Score

Each module gets a composite score (0–100, higher is better) based on:

- **Finding density**: findings per 100 lines of code (lower is better)
- **Severity weighting**: errors count 4x, warnings 2x, conventions 1x
- **Automatable fraction**: more automatable findings = easier fix = higher score

The score formula:
```
raw_penalty = sum(severity_weight * count) / lines_of_code * 100
score = max(0, 100 - raw_penalty)
```

A module with score 100 has zero findings. A module with score 0 is heavily
laden with Py2-isms relative to its size.

## Prioritized Fix List

The report includes a ranked list of what to fix first, ordered by:

1. **Gateway modules first** — modules with high fan-in (many dependents) because fixing
   them unblocks the most downstream work
2. **Automatable issues first** — within each module, tackle the easy wins
3. **Highest severity first** — within each category, errors before warnings

## Integration with Other Skills

After generating the baseline, update the migration state:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py \
    <state_file> record-output \
    --module <module_path> \
    --output-path <output_dir>/lint-baseline.json
```

The Gate Checker (Skill X.3) uses `lint-baseline.json` to verify:
- Phase 1 → 2: lint baseline is stable (no regressions)
- Phase 2 → 3: no lint regressions after conversion

## Important Notes

**Linter installation**: The script does not install linters — it uses whatever is
available in the environment. For best results, install:
```bash
pip install pylint pyupgrade flake8 flake8-2020
```

**Python 2 syntax and pylint**: Running `pylint --py3k` on Python 2 code requires
pylint version 2.x (the last version to support Python 2 parsing). If only pylint 3.x
is available, the script falls back to regex-based detection for Python 2 syntax that
would cause a parse error.

**pyupgrade target version**: The `--py3X-plus` flag controls which upgrades are shown.
For target 3.12, use `--py312-plus`. The script maps the `target_version` parameter to
the correct flag automatically.

## Scope and Chunking

Linting the entire codebase at once is safe — the linters themselves handle large codebases efficiently. The risk is in how the agent presents the results.

**For any codebase over 100 files**: Direct the agent to produce a summary report with aggregate counts per category and per-module scores, not per-finding detail. The full lint output should be saved to `migration-analysis/lint-baseline.json` and referenced by path, not pasted into the conversation.

**Recommended approach**:
1. Run all linters, capturing output to files
2. Summarize: total findings by category, top-10 modules by finding count, overall migration readiness score
3. Present the summary in the conversation; reference the full report by path

**Expected output sizes**:
- pylint --py3k on 100 files: 20–80KB
- pylint --py3k on 500 files: 100–400KB
- Combined lint output on 1000+ files: 500KB–2MB

The full lint baseline is consumed by downstream skills (Custom Lint Rules, Gate Checker) directly from disk. The agent never needs to load the entire baseline into the conversation.

## References

- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
