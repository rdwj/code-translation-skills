# Encoding Edge Cases

Comprehensive catalog of encoding edge cases that cause subtle bugs during Python 2→3
migration. These are the cases that normal testing misses because they require specific
byte patterns, environmental conditions, or interaction effects.

## Why Edge Cases Matter

In a legacy codebase with SCADA, mainframe, and CNC data sources, encoding bugs are
often silent. A wrong codec doesn't crash — it produces garbage data that propagates
through the system. A mishandled BOM shifts all field boundaries. A surrogate pair in
a filename causes the entire file operation to fail. These edge cases are the difference
between a migration that "works" and one that works correctly.

---

## BOM (Byte Order Mark) Edge Cases

### UTF-8 BOM

| Scenario | Bytes | Risk |
|----------|-------|------|
| File starts with UTF-8 BOM | `EF BB BF` + content | Py3 `open(encoding='utf-8-sig')` strips it; `utf-8` does not |
| BOM in middle of file | content + `EF BB BF` + content | BOM decoded as ZWNBSP (U+FEFF), invisible but breaks string comparison |
| Double BOM | `EF BB BF EF BB BF` + content | Two BOMs — first stripped by `utf-8-sig`, second becomes U+FEFF in text |
| BOM after newline | `0A EF BB BF` | BOM not at file start, never stripped |

**Migration Trap**: Py2 code that reads files as bytes and processes them character by
character doesn't notice BOMs — they're just bytes. Py3 code that opens files with
`encoding='utf-8'` will include the BOM as U+FEFF in the decoded text, which breaks
comparisons like `if line.startswith("DATA")` because the actual first character is U+FEFF.

**Fix**: Use `encoding='utf-8-sig'` for files that might have BOMs, or strip BOM manually:
```python
if text.startswith('\ufeff'):
    text = text[1:]
```

### UTF-16 BOM

| Scenario | Bytes | Risk |
|----------|-------|------|
| UTF-16 LE with BOM | `FF FE` + content | BOM indicates little-endian |
| UTF-16 BE with BOM | `FE FF` + content | BOM indicates big-endian |
| UTF-16 without BOM | content only | Platform-dependent byte order |
| UTF-16 BOM misidentified as UTF-8 | `FF FE` | Not valid UTF-8 — decode fails |

---

## Surrogate Pairs

### What They Are

Unicode surrogate pairs (U+D800–U+DFFF) are used in UTF-16 to encode characters above
U+FFFF. They should never appear in UTF-8, but they do in practice due to bugs in
other software.

### Edge Cases

| Scenario | Bytes (UTF-8 form) | Risk |
|----------|-------------------|------|
| Lone high surrogate | `ED A0 80` (U+D800) | Py3 `str` rejects this; Py2 `unicode` may accept |
| Lone low surrogate | `ED B0 80` (U+DC00) | Same rejection behavior |
| Surrogate pair encoded as UTF-8 | `ED A0 80 ED B0 80` | Rejected by Py3 strict; accepted by some Py2 codecs |
| Surrogateescape error handler | N/A | Py3 `surrogateescape` converts undecodable bytes to surrogates |
| Windows filenames with surrogates | Platform-specific | `os.listdir()` in Py3 may return strings with surrogates |

**Migration Trap**: Py3 uses `surrogateescape` as the default error handler for filesystem
operations on Unix. This means `os.listdir()` may return strings containing surrogate
characters if filenames contain non-UTF-8 bytes. Comparing these strings or encoding them
as UTF-8 will fail with `UnicodeEncodeError`.

**Fix**: When processing filenames, use `os.fsencode()`/`os.fsdecode()` or handle
`surrogateescape` explicitly:
```python
try:
    name_bytes = name.encode('utf-8')
except UnicodeEncodeError:
    name_bytes = name.encode('utf-8', errors='surrogateescape')
```

---

## Null Bytes

| Scenario | Risk |
|----------|------|
| Null byte in text file | Py2 `str` handles it; Py3 `str` handles it but some C-level APIs truncate at null |
| Null byte in filename | Py3 rejects null bytes in filenames (`ValueError`) |
| Null byte in EBCDIC | `0x00` is null in both EBCDIC and ASCII — but EBCDIC has `0x40` for space |
| Null byte as struct padding | `struct.pack('4s', b'AB')` → `b'AB\x00\x00'` |
| Null byte in Modbus frame | Valid binary data — must not be stripped |
| Null byte in JSON | JSON standard doesn't allow embedded null bytes |

