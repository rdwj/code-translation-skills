---
name: py2to3-custom-lint-rules-generator
description: >
  Generate progressive lint configurations and custom pylint/flake8 plugins that enforce
  Python 2→3 migration phases. Use this skill whenever you need to create phase-specific linting rules,
  set up custom static analysis for your project patterns, generate pylint plugins that catch
  Py2 idioms in specific modules, or create enforcement gates between migration phases.
  Also trigger when someone says "create lint rules," "generate custom checks," "enforce
  migration phases with linting," "create phase-specific lint configs," or "build custom
  plugins." This skill transforms your codebase analysis into actionable, automated checks.
---

# Custom Lint Rule Generator

After analyzing your codebase with Phase 0 discovery tools, you have detailed knowledge of
which modules are where and what patterns they use. This skill turns that knowledge into
**custom lint rules** that progressively enforce migration discipline. Each phase gets
phase-specific linting rules, ensuring modules stay on track as they migrate.

## What It Does

This skill generates three things:

### 1. Custom Pylint Plugins
AST-based Python checkers that flag:
- **Phase 1+**: Python 2 idioms in modules that should use `__future__` imports
- **Phase 2+**: `print` statements, `except` old-style, `<>` operator
- **Phase 3+**: `six` and `future` library usage (should be migrated away)
- **Phase 4+**: Missing type annotations on public functions

### 2. Custom Flake8 Plugins
Pattern-based checkers for project-specific rules:
- **SCADA modules**: Encoding declaration enforcement (all handlers need `# coding: utf-8`)
- **Binary I/O**: File open modes checked for bytes vs. text
- **Pickle usage**: Protocol version enforcement (should use `protocol=2` or higher)
- **String/bytes confusion**: Detection of problematic concatenations

### 3. Per-Phase Pylintrc Files
Incrementally stricter configurations:
- `pylintrc-phase1`: Baseline (mostly lenient)
- `pylintrc-phase2`: Enforces print_function, absolute imports
- `pylintrc-phase3`: Requires `__future__` imports, flags six/future usage
- `pylintrc-phase4`: Requires type annotations, enforces strict mode

## Inputs

- **analysis_dir**: Output directory from Phase 0 discovery tools (contains `raw-scan.json`,
  `data-layer-report.json`, etc.)
- **output_dir**: Where to write generated lint plugins and configs
- **project_patterns** (optional): JSON file with custom rules specific to your project
  Example: `{"scada_modules": ["app/scada/*.py"], "requires_encoding": true}`
- **target_version** (optional): Python 3 target version (default: 3.9)

## Outputs

| File | Format | Purpose |
|------|--------|---------|
| `plugins/py2_idioms_checker.py` | Python | Pylint plugin for detecting Python 2 idioms |
| `plugins/flake8_project_checker.py` | Python | Flake8 plugin for project-specific patterns |
| `pylintrc-phase1` through `pylintrc-phase4` | INI | Per-phase pylint configurations |
| `.pre-commit-config.yaml` | YAML | Pre-commit hooks with custom plugins |
| `lint-rules-report.json` | JSON | Summary of all rules generated |
| `lint-rules-documentation.md` | Markdown | Human-readable guide to the custom rules |

## Workflow

### Step 1: Generate Lint Rules

```bash
python3 scripts/generate_lint_rules.py <phase_0_analysis_dir> \
    --output <output_dir> \
    --target-version 3.12 \
    [--project-patterns custom-patterns.json]
```

This script:
1. Reads Phase 0 analysis outputs to understand module structure
2. Generates AST-based pylint checker plugin
3. Generates pattern-based flake8 checker plugin
4. Creates per-phase pylintrc files with incrementally stricter rules
5. Generates `.pre-commit-config.yaml` with both plugins
6. Writes `lint-rules-report.json` with rule definitions

### Step 2: Generate Documentation

```bash
python3 scripts/generate_lint_rules_report.py <output_dir>/lint-rules-report.json \
    --output <output_dir>/lint-rules-documentation.md
```

### Step 3: Install Custom Plugins Locally

```bash
# Copy plugins to your project
mkdir -p .lint-plugins
cp <output_dir>/plugins/*.py .lint-plugins/

# Install for local linting
pip install pylint flake8

# Test the plugins
pylint --load-plugins=.lint-plugins.py2_idioms_checker app/

# Or use pre-commit hooks
pip install pre-commit
cp <output_dir>/.pre-commit-config.yaml ./
pre-commit run --all-files
```

### Step 4: Enforce Phases in CI

For each migration phase, use the appropriate pylintrc:

```bash
# Phase 1: Inject futures
pylint --rcfile=pylintrc-phase1 app/

# Phase 2: Convert to Py3 syntax
pylint --rcfile=pylintrc-phase2 app/

# Phase 3: Remove compatibility shims
pylint --rcfile=pylintrc-phase3 app/

# Phase 4: Enforce strict Python 3
pylint --rcfile=pylintrc-phase4 app/
```

## Example Custom Rules

### Encoding Declaration Enforcement (SCADA modules)

