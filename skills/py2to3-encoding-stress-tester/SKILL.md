---
name: py2to3-encoding-stress-tester
description: >
  Adversarial encoding stress tester for Python 2→3 migration verification. Exercises
  every data ingestion path with deliberately difficult encoding inputs: BOM markers,
  surrogate pairs, null bytes, mixed encodings, EBCDIC variant confusion, binary data
  that looks like valid UTF-8, and multi-byte character splits. Use this skill whenever
  you need to prove encoding correctness after migration, flush out latent encoding bugs,
  stress-test SCADA/EBCDIC/serial data paths, or generate evidence for the Phase 4→5
  gate check. Also trigger when someone says "stress test encodings," "test encoding edge
  cases," "are there latent encoding bugs," or "run encoding adversarial tests." This is
  the highest-value verification skill for codebases with industrial/mainframe data sources.
---

# Skill 4.3: Encoding Stress Tester

## Why This Skill Is Critical

Normal tests use normal data. But encoding bugs only appear with abnormal data:
a BOM at the start of a config file, a null byte in a Modbus frame, an EBCDIC record
decoded with the wrong codepage variant, a Shift-JIS comment in CNC G-code. These
are the cases that cause silent data corruption in production.

In a Py2 codebase, encoding errors are hidden because `str` is bytes. Everything
"works" because bytes can be compared, concatenated, and sliced without decoding.
After migration to Py3, every implicit operation becomes explicit — and every assumption
about encoding becomes a potential crash or data corruption.

The encoding stress tester systematically exercises every data path with adversarial
inputs from the reference documents:
- `encoding-test-vectors.md` — canonical test data for every encoding
- `encoding-edge-cases.md` — BOM, surrogates, nulls, mixed encodings, platform quirks
- `adversarial-encoding-inputs.md` — inputs designed to trigger specific failure modes
- `industrial-data-encodings.md` — SCADA, CNC, mainframe encoding conventions

---

## Inputs

| Input | From | Notes |
|-------|------|-------|
| **codebase_path** | User | Root directory of the Python codebase |
| **data_layer_report** | Skill 0.2 (Data Format Analyzer) | Identifies all data paths and their encoding expectations |
| **encoding_map** | Skill 0.2 | Every encoding operation in the codebase |
| **target_version** | User | Python 3.x target (e.g., 3.9, 3.12) |
| **--state-file** | User | Path to migration-state.json |
| **--output** | User | Output directory for reports |
| **--test-vectors** | User | Path to custom test vectors JSON (optional) |
| **--paths** | User | Specific data paths to test (default: all) |
| **--quick** | User | Run reduced test set for fast feedback |

---

## Outputs

| Output | Purpose |
|--------|---------|
| **encoding-stress-report.json** | Pass/fail for every data path × every encoding vector |
| **encoding-stress-report.md** | Human-readable summary (from generate_stress_report.py) |
| **encoding-failures.json** | Detailed failure info with reproduction steps |
| **generated-test-cases.py** | Test cases that can be added to permanent test suite |

---

## Scope and Chunking

The encoding stress tester applies 6 adversarial test categories to data paths. On a codebase with many data paths, this produces a combinatorial expansion of test results.

**Two-pass strategy** (recommended for codebases with 10+ data paths):

**Pass 1 — Critical paths only**: Run stress tests against modules flagged as critical or high risk by the Data Format Analyzer (Skill 0.2). This typically covers the I/O boundary modules and serialization layer. Fix any failures before proceeding.

**Pass 2 — Remaining paths**: After critical paths are clean, run against medium and low-risk modules. These are less likely to have encoding issues but should still be verified.

**Per-module scoping**: If a single module has many data paths (e.g., a mainframe parser with 20 record types), run the stress tester per record type or per encoding family rather than all at once.

**Expected output sizes**:
- 5 data paths × 6 categories: 30–60KB
- 20 data paths × 6 categories: 100–300KB
- 50+ data paths: Split into passes; results are additive

**Key principle**: Run critical paths first. If they pass, the remaining paths are lower risk and can be batched more aggressively. Report failures only — passing tests need not appear in the conversation.

