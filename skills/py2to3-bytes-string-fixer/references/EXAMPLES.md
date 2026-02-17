# Code Examples and Pattern Tables

**This file supports:** `/sessions/stoic-practical-faraday/mnt/code-translation-skills/skills/py2to3-bytes-string-fixer/SKILL.md`

## Boundary Classification Examples

### BYTES-NATIVE (keep as bytes)

```python
# Bytes-native: struct.unpack returns bytes, don't decode until display
frame = socket.recv(1024)  # bytes
(msg_id, flags, length) = struct.unpack('>HBH', frame[:5])  # unpack from bytes → ints
```

```python
# Bytes-native
data = conn.recv(1024)  # explicitly bytes
socket.send(data)  # send bytes back
```

```python
# Bytes-native
with open(filename, 'rb') as f:
    raw_data = f.read()  # bytes
```

```python
# Bytes-native
ser = serial.Serial('/dev/ttyUSB0', 9600)
packet = ser.read(10)  # bytes
```

```python
# Bytes-native
def crc16(data: bytes) -> int:
    for byte in data:  # iterate over ints, not chars
        ...
```

### TEXT-NATIVE (decode to str)

```python
# Text-native
msg = f"Received {count} items"  # str, not bytes
print(msg)
```

```python
# Text-native
log.info(f"Frame ID: {frame_id}")  # str for logging
```

```python
# Text-native
config_value = config.get('name')  # str for display
```

```python
# Text-native
json_str = json.dumps(data)  # str, not bytes
```

```python
# Text-native
db.insert(table='users', name=user_name)  # str
```

### MIXED/AMBIGUOUS (needs human decision)

```python
# Ambiguous: is this EBCDIC or ASCII? Is it text or a binary field?
frame = socket.recv(512)  # bytes (binary-layer)
# ...later...
if frame[10:15] == 'HELLO':  # comparing bytes to str literal — will fail in Py3
    # Should this be frame[10:15] == b'HELLO'? Or decode first with known codec?
```

```python
# Ambiguous: function parameter type unclear
def process_record(data):
    # data could be bytes (from file) or str (from user input)
    # and the function doesn't document which
    return data.split(':')  # works in Py2, crashes in Py3 if bytes
```

```python
# Ambiguous: is this cp500 (international) or cp037 (US)? Are there CRC bytes?
data.decode()  # which codec? defaults to UTF-8 — wrong for EBCDIC!
```

## SCADA/Modbus Protocol Handling

### Complete Flow Example

```python
# 1. Read frames as bytes from socket/serial:
# TCP Modbus:
data = socket.recv(256)  # bytes ✓

# 2. Parse with struct.unpack on bytes:
(unit_id, func_code, byte_count) = struct.unpack('>BBB', data[:3])
# unpack works with bytes, returns ints

# 3. Validate CRC on bytes:
# CRC operates on raw bytes
crc_calc = crc16_modbus(data[:-2])  # bytes input
crc_recv = struct.unpack('>H', data[-2:])[0]  # bytes
assert crc_calc == crc_recv

# 4. Build response frames in bytes:
response = struct.pack('>BBB', unit_id, func_code, byte_count)  # bytes
response += register_values
response += struct.pack('>H', crc16_modbus(response))
socket.send(response)  # bytes ✓

# 5. Only decode for logging/display:
log.info(f"Sent {len(response)} bytes")  # str (count)
# Don't decode binary frames themselves
```

## EBCDIC Handling Examples

### Identifier Detection

```python
# EBCDIC data sources:
# - Files marked as EBCDIC
# - Functions documented as "mainframe data handler"
# - Byte comparisons with EBCDIC-range values (0xC1–0xE9 for letters)
```

### Explicit Decode at Ingestion

```python
# Before (Py2 implicit, wrong in Py3):
with open('mainframe_export.dat', 'rb') as f:
    records = f.read()  # bytes
# ...later...
if records[0] == 'X':  # comparing bytes to str — wrong!

# After (explicit cp500 decode):
with open('mainframe_export.dat', 'rb') as f:
    records_bytes = f.read()  # keep as bytes for now
records_text = records_bytes.decode('cp500', errors='replace')
# Now records_text is str, safe to compare with 'X'
```

### Codec Variants

- cp500: most common (international)
- cp037: US/Canada
- cp1047: Latin-1 extended
- cp273: German
- **Document which variant is used** in function docstring

### Mixed Records (EBCDIC + Binary)

```python
# Some fields EBCDIC, some binary (e.g., timestamps as big-endian int64)
ebcdic_part = record[0:100].decode('cp500')  # text
timestamp = struct.unpack('>Q', record[100:108])[0]  # binary int
```

## File I/O Handling Examples

### Binary Files

```python
# Py2 (implicit):
with open('data.bin') as f:
    data = f.read()  # bytes in Py2

# Py3 (explicit — our fix):
with open('data.bin', 'rb') as f:
    data = f.read()  # bytes ✓
```

### Text Files

```python
# Py2 (implicit UTF-8/system default):
with open('config.txt') as f:
    lines = f.readlines()  # bytes in Py2, but often treated as str

# Py3 (explicit):
with open('config.txt', encoding='utf-8') as f:
    lines = f.readlines()  # str ✓
```

