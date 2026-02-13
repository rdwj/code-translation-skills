---
name: py2to3-data-format-analyzer
description: >
  Deep-dive analysis of the data layer in a Python 2 codebase as part of Python 2→3 migration to Python 3.
  Use this skill whenever you need to inventory encoding patterns, binary protocol handlers,
  serialization formats, database connections, or data ingestion points. Especially critical
  for codebases that handle IoT/SCADA data (Modbus, OPC-UA, DNP3), mainframe data (EBCDIC),
  CNC/machine automation (G-code), or any mix of binary protocols and text processing.
  Also trigger when someone says "trace the data flow," "find encoding issues," "where are
  the bytes/str boundaries," "what serialization formats are in use," "map the data layer,"
  or "which files handle binary data." The bytes/str boundary is the single highest-risk
  area in any Python 2→3 migration — this skill maps every one of them.
---

# Data Format Analyzer

The Codebase Analyzer (Skill 0.1) does a broad sweep of the entire codebase and catches
surface-level encoding issues. This skill goes deeper into the data layer specifically,
because in a codebase with IoT/SCADA sensors, mainframe feeds, CNC machines, and legacy
databases, the data layer is where the migration will succeed or fail.

Python 2's `str` type is bytes. Python 3's `str` type is text. Every place in the code
where data crosses between these two worlds — reading from a socket, decoding EBCDIC,
parsing a Modbus register, unpickling a cached object — is a potential migration landmine.
This skill finds all of them.

## Why This Matters

In Python 2, code like `data = socket.recv(1024)` returns a `str` (which is bytes), and
you can do `data.split(',')` on it because string literals are also bytes. In Python 3,
`socket.recv()` returns `bytes`, and `b','.split(b',')` works differently than
`','.split(',')`. Every one of these implicit conversions needs to become explicit.

For this codebase specifically:
- **Mainframe data** may arrive in EBCDIC (cp500/cp1047), where byte values are completely
  different from ASCII — a comma isn't `0x2C`, it's `0x6B`
- **SCADA/Modbus data** uses packed binary registers where two bytes represent a 16-bit
  integer, and the code probably converts these to Python strings for display
- **CNC G-code** is ASCII text but parsed with positional indexing (`line[0:3]`) which
  behaves differently on `bytes` vs `str` in Python 3
- **Serialized data** (pickle, shelve) created under Python 2 will deserialize differently
  under Python 3 — Py2 `str` objects become Py3 `bytes`

## Inputs

- **codebase_path**: Root directory of the Python 2 codebase
- **output_dir**: Where to write analysis results (defaults to `<codebase_path>/migration-analysis/`)
- **sample_data_dir** (optional): Directory containing sample data files for encoding detection
- **exclude_patterns** (optional): Glob patterns for files/directories to skip

## Outputs

All outputs go to `<output_dir>/`:

| File | Format | Purpose |
|------|--------|---------|
| `data-layer-report.json` | JSON | Complete data flow inventory (consumed by other skills) |
| `data-layer-report.md` | Markdown | Human-readable analysis with risk ratings |
| `encoding-map.json` | JSON | Every encoding-related operation in the codebase |
| `serialization-inventory.json` | JSON | All serialization/deserialization points |
| `bytes-str-boundaries.json` | JSON | Every point where bytes become text or vice versa |

## Workflow

### Step 1: Scan the Data Layer

Run the main analysis script:

```bash
python3 scripts/analyze_data_layer.py <codebase_path> \
    --output <output_dir> \
    [--exclude "**/vendor/**" "**/test/**"] \
    [--sample-data <sample_data_dir>]
```

This walks every `.py` file and uses AST parsing plus regex fallback to detect data layer
patterns across seven categories:

1. **File I/O** — `open()`, `codecs.open()`, `io.open()`, file read/write with or without
   explicit encoding
2. **Network I/O** — `socket.recv()`, `socket.send()`, `urllib`, `requests`, serial port
   reads (`pyserial`)
