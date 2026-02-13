---
name: py2to3-test-scaffold-generator
description: >
  Generate characterization tests for Python 2 modules before Python 2→3 migration, with special
  attention to encoding edge cases and data boundary behavior. Use this skill whenever you
  need to add test coverage before converting modules, generate encoding-aware tests for
  data layer code, create characterization tests that capture current behavior, or build
  property-based tests for data transformations. Also trigger when someone says "generate
  tests for migration," "add test coverage," "create characterization tests," "test the
  data layer," "test encoding handling," "we need tests before converting," or "safety net
  for migration." The tests this skill generates are the safety net for the entire migration
  — they verify that behavior is preserved through conversion.
---

# Test Scaffold Generator

Before converting any module, you need tests that capture its current behavior. Not
"correct" behavior — we don't know what correct is in a codebase with no documentation
and no original developers. We need tests that say "given this input, the module currently
produces this output." After conversion to Python 3, the same tests should produce the
same outputs.

These are **characterization tests**: they characterize what the code does now so we can
verify it still does the same thing later.

## Why Encoding-Aware Tests Matter

Normal test generation focuses on logic paths. For a Py2→Py3 migration, the critical
paths are the data paths — anywhere bytes become text or text becomes bytes. A test suite
that only uses ASCII data will miss every encoding-related regression. This skill
deliberately generates tests with non-ASCII data:

- **UTF-8**: Accented characters (café), emoji, CJK text
- **Latin-1**: Characters in the 0x80-0xFF range that aren't valid UTF-8
- **EBCDIC**: Characters that map to completely different byte values than ASCII
- **Binary**: Byte sequences that aren't valid in any text encoding

## Test Types Generated

### Characterization Tests
Capture the module's current behavior with representative inputs. These may need updating
after migration if the behavior intentionally changes (e.g., a function that returns bytes
in Py2 should return str in Py3).

### Encoding Boundary Tests
Specifically test every point identified by the Data Format Analyzer (Skill 0.2) where
data crosses the bytes/str boundary. Use non-ASCII inputs to ensure encoding is handled
correctly.

### Round-Trip Tests
For serialization paths (pickle, marshal, shelve, JSON, etc.), verify that data survives
a serialize-then-deserialize cycle. Important: the serialized form may change between Py2
and Py3 (pickle protocol differences), but the logical data should be preserved.

### Property-Based Tests (Optional)
For data transformation functions, generate `hypothesis`-based tests that explore the
input space automatically. Especially valuable for functions that handle variable-length
data, mixed encodings, or binary protocols.

## Inputs

- **module_path**: Path to the module(s) to test
- **output_dir**: Where to write test files
- **data_layer_report** (optional): Path to the data-layer-report.json from Skill 0.2
- **encoding_map** (optional): Path to encoding-map.json from Skill 0.2
- **target_version**: Target Python 3 version (affects test framework features used)
- **test_framework**: Which framework to use (default: `pytest`; also supports `unittest`)
- **include_hypothesis**: Whether to generate property-based tests (default: `false`)

## Outputs

| File | Format | Purpose |
|------|--------|---------|
| `test_<module>_characterization.py` | Python | Characterization tests |
| `test_<module>_encoding.py` | Python | Encoding boundary tests |
| `test_<module>_roundtrip.py` | Python | Serialization round-trip tests |
| `test_<module>_properties.py` | Python | Property-based tests (if requested) |
| `test-coverage-report.json` | JSON | Before/after coverage metrics |
| `test-manifest.json` | JSON | Catalog of all generated tests |

## Workflow

### Step 1: Analyze the Module

```bash
python3 scripts/generate_tests.py <module_path> \
    --output <output_dir> \
    --target-version 3.12 \
    [--data-report <data-layer-report.json>] \
    [--encoding-map <encoding-map.json>] \
    [--framework pytest] \
    [--include-hypothesis]
```

The script performs AST analysis on the module to identify:
- All public functions and classes (for characterization tests)
- Function signatures and default arguments
- Data ingestion/egression points (for encoding tests)
- Serialization operations (for round-trip tests)
- Exception handling patterns

### Step 2: Generate Test Files

