---
name: py2to3-compatibility-shim-remover
description: >
  After full cutover to Python 3, removes all dual-compatibility code including __future__ imports,
  six library usage, python-future shims, and version-specific branching. Modernizes codebase for
  target Python 3.x version. Use this skill when you need to clean up compatibility code post-migration,
  remove six and future dependencies, collapse version guards, or modernize Python 3-specific features.
  Trigger on "remove compatibility shims," "clean up Py2 code," "remove six usage," or "post-cutover cleanup."
---

# Skill 5.2: Compatibility Shim Remover

## Why Remove Compatibility Code After Cutover

A successful Py2→Py3 canary deployment means Py3 is now stable in production. The dual-compatibility code that kept Py2 working becomes **technical debt**:

- **Performance Overhead**: Conditional imports and version checks add overhead
- **Cognitive Load**: Developers must understand both paths through code
- **Maintenance Burden**: Duplicate code paths mean more testing and bug fixes
- **Dependency Bloat**: `six` and `future` libraries are no longer needed
- **Type Safety**: Type hints can't optimize for unused code paths
- **Security**: Obsolete dependencies have unpatched vulnerabilities

**Compatibility Shim Remover** safely removes all this code, transforming the codebase into clean Python 3-only code.

---

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| **codebase_path** | User | Root directory of Python 2/3 dual-compatible codebase |
| **--target-version** | User | Python 3.x target (3.9, 3.11, 3.12, 3.13); default: 3.11 |
| **--output** | User | Output directory for modified files (default: current dir) |
| **--dry-run** | User | Show what would be removed, don't modify files |
| **--modules** | User | Comma-separated list of modules to process (default: all) |
| **--test-command** | User | Command to run tests after each batch (e.g., `pytest -xvs`) |
| **--batch-size** | User | Number of files to process per batch before testing (default: 10) |

---

## Outputs

All outputs go into the `--output` directory:

| File | Format | Purpose |
|------|--------|---------|
| `shim-removal-report.json` | JSON | Summary of removals by category, per-file changes, test results |
| `shim-removal-report.md` | Markdown | Human-readable summary with before/after examples |
| `shim-removal-diff.patch` | Patch | Unified diff of all changes (if `--dry-run` mode) |
| Modified source files | Python | Files with shims removed (if not dry-run) |

---

## Workflow

### Step 1: Analyze Dual-Compatibility Code

Run the main removal script:

```bash
python3 scripts/remove_shims.py <codebase_path> \
    --target-version 3.11 \
    --output ./cleaned-codebase/ \
    --dry-run \
    --test-command "pytest -xvs" \
    --batch-size 10
```

The script scans for:

**Category 1: `__future__` imports**
- `from __future__ import print_function`
- `from __future__ import division`
- `from __future__ import unicode_literals`
- `from __future__ import absolute_import`
- `from __future__ import with_statement`
- Exception: Keeps `annotations` if target < 3.14

**Category 2: `six` library usage**
- Type checks: `six.text_type`, `six.binary_type`, `six.string_types`, `six.integer_types`
- Iteration: `six.iteritems(d)`, `six.itervalues(d)`, `six.iterkeys(d)`
- Compatibility functions: `six.ensure_str()`, `six.ensure_text()`
- Moves/imports: `six.moves.range`, `six.moves.input`, `six.moves.urllib.*`
- Metaclass: `@six.add_metaclass(Meta)`
- Decorator: `@six.python_2_unicode_compatible`
- Conditions: `six.PY2`, `six.PY3`

**Category 3: `python-future` / `builtins` imports**
- `from builtins import range`
- `from builtins import bytes`
- `from past import *`
- `from future import *`

**Category 4: `sys.version_info` guards**
- `if sys.version_info[0] == 2: ... else: ...`
- `if sys.version_info < (3, ...): ... else: ...`
- Keeps only Py3 branch, deletes Py2 branch

**Category 5: Try-except import patterns**
- `try: import X except ImportError: import Y` where X is Py3 name
- Keeps only Py3 import, deletes except clause

**Category 6: Modernization via `pyupgrade`**
- If `pyupgrade` available, suggests modernizations for target version
- Examples: f-strings, type hints, dataclasses, etc.

### Step 2: Plan Removal Strategy

The script generates a removal plan:

1. Identify all files with compatibility code
2. Group files by complexity
3. Order removal to minimize test failures (simple files first)
4. Estimate impact per file

### Step 3: Batch Processing with Testing

Process files in batches and run tests after each batch:

```bash
# Batch 1: Simple __future__ imports (files 1-10)
# → Remove __future__ imports from 10 files
# → Run: pytest -xvs
# → Success? Proceed to Batch 2

# Batch 2: six.moves replacements (files 11-20)
# → Replace six.moves imports with Py3 equivalents
# → Run: pytest -xvs
# → Success? Proceed to Batch 3

# ... continue for all batches
```

Each batch:
1. Creates modified versions of target files
2. Runs test command
3. If tests pass, commits modifications
4. If tests fail, rolls back and reports problem file

### Step 4: Generate Report

The script produces a comprehensive report showing:

- **Summary**: Total removals by category
- **Per-file changes**: What was removed from each file
- **Remaining usage**: Any `six` or `future` that wasn't removed (manual review needed)
- **Test results**: Test status after each batch
- **Modernization suggestions**: Via `pyupgrade`

---

## Removal Patterns

### 1. `__future__` Imports

**Before**:
```python
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals
from __future__ import absolute_import

print("Hello")
x = 5 / 2  # Now float
```

**After**:
```python
print("Hello")
x = 5 / 2  # Float in Py3
```

**Rule**: Delete all `__future__` imports except `annotations` (if target < 3.14).

### 2. six Type Checks

**Before**:
```python
import six

if isinstance(x, six.string_types):
    ...

if isinstance(x, six.integer_types):
    ...

if isinstance(x, six.binary_type):
    ...
```

**After**:
```python
if isinstance(x, str):
    ...

if isinstance(x, int):
    ...

if isinstance(x, bytes):
    ...
```

**Mappings**:
- `six.text_type` → `str`
- `six.binary_type` → `bytes`
- `six.string_types` → `(str,)`
- `six.integer_types` → `(int,)`

### 3. six Iteration Methods

**Before**:
```python
import six

for k, v in six.iteritems(d):
    ...

for v in six.itervalues(d):
    ...

for k in six.iterkeys(d):
    ...
```

**After**:
```python
for k, v in d.items():
    ...

for v in d.values():
    ...

for k in d.keys():
    ...
```

### 4. six Moves (imports)

**Before**:
```python
from six.moves import range, input
from six.moves.urllib.parse import urlencode

for i in range(10):
    x = input("Enter value: ")
    url = f"?{urlencode(params)}"
```

**After**:
```python
# No imports needed (built-ins)

for i in range(10):
    x = input("Enter value: ")
    url = f"?{urlencode(params)}"  # from urllib.parse import urlencode
```

### 5. six Ensure Functions

**Before**:
```python
import six

s = six.ensure_str(data)
t = six.ensure_text(data)
```

**After**:
```python
s = data if isinstance(data, str) else data.decode('utf-8')
t = data if isinstance(data, str) else data.decode('utf-8')

# Or simply (if no encoding concerns):
s = str(data)
t = str(data)
```

### 6. six Python Version Checks

**Before**:
```python
import six

if six.PY2:
    # Py2-specific code
    x = unicode(s)
else:
    # Py3-specific code
    x = str(s)
```

**After**:
```python
x = str(s)  # Always Py3 now
```

**Optimization**: After simplification, often further optimization is possible:
- Remove entire conditionals if only one branch remains
- Collapse nested conditionals

### 7. six Metaclass Decorator

**Before**:
```python
import six

@six.add_metaclass(MetaClass)
class MyClass:
    ...
```

**After**:
```python
class MyClass(metaclass=MetaClass):
    ...
```

### 8. six Unicode Decorator

**Before**:
```python
import six

@six.python_2_unicode_compatible
class MyClass:
    def __str__(self):
        return "text"
```

**After**:
```python
class MyClass:
    def __str__(self):
        return "text"
```

### 9. sys.version_info Guards

**Before**:
```python
import sys

if sys.version_info[0] == 2:
    # Py2-specific code
    range_func = xrange
    str_type = unicode
else:
    # Py3-specific code
    range_func = range
    str_type = str

result = range_func(10)
```

**After**:
```python
result = range(10)  # Py3 only
```

### 10. Try-except Import Guards

