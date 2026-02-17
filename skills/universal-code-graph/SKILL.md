---
name: universal-code-graph
description: >
  Build a language-agnostic dependency graph and code structure map for any codebase using
  tree-sitter parsing. Use this skill whenever you need to analyze a codebase that contains
  multiple programming languages, when Python's ast module fails on Python 2 syntax, when you
  need a unified dependency graph across Python/Java/C/C++/Rust/Go/Ruby/JavaScript/TypeScript,
  when you want function-level call graphs, or when you need to understand the structure of a
  codebase before migration. Also trigger when someone says "map this codebase," "build a
  dependency graph," "what languages are in this repo," "show me the call graph," "analyze
  this polyglot project," or "what does this codebase look like." This skill is the
  language-agnostic foundation — it produces the structural data that all other migration
  and analysis skills consume.
---

# Universal Code Graph

Parse any codebase — regardless of programming language — into a unified dependency graph,
call graph, and symbol map. Uses tree-sitter for language-agnostic parsing with per-language
query files that extract imports, definitions, and call relationships into a normalized format.

This skill replaces the ast-only analysis path with a two-pipeline approach: Python files
that parse successfully under `ast` still use the existing `Py2PatternVisitor` (battle-tested,
100+ patterns). Files that fail `ast.parse()` (Python 2 syntax) and all non-Python files go
through tree-sitter. Both pipelines produce identical output formats so all downstream skills
work without modification.

## Design Principles

**Don't replace, augment.** The existing ast pipeline stays for Python 3-compatible files.
Tree-sitter handles everything ast can't.

**Same output contracts.** The `raw-scan.json` format with its `results[].imports`,
`results[].findings`, and `results[].metrics` structure stays identical. New fields
(`language`, `symbols`, `calls`, `parser`) are additive.

**Language as configuration.** Adding support for a new language means writing three
`.scm` query files (imports, definitions, calls). No Python code changes.

**Detect then load.** Scan the codebase first to determine which languages are present.
Only load grammars for those languages. A 100-language grammar pack sits on disk but only
the needed parsers live in memory.

**One graph, all languages.** Every file — regardless of language — produces the same
normalized extraction format. There's no special "cross-language boundary" concept. Python
importing a C extension and Java calling a REST endpoint defined in Go are just edges with
different `language` properties.

## When to Use

- Before starting any migration (Python 2→3, Java→Kotlin, C→Rust, etc.)
- When analyzing a polyglot codebase with mixed languages
- When Python's `ast.parse()` fails on Python 2 syntax
- When you need a dependency graph that spans language boundaries
- When you need function-level call graphs (not just module-level imports)
- When stakeholders need to understand codebase structure before planning work
- As the first step before running any other analysis or migration skill

## Inputs

The user provides:

- **codebase_path**: Root directory of the codebase to analyze
- **output_dir** (optional): Where to write outputs. Defaults to `<codebase_path>/migration-analysis/`
- **exclude_patterns** (optional): Glob patterns for directories/files to exclude (e.g., `["**/vendor/**", "**/node_modules/**", "**/.git/**"]`)
- **languages** (optional): Restrict analysis to specific languages (e.g., `["python", "java"]`). If omitted, all detected languages are analyzed.
- **target_versions** (optional): For Python analysis, which Py3 versions to evaluate compatibility against. Defaults to `["3.9", "3.11", "3.12", "3.13"]`
- **enable_depends** (optional): Whether to run multilang-depends for additional dependency edges. Defaults to `true` if JRE is available.

## Outputs

All outputs go into the output directory:

| File | Format | Purpose |
|------|--------|---------|
| `raw-scan.json` | JSON | Per-file analysis: imports, findings, metrics, symbols, calls. Same schema as py2to3-codebase-analyzer plus new optional fields. |
| `dependency-graph.json` | JSON | Module dependency graph with language-aware nodes and edges. Compatible with existing `build_dep_graph.py` consumers. |
| `dependency-graph.html` | HTML | Interactive force-directed visualization with language color-coding. |
| `migration-order.json` | JSON | Topologically sorted conversion order with cluster groupings. Same schema as existing. |
| `call-graph.json` | JSON | Function/method-level call relationships across all languages. |
| `codebase-graph.graphml` | GraphML | Full graph exported for external tools (Gephi, NetworkX, etc.). |
| `language-summary.json` | JSON | Detected languages, file counts, line counts per language. |

