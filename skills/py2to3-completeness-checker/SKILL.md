---
name: py2to3-completeness-checker
description: >
  Scans the entire codebase for remaining Python 2 artifacts, incomplete conversions,
  leftover compatibility shims, and unresolved migration debris. Use this skill whenever
  you need to verify that nothing was missed during conversion, prove that the codebase is
  fully migrated, identify cleanup work remaining before cutover, or generate evidence for
  the Phase 4→5 gate check. Also trigger when someone says "is the migration complete,"
  "are there any Py2 leftovers," "check migration completeness," "find remaining Py2
  artifacts," or "run the completeness check." This skill is the final inventory before
  declaring the migration done — it catches what the converter missed, what the semantic
  fixers skipped, and what the developer forgot.
---

# Skill 4.4: Migration Completeness Checker

## Why Completeness Checking Matters

Automated converters and semantic fixers don't catch everything. After Phase 2 and Phase 3
have processed the codebase, remnants remain:

- A `six.moves` import that `lib2to3` didn't touch because it's inside a try/except
- A `# -*- coding: ascii -*-` declaration that should now be `utf-8` or removed entirely
- A `sys.version_info[0] >= 3` guard that was added for dual-interpreter testing and
  should be collapsed now that Py2 support is dropped
- A `unicode_literals` future import that served its purpose and is now noise
- A `# TODO(migration): revisit this after Py3` comment that was never revisited
- A `from __future__ import print_function` that every file still has
- A `# type: ignore[override]` comment that was added to suppress a mypy error that
  may now be resolved

The completeness checker systematically finds every one of these and produces an ordered
cleanup task list. Until this tool reports 100%, the migration is not done.

---

## Inputs

| Input | From | Notes |
|-------|------|-------|
| **codebase_path** | User | Root directory of the Python codebase |
| **target_version** | User | Target Python 3.x version (e.g., 3.9, 3.12) |
| **--state-file** | User | Path to migration-state.json |
| **--output** | User | Output directory for reports |
| **--modules** | User | Specific modules to check (default: all `.py` files) |
| **--migration-state** | Skill X.1 | Module-level phase tracking for context |
| **--lint-baseline** | Skill 0.5 | Original lint baseline for comparison |
| **--bytes-str-report** | Skill 3.1 | Boundary fix report for cross-reference |
| **--strict** | User | Treat warnings as failures (for gate check) |

---

## Outputs

| Output | Purpose |
|--------|---------|
| **completeness-report.json** | Machine-readable: every remaining artifact found |
| **completeness-report.md** | Human-readable summary (from generate_completeness_report.py) |
| **cleanup-tasks.json** | Ordered list of remaining cleanup work with priority and effort |

---

## Workflow

### 1. Scan for Remaining Py2 Artifacts

```bash
python3 scripts/check_completeness.py <codebase_path> \
    --target-version 3.12 \
    --output ./completeness-output/
```

The script scans every `.py` file in the codebase and checks for 10 categories of
remaining migration artifacts.

### 2. Check Categories

The checker runs 10 categories of checks, each producing findings with severity levels:

#### Category 1: Remaining Py2 Syntax

Detects any Python 2 syntax that should have been converted by Skill 2.2:

| Pattern | Example | Severity |
|---------|---------|----------|
| Print statement | `print "hello"` | ERROR |
| Exec statement | `exec code` | ERROR |
| `<>` comparison | `if a <> b:` | ERROR |
| Backtick repr | `` `x` `` | ERROR |
| `has_key()` method | `d.has_key('x')` | ERROR |
| `raise` string exception | `raise "Error"` | ERROR |
| Old-style `except` | `except Exception, e:` | ERROR |
| `xrange()` call | `xrange(10)` | ERROR |
| `raw_input()` call | `raw_input("prompt")` | ERROR |
| `apply()` call | `apply(func, args)` | ERROR |

#### Category 2: Compatibility Library Usage

Detects `six`, `future`, and `past` imports that are no longer needed:

| Pattern | Example | Severity |
|---------|---------|----------|
| `import six` | Any six usage | WARNING |
| `from six import ...` | `from six import text_type` | WARNING |
| `from six.moves import ...` | `from six.moves import range` | WARNING |
| `import future` | Any future library (not `__future__`) | WARNING |
| `from builtins import ...` | `from builtins import str` | WARNING |
| `from past.builtins import ...` | Backward compatibility shims | WARNING |

#### Category 3: Unnecessary `__future__` Imports

Detects `__future__` imports that are default behavior in all supported Py3 versions:

| Import | Needed in Py3? | Severity |
|--------|---------------|----------|
| `print_function` | No (default since 3.0) | INFO |
| `division` | No (default since 3.0) | INFO |
| `absolute_import` | No (default since 3.0) | INFO |
| `unicode_literals` | No (default since 3.0) | INFO |
| `generators` | No (default since 2.3) | INFO |
| `nested_scopes` | No (default since 2.2) | INFO |
| `with_statement` | No (default since 2.6) | INFO |
| `annotations` | Still useful in 3.9-3.13 | OK |

#### Category 4: Version Guard Patterns

Detects `sys.version_info` checks and `PY2`/`PY3` constants:

| Pattern | Example | Severity |
|---------|---------|----------|
| `sys.version_info` comparison | `if sys.version_info[0] >= 3:` | WARNING |
| `sys.version` string check | `if sys.version.startswith('3'):` | WARNING |
| `PY2`/`PY3` constant | `if six.PY2:` | WARNING |
| `platform.python_version()` | Version-dependent branching | INFO |

