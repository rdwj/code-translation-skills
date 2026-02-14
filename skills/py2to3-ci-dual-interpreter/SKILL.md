---
name: py2to3-ci-dual-interpreter-configurator
description: >
  Automatically detect your project's CI system and generate configurations to run tests
  under both Python 2.7 and Python 3.X side-by-side during Python 2→3 migration. Use this skill whenever you need to
  set up dual-interpreter testing, validate that your code runs on both versions, configure
  a test matrix for the migration process, or test your codebase on multiple Python versions
  simultaneously. Also trigger when someone says "set up dual Python testing," "add Python 3
  to CI," "create a test matrix," "run tests on both versions," "configure GitHub Actions for
  Python 2 and 3," or "set up tox for dual testing." This skill is essential for validating
  migration progress without breaking Python 2 support.
---

# CI Dual-Interpreter Configurator

Running tests under both Python 2 and Python 3 simultaneously is critical during migration.
This skill auto-detects your CI system, generates appropriate configuration files, and sets
up a test matrix that validates both versions. It also produces a local tox.ini so developers
can test dual-interpreter compatibility on their machines before pushing.

## Supported CI Systems

The skill auto-detects and configures:

| CI System | Detection | Config File | Matrix Strategy |
|-----------|-----------|------------|-----------------|
| GitHub Actions | `.github/workflows/*.yml` | `.github/workflows/python-matrix.yml` | `strategy.matrix.python-version` |
| GitLab CI | `.gitlab-ci.yml` | `.gitlab-ci.yml` (update) | Parallel jobs with different Docker images |
| Jenkins | `Jenkinsfile` (Groovy/declarative) | `Jenkinsfile` (update) | Parallel stages for each Python version |
| Travis CI | `.travis.yml` | `.travis.yml` (update) | `python:` array with `allow_failures` |
| CircleCI | `.circleci/config.yml` | `.circleci/config.yml` (update) | Separate jobs in `jobs:` with different images |

If no CI config is detected, the skill still generates a `tox.ini` for local testing.

## Inputs

- **codebase_path**: Root directory of the Python 2 codebase
- **output_dir**: Where to write generated CI configs and reports
- **target_version** (optional): Target Python 3 version for matrix (default: 3.9). Options: 3.9, 3.11, 3.12, 3.13
- **ci_system** (optional): Force CI system: `auto` (detect), `github`, `gitlab`, `jenkins`, `travis`, `circle`, or `none` (tox-only). Default: `auto`
- **python2_version** (optional): Python 2 version to test (default: 2.7)
- **coverage_enabled** (optional): Generate coverage reporting configs (default: true)
- **allow_py3_failures** (optional): Mark Python 3 tests as informational (allowed to fail). Default: true
- **exclude_patterns** (optional): Glob patterns for files to skip in test discovery

## Outputs

| File | Format | Purpose |
|------|--------|---------|
| `tox.ini` | INI | Local dual-interpreter testing configuration |
| `<ci-config>` | YAML/Groovy | Auto-generated or updated CI configuration |
| `pytest.ini` | INI | Pytest configuration (if not present) |
| `ci-setup-report.json` | JSON | Detection results, generated configs, next steps |
| `ci-setup-report.md` | Markdown | Human-readable summary with setup instructions |

## Workflow

### Step 1: Detect and Generate CI Configs

```bash
python3 scripts/configure_ci.py <codebase_path> \
    --output <output_dir> \
    --target-version 3.12 \
    --coverage-enabled
```

This script:
1. Discovers CI system configuration files in the codebase
2. Parses the detected config to understand current setup
3. Generates or updates CI config to add Python 3 matrix
4. Generates `tox.ini` for local testing
5. Generates/updates `pytest.ini` if needed
6. Writes `ci-setup-report.json` with detection details

The script is **safe**: it reads configs but does not commit changes. All generated files
can be reviewed before checking in.

### Step 2: Review Generated Configs

```bash
# Review what was generated
cat <output_dir>/ci-setup-report.json
cat <output_dir>/ci-setup-report.md

# Compare with existing CI config
diff -u .github/workflows/python-matrix.yml <output_dir>/python-matrix.yml
```

### Step 3: Generate the Report

```bash
python3 scripts/generate_ci_report.py <output_dir>/ci-setup-report.json \
    --output <output_dir>/ci-setup-report.md
```

### Step 4: Apply the Generated Configs

Copy generated configs to your project:

```bash
# For GitHub Actions
cp <output_dir>/python-matrix.yml .github/workflows/python-matrix.yml

# For tox (commit this for team use)
cp <output_dir>/tox.ini ./tox.ini

# For pytest config
cp <output_dir>/pytest.ini ./pytest.ini
```

### Step 5: Test Locally Before Pushing

```bash
# Test on Python 2.7
tox -e py27

# Test on Python 3.12
tox -e py312

# Test on all configured versions
tox
```

## GitHub Actions Example

The generated `.github/workflows/python-matrix.yml` looks like:

