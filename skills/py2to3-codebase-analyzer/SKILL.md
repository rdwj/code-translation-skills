---
name: py2to3-codebase-analyzer
description: >
  Analyze a Python 2 codebase to produce a comprehensive migration readiness report for
  upgrading to Python 3. Use this skill whenever someone needs to assess a legacy Python 2
  codebase before migration, understand the scope and risk of a Py2→Py3 conversion, build
  a dependency graph of Python modules, inventory Python 2-isms and categorize them by risk,
  or generate a version compatibility matrix for different Python 3 target versions. Also
  trigger when someone says things like "scan this codebase," "what's the migration risk,"
  "how big is this conversion," "analyze imports," or "what Python 2 patterns are in here."
  For polyglot codebases or when ast.parse() fails on Python 2 syntax, this skill now
  delegates to the universal-code-graph skill for tree-sitter-based analysis.
---

# Codebase Analyzer

Scan a Python 2 codebase and produce a migration readiness report that tells you: how big
is this project, what are the dependencies between modules, what Python 2 patterns exist
and how risky are they, what's the test coverage situation, and which Python 3 target
versions are feasible.

This skill is the foundation of the entire migration — every other skill in the suite
depends on its outputs. Take the time to be thorough.

**Enhanced with tree-sitter:** This skill now supports a two-pipeline approach. Python files
that parse under `ast` still use the battle-tested `Py2PatternVisitor`. Files that fail
`ast.parse()` (Python 2 syntax like `print "hello"` or `except Error, e:`) are analyzed
via tree-sitter, which provides error-recovery parsing that extracts imports, definitions,
and patterns from the parseable portions of the file. Non-Python files in polyglot codebases
are also analyzed via tree-sitter. For full polyglot analysis, use the `universal-code-graph`
skill directly — this skill focuses on the Python 2→3 migration perspective.

## When to Use

- Before starting any Python 2 → 3 migration work
- When stakeholders need a scope/timeline estimate
- When you need to determine the migration order for modules
- When assessing whether a codebase can target Python 3.12+ (which removed many stdlib modules)
- When `ast.parse()` fails on Python 2 files and you need better coverage than regex fallback
- When the codebase contains non-Python files that participate in the dependency graph

## Inputs

The user provides:
- **codebase_path**: Root directory of the Python 2 codebase
- **target_versions** (optional): Python 3 versions to evaluate compatibility against. Defaults to `["3.9", "3.11", "3.12", "3.13"]`
- **exclude_patterns** (optional): Glob patterns for directories/files to exclude (e.g., `["**/vendor/**", "**/test/**"]`)

## Outputs

All outputs go into a `migration-analysis/` directory at the codebase root (or a user-specified output location):

| File | Format | Purpose |
|------|--------|---------|
| `migration-report.md` | Markdown | Human-readable summary with key findings and recommendations |
| `migration-report.json` | JSON | Machine-readable full analysis (consumed by other skills) |
| `dependency-graph.json` | JSON | Module dependency graph with import relationships. Nodes now include `language` property. |
| `dependency-graph.html` | HTML | Interactive force-directed visualization (language color-coded when polyglot) |
| `migration-order.json` | JSON | Topologically sorted conversion order with cluster groupings |
| `version-matrix.md` | Markdown | Compatibility assessment per target Python 3 version |
| `py2-ism-inventory.json` | JSON | Every Python 2 pattern found, categorized and located |
| `call-graph.json` | JSON | Function/method-level call relationships (NEW — when tree-sitter is available) |
| `language-summary.json` | JSON | Detected languages and file counts (NEW — when tree-sitter is available) |

## Scope and Chunking

This skill scans the entire codebase in a single pass to build a complete dependency graph. On large codebases (500+ Python files), this can produce substantial output that strains the agent's context window.

**For codebases under 200 files**: Run on the full codebase. Output will typically be under 50KB.

**For codebases of 200–500 files**: Run on the full codebase but direct the agent to produce summary output (top-20 highest-risk modules, dependency graph statistics) rather than per-file detail. The full JSON outputs on disk remain complete — the agent just shouldn't dump them into the conversation.

**For codebases over 500 files**: Split by top-level package. Run the analyzer on each package directory separately, producing per-package output files. Then run a final pass that merges the dependency graphs at the cross-package boundary. Example:

```bash
# Analyze packages separately
python scripts/analyze_codebase.py src/core/ --output migration-analysis/core/
python scripts/analyze_codebase.py src/data_processing/ --output migration-analysis/data_processing/
python scripts/analyze_codebase.py src/io_protocols/ --output migration-analysis/io_protocols/

# Merge results
python scripts/analyze_codebase.py --merge migration-analysis/*/raw-scan.json --output migration-analysis/
```

**Key principle**: The JSON output files can be arbitrarily large — they live on disk and downstream skills read them from disk. What matters for context management is how much the agent puts into the conversation. Direct the agent to summarize, not regurgitate.

## Workflow

### Step 1: Discover the Codebase

Run `scripts/analyze.py` to perform the initial scan. This script walks the codebase and
produces a raw inventory of every `.py` file with metadata:

```bash
python3 scripts/analyze.py <codebase_path> --output <output_dir> [--exclude <patterns>]
```

The script uses Python's `ast` module to parse each file and extract:
- All imports (what each module depends on)
- All Python 2-isms found (categorized — see "Pattern Categories" below)
- Basic metrics (lines of code, number of functions/classes, complexity estimate)
- Encoding declarations
- Shebang lines

If a file fails to parse under Python 3's ast (which it will for files with Python 2-only
syntax like `print "hello"`), the script falls back in two stages:

1. **Tree-sitter fallback** (preferred): If tree-sitter is available, the file is parsed
   using the tree-sitter Python grammar. Tree-sitter does error-recovery parsing — it
   produces a concrete syntax tree even for Python 2 constructs, marking unparseable
   regions as ERROR nodes while continuing with the rest. This gives us imports, function
   definitions, class definitions, and Python 2 pattern detection (via `Py2PatternDetectorTS`)
   from the parseable portions. This is a major improvement over regex-only.

2. **Regex fallback** (legacy): If tree-sitter is not available, the script falls back to
   regex-based detection as before. This still works but misses function definitions, class
   hierarchies, and import relationships that tree-sitter captures.

The tree-sitter fallback is transparent — same output format, same findings dicts, same
risk scoring. A `parser: "tree-sitter"` field distinguishes these results from ast-parsed ones.

### Step 2: Build the Dependency Graph

Run `scripts/build_dep_graph.py` to construct the full dependency graph from the import data:

```bash
python3 scripts/build_dep_graph.py <output_dir>/raw-scan.json --output <output_dir>
```

This produces:
- `dependency-graph.json` — the full graph with nodes (modules) and edges (imports)
- `dependency-graph.html` — an interactive force-directed visualization (open in any browser)
- `migration-order.json` — topological sort with cluster detection

The HTML visualization is a self-contained file with no external dependencies. It renders
an interactive force-directed graph where nodes are color-coded by package and sized by
line count. Hover for details, click to highlight connections, drag to rearrange, and
scroll to zoom. Gateway modules are marked with orange rings, orphans with dashed purple
rings. The template lives in `assets/dependency-graph-template.html`.

The dependency graph is critical because it determines **what order to convert modules in**.
Leaf modules (those with no internal dependencies) get converted first. Tightly coupled
modules that import each other form "clusters" that must be converted as a unit.

The script identifies:
- **Leaf modules**: No imports from other project modules. Convert first.
- **Gateway modules**: Many modules depend on them. High-impact, convert carefully.
- **Clusters**: Groups of mutually-importing modules. Must convert together.
- **Orphan modules**: Nothing imports them. Could be dead code.

### Step 3: Assess Version Compatibility

For each target Python version, check whether the codebase uses any standard library
modules or features that were removed or changed in that version. The key version
boundaries are:

Read `references/stdlib-removals-by-version.md` for the complete list. The critical ones:

- **3.12**: `distutils` removed entirely, plus 13 other stdlib modules (see reference)
- **3.13**: Further removals, C API changes

For each target version, the report should say:
- How many files are affected by removals specific to that version
- What the incremental cost is to go from (e.g.) 3.11 → 3.12
- A recommendation on target version

### Step 4: Generate the Migration Report

Synthesize all findings into `migration-report.md`. The report structure:

```markdown
# Migration Readiness Report: [Project Name]

## Executive Summary
- Total Python files: N
- Total lines of code: N
- Estimated migration effort: [small/medium/large/very large]
- Recommended target version: 3.X
- Highest-risk areas: [list]

## Codebase Overview
- Module count and structure
- Dependency graph summary (how many clusters, max depth, gateway modules)
- Test coverage assessment

## Python 2 Pattern Inventory
- Syntax-only issues (automatable): N occurrences across M files
- Semantic issues (manual review needed): N occurrences across M files
- Data layer issues (highest risk): N occurrences across M files
- Breakdown by category (see Pattern Categories)

## Version Compatibility Matrix
- Table showing each target version and what breaks

## Dependency Analysis
- Conversion order recommendation
- Cluster list with members
- Gateway modules that block large subgraphs
- Estimated conversion units: N

## Risk Assessment
- Top 10 highest-risk modules with reasoning
- Data layer risk summary
- Third-party dependency risks

## Recommended Next Steps
- Specific actions to take before starting Phase 1
```

(see reference)` was:

```

## Pattern Categories

Each Python 2 pattern found is categorized by type and risk level. This categorization
drives the entire migration strategy — syntax-only issues go to the Automated Converter
(Phase 2), semantic issues go to the specialized Phase 3 skills.

### Syntax-Only (Low Risk — Automatable)

These can be fixed mechanically with high confidence:

| Pattern | Example | Py3 Equivalent |
|---------|---------|----------------|
| `print` statement | `print "hello"` | `print("hello")` |
| `except` comma syntax | `except Error, e:` | `except Error as e:` |
| `<>` operator | `a <> b` | `a != b` |
| Backtick repr | `` `x` `` | `repr(x)` |
| `has_key()` | `d.has_key(k)` | `k in d` |
| Octal literals | `0777` | `0o777` |
| `exec` statement | `exec code` | `exec(code)` |
| `raise` string | `raise "error"` | `raise Exception("error")` |
| Long integer suffix | `123L` | `123` |
| `raw_input` | `raw_input()` | `input()` |

### Semantic — Iterator/View Changes (Medium Risk)

These change return types. Usually automatable but can cause subtle bugs:

| Pattern | Py2 Behavior | Py3 Behavior | Risk |
|---------|-------------|-------------|------|
| `dict.keys()` | Returns list | Returns view | Medium — code that indexes into keys breaks |
| `dict.values()` | Returns list | Returns view | Medium |
| `dict.items()` | Returns list | Returns view | Medium |
| `dict.iteritems()` | Returns iterator | Removed | Low — just rename to `.items()` |
| `map()` | Returns list | Returns iterator | Medium — code that indexes result breaks |
| `filter()` | Returns list | Returns iterator | Medium |
| `zip()` | Returns list | Returns iterator | Medium |
| `range()` / `xrange()` | list / iterator | iterator (xrange behavior) | Low-Medium |

### Semantic — String/Bytes (High Risk)

The most dangerous category. The Py2 `str` type is bytes, the Py3 `str` type is text.
Code that conflates the two will break in ways that may not be caught by tests if test
data is ASCII-only.

| Pattern | What to Look For | Risk |
|---------|-----------------|------|
| Implicit encoding | `str` used where `bytes` or `unicode` is meant | Critical |
| `str()` on bytes | Code passing bytes to string operations | High |
| String formatting with bytes | `"pattern: %s" % byte_data` | High |
| File I/O without encoding | `open(f)` without `encoding=` or `mode='rb'` | High |
| Socket/network data | `socket.recv()` result used as string | High |
| `struct.pack/unpack` mixed with strings | Binary data crossing into text operations | High |
| `encode()`/`decode()` usage | May indicate awareness but check correctness | Medium |
| `unicode()` calls | Need to become `str()` but check encoding param | Medium |
| `__unicode__` method | Must become `__str__`, old `__str__` becomes `__bytes__` | Medium |
| Hardcoded byte values | `\x00`, `\xff` etc. in string context | High |
| EBCDIC codecs | `cp500`, `cp1047` usage | High — verify encoding handling |

### Semantic — Division and Numeric (Medium Risk)