---

## Workflow

### 1. Load Data Path Inventory

Read the data layer report to understand what data paths exist and what encodings each
path expects:

```bash
python3 scripts/stress_test.py <codebase_path> \
    --data-layer-report <data-layer-report.json> \
    --encoding-map <encoding-map.json> \
    --target-version 3.12 \
    --output ./encoding-stress-output/
```

### 2. Generate Adversarial Inputs

For each data path, generate inputs from all six adversarial categories:

1. **Correct encoding** — baseline: should always pass
2. **Wrong encoding** — e.g., EBCDIC data through UTF-8 decoder
3. **Malformed input** — truncated multi-byte, lone surrogates, overlong sequences
4. **Boundary conditions** — empty, single byte, max length, buffer-boundary splits
5. **Mixed encodings** — UTF-8 header + EBCDIC payload, BOM + content
6. **Binary-as-text** — sensor readings that happen to look like valid UTF-8

### 3. Execute Tests

For each (data_path, adversarial_input) pair:

1. Invoke the data path's entry function with the adversarial input
2. Capture: return value, stdout/stderr, exceptions raised, files written
3. Classify result:
   - **Pass**: Function handles input correctly (decodes, rejects, or processes)
   - **Fail — crash**: Function raises unhandled exception
   - **Fail — corruption**: Function produces wrong output without raising
   - **Fail — silent**: Function produces no output and no error

### 4. Generate Reports

The stress report shows a matrix: data paths × encoding categories, with pass/fail
for each cell.

---

## Test Categories

### Category 1: Valid Encoding Baseline

For each data path, send data in the encoding it's documented to handle:

| Data Path Type | Baseline Input |
|---------------|----------------|
| UTF-8 text file | Valid UTF-8 with accented characters |
| EBCDIC mainframe record | Valid CP500-encoded record |
| Modbus register block | Valid binary register data |
| Serial G-code | Valid ASCII G-code commands |
| JSON API response | Valid UTF-8 JSON |

If baseline tests fail, the migration has fundamental issues that must be fixed before
stress testing is meaningful.

### Category 2: Wrong Encoding

Send data encoded in a different encoding than the path expects:

| Data Path | Expected | Send Instead | Expected Behavior |
|-----------|----------|-------------|-------------------|
| UTF-8 reader | UTF-8 | CP500 (EBCDIC) | UnicodeDecodeError or garbled text |
| EBCDIC reader | CP500 | UTF-8 | Garbled text (EBCDIC bytes interpreted as wrong chars) |
| ASCII reader | ASCII | UTF-8 with emoji | UnicodeDecodeError on non-ASCII bytes |
| Latin-1 reader | Latin-1 | Shift-JIS | Garbled text (multi-byte interpreted as single-byte) |

The correct behavior is either: raise an error, or degrade gracefully with error handler.
Silent corruption is a test failure.

### Category 3: Malformed Input

Send deliberately broken encoding sequences:

| Input | Category | Expected Behavior |
|-------|----------|-------------------|
| Truncated UTF-8 (`C3` without continuation) | Incomplete multi-byte | Error or replacement char |
| Lone surrogate (`ED A0 80`) | Invalid UTF-8 | Error or replacement char |
| Overlong null (`C0 80`) | Security hazard | Error (must reject) |
| Invalid continuation (`80 81 82`) | Orphan continuation bytes | Error or replacement char |
| UTF-8 BOM in middle of data | Misplaced BOM | Should not affect parsing |
| Null byte in text stream | Embedded null | Should handle or reject cleanly |

### Category 4: Boundary Conditions

| Input | Condition | Why It Matters |
|-------|-----------|---------------|
| Empty bytes `b""` | Zero length | Many parsers don't handle empty input |
| Single byte (0x00-0xFF, all 256) | Minimal input | Catches assumptions about minimum length |
| Exactly buffer-size bytes | Buffer boundary | Catches off-by-one in read loops |
| Buffer-size + 1 multi-byte char | Split char | Catches incomplete character at buffer end |
| Maximum advertised length | Capacity limit | Catches buffer overflow in fixed-size handling |

