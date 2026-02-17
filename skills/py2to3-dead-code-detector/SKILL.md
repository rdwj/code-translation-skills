---
name: py2to3-dead-code-detector
description: >
  Identifies dead code that was only reachable under Python 2, dead Py2 compatibility functions,
  unused imports, unreachable code, and Py2 compatibility modules. Detects version-guarded blocks
  that are always False in Py3, cross-references functions with usage, and flags dead test code.
  Use this skill when you need to clean up legacy compatibility code, understand what can be safely
  removed post-migration, verify migration completeness, or audit for Py2 remnants. Also trigger
  when someone says "find dead code," "remove Py2 compat," "what can be deleted," "cleanup code,"
  or "find unused imports." This skill now supports tree-sitter as a fallback for files that fail ast.parse() and can detect dead code in non-Python files when the universal-code-graph skill has been run.
---

# Skill 5.3: Dead Code Detector

## Why Dead Code Cleanup Matters for Py2→Py3 Completion

Dead code cleanup is essential for migration completion because:

- **Version-guarded code is guaranteed dead in Py3**: Code under `if sys.version_info[0] < 3:` or
  `if PY2:` can never execute in Python 3. It's safe to remove, but only after confirming no dynamic
  execution paths depend on it.

- **Py2 compatibility functions have no purpose**: Functions like `ensure_bytes()`, `to_unicode()`,
  `to_native_str()` were workarounds for Py2/Py3 string differences. These are dead weight in Py3.

- **Dead code increases maintenance burden**: Every unused function, unused import, and compatibility
  module must be maintained, tested, and documented. Removal reduces cognitive load and test burden.

- **Unused imports hide dependency issues**: An unused import of `six` or `future` can mask the fact
  that you're still depending on a Py2 compatibility package that could be removed entirely.

- **Dead test code obscures coverage**: Tests written for Py2-specific behavior won't run in Py3.
  They inflate test counts but don't provide coverage. Removing them clarifies actual coverage.

- **Confidence matters**: High-confidence dead code (e.g., inside version guards or only called from
  dead blocks) can be auto-removed. Medium-confidence code (no references found) may be called
  dynamically. Low-confidence (heuristic matches) needs manual review.

This skill audits all categories and provides confidence-based recommendations for removal.

---

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| **codebase_path** | User | Root directory of Python 3 migrated codebase |
| **--target-version** | User | Python 3.x target (3.9, 3.11, 3.12, 3.13) for context |
| **--output** | User | Output directory for reports (default: current dir) |
| **--coverage-data** | User | Optional `.coverage` file for cross-reference with coverage |
| **--modules** | User | Specific modules to scan (default: all Python files) |

---

## Outputs

All outputs go into the `--output` directory:

| File | Format | Purpose |
|------|--------|---------|
| `dead-code-report.json` | JSON | Complete inventory of dead code with confidence levels |
| `safe-to-remove.json` | JSON | High-confidence removals only (for automated cleanup) |
| `dead-code-report.md` | Markdown | Human-readable summary by category with removal guidance |

---

## Scope and Chunking

Dead code detection requires cross-module call graph analysis, which means it benefits from seeing the full codebase. However, the output can be presented incrementally.

**Analysis**: Run on the full codebase — the call graph needs complete visibility to accurately determine reachability. This is a one-time scan, not an iterative process.

**Output presentation**: Present findings by confidence tier:
1. **Definite dead code** (confidence > 90%): Py2-only branches behind `sys.version_info` checks, unused `compat.py` re-exports — safe to remove
2. **Likely dead code** (confidence 60–90%): Functions with no detected callers but possible dynamic invocation — review needed
3. **Uncertain** (confidence < 60%): Flagged for human review, may be dynamically loaded

Present only tiers 1 and 2 in the conversation. Save all findings to `dead-code-report.json` on disk.

**For very large codebases (1000+ files)**: The call graph construction may be slow. Direct the agent to build the graph once, save it, and then query it for dead code patterns. The graph is reusable across multiple analysis passes.

**Key principle**: Cast a wide net during analysis (full codebase), narrow the focus during presentation (high-confidence findings only).

---

## Workflow

### Step 1: Discover All Code Definitions

Run the main detection script:

```bash
python3 scripts/detect_dead_code.py <codebase_path> \
    --target-version 3.12 \
    --output ./dead-code-output/
```

This scans for:
- All function definitions (AST-based)
- All class definitions (AST-based)
- All import statements
- All top-level variables/constants
- Cross-build usage graph (imports, function calls, attribute access)

### Step 2: Identify Version-Guarded Dead Code

For each conditional block:

1. Check if the condition is a version guard:
   - `if sys.version_info[0] < 3:`
   - `if sys.version_info[0] == 2:`
   - `if PY2:` (from `six` or `future`)
   - `if six.PY2:`
   - `if PY3:` (inverse — else block is dead)
   - `if not PY3:`
   - Nested versions: `if sys.version_info < (3,):`

2. If the condition is always False in Py3, mark the block as dead code with HIGH confidence.

3. Track any code inside version-guarded blocks (entire subtrees are dead).

### Step 3: Identify Py2 Compatibility Functions

Scan all function/class definitions for compatibility patterns:

**Function name patterns** (heuristic):
- `*_compat` (e.g., `decode_compat`)
- `ensure_*` (e.g., `ensure_bytes`, `ensure_str`)
- `to_text`, `to_bytes`, `to_native_str`, `to_unicode`
- `compat_*` (e.g., `compat_iteritems`)
- `py2_*`, `py3_*` (explicit version names)
- `string_types`, `text_type`, `binary_type` (type aliases)
- `quote_plus`, `quote`, `unquote_plus`, `unquote` (urllib compat)

For each matching function:
- Check if it's called only from version-guarded dead code
- If yes → HIGH confidence (dead)
- Check if it's called at all in live code
- If not → MEDIUM confidence (unused, but possibly dynamic)

### Step 4: Track Usage Across Files

Build a call graph:
- For each function/class definition, find all references (calls, imports, attribute access)
- Handle dynamic patterns:
  - `getattr(obj, "func_name")`
  - `eval()`, `exec()`, `compile()` (flag as unknown)
  - String references in `__all__`
- Track cross-module imports and re-exports (especially in `__init__.py`)

### Step 5: Identify Unused Imports

For each import statement:
- Track what was imported
- Find all uses in the module
- Exclude:
  - Re-exports in `__all__` (for __init__.py)
  - Imports used in docstrings or comments
  - Imports used in type hints
  - Magic imports like `TYPE_CHECKING`

If no uses found → MEDIUM confidence (could be imported for side effects or public API)

### Step 6: Detect Unreachable Code

Check for code after unconditional `return`, `raise`, `continue`, `break`, `exit()`:
- Track control flow within functions
- Mark code after terminal statements as dead
- HIGH confidence (guaranteed unreachable)

### Step 7: Identify Dead Test Code

Scan test files (files matching `*_test.py`, `test_*.py`, `**/tests/**`):
- Test functions decorated with `@skipIf(PY3)`, `@skipIf(not PY2)`, etc. → HIGH confidence
- Test classes inheriting from skipped base classes → MEDIUM confidence
- Test functions testing Py2-specific modules (now removed) → HIGH confidence
- Test functions for removed compat functions → HIGH confidence

### Step 8: Assess Confidence Levels

For each finding:

**HIGH Confidence**:
- Inside `if PY2:` or `if sys.version_info[0] < 3:` blocks
- Functions only called from HIGH-confidence dead code
- Test code explicitly decorated with `@skipIf(PY3)` or similar
- Code after unconditional `return`/`raise`
- Imports only used in dead code blocks

**MEDIUM Confidence**:
- No references found in codebase (could be called dynamically)
- Functions matching compat names but with some references
- Imports used only in docstrings or comments
- Dead test code not explicitly decorated

**LOW Confidence**:
- Function names suggest Py2 compat but used in live code
- Heuristic matches without strong signals
- Imports of known compat libraries (six, future) without reference analysis

### Step 9: Generate Reports

Main report includes:
- Executive summary (total dead code by category)
- Confidence distribution
- Per-file dead code listing
- Cross-module dependency analysis

Safe-to-remove report includes:
- HIGH-confidence findings only
- Safe removal order (dependencies first)
- Line numbers and exact code snippets

### Tree-sitter Fallback

When tree-sitter is available and a Python file fails `ast.parse()` (Python 2 syntax),
the dead code detector uses tree-sitter queries to extract function and class definitions
and their call relationships. This enables dead code detection in files that would
otherwise be skipped entirely.

The tree-sitter path uses the same query files as the universal-code-graph skill:
- `python_definitions.scm` — extracts function and class definitions
- `python_calls.scm` — extracts call relationships

Cross-referencing definitions against calls identifies functions and classes that are
defined but never called from anywhere in the analyzed scope.

### Multi-Language Dead Code Detection

When the universal-code-graph skill has been run and a `call-graph.json` is available,
the dead code detector can identify unreachable code in any supported language — not
just Python. The analysis uses graph-based reachability:

1. Start from known entry points (main functions, exported APIs, test files)
2. Walk the call graph to find all reachable functions
3. Any function defined but not reachable from any entry point is flagged as dead

