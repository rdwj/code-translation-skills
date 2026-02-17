---
name: py2to3-serialization-detector
description: >
  Identifies all serialization/deserialization points in a Python 2 codebase (pickle, marshal,
  shelve, json, yaml, msgpack, protobuf, struct-based custom, __getstate__/__setstate__),
  assesses Py2→Py3 data compatibility risk, and scans for persisted data files. Use this skill
  when you need to understand data persistence mechanisms, assess binary format migration risk,
  find unsafe pickle usage, or plan data migration strategy. Also trigger when someone says
  "find serialization," "check pickle usage," "what data formats are used," "assess data
  compatibility," or "scan for persisted data files."
---

# Skill 0.3: Serialization Boundary Detector

## Why Serialization Matters for Py2→Py3 Migration

Serialization is the highest-risk area of Python 2→3 migration. Here's why:

- **Data format mismatch**: Py2 pickles contain `str` (bytes) objects. Py3 pickles expect
  `str` (unicode) objects. Loading old pickles with `pickle.load()` (which defaults to
  `protocol=3`) fails because the type signatures don't match.

- **Protocol version issues**: Py2 used protocols 0-2 by default. Py3 uses protocol 3+.
  Old data files in Py2 format must be read with `encoding='latin1'` or `'bytes'`, then
  re-serialized in Py3 format.

- **Custom class serialization**: If your code defines `__getstate__`, `__setstate__`,
  `__reduce__`, or `__reduce_ex__`, Py3's behavior differs. Classes may fail to unpickle.

- **Marshal is unsafe and version-specific**: Python's `marshal` module version-checks on
  load. Py2-marshaled data often won't load in Py3 at all.

- **Shelve and DBM formats**: Both are dependent on the underlying database format (`gdbm`,
  `bdb`, etc.). Py3 may use different defaults, causing incompatibility.

- **Custom binary formats**: Code using `struct.pack/unpack` or hand-crafted binary parsing
  must be audited for encoding assumptions.

This skill finds every serialization boundary and assesses whether existing persisted data
will survive the migration.

---

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| **codebase_path** | User | Root directory of Python 2 codebase |
| **--target-version** | User | Python 3.x target (3.9, 3.11, 3.12, 3.13) |
| **--data-dirs** | User | Directories to scan for .pkl, .shelve, .db files (optional) |
| **--state-file** | User | Path to migration-state.json for integration (optional) |
| **--output** | User | Output directory for reports (default: current dir) |

---

## Outputs

All outputs go into the `--output` directory:

| File | Format | Purpose |
|------|--------|---------|
| `serialization-report.json` | JSON | Complete inventory of all serialization points with risk scores |
| `data-migration-plan.json` | JSON | Step-by-step plan for migrating persisted data |
| `serialization-report.md` | Markdown | Human-readable summary with findings and remediation |

---

## Workflow

### Step 1: Detect Serialization Code Patterns

Run the main detection script:

```bash
python3 scripts/detect_serialization.py <codebase_path> \
    --target-version 3.12 \
    --output ./serialization-output/
```

This walks the codebase and detects 10 categories of serialization usage.

### Step 2: Assess Risk Per Category

For each serialization point found, the script assigns a risk level:

**CRITICAL** (Must fix before migration):
- `marshal` usage anywhere in the codebase
- `pickle.load()` calls without `encoding=` parameter
- Persisted Py2-format pickle files (.pkl, .pickle) found on disk
- `cPickle` imports (must become `pickle`)

**HIGH** (Likely to break, significant work required):
- `shelve` databases (open files, unclear underlying format)
- `pickle.load` without `encoding=` param for custom classes
- Custom `__getstate__`/`__setstate__` methods without Py3 awareness
- `yaml.load()` without `SafeLoader`
- `struct`-based custom serialization mixed with string operations

**MEDIUM** (May break with non-ASCII data, test needed):
- `json` with potential bytes keys or `allow_nan=False`
- `msgpack` with type mapping assumptions
- `protobuf` if custom message definitions exist

**LOW** (Safe, but inventory):
- `json.dumps()`/`json.loads()` (standard text format)
- `yaml.safe_load()`/`yaml.safe_dump()`
- `protobuf` with standard message definitions (versioning is built-in)

### Step 3: Scan for Persisted Data Files

If `--data-dirs` is provided, the script scans the filesystem for actual data files:

- `*.pkl`, `*.pickle` — Pickle archives
- `*.marshal` — Marshal format
- `*.shelve`, `*.db` — Shelve/DBM databases
- `*.dat` — Generic binary files near serialization code (heuristic)

For each file found, assess its format and whether it needs migration.

### Step 4: Generate Migration Plan

The `data-migration-plan.json` contains an ordered list of actions:

```json
{
  "steps": [
    {
      "step_number": 1,
      "action": "Read all pickle files with encoding='latin1'",
      "affected_files": ["src/data_loader.py"],
      "data_files": ["/var/data/cache.pkl"],
      "effort": "low",
      "verify_command": "python3 scripts/test_pickle_load.py /var/data/cache.pkl"
    },
    {
      "step_number": 2,
      "action": "Re-serialize pickles in Py3 protocol 4 format",
      "affected_files": ["src/data_serializer.py"],
      "data_files": ["/var/data/cache.pkl"],
      "effort": "medium",
      "verify_command": "python3 scripts/verify_pickle_migration.py /var/data/cache.pkl"
    }
  ]
}
```

