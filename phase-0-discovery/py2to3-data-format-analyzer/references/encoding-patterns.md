# Encoding Patterns Reference

Reference document for detecting and handling encoding-related patterns in Python 2→3
migration. Used by the Data Format Analyzer (0.2), Bytes/String Boundary Fixer (3.1),
and Encoding Stress Tester (4.3).

## Table of Contents

1. [EBCDIC Encoding](#ebcdic-encoding)
2. [Common Codecs and Their Usage](#common-codecs)
3. [Binary Protocol Encoding Conventions](#binary-protocols)
4. [Mixed Encoding Detection](#mixed-encoding)
5. [Implicit Encoding in Python 2](#implicit-encoding-py2)
6. [Detection Heuristics](#detection-heuristics)

---

## EBCDIC Encoding

### What It Is

EBCDIC (Extended Binary Coded Decimal Interchange Code) is IBM's character encoding,
still in active use on mainframes (zOS, AS/400, iSeries). Unlike ASCII where `A` = 0x41,
in EBCDIC `A` = 0xC1. This means hardcoded byte values in code that handles mainframe
data will be **completely wrong** if interpreted as ASCII/UTF-8.

### EBCDIC Byte Ranges

| Character Range | EBCDIC Bytes | ASCII Bytes | Notes |
|----------------|-------------|------------|-------|
| Uppercase A–I | 0xC1–0xC9 | 0x41–0x49 | |
| Uppercase J–R | 0xD1–0xD9 | 0x4A–0x52 | |
| Uppercase S–Z | 0xE2–0xE9 | 0x53–0x5A | |
| Lowercase a–i | 0x81–0x89 | 0x61–0x69 | |
| Lowercase j–r | 0x91–0x99 | 0x6A–0x72 | |
| Lowercase s–z | 0xA2–0xA9 | 0x73–0x7A | |
| Digits 0–9 | 0xF0–0xF9 | 0x30–0x39 | |
| Space | 0x40 | 0x20 | |
| Period (.) | 0x4B | 0x2E | |
| Comma (,) | 0x6B | 0x2C | |
| Plus (+) | 0x4E | 0x2B | |
| Minus (-) | 0x60 | 0x2D | |
| Newline | 0x15 or 0x25 | 0x0A | Varies by EBCDIC variant |

### Python EBCDIC Codecs

| Codec Name | Used For | Notes |
|-----------|---------|-------|
| `cp037` | US/Canada mainframes | Common in North American shops |
| `cp500` | International/multilingual | Most common in mixed environments |
| `cp1047` | Latin-1/Open Systems | Common in Unix Services on zOS |
| `cp273` | German mainframes | |
| `cp1140` | Euro-sign variant of cp037 | |
| `cp1141` | Euro-sign variant of cp273 | |

### Code Patterns to Flag

```python
# Explicit EBCDIC — good, but verify the codec variant is correct
data.decode('cp500')
codecs.open(filename, encoding='cp1047')

# Hardcoded EBCDIC byte values — CRITICAL risk
if byte == '\xC1':  # This is EBCDIC 'A', not ASCII
delimiter = '\x6B'  # EBCDIC comma, not ASCII

# Manual translation table — often hand-rolled in legacy code
ebcdic_to_ascii = {0xC1: 'A', 0xC2: 'B', ...}
```

### Migration Strategy

1. Find all EBCDIC codec references — the codec name tells you the variant
2. Find all hardcoded byte constants in files that also use EBCDIC codecs
3. Ensure decode happens at the ingestion boundary (as early as possible)
4. After decoding, data should be `str` (text) for the rest of the pipeline
5. If data needs to go back to mainframe, encode at the egression boundary

---

## Common Codecs

| Codec | Typical Source | Python 2 Behavior | Python 3 Behavior |
|-------|---------------|-------------------|-------------------|
| `utf-8` | Modern systems, web | Works as expected | Default for str |
| `ascii` | Legacy US English | Default str encoding | Must be explicit |
| `latin-1` (iso-8859-1) | Western European | Lossless for all byte values | Must be explicit |
| `cp1252` | Windows Western | Similar to latin-1 but different | Must be explicit |
| `shift_jis` | Japanese equipment | Common in CNC/Fanuc controllers | Must be explicit |
| `euc-jp` | Japanese Unix | Alternative to Shift-JIS | Must be explicit |
| `utf-16` | Windows APIs, some DBs | BOM handling needed | BOM handling needed |
| `cp500` | IBM mainframes (intl) | See EBCDIC section | See EBCDIC section |
| `cp1047` | IBM zOS Unix | See EBCDIC section | See EBCDIC section |

### The latin-1 Escape Hatch

`latin-1` (iso-8859-1) is special: it maps bytes 0x00–0xFF one-to-one to Unicode
codepoints U+0000–U+00FF. This means `bytes.decode('latin-1')` never fails — every
byte value is valid. Legacy code sometimes uses this as a "pass anything through"
codec. In Python 3, this is sometimes used as an intermediate step when the true
encoding is unknown:

```python
# Py2 pattern (implicit, works because str is bytes):
data = socket.recv(1024)
text = data.upper()  # "works" because str methods work on bytes in Py2

# Py3 safe interim pattern (not ideal, but doesn't crash):
data = socket.recv(1024)
text = data.decode('latin-1')  # Always succeeds
text = text.upper()

# Py3 correct pattern (requires knowing the actual encoding):
data = socket.recv(1024)
text = data.decode('utf-8')  # or whatever the actual encoding is
```

---

## Binary Protocols

### struct Format Strings

The `struct` module uses format characters to describe binary layouts. Key ones
for migration:

| Format | C Type | Python 2 | Python 3 | Risk |
|--------|--------|----------|----------|------|
| `s` | char[] | Returns str (bytes) | Returns bytes | High if used as text |
| `c` | char | Returns 1-byte str | Returns bytes of length 1 | High |
| `p` | Pascal string | Returns str | Returns bytes | High |
| `b`, `B` | signed/unsigned byte | Returns int | Returns int | Low |
| `h`, `H` | short | Returns int | Returns int | Low |
| `i`, `I` | int | Returns int | Returns int | Low |

The dangerous ones are `s`, `c`, and `p` — these return `str` in Python 2 (which
is bytes-compatible) but return `bytes` in Python 3 (which is not string-compatible).

### Byte Indexing Behavior Change

```python
data = b'\x48\x65\x6c\x6c\x6f'
# Python 2: data[0] = '\x48' (a one-character string)
# Python 3: data[0] = 72 (an integer)
```

This breaks any code that compares `data[i]` against a string character or
concatenates indexed bytes into a string.

---

## Mixed Encoding Detection

### Heuristics for Identifying Encoding

When examining a file or data stream of unknown encoding:

1. **BOM check**: UTF-8 BOM is `EF BB BF`, UTF-16 LE is `FF FE`, UTF-16 BE is `FE FF`
2. **High-byte ratio**: If >85% of bytes are in 0x40–0xF9 range, likely EBCDIC
3. **Null byte pattern**: UTF-16 has alternating null bytes; binary data has irregular nulls
4. **ASCII check**: If all bytes are 0x20–0x7E plus 0x09/0x0A/0x0D, likely ASCII
5. **UTF-8 validation**: Try `data.decode('utf-8')` — if it succeeds without error,
   likely UTF-8 (but could still be ASCII or latin-1 subset)

### Mixed Encoding Within a Single File

Some legacy files have mixed encodings — for example, ASCII headers with EBCDIC
data records, or UTF-8 text with embedded binary blobs. These require per-section
handling:

```python
# Example: file with ASCII header and EBCDIC data
header = f.read(80)  # ASCII header
header_text = header.decode('ascii')

data = f.read(1000)  # EBCDIC data records
data_text = data.decode('cp500')
```

---

## Implicit Encoding in Python 2

### The Default Encoding Problem

Python 2's default encoding is ASCII. When Python 2 needs to convert between `str`
and `unicode` implicitly, it uses ASCII. This means:

```python
# Python 2 — works if name is ASCII, UnicodeDecodeError if not
name = get_name()  # returns str (bytes)
greeting = u"Hello " + name  # implicit decode with ASCII
```

Python 3 eliminates this implicit conversion — `str` is always text, `bytes` is
always bytes, and you must explicitly convert between them.

### Where Implicit Conversions Hide

1. String concatenation: `str + unicode` → implicit decode
2. String formatting: `"%s" % byte_data` → implicit decode
3. Comparison: `str == unicode` → implicit decode
4. Dictionary lookup: `{str_key: value}[unicode_key]` → implicit decode
5. `print` statement: `print str_data` → implicit encode to stdout encoding
6. File path operations: `os.path.join(unicode_dir, bytes_filename)`

All of these will become `TypeError` in Python 3 if bytes and str are mixed.

---

## Detection Heuristics

### Signals That a Module Handles Binary Data

- Imports `struct`, `ctypes`, `socket`, `serial`
- Opens files in binary mode (`'rb'`, `'wb'`)
- Uses hex escape sequences in strings
- Contains format strings with `s`, `c`, or `p` characters
- Has variables named `buf`, `buffer`, `packet`, `frame`, `register`, `raw`

### Signals That a Module Handles Text Data

- Imports `codecs`, `locale`, `unicodedata`
- Uses `.encode()` or `.decode()` methods
- Opens files with `encoding=` parameter
- Has variables named `text`, `message`, `name`, `label`, `title`

### Signals That a Module Has Bytes/Str Confusion

- Uses both binary and text patterns in the same function
- Passes data between binary I/O and string operations without explicit conversion
- Has `str()` calls on data received from binary sources
- Uses string formatting (`%s`, `.format()`, f-strings) with data from binary sources
- Concatenates data from different sources without consistent encoding
