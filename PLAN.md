# Python 2 → 3 Migration Skill Suite: Complete Plan

## Project Context

This skill suite supports the migration of a large, legacy Python 2 codebase to Python 3. The codebase has the following characteristics:

- **No original developers available** — this is an archaeology project
- **Data sources span**: IoT/SCADA devices (water monitors, industrial sensors), CNC/machine shop automation, mainframe systems, and a mix of structured, semi-structured, and unstructured data
- **Expected encoding challenges**: EBCDIC from mainframes, binary packed data from SCADA/Modbus protocols, fixed-width record formats, custom serialization, mixed encodings (ASCII, Latin-1, potentially Shift-JIS from Japanese equipment)
- **Unknown scope**: We don't know the full extent of what we're walking into

The skill suite is organized into six phases (0–5), three cross-cutting orchestration skills, and a target version compatibility layer. Each phase has explicit gate criteria that must be met before proceeding to the next phase, and rollback procedures for when things go wrong.

---

## Target Python Version Strategy

### Why This Matters

Migrating from Python 2 doesn't just mean "make it run on Python 3." Each minor version of Python 3 has introduced breaking changes that compound on top of the Py2→Py3 delta. The target version affects which standard library modules are available, which deprecation warnings become errors, and which new features can be leveraged.

### Version-Specific Breaking Changes

**Python 3.9** (minimum recommended target for new migrations)
- `typing.List`, `typing.Dict` etc. deprecated in favor of `list[str]`, `dict[str, int]`
- `zoneinfo` module added (replaces `pytz` for many use cases)

**Python 3.10**
- Structural pattern matching (`match`/`case`) available
- Parenthesized context managers
- Better error messages (helps during migration debugging)

**Python 3.11**
- `tomllib` added to stdlib
- Exception groups and `except*`
- 10-60% performance improvement over 3.10 (relevant for benchmarking phase)
- `asyncio.TaskGroup` added

**Python 3.12** (significant breaking changes)
- **`distutils` removed entirely** — any code using `from distutils import ...` breaks. Must migrate to `setuptools` or `sysconfig`
- **Deprecated modules removed**: `aifc`, `audioop`, `cgi`, `cgitb`, `chunk`, `crypt`, `imghdr`, `mailcap`, `msilib`, `nis`, `nntplib`, `ossaudiodev`, `pipes`, `sndhdr`, `spwd`, `sunau`, `telnetlib`, `uu`, `xdrlib`
- `wstr` removed from Unicode C API (affects C extensions)
- Per-interpreter GIL (experimental)
- f-string grammar relaxed (nested quotes, backslashes, comments)

**Python 3.13** (additional breaking changes)
- More deprecated modules removed: `cgi` and `cgitb` removal finalized
- Free-threaded mode (no GIL) available as experimental build option
- JIT compiler (experimental)
- `pathlib.Path` becomes abstract (affects subclassing)
- Further C API removals affecting native extensions

### Recommendation

Every skill that generates or transforms code must accept a `target_version` parameter (e.g., "3.11", "3.12", "3.13"). This parameter controls:

1. Which standard library replacements are suggested
2. Which deprecation warnings are flagged vs. which removals are errors
3. Whether `distutils` usage is flagged as a migration blocker
4. Which new idioms are suggested (e.g., pattern matching only if target >= 3.10)
5. Whether C API compatibility checks are version-appropriate

The Phase 0 Codebase Analyzer should produce a **version compatibility matrix** showing which target versions the codebase can feasibly reach and what the incremental cost is for each step up.

---

## Data Layer Considerations

### The Encoding Landscape

This codebase handles data from sources that span decades of computing history. The Python 2 `str` type's ambiguity (is it bytes? text? who knows?) probably "works" only because implicit encoding conversions happen silently. Under Python 3, these will become explicit errors. The data layer is likely the single highest-risk area of this migration.

#### Mainframe Data (EBCDIC)
- EBCDIC-encoded data uses completely different byte values than ASCII/UTF-8
- Python 2 code may use hardcoded byte values for field delimiters that are EBCDIC-specific
- The `codecs` module supports EBCDIC (`cp500`, `cp1047`, etc.) but the code may use manual byte manipulation instead
- **Skill requirement**: The Data Format Analyzer must detect EBCDIC patterns in both code and sample data files, and flag any hardcoded byte constants that assume a specific encoding

#### IoT/SCADA Protocols
- Modbus, OPC-UA, DNP3, and proprietary serial protocols use packed binary formats
- `struct.pack`/`struct.unpack` calls are likely throughout the codebase
- These are bytes-native and may actually be *easier* to migrate if they're already treating data as bytes
- **Risk**: Code that converts Modbus register values to Python strings — the str/bytes boundary is exactly here
- **Skill requirement**: The Serialization Boundary Detector must trace data flow from protocol parsing through to application logic and flag every point where binary protocol data becomes "text"

#### CNC/Machine Automation
- G-code and M-code are typically ASCII text, but with fixed-width fields and position-dependent parsing
- Custom parsers likely use string indexing (`line[0:3]`) which behaves differently for bytes vs str in Py3
- **Skill requirement**: Flag all positional string operations and determine whether the code is operating on bytes or text semantically

#### Mixed/Legacy Databases
- DBF files, flat files with fixed-width records, possibly ISAM databases
- `pickle` and `marshal` serialized objects — a pickled Py2 `str` deserializes as `bytes` in Py3
- **Skill requirement**: Every `pickle.load`, `marshal.load`, `shelve.open`, and similar call needs to be inventoried and tested with actual data

### Data Format Inventory

The Phase 0 analysis must produce a complete inventory of:

1. **Encodings detected in code** — any `encode()`, `decode()`, `codecs.open()`, encoding declarations, BOM markers
2. **Binary protocol usage** — `struct`, `ctypes`, `socket.recv`, serial port reads
3. **Serialization formats** — pickle, marshal, shelve, json, yaml, xml, custom
4. **File format handlers** — CSV readers, fixed-width parsers, binary file readers
5. **Database connectors** — which drivers, what encoding settings, how results are decoded
6. **Hardcoded byte constants** — magic bytes, delimiters, protocol headers

