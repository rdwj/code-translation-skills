# Serialization Migration Reference

Guide for migrating Python 2 serialization (pickle, marshal, shelve) to Python 3.
Used by the Data Format Analyzer (0.2) and Serialization Boundary Detector (0.3).

## Table of Contents

1. [The Core Problem](#core-problem)
2. [Pickle Migration](#pickle)
3. [Marshal Migration](#marshal)
4. [Shelve Migration](#shelve)
5. [JSON / YAML (Low Risk)](#json-yaml)
6. [Custom Serialization](#custom)
7. [Migration Strategy](#strategy)

---

## The Core Problem

In Python 2, `str` is bytes. In Python 3, `str` is text (Unicode). When Python 2
pickles a `str` object, it stores it as a byte string. When Python 3 unpickles that
same data, it gets `bytes` instead of `str`.

This means: **any pickled data created by Python 2 will behave differently when
loaded by Python 3.**

```python
# Python 2: pickle a str
import pickle
data = {"name": "sensor-1", "value": 42}
pickle.dump(data, open("data.pkl", "wb"))
# "name" and "sensor-1" are str (bytes) in the pickle

# Python 3: load the same pickle
import pickle
data = pickle.load(open("data.pkl", "rb"))
# data = {b"name": b"sensor-1", b"value": 42}
# Keys and string values are now bytes!
```

---

## Pickle

### Protocol Versions

| Protocol | Python Version | Notes |
|----------|---------------|-------|
| 0 | 2.0+ | ASCII, human-readable |
| 1 | 2.0+ | Binary, more compact |
| 2 | 2.3+ | New-style classes |
| 3 | 3.0+ | bytes/str distinction, Py3 only |
| 4 | 3.4+ | Large objects, more types |
| 5 | 3.8+ | Out-of-band data |

**Key point**: Protocol 0, 1, and 2 pickles created by Python 2 can be loaded by
Python 3, but `str` objects will become `bytes`.

### Loading Py2 Pickles in Py3

Python 3's `pickle.load()` accepts an `encoding` parameter specifically for loading
Python 2 pickles:

```python
# Load Py2 pickle with str→str conversion (not bytes)
data = pickle.load(open("py2_data.pkl", "rb"), encoding='latin-1')

# Load Py2 pickle keeping original bytes
data = pickle.load(open("py2_data.pkl", "rb"), encoding='bytes')
# This is the DEFAULT — str becomes bytes

# The encoding parameter only affects Py2 str objects:
# - encoding='latin-1': Py2 str → Py3 str (lossless for any byte value)
# - encoding='ascii': Py2 str → Py3 str (fails on non-ASCII bytes)
# - encoding='bytes': Py2 str → Py3 bytes (the default)
# - encoding='utf-8': Py2 str → Py3 str (fails on non-UTF-8 bytes)
```

### Which Encoding to Use?

| If the Py2 str contained... | Use encoding= | Notes |
|------------------------------|--------------|-------|
| ASCII text only | `'ascii'` or `'latin-1'` | Both work |
| UTF-8 text | `'utf-8'` | Will fail on non-UTF-8 |
| Arbitrary bytes (binary data) | `'bytes'` (default) | Keep as bytes |
| Mixed text and binary | `'latin-1'` | Lossless, then sort out later |
| Unknown | `'latin-1'` | Safest default |

### Common Pickle Patterns in Legacy Code

```python
# Pattern 1: cPickle (Py2 C-accelerated pickle)
import cPickle  # ImportError on Py3
# Fix: import pickle (Py3 automatically uses C implementation)

# Pattern 2: Protocol not specified (defaults to 0 in Py2)
pickle.dump(obj, f)  # Uses protocol 0 in Py2, highest available in Py3
# Fix: pickle.dump(obj, f, protocol=2)  # if interop needed

# Pattern 3: String mode file open
pickle.dump(obj, open("data.pkl", "w"))  # Py2 allows 'w' for protocol 0
# Fix: Must use 'wb' in Py3 for all protocols

# Pattern 4: pickle.loads with str argument
data = pickle.loads(some_string)  # Py2: str is bytes, fine
# Py3: must pass bytes, not str
```

### Classes and Pickle

If the pickled data contains class instances, the class must be importable
at the same module path when unpickling. Py2→Py3 module renames break this:

```python
# Py2 pickled an object from module 'ConfigParser'
# Py3 renamed it to 'configparser'
# → UnpicklingError: No module named 'ConfigParser'

# Fix: use pickle's find_class mechanism
import pickle
class Py2Unpickler(pickle.Unpickler):
    def find_class(self, module, name):
        # Map Py2 module names to Py3 equivalents
        renames = {
            'ConfigParser': 'configparser',
            'Queue': 'queue',
            'copy_reg': 'copyreg',
        }
        module = renames.get(module, module)
        return super().find_class(module, name)
```

---

## Marshal

### Why Marshal is Dangerous

`marshal` is used internally by Python to serialize `.pyc` files. Its format is
**version-specific** — marshal data from one Python version is NOT guaranteed to
load on another.

```python
# Python 2.7
import marshal
data = marshal.dumps({"key": "value"})
# This data may not load on Python 3.x

# marshal format version changes:
# Python 2.7: format version 2
# Python 3.4+: format version 4
# Python 3.13+: format version 5
```

### Migration Strategy for Marshal

1. **Identify all marshal usage**: It's rare in application code (mostly used by
   the Python compiler). If found, it's a red flag.
2. **Convert to pickle or JSON before migration**: Load with Py2, re-serialize in
   a portable format.
3. **If marshal data is in .pyc files**: Just delete them. Python regenerates .pyc files.
4. **If marshal data is in application data stores**: This is a data migration task — the
   data must be converted before the code migration.

---

## Shelve

### How Shelve Works

`shelve` is a persistent dictionary backed by `dbm` and `pickle`. Opening a shelve
database loads keys (which are always strings) and values (which are pickled objects).

```python
import shelve
db = shelve.open('mydata')
db['sensor_1'] = {'temp': 25.5, 'status': 'ok'}
db.close()
```

### Shelve Migration Issues

1. **Keys are str in Py2 (bytes) and str in Py3 (text)**: The underlying dbm
   database stores keys as bytes. Python 3's shelve handles this, but if application
   code stores keys from external sources, encoding matters.

2. **Values are pickled**: All the pickle migration issues apply to every value in
   the shelve database.

3. **dbm backend compatibility**: The dbm backend used by shelve varies by platform
   (gdbm, ndbm, bdb). The database file format may or may not be compatible between
   Py2 and Py3 on the same platform.

### Shelve Migration Strategy

```python
# Step 1: Export with Py2
import shelve, json
db = shelve.open('mydata')
export = {}
for key in db:
    export[key] = db[key]
json.dump(export, open('mydata_export.json', 'w'))
db.close()

# Step 2: Import with Py3
import shelve, json
data = json.load(open('mydata_export.json'))
db = shelve.open('mydata_v3')
for key, value in data.items():
    db[key] = value
db.close()
```

Note: This only works if the values are JSON-serializable. For complex objects,
use Py2 pickle → JSON → Py3 pickle, or use the encoding parameter approach
described in the Pickle section.

---

## JSON / YAML (Low Risk)

JSON and YAML are text-based formats and are generally safe for migration.

### JSON Considerations

```python
# Py2: json.dumps returns str (bytes). json.loads accepts str (bytes) or unicode
# Py3: json.dumps returns str (text). json.loads accepts str (text) or bytes

# The only risk is file I/O:
json.dump(data, open('data.json', 'w'))     # Py2: writes bytes. Py3: writes text
json.load(open('data.json', 'r'))           # Usually fine in both

# Risk: Non-ASCII data in JSON
json.dumps({"name": u"Ñoño"})               # Py2: returns bytes with \u escapes
                                              # Py3: returns str with actual chars
json.dumps({"name": "Ñoño"}, ensure_ascii=False)  # Both: actual Unicode chars
```

### YAML Considerations

```python
# yaml.load() behavior depends on the data types in the YAML:
# - Strings in YAML become unicode in Py2 with proper loading
# - Binary data in YAML (!!binary) becomes bytes in both Py2 and Py3

# Risk: yaml.load() without Loader is deprecated since PyYAML 5.1
yaml.load(data)                              # DeprecationWarning
yaml.safe_load(data)                         # Safe, recommended
yaml.load(data, Loader=yaml.SafeLoader)      # Explicit
```

---

## Custom Serialization

### `__getstate__` / `__setstate__`

Classes that implement `__getstate__` and `__setstate__` control what gets pickled.
These methods may return or expect `str` objects:

```python
class SensorData:
    def __getstate__(self):
        # Py2: returns dict with str keys/values
        return {'name': self.name, 'raw_data': self.raw_bytes}

    def __setstate__(self, state):
        # Py3: state may have bytes keys if loaded from Py2 pickle
        self.name = state.get('name') or state.get(b'name')
        self.raw_data = state.get('raw_data') or state.get(b'raw_data')
```

### `__reduce__` / `__reduce_ex__`

These methods control how an object is reconstructed during unpickling.
If they reference Py2-specific types or modules, unpickling will fail on Py3.

---

## Migration Strategy

### Step 1: Inventory

Run the Data Format Analyzer to find all serialization points. For each one, answer:
- What format? (pickle, marshal, shelve, json, yaml, custom)
- Does persisted data exist that was created by Python 2?
- Where is that data stored? (files, databases, caches, network)
- What object types are serialized?
- Are there any custom `__getstate__`/`__setstate__` or `__reduce__` methods?

### Step 2: Classify Risk

| Scenario | Risk | Action |
|----------|------|--------|
| JSON/YAML, no persisted data | Low | Just update code |
| Pickle, no persisted Py2 data | Medium | Update code, set protocol |
| Pickle, Py2 data exists, simple types | Medium | Use `encoding='latin-1'` |
| Pickle, Py2 data exists, custom classes | High | Write migration script |
| Marshal, data exists | Critical | Convert before migration |
| Shelve, data exists | High | Export/reimport |

### Step 3: Data Migration Plan

For High and Critical risk items, write a data migration script that:
1. Loads data under Python 2 (or Py3 with compat flags)
2. Converts all `str`→`bytes` / `str`→`str` as appropriate
3. Re-serializes in a Py3-native format
4. Verifies round-trip correctness

### Step 4: Update Code

- `cPickle` → `pickle`
- Add `encoding=` parameter to `pickle.load()` / `pickle.loads()` where loading
  Py2 data
- Set explicit `protocol=` in `pickle.dump()` / `pickle.dumps()`
- Replace `marshal` with `pickle` or `json` unless marshal is specifically needed
- Update shelve to use new database files if the dbm backend isn't compatible
