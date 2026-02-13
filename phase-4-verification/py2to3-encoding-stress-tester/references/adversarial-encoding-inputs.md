# Adversarial Encoding Inputs

Test vectors designed to trigger encoding bugs that survive normal testing. Each vector
targets a specific failure mode that commonly occurs during Python 2→3 migration,
especially in codebases with SCADA, mainframe, and CNC data sources.

## How to Use These Inputs

Feed these inputs through every data path identified by the Data Format Analyzer (Skill
0.2). A correctly migrated codebase should handle all of them without crashing, data
corruption, or silent behavioral changes.

The Encoding Stress Tester (Skill 4.3) uses these as its primary input corpus.

---

## Category 1: Bytes That Look Like Valid Text

These byte sequences are valid binary data (e.g., sensor readings, protocol frames) that
happen to look like valid UTF-8 or ASCII. A buggy migration that accidentally decodes
binary data will produce garbage text instead of raising an error.

### 1.1 IEEE 754 Floats That Are Valid UTF-8

| Float Value | Hex (big-endian) | UTF-8 Interpretation | Failure Mode |
|-------------|------------------|---------------------|--------------|
| 25.5 | `41 CC 00 00` | `AÌ\x00\x00` | Decoded as text, produces "AÌ" + nulls |
| -1.0 | `BF 80 00 00` | Invalid UTF-8 (BF is continuation) | Decode error — good, detectable |
| 100.0 | `42 C8 00 00` | `BÈ\x00\x00` | Decoded as text, produces "BÈ" + nulls |
| 3.14 | `40 48 F5 C3` | `@HõÃ` | All valid Latin-1; valid UTF-8 too |
| NaN | `7F C0 00 00` | `\x7fÀ\x00\x00` | `C0 00` is overlong null — rejected by strict UTF-8 |
| +Inf | `7F 80 00 00` | Invalid UTF-8 | Good — decode fails |

**Test**: Parse a Modbus response containing these float values. Verify the parsed
float matches the original, not a garbage text interpretation.

### 1.2 Uint16 Register Values That Are ASCII

| Register Value | Hex | ASCII Interpretation | Failure Mode |
|----------------|-----|---------------------|--------------|
| 16706 | `41 42` | `AB` | Decoded as text "AB" instead of integer 16706 |
| 12336 | `30 30` | `00` | Decoded as text "00" instead of integer 12336 |
| 8224 | `20 20` | `  ` (two spaces) | Decoded as whitespace, may be stripped |
| 2573 | `0A 0D` | `\n\r` | Decoded as newline + CR, may split lines |

### 1.3 Binary Protocol Headers That Are Printable ASCII

| Protocol | Header Bytes | ASCII Reading | Risk |
|----------|-------------|---------------|------|
| Modbus TCP | `00 01 00 00 00 06 01 03` | `\x00\x01\x00\x00\x00\x06\x01\x03` | Control chars, not decodable as text |
| DNP3 | `05 64` | `\x05d` | `64` is ASCII `d` — partial decode possible |
| HTTP | `48 54 54 50` | `HTTP` | Is valid ASCII text — but framing is binary |

---

## Category 2: Text That Breaks Common Assumptions

These are valid text strings that break common assumptions in string processing code.

### 2.1 Unicode Normalization Attacks

| Input | Hex (UTF-8) | Appearance | Issue |
|-------|-------------|------------|-------|
| `é` (precomposed, NFC) | `C3 A9` | é | One codepoint, 2 bytes |
| `é` (decomposed, NFD) | `65 CC 81` | é | Two codepoints (`e` + combining accent), 3 bytes |
| `ñ` (precomposed) | `C3 B1` | ñ | One codepoint |
| `ñ` (decomposed) | `6E CC 83` | ñ | Two codepoints (`n` + combining tilde) |
| `Ω` (Greek omega) | `CE A9` | Ω | U+03A9 |
| `Ω` (Ohm sign) | `E2 84 A6` | Ω | U+2126 — looks identical but different codepoint |
| `Å` (A-ring) | `C3 85` | Å | U+00C5 |
| `Å` (Angstrom) | `E2 84 AB` | Å | U+212B — looks identical but different codepoint |

**Test**: Use these pairs as dictionary keys, filename components, and comparison targets.
A migration that doesn't normalize Unicode will produce inconsistent lookups.

### 2.2 Zero-Width Characters

