# Hypothesis Testing Strategies

Property-based testing strategies for Python 2→3 migration verification using the
`hypothesis` library. These strategies generate randomized inputs to exercise data
transformations, encoding paths, and boundary conditions that manual test cases miss.

---

## Why Property-Based Testing for Migration

Traditional unit tests check specific inputs and expected outputs. Property-based tests
check that *properties* hold for *all* inputs. In a Py2→Py3 migration, key properties
include:

- **Round-trip**: `decode(encode(text)) == text` for all text
- **Idempotence**: Converting a module twice produces the same result as converting once
- **Equivalence**: `py2_function(input) == py3_function(input)` for all valid inputs
- **Type consistency**: Functions that return `str` in Py2 should return `str` in Py3
  (not `bytes`)

Hypothesis finds the edge cases humans forget: empty strings, null bytes, surrogate
characters, maximum-length inputs, and combinations thereof.

---

## Core Strategies

### Text Strategies

```python
from hypothesis import strategies as st

# Basic text (ASCII only)
ascii_text = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126))

# Text with common extended characters
extended_text = st.text(alphabet=st.characters(
    min_codepoint=32,
    max_codepoint=0xFFFF,
    blacklist_categories=('Cs',),  # Exclude surrogates
))

# Text that's valid in a specific encoding
latin1_text = st.text(alphabet=st.characters(
    min_codepoint=0,
    max_codepoint=255,
    whitelist_categories=('L', 'N', 'P', 'Z', 'S'),
))

# Text with CJK characters (for CNC/Japanese equipment)
cjk_text = st.text(alphabet=st.characters(
    min_codepoint=0x4E00,
    max_codepoint=0x9FFF,
))

# Mixed text: ASCII + accented + CJK
mixed_text = st.text(alphabet=st.characters(
    whitelist_categories=('L', 'N', 'P', 'Z', 'S'),
    blacklist_categories=('Cs',),
))

# Text that includes combining characters
combining_text = st.text(alphabet=st.characters(
    whitelist_categories=('L', 'M', 'N', 'P', 'Z'),
    blacklist_categories=('Cs',),
))
```

### Bytes Strategies

```python
# Arbitrary bytes (any value 0x00-0xFF)
raw_bytes = st.binary()

# Bytes that are valid UTF-8
valid_utf8_bytes = st.text(
    alphabet=st.characters(blacklist_categories=('Cs',))
).map(lambda t: t.encode('utf-8'))

# Bytes that are valid Latin-1 (all bytes are valid)
latin1_bytes = st.binary()

# Bytes that are valid EBCDIC text (printable range)
ebcdic_text_bytes = st.binary(min_size=1).map(
    lambda b: bytes(byte for byte in b if 0x40 <= byte <= 0xFE)
).filter(lambda b: len(b) > 0)

# Modbus register pairs (2-byte big-endian unsigned int)
modbus_register = st.integers(min_value=0, max_value=65535).map(
    lambda v: v.to_bytes(2, 'big')
)

# IEEE 754 float as bytes
ieee_float_bytes = st.floats(
    allow_nan=False, allow_infinity=False
).map(lambda f: __import__('struct').pack('>f', f))
```

### Structured Data Strategies

```python
# Fixed-width record (like mainframe)
def fixed_width_record(field_sizes):
    """Generate a fixed-width record with given field sizes."""
    fields = [st.binary(min_size=size, max_size=size) for size in field_sizes]
    return st.tuples(*fields).map(lambda fs: b''.join(fs))

# Modbus RTU frame
modbus_frame = st.tuples(
    st.integers(1, 247),       # unit_id
    st.integers(1, 127),       # function_code
    st.binary(min_size=0, max_size=252),  # data
).map(lambda t: bytes([t[0], t[1]]) + t[2])

# EBCDIC record with mixed text and packed decimal
ebcdic_record = st.tuples(
    st.text(min_size=10, max_size=10, alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '),
    st.integers(0, 999999),
).map(lambda t: t[0].encode('cp500') + _pack_bcd(t[1]))

def _pack_bcd(value):
    """Pack integer as EBCDIC packed decimal (COMP-3)."""
    sign = 0x0C if value >= 0 else 0x0D
    digits = str(abs(value))
    if len(digits) % 2 == 0:
        digits = '0' + digits
    result = bytes(int(digits[i:i+2], 16) for i in range(0, len(digits)-1, 2))
    last_digit = int(digits[-1])
    result += bytes([(last_digit << 4) | sign])
    return result

# CSV row with mixed types
csv_row = st.tuples(
    st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=('L', 'N'),
        blacklist_characters=',\n\r"',
    )),
    st.integers(-1000000, 1000000),
    st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
).map(lambda t: f'{t[0]},{t[1]},{t[2]:.6f}')
```

