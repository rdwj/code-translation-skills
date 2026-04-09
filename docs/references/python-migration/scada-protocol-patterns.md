# SCADA / IoT Protocol Patterns Reference

Reference for common data handling patterns in IoT, SCADA, CNC, and industrial
automation codebases. Used by the Data Format Analyzer (0.2) and Bytes/String
Boundary Fixer (3.1).

## Table of Contents

1. [Modbus Protocol](#modbus)
2. [OPC-UA](#opcua)
3. [DNP3](#dnp3)
4. [Serial / RS-232/485](#serial)
5. [CNC / G-code](#cnc)
6. [Common Python Libraries](#libraries)
7. [Migration Patterns](#migration)

---

## Modbus

### How Modbus Data Works

Modbus is a register-based protocol. Data is stored in 16-bit registers (holding
registers, input registers) or single-bit values (coils, discrete inputs). The
protocol itself is purely binary.

A Modbus "register" is 2 bytes (big-endian by default). Common patterns:

| Register Type | Read Function Code | Data Width | Python Type |
|--------------|-------------------|------------|-------------|
| Coil | FC01 | 1 bit | bool |
| Discrete Input | FC02 | 1 bit | bool |
| Input Register | FC04 | 16 bits | int |
| Holding Register | FC03 | 16 bits | int |

### Python Code Patterns

```python
# pymodbus pattern — reading holding registers
from pymodbus.client.sync import ModbusTcpClient
client = ModbusTcpClient('192.168.1.100')
result = client.read_holding_registers(address=0, count=10, unit=1)
values = result.registers  # list of ints (16-bit values)

# minimalmodbus pattern
import minimalmodbus
inst = minimalmodbus.Instrument('/dev/ttyUSB0', 1)
temperature = inst.read_register(0, 1)  # returns float

# Raw Modbus over TCP (manual struct unpacking)
import socket, struct
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('192.168.1.100', 502))
# MBAP header: transaction_id(2) + protocol_id(2) + length(2) + unit_id(1)
request = struct.pack('>HHHBB', 0x0001, 0x0000, 0x0006, 0x01, 0x03)
request += struct.pack('>HH', 0x0000, 0x000A)  # start_addr, num_registers
sock.send(request)
response = sock.recv(1024)
# Parse response — this is where bytes/str confusion typically lives
```

### Migration Risk Areas

1. **`struct.unpack` results fed to string operations**: After unpacking register
   values, legacy code may convert to string with `str()` — in Py2 this is a
   bytes-compatible str, in Py3 it's a text str. Usually fine for display, but
   check if the string is later written to a binary protocol.

2. **Raw TCP Modbus**: Code that builds Modbus frames manually with `struct.pack`
   and `socket.send` needs to ensure it sends `bytes`, not `str`.

3. **Register-to-string conversion**: Values like `temperature = str(registers[0] / 10.0)`
   — the division behavior also changes (integer division in Py2 vs true division).

4. **Modbus ASCII mode** (as opposed to RTU or TCP): The ASCII mode transmits data
   as ASCII hex characters. Code handling this mode will have extensive
   string↔bytes interaction.

---

## OPC-UA

### Data Model

OPC-UA uses typed data nodes. Relevant types for migration:

| OPC-UA Type | Python Mapping | Migration Risk |
|-------------|---------------|----------------|
| String | str | Low (already text) |
| ByteString | bytes | Medium (was str in Py2) |
| LocalizedText | str | Low |
| XmlElement | str | Low |
| NodeId (string form) | str | Low |

### Python Library: opcua / asyncua

```python
from opcua import Client
client = Client("opc.tcp://localhost:4840")
client.connect()
node = client.get_node("ns=2;i=3")
value = node.get_value()  # type depends on the node's data type
```

The main risk is `ByteString` nodes — the value comes back as bytes, and Py2 code
may treat it as a regular string.

---

## DNP3

### Protocol Structure

DNP3 (Distributed Network Protocol) is used in utilities (water, electric, gas).
It's a binary protocol with complex framing:

- **Data Link Layer**: CRC-protected binary frames
- **Transport Layer**: Fragment reassembly
- **Application Layer**: Objects with typed data points

### Python Code Patterns

```python
# pydnp3 pattern
from pydnp3 import opendnp3
# Binary data points
analog_value = response.analog[0].value  # float
binary_value = response.binary[0].value  # bool

# Manual DNP3 parsing (legacy code)
frame = serial_port.read(292)  # max DNP3 frame size
start_bytes = frame[0:2]  # 0x05, 0x64
length = struct.unpack('<B', frame[2:3])[0]
```

### Migration Risk

DNP3 parsers that manually unpack frames have extensive `struct` usage and
byte-level operations. The `frame[i]` indexing change (returns int in Py3
instead of str in Py2) is the primary concern.

---

## Serial / RS-232/485

### pyserial Patterns

```python
import serial
ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)

# Read — returns bytes in Py3, str (bytes-compatible) in Py2
data = ser.read(100)
line = ser.readline()

# Write — requires bytes in Py3
ser.write(b'AT\r\n')           # Py3 correct
ser.write('AT\r\n')            # Py2 works, Py3 TypeError
ser.write('AT\r\n'.encode())   # Py3 correct alternative
```

### Common Patterns in Industrial Code

```python
# Pattern: Read sensor value from serial, parse as text
response = ser.readline()          # bytes in Py3
value = response.strip().split(',')  # Py2: works. Py3: need .decode() first

# Pattern: Send command, check echo
ser.write(command)
echo = ser.read(len(command))
if echo == command:  # Py2: str==str. Py3: need matching types
    pass

# Pattern: STX/ETX framing (common in industrial protocols)
STX = '\x02'  # Py2: str byte. Py3: str character
ETX = '\x03'
data = ser.read_until(ETX)  # Py3: need b'\x03'
```

---

## CNC / G-code

### G-code Structure

G-code is plain ASCII text with positional semantics:

```
G01 X100.0 Y200.0 F500    ; Linear move
M03 S12000                  ; Spindle on
```

### Parsing Patterns

```python
# Positional parsing — common in legacy CNC code
line = "G01 X100.0 Y200.0 F500"
code = line[0:3]          # "G01" — works same in Py2 and Py3 IF line is str
x_pos = line[4:10]        # "X100.0"
value = float(x_pos[1:])  # 100.0

# Character-by-character parsing
for char in line:
    if char == 'G':       # Py2 and Py3 same IF line is str, not bytes
        ...
```

### Migration Risks

1. **If G-code is read from file without encoding**: `open('program.nc')` in Py2
   returns bytes-as-str; in Py3 returns text with system default encoding. Usually
   safe for ASCII G-code, but Japanese Fanuc controllers may embed Shift-JIS comments.

2. **If G-code is read from serial port**: `ser.readline()` returns bytes in Py3.
   All the positional parsing (`line[0:3]`) works differently on bytes vs str.

3. **Fixed-width field extraction**: `line[start:end]` is the same for str in both
   versions, but if the data source changes from returning str to bytes, all
   indexes still work but return `bytes` (and `bytes[0]` returns int, not char).

---

## Common Python Libraries

| Library | Protocol | Py3 Support | Notes |
|---------|----------|-------------|-------|
| `pymodbus` | Modbus TCP/RTU | Yes (2.x+) | Verify version compatibility |
| `minimalmodbus` | Modbus RTU | Yes | |
| `opcua` | OPC-UA | Py2 only | Use `asyncua` for Py3 |
| `asyncua` | OPC-UA | Py3 only | Async-first, replacement for `opcua` |
| `pydnp3` | DNP3 | Yes | |
| `pyserial` | Serial | Yes (3.x+) | Returns bytes in Py3 |
| `pymodbus3` | Modbus | Py3 only | Fork of pymodbus |

---

## Migration Patterns

### General Rule: Decode at Ingestion, Encode at Egression

```
[Binary Source] → .decode(codec) → str → [Application Logic] → .encode(codec) → [Binary Sink]
     bytes                        text                          bytes
```

### Modbus Register → Display Value

```python
# Before (Py2):
registers = client.read_holding_registers(0, 2)
temp = registers[0] / 10  # integer division in Py2!
display = "Temperature: %s" % str(temp)

# After (Py3):
registers = client.read_holding_registers(0, 2)
temp = registers[0] / 10.0  # explicit float division
display = f"Temperature: {temp}"  # f-string, no bytes/str issue
```

### Serial Read → Parse → Act

```python
# Before (Py2):
response = ser.readline()  # str (bytes-compatible)
parts = response.strip().split(',')
value = float(parts[1])

# After (Py3):
response = ser.readline()  # bytes
response_text = response.decode('ascii')  # or 'utf-8', depending on device
parts = response_text.strip().split(',')
value = float(parts[1])
```

### Socket Frame → Struct Unpack → Process

```python
# Before (Py2):
frame = sock.recv(256)
header = struct.unpack('>HHH', frame[:6])
payload = frame[6:]
if payload[0] == '\x01':  # comparing str byte

# After (Py3):
frame = sock.recv(256)  # bytes
header = struct.unpack('>HHH', frame[:6])  # still works (bytes input)
payload = frame[6:]  # still bytes
if payload[0] == 0x01:  # comparing int (bytes indexing returns int in Py3)
```