#### Category 5: Migration TODO/FIXME Comments

Detects comments that were added during migration:

| Pattern | Example | Severity |
|---------|---------|----------|
| `# TODO(migration)` | Migration-tagged TODO | WARNING |
| `# FIXME(py3)` | Py3-tagged FIXME | WARNING |
| `# TODO: py2` / `# TODO: python 2` | Migration-related TODO | WARNING |
| `# HACK: py2` / `# HACK: python 3` | Migration workarounds | WARNING |
| `# XXX: encoding` / `# XXX: bytes` | Encoding-related flags | INFO |

#### Category 6: Type Ignore Comments

Detects `# type: ignore` comments that may be resolvable:

| Pattern | Example | Severity |
|---------|---------|----------|
| `# type: ignore` (bare) | No specific error code | WARNING |
| `# type: ignore[override]` | May be resolved by now | INFO |
| `# type: ignore[assignment]` | May indicate type confusion | INFO |
| `# type: ignore[attr-defined]` | May indicate missing stub | INFO |

#### Category 7: Encoding Declarations

Detects encoding declarations that may need updating:

| Pattern | Example | Severity |
|---------|---------|----------|
| `# -*- coding: ascii -*-` | Should be `utf-8` or removed | WARNING |
| `# -*- coding: latin-1 -*-` | May need update to `utf-8` | INFO |
| `# coding: utf-8` | Redundant in Py3 (default) but harmless | INFO |
| No encoding declaration | OK in Py3 (default is UTF-8) | OK |

#### Category 8: Dual-Compatibility Patterns

Detects code patterns written for Py2+Py3 compatibility that can be simplified:

| Pattern | Example | Severity |
|---------|---------|----------|
| `str`/`bytes` type checks | `isinstance(x, (str, bytes))` | INFO |
| `try: unicode except NameError` | Py2/Py3 unicode detection | WARNING |
| `try: from StringIO` | `try: from StringIO import ...` | WARNING |
| `try: from io import StringIO` | If `except` falls back to Py2 | WARNING |
| Conditional `encode`/`decode` | `s.encode('utf-8') if PY2 else s` | WARNING |
| `getattr(str, 'decode', None)` | Runtime Py2/Py3 detection | WARNING |

#### Category 9: Deprecated Standard Library Usage

Checks for stdlib modules that are removed in the target Python version:

Uses `stdlib-removals-by-version.md` to check for imports of modules removed in the
target version (e.g., `distutils` removed in 3.12, `aifc`/`audioop`/`cgi` in 3.13).

#### Category 10: Lint and Type Check Compliance

Runs linters and type checkers at Phase 4 strictness:

| Tool | Check | Severity |
|------|-------|----------|
| `pylint --py3k` | Zero Py2 compatibility warnings | ERROR if any |
| `pyupgrade --py3X-plus` | Zero remaining upgrades possible | WARNING |
| `mypy --strict` | Type errors in converted modules | INFO |

---

## Integration with Migration State Tracker

After generating the completeness report:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py \
    <state_file> note \
    --module "src/scada/modbus_reader.py" \
    --text "Completeness check: 2 remaining artifacts (1 six import, 1 future import)"
```

The Gate Checker (Skill X.3) reads `completeness-report.json` and checks the
`migration_complete` criterion for Phase 4→5 advancement:

```json
{
  "criterion": "migration_complete",
  "threshold": "100% completeness (zero ERROR-severity findings)",
  "evidence_file": "completeness-report.json",
  "check": "summary.error_count == 0"
}
```

---

## Cleanup Task Prioritization

The `cleanup-tasks.json` output orders remaining work by:

1. **Priority** (how blocking is this for Phase 4→5):
   - `critical` — ERROR severity findings that block the gate
   - `high` — WARNING severity findings that should be resolved
   - `low` — INFO severity findings that are cleanup nice-to-haves

2. **Effort** (estimated lines to change):
   - `trivial` — single-line change (remove an import, delete a comment)
   - `small` — 2-10 lines (replace a compatibility pattern)
   - `medium` — 10-50 lines (refactor a version-guarded block)
   - `large` — 50+ lines (rewrite a compatibility shim)

3. **Automation** (can this be auto-fixed?):
   - `auto` — safe to auto-fix (remove `__future__` import, delete comment)
   - `semi-auto` — likely auto-fixable but needs review (remove `six` call)
   - `manual` — needs human judgment (collapse version guard, replace shim)

---

## References

- **stdlib-removals-by-version.md**: Modules removed in each Py3 minor version
- **py2-py3-syntax-changes.md**: All Py2 syntax that should be gone
- **py2-py3-semantic-changes.md**: Semantic patterns that may remain as compatibility code

---

## Success Criteria

- [ ] Every `.py` file in the codebase scanned
- [ ] All 10 check categories executed
- [ ] Zero ERROR-severity findings (hard gate requirement)
- [ ] All WARNING-severity findings triaged (fixed or documented as acceptable)
- [ ] completeness-report.json produced for Gate Checker consumption
- [ ] cleanup-tasks.json produced with prioritized remediation list
- [ ] No remaining `six` or `future` library usage (unless documented exception)
- [ ] No remaining `__future__` imports (except `annotations` if target < 3.14)
- [ ] No remaining `sys.version_info` guards for Py2 vs Py3
- [ ] Lint baseline shows improvement over Phase 0 baseline