| Pattern | Py2 Behavior | Py3 Behavior | Risk |
|---------|-------------|-------------|------|
| `/` operator on ints | Integer division (truncating) | True division (float) | High if math depends on truncation |
| `long` type | Separate type | Merged into `int` | Low |
| `int` overflow to `long` | Automatic | N/A (always arbitrary precision) | Low |
| `__div__` method | Division operator | Must split into `__truediv__`/`__floordiv__` | Medium |
| `cmp()` function | Built-in | Removed | Medium |
| `__cmp__` method | Comparison | Must implement rich comparison methods | Medium |

### Semantic — Import and Module (Medium Risk)

| Pattern | Issue | Risk |
|---------|-------|------|
| Relative imports | Implicit in Py2, must be explicit in Py3 | Medium |
| `from __future__` | Already present = good sign | Low |
| Renamed stdlib modules | `ConfigParser` → `configparser`, etc. | Low (mechanical) |
| Removed stdlib modules | `cgi`, `pipes`, `telnetlib`, etc. (version-dependent) | High for 3.12+ |
| `distutils` usage | Removed in 3.12 | Blocker for 3.12+ |

### Metaclass and Class Patterns (Medium Risk)

| Pattern | Py2 | Py3 | Risk |
|---------|-----|-----|------|
| `__metaclass__` attribute | Class attribute | `metaclass=` keyword | Medium |
| Old-style classes | `class Foo:` (no base) | Always new-style | Low-Medium |
| `__nonzero__` | Bool conversion | `__bool__` | Low |
| `__getslice__` | Slice access | Removed, use `__getitem__` | Medium |
| `buffer()` | Buffer protocol | `memoryview()` | Medium |

## Interpreting Risk Scores

The migration report assigns each module a composite risk score based on:

1. **Pattern density**: How many Py2-isms per 100 lines of code
2. **Semantic ratio**: What fraction of issues are semantic (not just syntax)
3. **Data layer exposure**: Does this module handle binary data, encodings, or serialization
4. **Dependency fan-in**: How many other modules depend on this one (gateway effect)
5. **Test coverage**: Modules with no tests are higher risk (can't verify behavior preserved)

The score combines these into a simple rating:
- **Low**: Mostly syntax issues, good test coverage, leaf module
- **Medium**: Mix of syntax and semantic issues, some test coverage
- **High**: Significant semantic issues, data layer involvement, or gateway module with low test coverage
- **Critical**: Heavy data layer involvement (SCADA/EBCDIC/serialization), no tests, many dependents

## Third-Party Dependency Check

The analysis script also checks all third-party imports against PyPI to determine:
- Whether a Py3-compatible version exists
- Whether the version currently pinned (if using requirements.txt/setup.py) supports Py3
- Whether the library has been abandoned (no releases in 2+ years)

This check uses `pip index versions <package>` or PyPI's JSON API and doesn't require
installing anything.

## Scripts Reference

### `scripts/analyze.py`
Main analysis script. Walks the codebase, parses each file, inventories all Py2 patterns.

Usage:
```
python3 scripts/analyze.py <codebase_path> \
    --output <output_dir> \
    --exclude "**/vendor/**" "**/test/**" \
    --target-versions 3.9 3.11 3.12 3.13
```

### `scripts/build_dep_graph.py`
Builds the dependency graph from the raw scan output. Performs topological sort, cluster
detection, and migration order computation.

Usage:
```
python3 scripts/build_dep_graph.py <output_dir>/raw-scan.json \
    --output <output_dir>
```

### `scripts/generate_report.py`
Generates the human-readable migration report from the analysis outputs.

Usage:
```
python3 scripts/generate_report.py <output_dir> \
    --project-name "My Project" \
    --output <output_dir>/migration-report.md
```

## Important Considerations

**This is an archaeology project.** The original developers are not available. Every
finding should be documented with enough context that someone unfamiliar with the codebase
can understand why a pattern is risky and what to do about it.

**The data layer is the highest-risk area.** This codebase handles data from IoT/SCADA
devices, CNC/machine automation, and potentially mainframe systems. Binary protocols,
mixed encodings, EBCDIC, and custom serialization formats are expected. The analysis
must be especially thorough in identifying data ingestion points and encoding patterns.

**Target version matters.** Python 3.12 removed `distutils` and 13 other stdlib modules.
Python 3.13 continued removals. The version compatibility matrix is not optional — it
directly affects migration scope and timeline. Always check
`references/stdlib-removals-by-version.md` for the authoritative list.

## Tree-sitter Enhanced Analysis

When tree-sitter is available (installed via `pip install tree-sitter tree-sitter-language-pack`),
this skill gains several capabilities:

**Better Python 2 coverage:** Files that fail `ast.parse()` are no longer limited to regex
detection. Tree-sitter extracts all the same patterns as `Py2PatternVisitor` via S-expression
queries, plus imports, definitions, and call relationships from the parseable portions.

**Polyglot awareness:** If the codebase contains non-Python files (Java, C, JavaScript, etc.),
the dependency graph includes them as nodes with a `language` property. This matters for
codebases with C extensions, Java backends, or mixed-language services.

**Call graph extraction:** In addition to module-level import dependencies, tree-sitter
enables function-level call graph extraction. This feeds into the behavioral-contract-extractor
and work-item-generator for atomic work decomposition.

**Language detection:** A two-pass detection system (file extension + `identify` library
for shebang detection, with `pygments` as fallback for ambiguous files) determines the
language of each file before parsing. Only detected languages have their tree-sitter
grammars loaded.

### Using the enhanced pipeline

```bash
# Standard analysis (uses tree-sitter automatically if available)
python3 scripts/analyze.py <codebase_path> --output <output_dir>

# Or use the universal analyzer directly for full polyglot analysis
python3 ../universal-code-graph/scripts/analyze_universal.py <codebase_path> \
    --output <output_dir> \
    [--languages python java c]
```

The standard `analyze.py` script detects tree-sitter availability and uses it as a
fallback. The `analyze_universal.py` script from the universal-code-graph skill provides
the full polyglot pipeline. Both produce compatible output.

### Depends Enrichment (Optional)

When multilang-depends is available (requires JRE), it provides additional file-level
dependency edges that validate and enrich the tree-sitter analysis. See the
universal-code-graph skill for details.

## Atomic Work Decomposition

The analysis outputs from this skill feed directly into the work-item-generator skill,
which decomposes findings into atomic, model-appropriate work items:

- **Haiku-tier** (~70% of findings): Mechanical pattern fixes — `has_key`, `xrange`,
  `print` statement, `except` syntax, stdlib renames. Each work item is self-contained
  with full context, expected result, and verification step.

- **Sonnet-tier** (~25%): Complex patterns — string/bytes mixing, metaclass changes,
  `struct.pack/unpack`, encoding issues. Need moderate reasoning.

- **Opus-tier** (~5%): Architectural decisions — C extensions, custom codecs, dynamic
  patterns, thread safety concerns. Need full-codebase reasoning.

The raw-scan.json output includes pattern classifications that drive this routing.
See the work-item-generator skill for details on the decomposition.

## Integration with New Skills

This skill's outputs now feed into an expanded ecosystem:

| Downstream skill | What it reads | Purpose |
|-----------------|---------------|---------|
| universal-code-graph | (upstream) | Provides tree-sitter pipeline this skill can delegate to |
| behavioral-contract-extractor | raw-scan.json, call-graph.json | Infers per-function behavioral contracts |
| work-item-generator | raw-scan.json, dependency-graph.json | Produces atomic work items with model routing |
| haiku-pattern-fixer | (via work items) | Executes mechanical fixes at scale |
| translation-verifier | (via contracts) | Verifies behavioral equivalence post-migration |
| modernization-advisor | (via contracts) | Suggests idiomatic target-language alternatives |
| migration-dashboard | dependency-graph.json, migration-state.json | Visual progress tracking |

## Model Tier

**Haiku (90%) + Sonnet (10%).** File scanning, pattern detection, and dependency graph assembly are mechanical — use Haiku. The executive summary narrative and risk assessment in the migration report benefit from Sonnet's reasoning, but this is a small fraction of the work. For Express workflow (small projects), the entire analysis runs on Haiku.

When decomposing as sub-agents: spawn Haiku sub-agents for per-file scanning, aggregate results, then use Sonnet for the final report synthesis only if the project is Standard or Full workflow.

## References

- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
- `ARCHITECTURE-universal-code-graph.md` — Full architecture for the universal code graph system