If Phase 0 analysis tagged modules in `app/scada/` as handling SCADA protocols, the
generated flake8 plugin flags any `.py` file in that directory without an explicit
encoding declaration:

```python
# app/scada/modbus_handler.py
# Missing encoding declaration! Should have:
# coding: utf-8

# ❌ This file would trigger E950 (custom rule)
```

Add the declaration:

```python
# coding: utf-8
"""Modbus protocol handler."""
```

### Binary I/O Mode Enforcement

When reading/writing binary data (detected from Phase 0 analysis of pickle, protobuf, etc.),
the plugin flags text-mode opens:

```python
# ❌ Wrong: opens in text mode, will fail on binary data
with open("data.pkl") as f:
    data = pickle.load(f)

# ✓ Correct: opens in binary mode
with open("data.pkl", "rb") as f:
    data = pickle.load(f)
```

### String/Bytes Concatenation Detection

When Phase 0 analysis finds string literals mixed with bytes from external sources:

```python
# ❌ Wrong: string literal + bytes
header = b"PREFIX_" + "data"

# ✓ Correct: consistent types
header = b"PREFIX_" + b"data"
# or
header = "PREFIX_" + "data"
```

## Phase-Specific Rules

### Phase 1 Rules (Future Imports)
- **PY2001**: Module missing `from __future__ import` statements
- **PY2002**: Using old `print` statement (should use print_function)
- **PY2003**: Using old `except` syntax (`except E, e:` instead of `except E as e:`)

### Phase 2 Rules (Py3 Syntax)
- **PY2004**: Using `xrange()` (should be `range()`)
- **PY2005**: Using `.iteritems()` (should be `.items()`)
- **PY2006**: Using `basestring` (should be `str`)
- **PY2007**: Using `__unicode__` method (should be `__str__`)

### Phase 3 Rules (Remove Shims)
- **PY2008**: Using `six.string_types` (should use `str`)
- **PY2009**: Using `future` library imports (should have been removed)
- **PY2010**: Using `bytes` vs `str` incorrectly (should be consistent)

### Phase 4 Rules (Strict Python 3)
- **PY2011**: Public function missing type annotations
- **PY2012**: Function has no docstring
- **PY2013**: Class missing `__repr__` method

## Custom Project Patterns

Provide a JSON file with project-specific rules:

```json
{
  "scada_modules": [
    "app/scada/*.py",
    "app/protocol/*.py"
  ],
  "requires_encoding": true,
  "binary_modules": [
    "app/storage/*.py",
    "app/serialization/*.py"
  ],
  "pickle_modules": [
    "app/cache/*.py"
  ],
  "pickle_protocol_min": 2,
  "exclude_patterns": [
    "**/vendor/**",
    "**/test/**"
  ]
}
```

## Report Structure

The `lint-rules-report.json` contains:

```json
{
  "timestamp": "2026-02-12T...",
  "analysis_dir": "/path/to/phase-0-output",
  "target_python3_version": "3.12",
  "rules_generated": {
    "pylint_plugin": {
      "count": 12,
      "rules": [
        {
          "code": "PY2001",
          "message": "Module missing __future__ imports",
          "phase": 1,
          "category": "future-imports",
          "automatable": true
        }
      ]
    },
    "flake8_plugin": {
      "count": 8,
      "rules": [
        {
          "code": "E950",
          "message": "SCADA module missing encoding declaration",
          "pattern": "scada",
          "automatable": false
        }
      ]
    }
  },
  "custom_patterns": {},
  "configuration_files": {
    "pylintrc_phase1": "pylintrc-phase1",
    "pylintrc_phase2": "pylintrc-phase2",
    "pylintrc_phase3": "pylintrc-phase3",
    "pylintrc_phase4": "pylintrc-phase4",
    "pre_commit_config": ".pre-commit-config.yaml"
  }
}
```

## Integration with Other Skills

This skill's outputs feed into:

- **Skill X.3 (Gate Checker)**: Per-phase pylintrc files are used to enforce migration gates
  - Phase 1→2: All Phase 1 modules must pass `pylintrc-phase1`
  - Phase 2→3: All Phase 2 modules must pass `pylintrc-phase2`
- **CI/CD Pipeline**: Use `--rcfile=pylintrc-phaseN` in CI to enforce phase discipline
- **Pre-commit hooks**: Installed hooks check each commit against the appropriate phase config

After running, update the migration state:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py \
    <state_file> record-output \
    --module <module_path> \
    --output-path <output_dir>/lint-rules-report.json
```

## Important Notes

**Custom plugins are project-specific.** The generated pylint and flake8 plugins are tailored
to your codebase structure. They won't work on other projects without modification.

**Phase-specific linting is progressive.** Each phase's pylintrc is less strict than the next.
This allows modules to migrate at different speeds while still catching regressions.

**Pre-commit hooks enforce discipline.** Use the generated `.pre-commit-config.yaml` to
automatically check each commit. This prevents accidental regressions.

**Documentation is essential.** The generated `lint-rules-documentation.md` explains what each
custom rule does and why it matters. Share this with your team.

## References

- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