---

## Property Templates

### Round-Trip Properties

```python
from hypothesis import given, settings

@given(text=extended_text)
def test_utf8_roundtrip(text):
    """UTF-8 encode/decode round-trips for all valid Unicode text."""
    encoded = text.encode('utf-8')
    decoded = encoded.decode('utf-8')
    assert decoded == text

@given(text=latin1_text)
def test_latin1_roundtrip(text):
    """Latin-1 encode/decode round-trips for all Latin-1 text."""
    encoded = text.encode('latin-1')
    decoded = encoded.decode('latin-1')
    assert decoded == text

@given(data=raw_bytes)
def test_latin1_bytes_roundtrip(data):
    """Every byte sequence survives Latin-1 decode/encode."""
    text = data.decode('latin-1')
    reencoded = text.encode('latin-1')
    assert reencoded == data

@given(text=st.text(alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 '))
def test_ebcdic_roundtrip(text):
    """EBCDIC encode/decode round-trips for basic alphanumeric text."""
    encoded = text.encode('cp500')
    decoded = encoded.decode('cp500')
    assert decoded == text
```

### Type Consistency Properties

```python
@given(data=raw_bytes)
def test_socket_recv_returns_bytes(data):
    """Simulated socket.recv always returns bytes."""
    # In migrated code, recv should always return bytes
    assert isinstance(data, bytes)
    # And struct.unpack on bytes should return tuple of ints
    if len(data) >= 2:
        result = struct.unpack('>H', data[:2])
        assert isinstance(result[0], int)

@given(text=extended_text)
def test_string_operations_return_str(text):
    """String operations on str return str, not bytes."""
    if text:
        assert isinstance(text.upper(), str)
        assert isinstance(text.lower(), str)
        assert isinstance(text.strip(), str)
        assert isinstance(text[:1], str)
        parts = text.split()
        for part in parts:
            assert isinstance(part, str)
```

### Equivalence Properties

```python
@given(value=st.integers(0, 65535))
def test_modbus_register_parse_equivalence(value):
    """Modbus register parsing produces same value in Py2 and Py3."""
    raw = struct.pack('>H', value)
    parsed = struct.unpack('>H', raw)[0]
    assert parsed == value
    assert isinstance(parsed, int)

@given(items=st.lists(st.tuples(ascii_text, st.integers())))
def test_dict_serialization_equivalence(items):
    """Dict JSON serialization is semantically equivalent regardless of order."""
    d = dict(items)
    json_str = json.dumps(d, sort_keys=True)
    roundtripped = json.loads(json_str)
    assert roundtripped == d

@given(data=raw_bytes)
def test_crc_on_bytes(data):
    """CRC computation works on bytes (not str) and is deterministic."""
    if len(data) >= 2:
        crc1 = _compute_crc(data)
        crc2 = _compute_crc(data)
        assert crc1 == crc2
        assert isinstance(crc1, int)
```

### Boundary Properties