The script produces test files organized by purpose. Each test is tagged with its type
so the migration team can distinguish characterization tests (may need updating) from
correctness tests (should never change).

### Step 3: Review Coverage

```bash
python3 scripts/measure_coverage.py <module_path> \
    --test-dir <output_dir> \
    --output <output_dir>/test-coverage-report.json
```

## Test Generation Strategy

### For Each Public Function

```python
# Template: characterization test
def test_{function_name}_characterization_basic():
    """Characterization test: capture current behavior."""
    # GENERATED: This test captures the function's current behavior.
    # If this test fails after Py3 conversion, investigate whether the
    # behavior change is expected or a regression.
    result = module.{function_name}({representative_args})
    assert result == {observed_result}  # Captured from Py2 execution
```

### For Data Boundary Points

```python
# Template: encoding boundary test
def test_{function_name}_encoding_utf8():
    """Encoding test: verify behavior with UTF-8 input."""
    input_data = "café résumé naïve"  # Non-ASCII but common
    result = module.{function_name}(input_data)
    # Verify no UnicodeError and result type is consistent
    assert isinstance(result, (str, bytes))

def test_{function_name}_encoding_latin1():
    """Encoding test: Latin-1 characters outside ASCII."""
    input_data = b'\xe9\xe8\xea'  # é è ê in Latin-1
    result = module.{function_name}(input_data)
    assert result is not None  # At minimum, should not crash
```

### For Serialization Round-Trips

```python
# Template: round-trip test
def test_{class_name}_pickle_roundtrip():
    """Round-trip: pickle serialize then deserialize."""
    import pickle
    obj = module.{class_name}({constructor_args})
    pickled = pickle.dumps(obj, protocol=2)  # Py2-compatible protocol
    restored = pickle.loads(pickled)
    assert restored == obj  # Or equivalent comparison
```

## Test Manifest

The manifest tracks every generated test so the team knows which ones are
characterization tests (may need updating post-migration) and which are
correctness tests (should always pass):

```json
{
  "generated": "ISO-8601",
  "module": "src/scada/modbus_reader.py",
  "tests": [
    {
      "file": "test_modbus_reader_characterization.py",
      "test_name": "test_read_register_basic",
      "type": "characterization",
      "target_function": "read_register",
      "data_category": null,
      "notes": "Captures current return type (str in Py2, may become bytes in Py3)"
    },
    {
      "file": "test_modbus_reader_encoding.py",
      "test_name": "test_read_register_utf8",
      "type": "encoding_boundary",
      "target_function": "read_register",
      "data_category": "binary_protocol",
      "notes": "Tests with non-ASCII register data"
    }
  ],
  "coverage": {
    "before": null,
    "after": null
  }
}
```

## Integration with Other Skills

This skill depends on outputs from:
- **Skill 0.2 (Data Format Analyzer)**: `encoding-map.json` and `bytes-str-boundaries.json`
  tell us where to focus encoding tests
- **Skill 1.1 (Future Imports Injector)**: `high-risk-modules.json` identifies modules
  that need extra characterization tests

This skill's outputs feed into:
- **Skill X.3 (Gate Checker)**: `test-coverage-report.json` is evidence for the Phase 1→2
  gate's test coverage criterion
- **Skill 4.1 (Behavioral Diff Generator)**: Uses the generated tests to compare Py2/Py3 behavior

After running, update the migration state:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py \
    <state_file> record-output \
    --module <module_path> \
    --output-path <output_dir>/test-manifest.json
```

## Important Notes

**Characterization tests may "fail" correctly.** After migration, some characterization
tests will fail because the behavior intentionally changed (e.g., a function that returned
bytes now returns str). This is expected. The test manifest helps distinguish these expected
changes from actual regressions.

**Encoding tests should use real-world patterns.** For SCADA code, use actual Modbus
register values. For mainframe code, use actual EBCDIC byte sequences. The reference
documents in `references/` contain test vectors for these.

**Coverage is a means, not an end.** The goal isn't 100% coverage — it's coverage on
the paths that matter for migration. A module with 40% overall coverage but 100% coverage
on its data ingestion paths is better protected than one with 80% coverage that never
tests with non-ASCII data.