## Workflow

### Step 1: Language Detection

Scan the codebase to determine which programming languages are present. This runs before
any parsing and drives grammar loading.

The detection is two-pass:

1. **Extension lookup** (covers 95%+ of files): `.py` → python, `.java` → java, `.rs` → rust, etc.
2. **identify library** (shebang detection): For extensionless scripts, uses `identify.tags_from_path()` to detect language from shebang lines.
3. **pygments fallback** (content analysis): For truly ambiguous files, `guess_lexer_for_filename()` analyzes file content. This is a last resort and runs on <1% of files.

Output: a set of languages present (e.g., `{"python", "java", "c"}`) and a per-file language mapping.

```bash
# The language scan is automatic — it happens as the first step of analyze_universal.py
# You can also run it standalone:
python3 scripts/language_detect.py <codebase_path> [--exclude <patterns>]
```

### Step 2: Grammar Loading

Load tree-sitter grammars only for the detected languages. Uses `tree-sitter-language-pack`
which provides pre-compiled grammars for 50+ languages with lazy loading via `get_parser()`.

Grammar loading is transparent — no user action needed. The log will show:
```
Languages detected: python, java, c
Loading grammars: python, java, c (3 of 50+ available)
```

### Step 3: File-by-File Analysis

For each source file in the codebase:

1. **Detect language** (from the per-file mapping built in Step 1).
2. **Choose pipeline:**
   - Python files: try `ast.parse()` first (richest analysis). On `SyntaxError`, fall back to tree-sitter.
   - All other files: tree-sitter directly.
3. **Extract:** imports, symbol definitions (functions, classes, methods), call relationships, basic metrics.
4. **For Python files:** Also run Python 2 pattern detection (either via `Py2PatternVisitor` for ast-parsed files, or via `Py2PatternDetectorTS` for tree-sitter-parsed files). Supplement with regex patterns.
5. **Produce:** A result dict in the standard `raw-scan.json` format, with `language`, `symbols`, `calls`, and `parser` fields added.

```bash
python3 scripts/analyze_universal.py <codebase_path> \
    --output <output_dir> \
    [--exclude "**/vendor/**" "**/test/**"] \
    [--languages python java c] \
    [--target-versions 3.9 3.11 3.12 3.13]
```

### Step 4: Depends Enrichment (Optional)

If multilang-depends is available (requires JRE), run it for additional dependency edge
detection. Depends catches file-level dependencies that tree-sitter queries may miss:
build system references, transitive imports, dynamic imports.

```bash
# Automatic if JRE is available. To force-disable:
python3 scripts/analyze_universal.py <codebase_path> --output <output_dir> --no-depends
```

The merge strategy: start with tree-sitter results (symbol-rich), add depends edges not
already present, flag depends-only edges for review (may indicate tree-sitter query gaps).

### Step 5: Graph Building

Build the unified dependency graph from all per-file results. This extends the existing
`build_dep_graph.py` logic with:

- Language-aware nodes (each node has a `language` property)
- Function-level call graph (in addition to module-level import graph)
- NetworkX representation for algorithmic analysis
- GraphML export for external visualization