### Step 5: Generate Markdown Report

Run the report generator:

```bash
python3 scripts/generate_serialization_report.py \
    ./serialization-output/serialization-report.json \
    --output ./serialization-output/serialization-report.md
```

The report contains:
- Executive summary (how many critical issues found)
- Risk breakdown by category
- Per-file findings with code context
- Data file inventory
- Recommended remediation actions

---

## Detection Categories

### 1. Pickle/cPickle

Detects:
- `import pickle`, `from pickle import ...`
- `import cPickle` (deprecated in Py2, removed in Py3)
- `pickle.load()`, `pickle.loads()`, `pickle.dump()`, `pickle.dumps()`
- `pickle.Unpickler()`/`Pickler()` instantiation
- Protocol version specification (`protocol=0`, `protocol=2`, etc.)
- `encoding=` parameter (present = good sign)

Risk assessment:
- CRITICAL if `load()` without `encoding=` param
- HIGH if `cPickle` is used
- MEDIUM if protocol version is hardcoded to 0 or 1

### 2. Marshal

Detects:
- `import marshal`
- `marshal.load()`, `marshal.loads()`, `marshal.dump()`, `marshal.dumps()`

Risk assessment:
- **CRITICAL**: Marshal is not designed for long-term data storage and version changes
  between Python releases often break old marshal data. If you must use it, it's a blocker
  for migration.

### 3. Shelve

Detects:
- `import shelve`
- `shelve.open()`

Risk assessment:
- **HIGH**: Shelve databases are tied to the underlying DBM format (gdbm, bdb, etc).
  Py3 may use different defaults. Requires manual testing.

### 4. JSON

Detects:
- `import json`
- `json.load()`, `json.loads()`, `json.dump()`, `json.dumps()`

Risk assessment:
- **LOW** in most cases (JSON is text-based and Py3-safe)
- **MEDIUM** if `allow_nan=False` or non-string keys are used

### 5. YAML

Detects:
- `import yaml`
- `yaml.load()`, `yaml.safe_load()`, `yaml.dump()`, `yaml.safe_dump()`

Risk assessment:
- **CRITICAL** if `yaml.load()` without `Loader=` (arbitrary code execution risk)
- **LOW** if `yaml.safe_load()` is used

### 6. MessagePack

Detects:
- `import msgpack`
- `msgpack.packb()`, `msgpack.unpackb()`, `msgpack.pack()`, `msgpack.unpack()`

Risk assessment:
- **MEDIUM**: Depends on custom type handling and version compatibility

### 7. Protocol Buffers

Detects:
- `import google.protobuf` or `from google.protobuf import ...`
- `message.SerializeToString()`, `message.ParseFromString()`
- Generated `_pb2.py` files

Risk assessment:
- **LOW**: Protobuf has built-in versioning and Py3 support is solid

### 8. Struct-Based Custom Serialization

Detects:
- `import struct`
- `struct.pack()` and `struct.unpack()` used in class methods
- Binary data concatenation patterns (e.g., `data + struct.pack(...)`)

Risk assessment:
- **MEDIUM**: Depends on whether strings are being mixed with bytes

### 9. Custom Class Serialization (`__getstate__`, `__setstate__`, `__reduce__`)

Detects:
- Classes defining `__getstate__()`, `__setstate__()`, `__reduce__()`, `__reduce_ex__()`

Risk assessment:
- **HIGH**: These methods must be audited to ensure Py3 compatibility
- Check if they're returning bytes vs. strings
- Check if they assume Py2 object layouts

### 10. Binary File I/O

Detects:
- `open(filename, 'rb')`, `open(filename, 'wb')` (binary mode)
- Near serialization code (heuristic)

Risk assessment:
- **MEDIUM**: May contain serialized data; requires inspection

---

## Success Criteria

The skill has succeeded when:

1. Every `pickle.load()` call has been identified and assessed
2. Every `pickle.load()` without `encoding=` parameter is flagged as CRITICAL
3. All `cPickle` imports are flagged for replacement
4. All `marshal` usage is flagged as CRITICAL (blocker)
5. All `__getstate__`, `__setstate__`, `__reduce__` methods are listed with file locations
6. If `--data-dirs` is provided, all `.pkl`, `.pickle`, `.shelve`, `.db`, `.marshal` files are found
7. A data migration plan is generated with step-by-step remediation
8. The Markdown report is human-readable and actionable

---

## Model Tier

**Haiku (80%) + Sonnet (20%).** Detecting pickle/marshal/struct/json/yaml usage is pattern matching — use Haiku. Assessing cross-version compatibility for complex serialization (custom pickle reducers, struct format strings mixing text and binary) benefits from Sonnet.

## References

- `references/serialization-migration.md` — Comprehensive pickle/marshal/shelve Py2→Py3 migration guide covering protocol version matrix, marshal dangers, shelve backend compatibility, custom `__getstate__`/`__setstate__` auditing, and struct packing patterns
- `references/encoding-patterns.md` — EBCDIC, binary protocol, and mixed encoding detection patterns (relevant for struct-based serialization)
- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
