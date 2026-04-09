# Bytes/String Boundary Patterns Reference

Reference document for detecting and fixing bytes/str boundary issues in Python 2→3
migration. Used by the Bytes/String Boundary Fixer (3.1) to classify boundaries and
generate fixes.

## Table of Contents

1. [Bytes-Native Patterns](#bytes-native-patterns)
2. [Text-Native Patterns](#text-native-patterns)
3. [Ambiguous Patterns](#ambiguous-patterns)
4. [Common Anti-Patterns](#common-anti-patterns)
5. [Layer Boundary Rules](#layer-boundary-rules)

---

## Bytes-Native Patterns

These patterns work exclusively with bytes. Keep data as bytes throughout.

### Network I/O (socket)

```python
# Python 2 & 3 — socket.recv returns bytes
import socket
conn, addr = server_socket.accept()
data = conn.recv(4096)  # bytes

# Parse with struct
(msg_id, flags) = struct.unpack('>HB', data[:3])

# Send bytes back
response = struct.pack('>HB', response_id, 0)
conn.send(response)  # send bytes
conn.close()
```

**Rule:** socket.recv/send always work with bytes in both Py2 and Py3.

### Serial Port I/O

```python
import serial

ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
data = ser.read(10)  # bytes

# Parse
(command, length) = struct.unpack('>BB', data[:2])

# Send response
response = struct.pack('>BH', ACK_CMD, result)
ser.write(response)  # write bytes
```

**Rule:** Serial.read/write always work with bytes.

### Binary File I/O

```python
# Read binary
with open('protocol.bin', 'rb') as f:
    frame = f.read()  # bytes

# Parse with struct
(version, size) = struct.unpack('>HH', frame[:4])

# Write binary
with open('output.bin', 'wb') as f:
    f.write(frame)  # bytes
```

**Rule:** Always use 'rb'/'wb' mode for binary files in Py3.

### struct.pack / struct.unpack

```python
import struct

# struct.pack returns bytes
packet = struct.pack('>HBB', msg_id, flags, length)  # bytes
assert isinstance(packet, bytes)

# struct.unpack expects bytes
(msg_id, flags, length) = struct.unpack('>HBB', packet)  # ints/floats

# Common pattern: iterate over bytes
data = b'\x01\x02\x03'
for byte_val in data:
    # In Py3, byte_val is int (0-255), not str
    assert isinstance(byte_val, int)
    if byte_val == 0x01:
        ...
```

**Rule:** struct.pack/unpack strictly enforce bytes in Py3.

### CRC/Checksum Calculations

```python
# CRC operates on bytes, not characters
def crc16_ccitt(data: bytes) -> int:
    """Calculate CRC16-CCITT of bytes."""
    assert isinstance(data, bytes), "CRC input must be bytes"
    crc = 0xFFFF
    for byte_val in data:  # In Py3, byte_val is int
        crc ^= (byte_val << 8)
        for _ in range(8):
            crc <<= 1
            if crc & 0x10000:
                crc ^= 0x1021
            crc &= 0xFFFF
    return crc

# Usage
frame = socket.recv(256)
crc_recv = struct.unpack('>H', frame[-2:])[0]
crc_calc = crc16_ccitt(frame[:-2])
assert crc_calc == crc_recv, "CRC mismatch"
```

**Rule:** Checksum functions take bytes, iterate as ints.

### os.read

```python
import os

fd = os.open('/dev/ttyUSB0', os.O_RDONLY | os.O_NONBLOCK)
data = os.read(fd, 256)  # bytes
os.close(fd)
```

**Rule:** os.read returns bytes in both Py2 and Py3.

---

## Text-Native Patterns

These patterns work exclusively with strings (str in Py3). Decode from bytes early.

### String Formatting

```python
# Text-native — result is str, not bytes
msg = f"Received {packet_id} at {timestamp}"
assert isinstance(msg, str)

msg = "Value: {}".format(sensor_reading)
assert isinstance(msg, str)

msg = "Status: %s" % status_name
assert isinstance(msg, str)
```

**Rule:** All string formatting produces str, which is correct for display.

### print() and Logging

```python
import logging

# print() accepts str in Py3, not bytes
value = 42
print(f"Result: {value}")  # str, correct ✓

# Don't do this:
# print(b"Result: 42")  # Will print "b'Result: 42'" instead of "Result: 42"

# Logging always uses str
log = logging.getLogger(__name__)
log.info(f"Processed {count} records")  # str
```

**Rule:** Display layer (print, logging) always uses str.

### JSON Serialization

```python
import json

# json.dumps expects str or objects, not bytes
data = {"id": 123, "name": "sensor1"}
json_str = json.dumps(data)  # str
assert isinstance(json_str, str)

# Don't do this:
# json_bytes = json.dumps(data).encode('utf-8')  # unnecessary
```

**Rule:** JSON layer produces str; encode only if output destination requires bytes.

### Text File I/O

```python
# Read text with encoding
with open('config.ini', encoding='utf-8') as f:
    lines = f.readlines()  # list of str

# Write text with encoding
with open('output.txt', 'w', encoding='utf-8') as f:
    f.write("Hello\n")  # str
```

**Rule:** Always specify encoding for text files; never use default.

### UI Display / Configuration

```python
# Configuration values are str
config = {
    'hostname': 'scada.example.com',  # str
    'port': 502,  # int
    'timeout': 30.0,  # float
}

# User-facing strings are str
error_msg = f"Cannot connect to {config['hostname']}"  # str
display_value = f"Temperature: {temp:.1f}°C"  # str
```

**Rule:** Configuration and UI always use str.

### Database ORM (text columns)

```python
# Using SQLAlchemy or similar ORM
session.add(Sensor(name=sensor_name, location=location))
# name and location are str

# Binary columns use bytes
session.add(BinaryData(data=binary_blob))
# data is bytes
```

**Rule:** Text columns get str; BLOB columns get bytes.

---

## Ambiguous Patterns

These patterns require human judgment because data flow is unclear or crosses layer boundaries.

### Bytes-to-String Comparison

```python
# Python 2 — works (str == bytes if both are ASCII)
if record[0] == 'A':
    ...

# Python 3 — fails
# TypeError: 'bytes' != 'str'

# Fix: option 1 — use bytes literal
if record[0:1] == b'A':  # Compare bytes to bytes
    ...

# Fix: option 2 — decode first
text = record.decode('utf-8')
if text[0] == 'A':  # Compare str to str
    ...

# Ambiguous decision: is this field ASCII text or binary?
# Need to check with domain expert.
```

**Pattern:** Comparing bytes/str literals without explicit conversion.

**Decision needed:** Is data text (ASCII/UTF-8/EBCDIC) or binary?

### Mixed Encoding in One Module

```python
def process_message(data):
    """Ambiguous: is data bytes or str?"""
    # Could be called from network layer (bytes) or API layer (str)
    if isinstance(data, bytes):
        text = data.decode('utf-8')
    else:
        text = data
    return text.upper()

# Call 1: from socket (bytes)
raw = socket.recv(256)
result = process_message(raw)  # bytes

# Call 2: from user input (str)
user_input = input("Enter message: ")
result = process_message(user_input)  # str
```

**Pattern:** Function accepts both bytes and str without clear documentation.

**Decision needed:** Should this be bytes-only, str-only, or explicitly polymorphic?

### EBCDIC with Ambiguous Codec

```python
# Mainframe data — is it cp037, cp500, or cp1047?
def parse_cobol_record(data: bytes) -> dict:
    """
    Ambiguous: which EBCDIC codec?
    - cp037: US/Canada mainframes
    - cp500: International mainframes
    - cp1047: Latin-1 extended
    """
    text = data.decode('cp500')  # Guessed codec — might be wrong
    ...
```

**Pattern:** EBCDIC decode without clear codec variant.

**Decision needed:** Which codec variant is used in your mainframe system?

### Legacy String Operations on Bytes

```python
# Python 2 — works (str methods on bytes)
data = socket.recv(256)
msg = data.split(b':')[0]  # Py2: this is str, not bytes!

# Python 3 — must be explicit
data = socket.recv(256)
msg = data.split(b':')[0]  # bytes
msg_str = msg.decode('utf-8')  # convert if needed
```

**Pattern:** Calling str methods on bytes without type clarity.

**Decision needed:** What's the intended data type for this variable?

---

## Common Anti-Patterns

### ❌ Silent Type Coercion

```python
# Python 2 — silently coerces bytes ↔ str
data = socket.recv(256)
msg = "Got: " + data  # Works in Py2 (bytes + bytes), fails in Py3

# ✓ Py3 fix: explicit
msg = "Got: " + data.decode('utf-8')  # str + str
```

### ❌ Implicit Encoding Assumption

```python
# Python 2 — assumes system default (often ASCII, sometimes Latin-1)
with open('data.txt') as f:
    lines = f.readlines()

# ✓ Py3 fix: explicit UTF-8
with open('data.txt', encoding='utf-8') as f:
    lines = f.readlines()
```

### ❌ Default .decode() Without Codec

```python
# Python 2 — assumes ASCII
data = b'\x81\x82\x83'
try:
    text = data.decode()  # Py3: UTF-8, wrong for EBCDIC!
except UnicodeDecodeError:
    text = '???'

# ✓ Py3 fix: explicit codec
text = data.decode('cp500', errors='replace')  # EBCDIC with fallback
```

### ❌ Binary File Opened as Text

```python
# Python 2 — both work the same
with open('protocol.bin') as f:
    frame = f.read()  # bytes in Py2

# Python 3 — fails
with open('protocol.bin') as f:
    frame = f.read()  # str in Py3 — TypeError later!

# ✓ Py3 fix: explicit 'rb'
with open('protocol.bin', 'rb') as f:
    frame = f.read()  # bytes ✓
```

### ❌ Incorrect .encode() / .decode() Codec

```python
# EBCDIC data decoded as UTF-8
ebcdic_bytes = b'\xC1\xC2\xC3'  # 'ABC' in cp500
text = ebcdic_bytes.decode('utf-8')  # UnicodeDecodeError or garbage

# ✓ Fix: correct codec
text = ebcdic_bytes.decode('cp500')  # 'ABC' ✓
```

---

## Layer Boundary Rules

### Rule 1: Binary Layer (bytes)

At the **binary layer** (network, serial, file I/O), data is always bytes:

```python
# Socket layer
data = socket.recv(256)  # bytes
response = struct.pack('>H', result)  # bytes
socket.send(response)  # bytes

# The entire flow stays bytes until the next layer
```

### Rule 2: Parsing Layer (struct → ints)

Between **binary** and **text** layers, use struct to unpack bytes to native types:

```python
frame = socket.recv(256)  # bytes
(msg_id, flags, length) = struct.unpack('>HBH', frame[:5])  # ints

# Now we have native Python ints; never go back to bytes
if msg_id == 0x1234:  # int comparison
    ...
```

### Rule 3: Text Layer (str)

At the **text layer** (display, logging, JSON, UI), everything is str:

```python
# Format for display
msg = f"Received message {msg_id} from {sender}"  # str
log.info(msg)  # str
json_output = json.dumps({"id": msg_id, "msg": msg})  # str
```

### Rule 4: Codec at Boundary

When crossing between **bytes** and **str**, use explicit `.encode()` / `.decode()` with codec:

```python
# Bytes → Str: use .decode(codec)
raw_frame = socket.recv(256)  # bytes
frame_text = raw_frame.decode('utf-8')  # str

# Str → Bytes: use .encode(codec)
message = "Hello"  # str
encoded = message.encode('utf-8')  # bytes
socket.send(encoded)  # bytes
```

### Rule 5: No Mixed Operations

Never mix bytes and str in the same operation:

```python
# ❌ Wrong
msg = "Message: " + data  # bytes + str — TypeError

# ✓ Right
msg = "Message: " + data.decode('utf-8')  # str + str
```

---

## Decision Tree

When you encounter a bytes/str boundary, use this decision tree:

```
Is this data coming from or going to a binary source?
(socket, serial port, binary file, struct.pack/unpack)
  |
  YES → BYTES-NATIVE
        └─ Keep as bytes throughout parsing layer
        └─ Decode only when displaying to user/logging

  NO → Is this data a string literal, format operation, or display?
       (string format, print, logging, JSON, config)
       |
       YES → TEXT-NATIVE
             └─ Use str
             └─ Encode only when writing to binary sink

       NO → Is data flow unclear or crossing layers?
            |
            YES → AMBIGUOUS
                  └─ Requires human review
                  └─ Check with domain expert
                  └─ Document decision in code
```