---

## Linting Strategy

### Pre-Migration Lint Rules

Linting serves three purposes in this project: discovery (finding Py2-isms), prevention (blocking regression), and enforcement (ensuring converted code stays clean).

**Discovery linters (Phase 0):**
- `pylint --py3k` — purpose-built Python 2→3 compatibility checker
- `pyupgrade --py3-plus` (dry run) — shows what automated rewrites are possible
- `flake8` with `flake8-2020` plugin — catches forward-incompatibility patterns
- Custom AST-based linting for project-specific patterns (EBCDIC handling, protocol parsing, etc.)

**Prevention linters (Phase 1+):**
- Custom rules that flag Py2 idioms introduced into already-converted modules
- Import-order enforcement (no relative imports in converted code)
- Encoding declaration requirements (`# -*- coding: utf-8 -*-` or explicit removal)

**Enforcement linters (Phase 3+):**
- `mypy` with strict mode on converted modules (type annotation enforcement)
- `bandit` for security regressions (Py2→Py3 can introduce new attack surfaces via encoding confusion)
- Custom rules that flag `six` or `future` usage in modules that have passed Phase 3

### Progressive Lint Configuration

Each module should have a lint configuration that corresponds to its migration phase. The Custom Lint Rule Generator (Phase 1 skill) produces configs that get stricter as modules progress:

- **Unconverted**: Discovery rules only (informational)
- **Phase 1 complete**: Future imports required, no new Py2 idioms
- **Phase 2 complete**: All Py2 syntax eliminated
- **Phase 3 complete**: All semantic issues resolved, type hints present
- **Phase 4 complete**: Full strict mode, mypy clean, bandit clean

---

## Phase Architecture

### Phase 0: Discovery & Assessment

**Purpose**: Understand what we have before touching anything. This phase produces the migration readiness report that determines scope, timeline, and risk.

**Gate criteria**: Stakeholder review and sign-off on the assessment report. Migration plan approved. Target Python version selected.

**Rollback**: No code changes made. Nothing to roll back.

#### Skill 0.1: Codebase Analyzer

**What it does**: Scans the entire codebase and produces a comprehensive migration readiness report including a dependency graph, Python 2-ism inventory categorized by type and risk, test coverage assessment, and version compatibility matrix.

**Key capabilities**:
- AST-based import analysis to build the full dependency graph
- Topological sort to determine migration order
- Cluster detection for tightly-coupled module groups
- Categorization of Py2-isms: syntax-only (low risk, automatable) vs. semantic (high risk, manual review needed)
- Test coverage measurement per module
- Version compatibility matrix (what breaks at 3.9, 3.10, 3.11, 3.12, 3.13)
- Lines-of-code and complexity metrics per module
- `pylint --py3k` integration for automated issue detection

**Inputs**: Path to codebase root, target Python version(s) to evaluate

**Outputs**: 
- `migration-report.json` — machine-readable full analysis
- `migration-report.md` — human-readable summary with visualizations
- `dependency-graph.json` — importable graph structure
- `migration-order.json` — topologically sorted conversion order
- `version-matrix.md` — compatibility assessment per target version

**References needed**: 
- `references/py2-py3-syntax-changes.md` — complete catalog of syntax differences
- `references/py2-py3-semantic-changes.md` — complete catalog of semantic differences
- `references/stdlib-removals-by-version.md` — what's removed in each Py3 minor version

#### Skill 0.2: Data Format Analyzer

**What it does**: Specialized deep-dive into the data layer. Identifies all data ingestion points, encoding patterns, serialization formats, binary protocol handlers, and database connections. Produces a data flow map showing where bytes become text and vice versa.

**Why this is a separate skill**: In a codebase with IoT/SCADA, mainframe, and CNC data sources, the data layer is complex enough to warrant dedicated analysis. The Codebase Analyzer catches surface-level encoding issues; this skill traces data flows end-to-end.

**Key capabilities**:
- Trace data from ingestion (file read, socket recv, DB query) through transformation to output
- Identify all encoding/decoding operations (explicit and implicit)
- Detect EBCDIC patterns (cp500, cp1047 codecs or manual byte manipulation)
- Inventory all `struct.pack`/`unpack` calls with format strings
- Find all `pickle`/`marshal`/`shelve` usage and assess deserialization risk
- Map all database connections and their encoding configurations
- Identify hardcoded byte constants that assume specific encodings
- Flag all points where binary data transitions to text data (the "bytes/str boundary")

**Inputs**: Path to codebase root, optional sample data files for encoding detection

**Outputs**:
- `data-layer-report.json` — complete data flow inventory
- `data-layer-report.md` — human-readable analysis with risk ratings
- `encoding-map.json` — every encoding-related operation in the codebase
- `serialization-inventory.json` — all serialization/deserialization points
- `bytes-str-boundaries.json` — every point where bytes become text or vice versa

**References needed**:
- `references/encoding-patterns.md` — EBCDIC, binary protocols, mixed encoding detection
- `references/scada-protocol-patterns.md` — common IoT/SCADA data handling patterns
- `references/serialization-migration.md` — pickle/marshal/shelve Py2→Py3 guide

#### Skill 0.3: Serialization Boundary Detector

**What it does**: Finds every place the codebase serializes or deserializes data, and assesses the migration risk for each. This includes not just `pickle` but also custom serialization, protocol buffers, msgpack, binary file formats, and any other persistence mechanism.

**Key capabilities**:
- Inventory all serialization libraries in use
- Detect custom serialization (classes with `__getstate__`/`__setstate__`, manual `struct` packing)
- Assess whether existing serialized data (on disk, in caches, in databases) will be readable after migration
- Flag pickle protocol versions and their Py2/Py3 compatibility
- Identify any use of `marshal` (Python-version-specific, extremely fragile across versions)
- Check for `shelve` databases that may contain Py2-pickled objects