**Before**:
```python
try:
    from urllib.parse import urlencode  # Py3
except ImportError:
    from urllib import urlencode  # Py2
```

**After**:
```python
from urllib.parse import urlencode  # Py3 only
```

### 11. builtins Module Imports

**Before**:
```python
from builtins import range, bytes, str

for i in range(10):
    data = bytes([1, 2, 3])
```

**After**:
```python
for i in range(10):
    data = bytes([1, 2, 3])  # No import needed
```

### 12. Cleanup: Remove six and future from Dependencies

**Before** (requirements.txt):
```
django==3.2
six==1.16.0
python-future==0.18.2
requests==2.28.0
```

**After**:
```
django==3.2
requests==2.28.0
```

**Before** (setup.py):
```python
setup(
    name="myapp",
    install_requires=[
        "six>=1.15.0",
        "python-future>=0.18.0",
    ],
)
```

**After**:
```python
setup(
    name="myapp",
    install_requires=[],
)
```

---

## Test Strategy

### Pre-Removal Testing

Before running removal:

1. Ensure all tests pass with current code
2. Establish baseline test time
3. Verify test coverage is good (especially compatibility-related code)

### Batch Testing

After each batch of removals:

1. Run full test suite
2. Check for test failures
3. If failures: analyze, fix in-batch, re-run tests
4. If success: proceed to next batch

### Post-Removal Testing

After all removals:

1. Full test suite
2. Load testing (if applicable)
3. Manual QA in staging
4. Code review focused on removed patterns

---

## Success Criteria

The skill has succeeded when:

1. All `__future__` imports are removed (except `annotations` if applicable)
2. All `six` library usage is replaced with Py3 equivalents
3. All `python-future` / `builtins` imports are removed
4. All `sys.version_info` guards are collapsed to Py3 branch
5. All try-except import patterns are simplified to Py3 imports
6. `six` and `future` are removed from requirements.txt / setup.py / pyproject.toml
7. All tests pass after removal
8. A report is generated showing what was removed and what remains
9. Code is cleaner, more readable, with less cognitive load

---

## Special Cases

### Type Hints and Annotations

If using type hints:

**Before**:
```python
from __future__ import annotations  # Deferred evaluation for Py3.7+
from typing import Optional, List

def process(items: List[str]) -> Optional[str]:
    ...
```

**After** (if target >= 3.10):
```python
def process(items: list[str]) -> str | None:
    ...
```

**Note**: Keep `from __future__ import annotations` only if target < 3.14 and using string annotations.

### Deprecated Modules

Some modules moved between Py2 and Py3:

**Before**:
```python
try:
    import configparser  # Py3
except ImportError:
    import ConfigParser as configparser  # Py2
```

**After**:
```python
import configparser  # Py3 only
```

### Unicode Literals

In Py2, string literals were bytes by default. In Py3, they're Unicode.

**Before**:
```python
from __future__ import unicode_literals

message = "Hello"  # Unicode in both Py2 and Py3
```

**After**:
```python
message = "Hello"  # Always Unicode in Py3
```

---

## Troubleshooting

### "Test failure after batch N"

1. Identify which file in batch caused failure
2. Review what was removed from that file
3. Understand the test failure (type error, import error, logic error)
4. Decide: fix removal pattern or revert batch
5. If reverting: mark file as "needs manual review"

### "six or future imports still present after removal"

1. Check for non-standard patterns (e.g., `from six.moves import *`)
2. Verify coverage of removal patterns (may need manual cleanup)
3. Report remaining usage in shim-removal-report.md

### "Performance got worse after removal"

1. Unlikely but possible if modernization exposed hot paths
2. Profile before/after
3. Optimize hot paths specifically for Py3

---

## References

- `references/six-to-py3-equivalents.md` — Complete mapping of six functions to Py3
- `references/future-to-py3-migration.md` — python-future removal patterns
- `references/version-guard-collapse.md` — Simplifying sys.version_info checks
- `references/pyupgrade-modernization.md` — Modernizing Py3 code with pyupgrade
- [six Documentation](https://six.readthedocs.io/)
- [python-future Documentation](https://python-future.org/)
- [PEP 570 - Python 3.8+ Features](https://www.python.org/dev/peps/pep-0570/)
- [PEP 604 - Union Types (Py 3.10+)](https://www.python.org/dev/peps/pep-0604/)
