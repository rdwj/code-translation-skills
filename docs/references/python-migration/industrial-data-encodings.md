# Industrial Data Encodings

Encoding conventions for SCADA, CNC, and mainframe data as encountered in legacy Python 2
codebases. This reference maps each industrial data source type to its encoding
characteristics, common byte patterns, and the correct Py3 handling strategy.

---

## SCADA / IoT Protocols

### Modbus (TCP and RTU)

**Encoding**: Pure binary. No text encoding involved at the protocol level.

| Data Type | Format | Size | Py3 Handling |
|-----------|--------|------|-------------|
| Coil status | Single bit (packed in bytes) | 1 bit | `bytes` — unpack with bitwise ops |
| Discrete input | Single bit (packed in bytes) | 1 bit | `bytes` — unpack with bitwise ops |
| Holding register | Unsigned 16-bit big-endian | 2 bytes | `struct.unpack('>H', data)` |
| Input register | Unsigned 16-bit big-endian | 2 bytes | `struct.unpack('>H', data)` |
| Float (2 registers) | IEEE 754 big-endian | 4 bytes | `struct.unpack('>f', data)` |
| String (N registers) | ASCII packed in register pairs | N×2 bytes | `data.decode('ascii')` after extraction |
| Exception response | Function code + exception code | 2 bytes | `struct.unpack('>BB', data)` |

**Key Rule**: All Modbus data stays as `bytes` through parsing. Only decode to `str` for:
- Device name strings (registers containing ASCII text)
- Logging and display
- JSON serialization of human-readable fields

**Endianness Variants**:
- Standard Modbus: big-endian (most significant byte first)
- Some devices: little-endian or mid-endian (byte-swapped, word-swapped)
- The Py2 code may have custom `struct` format strings — preserve these exactly

### OPC-UA

**Encoding**: Mixed binary and UTF-8.

| Data Type | Encoding | Py3 Handling |
|-----------|----------|-------------|
| Node IDs | Binary (4-byte numeric or UTF-8 string) | `bytes` for numeric, `str` for string IDs |
| Attribute values | Type-dependent (float, int, string, bytes) | Decode strings as UTF-8 |
| Timestamps | 64-bit Windows FILETIME | `struct.unpack('<Q', data)` → convert to datetime |
| StatusCode | Unsigned 32-bit | `struct.unpack('<I', data)` |

### DNP3 (Distributed Network Protocol)

**Encoding**: Pure binary with CRC checksums.

| Component | Format | Py3 Handling |
|-----------|--------|-------------|
| Data link header | 10 bytes binary | `bytes` — `struct.unpack` |
| CRC (per block) | CRC-16 over 16-byte blocks | Compute on `bytes` — never decode |
| Application data | Binary objects | `bytes` — parse by object type |
| Timestamps | 48-bit milliseconds since epoch | `struct.unpack('<Q', data[:6] + b'\x00\x00')` |

### BACnet (Building Automation)

**Encoding**: Mixed binary and character strings.

| Data Type | Encoding | Py3 Handling |
|-----------|----------|-------------|
| Character strings | UTF-8 with length prefix | `data[prefix_len:].decode('utf-8')` |
| ANSI strings | ISO-8859-1 | `data.decode('latin-1')` |
| Bit strings | Packed bits | `bytes` — bitwise operations |
| Enumerated values | Unsigned integer | `struct.unpack('>I', data)` |

### MQTT

**Encoding**: UTF-8 for topic names and payloads (by convention).

| Component | Encoding | Py3 Handling |
|-----------|----------|-------------|
| Topic name | UTF-8 (MQTT spec requires) | `topic.decode('utf-8')` |
| Payload | Application-defined (often JSON) | `payload.decode('utf-8')` then `json.loads()` |
| Client ID | UTF-8 | `client_id.decode('utf-8')` |
| Fixed header | Binary | `bytes` — `struct.unpack` |

---

## CNC / Machine Automation

### G-code

**Encoding**: ASCII text, transmitted as bytes over serial.