This works identically regardless of language because the call graph normalizes all
languages into the same format. A Java method that nothing calls is dead code just
like a Python function that nothing calls.

**Additional inputs (optional):**
- `call-graph.json` from universal-code-graph — enables graph-based reachability
- `--entry-points` — glob patterns for known entry points (e.g., `**/main.py`, `**/app.java`)

---

## Detection Categories

### 1. Version-Guarded Dead Code

Patterns:
- `if sys.version_info[0] < 3:` — entire block is dead in Py3
- `if sys.version_info >= (3, 0):` — else block is dead
- `if PY2:` (from `six` import) — block is dead in Py3
- `if six.PY2:` — block is dead
- `if PY3:` — else block is dead
- Nested: `if sys.version_info < (3,):` and `if sys.version_info[0] == 2:`

Handling:
- Detect condition syntax via AST
- Evaluate condition in Py3 context
- Mark entire if/else blocks as dead/live
- Track nested conditionals

### 2. Py2 Compatibility Functions

Patterns:
- Function names: `ensure_bytes`, `to_unicode`, `compat_iteritems`, `py2_iteritems`
- Class names: `string_types`, `text_type` (often type aliases)
- Modules: `compat.py`, `py2compat.py`, `six_compat.py`

Analysis:
- Cross-reference with call graph
- If called only from dead code → HIGH
- If not called at all → MEDIUM (could be API, dynamic call)
- If name matches pattern but used in live code → flag for review

### 3. Unused Imports

Patterns:
- `import six` but never used
- `from future import ...` where future is not referenced
- `import compat` but `compat.*` never called
- `from functools import lru_cache` but name never referenced

Handling:
- Build import table per file
- Track all name references
- Exclude: `__all__` exports, type hints, TYPE_CHECKING blocks
- Report unused with MEDIUM confidence (could be public API)

### 4. Unreachable Code

Patterns:
- Code after unconditional `return`
- Code after unconditional `raise`
- Code after `break`/`continue` (in loops)
- Code after `sys.exit()`

Analysis:
- AST-based control flow tracking
- Mark unreachable nodes as dead
- HIGH confidence

### 5. Dead Py2 Compat Modules

Patterns:
- Module files like `compat.py`, `py2compat.py`, `six_compat.py`
- All exports are dead or unused
- Module imported only from dead code

Analysis:
- If all module functions/classes are dead → mark module as dead
- If module has no live callers → MEDIUM
- Entire module removal is HIGH confidence if all exports are dead

### 6. Unused Classes and Functions

Patterns:
- Function defined but never called
- Class defined but never instantiated
- Method defined but never called (static analysis limit)

Analysis:
- Build call graph from AST + attribute access
- If definition has no references → MEDIUM (could be dynamic)
- If definition only in dead code → HIGH
- Exclude: `__init__`, `__repr__`, other magic methods, classes inheriting from ABC

### 7. Dead Test Code

Patterns:
- `@skipIf(PY3)` decorated test functions
- `@skipIf(PY2)` but running in Py2 context (shouldn't happen post-migration)
- Test classes inheriting from skipped base classes
- Test functions testing removed Py2 modules
- Test fixtures for Py2-specific behavior

Analysis:
- Scan test files
- Detect skip decorators and conditions
- Cross-reference with removed modules
- HIGH confidence for explicitly decorated tests

---

## Success Criteria

The skill has succeeded when:

1. All `if sys.version_info`, `if PY2`, `if PY3`, `if six.PY2` blocks are identified
2. All version-guarded code blocks are marked as dead or live
3. All Py2 compatibility functions (by name and usage) are discovered
4. All imports are tracked and unused imports flagged
5. Cross-file usage graph is built (accounting for imports and attribute access)
6. All unreachable code (after return/raise) is detected
7. All dead test code is flagged
8. Confidence levels are assigned consistently
9. Safe-to-remove.json contains only HIGH-confidence findings
10. Removal order respects dependencies (dependent code removed before dependencies)
11. Report includes line numbers, code snippets, and remediation steps

---

## Dependencies (Optional)

For enhanced dead code detection:
- tree-sitter + tree-sitter-language-pack — enables detection in files that fail ast
- universal-code-graph skill outputs (call-graph.json) — enables multi-language detection
- Neither is required; the skill falls back to ast-only analysis when unavailable

---

## References

- `references/py2-compat-patterns.md` — Common Py2 compatibility patterns to detect
- `references/dead-code-removal-strategy.md` — Safe removal order and dependency analysis
- `references/version-guard-catalog.md` — All known version guard patterns
- [Python AST documentation](https://docs.python.org/3/library/ast.html)
- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
