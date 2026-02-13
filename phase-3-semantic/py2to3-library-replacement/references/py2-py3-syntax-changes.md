# Python 2 → Python 3: Complete Syntax Changes Reference

## Document Purpose

This is a comprehensive catalog of ALL syntax differences between Python 2 and Python 3. It is designed to be consulted by:
- **Skill 0.1 (Codebase Analyzer)**: To identify all syntax constructs that need migration
- **Skill 2.2 (Automated Converter)**: To apply automatic transformations safely
- **Skill 3.1 (Semantic Validator)**: To understand which changes need behavioral verification

Each entry includes the exact syntax change, migration approach, risk level, auto-fixability, and common gotchas. This document should be the single source of truth for syntax migration patterns.

---

## Table of Contents

1. [Print Statement → Print Function](#1-print-statement--print-function)
2. [Exception Syntax Changes](#2-exception-syntax-changes)
3. [Integer Division Operator](#3-integer-division-operator)
4. [String and Bytes Literals](#4-string-and-bytes-literals)
5. [Octal Literals](#5-octal-literals)
6. [Long Integer Type](#6-long-integer-type)
7. [Backtick Repr Syntax](#7-backtick-repr-syntax)
8. [Not-Equal Operator](#8-not-equal-operator)
9. [Exec Statement → Function](#9-exec-statement--function)
10. [Dictionary Iterator Methods](#10-dictionary-iterator-methods)
11. [Map/Filter/Zip Return Types](#11-mapfilterzip-return-types)
12. [Range and Xrange](#12-range-and-xrange)
13. [Input and Raw_Input](#13-input-and-raw_input)
14. [Unicode and Str Types](#14-unicode-and-str-types)
15. [Has_Key → In Operator](#15-has_key--in-operator)
16. [Sort cmp Parameter](#16-sort-cmp-parameter)
17. [Relative Imports](#17-relative-imports)
18. [Metaclass Syntax](#18-metaclass-syntax)
19. [Super Calls](#19-super-calls)
20. [Tuple Parameter Unpacking](#20-tuple-parameter-unpacking)
21. [Class Definition Changes](#21-class-definition-changes)
22. [Magic Method Renames](#22-magic-method-renames)
23. [Reduce Function](#23-reduce-function)
24. [Apply Function](#24-apply-function)
25. [Buffer Type](#25-buffer-type)
26. [Execfile Function](#26-execfile-function)
27. [Reload Function](#27-reload-function)

---

## 1. Print Statement → Print Function

**Category**: I/O Syntax

**Description**: The most visible change in Python 3. `print` becomes a function requiring parentheses, enabling multiple arguments, sep/end parameters, and file redirection.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Basic print** | `print "hello"` | `print("hello")` |
| **Multiple items** | `print "a", "b", "c"` | `print("a", "b", "c")` |
| **Trailing comma** | `print "no newline",` | `print("no newline", end="")` |
| **File redirection** | `print >> sys.stderr, "err"` | `print("err", file=sys.stderr)` |
| **Separator** | Not supported | `print(a, b, sep=", ")` |
| **Flush** | Not available | `print(x, flush=True)` |

**Python 2 Examples**:
```python
# Basic print
print "Hello, World!"

# Multiple values (comma-separated)
print "Name:", name, "Age:", age

# No newline
print "Loading...",

# Print to stderr
print >> sys.stderr, "Error occurred"

# With multiple arguments
print "x=%d y=%d" % (x, y)
```

**Python 3 Examples**:
```python
# Basic print
print("Hello, World!")

# Multiple values (as arguments)
print("Name:", name, "Age:", age)

# No newline
print("Loading...", end="")

# Print to stderr
print("Error occurred", file=sys.stderr)

# With multiple arguments
print(f"x={x} y={y}")
```

**Risk Level**: Low — Nearly all print statements can be automatically converted.

**Auto-fixable by 2to3**: Yes, `fix_print` handles most cases automatically.

**Notes/Gotchas**:
- Parentheses around multiple arguments: `print (a, b)` in Py2 with intent to print two items becomes ambiguous — `(a, b)` is a tuple, printed as one item.
- `print >> sys.stderr` syntax is completely removed; requires function syntax.
- The `from __future__ import print_function` allows Python 2.6+ code to use print as function.
- Debugging: `print` statements can be globally converted even if the code mixes old and new styles.

---

## 2. Exception Syntax Changes

**Category**: Error Handling

**Description**: Exception handling syntax changes significantly. The `except X, e:` syntax is replaced with `except X as e:`. The `raise` statement handling also changes for re-raising and exception chaining.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Catch exception** | `except IOError, e:` | `except IOError as e:` |
| **Multiple types** | `except (TypeError, ValueError), e:` | `except (TypeError, ValueError) as e:` |
| **Bare raise** | `except: raise` | `except: raise` (same, re-raises) |
| **Raise string** | `raise "error"` | `raise TypeError("error")` |
| **Raise tuple** | `raise ValueError, "msg"` | `raise ValueError("msg")` |
| **Raise re-raise** | `except: raise` | `except: raise` (same) |
| **Exception chaining** | Not available | `raise ValueError() from e` |

**Python 2 Examples**:
```python
# Old syntax with comma
try:
    file = open("missing.txt")
except IOError, e:
    print "Error:", e

# Multiple exception types
try:
    value = int(input)
except (ValueError, IndexError), err:
    print "Bad input:", err

# Raise with string
raise ValueError, "Invalid value"

# Raise tuple form
raise IOError(2, "No such file")
```

**Python 3 Examples**:
```python
# New syntax with 'as'
try:
    file = open("missing.txt")
except IOError as e:
    print("Error:", e)

# Multiple exception types (syntax same, just 'as')
try:
    value = int(input)
except (ValueError, IndexError) as err:
    print("Bad input:", err)

# Always use exception constructor
raise ValueError("Invalid value")

# Constructor with args
raise IOError(2, "No such file")

# Exception chaining (Python 3 only)
try:
    do_something()
except ValueError as e:
    raise TypeError("Invalid type") from e
```

**Risk Level**: Low — Syntax change is mechanical and well-handled by 2to3.

**Auto-fixable by 2to3**: Yes, `fix_except` and `fix_raise` handle this automatically.

**Notes/Gotchas**:
- Bare `except:` clauses catch all exceptions (same in both versions). Use `except Exception:` to exclude SystemExit, KeyboardInterrupt.
- In Python 2, you could `raise "string"`, but this is never valid in Python 3 — must be an exception instance.
- Exception chaining with `from` is a Python 3 feature for preserving context; not available in Python 2.
- The variable `e` is automatically deleted after the except block in Python 3 to avoid circular references.
- Re-raising (`raise`) without arguments works identically in both versions.

---

## 3. Integer Division Operator

**Category**: Arithmetic Operators

**Description**: The `/` operator behavior changes fundamentally. In Python 2, integer division (`5 / 2 = 2`) uses truncation. In Python 3, `/` always returns float (`5 / 2 = 2.5`). Use `//` for floor division in both.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Integer / Integer** | `5 / 2` = 2 (int) | `5 / 2` = 2.5 (float) |
| **Float / Integer** | `5.0 / 2` = 2.5 (float) | `5.0 / 2` = 2.5 (float) |
| **Floor division** | `5 / 2` (implicit) | `5 // 2` = 2 (explicit) |
| **Modulo** | `5 % 2` = 1 (unchanged) | `5 % 2` = 1 (unchanged) |

**Python 2 Examples**:
```python
# Integer division truncates
result = 5 / 2  # 2
quotient = 10 / 3  # 3

# Mixed types promote to float
result = 5.0 / 2  # 2.5
result = 5 / 2.0  # 2.5

# Workaround for floor division (explicit)
result = 5 // 2  # 2
```

**Python 3 Examples**:
```python
# Integer division returns float
result = 5 / 2  # 2.5
quotient = 10 / 3  # 3.333...

# Floor division uses //
result = 5 // 2  # 2
quotient = 10 // 3  # 3

# Mixed types (same result as Py2)
result = 5.0 / 2  # 2.5
result = 5 / 2.0  # 2.5
```

**Risk Level**: High — This is a semantic change that affects calculations and can silently break logic.

**Auto-fixable by 2to3**: Partially. The `fix_division` fixer inserts `from __future__ import division` in Python 2 code, making it future-compatible. For migration, code must explicitly use `//` where floor division is intended.

**Notes/Gotchas**:
- This is one of the most dangerous changes because results silently differ without raising exceptions.
- Code that relies on integer truncation behavior MUST be audited. Look for patterns like `index = offset / stride`.
- The `//` operator exists in Python 2.2+ and works identically in both versions, making it the safe choice for floor division.
- Mixing int and float: both versions promote to float, but Py3 `/` still returns float even with two ints.
- Negative division: `-5 // 2` = -3 in both versions (floor division, not truncation).
- Tests: Any numerical assertions need careful review for rounding changes.

---

## 4. String and Bytes Literals

**Category**: Data Types

**Description**: Python 3 distinguishes text (str, uses Unicode) from bytes (bytes, raw data). All literals are text by default. Unicode literals require explicit `u""` in Python 2, but in Python 3 that's the default. Byte literals require explicit `b""`.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Plain string** | `"hello"` = bytes | `"hello"` = str (text) |
| **Unicode literal** | `u"hello"` | `u"hello"` (allowed for compatibility, same as str) |
| **Bytes literal** | `"bytes"` or `b"bytes"` | `b"bytes"` (explicit) |
| **Triple-quoted** | `"""text"""` = bytes | `"""text"""` = str (text) |
| **Encoding attribute** | `u"x".encode("utf-8")` | `"x".encode("utf-8")` |

**Python 2 Examples**:
```python
# Implicit bytes
message = "hello"  # bytes type
data = "x00x01x02"  # bytes (raw)

# Unicode explicit
name = u"François"  # unicode type
path = u"C:Users"  # unicode for safety

# Triple-quoted (bytes)
text = """Multi
line"""  # bytes

# Encoding
encoded = u"hello".encode("utf-8")  # bytes

# Raw bytes
binary = b"x89PNG"  # bytes, b prefix available in 2.6+
```

**Python 3 Examples**:
```python
# Text strings by default
message = "hello"  # str (text)
name = "François"  # str with Unicode support

# Bytes explicit
data = b"x00x01x02"  # bytes (raw)
binary = b"x89PNG"  # bytes

# u prefix allowed but redundant
name = u"François"  # still str, allowed for compat

# Encoding
encoded = "hello".encode("utf-8")  # bytes

# Decoding
text = b"hello".decode("utf-8")  # str
```

**Risk Level**: High — Fundamental type system change affecting all string/bytes handling.

**Auto-fixable by 2to3**: Partially. The `fix_unicode` fixer helps, but this requires semantic analysis. Simple string literals are often left as-is, causing issues. See py2-py3-semantic-changes.md for detailed type system discussion.

**Notes/Gotchas**:
- In Python 2, `str` is bytes; in Python 3, `str` is text. This is THE fundamental change.
- The `b""` prefix works in Python 2.6+ but creates `str` (bytes), not a distinct type.
- In Python 3, mixing str and bytes operations raises `TypeError` — no implicit conversions.
- File I/O: Opening in text mode returns str (text); binary mode returns bytes.
- The `from __future__ import unicode_literals` (Py2.6+) makes all literals unicode by default, useful for transition.
- Regex patterns: `re.compile("pattern")` in Py3 matches str; `re.compile(b"pattern")` matches bytes.
- JSON: `json.loads()` in Py2 accepts str (bytes); Py3 requires str (text). Bytes must decode first.

---

## 5. Octal Literals

**Category**: Number Literals

**Description**: Octal number notation changes. Python 2 uses leading zero (`0777`), which is confusing and conflicts with decimal. Python 3 uses `0o` prefix (`0o777`), aligning with hex (`0x`) and binary (`0b`).

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Octal literal** | `0755` | `0o755` |
| **File permissions** | `mode = 0755` | `mode = 0o755` |
| **Leading zero behavior** | `0` = 0, `00` = 0, `0777` = 511 | Leading zero (no octal) is syntax error |

**Python 2 Examples**:
```python
# Octal permissions
mode = 0755  # 493 in decimal (rwxr-xr-x)
mask = 0777  # 511 in decimal

# Confusing: leading zero
port = 0123  # 83 in decimal (octal!)
# Hard to spot bugs with similar-looking numbers
result = 0888  # SyntaxError in Py2! (8 is invalid octal digit)
```

**Python 3 Examples**:
```python
# Octal with 0o prefix
mode = 0o755  # 493 in decimal (rwxr-xr-x)
mask = 0o777  # 511 in decimal

# Clear intent with explicit prefix
port = 123  # 123 in decimal (no octal)

# Hex and binary also use prefixes
hex_val = 0xFF  # 255
bin_val = 0b1010  # 10
oct_val = 0o12  # 10
```

**Risk Level**: Low — Syntax change is mechanical and well-caught by parsers.

**Auto-fixable by 2to3**: Yes, `fix_octal` automatically converts `0NNN` to `0oNNN`.

**Notes/Gotchas**:
- Invalid octal digits (8, 9) in Python 2 produce `SyntaxError`. If code runs in Py2, it won't have this issue.
- Strings with octal escapes are unaffected: `"\777"` is still valid in both (octal escape sequence).
- Leading zeros on decimals: `0123` in Py2 is octal; `0123` in Py3 is a syntax error. Use `123`.
- File permissions: Must update all `0NNN` patterns to `0oNNN`, especially in `os.chmod()`, `os.umask()`.

---

## 6. Long Integer Type

**Category**: Number Types

**Description**: Python 2 has separate `int` and `long` types. Large integers automatically promote to `long`. Python 3 unifies them into a single `int` type that can be arbitrarily large. The `L` suffix is removed.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Integer type** | `type(5)` = int | `type(5)` = int |
| **Large integer** | `type(999999999999999999999)` = long | `type(999999999999999999999)` = int |
| **Long literal** | `5L` or `5l` | `5` (no suffix needed) |
| **Long constructor** | `long(x)` | `int(x)` (always) |

**Python 2 Examples**:
```python
# Small integers stay int
num = 5  # type: int

# Large integers auto-promote to long
big = 999999999999999999999  # type: long
huge = 5L  # Explicitly long

# Long operations
result = 2L ** 100

# Conversion
val = long("123456789012345678901234567890")
```

**Python 3 Examples**:
```python
# All integers are int type
num = 5  # type: int
big = 999999999999999999999  # type: int (automatic large precision)

# No L suffix
huge = 5

# Large operations work seamlessly
result = 2 ** 100

# Just use int()
val = int("123456789012345678901234567890")
```

**Risk Level**: Low — Type unification is transparent for most code.

**Auto-fixable by 2to3**: Yes, `fix_long` removes `L`/`l` suffixes automatically. The `long()` function is not directly handled; code must explicitly use `int()`.

**Notes/Gotchas**:
- Code checking `type(x) == long` will fail in Python 3 (no `long` type). Use `isinstance(x, int)` instead.
- Metaclass usage: `long` is no longer a valid type. Code like `__bases__ = (long,)` fails.
- Division: In Python 2, `1L / 2` uses long division (returns `0L`). In Py3, `1 / 2` returns `0.5` (float division). See integer division section.
- Hex strings: `0xFFFFFFFFFFL` in Py2 becomes `0xFFFFFFFFFF` in Py3.
- Databases/pickling: Pickled long values from Py2 unpickle as int in Py3 (protocol-dependent).

---

## 7. Backtick Repr Syntax

**Category**: Object Representation

**Description**: Python 2 has a backtick operator (`` `x` ``) as shorthand for `repr(x)`. Python 3 removes this syntax entirely. Always use the `repr()` function instead.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Repr syntax** | `` `value` `` | `repr(value)` |
| **In f-strings** | Not available | `f"{value!r}"` |
| **Debugging output** | `` print "x=" + `x` `` | `print("x=" + repr(x))` |

**Python 2 Examples**:
```python
# Backtick for repr
value = 42
print "Value is " + `value`  # "Value is 42"

# In string formatting
name = "Alice"
msg = "Name: " + `name`  # "Name: 'Alice'"

# Backticks preserve representation
data = [1, 2, 3]
debug = "data=" + `data`  # "data=[1, 2, 3]"
```

**Python 3 Examples**:
```python
# Use repr() function
value = 42
print("Value is " + repr(value))  # "Value is 42"

# In string formatting
name = "Alice"
msg = "Name: " + repr(name)  # "Name: 'Alice'"

# f-string with !r conversion
data = [1, 2, 3]
debug = f"data={data!r}"  # "data=[1, 2, 3]"

# Simple str() vs repr()
print(f"Value: {value}")  # str representation
print(f"Value: {value!r}")  # repr representation
```

**Risk Level**: Low — Simple text replacement.

**Auto-fixable by 2to3**: Yes, `fix_repr` converts backticks to `repr()` calls.

**Notes/Gotchas**:
- Backticks are invalid syntax in Python 3 — causes immediate `SyntaxError`.
- Readability: `repr(x)` is clearer than `` `x` `` for modern Python developers.
- f-strings (Py3.6+): `f"{x!r}"` is the modern replacement for debugging.
- Nested backticks were occasionally used: `` `[`x`]` `` becomes `repr([repr(x)])`.

---

## 8. Not-Equal Operator

**Category**: Comparison Operators

**Description**: Python 2 allows both `!=` and `<>` for not-equal comparison. Python 3 removes the `<>` operator. Always use `!=`.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Not equal** | `x != y` or `x <> y` | `x != y` |
| **Preferred** | `!=` is preferred even in Py2 | `!=` (only option) |

**Python 2 Examples**:
```python
# Both are valid
if x != y:
    pass

if x <> y:  # Also valid, less common
    pass

# Less readable
while count <> 10:
    count += 1
```

**Python 3 Examples**:
```python
# Only != is valid
if x != y:
    pass

# <> is a syntax error
if x <> y:  # SyntaxError!
    pass
```

**Risk Level**: Very Low — Easy to identify and replace.

**Auto-fixable by 2to3**: Yes, `fix_ne` converts `<>` to `!=`.

**Notes/Gotchas**:
- The `<>` operator is rare in modern code but may appear in legacy codebases.
- Simple search-and-replace: `<>` → `!=`.

---

## 9. Exec Statement → Function

**Category**: Code Execution

**Description**: `exec` changes from a statement to a function. In Python 2, `exec` is a statement like `print`. In Python 3, it's a regular function requiring parentheses.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Basic exec** | `exec code` | `exec(code)` |
| **With globals** | `exec code in globals()` | `exec(code, globals())` |
| **With locals** | `exec code in globals, locals` | `exec(code, globals, locals)` |

**Python 2 Examples**:
```python
# Simple exec
code = "x = 5"
exec code

# With namespace
code = "result = x * 2"
namespace = {'x': 10}
exec code in namespace
print namespace['result']  # 20

# With globals and locals
exec code in globals(), locals()
```

**Python 3 Examples**:
```python
# Function syntax
code = "x = 5"
exec(code)

# With namespace
code = "result = x * 2"
namespace = {'x': 10}
exec(code, namespace)
print(namespace['result'])  # 20

# With globals and locals
exec(code, globals(), locals())
```

**Risk Level**: Medium — Requires parentheses and namespace syntax adjustment.

**Auto-fixable by 2to3**: Yes, `fix_exec` converts statements to function calls.

**Notes/Gotchas**:
- Namespaces: In Py2, `exec code in ns` mutates `ns`. In Py3, `exec(code, ns)` does the same.
- Default namespace: `exec(code)` in Py3 uses current scope; be explicit with `globals()`/`locals()` for clarity.
- Security: `exec()` with untrusted input is dangerous. Use `ast.literal_eval()` for safer parsing.
- Return values: Neither `exec` nor `exec()` return anything meaningful.

---

## 10. Dictionary Iterator Methods

**Category**: Collection Methods

**Description**: Dictionary methods `.iteritems()`, `.itervalues()`, `.iterkeys()` return iterators in Python 2. These methods are removed in Python 3. Instead, `.items()`, `.values()`, `.keys()` return view objects (which are iterable but not lists). Old `.items()` behavior (returning lists) is gone.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Iterate items** | `.iteritems()` → iterator | `.items()` → view (iterable) |
| **Iterate keys** | `.iterkeys()` → iterator | `.keys()` → view (iterable) |
| **Iterate values** | `.itervalues()` → iterator | `.values()` → view (iterable) |
| **Get list** | `.items()` → list | `list(.items())` → list |
| **Indexing** | `d.keys()[0]` → key | `list(d.keys())[0]` → key |

**Python 2 Examples**:
```python
# Dictionary methods return lists
d = {'a': 1, 'b': 2, 'c': 3}

# Old behavior: returns lists
keys = d.keys()  # ['a', 'b', 'c'] - list
values = d.values()  # [1, 2, 3] - list
items = d.items()  # [('a', 1), ('b', 2), ('c', 3)] - list

# Can index directly
first_key = d.keys()[0]  # 'a'
first_value = d.values()[0]  # 1

# For iteration, use iterators to save memory
for k, v in d.iteritems():
    print k, v

for k in d.iterkeys():
    print k

for v in d.itervalues():
    print v
```

**Python 3 Examples**:
```python
# Dictionary methods return views (not lists)
d = {'a': 1, 'b': 2, 'c': 3}

# New behavior: returns views
keys = d.keys()  # dict_keys(['a', 'b', 'c']) - view
values = d.values()  # dict_values([1, 2, 3]) - view
items = d.items()  # dict_items([('a', 1), ('b', 2), ('c', 3)]) - view

# Views are iterable but not indexable
first_key = list(d.keys())[0]  # 'a'
first_value = list(d.values())[0]  # 1

# Iteration (views are iterable)
for k, v in d.items():
    print(k, v)

for k in d.keys():
    print(k)

for v in d.values():
    print(v)

# Convert to list when needed
keys_list = list(d.keys())
values_list = list(d.values())
items_list = list(d.items())
```

**Risk Level**: Medium — Views are iterable, so simple loops work. But indexing and method calls expecting lists fail.

**Auto-fixable by 2to3**: Partially. The `fix_dict` fixer converts `.iteritems()` → `.items()`, `.iterkeys()` → `.keys()`, `.itervalues()` → `.values()`. But it doesn't add `list()` calls where indexing is needed.

**Notes/Gotchas**:
- Views are dynamic: if dict changes, view reflects changes (unlike lists).
- Dictionary size changes during iteration cause `RuntimeError`.
- Views support operators: `d.keys() & other_dict.keys()` (set-like operations).
- Membership test: `'a' in d.keys()` works but `'a' in d` is faster.
- Unpacking: `keys, values = zip(*d.items())` still works (views are iterable).
- Testing: Code checking `len(d.keys())` works (views have `__len__`), but indexing fails.

---

## 11. Map/Filter/Zip Return Types

**Category**: Built-in Functions

**Description**: `map()`, `filter()`, and `zip()` return lists in Python 2 but return iterators in Python 3. This is for memory efficiency with large sequences.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **map()** | Returns list | Returns iterator |
| **filter()** | Returns list | Returns iterator |
| **zip()** | Returns list | Returns iterator |
| **Type** | `list` | `map` / `filter` / `zip` (iterable) |
| **Indexing** | `map(f, x)[0]` works | `list(map(f, x))[0]` required |
| **Length** | `len(map(...))` works | No `len()`; count with `sum(1...)` |

**Python 2 Examples**:
```python
# All return lists
numbers = [1, 2, 3, 4, 5]

# map() returns list
doubled = map(lambda x: x * 2, numbers)  # [2, 4, 6, 8, 10]
first = doubled[0]  # 2 (indexing works)

# filter() returns list
evens = filter(lambda x: x % 2 == 0, numbers)  # [2, 4]
length = len(evens)  # 2

# zip() returns list
x = [1, 2, 3]
y = ['a', 'b', 'c']
pairs = zip(x, y)  # [(1, 'a'), (2, 'b'), (3, 'c')]
first_pair = pairs[0]  # (1, 'a')
```

**Python 3 Examples**:
```python
# All return iterators
numbers = [1, 2, 3, 4, 5]

# map() returns iterator
doubled = map(lambda x: x * 2, numbers)  # <map object>
doubled_list = list(doubled)  # [2, 4, 6, 8, 10]

# Convert to list if indexing needed
first = list(map(lambda x: x * 2, numbers))[0]  # 2

# filter() returns iterator
evens = filter(lambda x: x % 2 == 0, numbers)  # <filter object>
evens_list = list(evens)  # [2, 4]

# zip() returns iterator
x = [1, 2, 3]
y = ['a', 'b', 'c']
pairs = zip(x, y)  # <zip object>
pairs_list = list(pairs)  # [(1, 'a'), (2, 'b'), (3, 'c')]

# For single iteration, don't convert
for pair in zip(x, y):
    print(pair)
```

**Risk Level**: Medium — Code that indexes or uses `len()` fails. Most iteration code works unchanged.

**Auto-fixable by 2to3**: Partially. The `fix_map`, `fix_filter`, `fix_zip` fixers wrap calls with `list()` when the result is assigned, but this is overly conservative. Manual review is needed.

**Notes/Gotchas**:
- **Performance**: Wrapping with `list()` defeats the purpose. Use iterators when possible.
- **Memory**: Py3 approach is better for large datasets; Py2 approach loads everything into memory.
- **Chaining**: `map(f, map(g, x))` creates nested iterators; both evaluated lazily.
- **Indexing**: `.map(...)[0]` is a common pattern that must change to `next(map(...))` or `list(...)[0]`.
- **Multiple passes**: `iter = map(...); print(len(iter))` fails (no `len()`). Use `list()` only if needed.
- **Exhaustion**: Iterators are exhausted after one pass: `x = map(...); list(x); list(x)` — second list is empty.

---

## 12. Range and Xrange

**Category**: Iteration

**Description**: `range()` returns a list in Python 2 and an iterator in Python 3. `xrange()` (memory-efficient range) is removed in Python 3; its behavior becomes the default for `range()`.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **range()** | Returns list | Returns range object (iterable) |
| **xrange()** | Memory-efficient iterator | Removed, use range() |
| **Indexing** | `range(10)[5]` → 5 | `range(10)[5]` → 5 (still works) |
| **len()** | `len(range(10))` → 10 | `len(range(10))` → 10 (still works) |
| **Slicing** | Works on lists | Works on range objects (Py3.2+) |
| **Type check** | `type(range(10)) == list` | `type(range(10)) == range` |

**Python 2 Examples**:
```python
# range() returns list (all in memory)
nums = range(10)  # [0, 1, 2, 3, 4, 5, 6, 7, 8, 9] - list
first = nums[0]  # 0 (indexing works)

# xrange() memory-efficient (for large ranges)
for i in xrange(1000000):
    process(i)  # Only one value in memory at a time

# Nested iteration
for i in range(10):
    for j in range(10):
        print i, j

# Creating large lists
big_list = range(1000000)  # Memory-intensive in Py2
```

**Python 3 Examples**:
```python
# range() returns range object (lazy)
nums = range(10)  # range(0, 10) - NOT a list
first = nums[0]  # 0 (indexing still works!)

# No xrange; range is now lazy
for i in range(1000000):
    process(i)  # Memory-efficient

# Iteration same as Py2
for i in range(10):
    for j in range(10):
        print(i, j)

# Convert to list if needed
nums_list = list(range(10))  # [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

# range objects support indexing and len() natively
print(range(10)[5])  # 5
print(len(range(10)))  # 10
```

**Risk Level**: Low — `range()` and `xrange()` work similarly in iteration contexts.

**Auto-fixable by 2to3**: Yes, `fix_xrange` converts `xrange()` → `range()`. For Py2 compatibility, use `from builtins import range` (via `future` package) or create a compatibility shim.

**Notes/Gotchas**:
- **Indexing still works**: Unlike `map()`/`filter()`, range objects support indexing and `len()` in Py3.
- **Type checks**: Code checking `type(x) == list` for range results will fail.
- **Memory**: Py2's `range(1000000)` allocates huge lists; Py3's lazy range is better.
- **Slicing**: `range(10)[2:5]` returns a list in Py2, range object in Py3.
- **float range**: Use `numpy.arange()` or list comprehension for float ranges (neither supports floats).
- **Step parameter**: `range(0, 10, 2)` works identically in both versions.
- **Backwards compat**: If code must support both Py2 and Py3, use `from builtins import range` (from `future` package).

---

## 13. Input and Raw_Input

**Category**: I/O Functions

**Description**: Python 2 has `input()` (evaluates input as Python code — DANGEROUS) and `raw_input()` (reads string safely). Python 3 removes both; `input()` becomes safe (like Py2's `raw_input()`). The unsafe `input()` is removed.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Read string** | `raw_input()` | `input()` |
| **Evaluate input** | `input()` (DANGEROUS) | Removed, use `eval()` explicitly |
| **Safety** | `raw_input()` preferred | `input()` safe by default |

**Python 2 Examples**:
```python
# Raw input (safe - returns string)
name = raw_input("Enter name: ")  # Always returns str

# Dangerous input (evaluates as Python code!)
data = input("Enter value: ")  # If user enters "5", gets int 5
# If user enters "__import__('os').system('rm -rf /')", disaster!

# Workaround: wrap input() with eval/int conversions
age = int(raw_input("Enter age: "))  # Safe: string to int
```

**Python 3 Examples**:
```python
# Safe input (no evaluation)
name = input("Enter name: ")  # Always returns str

# To evaluate, use explicit eval() (still dangerous with untrusted input!)
data = eval(input("Enter value: "))  # Explicitly evaluate
age = int(input("Enter age: "))  # Convert string to int safely

# For JSON or structured data
import json
data = json.loads(input("Enter JSON: "))  # Parse JSON safely
```

**Risk Level**: Low → Medium depending on code. If code uses `input()`, danger!

**Auto-fixable by 2to3**: Yes, `fix_input` converts `raw_input()` → `input()`. But `input()` calls require manual review to determine if evaluation is needed.

**Notes/Gotchas**:
- **Dangerous code**: Py2's `input()` is a security nightmare. Search codebase for `input()` (not `raw_input()`).
- **Conversion pattern**: `int(input(...))` converts input string to int, common pattern.
- **Explicit eval**: `eval(input(...))` in Py3 is explicit but dangerous. Use `ast.literal_eval()` for safer evaluation of literals.
- **Unicode**: `raw_input()` in Py2 returns `str` (bytes); in Py3, `input()` returns `str` (text).
- **Testing**: Mock `input()` function for unit tests to avoid actual user input.

---

## 14. Unicode and Str Types

**Category**: String Types

**Description**: Python 2 has two string types: `str` (bytes) and `unicode` (text). Python 3 unifies to single `str` (always text). Python 2's `str` becomes `bytes` in Py3.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Text type** | `unicode` | `str` |
| **Bytes type** | `str` | `bytes` |
| **Type of "x"** | `str` | `str` (text) |
| **Type of u"x"** | `unicode` | `str` (text, u prefix optional) |
| **Type of b"x"** | `str` (or `bytes` alias) | `bytes` |
| **unicode() func** | Convert to unicode | Removed, use `str()` |
| **basestring type** | Parent of str and unicode | Removed, use `str` |

**Python 2 Examples**:
```python
# Bytes string
text = "hello"  # type: str (bytes)
data = str([1, 2, 3])  # "[1, 2, 3]" - bytes

# Unicode string
name = u"François"  # type: unicode
msg = unicode(123)  # u"123" - unicode

# Type checking
if isinstance(x, basestring):  # Match both str and unicode
    process(x)

# Encoding/decoding
encoded = u"hello".encode("utf-8")  # bytes
decoded = "hello".decode("utf-8")  # unicode

# Mixing (implicit conversions, often wrong)
result = "x" + u"y"  # Tries to decode "x" as ASCII -> u"xy"
```

**Python 3 Examples**:
```python
# Text string (always)
text = "hello"  # type: str (text)
name = "François"  # type: str (text, Unicode support built-in)

# Bytes explicit
data = b"hello"  # type: bytes
encoded = "hello".encode("utf-8")  # bytes

# Type checking
if isinstance(x, str):  # Only str type
    process(x)

# Encoding/decoding
encoded = "hello".encode("utf-8")  # bytes
decoded = b"hello".decode("utf-8")  # str

# Mixing (TypeError)
result = "x" + b"y"  # TypeError! Can't mix str and bytes
```

**Risk Level**: High — Fundamental type system change.

**Auto-fixable by 2to3**: Partially. See py2-py3-semantic-changes.md for detailed discussion.

**Notes/Gotchas**:
- **basestring**: Used for type-checking; remove or replace with `str` in Py3.
- **unicode()**: Remove or replace with `str()`.
- **Implicit conversions**: Gone in Py3. Code relying on `str` + `unicode` auto-conversion fails.
- **File I/O**: Text mode returns `str` (text); binary mode returns `bytes`.
- **Databases**: Libraries like `sqlite3` return `str` (text) by default in Py3; may need decoding in binary contexts.
- **Pickle/JSON**: Interchange formats affected; see serialization-migration.md.

---

## 15. Has_Key → In Operator

**Category**: Dictionary Methods

**Description**: Dictionary `.has_key()` method is removed in Python 3. Use the `in` operator instead.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Check key exists** | `d.has_key("x")` | `"x" in d` |
| **Preferred in Py2** | `"x" in d` preferred | `"x" in d` (only option) |

**Python 2 Examples**:
```python
d = {'a': 1, 'b': 2}

# Old method
if d.has_key('a'):
    print d['a']

# Preferred even in Py2
if 'a' in d:
    print d['a']

# has_key returns boolean
result = d.has_key('c')  # False
```

**Python 3 Examples**:
```python
d = {'a': 1, 'b': 2}

# In operator only
if 'a' in d:
    print(d['a'])

# Membership testing
exists = 'c' in d  # False
```

**Risk Level**: Very Low — Simple replacement.

**Auto-fixable by 2to3**: Yes, `fix_has_key` converts `.has_key(x)` → `x in dict`.

**Notes/Gotchas**:
- `.has_key()` is rare in modern Py2 code; `in` operator is preferred.
- Logical negation: `not d.has_key('x')` → `'x' not in d` (more readable).

---

## 16. Sort cmp Parameter

**Category**: Sorting

**Description**: The `cmp` parameter for `sort()` and `sorted()` is removed in Python 3. Use a `key` parameter instead, optionally with `functools.cmp_to_key()` for complex comparisons.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Sort with cmp** | `list.sort(cmp=fn)` | Removed |
| **Sort with key** | `list.sort(key=fn)` | `list.sort(key=fn)` (preferred) |
| **Convert cmp** | N/A | `from functools import cmp_to_key` |
| **Descending** | `sort(cmp=..., reverse=True)` | `sort(key=..., reverse=True)` |

**Python 2 Examples**:
```python
# Using cmp function
def compare(a, b):
    if a < b:
        return -1
    elif a > b:
        return 1
    else:
        return 0

nums = [3, 1, 4, 1, 5, 9, 2, 6]
nums.sort(cmp=compare)  # [1, 1, 2, 3, 4, 5, 6, 9]

# Built-in cmp
numbers = [3, 1, 2]
numbers.sort(cmp=cmp)  # Sorted ascending

# Reverse with cmp
numbers.sort(cmp=compare, reverse=True)

# With sorted()
sorted(nums, cmp=compare)
```

**Python 3 Examples**:
```python
# Using key function (simpler, faster)
nums = [3, 1, 4, 1, 5, 9, 2, 6]
nums.sort(key=lambda x: x)  # [1, 1, 2, 3, 4, 5, 6, 9]

# Descending with key
nums.sort(key=lambda x: -x)  # [9, 6, 5, 4, 3, 2, 1, 1]
# Or use reverse parameter
nums.sort(reverse=True)  # [9, 6, 5, 4, 3, 2, 1, 1]

# Complex comparisons with cmp_to_key
from functools import cmp_to_key

def compare(a, b):
    if a < b:
        return -1
    elif a > b:
        return 1
    else:
        return 0

nums.sort(key=cmp_to_key(compare))

# With sorted()
sorted(nums, key=cmp_to_key(compare))
```

**Risk Level**: Medium — Requires logic refactoring, not just syntax.

**Auto-fixable by 2to3**: Partially. Complex `cmp` functions need manual conversion to `key` functions.

**Notes/Gotchas**:
- **Key is better**: `key` parameter is simpler, faster, and more Pythonic.
- **Custom objects**: For custom comparison, define `__lt__`, `__le__`, etc., or use `@functools.total_ordering` decorator.
- **Multiple keys**: `sort(key=lambda x: (x.field1, x.field2))` sorts by multiple fields.
- **Cmp to key conversion**: `functools.cmp_to_key()` wraps cmp functions for compatibility.
- **Performance**: `key` functions are called once per element; cmp functions called multiple times.

---

## 17. Relative Imports

**Category**: Module Imports

**Description**: Implicit relative imports are removed in Python 3. All relative imports must be explicit using dot notation (`.module`, `..module`, etc.).

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Implicit relative** | `import module` (in package) | Always absolute |
| **Explicit relative** | `from . import module` (works) | `from . import module` (required) |
| **Parent package** | Not common | `from .. import module` (explicit) |

**Python 2 Examples**:
```python
# In mypackage/submodule.py
# Implicit relative import (confusing!)
import utils  # Is this mypackage.utils or utils elsewhere?

# Works if mypackage.utils exists, but ambiguous
from other import func  # Is this mypackage.other or other?

# Explicit relative (clear, preferred in Py2)
from . import utils  # Current package
from . import other
from .. import parent_module  # Parent package
```

**Python 3 Examples**:
```python
# In mypackage/submodule.py
# Implicit import always absolute
import utils  # Absolute import (not from mypackage!)

# Explicit relative imports (REQUIRED in Py3)
from . import utils  # Same package
from .other import func  # Same package, specific import
from .. import parent_module  # Parent package
from ..sibling import func  # Sibling package

# Absolute imports (clear)
import mypackage.utils  # Always works
```

**Risk Level**: Medium — Changes module resolution; can break imports if not careful.

**Auto-fixable by 2to3**: Partially. The `fix_import` fixer can help but requires understanding the package structure.

**Notes/Gotchas**:
- **Ambiguity**: Py2's implicit imports are ambiguous; Py3 removes the ambiguity.
- **Circular imports**: Explicit relative imports can help avoid circular dependency issues.
- **__future__ import**: `from __future__ import absolute_import` in Py2.5+ enforces Py3 behavior.
- **Top-level execution**: Module executed as script (`python mypackage/submodule.py`) may have import issues; use `-m` flag instead (`python -m mypackage.submodule`).
- **Package structure**: Ensure all packages have `__init__.py` files in Python 3.

---

## 18. Metaclass Syntax

**Category**: Class Definition

**Description**: Metaclass syntax changes significantly. Python 2 uses a class variable `__metaclass__`; Python 3 uses a keyword argument in the class definition.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Set metaclass** | `__metaclass__ = Meta` | `class X(metaclass=Meta):` |
| **With base classes** | `class X(Base): __metaclass__ = Meta` | `class X(Base, metaclass=Meta):` |
| **Nested syntax** | Different for old-style/new-style | Consistent |

**Python 2 Examples**:
```python
# Define metaclass
class Meta(type):
    def __new__(cls, name, bases, dct):
        print "Creating class", name
        return super(Meta, cls).__new__(cls, name, bases, dct)

# Use metaclass
class MyClass(object):
    __metaclass__ = Meta

# With base classes
class MyClass(SomeBase):
    __metaclass__ = Meta

# Old-style classes (no object inheritance)
class OldStyle:
    __metaclass__ = Meta  # Different behavior
```

**Python 3 Examples**:
```python
# Define metaclass (same in both versions)
class Meta(type):
    def __new__(cls, name, bases, dct):
        print(f"Creating class {name}")
        return super().__new__(cls, name, bases, dct)

# Use metaclass with keyword
class MyClass(metaclass=Meta):
    pass

# With base classes
class MyClass(SomeBase, metaclass=Meta):
    pass

# All classes are new-style (inherit from object implicitly)
```

**Risk Level**: Medium — Metaclass changes require understanding Python's class creation.

**Auto-fixable by 2to3**: Yes, `fix_metaclass` converts Py2 syntax to Py3. However, understanding the metaclass behavior is critical.

**Notes/Gotchas**:
- **Old-style classes**: Py2's old-style classes (no `object` inheritance) behave differently; Py3 has only new-style.
- **Metaclass parameters**: Parameters passed to metaclass differ slightly between Py2 and Py3.
- **Multiple inheritance**: Metaclass resolution can be complex with multiple base classes.
- **Compatibility**: Use `six.with_metaclass()` or `future.utils.with_metaclass()` for Py2/3 compatibility.

---

## 19. Super Calls

**Category**: Object-Oriented Programming

**Description**: `super()` simplified in Python 3. Python 2 requires explicit arguments (`super(ClassName, self)`); Python 3 infers them automatically.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Super basic** | `super(ClassName, self)` | `super()` |
| **Super __init__** | `super(ClassName, self).__init__()` | `super().__init__()` |
| **Works in Py2** | Need to pass args | N/A |

**Python 2 Examples**:
```python
class Base(object):
    def __init__(self, x):
        self.x = x

class Child(Base):
    def __init__(self, x, y):
        super(Child, self).__init__(x)
        self.y = y
    
    def method(self):
        # Must pass class and self
        result = super(Child, self).method()
        return result

# Multiple inheritance
class A(object):
    def greet(self):
        return "A"

class B(A):
    def greet(self):
        return super(B, self).greet() + " + B"

class C(A):
    def greet(self):
        return super(C, self).greet() + " + C"

class D(B, C):
    def greet(self):
        return super(D, self).greet() + " + D"
```

**Python 3 Examples**:
```python
class Base:
    def __init__(self, x):
        self.x = x

class Child(Base):
    def __init__(self, x, y):
        super().__init__(x)  # No args!
        self.y = y
    
    def method(self):
        result = super().method()  # Cleaner
        return result

# Multiple inheritance (MRO same, syntax simpler)
class A:
    def greet(self):
        return "A"

class B(A):
    def greet(self):
        return super().greet() + " + B"

class C(A):
    def greet(self):
        return super().greet() + " + C"

class D(B, C):
    def greet(self):
        return super().greet() + " + D"
```

**Risk Level**: Low — Mechanical replacement in most cases.

**Auto-fixable by 2to3**: Yes, `fix_super` converts `super(ClassName, self)` → `super()`.

**Notes/Gotchas**:
- **Inside class only**: `super()` without args only works inside class methods. Outside, pass explicit class/instance.
- **Classmethods**: In classmethods, `super()` still works (uses `cls` instead of `self`).
- **Staticmethods**: `super()` doesn't work in staticmethods; avoid super there.
- **Multiple inheritance**: `super()` respects MRO (Method Resolution Order); same in both versions.
- **Compatibility**: For Py2/3 support, explicitly use `super(ClassName, self)` in Py2-compatible code.

---

## 20. Tuple Parameter Unpacking

**Category**: Function Parameters

**Description**: Python 2 allows unpacking tuple parameters in function definitions. Python 3 removes this syntax; arguments must be explicitly unpacked in function body.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Tuple parameter** | `def f((a, b)):` | Not allowed |
| **List parameter** | `def f([a, b]):` | Not allowed |
| **Workaround** | Extract in body | Extract in body |

**Python 2 Examples**:
```python
# Tuple unpacking in parameters
def process((x, y)):
    return x + y

process((1, 2))  # 3

# List unpacking in parameters
def handle([first, second]):
    print first, second

handle([10, 20])  # 10 20

# Nested unpacking
def nested((a, (b, c))):
    return a + b + c

nested((1, (2, 3)))  # 6
```

**Python 3 Examples**:
```python
# Explicit unpacking in body (required)
def process(pair):
    x, y = pair
    return x + y

process((1, 2))  # 3

# Or use unpacking in function signature (only in Py3 via lambdas)
from functools import wraps

def process(pair):
    x, y = pair
    return x + y

# Nested unpacking in body
def nested(pair):
    a, (b, c) = pair
    return a + b + c

nested((1, (2, 3)))  # 6
```

**Risk Level**: Low — Rare pattern, easily refactored.

**Auto-fixable by 2to3**: Yes, `fix_unpack` adds explicit unpacking in function bodies.

**Notes/Gotchas**:
- **Rare pattern**: Most Py2 code doesn't use tuple unpacking in parameters; normal unpacking is preferred.
- **Readability**: Explicit unpacking in function body is clearer anyway.
- **Lambdas**: Lambda can't have unpacking parameters in Py3; use regular functions or comprehensions.

---

## 21. Class Definition Changes

**Category**: Object-Oriented Programming

**Description**: Old-style classes (not inheriting from `object`) are removed in Python 3. All classes are new-style. Additionally, class bodies can't execute arbitrary statements in certain contexts (affects metaclasses).

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Old-style class** | `class X:` | Not allowed |
| **New-style class** | `class X(object):` | `class X:` (implicitly inherits object) |
| **isinstance checks** | Different for old/new | All new-style |
| **MRO** | Different | C3 linearization always |

**Python 2 Examples**:
```python
# Old-style class
class OldStyle:
    def __init__(self):
        self.x = 1

# New-style class (preferred in Py2)
class NewStyle(object):
    def __init__(self):
        self.x = 1

# Mixing causes issues
class Derived(OldStyle):
    pass

# isinstance fails across old/new
obj = OldStyle()
isinstance(obj, object)  # False! (old-style)

obj2 = NewStyle()
isinstance(obj2, object)  # True (new-style)
```

**Python 3 Examples**:
```python
# All classes are new-style
class MyClass:
    def __init__(self):
        self.x = 1

# Inheriting from object is explicit but redundant
class MyClass(object):
    def __init__(self):
        self.x = 1

# All instances are objects
obj = MyClass()
isinstance(obj, object)  # True always
```

**Risk Level**: Low — Mostly transparent; behavior aligns with modern Python.

**Auto-fixable by 2to3**: Partially. The `fix_types` fixer helps, but manually adding `(object)` is simple.

**Notes/Gotchas**:
- **MRO changes**: Old-style classes use depth-first, left-to-right MRO. New-style use C3 linearization. Existing code using new-style won't notice.
- **Slots**: `__slots__` in old-style classes works differently; may need adjustment.
- **Pickle**: Pickled old-style instances don't unpickle in Py3 as new-style.

---

## 22. Magic Method Renames

**Category**: Special Methods

**Description**: Several magic methods are renamed or removed in Python 3. Most notably: `__cmp__` removed (use rich comparison methods), `__nonzero__` → `__bool__`, `__unicode__` → `__str__`, and division methods consolidation.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Boolean check** | `__nonzero__()` | `__bool__()` |
| **String repr** | `__str__()` (bytes), `__unicode__()` (text) | `__str__()` (text only) |
| **Unicode repr** | `__unicode__()` | Removed, use `__str__()` |
| **Comparison** | `__cmp__()` | Removed, use `__lt__`, `__eq__`, etc. |
| **True division** | `__div__()` (with /) | `__truediv__()` (with /) |
| **Floor division** | `__div__()` in Py2 (with /) | `__floordiv__()` (with //) |
| **Division fallback** | `__coerce__()` | Removed |
| **Method reflection** | `__get__()`, etc. | Same but refined |
| **Container length** | `__len__()` (same) | `__len__()` (same) |
| **Iteration** | `next()` method on iterator | `__next__()` method |

**Python 2 Examples**:
```python
class MyNum(object):
    def __init__(self, value):
        self.value = value
    
    # Old boolean check
    def __nonzero__(self):
        return self.value != 0
    
    # Comparison function
    def __cmp__(self, other):
        if self.value < other.value:
            return -1
        elif self.value > other.value:
            return 1
        else:
            return 0
    
    # Division methods
    def __div__(self, other):
        return MyNum(self.value / other.value)
    
    def __truediv__(self, other):
        return MyNum(float(self.value) / other.value)
    
    # String representations
    def __str__(self):
        return str(self.value)  # bytes
    
    def __unicode__(self):
        return u"MyNum(%d)" % self.value  # unicode

# Iterators
class MyIterator(object):
    def __init__(self, data):
        self.data = data
        self.index = 0
    
    def __iter__(self):
        return self
    
    def next(self):  # Old iterator method
        if self.index >= len(self.data):
            raise StopIteration
        value = self.data[self.index]
        self.index += 1
        return value
```

**Python 3 Examples**:
```python
class MyNum:
    def __init__(self, value):
        self.value = value
    
    # New boolean check
    def __bool__(self):
        return self.value != 0
    
    # Rich comparison methods (required)
    def __lt__(self, other):
        return self.value < other.value
    
    def __le__(self, other):
        return self.value <= other.value
    
    def __eq__(self, other):
        return self.value == other.value
    
    def __ne__(self, other):
        return self.value != other.value
    
    def __gt__(self, other):
        return self.value > other.value
    
    def __ge__(self, other):
        return self.value >= other.value
    
    # Division methods
    def __truediv__(self, other):
        return MyNum(self.value / other.value)
    
    def __floordiv__(self, other):
        return MyNum(self.value // other.value)
    
    # String representation (text only)
    def __str__(self):
        return f"MyNum({self.value})"
    
    def __repr__(self):
        return f"MyNum({self.value!r})"

# Iterators
class MyIterator:
    def __init__(self, data):
        self.data = data
        self.index = 0
    
    def __iter__(self):
        return self
    
    def __next__(self):  # New iterator method
        if self.index >= len(self.data):
            raise StopIteration
        value = self.data[self.index]
        self.index += 1
        return value
```

**Risk Level**: Medium → High depending on custom classes.

**Auto-fixable by 2to3**: Partially. The `fix_types` fixer can help, but complex comparison logic needs manual review.

**Notes/Gotchas**:
- **`__nonzero__` → `__bool__`**: Only the new name works in Py3; old name is ignored.
- **`__cmp__` removal**: Code relying on `cmp()` function must define rich comparison methods.
- **`@functools.total_ordering`**: Decorator can auto-generate missing comparison methods.
- **`__unicode__` removal**: Use `__str__()` for text representation (text is default in Py3).
- **`__str__` vs `__repr__`**: In Py3, both should return `str` (text). `__str__` for user-friendly, `__repr__` for developer-friendly.
- **Iterator protocol**: `next()` → `__next__()`. The old `next()` function still works but calls `__next__()` internally.
- **Division**: `__div__` removed; `/` uses `__truediv__`, `//` uses `__floordiv__`.

---

## 23. Reduce Function

**Category**: Built-in Functions

**Description**: `reduce()` is removed from built-ins in Python 3. It's moved to `functools` module. Use `functools.reduce()` or express logic with loops or comprehensions.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Built-in reduce** | `reduce(func, seq)` | Removed |
| **Functools module** | Not needed | `from functools import reduce` |
| **Import location** | N/A | `functools.reduce()` |

**Python 2 Examples**:
```python
# Built-in reduce
from operator import add
numbers = [1, 2, 3, 4, 5]

# Sum using reduce
total = reduce(add, numbers)  # 15

# Or with lambda
total = reduce(lambda x, y: x + y, numbers)  # 15

# Product
product = reduce(lambda x, y: x * y, numbers)  # 120

# With initial value
total = reduce(add, numbers, 0)  # 15 (same, 0 is initial)
```

**Python 3 Examples**:
```python
# Must import from functools
from functools import reduce
from operator import add

numbers = [1, 2, 3, 4, 5]

# Same usage as Py2
total = reduce(add, numbers)  # 15

# Or with lambda
total = reduce(lambda x, y: x + y, numbers)  # 15

# Product
product = reduce(lambda x, y: x * y, numbers)  # 120

# With initial value
total = reduce(add, numbers, 0)  # 15

# Alternative: use built-in sum() for common cases
total = sum(numbers)  # 15 (cleaner!)

# Or use explicit loops
total = 0
for num in numbers:
    total += num  # Clearer intent
```

**Risk Level**: Low — Function location change; behavior unchanged.

**Auto-fixable by 2to3**: Yes, `fix_reduce` adds `from functools import reduce`.

**Notes/Gotchas**:
- **Functional style**: Python 3 discourages heavy functional style; imperative loops are preferred.
- **Built-in alternatives**: Many common reduce operations have cleaner alternatives:
  - `reduce(add, seq)` → `sum(seq)`
  - `reduce(max, seq)` → `max(seq)`
  - `reduce(mul, seq)` → `math.prod(seq)` (Py3.8+)
- **Import**: Always use `from functools import reduce` at module level.
- **Readability**: Explicit loops are often clearer than reduce.

---

## 24. Apply Function

**Category**: Built-in Functions

**Description**: `apply()` is removed in Python 3. Use `*args` unpacking and function calls instead.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **apply()** | `apply(func, args)` | Removed |
| **Function call** | `func(*args)` (works) | `func(*args)` (preferred) |
| **With kwargs** | `apply(func, args, kwargs)` | `func(*args, **kwargs)` |

**Python 2 Examples**:
```python
def greet(name, greeting="Hello"):
    return f"{greeting}, {name}!"

# Using apply()
args = ("Alice",)
result = apply(greet, args)  # "Hello, Alice!"

# With keyword arguments
args = ("Bob",)
kwargs = {"greeting": "Hi"}
result = apply(greet, args, kwargs)  # "Hi, Bob!"
```

**Python 3 Examples**:
```python
def greet(name, greeting="Hello"):
    return f"{greeting}, {name}!"

# Using unpacking (cleaner, always works)
args = ("Alice",)
result = greet(*args)  # "Hello, Alice!"

# With keyword arguments
args = ("Bob",)
kwargs = {"greeting": "Hi"}
result = greet(*args, **kwargs)  # "Hi, Bob!"
```

**Risk Level**: Very Low — Mechanical replacement.

**Auto-fixable by 2to3**: Yes, `fix_apply` converts `apply(f, args, kwargs)` → `f(*args, **kwargs)`.

**Notes/Gotchas**:
- **Already idiomatic**: Unpacking syntax is already preferred in Py2.
- **Readability**: `func(*args)` is clearer than `apply(func, args)`.

---

## 25. Buffer Type

**Category**: Binary Data

**Description**: `buffer` type is removed in Python 3. Use `memoryview` instead for memory views of binary data.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Buffer type** | `buffer(bytes)` | Removed |
| **Memory view** | Not common | `memoryview(bytes)` |
| **Read-only access** | `buffer` limited | `memoryview` flexible |

**Python 2 Examples**:
```python
# Buffer for memory view without copy
data = "hello"
buf = buffer(data)  # buffer object

# Index into buffer
first_byte = buf[0]  # 'h'

# No copying
sub_buf = buf[1:4]  # 'ell' (view, not copy)
```

**Python 3 Examples**:
```python
# Use memoryview instead
data = b"hello"  # bytes
mv = memoryview(data)  # memoryview object

# Index into memoryview
first_byte = mv[0]  # 104 (ord value)

# No copying
sub_mv = mv[1:4]  # memoryview object (view)

# Convert memoryview to bytes if needed
sub_bytes = bytes(sub_mv)  # b'ell'
```

**Risk Level**: Low → Medium depending on buffer usage.

**Auto-fixable by 2to3**: Partially. The `fix_buffer` fixer can help, but semantics differ slightly.

**Notes/Gotchas**:
- **Bytes indexing**: In Py3, `bytes[0]` and `memoryview[0]` return integers, not characters.
- **Copying**: Both `buffer` and `memoryview` avoid copies, but usage differs.
- **String vs bytes**: In Py2, `buffer("string")` works. In Py3, `memoryview(b"bytes")` required.

---

## 26. Execfile Function

**Category**: Code Execution

**Description**: `execfile()` function is removed in Python 3. Use `exec()` with `open()` instead.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **execfile()** | `execfile("script.py")` | Removed |
| **Replacement** | `open()` + `exec()` | `exec(open(...).read())` |

**Python 2 Examples**:
```python
# Execute file directly
execfile("config.py")

# With namespace
execfile("config.py", globals())

# With separate globals and locals
execfile("script.py", globals(), locals())
```

**Python 3 Examples**:
```python
# Read and execute file
exec(open("config.py").read())

# With namespace
exec(open("config.py").read(), globals())

# With separate globals and locals
exec(open("script.py").read(), globals(), locals())

# More explicit (context manager)
with open("config.py") as f:
    exec(f.read(), globals())
```

**Risk Level**: Low → Medium depending on dynamic execution patterns.

**Auto-fixable by 2to3**: Yes, `fix_execfile` converts to `exec(open(...).read(), ...)`.

**Notes/Gotchas**:
- **File encoding**: `open()` in Py3 defaults to platform encoding; specify encoding if needed: `open("script.py", encoding="utf-8")`.
- **Context manager**: Using `with open() as f:` is safer (ensures file closure).
- **Security**: `exec()` with file content can be dangerous; avoid with untrusted files.

---

## 27. Reload Function

**Category**: Module Management

**Description**: `reload()` is removed from built-ins in Python 3. It's moved to `importlib` module.

| Aspect | Python 2 | Python 3 |
|--------|----------|----------|
| **Built-in reload** | `reload(module)` | Removed |
| **Importlib module** | Not needed | `from importlib import reload` |
| **Usage** | `reload(sys)` | `reload(sys)` (after import) |

**Python 2 Examples**:
```python
import sys

# Built-in reload
reload(sys)  # Reloads sys module

# After modifying a module file
import mymodule
# ... modify mymodule.py ...
reload(mymodule)  # Re-execute module code
```

**Python 3 Examples**:
```python
import sys
from importlib import reload

# Use reload from importlib
reload(sys)  # Reloads sys module

# After modifying a module file
import mymodule
# ... modify mymodule.py ...
reload(mymodule)  # Re-execute module code
```

**Risk Level**: Low — Function location change; behavior mostly unchanged.

**Auto-fixable by 2to3**: Yes, `fix_reload` adds `from importlib import reload`.

**Notes/Gotchas**:
- **Rare usage**: `reload()` is rarely needed in production code; mostly used in development/REPL.
- **Side effects**: Reloading a module re-executes all module-level code; can have unexpected side effects.
- **Imports**: Already-imported names from module won't update after reload; rebind them.
- **Circular imports**: Reloading can expose circular import issues.

---

## Summary Table

| Change | Python 2 | Python 3 | Risk | Auto-fixable |
|--------|----------|----------|------|--------------|
| Print | `print x` | `print(x)` | Low | Yes |
| Exceptions | `except X, e:` | `except X as e:` | Low | Yes |
| Division | `5/2` = 2 | `5/2` = 2.5 | High | Partial |
| Strings | `"x"` = bytes | `"x"` = str | High | Partial |
| Octals | `0755` | `0o755` | Low | Yes |
| Longs | `5L` | `5` | Low | Yes |
| Backticks | `` `x` `` | `repr(x)` | Low | Yes |
| `<>` | Valid | Invalid | Very Low | Yes |
| Exec | `exec x` | `exec(x)` | Medium | Yes |
| `.iteritems()` | Iterator | Use `.items()` | Medium | Partial |
| `map()/filter()/zip()` | Lists | Iterators | Medium | Partial |
| `range()` / `xrange()` | Lists / Iterator | Range iterator | Low | Yes |
| `input()` | Unsafe | Safe | Low | Yes |
| `unicode` / `str` | Two types | One type | High | Partial |
| `.has_key()` | Valid | Invalid | Very Low | Yes |
| `cmp` parameter | Valid | Invalid | Medium | Partial |
| Relative imports | Implicit | Explicit | Medium | Partial |
| Metaclass | `__metaclass__` | `metaclass=` | Medium | Yes |
| `super()` | `super(C, self)` | `super()` | Low | Yes |
| Tuple unpacking | In params | In body | Low | Yes |
| Old-style classes | `class C:` | `class C:` (new-style) | Low | Partial |
| Magic methods | Various | Renamed/removed | Medium | Partial |
| `reduce()` | Built-in | `functools.reduce()` | Low | Yes |
| `apply()` | Valid | Use `*args` | Very Low | Yes |
| `buffer` | Valid | Use `memoryview` | Low | Partial |
| `execfile()` | Valid | Use `exec(open())` | Low | Yes |
| `reload()` | Built-in | `importlib.reload()` | Low | Yes |

