# Encoding Test Vectors

Test data for verifying encoding handling across the Python 2→3 migration. These vectors
cover every encoding family the codebase is expected to encounter, from standard UTF-8
through EBCDIC mainframe encodings and binary protocol data.

## How to Use These Vectors

Each vector provides:
- **Hex bytes**: The raw byte representation
- **Expected decoded text**: What the bytes should decode to
- **Codec**: Which Python codec to use
- **Use case**: Where this encoding appears in the codebase
- **Py2→Py3 risk**: What changes between interpreters

Use these vectors in:
- Skill 1.2 (Test Scaffold Generator) — for encoding-aware test generation
- Skill 4.3 (Encoding Stress Tester) — as baseline inputs for stress tests
- Manual verification of bytes/str boundary fixes

---

## UTF-8 Test Vectors

### ASCII Subset (Trivial)

| Input (hex) | Decoded | Notes |
|-------------|---------|-------|
| `48 65 6C 6C 6F` | `Hello` | Pure ASCII, identical in Py2/Py3 |
| `30 31 32 33` | `0123` | Numeric ASCII |
| `20 09 0A 0D` | ` \t\n\r` | Whitespace characters |

### 2-Byte UTF-8 (Latin Extended)

| Input (hex) | Decoded | Codepoint | Notes |
|-------------|---------|-----------|-------|
| `C3 A9` | `é` | U+00E9 | Common in French text |
| `C3 BC` | `ü` | U+00FC | German umlaut |
| `C3 B1` | `ñ` | U+00F1 | Spanish |
| `C2 A3` | `£` | U+00A3 | British pound |
| `C2 A5` | `¥` | U+00A5 | Japanese yen |
| `C2 A9` | `©` | U+00A9 | Copyright symbol |

### 3-Byte UTF-8 (CJK, Symbols)

| Input (hex) | Decoded | Codepoint | Notes |
|-------------|---------|-----------|-------|
| `E4 B8 AD` | `中` | U+4E2D | CJK character (Chinese "middle") |
| `E6 97 A5` | `日` | U+65E5 | CJK character (Japanese "day/sun") |
| `E2 82 AC` | `€` | U+20AC | Euro sign |
| `E2 80 93` | `–` | U+2013 | En dash |
| `E2 80 9C` | `"` | U+201C | Left double quotation mark |
| `EF BB BF` | BOM | U+FEFF | UTF-8 BOM (byte order mark) |

### 4-Byte UTF-8 (Emoji, Supplementary)

| Input (hex) | Decoded | Codepoint | Notes |
|-------------|---------|-----------|-------|
| `F0 9F 98 80` | `😀` | U+1F600 | Emoji (grinning face) |
| `F0 9F 92 A7` | `💧` | U+1F4A7 | Emoji (water droplet — relevant for water monitoring) |
| `F0 9D 94 B8` | `𝔸` | U+1D538 | Mathematical double-struck A |

### Malformed UTF-8

| Input (hex) | Issue | Expected Behavior |
|-------------|-------|-------------------|
| `C0 80` | Overlong null byte | Should reject (security concern) |
| `ED A0 80` | Lone high surrogate (U+D800) | Should reject |
| `ED B0 80` | Lone low surrogate (U+DC00) | Should reject |
| `FE FF` | Invalid UTF-8 starter bytes | Should reject |
| `C3` (truncated) | Incomplete 2-byte sequence | Should reject or replace |
| `E4 B8` (truncated) | Incomplete 3-byte sequence | Should reject or replace |
| `80 81 82` | Continuation bytes without starter | Should reject |
| `F5 80 80 80` | Above U+10FFFF | Should reject |

---

## Latin-1 (ISO-8859-1) Test Vectors

| Input (hex) | Decoded | Notes |
|-------------|---------|-------|
| `E9` | `é` | Latin-1 single byte (vs UTF-8 `C3 A9`) |
| `FC` | `ü` | Latin-1 single byte (vs UTF-8 `C3 BC`) |
| `F1` | `ñ` | Latin-1 single byte |
| `A3` | `£` | Latin-1 pound sign |
| `A9` | `©` | Latin-1 copyright |
| `80` | `\x80` | Control character (valid Latin-1, not printable) |
| `FF` | `ÿ` | Highest Latin-1 codepoint |
| `00` through `7F` | (ASCII range) | Identical to ASCII |
| `A0` | NBSP | Non-breaking space — often confused with regular space |

**Py2→Py3 Risk**: Latin-1 is a single-byte encoding where every byte 0x00-0xFF is valid.
This means `bytes.decode('latin-1')` never fails, making it a common "fallback" codec.
However, using it incorrectly (decoding EBCDIC or UTF-8 data as Latin-1) produces garbage
without raising an error.

