# Code Examples and Pattern Tables

**This file supports:** `/sessions/stoic-practical-faraday/mnt/code-translation-skills/skills/py2to3-dynamic-pattern-resolver/SKILL.md`

## Class Transformation Examples

### __metaclass__ Attribute

```python
# Python 2
class Foo(object):
    __metaclass__ = SomeMeta

# Python 3
class Foo(metaclass=SomeMeta):
    pass
```

### __nonzero__ → __bool__

```python
# Python 2
def __nonzero__(self):
    return len(self) > 0

# Python 3
def __bool__(self):
    return len(self) > 0
```

### __unicode__ → __str__ (with __str__ → __bytes__)

```python
# Python 2
class Foo:
    def __str__(self):
        return b"bytes"

    def __unicode__(self):
        return u"unicode"

# Python 3
class Foo:
    def __str__(self):
        return "unicode"

    def __bytes__(self):
        return b"bytes"
```

### __div__ → __truediv__ and __floordiv__

```python
# Python 2
def __div__(self, other):
    return Foo(self.x / other.x)

# Python 3
def __truediv__(self, other):
    return Foo(self.x / other.x)

def __floordiv__(self, other):
    return Foo(self.x // other.x)
```

### __getslice__, __setslice__, __delslice__ → slice protocol

```python
# Python 2
def __getslice__(self, i, j):
    return self.items[i:j]

# Python 3
def __getitem__(self, key):
    if isinstance(key, slice):
        return self.items[key]
    else:
        return self.items[key]
```

### __cmp__ → Rich Comparison Methods

```python
# Python 2
def __cmp__(self, other):
    if self.x < other.x:
        return -1
    elif self.x > other.x:
        return 1
    else:
        return 0

# Python 3 — Option A: Full comparison methods
def __lt__(self, other):
    return self.x < other.x

def __eq__(self, other):
    return self.x == other.x

# Python 3 — Option B: functools.total_ordering
from functools import total_ordering

@total_ordering
class Foo:
    def __eq__(self, other):
        return self.x == other.x

    def __lt__(self, other):
        return self.x < other.x
```

### __hash__ When __eq__ is Defined

```python
# Python 2
class Foo:
    def __eq__(self, other):
        return self.x == other.x
    # __hash__ inherited from object

# Python 3 — needs explicit __hash__
class Foo:
    def __eq__(self, other):
        return self.x == other.x

    def __hash__(self):
        return hash(self.x)
```

## Builtin Function Changes Examples

### map(), filter(), zip() Return Iterators

```python
# Python 2
result = map(f, seq)
x = result[0]  # indexing works, result is list

# Python 3
result = list(map(f, seq))
x = result[0]  # must wrap in list()
```

### dict.keys(), dict.values(), dict.items() Return Views

```python
# Python 2
keys = mydict.keys()
x = keys[0]  # indexing works, result is list

# Python 3
keys = list(mydict.keys())
x = keys[0]  # must wrap in list()
```

### sorted() and list.sort() with cmp= Parameter

```python
# Python 2
sorted(seq, cmp=my_cmp_func)

# Python 3
from functools import cmp_to_key
sorted(seq, key=cmp_to_key(my_cmp_func))
```

### reduce() Builtin Removed

```python
# Python 2
reduce(f, seq, init)

# Python 3
from functools import reduce
reduce(f, seq, init)
```

### apply() Removed

```python
# Python 2
apply(f, (a, b), {"x": 1})

# Python 3
f(a, b, x=1)
```

### buffer() → memoryview()

```python
# Python 2
buf = buffer(data, offset, size)

# Python 3
buf = memoryview(data)[offset:offset+size]
```

### cmp() Builtin Removed

```python
# Python 2
result = cmp(a, b)

# Python 3
result = (a > b) - (a < b)
```

### execfile() Removed

```python
# Python 2
execfile("script.py")

# Python 3
exec(open("script.py").read())
# Or with proper cleanup:
with open("script.py") as f:
    exec(f.read())
```

### reload() Moved to importlib

```python
# Python 2
reload(mymodule)

# Python 3
from importlib import reload
reload(mymodule)
```

## Integer Division Example

