---
name: py2to3-behavioral-diff-generator
description: >
  Run the same inputs through both Python 2 and Python 3 code paths, capture every
  observable output, and compare them. Any unexpected difference is a potential migration
  bug. Use this skill whenever you need to verify behavioral equivalence after conversion,
  prove that Py3 code produces the same results as Py2, identify regressions introduced
  during mechanical or semantic conversion, or generate evidence for the Phase 4→5 gate
  check. Also trigger when someone says "compare Py2 vs Py3 output," "are there behavioral
  differences," "run the diff check," "does the migration break anything," or "generate
  the behavioral diff report." This is the primary correctness proof — zero unexpected
  diffs is the gate criterion for advancing to Phase 5.
---

# Skill 4.1: Behavioral Diff Generator

## Why Behavioral Diffs Matter

Passing tests is necessary but not sufficient. Tests check what the developer *thought*
to test; behavioral diffs check *everything observable*. In a legacy codebase with
incomplete test coverage, the behavioral diff catches regressions that tests miss:

- A function that used to return `b'OK'` now returns `'OK'` — tests that compare with
  `== 'OK'` pass under both interpreters (Py2 treats `b'OK' == 'OK'` as True), but
  downstream code that does `response + b'\n'` will crash under Py3.

- Dict ordering changed between Py2 and Py3 (dicts are insertion-ordered in 3.7+).
  JSON serialization of dicts may produce different output — this is *expected* but
  must be distinguished from *unexpected* differences.

- Integer division: `7 / 2` returns `3` in Py2 but `3.5` in Py3. If `from __future__
  import division` wasn't added everywhere, this is a silent behavioral change.

- `sorted()` with mixed types: Py2 allows comparing int to str (`sorted([1, 'a'])`);
  Py3 raises TypeError. The behavioral diff catches this at runtime.

The behavioral diff generator separates *expected differences* (dict repr, bytes repr,
unicode repr) from *unexpected differences* (value changes, type changes, errors) and
produces a clear report for human review.

---

## Inputs

| Input | From | Notes |
|-------|------|-------|
| **codebase_path** | User | Root directory of the Python codebase |
| **test_suite** | User | Path to test suite or test directory |
| **py2_interpreter** | User | Path to Python 2 interpreter (e.g., `python2.7`) |
| **py3_interpreter** | User | Path to Python 3 interpreter (e.g., `python3.12`) |
| **target_version** | User | Target Python 3.x version (e.g., 3.9, 3.12) |
| **--state-file** | User | Path to migration-state.json for recording results |
| **--output** | User | Output directory for reports |
| **--test-runner** | User | Test runner command (default: `pytest`) |
| **--timeout** | User | Per-test timeout in seconds (default: 60) |
| **--modules** | User | Specific modules to test (default: all) |
| **--capture-mode** | User | What to capture: `stdout`, `stderr`, `returncode`, `files`, `all` (default: `all`) |
| **--expected-diffs-config** | User | Path to JSON config listing known expected differences |

---

## Outputs

| Output | Purpose |
|--------|---------|
| **behavioral-diff-report.json** | Machine-readable: every diff found, categorized |
| **behavioral-diff-report.md** | Human-readable summary for stakeholders (from generate_diff_report.py) |
| **expected-differences.json** | Diffs classified as known/acceptable |
| **potential-bugs.json** | Diffs that need investigation |
| **py2-outputs.json** | Raw captured outputs from Python 2 runs |
| **py3-outputs.json** | Raw captured outputs from Python 3 runs |

---

## Scope and Chunking

Behavioral diff generation runs test inputs through both Python 2 and Python 3 interpreters and compares outputs. The output size is proportional to the test suite size × the number of behavioral differences found.

**Scoping strategy**: Run per conversion unit, not per codebase. The conversion unit's tests are the natural scope boundary.

**For large test suites (200+ tests per unit)**: Split into test categories:
1. First pass: Unit tests only (fast, targeted)
2. Second pass: Integration tests (cross-module, may reveal boundary issues)
3. Third pass: Characterization tests (behavioral preservation validation)

Present only the diffs that show actual behavioral differences — identical outputs need not appear in the conversation. The full comparison matrix should be saved to disk.

**Expected output sizes**:
- 50 tests with few diffs: 10–30KB
- 200 tests with moderate diffs: 50–150KB
- 500+ tests: Split into batches; do not attempt in a single pass

**Key principle**: The agent should report behavioral diffs by severity (breaking → semantic → cosmetic) and focus the conversation on breaking changes. The full matrix lives on disk.

---

## Workflow

### 1. Discover Test Cases

Scan the test suite to build an inventory of executable test cases:

```bash
python3 scripts/generate_diffs.py <codebase_path> \
    --test-suite tests/ \
    --py2 /usr/bin/python2.7 \
    --py3 /usr/bin/python3.12 \
    --target-version 3.12 \
    --output ./behavioral-diff-output/
```

The script discovers tests using the test runner's collection mechanism (e.g.,
`pytest --collect-only`).

### 2. Execute Under Both Interpreters

For each test case:

1. Run under Python 2 interpreter, capturing:
   - Return code (0 = pass, non-zero = fail)
   - stdout (all printed output)
   - stderr (warnings, errors)
   - Execution time
   - Any files written to a temp directory

2. Run under Python 3 interpreter with identical inputs, capturing the same.

3. Record both outputs for comparison.

### 3. Compare Outputs

For each test case, compare Py2 vs Py3 outputs across all captured dimensions:

#### Return Code Comparison
- Same return code → no diff
- Py2 passes, Py3 fails → **potential bug** (regression)
- Py2 fails, Py3 passes → **expected improvement** (Py3 might fix a Py2 bug)
- Both fail with different errors → **needs investigation**

#### Stdout/Stderr Comparison
- Exact match → no diff
- Differ only in repr format → **expected difference** (e.g., `u'foo'` vs `'foo'`)
- Differ only in dict ordering → **expected difference**
- Differ in values → **potential bug**
- One has output, other doesn't → **potential bug**

#### File Output Comparison
- Binary files: byte-for-byte comparison
- Text files: normalized comparison (strip trailing whitespace, normalize newlines)
- JSON/YAML files: semantic comparison (parse and compare structure, not text)

### 4. Classify Diffs

Each difference gets classified into one of these categories:

#### Expected Differences (Known Safe)

These are behavioral changes between Py2 and Py3 that are correct and expected:

| Pattern | Example | Why It's Safe |
|---------|---------|---------------|
| `repr()` format | `u'foo'` → `'foo'`, `123L` → `123` | Repr changes don't affect logic |
| Dict ordering in output | `{'b': 2, 'a': 1}` → `{'a': 1, 'b': 2}` | Insertion order vs arbitrary |
| Bytes repr | `'\\x00'` → `b'\\x00'` | Type awareness improvement |
| Exception message wording | `"integer argument expected"` vs different wording | Message text isn't API |
| `range()` repr | `[0, 1, 2]` → `range(0, 3)` | Iterator vs list is correct |
| `map()`/`filter()` repr | `[1, 2, 3]` → `<map object>` | Iterator vs list is correct |
| `round()` banker's rounding | `round(0.5) = 1` → `round(0.5) = 0` | IEEE 754 compliance |
| `True`/`False` type | `True == 1` identity vs equality | Boolean subclass of int |
| Relative import errors | Implicit relative import fails | Correct Py3 behavior |

#### Potential Bugs (Need Investigation)

| Pattern | Example | Why It's Suspicious |
|---------|---------|---------------------|
| Value change | `7/2 = 3` → `7/2 = 3.5` | Integer division semantics |
| Type change | Returns `str` → returns `bytes` | Bytes/str boundary issue |
| New exception | No error → `TypeError` | Missing conversion |
| Missing output | Output present → empty | Logic path changed |
| Encoding error | Clean output → `UnicodeDecodeError` | Encoding not handled |
| Sort order change | Consistent order → different order | Mixed-type comparison |

### 5. Generate Reports

```bash
python3 scripts/generate_diff_report.py \
    --diff-report behavioral-diff-output/behavioral-diff-report.json \
    --output behavioral-diff-output/behavioral-diff-report.md
```

---

## Expected Differences Configuration

You can pre-configure known expected differences so they're automatically classified:

```json
{
  "expected_patterns": [
    {
      "pattern": "repr_unicode_prefix",
      "description": "u'...' prefix removed in Py3 repr",
      "regex": "u'([^']*)'",
      "replacement": "'\\1'"
    },
    {
      "pattern": "repr_long_suffix",
      "description": "L suffix removed from long integers",
      "regex": "(\\d+)L\\b",
      "replacement": "\\1"
    },
    {
      "pattern": "dict_order",
      "description": "Dict ordering may differ between Py2 and Py3",
      "type": "structural_json",
      "compare_mode": "unordered"
    },
    {
      "pattern": "bytes_repr",
      "description": "Bytes repr differs",
      "regex": "'(\\\\x[0-9a-f]{2})'",
      "replacement": "b'\\1'"
    },
    {
      "pattern": "range_repr",
      "description": "range() returns iterator in Py3",
      "regex": "\\[([0-9, ]+)\\]",
      "type": "range_to_list"
    }
  ]
}
```

---

## SCADA/Industrial Considerations

For this codebase, behavioral diffs in the data layer are highest priority:

1. **Modbus register parsing**: Compare parsed register values. A single byte-order
   or type difference means the system reads wrong sensor values.

2. **EBCDIC decoding**: Compare decoded mainframe records. Field alignment must match
   exactly — an off-by-one in EBCDIC field boundaries corrupts all downstream data.

3. **Serial protocol responses**: Compare command/response pairs. Binary protocol
   frames must be byte-identical.

4. **CNC G-code parsing**: Compare parsed coordinates and commands. Positional
   string operations behave differently for bytes vs str in Py3.

---

## Integration with Migration State Tracker

After generating the behavioral diff report:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py \
    <state_file> note \
    --module "src/scada/modbus_reader.py" \
    --text "Behavioral diff: 0 unexpected diffs, 3 expected diffs (repr format)"
```

The Gate Checker (Skill X.3) reads `behavioral-diff-report.json` and checks the
`zero_behavioral_diffs` criterion for Phase 4→5 advancement.

---

## References

- **py2-py3-syntax-changes.md**: Syntax changes that cause expected repr diffs
- **py2-py3-semantic-changes.md**: Semantic changes that cause behavioral diffs
- **bytes-str-patterns.md**: Common bytes/str diffs to expect
- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution

---

## Success Criteria

- [ ] All test cases executed under both interpreters
- [ ] Every diff classified as expected or potential-bug
- [ ] Zero unclassified diffs in final report
- [ ] All potential bugs investigated and resolved (or waived)
- [ ] behavioral-diff-report.json produced for Gate Checker consumption
- [ ] SCADA/industrial data paths show zero unexpected diffs
- [ ] Encoding-related diffs traced to root cause