| Element | Format | Py3 Handling |
|---------|--------|-------------|
| Command letters | Single ASCII char (G, M, X, Y, Z, F, S, T) | `data.decode('ascii')` then parse |
| Numeric values | ASCII decimal (e.g., `100.000`) | Decode to `str`, then `float()` |
| Line numbers | `N` + digits (e.g., `N0010`) | Decode to `str` |
| Comments | `(text)` or `;text` | Decode to `str` |
| Block delimiter | CR+LF or LF | Handle with universal newlines |
| Checksum | XOR of all bytes before `*` | Compute on `bytes` before decoding |

**Encoding Variant**: Some Japanese CNC controllers (Fanuc, Mazak) may use Shift-JIS
for operator comments. The G-code commands are still ASCII, but comment blocks may
contain Japanese characters.

```python
# Safe parsing pattern:
raw_line = serial_port.read_until(b'\n')  # bytes
# G-code commands are always ASCII
if raw_line.startswith(b'('):
    # Comment — may be Shift-JIS
    comment = raw_line.decode('shift_jis', errors='replace')
else:
    # Command — always ASCII
    command = raw_line.decode('ascii')
```

### RS-274 (Gerber Format)

**Encoding**: Pure ASCII subset (0x20-0x7E plus CR/LF).

| Element | Format | Py3 Handling |
|---------|--------|-------------|
| Aperture definitions | `%ADD...%` blocks | `data.decode('ascii')` |
| Coordinate data | `X...Y...D...` | `data.decode('ascii')` |
| End of file | `M02*` | `data.decode('ascii')` |

### HPGL (Plotter Language)

**Encoding**: ASCII text commands.

| Element | Format | Py3 Handling |
|---------|--------|-------------|
| Commands | Two-letter codes (PU, PD, PA) | `data.decode('ascii')` |
| Parameters | Comma-separated integers | `data.decode('ascii')` then `int()` |
| Label text | `LB<text>\x03` | `data.decode('ascii')` — ETX terminator is 0x03 |

---

## Mainframe Systems

### EBCDIC Record Formats

**Encoding**: EBCDIC (CP500, CP037, or CP1047 depending on system and region).

#### Fixed-Width Records (Most Common)

| Field Type | EBCDIC Handling | Py3 Strategy |
|------------|-----------------|-------------|
| Text (PIC X) | EBCDIC encoded, space-padded right | `field_bytes.decode('cp500').rstrip()` |
| Numeric display (PIC 9) | EBCDIC digits (F0-F9) | `field_bytes.decode('cp500')` then `int()` |
| Packed decimal (COMP-3) | BCD with sign nibble | Parse bytes directly — do NOT decode |
| Binary (COMP) | Big-endian integer | `struct.unpack('>i', field_bytes)` |
| Floating point (COMP-1/2) | IBM hex float (NOT IEEE 754) | Custom conversion — `struct` won't work |
| Date (PIC 9(8)) | YYYYMMDD as EBCDIC digits | `field_bytes.decode('cp500')` then parse |
| Timestamp | System-dependent | May be packed decimal or binary |

#### Variable-Length Records

| Component | Format | Py3 Strategy |
|-----------|--------|-------------|
| Record Descriptor Word (RDW) | 4 bytes: 2-byte length + 2 zero bytes | `struct.unpack('>HH', rdw)` |
| Block Descriptor Word (BDW) | 4 bytes: 2-byte length + 2 zero bytes | `struct.unpack('>HH', bdw)` |
| Segment indicator | Part of RDW | Check bits for segmented records |

#### VSAM Records

| Format | Notes | Py3 Strategy |
|--------|-------|-------------|
| KSDS (keyed) | Key + data, EBCDIC | Decode key and data separately |
| ESDS (entry-sequenced) | Sequential, EBCDIC | Decode per-field |
| RRDS (relative record) | Fixed slot, EBCDIC | Decode per-field |

### IBM Hex Floating Point

IBM mainframes use a hex floating-point format that is NOT IEEE 754:
- 1 sign bit + 7-bit hex exponent + 56-bit hex fraction
- Exponent is base-16 (not base-2)
- Cannot use `struct.unpack('>f', data)` — must convert manually

```python
def ibm_hex_to_ieee(data: bytes) -> float:
    """Convert IBM hex float (4 bytes) to Python float."""
    assert len(data) == 4
    sign = (data[0] & 0x80) >> 7
    exponent = (data[0] & 0x7F) - 64  # Excess-64 notation
    fraction = int.from_bytes(data[1:4], 'big') / (16**6)
    value = fraction * (16 ** exponent)
    return -value if sign else value
```