3. **Binary Protocol** — `struct.pack()`/`unpack()`, `ctypes`, Modbus/OPC-UA/DNP3 library
   usage, raw byte manipulation
4. **Encoding/Decoding** — `.encode()`, `.decode()`, `codecs` module, EBCDIC codec usage,
   explicit and implicit conversions
5. **Serialization** — `pickle`, `cPickle`, `marshal`, `shelve`, `json`, `yaml`, `xml`,
   `msgpack`, custom `__getstate__`/`__setstate__`
6. **Database** — connection creation, cursor operations, encoding configuration for
   `sqlite3`, `MySQLdb`, `psycopg2`, `cx_Oracle`, `pyodbc`, `pymongo`, etc.
7. **Hardcoded Constants** — hex escape sequences (`\x00`–`\xff`), byte string literals
   used as delimiters or protocol markers, magic bytes

For each finding, the script records:
- File path and line number
- Category and specific pattern name
- The matched code snippet
- Risk level (low/medium/high/critical)
- Data direction: `ingestion` (external → code), `egression` (code → external), or
  `internal` (within the codebase)
- Boundary type: `bytes_to_text`, `text_to_bytes`, `bytes_only`, `text_only`, or `ambiguous`

### Step 2: Identify Bytes/Str Boundaries

The script automatically classifies every finding by its boundary type. A "boundary" is
any point where data transitions between bytes and text semantics. These are the critical
points for migration because they need explicit `encode()`/`decode()` calls in Python 3.

The classification logic:
- `socket.recv()` → `bytes_to_text` if the result is used in string operations
- `open()` without `'b'` mode → `ambiguous` (could be text or binary, depends on usage)
- `struct.unpack()` → `bytes_only` if result stays numeric, `bytes_to_text` if converted
- `.encode()` → `text_to_bytes`
- `.decode()` → `bytes_to_text`
- `pickle.load()` → `bytes_to_text` (Py2 str objects become Py3 bytes)

### Step 3: Generate the Report

```bash
python3 scripts/generate_data_report.py <output_dir> \
    --project-name "Legacy SCADA System" \
    --output <output_dir>/data-layer-report.md
```

The report organizes findings by risk and category, highlighting the areas that need
the most attention during Phase 3 (Semantic Fixes).

## Detection Patterns

### File I/O Patterns

| Pattern | What We're Looking For | Risk |
|---------|----------------------|------|
| `open(f)` | No mode, no encoding — ambiguous | High |
| `open(f, 'r')` | Text mode but no encoding specified | Medium |
| `open(f, 'rb')` | Binary mode — likely correct as-is | Low |
| `open(f, 'r', encoding='...')` | Explicit encoding — good sign | Low |
| `codecs.open(f, encoding='...')` | Py2-style explicit encoding | Medium (codecs.open still works but is redundant in Py3) |
| `io.open(...)` | Forward-compatible open — good | Low |
| `file(f)` | Py2-only builtin — removed in Py3 | High |

### Network / Serial I/O Patterns

| Pattern | Boundary Type | Risk |
|---------|--------------|------|
| `socket.recv(N)` | bytes_to_text (if result used as string) | High |
| `socket.send(data)` | text_to_bytes (if data is a string) | High |
| `serial.read(N)` | bytes_to_text | High |
| `serial.write(data)` | text_to_bytes | High |
| `urllib.urlopen()` / `urllib2.urlopen()` | bytes_to_text | Medium |

### Binary Protocol Patterns

| Pattern | What It Tells Us | Risk |
|---------|-----------------|------|
| `struct.pack(fmt, ...)` | Binary packing — should stay as bytes | Low (if stays bytes) |
| `struct.unpack(fmt, data)` | Binary unpacking — check what happens to result | Medium |
| `struct.unpack` → string format | Result fed to string operations | High |
| Modbus register read | 16-bit register → needs explicit int conversion | High |
| Manual byte indexing (`data[i]`) | In Py3, indexing bytes returns int, not byte | Critical |