```python
# Python 2
x = 5 / 2  # = 2 (integer division)

# Python 3
x = 5 / 2  # = 2.5 (true division)
x = 5 // 2  # = 2 (floor division)

# Solution: Add to module top
from __future__ import division
# Then 5 / 2 = 2.5 in Py2, same as Py3
```

## exec Statement Edge Cases

```python
# Python 2
exec code in globals, locals

# Python 3
exec(code, globals, locals)
```

## Comparison Operators with Mixed Types

```python
# Python 2 — comparing int and str
if x < "hello":  # works in Py2 (type ordering)
    pass

# Python 3 — raises TypeError
# Fix: type-aware comparison
if isinstance(x, int) and isinstance("hello", int):
    result = x < int("hello")
else:
    result = False
```

## Dynamic Pattern Report JSON Example

```json
{
  "skill_name": "dynamic-pattern-resolver",
  "phase": 3,
  "timestamp": "2025-02-12T...",
  "patterns_found": {
    "metaclass": 3,
    "nonzero": 1,
    "__cmp__": 2,
    "map_filter_zip": 5,
    "dict_views": 4
  },
  "auto_fixed": 12,
  "manual_review": 3,
  "decisions": [
    {
      "file": "mymodule.py",
      "line": 42,
      "pattern": "__cmp__",
      "action": "auto_fix",
      "details": "Split into __eq__ and __lt__"
    }
  ]
}
```

## Pattern Detection Matrix

| Pattern | Type | Auto-fixable | Confidence | Notes |
|---------|------|--------------|------------|-------|
| `__metaclass__` | Class | YES | High | Direct rename in class signature |
| `__nonzero__` | Class | YES | High | Simple rename to `__bool__` |
| `__unicode__` | Class | YES (warn) | High | Requires code review for correctness |
| `__div__` | Class | PARTIAL | Medium | Split into `__truediv__`, but `__floordiv__` needs review |
| `__getslice__` | Class | YES | High | Convert to `__getitem__` with slice check |
| `__cmp__` | Class | CONDITIONAL | Medium | Extract logic, generate `__eq__` + `__lt__`, add `@total_ordering` |
| `__hash__` (missing) | Class | CONDITIONAL | Medium | Suggest implementation, requires review |
| `map()` result indexing | Builtin | CONDITIONAL | Medium | Auto-fix if indexed/len'd, leave if single iteration |
| `filter()` result | Builtin | CONDITIONAL | Medium | Same as map() |
| `zip()` result | Builtin | CONDITIONAL | Medium | Same as map() |
| `dict.keys()` indexing | Builtin | CONDITIONAL | Medium | Auto-fix if indexed, leave if used in for/in |
| `dict.items()` | Builtin | CONDITIONAL | Medium | Same as keys() |
| `sorted(cmp=...)` | Builtin | YES | High | Rewrite with `functools.cmp_to_key()` |
| `reduce()` | Builtin | YES | High | Add `from functools import reduce` |
| `apply()` | Builtin | YES | High | Expand into direct call with `*args/**kwargs` |
| `buffer()` | Builtin | CONDITIONAL | Medium | Simple → direct rename, with slicing → needs review |
| `cmp()` | Builtin | YES | High | Use `(a > b) - (a < b)` |
| `execfile()` | Builtin | YES | High | Rewrite as `exec(open(...).read())` |
| `reload()` | Builtin | YES | High | Add `from importlib import reload` |
| `exec` statement | Statement | YES | High | Convert to function call syntax |
| `/` with ints | Operator | CONDITIONAL | Medium | Phase 1 should add `from __future__ import division`, flag if missing |
| Mixed-type comparison | Operator | NO | Low | Requires human judgment |

## Workflow State Tracking

Per-file state after processing:

```json
{
  "file": "mymodule.py",
  "patterns_found": [
    {
      "line": 42,
      "pattern": "__cmp__",
      "status": "auto_fixed",
      "result": "Split into __eq__ and __lt__ with @total_ordering"
    },
    {
      "line": 105,
      "pattern": "map() indexing",
      "status": "auto_fixed",
      "result": "Wrapped in list()"
    },
    {
      "line": 230,
      "pattern": "mixed-type comparison",
      "status": "manual_review",
      "reason": "Cannot auto-fix comparison between str and int"
    }
  ]
}
```