The existing algorithms (Tarjan's SCC, topological sort, leaf/gateway/orphan detection)
work unchanged — they operate on graph topology, not language specifics.

```bash
python3 scripts/graph_builder.py <output_dir>/raw-scan.json --output <output_dir>
```

### Step 6: Generate Visualizations

Produce the interactive HTML visualization. The existing Canvas-based force-directed graph
template is enhanced with:

- Language color-coding (Python = blue, Java = red, C = gray, etc.)
- Node size by line count
- Edge thickness by number of import relationships
- Click to highlight all connections
- Hover for module details (language, metrics, risk score)

## Supported Languages

| Language | Grammar | Import queries | Definition queries | Call queries | Status |
|----------|---------|---------------|-------------------|-------------|--------|
| Python | python | `python_imports.scm` | `python_definitions.scm` | `python_calls.scm` | Full (+ Py2 pattern detection) |
| Java | java | `java_imports.scm` | `java_definitions.scm` | `java_calls.scm` | Full |
| JavaScript | javascript | `javascript_imports.scm` | `javascript_definitions.scm` | `javascript_calls.scm` | Full |
| TypeScript | typescript | (shares JS queries) | (shares JS queries) | (shares JS queries) | Full |
| C | c | `c_includes.scm` | `c_definitions.scm` | `c_calls.scm` | Full |
| C++ | cpp | `cpp_includes.scm` | `cpp_definitions.scm` | `cpp_calls.scm` | Full |
| Rust | rust | `rust_imports.scm` | `rust_definitions.scm` | `rust_calls.scm` | Full |
| Go | go | `go_imports.scm` | `go_definitions.scm` | `go_calls.scm` | Full |
| Ruby | ruby | `ruby_imports.scm` | `ruby_definitions.scm` | `ruby_calls.scm` | Full |

Additional languages can be added by writing three `.scm` query files. See
`references/tree-sitter-query-syntax.md` for the query language reference and
`references/adding-a-language.md` for a step-by-step guide.

## Query Files

Each language gets three S-expression query files in the `queries/` directory. These use
tree-sitter's pattern-matching syntax to extract structured data from concrete syntax trees.

**Import queries** (`*_imports.scm`): Extract what each file depends on.
```scheme
;; Example: python_imports.scm
(import_statement name: (dotted_name) @import.module)
(import_from_statement
  module_name: (dotted_name) @import.module
  name: (dotted_name) @import.name)
```

**Definition queries** (`*_definitions.scm`): Extract what each file provides.
```scheme
;; Example: python_definitions.scm
(function_definition name: (identifier) @definition.function)
(class_definition name: (identifier) @definition.class)
```

**Call queries** (`*_calls.scm`): Extract function/method invocations.
```scheme
;; Example: python_calls.scm
(call function: (identifier) @call.function)
(call function: (attribute
    object: (identifier) @call.object
    attribute: (identifier) @call.method))
```

All query results are normalized into identical JSON shapes regardless of source language.

## Python 2 Pattern Detection via Tree-sitter

When `ast.parse()` fails on a Python file (Python 2 syntax), the `Py2PatternDetectorTS`
class runs tree-sitter queries that match every pattern the existing `Py2PatternVisitor`
detects. This includes:

- Builtin function calls: `has_key`, `iteritems/itervalues/iterkeys`, `xrange`, `raw_input`, `unicode`, `apply`, `execfile`, `cmp`, `long`, `buffer`, `file`, `reload`, `reduce`
- Magic methods: `__cmp__`, `__nonzero__`, `__unicode__`, `__getslice__/__setslice__/__delslice__`, `__div__`, `__metaclass__`
- Data layer patterns: `struct.pack/unpack`, `pickle/cPickle`, `socket.recv`, `encode/decode`

The findings produce identical dicts (pattern, file, line, category, risk, description,
py3_fix) so risk scoring, reporting, and gate checking work unchanged. A `detection: "tree-sitter"`
field distinguishes these from ast-detected findings.

## Depends Integration

[multilang-depends](https://github.com/multilang-depends/depends) is an optional Java-based
tool that provides fast file-level dependency extraction for 10+ languages.

**When it helps:**
- Catches dynamic imports and build-system references that tree-sitter queries miss
- Validates tree-sitter edges (if both tools find the same edge, confidence is higher)
- Provides a quick first-pass that the tree-sitter analysis can enrich with symbol detail

**When it's not available:**
- No JRE installed → depends is skipped, tree-sitter works alone
- The skill logs "Depends not available (no JRE) — using tree-sitter only"
- No loss of core functionality; depends is enrichment, not requirement

**Installation:**
See `tools/README.md` for instructions on downloading `depends.jar` and ensuring JRE is available.

## Scripts Reference

### `scripts/analyze_universal.py`
Main entry point. Orchestrates language detection, grammar loading, file analysis,
depends enrichment, and output generation.

```
python3 scripts/analyze_universal.py <codebase_path> \
    --output <output_dir> \
    [--exclude <patterns>] \
    [--languages <lang1> <lang2>] \
    [--target-versions <ver1> <ver2>] \
    [--no-depends]
```

### `scripts/language_detect.py`
Two-pass language detection. Can be run standalone to survey a codebase.

```
python3 scripts/language_detect.py <codebase_path> [--exclude <patterns>]
```

### `scripts/ts_parser.py`
Tree-sitter wrapper with lazy grammar loading. Not called directly — used by
`analyze_universal.py` and `universal_extractor.py`.

### `scripts/universal_extractor.py`
Query-driven extraction engine. Runs `.scm` queries against parsed trees and
normalizes results into the standard format.

### `scripts/py2_patterns_ts.py`
Python 2 pattern detection via tree-sitter queries. Produces identical findings
to `Py2PatternVisitor` for files that can't be ast-parsed.

### `scripts/depends_runner.py`
Subprocess wrapper for multilang-depends. Handles JRE detection, output parsing,
and merge with tree-sitter results.

### `scripts/graph_builder.py`
Enhanced graph builder. Extends the existing `build_dep_graph.py` with language-aware
nodes, call graph construction, and NetworkX/GraphML export.

### `scripts/visualize.py`
HTML visualization generator using the enhanced template with language color-coding.

## Dependencies

```
# Core (required)
tree-sitter>=0.23.0
tree-sitter-language-pack>=0.2.0
identify>=2.6.0
networkx>=3.0

# Language detection fallback (optional)
pygments>=2.17.0

# Interactive visualization (optional)
pyvis>=0.3.0

# Depends integration (optional, requires JRE)
# Install separately: download depends.jar from https://github.com/multilang-depends/depends
```

## Scope and Chunking

This skill scans entire codebases. Output size scales with codebase size.

**Under 200 files:** Run on the full codebase. Summarize key findings in conversation.

**200–500 files:** Run full scan, but present only top-20 highest-impact modules and
graph statistics in conversation. Full data lives on disk.

**Over 500 files:** Run per top-level package/directory, then merge. The graph builder
accepts multiple `raw-scan.json` files and merges them:

```bash
python3 scripts/analyze_universal.py src/core/ --output analysis/core/
python3 scripts/analyze_universal.py src/services/ --output analysis/services/
python3 scripts/graph_builder.py --merge analysis/*/raw-scan.json --output analysis/
```

## Integration with Other Skills

This skill produces the foundational data that most other skills consume:

| Consumer skill | What it reads | How it uses it |
|---------------|---------------|---------------|
| py2to3-codebase-analyzer | raw-scan.json | Enhanced with tree-sitter results for Py2 files |
| py2to3-conversion-unit-planner | dependency-graph.json, migration-order.json | Language-aware wave planning |
| py2to3-behavioral-diff-generator | raw-scan.json | Structural data for targeted test generation |
| behavioral-contract-extractor | raw-scan.json, call-graph.json | Source data for contract inference |
| work-item-generator | raw-scan.json, dependency-graph.json | Findings → atomic work items |
| py2to3-dead-code-detector | call-graph.json | Graph-based reachability analysis |
| migration-dashboard | dependency-graph.json, language-summary.json | Visualization data |

## Model Tier

**Haiku** for the core pipeline (language detection, tree-sitter parsing, graph assembly). The universal code graph skill is primarily script execution — tree-sitter does the parsing, NetworkX does the graph math, the LLM orchestrates. No semantic reasoning about code contents is needed.

When used as infrastructure for other skills (e.g., behavioral-contract-extractor reads the call graph), the downstream skill's model tier applies, not this one's.

## References

- `references/tree-sitter-query-syntax.md` — S-expression query language reference
- `references/adding-a-language.md` — How to add support for a new language
- `references/supported-languages.md` — Full list of tree-sitter-language-pack grammars
- `ARCHITECTURE-universal-code-graph.md` — Detailed architecture with code sketches