### JCL and Job Output

| Format | Encoding | Py3 Handling |
|--------|----------|-------------|
| JCL statements | EBCDIC, 80-column fixed | `line.decode('cp500')` |
| SYSOUT / SYSPRINT | EBCDIC, variable width | `line.decode('cp500')` |
| Carriage control | Column 1: ASA control character | Parse before decoding content |
| JES2 headers | EBCDIC + binary routing info | Decode text fields, leave routing as bytes |

---

## Database Wire Formats

### ODBC/JDBC from Mainframe (DB2)

| Data Type | Wire Format | Py3 Handling |
|-----------|-------------|-------------|
| CHAR/VARCHAR | EBCDIC (server) → driver converts | Driver should handle encoding; verify |
| GRAPHIC/VARGRAPHIC | DBCS (double-byte) | May need `euc_jp` or `cp933` depending on region |
| DECIMAL/NUMERIC | Packed decimal on wire | Driver converts to Python `Decimal` |
| BLOB | Raw bytes | `bytes` — no conversion |
| CLOB | Server encoding (EBCDIC or Unicode) | Driver should decode; verify encoding |

### SQLite (Local)

| Data Type | Wire Format | Py3 Handling |
|-----------|-------------|-------------|
| TEXT | UTF-8 | `str` — Py3 sqlite3 module handles this |
| BLOB | Raw bytes | `bytes` |
| INTEGER | 64-bit | `int` |
| REAL | IEEE 754 float | `float` |

---

## Serial Port Conventions

### RS-232 Parameters by Device Type

| Device | Baud | Data Bits | Parity | Stop | Encoding |
|--------|------|-----------|--------|------|----------|
| CNC (Fanuc) | 9600 | 7 | Even | 2 | ASCII (7-bit) or Shift-JIS |
| CNC (Mazak) | 9600 | 8 | None | 1 | ASCII or Shift-JIS |
| Lab instrument (GPIB→serial) | 9600 | 8 | None | 1 | ASCII |
| PLC (Modbus RTU) | 9600/19200 | 8 | Even/None | 1 | Binary (not text) |
| Barcode scanner | 9600 | 8 | None | 1 | ASCII or UTF-8 |
| Scale/balance | 2400/9600 | 7/8 | Even/None | 1 | ASCII |
| GPS (NMEA 0183) | 4800 | 8 | None | 1 | ASCII (printable only) |

### Framing Conventions

| Framing | Start | End | Usage |
|---------|-------|-----|-------|
| CR/LF terminated | None | `0D 0A` | G-code, NMEA, lab instruments |
| STX/ETX | `02` | `03` | Some PLCs, barcode scanners |
| Length-prefixed | 2-byte length | None | Modbus TCP, DNP3 |
| Fixed-length | None | None | Modbus RTU (timing-based) |
| Custom delimiter | Varies | Varies | Proprietary protocols |

---

## Quick Reference: Encoding Decision Tree

```
Is the data from a network/serial protocol?
├── Yes → Does the protocol spec say "binary"?
│   ├── Yes → Keep as bytes. Use struct.unpack.
│   │         Never decode. (Modbus, DNP3, binary PLCs)
│   └── No → Is it a text protocol?
│       ├── ASCII only → decode('ascii')
│       ├── UTF-8 → decode('utf-8')
│       └── Unknown → read protocol spec or check with chardet
│
├── Is the data from a mainframe?
│   ├── Text fields → decode('cp500') or ('cp037'/'cp1047')
│   ├── Packed decimal → parse bytes directly (COMP-3)
│   ├── Binary numeric → struct.unpack (COMP)
│   └── IBM float → custom conversion (NOT struct)
│
├── Is the data from a file?
│   ├── Binary file (.dat, .bin) → open('rb'), keep as bytes
│   ├── Text file (.txt, .csv, .cfg) → open(encoding='utf-8') or detect
│   ├── Legacy export → chardet or try utf-8 → latin-1 fallback
│   └── EBCDIC file → open('rb'), then decode('cp500')
│
└── Is the data from a database?
    ├── Driver handles encoding → verify str returned (not bytes)
    ├── BLOB column → bytes
    └── Text column → str (driver should decode)
```