---

## Windows-1252 (CP1252) Test Vectors

| Input (hex) | Decoded | Notes |
|-------------|---------|-------|
| `93` | `"` | Left double quote (NOT in Latin-1 0x80-0x9F range) |
| `94` | `"` | Right double quote |
| `91` | `'` | Left single quote |
| `92` | `'` | Right single quote |
| `96` | `–` | En dash |
| `97` | `—` | Em dash |
| `85` | `…` | Ellipsis |
| `80` | `€` | Euro sign |

**Py2→Py3 Risk**: CP1252 and Latin-1 differ in the 0x80-0x9F range. Files labeled as
"Latin-1" are often actually CP1252. Py2 code that reads these bytes as `str` "works"
because bytes are bytes. Py3 code that decodes with `latin-1` instead of `cp1252` will
produce different Unicode characters for 0x80-0x9F.

---

## EBCDIC Test Vectors

### CP500 (International EBCDIC)

| Input (hex) | Decoded | ASCII equiv | Notes |
|-------------|---------|-------------|-------|
| `C1` | `A` | `0x41` | EBCDIC letter A |
| `C2` | `B` | `0x42` | EBCDIC letter B |
| `D1` | `J` | `0x4A` | EBCDIC letter J |
| `E2` | `S` | `0x53` | EBCDIC letter S |
| `F0` | `0` | `0x30` | EBCDIC digit 0 |
| `F1` | `1` | `0x31` | EBCDIC digit 1 |
| `F9` | `9` | `0x39` | EBCDIC digit 9 |
| `40` | ` ` | `0x20` | EBCDIC space |
| `4B` | `.` | `0x2E` | EBCDIC period |
| `6B` | `,` | `0x2C` | EBCDIC comma |
| `7D` | `'` | `0x27` | EBCDIC apostrophe |
| `5C` | `*` | `0x2A` | EBCDIC asterisk |

### CP037 (US/Canada EBCDIC)

| Input (hex) | CP037 decoded | CP500 decoded | Notes |
|-------------|---------------|---------------|-------|
| `5B` | `$` | `[` | **Critical difference** — field delimiter confusion |
| `BA` | `[` | `¬` | Bracket position differs |
| `BB` | `]` | (different) | Bracket position differs |
| `4A` | `¢` | `¢` | Same (cent sign) |
| `B0` | `^` | (different) | Caret position differs |

### CP1047 (Latin-1 Extended EBCDIC)

| Input (hex) | CP1047 decoded | CP500 decoded | Notes |
|-------------|----------------|---------------|-------|
| `AD` | `[` | `[` | Same in both |
| `BD` | `]` | `]` | Same in both |
| `4F` | `\|` | `\|` | Pipe character |
| `15` | newline | newline | EBCDIC newline (NL) |
| `25` | line feed | line feed | EBCDIC LF |

### EBCDIC Packed Decimal

| Input (hex) | Meaning | Notes |
|-------------|---------|-------|
| `01 23 4C` | `+1234` | Packed BCD, C = positive |
| `01 23 4D` | `-1234` | Packed BCD, D = negative |
| `00 00 0F` | `+0` | Packed BCD, F = unsigned positive |

**Py2→Py3 Risk**: Py2 code may compare raw bytes with hardcoded hex values (e.g.,
`if byte == '\xC1':` to check for EBCDIC 'A'). In Py3, this comparison is str vs bytes
and will always be False. Must change to `if byte == b'\xC1':` or decode first.

---

## Shift-JIS Test Vectors