### EBCDIC Patterns

| Pattern | What It Tells Us | Risk |
|---------|-----------------|------|
| `decode('cp500')` / `decode('cp1047')` | Explicit EBCDIC — good, but verify correctness | Medium |
| Hex constants `\xC1`–`\xC9` | EBCDIC uppercase A-I byte range | Critical |
| Hex constants `\xF0`–`\xF9` | EBCDIC digit 0-9 byte range | Critical |
| Manual byte-to-char mapping | Possibly hand-rolled EBCDIC translation | Critical |

### Serialization Patterns

| Pattern | Risk for Migration |
|---------|--------------------|
| `pickle.dump()` / `pickle.load()` | High — Py2 str pickles as Py3 bytes |
| `cPickle` import | Medium — just rename to `pickle` |
| `pickle.loads(data)` | High — if `data` came from Py2 pickle |
| `marshal.dump()` / `marshal.load()` | Critical — version-specific format |
| `shelve.open()` | High — shelve uses pickle internally |
| `json.dumps()` / `json.loads()` | Low — JSON is text-based |
| `yaml.dump()` / `yaml.load()` | Low-Medium — usually text but check |
| `__getstate__` / `__setstate__` | High — custom serialization logic |
| `__reduce__` / `__reduce_ex__` | High — custom pickle protocol |

### Database Patterns

| Pattern | What to Check | Risk |
|---------|--------------|------|
| `sqlite3.connect()` | Default text_factory setting | Medium |
| `MySQLdb.connect(charset=...)` | Encoding configuration | Medium |
| `psycopg2.connect()` | Client encoding setting | Medium |
| `cx_Oracle.connect()` | NLS_LANG encoding | High (often EBCDIC for mainframe DBs) |
| `pyodbc.connect()` | Connection string encoding | Medium |
| `cursor.execute()` | Query parameter encoding | Medium |
| `cursor.fetchone/all()` | Result set decoding | Medium |

## Integration with Other Skills

This skill's outputs feed directly into:
- **Skill 3.1: Bytes/String Boundary Fixer** — uses `bytes-str-boundaries.json` to know
  exactly where to add encode/decode calls
- **Skill 0.3: Serialization Boundary Detector** — uses `serialization-inventory.json`
  as a starting point for deeper serialization analysis
- **Skill 1.2: Test Scaffold Generator** — uses `encoding-map.json` to generate encoding-
  aware test cases
- **Skill X.1: Migration State Tracker** — findings update module risk scores and risk
  factors

After running this skill, update the migration state tracker:

```bash
python3 ../orchestration/migration-state-tracker/scripts/update_state.py \
    <state_file> record-output \
    --module <module_path> \
    --output-path <output_dir>/data-layer-report.json
```

## References

This skill uses shared reference documents. Read them for detection guidance:

- `references/encoding-patterns.md` — EBCDIC byte ranges, binary protocol
  encoding conventions, mixed-encoding detection heuristics
- `references/scada-protocol-patterns.md` — Modbus register layouts, OPC-UA
  data types, DNP3 binary formats, common pyserial patterns
- `references/serialization-migration.md` — pickle protocol versions and
  Py2/Py3 compatibility, marshal format issues, shelve migration guide

## Important Notes

**This is archaeology.** The original developers aren't here to explain why
`data[7:11].strip()` works on Modbus register data. The analysis needs to be thorough
enough that the person doing the Phase 3 fixes can understand the data flow without having
to reverse-engineer it again.

**False positives are better than false negatives.** If the script isn't sure whether
something is a bytes/str boundary, it should flag it as `ambiguous` rather than skip it.
A human reviewer can dismiss false positives; they can't find missed boundaries.

**Sample data helps.** If sample data files are provided (actual EBCDIC files, Modbus
captures, pickled objects), the script can do encoding detection on them and correlate
with code patterns. This isn't required but improves accuracy significantly.