**Migration Trap**: Py2 code that uses `str.find('\x00')` to locate null terminators in
binary data works because `str` is bytes. In Py3, this comparison is str vs str — it
works only if the data is decoded. But if the data is bytes, you need `data.find(b'\x00')`.

---

## Mixed Encodings

### Within a Single File

| Scenario | Example | Risk |
|----------|---------|------|
| UTF-8 metadata + EBCDIC payload | Log file header in UTF-8, data records in CP500 | Must switch codecs mid-file |
| ASCII header + Latin-1 body | HTTP response with ASCII headers, Latin-1 body | Content-Type may lie about encoding |
| UTF-8 with Latin-1 fallback | Some lines valid UTF-8, others Latin-1 | Chardet/charset detection needed |
| BOM in UTF-8 file with EBCDIC data | BOM signals UTF-8 but payload is EBCDIC | BOM is misleading |

**Migration Trap**: Py2 code that reads a file as bytes and uses different parsing logic
for different sections "works" because everything is bytes. Py3 code that opens the file
in text mode with a single encoding will garble the sections that use a different encoding.

**Fix**: Always open mixed-encoding files in binary mode (`'rb'`), then decode each
section with its appropriate codec:
```python
with open(path, 'rb') as f:
    header = f.read(100).decode('utf-8')
    payload = f.read().decode('cp500')
```

### Within a Single String

| Scenario | Example | Risk |
|----------|---------|------|
| Mojibake | UTF-8 bytes decoded as Latin-1, then encoded as UTF-8 | Double-encoded text (e.g., `Ã©` instead of `é`) |
| Mixed script | ASCII + CJK in same string | Valid UTF-8, but indexing is O(n) for non-ASCII |
| Combining characters | `e` + `\u0301` (combining acute) vs `é` (precomposed) | String comparison fails without normalization |
| Zero-width characters | `\u200B` (ZWSP), `\u200C` (ZWNJ), `\uFEFF` (BOM/ZWNBSP) | Invisible but affect string length and comparison |

---

## Platform-Specific Edge Cases

### Line Endings

| Platform | Line ending | Hex | Notes |
|----------|-------------|-----|-------|
| Unix/Linux | LF | `0A` | Standard in Python |
| Windows | CRLF | `0D 0A` | Py3 text mode converts to `\n` on read |
| Old Mac | CR | `0D` | Py3 text mode converts to `\n` on read |
| Mainframe | NEL | `15` (EBCDIC) | Not converted by Py3 text mode |
| Mixed | LF + CRLF | varies | Py3 universal newlines handles this |

**Migration Trap**: Py2 `open()` in default mode doesn't translate newlines. Py3 `open()`
in text mode uses universal newline translation. This means:
- `len(f.read())` may differ between Py2 and Py3 (CRLF → LF changes byte count)
- `f.read().split('\n')` produces different results
- Binary files opened in text mode may be corrupted by newline translation

### Filesystem Encoding

| Platform | Default FS encoding | Notes |
|----------|---------------------|-------|
| Linux | UTF-8 | Py3 uses `surrogateescape` for non-UTF-8 bytes |
| macOS | UTF-8 (NFD normalized) | Filenames auto-decomposed; `é` stored as `e` + combining accent |
| Windows | UTF-16 (via Win32 API) | Py3 uses wide APIs directly; Py2 used MBCS |

**Migration Trap**: macOS NFD normalization means `os.path.exists('café')` may fail if
the filename is stored as `cafe\u0301` (decomposed). Use `unicodedata.normalize('NFC', name)`
before comparisons.

---

## SCADA/Industrial Edge Cases

### Byte Values That Look Like Valid UTF-8

| Modbus register value | Hex | UTF-8 interpretation | Risk |
|-----------------------|-----|---------------------|------|
| Temperature: 25.5°C | `41 CC 00 00` (IEEE 754 float) | `41 CC` looks like valid 2-byte UTF-8 (`Ì`) | Accidental decode produces garbage |
| Register pair: 500, 100 | `01 F4 00 64` | `01 F4` is not valid UTF-8 starter | Decode fails with UnicodeDecodeError |
| Status word: 0xFF00 | `FF 00` | `FF` is never valid UTF-8 | Immediate failure |
| Counter: 0xC0A8 | `C0 A8` | Valid 2-byte UTF-8 sequence (overlong `¨`) | Technically decodable but semantically wrong |