### Legacy Non-UTF-8 Codecs

```python
# Latin-1 file (e.g., Windows-1252 legacy data):
with open('legacy_export.csv', encoding='latin-1') as f:
    data = f.read()  # str, decoded with latin-1

# EBCDIC file:
with open('mainframe_data.dat', 'rb') as f:
    raw = f.read()  # bytes
data = raw.decode('cp500')  # str, EBCDIC decoded
```

## Phase 0 Boundary Map Example

```json
{
  "boundaries": [
    {
      "file": "scada/modbus.py",
      "line": 45,
      "type": "socket_recv",
      "source_var": "data",
      "dest_usage": "struct.unpack",
      "context": "frame_parser()",
      "confidence_bytes": 0.95,
      "confidence_text": 0.05
    },
    {
      "file": "legacy/ebcdic.py",
      "line": 12,
      "type": "open_binary",
      "source_var": "file_handle",
      "dest_usage": "string_comparison",
      "context": "read_cobol_record()",
      "confidence_bytes": 0.60,
      "confidence_text": 0.40
    }
  ]
}
```

## Encoding Annotations JSON Example

```json
{
  "encoding_annotations": [
    {
      "file": "scada/modbus.py",
      "line": 78,
      "operation": "decode",
      "codec": "utf-8",
      "context": "message logging",
      "confidence": 0.95,
      "risk": "low",
      "note": "Modbus text fields (device name) are documented as ASCII/UTF-8"
    },
    {
      "file": "legacy/ebcdic.py",
      "line": 23,
      "operation": "decode",
      "codec": "cp500",
      "context": "mainframe record ingestion",
      "confidence": 0.75,
      "risk": "medium",
      "note": "Codec cp500 is common but variant cp037 is possible; requires verification with IBM reference"
    },
    {
      "file": "legacy/ebcdic.py",
      "line": 101,
      "operation": "decode",
      "codec": "None (implicit UTF-8)",
      "context": "legacy field parsing",
      "confidence": 0.20,
      "risk": "high",
      "note": "Data is EBCDIC mainframe data; UTF-8 decode will produce garbage; fix immediately"
    }
  ]
}
```

## Decisions-Needed JSON Example

```json
{
  "decisions": [
    {
      "file": "legacy/ebcdic.py",
      "line": 42,
      "boundary_type": "ambiguous_comparison",
      "source_code": "if record[0:5] == 'XXXXX':",
      "context": "read_mainframe_record()",
      "data_flow": {
        "source": "file opened as binary (rb)",
        "current_operation": "string literal comparison",
        "next_use": "stored in list, used in JSON export"
      },
      "confidence_bytes": 0.50,
      "confidence_text": 0.50,
      "options": [
        {
          "option": 1,
          "description": "Keep as bytes, use b'XXXXX' comparison",
          "rationale": "Data comes from binary file; comparison is field matching in EBCDIC protocol"
        },
        {
          "option": 2,
          "description": "Decode with cp500 early, compare with 'XXXXX'",
          "rationale": "If this is text data from mainframe, EBCDIC decode is needed"
        },
        {
          "option": 3,
          "description": "Document data format in function docstring, request clarification",
          "rationale": "Function signature doesn't specify if result is bytes or str; need developer input"
        }
      ],
      "impact": "If wrong codec chosen, data will be garbled; if bytes/str mismatch, TypeError at runtime",
      "next_step": "Review with domain expert (SCADA/mainframe) to confirm data format"
    }
  ]
}
```

## Auto-Fix Examples

### Struct Unpack Results

```python
# Before (buggy in Py3):
data = socket.recv(256)
(id,) = struct.unpack('>H', data[:2])
if id == 0x1234:  # ok, ints
    ...

# After (explicit, correct):
data = socket.recv(256)
assert isinstance(data, bytes), "socket.recv must return bytes"
(id,) = struct.unpack('>H', data[:2])
if id == 0x1234:
    ...
```

### File Binary Mode

```python
# Before (ambiguous):
with open('protocol.dat') as f:
    frame = f.read(512)  # Py2: bytes; Py3: str — broken!

# After (explicit):
with open('protocol.dat', 'rb') as f:
    frame = f.read(512)  # Py3: bytes ✓
```

### Socket Recv Kept as Bytes

```python
# Before (implicit):
data = conn.recv(1024)
parsed = parse_modbus_frame(data)  # expects bytes

# After (assertion for clarity):
data = conn.recv(1024)
assert isinstance(data, bytes), "conn.recv returns bytes in Python 3"
parsed = parse_modbus_frame(data)
```

## Migration State Tracking Example

```json
{
  "modules": {
    "scada/modbus.py": {
      "phase": "3-semantic",
      "bytes_str_status": "in_progress",
      "decisions_made": 12,
      "decisions_pending": 3,
      "risk_level": "high",
      "notes": [
        "Modbus frames kept as bytes through parsing layer",
        "Display functions explicitly decode to str",
        "Pending: CRC function needs endianness verification"
      ]
    }
  }
}
```
