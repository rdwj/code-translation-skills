---
name: py2to3-build-system-updater
description: >
  Python 2→3 build system updater. Updates build/packaging infrastructure (setup.py, setup.cfg, pyproject.toml, Dockerfile, Makefile, shell scripts, requirements) for Python 3 compatibility, with distutils→setuptools migration and shebang updates.
---

# Build System Updater (Skill 2.3)

## Overview

This skill scans and updates a Python project's build and packaging infrastructure for Python 3 compatibility. It detects critical issues like distutils usage (incompatible with Python 3.12+), updates version requirements, migrates outdated patterns, and flags dependency version concerns.

**Key responsibility**: Transform build artifacts from Python 2-style configuration to modern Python 3 standards, with emphasis on setuptools adoption and explicit version constraints.

## Inputs

| Input | Type | Required | Description |
|-------|------|----------|-------------|
| codebase_path | string | yes | Root directory of Python project to scan |
| target_version | string | yes | Target Python version (3.9, 3.11, 3.12, 3.13) |
| dry_run | boolean | no | Preview changes without modifying files (default: false) |
| migrate_to_pyproject | boolean | no | Generate pyproject.toml from setup.py, update others to PEP 518 format (default: false) |
| output_dir | string | no | Directory for JSON report outputs (default: codebase root) |

## Outputs

| Output | Type | Description |
|--------|------|-------------|
| modified_files | list[string] | Paths of files modified (or would be modified in dry-run) |
| build_system_report.json | file | Detailed findings: build files discovered, changes applied/suggested, distutils migration guidance |
| dependency_compatibility.json | file | Flagged incompatible pinned versions, unclear version specifiers |
| build_system_report.md | file | Markdown report with summary, detailed changes, remediation steps |
| exit_status | int | 0 = success, 1 = analysis errors, 2 = write errors |

## Workflow Steps

1. **Discover build files** in codebase:
   - setup.py, setup.cfg, pyproject.toml, Makefile, Dockerfile, docker-compose.yml
   - Shell scripts (*.sh), requirements*.txt, Pipfile, tox.ini
   - Capture absolute paths and file sizes

2. **Analyze setup.py** (if exists):
   - Parse using ast and re to detect distutils imports (critical for 3.12+)
   - Extract: `python_requires`, classifiers, entry_points, install_requires, extras_require
   - Flag: distutils.core, distutils.extension, distutils.command usage
   - Record: current version constraint, any dynamic version reading

3. **Analyze setup.cfg / pyproject.toml**:
   - Extract metadata sections, python_requires, classifiers, dependencies
   - Note format and any legacy patterns

4. **Update distutils usage**:
   - Replace `from distutils.core import setup` → `from setuptools import setup`
   - Replace `from distutils.extension import Extension` → `from setuptools import Extension`
   - Replace distutils.command.* → setuptools.command.* equivalents
   - Add setuptools to build-system.requires in pyproject.toml if needed

5. **Update version constraints**:
   - Change python_requires='>=2.7' to python_requires='>=3.X' (where X matches target_version)
   - Update/add classifiers: remove all `Programming Language :: Python :: 2.*`, add target version classifiers

6. **Update shebangs and CLI references**:
   - In shell scripts and Makefiles: `#!/usr/bin/env python` → `#!/usr/bin/env python3`
   - In Makefiles/scripts: `$(PYTHON)` → `$(PYTHON3)` (or hardcode python3 if unset)
   - In Dockerfile: `FROM python:2.7` → `FROM python:3.X`

7. **Check dependency versions** (flag-only):
   - Scan requirements.txt, Pipfile, install_requires for version pins
   - Flag packages with version specifiers that may not support Py3 target
   - Report as warnings, do not auto-update

8. **Optional: Migrate to pyproject.toml** (if --migrate-to-pyproject):
   - Parse setup.py + setup.cfg into unified pyproject.toml
   - Use modern PEP 517/518 format
   - Archive original setup.py as setup.py.bak

## References

- [PEP 517: Build system interface](https://www.python.org/dev/peps/pep-0517/)
- [PEP 518: Specifying build system requirements](https://www.python.org/dev/peps/pep-0518/)
- [PEP 621: Declaring project metadata in pyproject.toml](https://www.python.org/dev/peps/pep-0621/)
- [setuptools documentation](https://setuptools.pypa.io/)
- [distutils deprecation timeline](https://setuptools.pypa.io/en/latest/history.html)
- [Python 3.12 distutils removal](https://docs.python.org/3.12/whatsnew/3.12.html#distutils)

## Success Criteria

- All setup.py files converted to use setuptools (no distutils imports)
- python_requires updated to target Python version (e.g., `>=3.12` for target 3.12)
- All shebangs in scripts and Dockerfile updated to reference python3
- Makefile/shell scripts use python3 or $(PYTHON3) instead of python
- Dependency version flags generated for manual review
- Dry-run mode produces accurate diff without modifying files
- JSON reports machine-readable and aligned with downstream tools