**Inputs**: Path to codebase root, optional paths to data directories containing serialized files

**Outputs**:
- `serialization-report.json` — complete inventory with risk ratings
- `serialization-report.md` — human-readable summary with findings and remediation
- `data-migration-plan.json` — structured plan for migrating existing serialized data

#### Skill 0.4: C Extension Flagger

**What it does**: Identifies all C extensions, Cython modules, ctypes bindings, CFFI usage, and SWIG-generated wrappers in the codebase. Assesses their Python 3 compatibility and flags the specific C API changes that affect each.

**Key capabilities**:
- Find all `.c`, `.pyx`, `.pxd` files
- Detect `ctypes` and `cffi` usage patterns
- Check for SWIG `.i` interface files
- Flag deprecated C API usage (Py_UNICODE, PyCObject, etc.)
- Assess whether extensions use the limited/stable API
- Check for `tp_print` slot usage (removed in Py3.12+)
- Identify `wstr` usage (removed in 3.12)

**Inputs**: Path to codebase root, target Python version

**Outputs**:
- `c-extension-report.json` — inventory of all native code with compatibility assessment
- `c-extension-report.md` — human-readable summary with remediation guidance

#### Skill 0.5: Lint Baseline Generator

**What it does**: Runs all discovery linters against the codebase and produces a baseline report. This becomes the reference point for measuring migration progress.

**Key capabilities**:
- Run `pylint --py3k` and collect all warnings
- Run `pyupgrade --py3-plus` in dry-run mode
- Run `flake8` with `flake8-2020`
- Categorize all findings by type, severity, and module
- Produce per-module lint scores
- Generate a prioritized fix list

**Inputs**: Path to codebase root

**Outputs**:
- `lint-baseline.json` — all findings, categorized
- `lint-baseline.md` — human-readable summary
- `lint-config/` — initial configuration files for all linters

---

### Phase 1: Foundation

**Purpose**: Make the codebase migration-ready without actually converting anything. Add safety nets, establish dual-interpreter testing, and surface hidden issues.

**Gate criteria**: CI is green on Python 2 with all `__future__` imports in place. Test coverage on critical-path modules meets defined threshold. Lint baseline shows no regressions. All Phase 0 findings have been triaged (addressed, deferred, or accepted as risk).

**Rollback**: All changes in this phase are additive (new imports, new tests, new CI config). Rollback is straightforward revert of commits.

#### Skill 1.1: Future Imports Injector

**What it does**: Safely adds `from __future__ import print_function, division, unicode_literals, absolute_import` to every Python file in the codebase. This is backward-compatible with Python 2 but causes Python 2 to behave more like Python 3, flushing out issues early.

**Key capabilities**:
- Add future imports to all `.py` files that don't already have them
- Handle files with encoding declarations (future imports must come after)
- Handle files with docstrings (future imports come before or after depending on convention)
- Run tests after each batch of changes to catch breakage immediately
- Report which files broke after adding future imports (these are your highest-risk modules)
- Special handling for `unicode_literals` which is the most likely to cause breakage — can be applied separately with extra caution

**Inputs**: Path to codebase root, which future imports to add, batch size

**Outputs**:
- Modified `.py` files with future imports added
- `future-imports-report.json` — which files were modified, which broke, which were skipped
- `high-risk-modules.json` — files that failed after future import addition

**Important considerations**:
- `unicode_literals` changes the type of every string literal from `str` (bytes) to `unicode` (text) in Python 2. This *will* break code that passes string literals to APIs expecting bytes (file paths on some OSes, C extensions, binary protocols). This is actually desirable because it surfaces exactly the issues that will bite you in Py3, but it needs careful handling.
- The skill should offer a mode where `unicode_literals` is applied separately from the other three imports, with extra testing at each step.

#### Skill 1.2: Test Scaffold Generator

**What it does**: Generates characterization tests for modules that lack adequate test coverage, with special attention to encoding edge cases and data boundary behavior.

**Key capabilities**:
- Analyze existing test coverage and identify gaps
- Generate characterization tests that capture current behavior (not "correct" behavior — we want to know what the code does now so we can verify it does the same thing after conversion)
- **Encoding-aware test generation**: Deliberately inject non-ASCII data (accented characters, emoji, CJK text, EBCDIC-representable characters) into test inputs
- Generate tests for data ingestion paths (file reads, socket receives, DB queries)
- Generate tests for serialization round-trips (pickle/unpickle, serialize/deserialize)
- Generate tests for string/bytes boundary crossings identified by the Data Format Analyzer
- Generate property-based tests using `hypothesis` for critical data transformation functions
- Track which tests are characterization tests vs. correctness tests (characterization tests may need updating after migration; correctness tests should not)

**Inputs**: Path to module(s) to test, data layer report from Phase 0, encoding map from Phase 0

**Outputs**:
- Test files with comprehensive characterization tests
- `test-coverage-report.json` — before/after coverage metrics
- `test-manifest.json` — catalog of generated tests with their purpose (characterization vs. correctness)

**References needed**:
- `references/encoding-test-vectors.md` — test data for various encodings (UTF-8, Latin-1, EBCDIC, Shift-JIS, etc.)
- `references/hypothesis-strategies.md` — property-based testing strategies for data transformations

#### Skill 1.3: CI Dual-Interpreter Configurator

**What it does**: Configures the CI/CD pipeline to run tests under both Python 2 and Python 3, establishing the safety net for the entire migration.

**Key capabilities**:
- Detect existing CI system (Jenkins, GitHub Actions, GitLab CI, Travis, etc.)
- Add Python 3 test matrix alongside existing Python 2 tests
- Configure test reporting to clearly show which interpreter each failure comes from
- Set up "allowed failures" for Python 3 initially (informational, not blocking)
- Generate tox configuration for local dual-interpreter testing
- Configure coverage reporting for both interpreters

