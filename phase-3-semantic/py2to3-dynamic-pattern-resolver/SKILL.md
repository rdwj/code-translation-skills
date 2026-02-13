---
name: py2to3-dynamic-pattern-resolver
description: >
  Resolve semantic Python 2→3 patterns that require code understanding to fix correctly.
  Trigger on metaclass, exec, eval, dynamic import, __cmp__, __nonzero__, __unicode__,
  __div__, integer division, map/filter/zip returning iterators, dict views, sorted
  cmp parameter, buffer, apply, reduce, __hash__, comparison operators, __getslice__,
  __setslice__, __delslice__, and other dynamic language features that changed between
  Python 2 and 3.
---

# Dynamic Pattern Resolver

Handle Python language features that changed semantically between Py2 and Py3, where
the Automated Converter (Skill 2.2) cannot determine the correct fix without understanding
code semantics. This skill patterns that require semantic analysis — not just syntax
transformation — to migrate correctly.

These are patterns that the regex-based Automated Converter skipped, or patterns that
need context-aware AST transformation to fix safely.

## When to Use

- When the Automated Converter marks files as needing semantic analysis
- After Phase 1 (print fix) and Phase 2 (imports) are complete
- When you need to resolve class transformation patterns (__metaclass__, __cmp__, etc.)
- When you need to fix iterator vs list issues (map/filter/zip)
- When you need to handle division operator changes intelligently
- When you need to audit dynamic features (eval, exec, getattr, etc.)

## Inputs

The user provides:
- **conversion_unit_path**: Path to a single Python file or directory of files
- **--target-version**: Python 3 version target (e.g., `3.9`, `3.11`)
- **--state-file**: JSON state file from previous phases (tracks decisions)
- **--output**: Directory to write fixed files and reports
- **--phase0-dir**: Path to Phase 0 discovery output (for risk context)
- **--dry-run**: Show what would be changed without modifying files
- **--auto-only**: Only auto-fix high-confidence patterns; skip ambiguous ones
- **--conversion-plan**: Path to conversion plan JSON (from skill 2.2)

## Outputs

All outputs go into the `--output` directory:

| File | Format | Purpose |
|------|--------|---------|
| Fixed source files | Python | Modified files with semantic patterns resolved |
| `dynamic-pattern-report.json` | JSON | Every pattern found, resolution method, and context |
| `manual-review-needed.json` | JSON | Ambiguous patterns requiring human decision |
| `dynamic-pattern-summary.md` | Markdown | Human-readable summary of changes |

## Pattern Categories & Transformation Rules

### 1. Class Transformation Patterns

#### __metaclass__ Attribute

**Pattern**: Class using old-style `__metaclass__` assignment.

```python
# Python 2
class Foo(object):
    __metaclass__ = SomeMeta
```

**Transformation**:
```python
# Python 3
class Foo(metaclass=SomeMeta):
    pass
```

Auto-fixable: **YES** (high confidence) — extract metaclass name and rewrite class signature.

#### __nonzero__ → __bool__

**Pattern**: Instance method `__nonzero__` determines truthiness.

```python
# Python 2
def __nonzero__(self):
    return len(self) > 0
```

**Transformation**:
```python
# Python 3
def __bool__(self):
    return len(self) > 0
```

Auto-fixable: **YES** (high confidence) — direct rename.

#### __unicode__ → __str__ (with __str__ → __bytes__)

**Pattern**: Class has both `__str__` (Py2 returns bytes) and `__unicode__` (Py2 returns unicode).

In Python 2:
- `__str__` returns bytes (str type in Py2)
- `__unicode__` returns unicode

In Python 3:
- `__str__` returns unicode (str type in Py3)
- No `__unicode__`
- `__bytes__` returns bytes (new in Py3)

**Transformation**:
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

Auto-fixable: **YES** (with warning) — but requires code review for correctness.

#### __div__ → __truediv__ and __floordiv__

**Pattern**: Custom division operator via `__div__`.

In Python 2: `__div__` handles both `/` operator (context-dependent).
In Python 3: `/` always true division (use `__truediv__`), `//` is floor division (use `__floordiv__`).

**Transformation**:
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

Auto-fixable: **PARTIAL** — can split `__div__` into `__truediv__`, but `__floordiv__` logic
needs semantic review (may not be intended to floor).

#### __getslice__, __setslice__, __delslice__ → __getitem__/__setitem__/__delitem__ with slice

**Pattern**: Old-style slice protocol using separate methods.

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

Auto-fixable: **YES** (high confidence) — but check for edge cases with negative indices
(behavior changed between Py2 and Py3).

#### __cmp__ → Rich Comparison Methods