| Character | Hex (UTF-8) | Name | Risk |
|-----------|-------------|------|------|
| U+200B | `E2 80 8B` | Zero-Width Space | Invisible; breaks `strip()` expectations |
| U+200C | `E2 80 8C` | Zero-Width Non-Joiner | Invisible; changes word boundaries |
| U+200D | `E2 80 8D` | Zero-Width Joiner | Invisible; joins characters |
| U+FEFF | `EF BB BF` | BOM / Zero-Width No-Break Space | Invisible; may be at start of file |
| U+00AD | `C2 AD` | Soft Hyphen | Invisible in most renderings |
| U+2060 | `E2 81 A0` | Word Joiner | Invisible |

**Test**: Insert these into field values, config keys, and identifiers. Verify that
lookups, comparisons, and parsing still work correctly.

### 2.3 Strings That Change Length Under Operations

| Input | `len()` | `encode('utf-8')` length | Issue |
|-------|---------|--------------------------|-------|
| `"Hello"` | 5 | 5 | No issue |
| `"café"` | 4 | 5 | UTF-8 multi-byte `é` |
| `"日本語"` | 3 | 9 | Each CJK char is 3 bytes |
| `"😀"` | 1 (or 2 on narrow Py2) | 4 | Py2 narrow build: len=2 (surrogate pair) |
| `"e\u0301"` | 2 | 3 | Combining char: 2 codepoints, 1 visible glyph |

**Migration Trap**: Py2 narrow builds (UCS-2) represent emoji as surrogate pairs, so
`len("😀") == 2`. Py3 always uses UCS-4, so `len("😀") == 1`. Code that indexes into
strings or slices them will behave differently.

---

## Category 3: EBCDIC Adversarial Inputs

### 3.1 EBCDIC Bytes That Are Valid UTF-8

| EBCDIC Byte | CP500 Meaning | UTF-8 Interpretation | Risk |
|-------------|---------------|---------------------|------|
| `40` | Space | `@` (ASCII) | Space becomes `@` if decoded with wrong codec |
| `4B` | Period `.` | `K` (ASCII) | Period becomes `K` |
| `5A` | `!` | `Z` (ASCII) | Exclamation becomes `Z` |
| `61` | `/` | `a` (ASCII) | Slash becomes `a` |
| `C1 C2 C3` | `ABC` | `ÁÂÃ` (Latin-1) | Letters become accented characters |
| `F0 F1 F2` | `012` | `ðñò` (Latin-1) | Digits become accented lowercase |

**Test**: Decode EBCDIC data with `utf-8` codec (the Py3 default). Every byte will
produce garbage or errors. This catches places where Py2 code relied on bytes being
bytes and Py3 code accidentally decodes with the default codec.

### 3.2 EBCDIC Packed Decimal Edge Cases

| Input (hex) | Expected | Issue |
|-------------|----------|-------|
| `00 00 0C` | +0 | Positive zero |
| `00 00 0D` | -0 | Negative zero (valid in EBCDIC packed decimal) |
| `99 99 9C` | +99999 | Maximum 3-byte packed decimal |
| `00 00 0F` | 0 (unsigned) | F sign nibble = unsigned |
| `12 3A BC` | Invalid | Non-decimal nibble (A) in data portion |
| `12 34 5E` | Invalid | Invalid sign nibble (E) |

### 3.3 EBCDIC Variant Confusion

| Byte | CP037 (US) | CP500 (International) | CP1047 (Latin-1) |
|------|------------|----------------------|-------------------|
| `5B` | `$` | `[` | `$` |
| `7B` | `#` | `#` | `#` |
| `AD` | `[` | `[` | `[` |
| `BA` | `[` | `¬` | `¬` |
| `BB` | `]` | (different) | (different) |
| `4F` | `\|` | `\|` | `\|` |

**Test**: Decode the same EBCDIC data with CP037, CP500, and CP1047. If any field
delimiters or structural characters differ, the wrong codec silently garbles the data.

---

## Category 4: Boundary Condition Inputs

### 4.1 Empty and Minimal Inputs

| Input | Risk |
|-------|------|
| Empty bytes `b""` | `b"".decode("utf-8")` returns `""` — but code may not expect empty string |
| Single null byte `b"\x00"` | Valid in many encodings; may be treated as string terminator |
| Single newline `b"\n"` | May trigger line-processing code |
| Single byte `b"\xff"` | Not valid UTF-8; valid Latin-1 (`ÿ`); valid EBCDIC (varies) |
| Maximum length string (1MB) | Memory and performance edge case |

### 4.2 Exact Buffer Boundary Inputs