### EBCDIC Field Alignment

| Scenario | Risk |
|----------|------|
| Fixed-width EBCDIC record, 80 bytes | Off-by-one in field offset → wrong codec for wrong bytes |
| Packed decimal field followed by text | Packed decimal bytes may coincidentally decode as EBCDIC chars |
| COMP-3 field (packed BCD) | Sign nibble (C/D/F) overlaps with EBCDIC letter range |
| Record with embedded binary length prefix | 2-byte length + N bytes text — must not decode length as text |

### Serial Port Framing

| Scenario | Risk |
|----------|------|
| STX/ETX framing (0x02/0x03) | These bytes are valid ASCII control chars — may pass text mode |
| 8-bit binary data at 9600 baud | Any byte 0x00-0xFF possible; cannot assume any encoding |
| Checksum byte equals newline (0x0A) | Py3 text mode may interpret as line ending |
| Response contains 0x1A (Ctrl-Z) | Windows Py3 text mode may interpret as EOF |

---

## Python 2→3 Specific Edge Cases

### `str` vs `bytes` Identity

| Py2 Expression | Py2 Result | Py3 Result | Risk |
|----------------|------------|------------|------|
| `'abc' == b'abc'` | `True` | `False` | Silent behavioral change |
| `b'abc' in {'abc': 1}` | `True` (key found) | `False` (not found) | Dict lookup silently fails |
| `b'\x00' < '\x01'` | `True` | `TypeError` | Comparison raises exception |
| `str(b'abc')` | `'abc'` | `"b'abc'"` | String contains literal `b'` prefix |
| `bytes(5)` | `'\x05'` (Py2 str of length 1) | `b'\x00\x00\x00\x00\x00'` (5 null bytes) | Completely different behavior |

### `open()` Default Mode

| Code | Py2 Behavior | Py3 Behavior |
|------|-------------|-------------|
| `open(f).read()` | Returns bytes | Returns str (decoded with locale encoding) |
| `open(f).read(1)` | Returns 1 byte | Returns 1 character (may be multiple bytes) |
| `open(f, 'rb').read()` | Returns bytes | Returns bytes |
| `open(f).write(b'abc')` | Writes 3 bytes | `TypeError: write() argument must be str` |

### `sys.stdin`/`sys.stdout` Encoding

| Attribute | Py2 | Py3 | Risk |
|-----------|-----|-----|------|
| `sys.stdin.encoding` | Often `None` | Platform-dependent (usually UTF-8) | Piped input may fail |
| `sys.stdout.encoding` | Often `None` | Platform-dependent | Non-UTF-8 locales break emoji |
| `sys.stdin.buffer` | N/A | `io.BufferedReader` | Must use `.buffer` for binary stdin |
| `PYTHONIOENCODING` | Sets I/O encoding | Sets I/O encoding | Set in test harness for consistency |

---

## Error Handler Edge Cases

| Error Handler | Behavior on Decode Error | Behavior on Encode Error | Risk |
|---------------|--------------------------|--------------------------|------|
| `'strict'` (default) | Raises `UnicodeDecodeError` | Raises `UnicodeEncodeError` | Safest but may crash |
| `'replace'` | Inserts `\ufffd` | Inserts `?` | Data loss — replacement is visible |
| `'ignore'` | Silently drops bytes | Silently drops characters | Data loss — silent and dangerous |
| `'surrogateescape'` | Maps bytes to surrogates (U+DC80–U+DCFF) | Maps surrogates back to bytes | Py3-only; preserves bytes round-trip |
| `'xmlcharrefreplace'` | N/A (encode only) | Inserts `&#xNN;` references | Encode only |
| `'backslashreplace'` | Inserts `\xNN` | Inserts `\xNN` | Readable but changes data |

**Critical**: Never use `'ignore'` on SCADA or mainframe data. Silently dropping bytes
from a Modbus frame corrupts the entire message. Always use `'strict'` for binary data
and `'replace'` only for display/logging.
