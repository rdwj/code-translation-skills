---
name: py2to3-performance-benchmarker
description: >
  Compares performance between Python 2 and Python 3 execution to catch regressions
  introduced by the migration. Runs benchmarks on critical code paths under both
  interpreters, measures wall-clock time, CPU time, and memory usage, and applies
  statistical analysis to distinguish real regressions from noise. Use this skill
  whenever you need to detect performance regressions after migration, compare Py2 vs
  Py3 execution speed, identify Py3-specific optimization opportunities, or generate
  evidence for the Phase 4→5 gate check. Also trigger when someone says "benchmark
  the migration," "are there performance regressions," "compare Py2 vs Py3 speed,"
  "is the migrated code slower," or "run the performance check." Note that Py3.11+
  has significant performance improvements over earlier Py3 versions, so target
  version affects expected results.
---

# Skill 4.2: Performance Benchmarker

## Why Performance Benchmarking Matters

Migration introduces performance changes in both directions:

- **Regressions**: `str` operations are slower than `bytes` operations for data that
  was incorrectly treated as text. Adding explicit `.encode()`/`.decode()` calls adds
  overhead. `dict.keys()`, `dict.values()`, `dict.items()` returning views instead
  of lists changes memory characteristics.

- **Improvements**: Python 3.11+ has 10-60% performance improvements over Py2. F-strings
  are faster than `%` formatting or `.format()`. The `int` type is unified (no `long`),
  eliminating type promotion overhead. `range()` is lazy (saves memory).

- **Neutral changes that look like regressions**: Dict iteration order is now guaranteed
  (insertion order), which can change the order of operations and make timing comparisons
  confusing. `sorted()` may take different paths due to changed comparison behavior.

The benchmarker runs the same workloads under both interpreters, applies statistical
analysis (multiple runs, confidence intervals, outlier detection), and flags only
statistically significant regressions above a configurable threshold.

---

## Inputs

| Input | From | Notes |
|-------|------|-------|
| **codebase_path** | User | Root directory of the Python codebase |
| **py2_interpreter** | User | Path to Python 2 interpreter (e.g., `python2.7`) |
| **py3_interpreter** | User | Path to Python 3 interpreter (e.g., `python3.12`) |
| **target_version** | User | Target Python 3.x version (e.g., 3.9, 3.12) |
| **--state-file** | User | Path to migration-state.json |
| **--output** | User | Output directory for reports |
| **--benchmark-suite** | User | Path to benchmark scripts or test directory |
| **--modules** | User | Specific modules to benchmark (default: all) |
| **--iterations** | User | Number of runs per benchmark (default: 5) |
| **--warmup** | User | Number of warmup runs (default: 2) |
| **--threshold** | User | Regression threshold percentage (default: 10.0) |
| **--timeout** | User | Per-benchmark timeout in seconds (default: 300) |

---

## Outputs

| Output | Purpose |
|--------|---------|
| **performance-report.json** | Machine-readable: benchmark results with statistics |
| **performance-report.md** | Human-readable summary (from generate_perf_report.py) |
| **optimization-opportunities.json** | Py3-specific speedups that could be applied |

---

## Workflow

### 1. Discover Benchmarks

```bash
python3 scripts/benchmark.py <codebase_path> \
    --py2 /usr/bin/python2.7 \
    --py3 /usr/bin/python3.12 \
    --target-version 3.12 \
    --iterations 5 \
    --threshold 10.0 \
    --output ./performance-output/
```

The script discovers benchmarks by:
1. Looking for files matching `bench_*.py` or `*_benchmark.py`
2. Looking for test files with benchmark markers (`@pytest.mark.benchmark`)
3. Using the `--benchmark-suite` path if provided
4. Auto-generating simple timing benchmarks for critical-path modules

### 2. Execute Benchmarks

For each benchmark:

1. **Warmup**: Run `--warmup` iterations to fill caches and stabilize JIT (if any)
2. **Measure**: Run `--iterations` timed iterations, capturing:
   - Wall-clock time (time.perf_counter)
   - CPU time (time.process_time)
   - Peak memory usage (resource.getrusage or tracemalloc)
3. **Record**: Save all raw measurements for statistical analysis

### 3. Statistical Analysis

For each benchmark, compute:

| Metric | Method |
|--------|--------|
| Mean | Arithmetic mean of all iterations |
| Median | Middle value (robust to outliers) |
| Std dev | Standard deviation across iterations |
| Min/Max | Range of measurements |
| IQR | Interquartile range for outlier detection |
| CV | Coefficient of variation (std/mean) |
| CI 95% | 95% confidence interval using t-distribution |

Outlier detection: Values outside `median ± 1.5 × IQR` are flagged.

### 4. Compare Py2 vs Py3

For each benchmark, compare:

| Comparison | Classification |
|------------|----------------|
| Py3 within threshold of Py2 | **No regression** |
| Py3 > threshold% slower | **Regression** (needs investigation) |
| Py3 > threshold% faster | **Improvement** (Py3 optimization) |
| Py3 CI overlaps Py2 CI | **Inconclusive** (increase iterations) |
| Either interpreter fails | **Error** (not comparable) |

### 5. Identify Optimization Opportunities

Scan the codebase for patterns where Py3-specific features would improve performance:

| Pattern | Py2 Way | Py3 Optimization |
|---------|---------|-----------------|
| String formatting | `'%s %s' % (a, b)` | `f'{a} {b}'` (faster) |
| Dict comprehension | `dict([(k,v) for ...])` | `{k: v for ...}` |
| Chained comparison | `a > 0 and a < 10` | `0 < a < 10` |
| Unpacking | `a, b = t[0], t[1]` | `a, b = t` |
| `lru_cache` | Custom memoization | `@functools.lru_cache` |
| `dataclasses` (3.7+) | Manual `__init__` | `@dataclass` (less overhead) |
| `walrus` (3.8+) | `x = f(); if x:` | `if (x := f()):` |

### 6. Generate Reports

```bash
python3 scripts/generate_perf_report.py \
    --perf-report performance-output/performance-report.json \
    --output performance-output/performance-report.md
```

---

## Version-Specific Performance Notes

### Python 3.9-3.10
- Generally 10-30% slower than Py2 for CPU-bound work
- Better memory efficiency for large datasets (views, lazy iterators)
- Str operations slower than Py2 bytes for ASCII-only data

### Python 3.11
- Major performance improvements (10-60% faster than 3.10)
- Specialized adaptive interpreter
- Often matches or exceeds Py2 performance
- Best target for migration if performance is critical

### Python 3.12-3.13
- Further incremental improvements
- Per-interpreter GIL (3.12) and free-threaded mode (3.13) can help
  concurrent workloads
- JIT compiler (3.13 experimental) for further optimization

---

## SCADA/Industrial Performance Considerations

1. **Modbus polling loops**: These are I/O-bound and unlikely to show
   Py2→Py3 performance differences. Focus on data parsing throughput.

2. **EBCDIC decoding throughput**: Decoding large mainframe record batches
   may be measurably slower if `.decode('cp500')` is called per-field
   instead of per-record.

3. **Serial port communication**: Timing-critical code (Modbus RTU framing)
   must not have added latency from encoding/decoding operations.

4. **Sensor data aggregation**: Large-scale numeric data processing may
   benefit from Py3's improved `int` performance and `statistics` module.

---

## Integration with Gate Checker

The Gate Checker reads `performance-report.json` and checks the
`performance_acceptable` criterion for Phase 4→5 advancement:

```json
{
  "criterion": "performance_acceptable",
  "threshold": "no regression > 10% on critical paths",
  "evidence_file": "performance-report.json",
  "check": "summary.regressions_above_threshold == 0"
}
```

---

## References

- **py2-py3-semantic-changes.md**: Semantic changes that affect performance
- **bytes-str-patterns.md**: Encoding operations that may add overhead

---
- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution

## Success Criteria

- [ ] All benchmark suites executed under both interpreters
- [ ] Statistical analysis applied (min 5 iterations per benchmark)
- [ ] No regressions above threshold on critical-path benchmarks
- [ ] All regressions investigated and either fixed or documented
- [ ] Optimization opportunities identified for Py3-specific features
- [ ] performance-report.json produced for Gate Checker consumption
- [ ] SCADA/industrial data paths benchmarked for latency
- [ ] Memory usage compared (watch for increased memory from explicit encoding ops)