### Category 5: Mixed Encoding

| Input | Structure | Risk |
|-------|-----------|------|
| UTF-8 BOM + CP500 payload | BOM signals UTF-8 but data is EBCDIC | Decoder follows BOM, garbles payload |
| ASCII header + Latin-1 body | Common in HTTP responses | Single-codec open fails on body |
| CP500 text + COMP-3 packed decimal | Mainframe record | Must switch parsing mode mid-record |
| G-code commands + Shift-JIS comments | CNC program file | ASCII for code, SJIS for comments |

### Category 6: Binary Data That Looks Like Text

| Input | Binary Meaning | Text Interpretation | Risk |
|-------|---------------|--------------------|----|
| `41 CC 00 00` | Float 25.5 | "AÌ\x00\x00" (Latin-1) | Sensor reading becomes garbled text |
| `41 42 43 44` | Float 12.063 | "ABCD" (ASCII) | Float becomes string "ABCD" |
| `30 30 30 30` | Uint32 808464432 | "0000" (ASCII) | Integer becomes string "0000" |
| `0D 0A 0D 0A` | Binary sequence | "\r\n\r\n" | Line-ending handling triggered |

---

## SCADA/Industrial Focus Areas

### Modbus Data Path Stress Test

1. **Register values containing every byte 0x00-0xFF**: Some values will look like
   valid text; verify they're parsed as integers, not decoded as strings.

2. **Float registers with NaN/Inf**: `7F C0 00 00` (NaN), `7F 80 00 00` (Inf) — verify
   struct.unpack handles these correctly.

3. **Exception responses**: Verify the error handler works with bytes, not str.

### EBCDIC Data Path Stress Test

1. **CP037 vs CP500 confusion**: Same bytes, different text. Feed data encoded in one
   variant to a decoder configured for the other. Verify the difference is detected.

2. **Packed decimal with invalid nibbles**: Nibble values A-F are invalid in decimal
   positions. Verify the parser rejects them.

3. **Record with wrong length**: Short record (fewer bytes than expected) or long record
   (extra bytes). Verify clean error, not crash.

### Serial Port Data Path Stress Test

1. **Frame with checksum byte that equals ETX (0x03)**: Framing parser must not confuse
   checksum with end-of-frame.

2. **Response with embedded null (0x00)**: Some serial libraries strip nulls; others
   include them. Verify consistent behavior.

3. **8-bit data through 7-bit serial**: If port is configured for 7 data bits, high bit
   is stripped. Verify parsing handles this.

---

## Integration with Gate Checker

The Gate Checker reads `encoding-stress-report.json` and checks the `encoding_stress_pass`
criterion for Phase 4→5 advancement:

```json
{
  "criterion": "encoding_stress_pass",
  "threshold": "100% pass rate",
  "evidence_file": "encoding-stress-report.json",
  "check": "summary.pass_rate == 100"
}
```

---

## References

- **encoding-test-vectors.md**: Baseline test data for all encodings
- **encoding-edge-cases.md**: BOM, surrogates, nulls, platform quirks
- **adversarial-encoding-inputs.md**: Targeted failure-mode inputs
- **industrial-data-encodings.md**: SCADA, CNC, mainframe encoding conventions
- **hypothesis-strategies.md**: Property-based test strategies for randomized inputs

---

## Model Tier

**Haiku.** Encoding stress testing generates test vectors from templates and executes them. Test infrastructure work, no semantic reasoning about the code under test. Always use Haiku.

## References

- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution

## Success Criteria

- [ ] Every data path tested with all 6 adversarial categories
- [ ] Zero failures on Category 1 (valid baseline) — if baseline fails, migration is broken
- [ ] All Category 2-6 failures are either handled gracefully or documented as known issues
- [ ] No silent data corruption (Category 6 binary-as-text) detected
- [ ] SCADA data paths pass with every byte value 0x00-0xFF in register data
- [ ] EBCDIC paths correctly identify codec variant (CP037 vs CP500 vs CP1047)
- [ ] encoding-stress-report.json produced for Gate Checker consumption
- [ ] Generated test cases added to permanent test suite