**Inputs**: Path to codebase root, CI system type, target Python 3 version

**Outputs**:
- Modified CI configuration files
- `tox.ini` or equivalent for local testing
- `ci-setup-report.md` — what was configured and how to use it

#### Skill 1.4: Custom Lint Rule Generator

**What it does**: Generates project-specific lint rules based on the Phase 0 analysis. These rules enforce migration standards and prevent regression as modules progress through phases.

**Key capabilities**:
- Generate `pylint` plugins that enforce phase-appropriate coding standards
- Generate `flake8` plugins for project-specific patterns
- Create pre-commit hooks that run phase-appropriate linters on changed files
- Produce per-module lint configurations that match each module's migration phase
- Flag regressions (Py2 idioms introduced into already-converted modules)
- Generate rules specific to the project's data patterns (e.g., "all SCADA data handlers must use explicit encoding")

**Inputs**: Phase 0 analysis outputs, coding standards document (if any)

**Outputs**:
- Custom lint plugins (pylint and flake8)
- `.pre-commit-config.yaml` configuration
- Per-module lint configuration files
- `lint-rules-documentation.md` — explains each custom rule and why it exists

---

### Phase 2: Mechanical Conversion

**Purpose**: Apply automated syntax transformations to the codebase, module by module, in dependency order. This handles the ~70-80% of changes that are pure syntax and low-risk.

**Gate criteria**: Each conversion unit passes its tests under both Python 2 and Python 3 before the next unit begins. No lint regressions. The Migration State Tracker shows all units in the current batch are green.

**Rollback**: Per conversion unit. Each unit is its own branch/commit. Reverting a single unit does not affect others (because we convert in dependency order, leaf-first).

#### Skill 2.1: Conversion Unit Planner

**What it does**: Takes the dependency graph from Phase 0 and produces an ordered conversion plan, grouping tightly-coupled modules into conversion units and scheduling them for conversion in safe dependency order.

**Key capabilities**:
- Topological sort of the dependency graph
- Cluster detection for modules that must be converted together (mutual imports, shared state)
- Risk scoring per conversion unit based on Phase 0 findings
- Scheduling that balances parallelism with dependency safety
- Identification of "gateway" modules that block large subgraphs
- Produces a human-reviewable conversion plan with estimated effort per unit

**Inputs**: Dependency graph from Phase 0, Phase 0 risk assessments

**Outputs**:
- `conversion-plan.json` — ordered list of conversion units with dependencies and risk scores
- `conversion-plan.md` — human-readable plan with timeline estimates
- `critical-path.json` — the longest dependency chain (determines minimum migration time)

#### Skill 2.2: Automated Converter

**What it does**: Applies automated syntax transformations to a single conversion unit. This is the workhorse skill that handles print statements, dictionary methods, exception syntax, import changes, and other mechanical transformations.

**Key capabilities**:
- Apply `futurize` or equivalent AST-based transformations
- Handle all mechanical Py2→Py3 syntax changes:
  - `print` statement → `print()` function
  - `except Exception, e` → `except Exception as e`
  - `dict.has_key(k)` → `k in dict`
  - `dict.iteritems()` → `dict.items()`
  - `xrange()` → `range()`
  - `raw_input()` → `input()`
  - `unicode()` → `str()`
  - `long` type references → `int`
  - Backtick repr → `repr()`
  - `<>` operator → `!=`
  - `exec` statement → `exec()` function
  - Octal literal `0777` → `0o777`
  - Relative imports → absolute or explicit relative imports
- Target-version-aware: only applies transformations appropriate for the target Py3 version
- Runs tests after conversion and reports pass/fail
- Produces a diff for human review

**Inputs**: Path to conversion unit, target Python version, conversion plan from Skill 2.1

**Outputs**:
- Modified source files
- `conversion-diff.patch` — reviewable diff of all changes
- `conversion-report.json` — what was changed, what was skipped, test results

#### Skill 2.3: Build System Updater

**What it does**: Updates the build and packaging infrastructure for Python 3 compatibility.

**Key capabilities**:
- Migrate `setup.py` to `pyproject.toml` + `setup.cfg` (or just update setup.py for Py3)
- Replace `distutils` usage with `setuptools` or `sysconfig` (critical for 3.12+)
- Update `python_requires` metadata
- Update classifiers (`Programming Language :: Python :: 3`)
- Handle conditional dependencies (libraries with different Py2/Py3 versions)
- Update Makefile, shell scripts, Docker images that reference `python` vs `python3`
- Update shebang lines (`#!/usr/bin/env python` → `#!/usr/bin/env python3`)
- Scan for and update `requirements.txt` / `Pipfile` / `poetry.lock` Py3-compatible versions

**Inputs**: Path to codebase root, target Python version

**Outputs**:
- Modified build files
- `build-system-report.json` — what was changed and why
- `dependency-compatibility.json` — which dependencies need version bumps for Py3

---

### Phase 3: Semantic Fixes

**Purpose**: Handle the changes that require human judgment. These are the transformations where the correct fix depends on the developer's intent, not just syntax rules. The bytes/string divide, integer division semantics, comparison operator changes, and library replacements all live here.

**Gate criteria**: Full test suite passes under Python 3. Integration tests pass. No encoding errors in logs during test runs. All bytes/str boundaries have been explicitly annotated. Type hints added to all public interfaces.

**Rollback**: More complex than Phase 2. Each semantic fix should be a separate, well-documented commit. The Migration State Tracker records dependencies between fixes so rollback order is clear.

#### Skill 3.1: Bytes/String Boundary Fixer

**What it does**: The single most important semantic skill. Identifies every bytes/str boundary in a conversion unit, determines the correct type at each point, and applies the fix. This is where mainframe EBCDIC data, SCADA binary protocols, and CNC text formats all need careful handling.