```python
@given(data=raw_bytes)
def test_no_implicit_decode(data):
    """Bytes data should never be implicitly compared to str."""
    text = "hello"
    # In Py3, this comparison returns False (not TypeError)
    assert (data == text) == False or data == text.encode('utf-8')

@given(text=extended_text, encoding=st.sampled_from(['utf-8', 'latin-1', 'ascii']))
def test_open_text_mode_encoding(text, encoding):
    """Text written with explicit encoding can be read back."""
    try:
        encoded = text.encode(encoding)
        decoded = encoded.decode(encoding)
        assert decoded == text
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass  # Not all text is representable in all encodings — that's expected
```

---

## SCADA-Specific Strategies

```python
# Modbus holding register block (common: 1-125 registers)
modbus_register_block = st.integers(1, 125).flatmap(
    lambda n: st.binary(min_size=n*2, max_size=n*2)
)

# Temperature reading (common range: -40.0 to 150.0 °C)
temperature_reading = st.floats(min_value=-40.0, max_value=150.0).map(
    lambda f: struct.pack('>f', f)
)

# Pressure reading (common range: 0 to 1000 PSI)
pressure_reading = st.floats(min_value=0, max_value=1000).map(
    lambda f: struct.pack('>f', f)
)

# Water level (common range: 0 to 100 meters)
water_level = st.floats(min_value=0, max_value=100).map(
    lambda f: struct.pack('>f', f)
)

# Timestamp (seconds since epoch, uint32)
scada_timestamp = st.integers(0, 2**32 - 1).map(
    lambda t: struct.pack('>I', t)
)

# Alarm status word (16 bits, each bit = one alarm)
alarm_status = st.integers(0, 0xFFFF).map(
    lambda s: struct.pack('>H', s)
)
```

---

## Mainframe-Specific Strategies

```python
# EBCDIC text field (space-padded, fixed width)
def ebcdic_field(width):
    return st.text(
        min_size=1,
        max_size=width,
        alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-/',
    ).map(lambda t: t.ljust(width).encode('cp500'))

# COBOL PIC 9(N) numeric display field
def cobol_numeric(digits):
    return st.integers(0, 10**digits - 1).map(
        lambda n: str(n).zfill(digits).encode('cp500')
    )

# COMP-3 packed decimal
def comp3(max_digits=9):
    return st.integers(-(10**max_digits - 1), 10**max_digits - 1).map(_pack_bcd)

# Fixed-width mainframe record
mainframe_record = st.tuples(
    ebcdic_field(20),           # Name field, 20 chars
    ebcdic_field(10),           # Account number
    cobol_numeric(8),           # Date YYYYMMDD
    comp3(7),                   # Balance (packed decimal)
    st.binary(min_size=4, max_size=4),  # Binary timestamp
).map(lambda fields: b''.join(fields))
```

---

## Test Configuration

### Recommended `hypothesis` Settings

```python
from hypothesis import settings, HealthCheck

# For migration testing: more examples, slower but thorough
migration_settings = settings(
    max_examples=500,
    deadline=None,  # Disable deadline for slow I/O tests
    suppress_health_check=[HealthCheck.too_slow],
    database=None,  # Don't persist database between runs
)

# For CI: faster, fewer examples
ci_settings = settings(
    max_examples=100,
    deadline=5000,  # 5 second deadline
)

# For encoding stress testing: many examples, focus on edge cases
encoding_stress_settings = settings(
    max_examples=1000,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.large_base_example],
)
```

### Integration with Skill 4.3 (Encoding Stress Tester)

The encoding stress tester uses hypothesis strategies to generate inputs. Configure it
to use the `encoding_stress_settings` profile and the SCADA/mainframe-specific strategies
defined above.

```python
# In stress test runner:
@given(data=modbus_register_block)
@settings(encoding_stress_settings)
def test_modbus_data_path(data):
    """Exercise entire Modbus data path with random register data."""
    # Parse registers
    registers = [
        struct.unpack('>H', data[i:i+2])[0]
        for i in range(0, len(data), 2)
    ]
    # Verify all are integers
    assert all(isinstance(r, int) for r in registers)
    # Verify range
    assert all(0 <= r <= 65535 for r in registers)
    # Verify round-trip
    repacked = b''.join(struct.pack('>H', r) for r in registers)
    assert repacked == data
```