```yaml
name: Python 2 & 3 Matrix Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ['2.7', '3.9', '3.11', '3.12']

    steps:
    - uses: actions/checkout@v3
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements-dev.txt
    - name: Lint with flake8
      run: flake8 .
    - name: Test with pytest
      run: pytest tests/
    - name: Report coverage
      if: matrix.python-version == '3.12'
      run: coverage report
```

## tox.ini Example

The generated `tox.ini` includes:

```ini
[tox]
envlist = py27,py39,py311,py312

[testenv]
deps =
    pytest>=4.0
    pytest-cov
    -r{toxinidir}/requirements-dev.txt
commands =
    pytest {posargs:tests/}
    coverage report --skip-covered

[testenv:py27]
basepython = python2.7

[testenv:py312]
basepython = python3.12
```

## Configuration Details

### GitHub Actions

- Creates a matrix job with `python-version: ['2.7', '3.9', ...]`
- Runs install, lint, and test steps for each version
- Python 3 failures are marked with `continue-on-error: true` (allowed to fail)
- Coverage reporting runs only on the latest Python 3 version
- Uses standard `actions/setup-python@v4` action

### GitLab CI

- Generates parallel jobs with different `image:` directives
- `py27` job uses `python:2.7-slim`
- `py3X` jobs use `python:3.X-slim`
- Python 3 jobs allow failure with `allow_failure: true`
- Coverage artifacts collected from latest Python 3 version

### tox.ini (Local Testing)

- Environments: `py27` (Python 2.7), `py39`, `py311`, `py312` (configurable)
- Each environment has its own virtualenv
- Dependencies installed from requirements files
- Test command: `pytest` by default
- Coverage plugin integrated

### Jenkins (Declarative Pipeline)

- Parallel stages for py27 and each py3X version
- Each stage runs in its own workspace
- Python 3 stages use `catchError()` to allow failure
- Coverage results aggregated

### Travis CI

- `python:` array with all versions
- `allow_failures:` section for Python 3 versions
- Before-script: install dependencies
- Script: run pytest

### CircleCI

- Separate jobs in `jobs:` section
- Different Docker images per job
- Python 3 jobs don't block on failure
- Coverage data uploaded to Codecov

## Coverage Reporting

If `--coverage-enabled` is set (default), the generated configs:
- Install `pytest-cov` or `coverage` package
- Add `pytest --cov=.` to test commands
- Collect coverage.xml artifacts
- Report coverage only on latest Python 3 (to avoid duplication)
- Optionally integrate with Codecov, Coveralls, or other CI coverage services

## Pytest Configuration

If `pytest.ini` doesn't exist, the script generates one:

```ini
[pytest]
testpaths = tests
python_files = test_*.py *_test.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

## Report Structure

The `ci-setup-report.json` contains:

```json
{
  "timestamp": "2026-02-12T...",
  "codebase_path": "/path/to/codebase",
  "ci_system_detected": "github|gitlab|jenkins|travis|circle|none",
  "ci_config_path": ".github/workflows/...",
  "target_python3_version": "3.12",
  "python2_version": "2.7",
  "coverage_enabled": true,
  "allow_py3_failures": true,
  "generated_files": {
    "tox_ini": "tox.ini",
    "pytest_ini": "pytest.ini",
    "ci_config": ".github/workflows/python-matrix.yml"
  },
  "configuration": {
    "test_envs": ["py27", "py39", "py311", "py312"],
    "matrix_strategy": "github_actions|tox|...",
    "coverage_tool": "pytest-cov",
    "test_command": "pytest tests/"
  },
  "next_steps": [
    "Review generated config files",
    "Run 'tox -e py27' to test locally",
    "Commit generated files to repository"
  ]
}
```

## Integration with Other Skills

This skill's outputs feed into:

- **Skill X.3 (Gate Checker)**: CI config is evidence for Phase 1→2 gate (dual-interpreter
  testing must be operational)
- **Skill 1.1 (Future Imports Injector)**: After injecting futures, use this to validate
  both versions pass in CI
- **Skill 1.2 (Test Scaffold Generator)**: Generated test configs work with the CI matrix

After running, update the migration state:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py \
    <state_file> record-output \
    --module <module_path> \
    --output-path <output_dir>/ci-setup-report.json
```

## Important Notes

**Python 2.7 support is being phased out.** GitHub Actions, GitLab CI, and CircleCI are
deprecating Python 2.7 support. The generated configs may need adjustment:
- For GitHub Actions: use `ubuntu-20.04` runner (not 22.04) for Python 2.7 support
- For GitLab: `python:2.7-slim` is still available but consider alternative runners
- For CircleCI: legacy Python 2.7 image support varies by plan

**Test on both versions locally first.** Don't rely on CI to catch dual-version issues.
Run `tox` locally before pushing to catch problems early.

**Coverage reporting on both versions adds overhead.** The configs only report coverage
from the latest Python 3 version to keep CI times reasonable.

**Pre-existing CI configs are not overwritten.** The script generates files in the output
directory. Review and apply them manually to avoid losing custom CI settings.

## References

- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