**Key capabilities**:
- Use the bytes-str boundary map from the Data Format Analyzer (Phase 0)
- For each boundary crossing, determine: is this data semantically bytes (binary data, protocol buffers, raw file content) or text (human-readable strings)?
- Apply appropriate fixes:
  - Text data: ensure it's `str` (decoded from bytes at ingestion point)
  - Binary data: ensure it's `bytes` (never decoded, stays as bytes throughout)
  - Mixed: add explicit encode/decode at the boundary with the correct codec
- Handle EBCDIC data paths: add explicit `decode('cp500')` or `decode('cp1047')` at mainframe data ingestion points
- Handle SCADA data paths: ensure binary protocol data stays as `bytes` and is only decoded when extracting text fields
- Handle file I/O: `open()` → `open(mode='rb')` for binary files, `open(encoding='...')` for text files
- Present decision points to the human: "This function receives data from a Modbus register and passes it to a string formatting operation. Should this be decoded as ASCII at the Modbus layer, or should the string formatting be changed to handle bytes?"

**Inputs**: Conversion unit path, bytes-str boundary map from Phase 0, data layer report

**Outputs**:
- Modified source files with explicit bytes/str handling
- `bytes-str-fixes.json` — every fix applied with reasoning
- `decisions-needed.json` — boundary crossings that require human judgment
- `encoding-annotations.json` — every encode/decode operation with its codec and rationale

**References needed**:
- `references/bytes-str-patterns.md` — common patterns and their correct Py3 form
- `references/industrial-data-encodings.md` — encoding conventions for SCADA, CNC, mainframe data

#### Skill 3.2: Library Replacement Advisor

**What it does**: Maps Python 2-only or deprecated libraries to their Python 3 equivalents, generates replacement code, and handles the transition.