| Input | Size | Risk |
|-------|------|------|
| Exactly 256 bytes | Modbus max PDU size | Frame boundary exact match |
| Exactly 4096 bytes | Common buffer size | Socket read boundary |
| 4095 bytes + 1 multi-byte char | 4097 bytes encoded | Split across buffer reads |
| 65535 bytes | Max uint16 | Length field overflow |

### 4.3 Multi-Byte Character Split Points

| Scenario | Risk |
|----------|------|
| 2-byte UTF-8 char split across two `socket.recv()` calls | First byte: `C3`, second byte: `A9` — incomplete sequence |
| 3-byte UTF-8 char split: 1+2 or 2+1 bytes | Partial decode fails |
| 4-byte UTF-8 char split at any point | Four possible split points |
| Shift-JIS 2-byte char where second byte is `0x5C` (backslash) | String escaping may eat the second byte |

**Test**: Feed data in chunks that split multi-byte characters. Verify the code
reassembles correctly or fails gracefully.

---

## Category 5: File System Edge Cases

### 5.1 Non-UTF-8 Filenames

| Filename (bytes) | Issue |
|------------------|-------|
| `b"\xff\xfe"` | Not valid UTF-8; `os.listdir()` returns surrogate-escaped string |
| `b"caf\xe9"` (Latin-1 `é`) | Not valid UTF-8; surrogate escape in Py3 |
| `b"test\x00file"` | Null byte in filename — Py3 raises ValueError |
| `b"\xc3\xa9"` (UTF-8 `é`) | Valid UTF-8 — but macOS stores as NFD decomposed |

### 5.2 Path Encoding

| Path | Issue |
|------|-------|
| `/tmp/données/résultats.csv` | Accented chars in path; must encode for Py2 |
| `C:\Users\données\fichier.txt` | Windows Unicode path; Py2 MBCS vs Py3 wide API |
| `//server/共有/ファイル.dat` | CJK in network path; Shift-JIS or UTF-8? |

---

## Category 6: Interaction Effects

These bugs only appear when multiple edge cases combine.

### 6.1 EBCDIC Data Through UTF-8 Logging

```
1. Read EBCDIC record from mainframe (bytes)
2. Parse fields using byte offsets (correct)
3. Log parsed values: log.info(f"Record: {field_value}")
4. If field_value is still bytes, Py3 logs "b'...'" instead of decoded text
5. If field_value is decoded with wrong codec (utf-8 instead of cp500), logs garbage
```

### 6.2 Binary Protocol Data in JSON Serialization

```
1. Read Modbus register (bytes: b'\x01\xF4' = 500)
2. Parse with struct.unpack (correct: 500)
3. Store in dict: {"register_10": register_value}
4. Serialize to JSON: json.dumps(data)
5. If register_value is accidentally bytes instead of int, Py3 raises TypeError
6. Py2 would serialize b'\x01\xf4' as string "\x01\xf4" — wrong but "works"
```

### 6.3 Mixed-Encoding CSV

```
1. CSV file with UTF-8 header row and Latin-1 data rows
2. Py2: open() reads bytes, csv.reader treats everything as bytes — "works"
3. Py3: open(encoding='utf-8') decodes header correctly but garbles Latin-1 rows
4. Py3: open(encoding='latin-1') decodes data correctly but misreads UTF-8 header
5. Fix: detect encoding per-line or use chardet
```

### 6.4 Pickle with EBCDIC Strings

```
1. Py2 pickles a dict: {"name": "\xC1\xC2\xC3"} (EBCDIC "ABC" as bytes)
2. Pickle stores this as Py2 str (which is bytes)
3. Py3 unpickle: "\xC1\xC2\xC3" becomes bytes b'\xc1\xc2\xc3'
4. Code that does value == "ABC" now compares bytes to str → always False
5. Code must decode: value.decode('cp500') == "ABC"
```

---

## Test Execution Checklist

For each data path in the codebase, verify with:

- [ ] Valid input in expected encoding
- [ ] Valid input in wrong encoding (e.g., EBCDIC through UTF-8 decoder)
- [ ] Empty input
- [ ] Single-byte input (every byte 0x00-0xFF)
- [ ] Multi-byte character at buffer boundaries
- [ ] Maximum-length input
- [ ] Input with BOM
- [ ] Input with null bytes
- [ ] Input with mixed encodings
- [ ] Input that looks like valid text but is binary (Category 1)
- [ ] Input with zero-width characters (Category 2.2)
- [ ] Input with combining characters (Category 2.1)
- [ ] EBCDIC data decoded with wrong variant (Category 3.3)