**Pattern**: Single `__cmp__` method returning -1, 0, or 1.

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

Auto-fixable: **CONDITIONAL** — extract comparison logic and generate `__eq__` + `__lt__`,
then add `@functools.total_ordering` decorator for brevity. High confidence for simple cases.

#### __hash__ When __eq__ is Defined

**Pattern**: Custom `__eq__` without explicit `__hash__`.

In Python 2: objects with `__eq__` still have default `__hash__`.
In Python 3: objects with custom `__eq__` get `__hash__ = None` by default (unhashable).

**Transformation**:
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

Auto-fixable: **CONDITIONAL** — flag all cases where `__eq__` is defined without `__hash__`.
Suggest a generic `__hash__` implementation based on immutable attributes, but requires review.

### 2. Builtin Function Changes

#### map(), filter(), zip() Return Iterators

**Pattern**: Calling `map()`, `filter()`, or `zip()` and treating result as a list.

In Python 2: Return lists (can be indexed, len'd, iterated multiple times).
In Python 3: Return iterators (can only be iterated once; cannot be indexed or len'd).

**Transformation**:
```python
# Python 2
result = map(f, seq)
x = result[0]  # indexing

# Python 3
result = list(map(f, seq))
x = result[0]
```

Auto-fixable: **CONDITIONAL** — if the result is indexed, len'd, or iterated multiple times,
wrap in `list()`. If only iterated once, leave as-is.

Detection:
1. Find all `map()`, `filter()`, `zip()` calls.
2. Analyze usage of the result:
   - If indexed: `result[i]` → auto-fix with `list()`
   - If len'd: `len(result)` → auto-fix with `list()`
   - If looped over multiple times → auto-fix with `list()`
   - If only iterated once → leave as-is (low risk)

#### dict.keys(), dict.values(), dict.items() Return Views

**Pattern**: Calling dict view methods and treating result as a list.

In Python 2: Return lists (indexable, mutable operations possible).
In Python 3: Return views (not indexable; don't support in-place modifications).

**Transformation**:
```python
# Python 2
keys = mydict.keys()
x = keys[0]  # indexing

# Python 3
keys = list(mydict.keys())
x = keys[0]
```

Auto-fixable: **CONDITIONAL** — if the result is indexed, wrap in `list()`. If only used
in `for` loops or `in` checks, leave as-is.

#### sorted() and list.sort() with cmp= Parameter

**Pattern**: Using `sorted(cmp=my_cmp)` or `list.sort(cmp=...)`.

In Python 2: `cmp=` parameter for custom comparison.
In Python 3: Use `key=` with `functools.cmp_to_key()`.

**Transformation**:
```python
# Python 2
sorted(seq, cmp=my_cmp_func)

# Python 3
from functools import cmp_to_key
sorted(seq, key=cmp_to_key(my_cmp_func))
```

Auto-fixable: **YES** (high confidence) — systematic rewrite using `functools.cmp_to_key`.

#### reduce() Builtin Removed

**Pattern**: Calling `reduce()` without import.

In Python 2: Builtin.
In Python 3: Moved to `functools` module.

**Transformation**:
```python
# Python 2
reduce(f, seq, init)

# Python 3
from functools import reduce
reduce(f, seq, init)
```

Auto-fixable: **YES** (high confidence) — add import and keep call as-is.

#### apply() Removed

**Pattern**: Calling `apply(func, args, kwargs)`.

In Python 2: Builtin for unpacking args/kwargs.
In Python 3: Removed; use `func(*args, **kwargs)` directly.

**Transformation**:
```python
# Python 2
apply(f, (a, b), {"x": 1})

# Python 3
f(a, b, x=1)
```

Auto-fixable: **YES** (high confidence) — expand into direct call with `*args` and `**kwargs`.

#### buffer() → memoryview()

**Pattern**: Calling `buffer()` to create a memory view.

In Python 2: `buffer()` builtin.
In Python 3: Removed; use `memoryview()` instead.

**Transformation**:
```python
# Python 2
buf = buffer(data, offset, size)

# Python 3
buf = memoryview(data)[offset:offset+size]
```

Auto-fixable: **CONDITIONAL** — simple case (no slicing) is direct rename. With slicing,
needs semantic review for offset/size logic.

#### cmp() Builtin Removed

**Pattern**: Calling `cmp(a, b)` to compare two values.

In Python 2: Builtin.
In Python 3: Removed.

**Transformation**:
```python
# Python 2
result = cmp(a, b)

# Python 3
result = (a > b) - (a < b)
```

Auto-fixable: **YES** (high confidence) — use comparison operators to synthesize result.

#### execfile() Removed

**Pattern**: Calling `execfile(filename)` to execute a file.

In Python 2: Builtin.
In Python 3: Removed; use `exec(open(...).read())`.

**Transformation**:
```python
# Python 2
execfile("script.py")

# Python 3
exec(open("script.py").read())
# Or with proper cleanup:
with open("script.py") as f:
    exec(f.read())
```

Auto-fixable: **YES** (high confidence) — systematic rewrite.

#### reload() Moved to importlib

**Pattern**: Calling `reload(module)` to reload a module.

In Python 2: Builtin.
In Python 3: Moved to `importlib.reload()`.

**Transformation**:
```python
# Python 2
reload(mymodule)

# Python 3
from importlib import reload
reload(mymodule)
```

Auto-fixable: **YES** (high confidence) — add import and keep call as-is.

### 3. Integer Division

**Pattern**: Using `/` operator where both operands are integers.

In Python 2: `/` does integer division on int operands (e.g., `5 / 2 == 2`).
In Python 3: `/` always does true division (e.g., `5 / 2 == 2.5`).

**Detection**:
1. Scan all `/` binary operations.
2. Analyze operand types using AST:
   - If both are numeric literals (int, long) → flag for review.
   - If both are variables: check type hints, assignment history → uncertain, flag for review.
   - If one is a float → safe, no change needed.

**Transformation Options**:
- **Option A** (already done in Phase 1): `from __future__ import division` at module top.
  This makes Py2 code use true division like Py3.
  
- **Option B**: Replace `/` with `//` for explicit integer division.

Auto-fixable: **CONDITIONAL** — Phase 1 should have added `from __future__ import division`.
If not present, flag for decision: add future import or replace with `//`.

### 4. exec Statement Edge Cases

**Pattern**: `exec code in globals, locals` — old statement syntax.

In Python 2: Statement syntax, can unpack tuples for scopes.
In Python 3: Function syntax, must use positional args.

**Transformation**:
```python
# Python 2
exec code in globals, locals

# Python 3
exec(code, globals, locals)
```

Auto-fixable: **YES** (high confidence) — systematic rewrite to function call.

Note: Phase 2 (Skill 2.3) should have handled most `exec` cases. This skill catches
edge cases with tuple unpacking or missing parentheses.

### 5. Comparison Operators with Mixed Types

**Pattern**: Comparing incompatible types using `<`, `>`, `<=`, `>=`.

In Python 2: Allowed (objects sorted by type then value).
In Python 3: Raises `TypeError` (only `<`, `>`, etc. work within comparable types).

**Detection**:
1. Find all comparison operations with non-obvious types.
2. Flag for review (hard to auto-fix without semantic analysis).

**Common Fixes**:
```python
# Python 2 — comparing int and str
if x < "hello":  # works in Py2 (type ordering)

# Python 3 — raises TypeError
# Fix: type-aware comparison
if isinstance(x, int) and isinstance("hello", int):
    result = x < int("hello")
else:
    result = False
```

Auto-fixable: **NO** — requires human judgment on intended behavior.

## Workflow

### Step 1: Scan Files for Dynamic Patterns

```bash
python3 scripts/resolve_patterns.py <path> \
    --target-version 3.9 \
    --output <output_dir> \
    --dry-run
```

The script uses AST analysis to find all dynamic patterns:
1. Walk AST of each file.
2. Identify all pattern types (see categories above).
3. Classify each as auto-fixable or needs-review.
4. Generate context (surrounding code, usage analysis).

### Step 2: Auto-Fix High-Confidence Patterns

For patterns classified as auto-fixable:
1. Generate AST transformation.
2. Apply transformation to source.
3. Record in `dynamic-pattern-report.json`.

### Step 3: Flag Ambiguous Patterns

For patterns that need human decision:
1. Capture full context (function/class scope, surrounding code).
2. Record in `manual-review-needed.json` with explanation.
3. Suggest possible fixes.

### Step 4: Generate Reports

Run `scripts/generate_pattern_report.py` to produce human-readable markdown summary:

```bash
python3 scripts/generate_pattern_report.py <output_dir>
```

## Integration with State Tracker

The skill records all decisions in `--state-file` (JSON):

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

## Files Modified

This skill modifies source files in-place (or to --output directory):
- All patterns in target files are transformed
- Original files backed up to `{file}.py2` if desired
- All changes tracked in state file

## Notes & Limitations

- **Type inference**: Uses AST and heuristics; may have false positives on ambiguous code.
- **Dynamic code**: Cannot analyze code in strings (eval, exec'd code, etc.) — flagged for review.
- **Complex logic**: Patterns with intricate semantics (e.g., custom `__cmp__` with side effects)
  are flagged for human review.
- **Test coverage**: Recommend running tests after each skill to validate transformations.