**Key capabilities**:
- Maintain a mapping of Py2 → Py3 library replacements:
  - `ConfigParser` → `configparser`
  - `Queue` → `queue`
  - `cPickle` → `pickle` (Py3's pickle auto-selects C implementation)
  - `cStringIO` → `io.StringIO` / `io.BytesIO`
  - `urllib`/`urllib2`/`urlparse` → `urllib.parse`/`urllib.request`/`urllib.error`
  - `HTMLParser` → `html.parser`
  - `commands` → `subprocess`
  - `thread` → `_thread` / `threading`
  - Standard library modules removed in 3.12+
- Check third-party dependencies for Py3 compatibility
- Suggest alternative libraries for Py2-only dependencies with no Py3 port
- Generate migration code for complex library transitions (e.g., `urllib2` → `requests`)
- Handle version-specific removals (modules removed in 3.12 that exist in 3.11)

**Inputs**: Conversion unit path, target Python version, dependency inventory from Phase 0

**Outputs**:
- `library-replacements.json` — mapping of old → new for this unit
- `no-replacement-found.json` — Py2 libraries with no clear Py3 equivalent (manual work needed)
- Modified source files with library replacements applied

#### Skill 3.3: Dynamic Pattern Resolver

**What it does**: Handles Python language features that changed semantically between Py2 and Py3, where the automated converter can't determine the correct fix.

**Key capabilities**:
- Metaclass syntax: `__metaclass__ = Meta` → `class Foo(metaclass=Meta)`
- `exec` statement edge cases: `exec code in globals, locals` → `exec(code, globals, locals)`
- Integer division: `/` operator behavior change (true division by default in Py3). Flag all `/` operations on integer operands.
- Comparison operators: `__cmp__` removal → must implement `__lt__`, `__eq__`, etc. via `functools.total_ordering` or explicit methods
- `__nonzero__` → `__bool__`
- `__unicode__` → `__str__`, old `__str__` → `__bytes__`
- `__div__` → `__truediv__` and `__floordiv__`
- `buffer()` → `memoryview()`
- `apply()` removal
- `reduce()` moved to `functools`
- `map()`/`filter()`/`zip()` return iterators not lists
- `dict.keys()`/`.values()`/`.items()` return views not lists
- `sorted()` no longer accepts `cmp` parameter → use `key` with `functools.cmp_to_key`
- Relative import changes
- `__hash__` changes when `__eq__` is defined

**Inputs**: Conversion unit path, Phase 0 analysis

**Outputs**:
- Modified source files
- `dynamic-pattern-report.json` — every pattern found and how it was resolved
- `manual-review-needed.json` — patterns that need human decision

#### Skill 3.4: Type Annotation Adder

**What it does**: Adds type annotations to converted code, leveraging the migration as an opportunity to improve long-term maintainability. Uses information from the bytes/str boundary analysis to add particularly valuable annotations about data types.

**Key capabilities**:
- Infer types from usage patterns, variable names, docstrings, and test cases
- Add function signature annotations for all public interfaces
- Add variable annotations where types are non-obvious
- Leverage bytes/str boundary analysis: annotate exactly which functions expect `bytes` vs `str`
- Generate `py.typed` marker file
- Configure `mypy` for gradual typing (start with `--ignore-missing-imports`)
- Use `Union[str, bytes]` sparingly and flag these as tech debt to resolve

**Inputs**: Conversion unit path, bytes-str boundary analysis, existing docstrings

**Outputs**:
- Modified source files with type annotations
- `mypy` configuration
- `typing-report.json` — annotation coverage metrics

---

### Phase 4: Verification & Hardening

**Purpose**: Prove that the migration is correct. Run comprehensive testing that goes beyond unit tests to compare actual behavior between Py2 and Py3 code paths.

**Gate criteria**: Zero behavioral diffs between Py2 and Py3 on the full test suite and integration tests. No performance regressions beyond acceptable thresholds. Encoding stress tests pass. Migration completeness checker reports 100%.

**Rollback**: At this phase, the code should be correct. If verification reveals issues, roll back specific modules to Phase 3 for additional semantic fixes. The Gate Checker tracks which modules need rework.

#### Skill 4.1: Behavioral Diff Generator

**What it does**: Runs the same inputs through both Python 2 and Python 3 code paths and compares every output. Any difference is a potential migration bug.

**Key capabilities**:
- Execute the test suite under both interpreters and capture all outputs (return values, stdout, stderr, files written, network requests made)
- Deep comparison of outputs, handling expected differences (repr format changes, dict ordering, etc.)
- Flag unexpected differences with full context for debugging
- Support for running integration tests and comparing HTTP responses, database writes, file outputs
- Generate a report that clearly separates "expected differences" from "potential bugs"

**Inputs**: Path to codebase, test suite, both interpreters

**Outputs**:
- `behavioral-diff-report.json` — every difference found, categorized
- `behavioral-diff-report.md` — human-readable summary
- `expected-differences.json` — diffs that are known/acceptable (dict repr, etc.)
- `potential-bugs.json` — diffs that need investigation

#### Skill 4.2: Performance Benchmarker

**What it does**: Compares performance between Python 2 and Python 3 execution to catch regressions.

**Key capabilities**:
- Run performance benchmarks on critical code paths under both interpreters
- Measure wall-clock time, CPU time, memory usage, I/O operations
- Statistical analysis (multiple runs, confidence intervals, outlier detection)
- Flag regressions beyond configurable threshold (e.g., >10% slower)
- Identify Py3-specific optimizations that could be applied (f-strings are faster than format(), etc.)
- Note: Py3.11+ has significant performance improvements; results will vary by target version

**Inputs**: Codebase path, benchmark suite (or auto-detected from tests), both interpreters

**Outputs**:
- `performance-report.json` — detailed benchmark results
- `performance-report.md` — human-readable summary with charts
- `optimization-opportunities.json` — Py3-specific speedups that could be applied

#### Skill 4.3: Encoding Stress Tester

**What it does**: Deliberately exercises every data path with adversarial encoding inputs to flush out latent encoding bugs that normal testing misses.

**Key capabilities**:
- Generate test inputs in every encoding the codebase handles (UTF-8, Latin-1, EBCDIC, Shift-JIS, etc.)
- Include edge cases: BOM markers, surrogate pairs, null bytes, mixed encodings within single files
- Test every data ingestion path (file read, network receive, DB query, serial port) with non-ASCII data
- Test serialization round-trips with non-ASCII data
- Test file I/O paths with non-ASCII filenames
- For SCADA/IoT paths: test with binary data that contains byte sequences that look like valid UTF-8 but aren't
- For mainframe paths: test EBCDIC data with characters that don't have ASCII equivalents

**Inputs**: Data layer report from Phase 0, encoding map, codebase path

**Outputs**:
- `encoding-stress-report.json` — pass/fail for every data path × every encoding
- `encoding-failures.json` — detailed failure information with reproduction steps
- Generated test cases that can be added to the permanent test suite

**References needed**:
- `references/encoding-edge-cases.md` — comprehensive list of encoding gotchas
- `references/adversarial-encoding-inputs.md` — test vectors for common failure modes

#### Skill 4.4: Migration Completeness Checker

**What it does**: Scans the entire codebase for any remaining Python 2 artifacts, incomplete conversions, or leftover compatibility shims that should have been resolved.

**Key capabilities**:
- Check for any remaining Py2 syntax
- Check for `six` or `future` usage that can be simplified now that Py2 support is dropped
- Check for `# type: ignore` comments that were added during migration and may no longer be needed
- Check for `TODO` or `FIXME` comments added during migration
- Check for `__future__` imports that are no longer needed
- Check for dual-compatibility patterns that can be simplified
- Check for `sys.version_info` checks that can be removed
- Verify all lint rules pass at Phase 4 strictness level
- Run `mypy` and report remaining type errors

**Inputs**: Codebase path, migration state tracker data

**Outputs**:
- `completeness-report.json` — every remaining migration artifact found
- `completeness-report.md` — human-readable summary with remediation guidance
- `cleanup-tasks.json` — ordered list of remaining cleanup work

---

### Phase 5: Cutover & Cleanup

**Purpose**: Switch production to Python 3 and remove all Py2 compatibility scaffolding. This is the point of no return.

**Gate criteria**: All Phase 4 gates passed. Production running on Python 3 for defined soak period with no issues. All stakeholders have signed off on cutover.

**Rollback**: Maintain the ability to switch back to Python 2 for a defined period after cutover (e.g., 2 weeks). After the soak period, Py2 compatibility code is removed and rollback is no longer possible.

#### Skill 5.1: Canary Deployment Planner

**What it does**: Generates the infrastructure configuration for running Python 2 and Python 3 side by side in production, routing a configurable percentage of traffic to each.

**Key capabilities**:
- Detect deployment infrastructure (Kubernetes, Docker Compose, bare metal, etc.)
- Generate configuration for parallel Py2/Py3 deployments
- Configure traffic routing (percentage-based, feature-flag-based, or request-attribute-based)
- Set up output comparison: log diffs between Py2 and Py3 responses for the same inputs
- Generate monitoring dashboards for error rates, latency, and correctness per interpreter
- Define rollback triggers (automatic rollback if error rate exceeds threshold)
- Plan the ramp-up schedule (1% → 5% → 25% → 50% → 100%)

**Inputs**: Deployment configuration, infrastructure type, rollback thresholds

**Outputs**:
- Deployment configuration files for parallel execution
- Monitoring dashboard configuration
- `canary-plan.md` — human-readable deployment plan with rollback procedures
- `rollback-runbook.md` — step-by-step rollback instructions

#### Skill 5.2: Compatibility Shim Remover

**What it does**: After full cutover to Python 3, removes all the dual-compatibility code that was added during migration.

**Key capabilities**:
- Remove `from __future__` imports (no longer needed on Py3)
- Replace `six` usage with direct Py3 equivalents
- Replace `python-future` usage with direct Py3 equivalents
- Remove `sys.version_info` conditional blocks (keep only the Py3 branch)
- Simplify `try/except ImportError` blocks that handle Py2/Py3 import differences
- Apply `pyupgrade --py3X-plus` for target-version-specific modernization
- Run tests after each batch of removals

**Inputs**: Codebase path, target Python version

**Outputs**:
- Modified source files with compatibility shims removed
- `shim-removal-report.json` — what was removed and where
- `shim-removal-diff.patch` — reviewable diff

#### Skill 5.3: Dead Code Detector

**What it does**: Finds code that was only reachable under Python 2 and is now dead, as well as any other dead code that the migration process surfaced.

**Key capabilities**:
- Detect unreachable `if sys.version_info < (3, 0)` blocks
- Detect unused Py2 compatibility functions
- Detect modules that were only imported for Py2 compatibility
- Use `vulture` or equivalent for general dead code detection
- Cross-reference with test coverage data to identify untested code
- Flag but don't auto-remove (dead code removal should be human-reviewed)

**Inputs**: Codebase path, coverage data

**Outputs**:
- `dead-code-report.json` — all suspected dead code with confidence scores
- `dead-code-report.md` — human-readable summary
- `safe-to-remove.json` — dead code that the skill is highly confident about (still requires human review)

---

## Cross-Cutting Orchestration Skills

These skills operate across all phases and provide the coordination layer that holds the migration together.

### Skill X.1: Migration State Tracker

**What it does**: Maintains a persistent record of the migration state for every module in the codebase. Tracks which phase each module is in, what gates have been passed, what's blocking progress, and overall migration metrics.

**Key capabilities**:
- Initialize from Phase 0 analysis (every module starts at Phase 0)
- Update module state as skills complete their work
- Track dependencies between modules (can't move module A to Phase 3 if module B, which it depends on, is still in Phase 2)
- Generate progress dashboards (percentage complete by phase, risk heatmap, timeline projection)
- Track decisions made and their rationale (for archaeology — the next team shouldn't have to re-derive why a decision was made)
- Record all rollbacks and their causes
- Export state for reporting to stakeholders

**Data model**:
```
module_state = {
    "module_path": "src/scada/modbus_reader.py",
    "current_phase": 2,
    "phase_history": [
        {"phase": 0, "completed": "2026-02-15", "gate_passed": true},
        {"phase": 1, "completed": "2026-02-20", "gate_passed": true},
        {"phase": 2, "started": "2026-02-22", "gate_passed": false}
    ],
    "conversion_unit": "scada-core",
    "risk_score": "high",
    "risk_factors": ["binary_protocol_handling", "ebcdic_decoding", "no_existing_tests"],
    "blockers": [],
    "decisions": [
        {"date": "2026-02-20", "decision": "Modbus register data stays as bytes until display layer", "rationale": "Protocol data is binary, only text representation needed at UI"}
    ]
}
```

**Inputs**: Phase 0 analysis outputs (to initialize), ongoing skill outputs (to update)

**Outputs**:
- `migration-state.json` — complete state for all modules
- `migration-dashboard.md` — human-readable progress summary
- `migration-timeline.json` — projected completion dates based on velocity

### Skill X.2: Rollback Plan Generator

**What it does**: At each phase, maintains the ability to undo the current phase's changes. Generates specific rollback procedures based on what has been changed.

**Key capabilities**:
- Track every change made by every skill (file modifications, configuration changes, new files)
- For Phase 1: generate simple revert instructions (remove future imports, remove tests, revert CI config)
- For Phase 2: generate per-unit rollback (revert specific commits, in reverse dependency order)
- For Phase 3: generate per-fix rollback with dependency tracking (some semantic fixes depend on others)
- For Phase 4: no code changes to roll back, but verification failures may trigger rollback to Phase 3
- For Phase 5: maintain Py2 deployment capability for defined soak period
- Generate rollback runbooks with exact commands
- Test rollback procedures periodically (can we actually roll back and have tests pass?)

**Inputs**: Migration state tracker data, git history

**Outputs**:
- `rollback-plan.json` — machine-executable rollback steps per phase per module
- `rollback-runbook.md` — human-readable rollback procedures
- `rollback-test-results.json` — results of rollback dry-run testing

### Skill X.3: Gate Checker

**What it does**: Validates that all gate criteria for a given phase have been met before allowing a module (or the entire codebase) to advance to the next phase.

**Key capabilities**:
- Define gate criteria per phase (configurable, with sensible defaults)
- Run all gate checks: test suite pass rate, lint compliance, coverage thresholds, encoding test results, performance benchmarks
- Produce a clear pass/fail report with evidence for each criterion
- Block advancement if any criteria are not met
- Track waivers (criteria that have been explicitly accepted as risk by stakeholders)
- Integrate with CI to automatically run gate checks on pull requests

**Default gate criteria**:
- **Phase 0 → 1**: Assessment report reviewed, migration plan approved, target version selected
- **Phase 1 → 2**: CI green on Py2 with future imports, test coverage at threshold, lint baseline stable
- **Phase 2 → 3**: All conversion units pass tests under both Py2 and Py3, no lint regressions
- **Phase 3 → 4**: Full test suite passes under Py3, no encoding errors, type hints on public interfaces
- **Phase 4 → 5**: Zero behavioral diffs, no performance regressions, encoding stress tests pass, completeness checker at 100%
- **Phase 5 done**: Production soak period complete, no rollback-triggering incidents

**Inputs**: Migration state, phase number, module or codebase scope

**Outputs**:
- `gate-check-report.json` — pass/fail per criterion with evidence
- `gate-check-report.md` — human-readable summary
- `waivers.json` — explicitly accepted risks

---

## Skill Implementation Priority

### Tier 1: Build First (foundation for everything else)
1. **Skill X.1: Migration State Tracker** — all other skills read from and write to this
2. **Skill 0.1: Codebase Analyzer** — everything depends on its output
3. **Skill 0.2: Data Format Analyzer** — critical given the IoT/SCADA/mainframe data landscape
4. **Skill X.3: Gate Checker** — enforces discipline from day one

### Tier 2: Build Next (enable Phase 1 work to begin)
5. **Skill 0.5: Lint Baseline Generator** — quick win, high value
6. **Skill 1.1: Future Imports Injector** — first real code changes
7. **Skill 1.2: Test Scaffold Generator** — safety net for everything that follows
8. **Skill 2.1: Conversion Unit Planner** — needed before any Phase 2 work

### Tier 3: Core Conversion (the main migration work)
9. **Skill 2.2: Automated Converter** — the mechanical conversion workhorse
10. **Skill 3.1: Bytes/String Boundary Fixer** — the hardest and most important semantic skill
11. **Skill 3.2: Library Replacement Advisor** — necessary for Py3 stdlib changes
12. **Skill 3.3: Dynamic Pattern Resolver** — handles remaining semantic changes

### Tier 4: Quality Assurance
13. **Skill 4.1: Behavioral Diff Generator** — proves correctness
14. **Skill 4.3: Encoding Stress Tester** — critical for this codebase's data landscape
15. **Skill 4.4: Migration Completeness Checker** — ensures nothing was missed
16. **Skill 4.2: Performance Benchmarker** — catches regressions

### Tier 5: Polish and Cutover
17. **Skill 0.3: Serialization Boundary Detector** — important but can be deferred from Phase 0 if needed
18. **Skill 0.4: C Extension Flagger** — important but scope may be small
19. **Skill 1.3: CI Dual-Interpreter Configurator** — valuable but team may already know how
20. **Skill 1.4: Custom Lint Rule Generator** — valuable but manual rules work initially
21. **Skill 2.3: Build System Updater** — can be done manually for smaller build systems
22. **Skill 3.4: Type Annotation Adder** — valuable but optional for migration correctness
23. **Skill 5.1: Canary Deployment Planner** — needed at cutover time, not before
24. **Skill 5.2: Compatibility Shim Remover** — needed after cutover
25. **Skill 5.3: Dead Code Detector** — cleanup, lowest urgency
26. **Skill X.2: Rollback Plan Generator** — important but can be manual initially

---

## Reference Documents Needed

These reference documents are bundled into each skill's own `references/` directory. Each skill contains only the references it needs:

| Reference | Used By | Content |
|-----------|---------|---------|
| `py2-py3-syntax-changes.md` | Skills 0.1, 2.2 | Complete catalog of syntax differences |
| `py2-py3-semantic-changes.md` | Skills 0.1, 3.1, 3.3 | Complete catalog of semantic differences |
| `stdlib-removals-by-version.md` | Skills 0.1, 3.2 | What's removed in each Py3 minor version |
| `encoding-patterns.md` | Skills 0.2, 3.1, 4.3 | EBCDIC, binary protocols, mixed encoding detection |
| `scada-protocol-patterns.md` | Skills 0.2, 3.1 | Common IoT/SCADA data handling patterns |
| `serialization-migration.md` | Skills 0.2, 0.3 | pickle/marshal/shelve Py2→Py3 guide |
| `encoding-test-vectors.md` | Skills 1.2, 4.3 | Test data for various encodings |
| `hypothesis-strategies.md` | Skill 1.2 | Property-based testing strategies |
| `bytes-str-patterns.md` | Skill 3.1 | Common patterns and correct Py3 form |
| `industrial-data-encodings.md` | Skill 3.1 | Encoding conventions for SCADA, CNC, mainframe |
| `encoding-edge-cases.md` | Skill 4.3 | Comprehensive encoding gotchas |
| `adversarial-encoding-inputs.md` | Skill 4.3 | Test vectors for common failure modes |

---

## Directory Structure

```
code-translation-skills/
├── PLAN.md                                  # This document
├── README.md
├── LICENSE
├── docs/
│   ├── MIGRATION-GUIDE.md
│   └── process/
│
└── skills/                                  # All skills are flat — copy into .claude/skills/
    ├── py2to3-automated-converter/          # Skill 2.2
    ├── py2to3-behavioral-diff-generator/    # Skill 4.1
    ├── py2to3-build-system-updater/         # Skill 2.3
    ├── py2to3-bytes-string-fixer/           # Skill 3.1
    ├── py2to3-c-extension-flagger/          # Skill 0.4
    ├── py2to3-canary-deployment-planner/    # Skill 5.1
    ├── py2to3-ci-dual-interpreter/          # Skill 1.3
    ├── py2to3-codebase-analyzer/            # Skill 0.1
    ├── py2to3-compatibility-shim-remover/   # Skill 5.2
    ├── py2to3-completeness-checker/         # Skill 4.4
    ├── py2to3-conversion-unit-planner/      # Skill 2.1
    ├── py2to3-custom-lint-rules/            # Skill 1.4
    ├── py2to3-data-format-analyzer/         # Skill 0.2
    ├── py2to3-dead-code-detector/           # Skill 5.3
    ├── py2to3-dynamic-pattern-resolver/     # Skill 3.3
    ├── py2to3-encoding-stress-tester/       # Skill 4.3
    ├── py2to3-future-imports-injector/      # Skill 1.1
    ├── py2to3-gate-checker/                 # Skill X.3
    ├── py2to3-library-replacement/          # Skill 3.2
    ├── py2to3-lint-baseline-generator/      # Skill 0.5
    ├── py2to3-migration-state-tracker/      # Skill X.1
    ├── py2to3-performance-benchmarker/      # Skill 4.2
    ├── py2to3-rollback-plan-generator/      # Skill X.2
    ├── py2to3-serialization-detector/       # Skill 0.3
    ├── py2to3-test-scaffold-generator/      # Skill 1.2
    └── py2to3-type-annotation-adder/        # Skill 3.4
```

---

## Next Steps

1. Review and approve this plan
2. Build Tier 1 skills (Migration State Tracker, Codebase Analyzer, Data Format Analyzer, Gate Checker)
3. Run Phase 0 against the actual codebase to validate assumptions and refine subsequent skill requirements
4. Iterate on the plan based on Phase 0 findings
5. Build Tier 2 skills and begin Phase 1 work
6. Continue through tiers, refining skills based on real-world results at each phase