| Input (hex) | Decoded | Notes |
|-------------|---------|-------|
| `82 A0` | `あ` | Hiragana 'a' |
| `83 41` | `ア` | Katakana 'a' |
| `8E A0` | (half-width katakana) | Single-byte JIS extension |
| `93 FA` | `日` | Kanji "day" |
| `96 7B` | `本` | Kanji "book/origin" |
| `5C` | `\` or `¥` | **Ambiguous** — backslash vs yen depending on context |
| `7E` | `~` or `‾` | **Ambiguous** — tilde vs overline |

**Py2→Py3 Risk**: Shift-JIS has multi-byte sequences where the second byte can overlap
with ASCII range (0x40-0x7E, 0x80-0xFC). Py2 code that does byte-level string operations
(indexing, slicing) on Shift-JIS data will produce different results in Py3 if the data
is decoded to str first. CNC machine interfaces from Japanese equipment likely use this.

---

## Binary Protocol Test Vectors (Non-Text)

### Modbus TCP Frame

```
Header (MBAP):    00 01 00 00 00 06 01
Function code:    03 (Read Holding Registers)
Start address:    00 0A (register 10)
Quantity:         00 02 (2 registers)
```

Hex: `00 01 00 00 00 06 01 03 00 0A 00 02`

This is pure bytes — must never be decoded to str.

### Modbus RTU Response

```
Unit ID:          01
Function code:    03 (Read Holding Registers)
Byte count:       04
Register 1:       01 F4 (500 as uint16)
Register 2:       00 64 (100 as uint16)
CRC:              B4 44
```

Hex: `01 03 04 01 F4 00 64 B4 44`

CRC must be computed on raw bytes. Decoding corrupts the CRC calculation.

### DNP3 Frame (SCADA)

```
Start bytes:      05 64
Length:            05
Control:          C0
Destination:      01 00
Source:            02 00
CRC:              XX XX
```

Hex: `05 64 05 C0 01 00 02 00 XX XX`

### Serial Port G-code (CNC)

```
G01 X100.000 Y50.000 F500\r\n
```

Hex: `47 30 31 20 58 31 30 30 2E 30 30 30 20 59 35 30 2E 30 30 30 20 46 35 30 30 0D 0A`

This is ASCII text but transmitted as bytes over serial. Must decode to str for parsing.

---

## Mixed-Encoding Test Cases

### Case 1: EBCDIC Header + Binary Payload

```
[EBCDIC text: "REC001" as cp500] [binary: 4 bytes big-endian int32] [EBCDIC text: "END"]
```

Hex: `D9 C5 C3 F0 F0 F1  00 00 01 F4  C5 D5 C4`

The EBCDIC portions decode to "REC001" and "END"; the middle 4 bytes are integer 500.

### Case 2: UTF-8 Log with Binary Sensor Data

```
"Sensor reading: " [2 bytes big-endian int16] " at " [ISO timestamp]
```

The text portions are UTF-8; the sensor reading is raw bytes that must be parsed with
`struct.unpack('>H', ...)`.

### Case 3: CSV with Mixed Line Endings

```
field1,field2\r\n    (Windows CRLF)
field3,field4\n      (Unix LF)
field5,field6\r      (Old Mac CR)
```

Py2 `open()` doesn't normalize line endings; Py3 `open()` in text mode does. This means
`splitlines()` may return different results.

---

## Codec Reference Table

| Codec | Python Name | Byte Range | Use In Codebase |
|-------|-------------|------------|-----------------|
| ASCII | `ascii` | 0x00-0x7F | G-code, basic config files |
| UTF-8 | `utf-8` | variable | Modern text, JSON, XML |
| Latin-1 | `latin-1` or `iso-8859-1` | 0x00-0xFF | Legacy Windows exports |
| CP1252 | `cp1252` | 0x00-0xFF | Windows text (misidentified as Latin-1) |
| CP500 | `cp500` | 0x00-0xFF | International EBCDIC (mainframe) |
| CP037 | `cp037` | 0x00-0xFF | US/Canada EBCDIC (mainframe) |
| CP1047 | `cp1047` | 0x00-0xFF | Latin-1 extended EBCDIC |
| Shift-JIS | `shift_jis` | 0x00-0xFF (multi-byte) | Japanese CNC equipment |
| EUC-JP | `euc_jp` | 0x00-0xFF (multi-byte) | Japanese Unix systems |
| UTF-16 LE | `utf-16-le` | 2+ bytes per char | Windows Unicode APIs |
| UTF-16 BE | `utf-16-be` | 2+ bytes per char | Network protocols |

---

## Verification Script Template

```python
#!/usr/bin/env python3
"""Verify encoding test vectors decode correctly."""

import codecs

VECTORS = {
    "utf-8": [
        (b"\x48\x65\x6c\x6c\x6f", "Hello"),
        (b"\xc3\xa9", "é"),
        (b"\xe4\xb8\xad", "中"),
        (b"\xf0\x9f\x98\x80", "😀"),
    ],
    "cp500": [
        (b"\xc1\xc2\xc3", "ABC"),
        (b"\xf0\xf1\xf2", "012"),
    ],
    "latin-1": [
        (b"\xe9", "é"),
        (b"\xfc", "ü"),
        (b"\xff", "ÿ"),
    ],
    "shift_jis": [
        (b"\x82\xa0", "あ"),
        (b"\x83\x41", "ア"),
    ],
}

for codec, vectors in VECTORS.items():
    for raw_bytes, expected in vectors:
        decoded = raw_bytes.decode(codec)
        assert decoded == expected, (
            f"{codec}: {raw_bytes.hex()} decoded to {decoded!r}, "
            f"expected {expected!r}"
        )
    print(f"  {codec}: {len(vectors)} vectors passed")

print("All encoding test vectors verified.")
```
