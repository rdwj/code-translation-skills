# Python 2 → Python 3: Semantic & Behavioral Changes Reference

## Document Purpose

This document catalogs behavioral and semantic changes between Python 2 and Python 3 — changes in HOW code executes, not just how it's written. These differences are often INVISIBLE to syntax checkers but can silently break functionality.

This document is consulted by:
- **Skill 0.1 (Codebase Analyzer)**: To identify behavioral patterns requiring semantic changes
- **Skill 3.1 (Semantic Validator)**: To detect behavioral differences that 2to3 can't fix
- **Skill 3.3 (Behavioral Testing)**: To design tests that expose semantic issues

Behavioral changes are more dangerous than syntax changes because they don't raise syntax errors — they silently produce wrong results.

---

## Table of Contents

1. [String/Bytes Type System](#1-stringbytes-type-system)
2. [Integer Division Behavior](#2-integer-division-behavior)
3. [Dictionary Ordering and Views](#3-dictionary-ordering-and-views)
4. [Map/Filter/Zip Iterator Behavior](#4-mapfilterzap-iterator-behavior)
5. [Comparison Operators](#5-comparison-operators)
6. [Bytes Indexing](#6-bytes-indexing)
7. [Rounding Behavior](#7-rounding-behavior)
8. [File I/O Default Encoding](#8-file-io-default-encoding)
9. [Pickle Protocol Compatibility](#9-pickle-protocol-compatibility)
10. [Hash Randomization](#10-hash-randomization)
11. [Unicode Normalization](#11-unicode-normalization)
12. [Exception Chaining and Scope](#12-exception-chaining-and-scope)
13. [Keyword-Only Arguments](#13-keyword-only-arguments)
14. [Function Annotations](#14-function-annotations)
15. [Generator Return Values](#15-generator-return-values)
16. [Standard Library Behavior Changes](#16-standard-library-behavior-changes)
17. [os.environ Type](#17-osenviron-type)
18. [Subprocess Default Encoding](#18-subprocess-default-encoding)
19. [Regular Expression Flags](#19-regular-expression-flags)
20. [sys.maxint and Numeric Limits](#20-sysmaxint-and-numeric-limits)
21. [Thread Safety Changes](#21-thread-safety-changes)
22. [open() Default Encoding](#22-open-default-encoding)

---

## 1. String/Bytes Type System

**Category**: Fundamental Type System

**Description**: The most profound semantic change. Python 2 conflates bytes and text (both `str` type). Python 3 rigorously separates them. In Python 2, you can mix strings and unicode, auto-converting. In Python 3, mixing raises `TypeError`.

### Python 2 Behavior
```python
# Implicit conversions (mostly work, sometimes fail)
text = "hello"  # bytes type
data = u"world"  # unicode type

# Auto-conversion attempts (confusing!)
combined = "x" + u"y"  # Tries to decode "x" as ASCII → u"xy"
combined = u"x" + "y"  # Encodes "y" as ASCII first → u"xy"

# Reading files (default returns bytes)
f = open("file.txt")
content = f.read()  # str (bytes), not unicode

# JSON always returns unicode in Py2.6+
import json
data = json.loads("""{"key": "value"}""")  # unicode keys, values

# Environment variables (bytes in Py2)
import os
path = os.environ["PATH"]  # str (bytes)

# Operations sometimes coerce
x = "hello" * 2  # "hellohello" (bytes)
y = u"world" * 2  # u"worldworld" (unicode)
z = "hello".upper()  # "HELLO" (bytes)
```

### Python 3 Behavior
```python
# Strict type separation (no auto-conversion)
text = "hello"  # str (text)
data = b"world"  # bytes (raw)

# Mixing raises TypeError
combined = "x" + b"y"  # TypeError! Can't mix str and bytes
combined = "x".encode() + b"y"  # Must be explicit

# Reading files (default returns str/text)
f = open("file.txt")  # Default mode='r' (text)
content = f.read()  # str (text) with default encoding

f = open("file.txt", "rb")  # Binary mode
content = f.read()  # bytes

# JSON returns text (str)
import json
data = json.loads("""{"key": "value"}""")  # str keys, values

# Environment variables (text in Py3)
import os
path = os.environ["PATH"]  # str (text)

# Operations consistent
x = "hello" * 2  # "hellohello" (str/text)
y = b"world" * 2  # b"worldworld" (bytes)
z = "hello".upper()  # "HELLO" (str/text)
```

### Risk Level
**HIGH** — This is the fundamental change affecting all string/data handling.

### Detection Approach
- Look for `str()` / `unicode()` / `.encode()` / `.decode()` operations
- Check file I/O operations and their usage
- Inspect JSON/pickle/database library interactions
- Find implicit string operations (concatenation, comparison)
- Trace data flow from sources (files, network, env vars) to sinks (output, databases)

### Migration Strategy
1. **Identify data sources**: File I/O, network, environment, databases
2. **Choose encoding**: Explicit encoding for all string operations
3. **Use str for text, bytes for data**: Clear separation
4. **Explicit conversions**: No implicit coercions; use `.encode()`, `.decode()`
5. **Test with different encodings**: UTF-8, ASCII, Latin-1

### Common Patterns
```python
# Py2: File reading (confusing - is it text or bytes?)
with open("config.txt") as f:
    config = f.read()

# Py3: Explicit (text mode)
with open("config.txt", encoding="utf-8") as f:
    config = f.read()

# Py3: Binary mode
with open("config.bin", "rb") as f:
    data = f.read()

# Py2: Mix of str and unicode (implicit conversions)
msg = "Error: " + unicode_user_input

# Py3: Explicit
msg = "Error: " + str(user_input)
```

### Notes/Gotchas
- **JSON**: Py2 `json.loads()` accepts str (bytes); Py3 requires str (text) or explicitly decode bytes first.
- **Pickle**: Protocol version affects compatibility; Py2 pickles may not unpickle correctly in Py3.
- **Regex**: Pattern type must match string type: `re.compile(u"pattern")` for text, `re.compile(b"pattern")` for bytes.
- **Database drivers**: Some return bytes; must decode to text for compatibility.

---

## 2. Integer Division Behavior

**Category**: Arithmetic Operations

**Description**: The `/` operator changes from floor division (with int operands) to true division (always returns float).

### Python 2 Behavior
```python
# Integer division
result = 5 / 2  # 2 (floor division, int result)
result = 10 / 3  # 3 (truncates)
result = -5 / 2  # -3 (floor division toward negative infinity)

# With floats (always returns float)
result = 5.0 / 2  # 2.5
result = 5 / 2.0  # 2.5

# Working around (explicit float conversion)
result = float(5) / 2  # 2.5
result = 5 * 1.0 / 2  # 2.5

# Floor division (explicit, works in both versions)
result = 5 // 2  # 2 (recommended way even in Py2)
```

### Python 3 Behavior
```python
# True division always returns float
result = 5 / 2  # 2.5
result = 10 / 3  # 3.333...
result = -5 / 2  # -2.5 (true division)

# With floats (same as Py2)
result = 5.0 / 2  # 2.5
result = 5 / 2.0  # 2.5

# Floor division (explicit)
result = 5 // 2  # 2
result = -5 // 2  # -3 (floor division toward negative infinity)
```

### Risk Level
**HIGH** — Silent data type and value changes; calculations differ fundamentally.

### Detection Approach
- Find all `/` operators; categorize as floor division vs true division
- Check computations using division results (especially array indexing, loop counts)
- Look for patterns like `offset / stride`, `count / batch_size`, `index / width`
- Trace division results to type-sensitive operations

### Migration Strategy
1. **Audit all division**: Use search for `/` operator
2. **Determine intent**: Does the code need floor division or true division?
3. **Use explicit operator**: Floor division → `//`, true division → `/` (Py3 behavior)
4. **Add tests**: Integer division calculations should have regression tests

### Common Patterns
```python
# Py2: Array indexing (bug waiting to happen)
stride = 2
index = 5
offset = index / stride  # 2 (floor division)
element = array[offset]  # Wrong element!

# Py3: Must use floor division explicitly
offset = index // stride  # 2 (explicit floor)
element = array[offset]  # Correct

# Py2: Loop counts (silent bug)
num_batches = total_items / batch_size  # Floor division
for i in range(num_batches):  # May skip last batch!
    process_batch(items[i*batch_size:(i+1)*batch_size])

# Py3: Must be explicit
num_batches = total_items // batch_size
for i in range(num_batches):
    process_batch(items[i*batch_size:(i+1)*batch_size])

# Math calculations (now correct)
# Py2: requires workaround
average = float(sum_values) / count  # Force float division

# Py3: works naturally
average = sum_values / count  # 2.5 (float)
```

### Notes/Gotchas
- **Silent changes**: No exception; calculations just differ.
- **Modulo behavior**: `%` operator unchanged; but combined with `/` behavior matters.
- **Negative numbers**: `-5 // 2` = -3 in both versions (floor division), but `-5 / 2` differs (Py2: -2, Py3: -2.5).
- **Type coercion**: Even small changes in division can cascade.

---

## 3. Dictionary Ordering and Views

**Category**: Collection Behavior

**Description**: Python 3.7+ guarantees dict insertion order (implementation detail in 3.6+). More importantly, `.keys()`, `.values()`, `.items()` return view objects, not lists. Views are iterable but not indexable.

### Python 2 Behavior
```python
d = {'z': 1, 'a': 2, 'm': 3}

# Iteration order is undefined (no guarantee)
for k in d:
    print k  # Unpredictable order

# .keys()/.values()/.items() return lists
keys = d.keys()  # ['z', 'a', 'm'] or different (undefined order)
values = d.values()  # [1, 2, 3] or different
items = d.items()  # [('z', 1), ...] or different

# Lists support indexing
first_key = keys[0]  # Depends on dict iteration order

# List operations work
sorted_keys = sorted(d.keys())  # ['a', 'm', 'z']

# Length works
len(d.keys())  # 3
```

### Python 3 Behavior
```python
d = {'z': 1, 'a': 2, 'm': 3}

# Iteration order is GUARANTEED (insertion order, Py3.7+)
for k in d:
    print(k)  # 'z', 'a', 'm' (insertion order)

# .keys()/.values()/.items() return views (not lists)
keys = d.keys()  # dict_keys(['z', 'a', 'm'])
values = d.values()  # dict_values([1, 2, 3])
items = d.items()  # dict_items([('z', 1), ...])

# Views are NOT indexable (raises TypeError)
first_key = keys[0]  # TypeError! dict_keys object is not subscriptable

# Views are iterable
for k in keys:
    print(k)  # Works

# Can convert to list if needed
first_key = list(keys)[0]  # 'z'

# Length works on views
len(d.keys())  # 3

# Views support set operations
dict1_keys = d1.keys()
dict2_keys = d2.keys()
common = dict1_keys & dict2_keys  # Set intersection

# Dynamic views (change with dict)
d = {1: 'a'}
keys = d.keys()  # dict_keys([1])
d[2] = 'b'
# keys now reflects the change (dynamic)
```

### Risk Level
**MEDIUM** — Iteration order guaranteed is good; indexing breaks bad.

### Detection Approach
- Find all indexing of `.keys()`, `.values()`, `.items()`: `d.keys()[0]`
- Look for assumptions about dictionary iteration order
- Check test assertions about dict ordering (Py2 tests may be brittle)
- Search for patterns like `sorted(d.items())` which assume list conversion

### Migration Strategy
1. **Remove indexing**: Convert `.keys()[n]` → `list(d.keys())[n]` (if needed)
2. **Use views when possible**: Views are more efficient than lists
3. **Update tests**: Remove brittle assertions about dict order
4. **Rely on insertion order** (Py3.7+): Can assume order is consistent

### Common Patterns
```python
# Py2: Dangerous — indexing into dict.keys()
def get_first_key(d):
    return d.keys()[0]  # Undefined order, but works

# Py3: Must convert to list or use next()
def get_first_key(d):
    return next(iter(d.keys()))  # Cleaner
    # OR
    return list(d.keys())[0]  # Explicit conversion

# Py2: Assuming certain key order
def assert_keys(d, expected):
    assert d.keys() == expected  # Brittle!

# Py3: More robust (if order matters)
def assert_keys(d, expected):
    assert list(d.keys()) == expected  # Explicit

# Py2: Using dict.keys() in set operations (fails)
dict1_keys = d1.keys()  # list
dict2_keys = d2.keys()  # list
common = set(dict1_keys) & set(dict2_keys)  # Must convert to set

# Py3: Views support set operations directly
dict1_keys = d1.keys()  # dict_keys view
dict2_keys = d2.keys()  # dict_keys view
common = dict1_keys & dict2_keys  # Works!
```

### Notes/Gotchas
- **Views are dynamic**: If dict changes, view reflects changes.
- **Views are iterable but not indexable**: Most common usage (iteration) works; indexing breaks.
- **Order guarantee**: Py3.7+ guarantees insertion order; Py3.6 is implementation detail; Py3.5- undefined.
- **Pickle/serialization**: Dicts in pickled data may have different order when unpickled in different versions.

---

## 4. Map/Filter/Zip Iterator Behavior

**Category**: Built-in Function Behavior

**Description**: These functions return iterators in Python 3 (lazy evaluation, single-pass) rather than lists (eager evaluation, reusable).

### Python 2 Behavior
```python
# All return lists (eager evaluation)
numbers = [1, 2, 3, 4, 5]

doubled = map(lambda x: x * 2, numbers)
# doubled = [2, 4, 6, 8, 10] (list)

# Can index directly
first = doubled[0]  # 2
second = doubled[1]  # 4

# Can iterate multiple times
for x in doubled:
    print x
for x in doubled:  # Second iteration works (list still there)
    print x

# Can check length
len(doubled)  # 5

# Can slice
subset = doubled[1:3]  # [4, 6]

# filter() and zip() similarly return lists
evens = filter(lambda x: x % 2 == 0, numbers)  # [2, 4]
pairs = zip([1, 2, 3], ['a', 'b', 'c'])  # [(1, 'a'), (2, 'b'), (3, 'c')]
```

### Python 3 Behavior
```python
# All return iterators (lazy evaluation, memory efficient)
numbers = [1, 2, 3, 4, 5]

doubled = map(lambda x: x * 2, numbers)
# doubled = <map object> (iterator, not list)

# Cannot index (raises TypeError)
first = doubled[0]  # TypeError! 'map' object is not subscriptable

# Single-pass iteration
for x in doubled:
    print(x)  # 2, 4, 6, 8, 10
for x in doubled:  # Second iteration produces nothing (exhausted)
    print(x)  # No output!

# Must convert to list to iterate multiple times
doubled = list(map(lambda x: x * 2, numbers))
for x in doubled:
    print(x)
for x in doubled:  # Now works (it's a list)
    print(x)

# Cannot check length of iterator
len(doubled)  # TypeError! object of type 'map' has no len()

# Cannot slice
subset = doubled[1:3]  # TypeError!

# filter() and zip() similarly return iterators
evens = filter(lambda x: x % 2 == 0, numbers)  # <filter object>
pairs = zip([1, 2, 3], ['a', 'b', 'c'])  # <zip object>
```

### Risk Level
**MEDIUM** — Code that indexes or reuses iterators breaks; single-iteration code works unchanged.

### Detection Approach
- Find all uses of `map()`, `filter()`, `zip()` in code
- Check for indexing: `map(...)[0]`
- Check for multiple iterations: `for x in result: ... for x in result: ...`
- Check for `len()` calls on results
- Look for list methods called on results: `.append()`, `.sort()`, etc.

### Migration Strategy
1. **Single iteration only**: Use iterators as-is (more efficient in Py3)
2. **Multiple iterations**: Convert to list: `list(map(...))`
3. **Indexing needed**: Use `list()` or consider list comprehension instead
4. **Length needed**: Convert to list or use `sum(1 for _ in map(...))`

### Common Patterns
```python
# Py2: map() returns list, can index
def get_first_squared(numbers):
    squared = map(lambda x: x ** 2, numbers)
    return squared[0]

# Py3: Must convert if indexing
def get_first_squared(numbers):
    squared = list(map(lambda x: x ** 2, numbers))
    return squared[0]
    # OR better: use list comprehension
    squared = [x ** 2 for x in numbers]
    return squared[0]
    # OR best: don't use indexing
    return next(map(lambda x: x ** 2, numbers))

# Py2: filter() and loop
def process_evens(numbers):
    evens = filter(lambda x: x % 2 == 0, numbers)
    for x in evens:
        print(x)
    return len(evens)  # Get count

# Py3: Requires list conversion for len()
def process_evens(numbers):
    evens = list(filter(lambda x: x % 2 == 0, numbers))
    for x in evens:
        print(x)
    return len(evens)
    # OR: Use list comprehension (cleaner)
    evens = [x for x in numbers if x % 2 == 0]
    for x in evens:
        print(x)
    return len(evens)

# Py2: zip() multiple times
def compare_pairs(list1, list2):
    pairs = zip(list1, list2)
    if pairs:  # Check if non-empty
        first = pairs[0]
    for p in pairs:
        process(p)

# Py3: zip() is single-pass
def compare_pairs(list1, list2):
    pairs = list(zip(list1, list2))  # Convert if reusing
    if pairs:
        first = pairs[0]
    for p in pairs:
        process(p)
```

### Notes/Gotchas
- **List comprehensions better**: `[x*2 for x in numbers]` is often clearer than `map(lambda x: x*2, numbers)`.
- **Exhaustion**: Iterators are exhausted after one pass; no way to "reset" them.
- **Performance**: Using iterators in Py3 is more efficient; use lists only when necessary.
- **Chaining**: `map(f, map(g, x))` creates nested iterators, evaluated lazily (efficient).

---

## 5. Comparison Operators

**Category**: Operator Behavior

**Description**: Python 3 removes `__cmp__()` magic method and disallows comparisons between incompatible types. In Python 2, you could compare `5 < "abc"` (weird); in Python 3, this raises `TypeError`.

### Python 2 Behavior
```python
# Old comparison function
class Value:
    def __init__(self, x):
        self.x = x
    
    def __cmp__(self, other):
        if self.x < other.x:
            return -1
        elif self.x > other.x:
            return 1
        else:
            return 0

# Works (returns -1, 0, or 1)
v1 = Value(5)
v2 = Value(10)
print v1 < v2  # True (calls __cmp__)
print v1 == v2  # False

# Comparing incompatible types (allowed, weird!)
print 5 < "abc"  # True (int < str always true in Py2, by type name)
print [] < {}  # True (list < dict by type name)
print None < 0  # True (NoneType < int)

# No rich comparison methods required
# cmp() built-in function uses __cmp__
print cmp(5, 10)  # -1
print cmp("a", "b")  # -1
```

### Python 3 Behavior
```python
# Must define rich comparison methods
class Value:
    def __init__(self, x):
        self.x = x
    
    def __lt__(self, other):
        return self.x < other.x
    
    def __le__(self, other):
        return self.x <= other.x
    
    def __eq__(self, other):
        return self.x == other.x
    
    def __ne__(self, other):
        return self.x != other.x
    
    def __gt__(self, other):
        return self.x > other.x
    
    def __ge__(self, other):
        return self.x >= other.x

# Works (each method independent)
v1 = Value(5)
v2 = Value(10)
print(v1 < v2)  # True
print(v1 == v2)  # False

# Comparing incompatible types raises TypeError
print(5 < "abc")  # TypeError: '<' not supported between instances of 'int' and 'str'
print([] < {})  # TypeError
print(None < 0)  # TypeError

# Use @functools.total_ordering for brevity
from functools import total_ordering

@total_ordering
class Value:
    def __init__(self, x):
        self.x = x
    
    def __eq__(self, other):
        return self.x == other.x
    
    def __lt__(self, other):
        return self.x < other.x
    
    # Other methods auto-generated

# cmp() function removed; use key= parameter in sort instead
# Or use functools.cmp_to_key() for compatibility
```

### Risk Level
**MEDIUM** — Custom comparison code breaks; cross-type comparisons raise exceptions.

### Detection Approach
- Find `__cmp__()` method definitions
- Look for cross-type comparisons (often in tests or edge cases)
- Check sorting code using `cmp=` parameter
- Look for `cmp()` function calls

### Migration Strategy
1. **Replace `__cmp__()`**: Define `__eq__()` and `__lt__()` (or use `@total_ordering`)
2. **Remove cross-type comparisons**: Ensure types are compatible before comparing
3. **Fix sorting**: Use `key=` parameter instead of `cmp=`
4. **Fix tests**: Tests comparing different types will fail

### Common Patterns
```python
# Py2: __cmp__ method
class Record:
    def __init__(self, value):
        self.value = value
    
    def __cmp__(self, other):
        return cmp(self.value, other.value)

records.sort(cmp=lambda r1, r2: r1 - r2)

# Py3: Rich comparison methods (verbose)
class Record:
    def __init__(self, value):
        self.value = value
    
    def __eq__(self, other):
        return self.value == other.value
    
    def __lt__(self, other):
        return self.value < other.value
    
    # ... other methods ...

# Py3: Using @total_ordering (cleaner)
from functools import total_ordering

@total_ordering
class Record:
    def __init__(self, value):
        self.value = value
    
    def __eq__(self, other):
        return self.value == other.value
    
    def __lt__(self, other):
        return self.value < other.value

# Sorting with key instead of cmp
records.sort(key=lambda r: r.value)
```

### Notes/Gotchas
- **`@total_ordering`**: Decorator generates missing comparison methods from `__eq__` and one other comparison.
- **Custom types**: If code defines custom `__cmp__`, must convert to rich methods.
- **Sorting**: Use `key=` (more efficient) rather than `cmp_to_key()` when possible.
- **Tests**: Unit tests with cross-type comparisons will fail with clear `TypeError` messages.

---

## 6. Bytes Indexing

**Category**: Data Type Behavior

**Description**: In Python 2, indexing into a string returns a character (str). In Python 3, indexing into bytes returns an integer (the byte value).

### Python 2 Behavior
```python
# Indexing string/bytes returns character
data = "hello"
char = data[0]  # 'h' (str, single character)
char = data[1]  # 'e' (str)

# Concatenation with characters
result = data[0] + data[1]  # 'he' (str)

# Comparison with characters
if data[0] == 'h':  # True
    pass

# Encoding to bytes
data_bytes = "hello".encode("utf-8")  # 'hello' (str type, no change!)
byte = data_bytes[0]  # 'h' (still str)
```

### Python 3 Behavior
```python
# Indexing bytes returns integer
data = b"hello"
byte_val = data[0]  # 104 (int, the byte value)
byte_val = data[1]  # 101 (int)

# Cannot concatenate int with bytes
result = data[0] + data[1]  # TypeError! int + int = 104 + 101 = 205 (not bytes)

# Comparison with integers (or characters)
if data[0] == ord('h'):  # True (compare int to int)
    pass

if data[0] == 'h':  # False! (int 104 != str 'h')
    pass

# Strings still return characters
text = "hello"
char = text[0]  # 'h' (str)

# To get single byte as bytes, use slice
data = b"hello"
byte_as_bytes = data[0:1]  # b'h' (bytes, not int)

# Or use chr() to convert int back to character
byte_val = data[0]  # 104
char = chr(byte_val)  # 'h' (str)
```

### Risk Level
**MEDIUM** — Affects code working with binary data; often breaks silently.

### Detection Approach
- Find indexing of binary data (bytes literals or `.encode()` results)
- Look for comparisons between indexed bytes and characters: `data[0] == 'h'`
- Check for arithmetic on indexed bytes: `data[0] + data[1]`
- Find code assuming indexing returns character, not int

### Migration Strategy
1. **Know the type**: Is it `str` (text, returns char) or `bytes` (binary, returns int)?
2. **Use slicing for bytes**: `data[0:1]` returns bytes, `data[0]` returns int
3. **Convert explicitly**: `chr(data[0])` or `bytes([byte_val])`
4. **Update comparisons**: Compare with integers or `ord(char)` for bytes

### Common Patterns
```python
# Py2: Check first byte of data
def check_magic_number(data):
    if data[0] == 'x89':  # PNG magic number
        return True
    return False

# Py3: Must compare with integer
def check_magic_number(data):
    if data[0] == 0x89:  # Integer, not string
        return True
    return False
    # OR: Compare string/byte slice
    if data[0:1] == b'\x89':
        return True

# Py2: Process bytes
def process_binary(data):
    for byte in data:
        print byte  # Prints characters

# Py3: Process bytes (different!)
def process_binary(data):
    for byte in data:
        print(byte)  # Prints integers (0-255)
    # To get characters:
    for byte in data:
        print(chr(byte))

# Py2: String/bytes confusion
def is_utf8(data):
    try:
        data.decode('utf-8')
        return True
    except:
        return False

# Py3: Must be explicit
def is_utf8(data):
    # data could be str (text) or bytes
    if isinstance(data, str):
        data = data.encode('utf-8')
    try:
        data.decode('utf-8')
        return True
    except:
        return False
```

### Notes/Gotchas
- **Slicing vs indexing**: `b"hello"[0]` → int 104, but `b"hello"[0:1]` → bytes b'h'
- **for loop iteration**: `for byte in bytes_data:` iterates as integers in Py3, characters in Py2
- **Strings unaffected**: `"hello"[0]` still returns `'h'` (str) in both versions
- **Encoding**: String `.encode()` returns bytes, which have different indexing

---

## 7. Rounding Behavior

**Category**: Numeric Behavior

**Description**: Python 3 implements "banker's rounding" (round to nearest even) instead of Python 2's traditional rounding.

### Python 2 Behavior
```python
# Traditional rounding (round half away from zero)
round(0.5)  # 1.0
round(1.5)  # 2.0
round(2.5)  # 3.0
round(3.5)  # 4.0
round(-0.5)  # -1.0 (away from zero)
round(-1.5)  # -2.0

# Banker's rounding not default
# (minimize bias in statistical operations)
```

### Python 3 Behavior
```python
# Banker's rounding (round half to even)
round(0.5)  # 0 (nearest even)
round(1.5)  # 2 (nearest even)
round(2.5)  # 2 (nearest even)
round(3.5)  # 4 (nearest even)
round(-0.5)  # 0 (nearest even)
round(-1.5)  # -2 (nearest even)

# Decimal module available for explicit rounding
from decimal import Decimal, ROUND_HALF_UP
d = Decimal('2.5')
d.quantize(Decimal('1'), rounding=ROUND_HALF_UP)  # 3
```

### Risk Level
**MEDIUM** — Subtle; affects financial calculations, statistics, rounding in edge cases.

### Detection Approach
- Find all `round()` calls with halves (e.g., `round(x * 100)` for percentages)
- Look for assertions on rounded values
- Check for statistical/financial calculations
- Search for tests asserting exact rounded values

### Migration Strategy
1. **Understand rounding direction**: Is banker's rounding acceptable?
2. **Use Decimal for precision**: `from decimal import Decimal, ROUND_HALF_UP`
3. **Test edge cases**: Especially `.5` values
4. **Document rounding**: Add comments explaining why certain rounding is used

### Common Patterns
```python
# Py2: Percentage rounding
percentage = (25.5 / 100)
rounded = round(percentage * 100)  # 26.0 (rounds up)

# Py3: Same code
percentage = (25.5 / 100)
rounded = round(percentage * 100)  # 25.0 (banker's rounding!)

# Py3: Use Decimal for control
from decimal import Decimal, ROUND_HALF_UP
percentage = Decimal('25.5')
rounded = percentage.quantize(Decimal('1'), rounding=ROUND_HALF_UP)  # 26

# Py2: Financial rounding
price = 9.95
quantity = 3
total = price * quantity
rounded = round(total, 2)  # 29.85

# Py3: May differ with banker's rounding
# Use Decimal for financial calculations
```

### Notes/Gotchas
- **Banker's rounding**: Unbiased over many operations, but different from traditional rounding
- **Decimal module**: Always available for precise rounding control
- **Tests**: Tests asserting rounded values may fail
- **Percentages**: Percentage rounding often uses traditional rounding; use Decimal

---

## 8. File I/O Default Encoding

**Category**: I/O Behavior

**Description**: Python 2 opens files in binary mode by default (returns `str`/bytes). Python 3 opens files in text mode with platform-dependent encoding (returns `str`/text).

### Python 2 Behavior
```python
# Default: opens in binary mode
f = open("file.txt")  # Returns bytes
content = f.read()  # str (bytes) type
lines = [line for line in f]  # List of str (bytes)

# Encoding ignored in text mode (there is no text mode by default)
f = open("file.txt", "r")  # Still binary! Just means "read"

# Binary explicitly
f = open("file.txt", "rb")
data = f.read()  # bytes (str type)

# Unicode text (special case)
f = open("file.txt", "rU")  # Universal newlines
content = f.read()  # Still bytes, but handles \r\n

# Must decode to unicode
f = open("file.txt")
content_bytes = f.read()
content_text = content_bytes.decode("utf-8")  # unicode
```

### Python 3 Behavior
```python
# Default: opens in text mode with platform encoding
f = open("file.txt")  # Returns text (str, Unicode)
content = f.read()  # str (text) type
lines = [line for line in f]  # List of str (text)

# Explicit encoding (recommended)
f = open("file.txt", encoding="utf-8")
content = f.read()  # str (text, UTF-8 decoded)

# Binary mode
f = open("file.txt", "rb")
data = f.read()  # bytes (raw data)

# Default encoding is platform-dependent!
f = open("file.txt")  # Uses locale.getpreferredencoding(False)
# On Windows: often 'cp1252' (not UTF-8!)
# On Linux: often 'utf-8'
# On Mac: often 'utf-8'

# Best practice: explicit encoding
f = open("file.txt", encoding="utf-8")  # Consistent across platforms
```

### Risk Level
**MEDIUM-HIGH** — Encoding issues cause subtle data corruption or exceptions.

### Detection Approach
- Find all `open()` calls; check if encoding is specified
- Look for `.read()` / `.readline()` / `.readlines()` operations
- Check for assumptions about encoding (Py2: bytes, Py3: might be wrong encoding)
- Search for `.encode()` / `.decode()` operations on file content
- Look for platform-specific behavior tests

### Migration Strategy
1. **Always specify encoding**: `open(file, encoding="utf-8")` for text
2. **Use binary mode explicitly**: `open(file, "rb")` for binary data
3. **Update code expecting bytes**: If code expects bytes from `open()`, add `"rb"` mode
4. **Test on multiple platforms**: Encoding differences cause silent failures

### Common Patterns
```python
# Py2: Read text file (gets bytes, works by accident)
with open("config.txt") as f:
    config = f.read()
    settings = config.split("\n")

# Py3: Must specify encoding OR code breaks on non-UTF-8 systems
with open("config.txt", encoding="utf-8") as f:
    config = f.read()
    settings = config.split("\n")

# Py2: Read binary file
with open("image.png", "rb") as f:
    data = f.read()
    magic = data[0:4]  # b'\x89PNG'

# Py3: Same (but indexing differs)
with open("image.png", "rb") as f:
    data = f.read()
    magic = data[0:4]  # b'\x89PNG' (slice returns bytes)
    byte = data[0]  # 0x89 (int)

# Py2: Process text (encoding issues lurk)
with open("text.txt") as f:
    for line in f:
        process(line)  # What encoding? UTF-8? Latin-1?

# Py3: Explicit encoding
with open("text.txt", encoding="utf-8") as f:
    for line in f:
        process(line)  # Clear: UTF-8
```

### Notes/Gotchas
- **Platform encoding**: `open()` without encoding uses `locale.getpreferredencoding()`, which varies by system.
- **Windows gotcha**: Default on Windows is often `cp1252` (Windows-1252), not UTF-8.
- **Newlines**: Py3's text mode auto-converts `\r\n` ↔ `\n` (Py2 did not by default).
- **`errors` parameter**: `open(file, errors="ignore")` or `errors="replace"` for handling bad encodings gracefully.

---

## 9. Pickle Protocol Compatibility

**Category**: Serialization

**Description**: Pickle protocol version differs between Python versions. Python 2 uses protocol 0-2 (text and binary). Python 3 uses protocol 3+ (binary only). Cross-version unpickling requires care.

### Python 2 Behavior
```python
import pickle

data = {'a': 1, 'b': 2}

# Protocol 0 (text-based, human-readable, slow)
pickle_bytes = pickle.dumps(data, protocol=0)

# Protocol 1 (binary, older)
pickle_bytes = pickle.dumps(data, protocol=1)

# Protocol 2 (binary, default in Py2.3+)
pickle_bytes = pickle.dumps(data)  # Default: protocol 2

# Unpickling
loaded = pickle.loads(pickle_bytes)
```

### Python 3 Behavior
```python
import pickle

data = {'a': 1, 'b': 2}

# Protocol 3 (binary, default in Py3)
pickle_bytes = pickle.dumps(data)  # Default: protocol 3

# Protocol 4 (Py3.4+, more compact)
pickle_bytes = pickle.dumps(data, protocol=4)

# Explicitly use Py2-compatible protocol
pickle_bytes = pickle.dumps(data, protocol=2)  # Py2 can unpickle!

# Unpickling Py2 pickles (may work)
loaded = pickle.loads(pickle_bytes_from_py2)  # Works if protocol 2-3

# Unpickling Py3 protocol 3+ in Py2 FAILS
# (Py2 doesn't understand protocol 3)
```

### Risk Level
**MEDIUM** — Pickle compatibility issues break data loading.

### Detection Approach
- Find all `pickle.dumps()` calls; check protocol version
- Find all `pickle.loads()` calls; understand data source
- Check for pickled data stored in files or databases
- Look for cross-process or cross-version communication

### Migration Strategy
1. **Use protocol 2 for compatibility**: `pickle.dumps(data, protocol=2)`
2. **Store protocol version**: Save metadata about pickle protocol
3. **Migrate old data**: Unpickle in Py2, re-pickle in Py3 with protocol 2
4. **Use other formats**: JSON, MessagePack, protobuf for cross-version data

### Common Patterns
```python
# Py2: Save pickle (default protocol 2)
with open("data.pkl", "wb") as f:
    pickle.dump(data, f)

# Py3: Load pickle (may fail if protocol 3)
with open("data.pkl", "rb") as f:
    data = pickle.load(f)

# Py3: Explicit protocol 2 (Py2 compatible)
with open("data.pkl", "wb") as f:
    pickle.dump(data, f, protocol=2)

# Py3: Load Py2 pickles
with open("data.pkl", "rb") as f:
    data = pickle.load(f)  # Works if protocol 0-2

# Py2/3 compatible approach
def save_pickle(filename, data):
    with open(filename, "wb") as f:
        pickle.dump(data, f, protocol=2)

def load_pickle(filename):
    with open(filename, "rb") as f:
        return pickle.load(f)
```

### Notes/Gotchas
- **Protocol 0**: Text-based, readable, but slow and large. Use only for debugging.
- **Protocol 2**: Binary, default in Py2.3+, compatible with Py3.
- **Protocol 3+**: Binary, Py3-only, not readable by Py2.
- **Custom objects**: Pickled custom class instances may fail to unpickle if class definition changes.
- **Alternative formats**: JSON, JSON Lines, MessagePack for cross-language/cross-version serialization.

---

## 10. Hash Randomization

**Category**: Dictionary/Set Behavior

**Description**: Python 3.3+ enables hash randomization by default (PYTHONHASHSEED). This means dict/set iteration order is unpredictable (unless Python 3.7+, where insertion order is guaranteed). Hash values change between runs.

### Python 2 Behavior
```python
# Consistent hash values across runs
hash("hello")  # Same hash each run

# Dict iteration order is consistent
d = {'a': 1, 'b': 2, 'c': 3}
list(d.keys())  # ['a', 'b', 'c'] (consistent, depends on insertion)

# Set iteration order is consistent
s = {1, 2, 3, 4, 5}
list(s)  # Consistent order (but not guaranteed)

# Tests can rely on dict order (fragile!)
def test_dict_order():
    d = {}
    d['x'] = 1
    d['y'] = 2
    assert list(d.keys()) == ['x', 'y']  # Works in Py2
```

### Python 3 Behavior
```python
# Hash values change between runs (randomization)
hash("hello")  # Different each run by default
# But consistent within same run

# Dict insertion order is GUARANTEED (Py3.7+)
d = {'a': 1, 'b': 2, 'c': 3}
list(d.keys())  # ['a', 'b', 'c'] (guaranteed insertion order)

# Set iteration order is unpredictable (no order guarantee)
s = {1, 2, 3, 4, 5}
list(s)  # Different order each run (unless PYTHONHASHSEED set)

# Tests must not assume dict/set order
def test_dict_order():
    d = {}
    d['x'] = 1
    d['y'] = 2
    assert set(d.keys()) == {'x', 'y'}  # Use set, not list!

# Disable hash randomization (for testing/debugging)
# PYTHONHASHSEED=0 python script.py  # Deterministic hashes
```

### Risk Level
**MEDIUM** — Tests fail intermittently; logic assuming dict order breaks.

### Detection Approach
- Find test assertions on dict/set order: `assert d.keys() == [...]`
- Look for code relying on set ordering: `set([...]) == set([...])`
- Check for hash-dependent logic
- Look for performance-sensitive code (hash collisions timing)

### Migration Strategy
1. **Don't assume set order**: Use set equality, not list equality
2. **Rely on insertion order for dicts** (Py3.7+): Now guaranteed
3. **Use PYTHONHASHSEED for deterministic testing**: `PYTHONHASHSEED=0`
4. **Fix flaky tests**: Replace order assertions with set/dict equality

### Common Patterns
```python
# Py2: Test assumes dict order (flaky in Py3)
def test_dict():
    d = {}
    d['a'] = 1
    d['b'] = 2
    assert list(d.keys()) == ['a', 'b']

# Py3: Better (order-independent)
def test_dict():
    d = {}
    d['a'] = 1
    d['b'] = 2
    assert set(d.keys()) == {'a', 'b'}
    # OR for insertion order (Py3.7+):
    assert list(d.keys()) == ['a', 'b']  # Now guaranteed

# Py2: Fragile test with sets
def test_set():
    s = {1, 2, 3}
    assert list(s) == [1, 2, 3]

# Py3: Order-independent
def test_set():
    s = {1, 2, 3}
    assert s == {1, 2, 3}  # Correct way
    # NOT: assert list(s) == [1, 2, 3]

# Deterministic test run
# In Py3: PYTHONHASHSEED=0 python -m pytest tests/
```

### Notes/Gotchas
- **PYTHONHASHSEED=0**: Disables randomization for testing; default is random seed.
- **Dict insertion order (Py3.7+)**: Now guaranteed; earlier versions don't guarantee.
- **Sets have no order**: Never rely on set iteration order (unpredictable).
- **Performance**: Hash randomization prevents hash collision attacks (security feature).

---

## 11. Unicode Normalization

**Category**: Text Processing

**Description**: Python 3 handles Unicode normalization differently. Two strings that look identical may have different byte representations (NFC vs NFD). This affects file path handling, string comparison, and text processing.

### Python 2 Behavior
```python
# Unicode normalization not automatic
text1 = u"café"  # NFC (composed: é is one character)
text2 = u"café"  # NFD (decomposed: e + accent)

text1 == text2  # False! (different byte sequences)

# File paths (depends on filesystem and OS)
# macOS: HFS+ stores as NFD (decomposed)
# Linux/Windows: No normalization

# String comparison must normalize first
import unicodedata
text1_nfc = unicodedata.normalize("NFC", text1)
text2_nfc = unicodedata.normalize("NFC", text2)
text1_nfc == text2_nfc  # True (after normalization)
```

### Python 3 Behavior
```python
# Same behavior as Py2 (no automatic normalization)
text1 = "café"  # NFC (composed)
text2 = "café"  # NFD (decomposed)

text1 == text2  # False! (different sequences)

# File paths (OS-dependent, no change)
# macOS: Still uses NFD
# Linux/Windows: No normalization

# Still must normalize for comparison
import unicodedata
text1_nfc = unicodedata.normalize("NFC", text1)
text2_nfc = unicodedata.normalize("NFC", text2)
text1_nfc == text2_nfc  # True

# But Py3 makes it easier (all text is Unicode by default)
# In Py2: text1 = "café" is bytes, must decode first
```

### Risk Level
**LOW-MEDIUM** — Usually not an issue unless comparing filenames or normalizing user input.

### Detection Approach
- Look for string comparisons involving accented characters
- Check filename handling (especially macOS)
- Find unicode-intensive code (natural language processing)
- Look for user input validation with accents

### Migration Strategy
1. **Normalize consistently**: Use NFC for internal storage/comparison
2. **Handle macOS file paths**: Normalize NFD (from filesystem) to NFC
3. **Document encoding/normalization**: Explain assumptions
4. **Test with accented characters**: Test é, ñ, ü, etc.

### Common Patterns
```python
# Py2: Must handle bytes/unicode separately
import unicodedata

def normalize_text(text):
    if isinstance(text, str):
        text = text.decode('utf-8')
    return unicodedata.normalize("NFC", text)

# Py3: All text is Unicode
import unicodedata

def normalize_text(text):
    return unicodedata.normalize("NFC", text)

# File path handling (macOS issue)
import os
import unicodedata

def normalize_path(path):
    # macOS returns NFD, normalize to NFC for consistency
    if isinstance(path, bytes):
        path = path.decode('utf-8')
    return unicodedata.normalize("NFC", path)

# String comparison with accents
text1 = "café"
text2 = "café"

if unicodedata.normalize("NFC", text1) == unicodedata.normalize("NFC", text2):
    print("Strings are equal")
```

### Notes/Gotchas
- **NFC vs NFD**: NFC (composed) is preferred for storage; NFD (decomposed) used by macOS.
- **Case sensitivity**: Normalization doesn't affect case; use `.lower()` separately if needed.
- **Regex**: Regex patterns may behave differently depending on normalization.
- **Database indexes**: Text comparison in databases may fail if normalization differs.

---

## 12. Exception Chaining and Scope

**Category**: Error Handling

**Description**: Python 3 supports explicit exception chaining (`raise X from Y`). More importantly, exception variables are automatically deleted after the except block, preventing circular references.

### Python 2 Behavior
```python
# Exception variable persists
try:
    1 / 0
except ZeroDivisionError as e:
    print e
    handle_error(e)

print e  # Still accessible (e persists)

# No explicit exception chaining (implicit implicit)
try:
    do_something()
except ValueError:
    raise TypeError("Wrong type")  # Original exception lost
```

### Python 3 Behavior
```python
# Exception variable deleted after except block
try:
    1 / 0
except ZeroDivisionError as e:
    print(e)
    handle_error(e)

print(e)  # NameError! (e deleted after except block)

# Explicit exception chaining (preserves context)
try:
    do_something()
except ValueError as e:
    raise TypeError("Wrong type") from e  # Preserves ValueError

# Implicit exception chaining (if exception raised in except block)
try:
    do_something()
except ValueError as e:
    try:
        handle()
    except IOError:
        raise TypeError("Error handling")  # ValueError implicit context

# Access exception context
try:
    do_something()
except Exception as e:
    print(e.__cause__)  # Explicitly chained exception (from X)
    print(e.__context__)  # Implicitly chained exception
```

### Risk Level
**LOW-MEDIUM** — Exception variable scope change; chaining is a feature, not a breaking change.

### Detection Approach
- Find references to exception variables outside except block: `except E as e: ...; use(e)`
- Look for exception handling code relying on exception variables
- Check for nested exception handling with implicit chaining

### Migration Strategy
1. **Don't use exception variable outside except block**: If needed, save it: `saved_exc = e`
2. **Use exception chaining**: `raise NewError() from original_error`
3. **Don't suppress exceptions silently**: Always preserve chain for debugging
4. **Update error logging**: Log both original and new exceptions

### Common Patterns
```python
# Py2: Exception variable used outside except block (fragile)
exc = None
try:
    do_something()
except Exception as e:
    exc = e

if exc:  # Use saved exception
    log_error(exc)

# Py3: Same pattern (save exception if needed)
exc = None
try:
    do_something()
except Exception as e:
    exc = e

if exc:
    log_error(exc)

# Py3: Explicit chaining (cleaner)
def process():
    try:
        load_data()
    except IOError as e:
        raise RuntimeError("Failed to load data") from e

# Py3: Implicit chaining (automatic)
def process():
    try:
        load_data()
    except IOError:
        try:
            log_error()
        except Exception:
            raise RuntimeError("Failed to load data")
            # IOError implicitly chained
```

### Notes/Gotchas
- **Circular references**: Py3 deletes exception variables to prevent circular refs (memory leak in Py2).
- **Exception chaining**: `from e` preserves original for debugging; `from None` suppresses chaining.
- **Traceback**: Use `traceback` module to print full chain including causes.

---

## 13. Keyword-Only Arguments

**Category**: Function Parameters

**Description**: Python 3 allows keyword-only arguments (arguments that MUST be passed by name, not position). Python 2 doesn't support this syntax (though it can be simulated).

### Python 2 Behavior
```python
# All arguments can be positional
def greet(name, greeting="Hello"):
    print greeting, name

greet("Alice")  # Works
greet("Alice", "Hi")  # Works
greet("Alice", greeting="Hi")  # Works

# No keyword-only arguments (must use *args / **kwargs)
def query(sql, **options):
    limit = options.get("limit", 10)
    offset = options.get("offset", 0)

query("SELECT * FROM users")
query("SELECT * FROM users", limit=5)
query("SELECT * FROM users", limit=5, offset=10)
```

### Python 3 Behavior
```python
# Keyword-only arguments after *
def greet(name, *, greeting="Hello"):
    print(greeting, name)

greet("Alice")  # Works
greet("Alice", "Hi")  # TypeError! Too many positional arguments
greet("Alice", greeting="Hi")  # Works (correct syntax)

# More explicit
def query(sql, *, limit=10, offset=0):
    # limit and offset MUST be passed by name

query("SELECT * FROM users")  # Works
query("SELECT * FROM users", 5)  # TypeError! Can't pass limit positionally
query("SELECT * FROM users", limit=5)  # Works

# Mixed positional and keyword-only
def process(data, *, validate=True, normalize=False):
    # data is positional, validate/normalize are keyword-only
    pass

process(my_data)  # Works
process(my_data, True)  # TypeError! validate must be keyword
process(my_data, validate=True)  # Works
```

### Risk Level
**LOW** — Feature addition in Py3; Py2 code doesn't use it.

### Detection Approach
- No detection needed; this is a Py3 feature for new code
- May help refactor Py2 code using **kwargs to be more explicit

### Migration Strategy
1. **Use keyword-only args for clarity**: `def api_call(url, *, timeout=30, retries=3)`
2. **Convert **kwargs patterns**: Replace complex option handling with keyword-only args
3. **Document required kwargs**: Make parameters explicit rather than hidden in **options

### Common Patterns
```python
# Py2: Options hidden in **kwargs (unclear API)
def fetch(url, **options):
    timeout = options.get("timeout", 30)
    retries = options.get("retries", 3)
    verify_ssl = options.get("verify_ssl", True)

# Py3: Explicit keyword-only arguments (clear API)
def fetch(url, *, timeout=30, retries=3, verify_ssl=True):
    pass

# Py2: Positional arguments can be confusing
def sort_records(records, reverse=False, key=None):
    # Did user intend key or positional by accident?

# Py3: Clearer
def sort_records(records, *, reverse=False, key=None):
    # reverse and key MUST be passed by name
```

### Notes/Gotchas
- **Backward compatibility**: Py3 keyword-only args are stricter; existing code passing by position breaks.
- **Default values**: Keyword-only args can have defaults or be required.
- **Self-documenting**: Keyword-only args make function signatures clearer.

---

## 14. Function Annotations

**Category**: Function Metadata

**Description**: Python 3 allows function annotations (type hints and metadata). Python 2 doesn't support this syntax.

### Python 2 Behavior
```python
# No annotations (type information in comments or docstrings)
def greet(name, greeting="Hello"):
    """Greet a person.
    
    Args:
        name (str): Person's name
        greeting (str): Greeting message
    
    Returns:
        str: Greeting message with name
    """
    return "{0} {1}".format(greeting, name)

# No type checking; must use docstrings or comments
def process(data):  # data should be list/dict
    return data
```

### Python 3 Behavior
```python
# Function annotations (optional, not enforced)
def greet(name: str, greeting: str = "Hello") -> str:
    """Greet a person."""
    return f"{greeting} {name}"

# Annotations accessible at runtime
print(greet.__annotations__)
# {'name': <class 'str'>, 'greeting': <class 'str'>, 'return': <class 'str'>}

# Annotations can be any expression
def process(data: list | dict) -> None:
    pass

# Type checking tools (mypy, pyright) use annotations
def add(a: int, b: int) -> int:
    return a + b

# Complex annotations
from typing import List, Dict, Optional

def query(filters: Dict[str, Any], limit: Optional[int] = 10) -> List[dict]:
    pass

# Note: Annotations are NOT enforced at runtime
def strict_greet(name: int) -> str:
    return f"Hello {name}"

# Calling with wrong type doesn't raise an error (no enforcement)
result = strict_greet("Alice")  # Works! (passes str, expects int)
```

### Risk Level
**LOW** — Feature addition; existing code unaffected.

### Detection Approach
- Not a breaking change; this is a Py3 feature
- May use type hints for static analysis during migration

### Migration Strategy
1. **Add type hints gradually**: Use `from typing import ...` for complex types
2. **Use type checkers**: mypy, pyright, pytype for static type checking
3. **Document intentions**: Type hints document function contracts
4. **Keep annotations simple**: Use built-in types; complex hints can be verbose

### Common Patterns
```python
# Py2: Type information in docstrings
def divide(numerator, denominator):
    """Divide two numbers.
    
    Args:
        numerator (int/float): Number to divide
        denominator (int/float): Number to divide by
    
    Returns:
        float: Result of division
    """
    return numerator / denominator

# Py3: Type hints (clearer to tools)
def divide(numerator: float, denominator: float) -> float:
    """Divide two numbers."""
    return numerator / denominator

# Py3: Complex types (from typing module)
from typing import List, Dict, Union, Optional

def process(items: List[str], config: Dict[str, Any]) -> Optional[str]:
    pass

def handle(value: Union[int, str]) -> None:
    pass
```

### Notes/Gotchas
- **Not enforced**: Type hints are for tools, not runtime checks.
- **Typing module**: Complex type hints require `from typing import ...`.
- **PEP 484**: Standard for function annotations and type hints.
- **Static checkers**: mypy, pyright, pytype read annotations for type checking.
- **Runtime overhead**: Minimal; annotations don't add execution cost.

---

## 15. Generator Return Values

**Category**: Generator Behavior

**Description**: In Python 2, returning from a generator is an error. In Python 3, generators can return values using `raise StopIteration` with value. The `return` statement in a generator (Py3.3+) returns a value via `StopIteration`.

### Python 2 Behavior
```python
# Returning from generator raises SyntaxError
def gen():
    yield 1
    yield 2
    return  # Just exit (SyntaxError in some contexts)

# Generators can't return values
def fibonacci():
    a, b = 0, 1
    while True:
        yield a
        a, b = b, a + b

# No way to return final value from generator
```

### Python 3 Behavior
```python
# Generators can return values (Py3.3+)
def gen():
    yield 1
    yield 2
    return "done"  # Returns value via StopIteration

# Consume with explicit return catching
def fibonacci(max):
    a, b = 0, 1
    count = 0
    while count < max:
        yield a
        a, b = b, a + b
        count += 1
    return a + b  # Return final value

# Catch return value
gen_obj = fibonacci(5)
try:
    while True:
        value = next(gen_obj)
        print(value)
except StopIteration as e:
    print("Final:", e.value)

# Or use yield from (Py3.3+)
def delegator():
    return (yield from fibonacci(5))

# async/await generators also support return values
async def async_gen():
    yield 1
    return "done"
```

### Risk Level
**LOW** — Py2 code doesn't use generator return values (not supported).

### Detection Approach
- Look for `return` statements in generators
- Check generator usage expecting return values
- Identify generators with meaningful final state

### Migration Strategy
1. **Return values from generators** (Py3.3+): Use `return value` to provide final result
2. **Catch StopIteration**: Handle returned value via exception
3. **Use yield from**: Delegate to sub-generators while returning values
4. **Document return semantics**: Explain what return value means

### Common Patterns
```python
# Py2: Generator can't return value; must wrap in class
class Generator:
    def __init__(self, seq):
        self.seq = seq
        self.index = 0
    
    def __iter__(self):
        return self
    
    def next(self):
        if self.index >= len(self.seq):
            raise StopIteration
        value = self.seq[self.index]
        self.index += 1
        return value
    
    def get_final(self):
        return self.seq[-1] if self.seq else None

# Py3: Generator with return value
def generator(seq):
    for value in seq:
        yield value
    return seq[-1] if seq else None

# Get return value
gen_obj = generator([1, 2, 3])
values = []
try:
    while True:
        values.append(next(gen_obj))
except StopIteration as e:
    final = e.value
    print(final)  # 3

# Py3.3+: yield from for delegation
def delegator(sequences):
    for seq in sequences:
        yield from seq  # Delegate to generator
    return "done"
```

### Notes/Gotchas
- **StopIteration with value**: `except StopIteration as e:` captures exception; `e.value` accesses return value.
- **yield from**: Delegates to sub-generator and returns its value.
- **for loop doesn't capture return**: `for x in gen():` never sees return value (exception suppressed).
- **Legacy code**: Py2 generators don't return; Py3.3+ feature.

---

## 16. Standard Library Behavior Changes

**Category**: Library Behavior

**Description**: Various standard library modules change behavior between Python 2 and 3.

### Common Changes

| Module | Python 2 | Python 3 | Impact |
|--------|----------|----------|--------|
| `configparser` | `ConfigParser` (case-insensitive) | `configparser` (case-sensitive by default) | Config parsing breaks if case varies |
| `urllib` | `urllib`, `urllib2`, `urlparse` | `urllib.parse`, `urllib.request` | Import statements change |
| `Queue` | `Queue` module | `queue` module (lowercase) | Import statements change |
| `socketserver` | `SocketServer` | `socketserver` | Import statements change |
| `xmlrpc` | `xmlrpclib`, `SimpleXMLRPCServer` | `xmlrpc.client`, `xmlrpc.server` | Import restructuring |
| `html` | Not standard | `html.parser`, `html.entities` | HTML parsing moves |
| `email` | Basic email | Enhanced email module | API slightly different |
| `unittest` | Less features | More features (mock, etc.) | Tests can use more features |

### Risk Level
**MEDIUM** — Import changes are straightforward; behavior changes require careful migration.

### Detection Approach
- Find all imports from renamed/moved modules
- Check `configparser` usage (case sensitivity)
- Look for urllib/urlparse usage (major restructuring)
- Check for other stdlib modules with behavior changes

### Migration Strategy
1. **Use 2to3 fixer**: Automatic for most imports
2. **Test stdlib calls**: Ensure behavior matches
3. **Consider compatibility libraries**: `six`, `future`, `2to3` can help
4. **Document changes**: Note which stdlib modules changed

### Example: configparser
```python
# Py2: Case-insensitive by default
import ConfigParser
config = ConfigParser.ConfigParser()
config.read("config.ini")
value = config.get("section", "KEY")  # Works even if ini has "key"

# Py3: Case-sensitive by default
import configparser
config = configparser.ConfigParser()
config.read("config.ini")
value = config.get("section", "key")  # Must match case exactly

# Py3: To make case-insensitive
config = configparser.RawConfigParser()
# OR override optionxform
config.optionxform = str  # Preserve case
```

### Notes/Gotchas
- **Module renames**: 2to3 handles most; double-check edge cases
- **Behavior changes**: Some modules (configparser, urllib) change behavior, not just structure
- **Compatibility libraries**: `six.moves` helps with imports across versions

---

## 17. os.environ Type

**Category**: OS Module

**Description**: `os.environ` returns bytes in Python 2 (`str` type) and strings in Python 3 (`str` type, Unicode). Environment variable handling differs subtly.

### Python 2 Behavior
```python
import os

# os.environ values are bytes (str type)
path = os.environ["PATH"]  # str (bytes)
type(path)  # <type 'str'>

# Concatenation with strings
full_path = path + ":/usr/local/bin"  # Bytes concatenation

# Decoding needed for Unicode
decoded = path.decode("utf-8")  # unicode type

# Keys are also bytes
for key in os.environ:
    print key  # str (bytes)
```

### Python 3 Behavior
```python
import os

# os.environ values are strings (str type, Unicode)
path = os.environ["PATH"]  # str (Unicode text)
type(path)  # <class 'str'>

# Concatenation with strings
full_path = path + ":/usr/local/bin"  # Strings (Unicode)

# No decoding needed; already Unicode
# decoded = path.decode("utf-8")  # Not needed

# Keys are also strings
for key in os.environ:
    print(key)  # str (Unicode)
```

### Risk Level
**LOW** — Usually transparent; issues appear with encoding-sensitive operations.

### Detection Approach
- Find `os.environ` usage
- Check for `.encode()` / `.decode()` on environ values
- Look for path operations with environ values

### Migration Strategy
1. **Treat as text (strings)**: No encoding/decoding needed in Py3
2. **Remove unnecessary conversions**: `.decode()` on environ values is unnecessary
3. **Handle missing keys**: Use `.get()` with default

### Common Patterns
```python
# Py2: May need encoding handling
import os
path = os.environ.get("PATH", "")
if path:
    parts = path.decode("utf-8").split(":")

# Py3: Simpler (already Unicode)
import os
path = os.environ.get("PATH", "")
if path:
    parts = path.split(":")

# Py2: May need to encode when setting
os.environ["CUSTOM"] = u"value".encode("utf-8")

# Py3: Just assign strings
os.environ["CUSTOM"] = "value"
```

### Notes/Gotchas
- **Case sensitivity**: Environment variable names are case-sensitive on Unix, case-insensitive on Windows.
- **Missing keys**: `.get()` returns `None` if missing; accessing directly raises `KeyError`.
- **Persistence**: Changes to `os.environ` don't affect parent process or new processes.

---

## 18. Subprocess Default Encoding

**Category**: Subprocess Module

**Description**: The `subprocess` module returns bytes in Python 2 and strings (decoded text) in Python 3 by default.

### Python 2 Behavior
```python
import subprocess

# Output is bytes (str type)
result = subprocess.check_output(["echo", "hello"])
type(result)  # <type 'str'>
result  # 'hello\n' (bytes)

# Pipe returns bytes
process = subprocess.Popen(["ls"], stdout=subprocess.PIPE)
output, error = process.communicate()
type(output)  # <type 'str'> (bytes)

# Must decode to get text
text = output.decode("utf-8")
```

### Python 3 Behavior
```python
import subprocess

# Output is bytes by default (same as Py2)
result = subprocess.check_output(["echo", "hello"])
type(result)  # <class 'bytes'>
result  # b'hello\n' (bytes)

# Text mode available
result = subprocess.check_output(["echo", "hello"], universal_newlines=True)
type(result)  # <class 'str'>
result  # 'hello\n' (text)

# Or use text parameter (Py3.7+)
result = subprocess.check_output(["echo", "hello"], text=True)
type(result)  # <class 'str'>

# Pipe with text mode
process = subprocess.Popen(["ls"], stdout=subprocess.PIPE, text=True)
output, error = process.communicate()
type(output)  # <class 'str'> (text)
```

### Risk Level
**LOW** — Default behavior same (bytes); text mode is cleaner in Py3.

### Detection Approach
- Find `subprocess.check_output()`, `Popen()`, `run()` calls
- Check if output is decoded or used as bytes
- Look for `.decode()` calls on subprocess output

### Migration Strategy
1. **Keep bytes if needed**: Default behavior (same in both)
2. **Use text mode for text**: `universal_newlines=True` (Py2/3 compatible) or `text=True` (Py3.7+)
3. **Remove unnecessary decoding**: If using text mode, no decoding needed
4. **Handle encoding explicitly**: `encoding='utf-8'` if needed

### Common Patterns
```python
# Py2: Output is bytes, decode if needed
import subprocess
output = subprocess.check_output(["python", "-c", "print('hello')"])
text = output.decode("utf-8").strip()

# Py3: Can use text mode (cleaner)
output = subprocess.check_output(["python", "-c", "print('hello')"], text=True)
text = output.strip()

# Py2/3 compatible (use universal_newlines)
output = subprocess.check_output(["ls"], universal_newlines=True)

# Binary output (same in both)
output = subprocess.check_output(["ls"], stdout=subprocess.PIPE)
# output is bytes, no automatic decoding
```

### Notes/Gotchas
- **universal_newlines**: Py2/3 compatible; makes subprocess return text
- **text parameter**: Py3.7+; cleaner than universal_newlines
- **encoding parameter**: Specify encoding explicitly if needed: `encoding='utf-8'`
- **stderr handling**: Apply same logic to stderr

---

## 19. Regular Expression Flags

**Category**: Regex Behavior

**Description**: Regular expression flags (`re.UNICODE` default, `re.ASCII`) have different behaviors between Python 2 and 3.

### Python 2 Behavior
```python
import re

# re.U (UNICODE) must be explicit
pattern = re.compile(r"\w+")  # Matches [a-zA-Z0-9_] (ASCII)
pattern = re.compile(r"\w+", re.UNICODE)  # Matches Unicode word chars

# re.ASCII doesn't exist
# \d, \w, \s match ASCII by default

# Case-insensitive
pattern = re.compile(r"\w+", re.IGNORECASE | re.UNICODE)
```

### Python 3 Behavior
```python
import re

# re.UNICODE is default (when pattern is str)
pattern = re.compile(r"\w+")  # Matches Unicode word chars by default
pattern = re.compile(r"\w+", re.UNICODE)  # Explicit, same as above

# re.ASCII forces ASCII-only (new in Py3)
pattern = re.compile(r"\w+", re.ASCII)  # Matches [a-zA-Z0-9_] only

# With bytes pattern, ASCII is default
pattern = re.compile(rb"\w+")  # ASCII by default (bytes)

# Case-insensitive with UNICODE default
pattern = re.compile(r"\w+", re.IGNORECASE)  # UNICODE is default
```

### Risk Level
**LOW-MEDIUM** — Unicode handling changes; affects non-ASCII patterns.

### Detection Approach
- Find `re.compile()` calls without flags
- Check for patterns expecting ASCII-only (need `re.ASCII`)
- Look for `\w`, `\d`, `\s` in patterns (flag-dependent behavior)

### Migration Strategy
1. **Unicode by default in Py3**: Patterns match Unicode unless `re.ASCII` specified
2. **Explicit flags for clarity**: Use `re.ASCII` if ASCII-only matching needed
3. **Bytes patterns**: Use `re.ASCII` explicitly for consistency
4. **Test with Unicode**: Test patterns with accented characters

### Common Patterns
```python
# Py2: ASCII by default
import re
pattern = re.compile(r"\w+")
pattern.match("café")  # No match (é not ASCII)

# Py3: Unicode by default
pattern = re.compile(r"\w+")
pattern.match("café")  # Matches! (é is Unicode word char)

# Py3: Force ASCII if needed
pattern = re.compile(r"\w+", re.ASCII)
pattern.match("café")  # No match (é not ASCII)

# Py2/3 compatible (explicit)
pattern = re.compile(r"\w+", re.UNICODE)  # Both versions understand

# Bytes pattern (ASCII by default)
pattern = re.compile(rb"\w+")  # ASCII in both versions
pattern.match(b"caf\xc3\xa9")  # No match (bytes \xc3\xa9 is UTF-8 é, not ASCII)
```

### Notes/Gotchas
- **String patterns**: `re.compile(r"...")` in Py3 defaults to UNICODE
- **Bytes patterns**: `re.compile(rb"...")` defaults to ASCII in both versions
- **re.ASCII**: New in Py3; forces ASCII matching for string patterns
- **Locale-dependent**: re.LOCALE flag (not recommended) makes behavior locale-specific

---

## 20. sys.maxint and Numeric Limits

**Category**: Numeric Types

**Description**: Python 2 has `sys.maxint` (maximum value for `int` type); Python 3 removes it since `int` is unlimited.

### Python 2 Behavior
```python
import sys

# sys.maxint is maximum int value
sys.maxint  # 2147483647 (on 32-bit) or 9223372036854775807 (on 64-bit)

# Numbers larger than maxint become long
large = sys.maxint + 1  # type: long

# Check against maxint
if value > sys.maxint:
    print "Value too large"

# sys.maxsize is available (size of container)
sys.maxsize  # Similar to maxint, but for containers
```

### Python 3 Behavior
```python
import sys

# sys.maxint removed (int is unlimited)
sys.maxint  # AttributeError!

# No long type; all numbers are int
large = 10 ** 100  # type: int (unlimited precision)

# sys.maxsize is available (size of largest container)
sys.maxsize  # Largest possible integer for array indexing

# For compatibility checks
try:
    value = int(very_large_string)
except ValueError:
    # Handle bad input, not overflow
    pass
```

### Risk Level
**LOW** — Code checking `sys.maxint` is rare; Py2 code handles overflow naturally.

### Detection Approach
- Search for `sys.maxint` references
- Look for overflow checks or long type handling
- Check for comparisons against maxint

### Migration Strategy
1. **Remove maxint checks**: Python 3 handles large numbers automatically
2. **Use sys.maxsize if needed**: For array/container size limits
3. **Trust unlimited integers**: Don't guard against overflow (unnecessary)

### Common Patterns
```python
# Py2: May check for overflow
import sys

def safe_multiply(a, b):
    if a > sys.maxint // b:
        raise OverflowError("Result too large")
    return a * b

# Py3: No overflow concern (unlimited int)
def safe_multiply(a, b):
    return a * b  # Works for arbitrarily large numbers
```

### Notes/Gotchas
- **sys.maxsize**: Still available in Py3; limits array indexing, not numeric values
- **Numeric overflow**: Py3 doesn't overflow; uses unlimited precision
- **Performance**: Large number arithmetic slower but correct
- **Bitwise operations**: Negative numbers have unlimited bits in Py3

---

## 21. Thread Safety Changes

**Category**: Concurrency

**Description**: Python 3 (3.13+) removes the Global Interpreter Lock (GIL) in some cases; earlier versions keep it. Additionally, some thread-safety guarantees differ.

### Python 2 Behavior
```python
import threading

# GIL (Global Interpreter Lock) enforces single-threaded execution
# Threads are safe from certain data corruption but may not run in parallel

lock = threading.Lock()

# Simple operations like list.append() are atomic (GIL-protected)
shared_list = []

def append_item(item):
    shared_list.append(item)  # Safe: GIL protects

# But operations aren't truly atomic
shared_dict = {}

def increment(key):
    # This is NOT atomic! Race condition:
    # 1. Read value
    # 2. Increment
    # 3. Write value
    if key not in shared_dict:
        shared_dict[key] = 0
    shared_dict[key] += 1

# Multiple threads calling increment() can lose updates
```

### Python 3 Behavior
```python
import threading

# GIL still present (except 3.13+)
lock = threading.Lock()

# Same atomicity guarantees as Py2
shared_list = []

def append_item(item):
    shared_list.append(item)  # Still safe

# Same race conditions as Py2
shared_dict = {}

def increment(key):
    if key not in shared_dict:
        shared_dict[key] = 0
    shared_dict[key] += 1  # Still not atomic!

# Python 3.13+: Experimental GIL removal
# True parallelism possible, but race conditions more common
```

### Risk Level
**MEDIUM** — Thread safety is subtle; most code doesn't have issues.

### Detection Approach
- Find all threading code
- Look for shared mutable state without locks
- Check for compound operations (read-modify-write)
- Find race condition patterns

### Migration Strategy
1. **Use locks for compound operations**: Always protect multi-step operations
2. **Prefer immutable data**: Use tuples, frozensets, or create new objects
3. **Use queue.Queue**: Thread-safe queue for communication
4. **Test with threading**: Use tools like `ThreadSanitizer` to find races

### Common Patterns
```python
# Py2/3: Unsafe without lock
shared_counter = 0
lock = threading.Lock()

def increment_unsafe():
    global shared_counter
    shared_counter += 1  # Race condition!

# Py2/3: Safe with lock
def increment_safe():
    global shared_counter
    with lock:
        shared_counter += 1  # Protected

# Py3: Use threading.local() for thread-local storage
local_data = threading.local()

def thread_func():
    local_data.value = 42  # Only visible in this thread
    # Other threads have their own local_data.value
```

### Notes/Gotchas
- **GIL**: Protects from some issues but not all; doesn't make code thread-safe
- **Atomic operations**: Single bytecode operations are atomic; multi-step operations are not
- **Python 3.13+**: Experimental GIL removal; true parallelism requires more careful coding
- **asyncio**: Async/await is often better than threading for I/O-bound code

---

## 22. open() Default Encoding

**Category**: I/O Encoding

**Description**: Python 3's `open()` uses platform default encoding (not ASCII). On Windows, this is often `cp1252`; on Unix, often `utf-8`. This causes silent encoding failures.

### Python 2 Behavior
```python
# open() returns binary mode (no encoding)
f = open("file.txt")
content = f.read()  # str (bytes)
# Encoding: binary (unchanged)

# Must explicitly handle encoding
f = open("file.txt", "rb")
content_bytes = f.read()
content_text = content_bytes.decode("utf-8")
```

### Python 3 Behavior
```python
# open() returns text mode with default encoding
f = open("file.txt")
content = f.read()  # str (text, platform default encoding)

# Platform encoding varies!
# Windows: Often cp1252 (Windows-1252)
# Linux: Often utf-8
# macOS: Often utf-8

# If file is UTF-8 but system default is cp1252:
# UnicodeDecodeError!

# Solution: Always specify encoding
f = open("file.txt", encoding="utf-8")
content = f.read()  # Consistent across platforms
```

### Risk Level
**MEDIUM-HIGH** — Silent encoding errors; portable code breaks on different systems.

### Detection Approach
- Find all `open()` calls
- Check if encoding is specified
- Look for platform-specific tests or bugs
- Search for files assuming UTF-8

### Migration Strategy
1. **ALWAYS specify encoding**: `open(file, encoding="utf-8")`
2. **Use UTF-8 universally**: Most portable choice
3. **Handle encoding errors gracefully**: `errors='replace'` or `errors='ignore'`
4. **Test on multiple platforms**: Windows, Linux, macOS

### Common Patterns
```python
# Py2: No encoding specified (binary by default)
with open("config.txt") as f:
    config = json.load(f)

# Py3: Must specify encoding (platform-dependent default)
with open("config.txt", encoding="utf-8") as f:
    config = json.load(f)

# Py2: Binary mode explicit
with open("data.bin", "rb") as f:
    data = f.read()

# Py3: Same, but note encoding not applicable
with open("data.bin", "rb") as f:
    data = f.read()

# Error handling
with open("file.txt", encoding="utf-8", errors="replace") as f:
    # Replace invalid characters with U+FFFD
    content = f.read()

# Try multiple encodings (fallback)
for encoding in ["utf-8", "cp1252", "iso-8859-1"]:
    try:
        with open("file.txt", encoding=encoding) as f:
            content = f.read()
        break
    except UnicodeDecodeError:
        continue
else:
    raise ValueError("Could not decode file")
```

### Notes/Gotchas
- **Default encoding**: Use `locale.getpreferredencoding(False)` to see system default
- **Newline handling**: Py3 text mode auto-converts `\r\n` ↔ `\n`; `newline=''` disables conversion
- **Errors parameter**: `errors='ignore'` silently drops bad characters; `errors='replace'` uses U+FFFD
- **JSON files**: `json.load()` in Py3 expects text file (not bytes)

---

## Summary

The most dangerous semantic changes are:

1. **String/Bytes type system** (HIGH): Fundamental type separation; mixing types raises `TypeError`
2. **Integer division** (HIGH): `/` returns float; use `//` for floor division
3. **File I/O encoding** (MEDIUM-HIGH): Platform-dependent; always specify encoding
4. **Dictionary iteration** (MEDIUM): Views aren't lists; indexing breaks
5. **Map/Filter/Zip iterators** (MEDIUM): Single-pass; convert to list if needed

All of these require careful migration and thorough testing to avoid silent failures.

