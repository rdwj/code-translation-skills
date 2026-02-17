# Code Examples and Pattern Tables

**This file supports:** `/sessions/stoic-practical-faraday/mnt/code-translation-skills/skills/py2to3-compatibility-shim-remover/SKILL.md`

## 1. __future__ Imports Removal

### Before
```python
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals
from __future__ import absolute_import

print("Hello")
x = 5 / 2  # Now float
```

### After
```python
print("Hello")
x = 5 / 2  # Float in Py3
```

**Rule**: Delete all `__future__` imports except `annotations` (if target < 3.14).

## 2. six Type Checks

### Before
```python
import six

if isinstance(x, six.string_types):
    ...
if isinstance(x, six.integer_types):
    ...
if isinstance(x, six.binary_type):
    ...
```

### After
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

## 3. six Iteration Methods

### Before
```python
import six

for k, v in six.iteritems(d):
    ...
for v in six.itervalues(d):
    ...
for k in six.iterkeys(d):
    ...
```

### After
```python
for k, v in d.items():
    ...
for v in d.values():
    ...
for k in d.keys():
    ...
```

## 4. six Moves (imports)

### Before
```python
from six.moves import range, input
from six.moves.urllib.parse import urlencode

for i in range(10):
    x = input("Enter value: ")
    url = f"?{urlencode(params)}"
```

### After
```python
# No imports needed (built-ins)

for i in range(10):
    x = input("Enter value: ")
    url = f"?{urlencode(params)}"  # from urllib.parse import urlencode
```

## 5. six Ensure Functions

### Before
```python
import six

s = six.ensure_str(data)
t = six.ensure_text(data)
```

### After
```python
s = data if isinstance(data, str) else data.decode('utf-8')
t = data if isinstance(data, str) else data.decode('utf-8')

# Or simply (if no encoding concerns):
s = str(data)
t = str(data)
```

## 6. six Python Version Checks

### Before
```python
import six

if six.PY2:
    # Py2-specific code
    x = unicode(s)
else:
    # Py3-specific code
    x = str(s)
```

### After
```python
x = str(s)  # Always Py3 now
```

## 7. six Metaclass Decorator

### Before
```python
import six

@six.add_metaclass(MetaClass)
class MyClass:
    ...
```

### After
```python
class MyClass(metaclass=MetaClass):
    ...
```

## 8. six Unicode Decorator

### Before
```python
import six

@six.python_2_unicode_compatible
class MyClass:
    def __str__(self):
        return "text"
```

### After
```python
class MyClass:
    def __str__(self):
        return "text"
```

## 9. sys.version_info Guards

### Before
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

### After
```python
result = range(10)  # Py3 only
```

## 10. Try-except Import Guards

### Before
```python
try:
    from urllib.parse import urlencode  # Py3
except ImportError:
    from urllib import urlencode  # Py2
```

### After
```python
from urllib.parse import urlencode  # Py3 only
```

## 11. builtins Module Imports

### Before
```python
from builtins import range, bytes, str

for i in range(10):
    data = bytes([1, 2, 3])
```

### After
```python
for i in range(10):
    data = bytes([1, 2, 3])  # No import needed
```

## 12. Cleanup: Remove six and future from Dependencies

### Before (requirements.txt)
```
django==3.2
six==1.16.0
python-future==0.18.2
requests==2.28.0
```

### After
```
django==3.2
requests==2.28.0
```

### Before (setup.py)
```python
setup(
    name="myapp",
    install_requires=[
        "six>=1.15.0",
        "python-future>=0.18.0",
    ],
)
```

### After
```python
setup(
    name="myapp",
    install_requires=[],
)
```

## Special Cases

### Type Hints and Annotations

**Before** (Python 3.7+):
```python
from __future__ import annotations
from typing import Optional, List

def process(items: List[str]) -> Optional[str]:
    ...
```

**After** (Python 3.10+):
```python
def process(items: list[str]) -> str | None:
    ...
```

**Note**: Keep `from __future__ import annotations` only if target < 3.14 and using string annotations.

### Deprecated Modules

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

**Before**:
```python
from __future__ import unicode_literals

message = "Hello"  # Unicode in both Py2 and Py3
```

**After**:
```python
message = "Hello"  # Always Unicode in Py3
```

## Removal Categories Summary

| Category | Pattern | Before | After | Auto-fixable |
|----------|---------|--------|-------|--------------|
| __future__ | `from __future__ import X` | 4 lines | 0 lines | YES |
| six types | `six.string_types` | 2 instances | 0 instances | YES |
| six iteration | `six.iteritems(d)` | 1 line | 1 line (d.items()) | YES |
| six moves | `from six.moves import range` | 1 line | 0 lines | YES |
| six ensure | `six.ensure_str()` | 1 call | Type-aware code | PARTIAL |
| six version | `if six.PY2: ... else: ...` | 2 branches | 1 branch | YES |
| six metaclass | `@six.add_metaclass()` | 1 decorator | class signature | YES |
| six unicode | `@six.python_2_unicode_compatible` | 1 decorator | 0 decorators | YES |
| sys.version_info | `if sys.version_info < (3,)` | Multi-branch | Single branch | YES |
| try-except imports | `try/except ImportError` | 2 imports | 1 import | YES |
| builtins | `from builtins import range` | 1 line | 0 lines | YES |
| dependencies | `six>=1.15.0` in requirements | Listed | Removed | Manual |

## Batch Processing Example

### Batch 1: Simple __future__ imports (files 1-10)
```
Before: 10 files × ~3 __future__ lines = ~30 lines to remove
Action: Remove all __future__ imports except annotations
Tests: pytest -xvs
Result: PASS → Proceed to Batch 2
```

### Batch 2: six.moves replacements (files 11-20)
```
Before: 10 files × ~2-3 six.moves imports = ~25 imports to replace
Action: Replace with built-in equivalents or Py3 stdlib
Tests: pytest -xvs
Result: PASS → Proceed to Batch 3
```

### Batch 3: six type checks and iteration (files 21-30)
```
Before: 10 files × ~5 six usages = ~50 replacements
Action: Replace six.string_types, six.iteritems, etc.
Tests: pytest -xvs
Result: PASS → Proceed to Batch 4
```

### Batch 4: sys.version_info and try-except guards (files 31-40)
```
Before: 10 files × ~3-4 guards = ~35 guards
Action: Collapse to Py3 branch, delete Py2 branch
Tests: pytest -xvs
Result: PASS → Proceed to Batch 5
```

### Batch 5: Clean up imports and dependencies
```
Before: 1 requirements.txt, 1 setup.py
Action: Remove six and python-future from dependencies
Tests: pytest -xvs
Result: PASS → All cleanup complete
```

## Report Content Example

### Shim Removal Report (shim-removal-report.json)

```json
{
  "summary": {
    "total_files_processed": 45,
    "total_removals": 187,
    "by_category": {
      "__future__": 23,
      "six_types": 34,
      "six_iteration": 28,
      "six_moves": 18,
      "six_ensure": 12,
      "six_version_checks": 15,
      "six_metaclass": 2,
      "six_unicode": 3,
      "sys_version_info": 25,
      "try_except_imports": 19,
      "builtins": 8
    }
  },
  "per_file_changes": [
    {
      "file": "mymodule.py",
      "removals": {
        "__future__": 3,
        "six_types": 5,
        "six_iteration": 2
      },
      "status": "completed"
    }
  ],
  "test_results": [
    {
      "batch": 1,
      "files": "1-10",
      "status": "PASS",
      "duration_seconds": 45
    }
  ]
}
```
