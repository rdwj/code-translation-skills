# Universal Code Graph: Architecture Plan

## The Problem

The py2to3 skill suite relies on Python's `ast` module for code analysis across 16 scripts. This creates two hard limitations. First, `ast` can't parse Python 2 syntax — files with `print "hello"` or `except Error, e:` throw `SyntaxError`, and the analyzer falls back to fragile regex patterns that miss function definitions, class hierarchies, and import relationships entirely. Second, `ast` is Python-only, so polyglot applications (Java services backing a Python frontend, C/C++ extensions, Rust modules, Ruby scripts) can't be analyzed at all.

The goal is to add a language-agnostic code graph layer alongside the existing `ast` pipeline. This is an additive change — `ast` remains available for Python 3 code where it works perfectly. The new layer handles everything else.

## Design Principles

**Don't replace, augment.** The existing `Py2PatternVisitor` with its 100+ pattern detections, risk scoring, and regex fallbacks is battle-tested. The new layer provides a universal parser that feeds the same downstream pipeline (dependency graph, SCC detection, topological sort, risk scoring, HTML visualization).

**Same output contracts.** The new layer must produce the same JSON shapes that `build_dep_graph.py` and `generate_report.py` already consume. This means the `raw-scan.json` format with its `results[].imports`, `results[].findings`, and `results[].metrics` structure stays identical.

**Language as configuration.** Adding support for a new language should require writing a query file (tree-sitter `.scm` patterns), not new Python code. The extraction engine is generic; the queries are language-specific.

**Detect then load.** We never load all grammars upfront. The language detector scans the codebase first and determines which languages are present. Only those grammars get loaded. Tree-sitter-language-pack already supports this — `get_parser("python")` lazy-loads only the Python grammar.

**One graph, all languages.** There's no special "cross-language boundary" concept. Every file in the repo — regardless of language — produces the same normalized extraction format. Imports, calls, and definitions all become nodes and edges in a single unified graph. A Python file importing a C extension and a Java file calling a REST endpoint defined in Go are just edges with different `language` properties on each side. The graph doesn't care about language boundaries; it cares about dependencies.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     Codebase Input                          │
│         (Python 2, Python 3, Java, C, Rust, Go, ...)       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Language Detection (two-pass)                   │
│                                                             │
│   Pass 1: identify (extension + shebang, zero deps)        │
│   Pass 2: pygments.guess_lexer() for ambiguous files       │
│                                                             │
│   Output: set of languages present → load only those        │
│           grammars from tree-sitter-language-pack            │
└────────┬──────────────────────────┬─────────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────────┐  ┌──────────────────────────────────┐
│   ast Pipeline       │  │   tree-sitter Pipeline           │
│   (Python files      │  │   (Python 2 files, Java, C,     │
│    that parse OK)    │  │    C++, Rust, Go, Ruby, etc.)    │
│                      │  │                                  │
│   Py2PatternVisitor  │  │   UniversalExtractor             │
│   (existing code)    │  │   + language .scm queries        │
└────────┬─────────────┘  └──────────┬───────────────────────┘
         │                           │
         ▼                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Unified Extraction Format                       │
│                                                             │
│   {                                                         │
│     "file": "path/to/file.py",                             │
│     "language": "python",                                  │
│     "imports": [...],          ← same shape as today        │
│     "findings": [...],         ← same shape as today        │
│     "metrics": {...},          ← same shape as today        │
│     "symbols": [...],          ← NEW: functions, classes    │
│     "calls": [...],            ← NEW: call relationships   │
│   }                                                         │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────────┐  ┌──────────────────────────────────┐
│  Depends (Java)       │  │  Graph Builder                   │
│  Fast first-pass      │  │  (build_dep_graph.py, enhanced)  │
│  dependency extract   │  │                                  │
│                       │  │  - Module dependency graph        │
│  Validates & enriches │  │  - Call graph                     │
│  tree-sitter edges    │  │  - Symbol graph                   │
│  Catches edges TS     │  │                                  │
│  queries may miss     │  │  Tarjan SCC, topo sort           │
└───────────┬──────────┘  │  NetworkX representation          │
            │              └──────────┬───────────────────────┘
            └────────────┬────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Output Layer                              │
│                                                             │
│  raw-scan.json          (same schema + new optional fields) │
│  dependency-graph.json  (same schema, language-aware)       │
│  dependency-graph.html  (enhanced, language color-coded)    │
│  migration-order.json   (same schema, unchanged)           │
│  call-graph.json        (NEW)                              │
│  codebase-graph.graphml (NEW, NetworkX export)             │
│  migration-state.json   (NEW, for dashboard)               │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│               Migration Dashboard (HTML)                     │
│                                                             │
│  ┌─────────────────────┐  ┌─────────────────────────────┐  │
│  │   Source Graph       │  │   Target Graph               │  │
│  │   (old codebase)     │  │   (new codebase, building)  │  │
│  │                      │  │                              │  │
│  │   Color-coded:       │  │   Color-coded:               │  │
│  │   ● not started      │  │   ● migrated                 │  │
│  │   ● in progress      │  │   ● tested                   │  │
│  │   ● migrated         │  │   ● evaluated                │  │
│  │   ● blocked          │  │   ● deployed                 │  │
│  └─────────────────────┘  └─────────────────────────────┘  │
│                                                             │
│  Status bar: 45/120 modules migrated | 12 clusters done    │
│  Risk heatmap | Blockers list | Timeline estimate          │
└─────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Language Detector (`language_detect.py`)

Two-pass detection that only loads grammars we actually need.

```python
# Dependencies:
#   pip install identify pygments

from identify import identify
from pathlib import Path

# Extension → tree-sitter grammar name (fast path)
EXTENSION_MAP = {
    ".py":    "python",
    ".pyw":   "python",
    ".java":  "java",
    ".js":    "javascript",
    ".mjs":   "javascript",
    ".ts":    "typescript",
    ".tsx":   "typescript",
    ".go":    "go",
    ".rb":    "ruby",
    ".c":     "c",
    ".cpp":   "cpp",
    ".cc":    "cpp",
    ".cxx":   "cpp",
    ".h":     "c",         # Ambiguous — could be C or C++
    ".hpp":   "cpp",
    ".cs":    "c_sharp",
    ".rs":    "rust",
    ".php":   "php",
    ".kt":    "kotlin",
    ".kts":   "kotlin",
    ".scala": "scala",
    ".swift": "swift",
    ".m":     "objc",
    ".mm":    "objc",
    ".lua":   "lua",
    ".pl":    "perl",
    ".pm":    "perl",
    ".r":     "r",
    ".R":     "r",
    ".sh":    "bash",
    ".bash":  "bash",
    ".zsh":   "bash",
    ".zig":   "zig",
    ".dart":  "dart",
    ".ex":    "elixir",
    ".exs":   "elixir",
    ".erl":   "erlang",
    ".hs":    "haskell",
    ".ml":    "ocaml",
    ".clj":   "clojure",
}

def detect_language(filepath: str) -> str | None:
    """Detect the programming language of a file.

    Pass 1: Extension lookup (covers 95%+ of cases).
    Pass 2: identify library (shebang detection for extensionless scripts).
    Pass 3: pygments guess_lexer_for_filename (content-based, last resort).

    Returns the tree-sitter grammar name, or None if unsupported.
    """
    ext = Path(filepath).suffix.lower()

    # Pass 1: Extension
    if ext in EXTENSION_MAP:
        return EXTENSION_MAP[ext]

    # Pass 2: identify (shebang + file type tags)
    try:
        tags = identify.tags_from_path(filepath)
        for tag in tags:
            if tag in EXTENSION_MAP.values():
                return tag
            # Map identify tags to our grammar names
            tag_map = {"python3": "python", "python2": "python", "bash": "bash"}
            if tag in tag_map:
                return tag_map[tag]
    except (ValueError, FileNotFoundError):
        pass

    # Pass 3: pygments content analysis (only for ambiguous files)
    try:
        from pygments.lexers import guess_lexer_for_filename
        with open(filepath, "r", errors="replace") as f:
            sample = f.read(4096)
        lexer = guess_lexer_for_filename(filepath, sample)
        # Map pygments lexer names to tree-sitter grammar names
        pygments_map = {
            "Python": "python", "Java": "java", "JavaScript": "javascript",
            "TypeScript": "typescript", "Go": "go", "Ruby": "ruby",
            "C": "c", "C++": "cpp", "Rust": "rust", "PHP": "php",
        }
        return pygments_map.get(lexer.name)
    except Exception:
        pass

    return None


def scan_codebase_languages(root: str, exclude_patterns: list[str]) -> set[str]:
    """Scan a codebase and return the set of languages present.

    This runs BEFORE any parsing. Only the detected languages
    will have their tree-sitter grammars loaded.
    """
    languages = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            filepath = os.path.join(dirpath, fname)
            lang = detect_language(filepath)
            if lang:
                languages.add(lang)
    return languages
```

The key insight: `scan_codebase_languages()` runs first, returns something like `{"python", "java", "c"}`, and only those three grammars get loaded. A 100-language grammar pack sits on disk but only 3 parsers live in memory.

### 2. Tree-sitter Parser (`ts_parser.py`)

Thin wrapper with lazy grammar loading driven by the language scan.

```python
from tree_sitter_language_pack import get_language, get_parser

class TreeSitterParser:
    """Parse source files into tree-sitter syntax trees.

    Grammars are loaded lazily — only when first requested.
    Call preload() with the output of scan_codebase_languages()
    to warm the cache at startup.
    """

    def __init__(self):
        self._parsers: dict[str, Parser] = {}
        self._languages: dict[str, Language] = {}

    def preload(self, languages: set[str]):
        """Pre-load grammars for all detected languages."""
        for lang in languages:
            try:
                self._languages[lang] = get_language(lang)
                self._parsers[lang] = get_parser(lang)
            except Exception as e:
                print(f"Warning: no tree-sitter grammar for '{lang}': {e}")

    def parse(self, source: bytes, language: str) -> Tree:
        if language not in self._parsers:
            self._parsers[language] = get_parser(language)
        return self._parsers[language].parse(source)

    def query(self, language: str, query_string: str) -> Query:
        if language not in self._languages:
            self._languages[language] = get_language(language)
        return self._languages[language].query(query_string)

    @property
    def loaded_languages(self) -> list[str]:
        return sorted(self._parsers.keys())
```

**Python 2 handling:** The tree-sitter `python` grammar is designed for Python 3 but is more forgiving than `ast.parse()`. It produces a concrete syntax tree (CST) even for Python 2 constructs — tree-sitter does error recovery, parsing as much as it can and marking unparseable regions as `ERROR` nodes while continuing with the rest of the file. This means we get imports, function definitions, and class definitions from the parseable portions, whereas `ast.parse()` gives us nothing at all on failure.

For the Python 2 grammar question: we plan to maintain grammar support for every language we target. For Python 2 specifically, the Python 3 grammar with tree-sitter's error recovery handles most constructs well. If we find coverage below ~90% on real Py2 codebases, we'll fork the grammar. For C, C++, Java, Rust, Ruby, Go — tree-sitter has mature, actively-maintained grammars for all of these already.

### 3. Query Files (`queries/*.scm`)

Each language gets a set of S-expression query files. Tree-sitter queries use pattern-matching over the concrete syntax tree. Three query types per language:

**`queries/python_imports.scm`** — Import extraction:
```scheme
;; import foo
(import_statement
  name: (dotted_name) @import.module)

;; from foo import bar
(import_from_statement
  module_name: (dotted_name) @import.module
  name: (dotted_name) @import.name)

;; from . import foo (relative import)
(import_from_statement
  module_name: (relative_import) @import.relative)
```

**`queries/python_definitions.scm`** — Symbol extraction:
```scheme
(function_definition
  name: (identifier) @definition.function
  parameters: (parameters) @definition.params
  return_type: (type)? @definition.return_type)

(class_definition
  name: (identifier) @definition.class
  superclasses: (argument_list)? @definition.bases)

(class_definition
  body: (block
    (function_definition
      name: (identifier) @definition.method)))
```

**`queries/python_calls.scm`** — Call extraction:
```scheme
(call function: (identifier) @call.function)

(call function: (attribute
    object: (identifier) @call.object
    attribute: (identifier) @call.method))
```

**`queries/java_imports.scm`:**
```scheme
(import_declaration (scoped_identifier) @import.module)
(package_declaration (scoped_identifier) @package.name)
```

**`queries/java_definitions.scm`:**
```scheme
(class_declaration
  name: (identifier) @definition.class
  interfaces: (super_interfaces)? @definition.implements
  superclass: (superclass)? @definition.extends)

(method_declaration
  name: (identifier) @definition.method
  parameters: (formal_parameters) @definition.params
  type: (_) @definition.return_type)

(interface_declaration
  name: (identifier) @definition.interface)
```

**`queries/javascript_imports.scm`:**
```scheme
(import_statement source: (string) @import.module)

(call_expression
  function: (identifier) @_require (#eq? @_require "require")
  arguments: (arguments (string) @import.module))
```

**`queries/c_includes.scm`:**
```scheme
(preproc_include path: (string_literal) @import.module)
(preproc_include path: (system_lib_string) @import.system)
```

**`queries/rust_imports.scm`:**
```scheme
(use_declaration argument: (scoped_identifier) @import.module)
(use_declaration argument: (use_wildcard) @import.wildcard)
(extern_crate_declaration name: (identifier) @import.crate)
```

The pattern: each language needs `*_imports.scm`, `*_definitions.scm`, and `*_calls.scm`. Adding C++, Ruby, Go, Kotlin, etc. means writing these three files per language. No Python code changes.

### 4. Depends Integration (`depends_runner.py`)

[multilang-depends](https://github.com/multilang-depends/depends) is a Java-based dependency extraction tool supporting Python, Java, C/C++, JavaScript, TypeScript, Ruby, Go, C#, and more. We use it as a fast first-pass to get file-level dependency edges, then enrich with tree-sitter for symbol-level detail.

```python
import subprocess
import json

class DependsRunner:
    """Run multilang-depends as a subprocess for fast dependency extraction.

    Depends provides file-level dependency edges across 10+ languages.
    Tree-sitter provides symbol-level detail (functions, classes, calls).
    The two complement each other.
    """

    def __init__(self, depends_jar: str = None):
        self.depends_jar = depends_jar or self._find_depends()

    def _find_depends(self):
        """Locate the depends.jar — either on PATH or in tools/ directory."""
        # Check PATH
        result = subprocess.run(["which", "depends"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
        # Check local tools dir
        local = os.path.join(os.path.dirname(__file__), "..", "tools", "depends.jar")
        if os.path.exists(local):
            return local
        return None

    def is_available(self) -> bool:
        """Check if depends is installed and callable."""
        if not self.depends_jar:
            return False
        try:
            subprocess.run(
                ["java", "-jar", self.depends_jar, "--help"],
                capture_output=True, timeout=10
            )
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            return False

    def extract_dependencies(
        self,
        codebase_root: str,
        language: str,
        output_dir: str,
    ) -> dict | None:
        """Run depends and return parsed JSON dependency data.

        Args:
            codebase_root: Path to analyze
            language: One of: python, java, cpp, javascript, ruby, go, csharp, php
            output_dir: Where to write depends output

        Returns:
            Parsed JSON with file-level dependency edges, or None if unavailable.
        """
        if not self.is_available():
            return None

        # Depends language names differ slightly from tree-sitter
        depends_lang_map = {
            "python": "python",
            "java": "java",
            "c": "cpp",     # Depends uses 'cpp' for both C and C++
            "cpp": "cpp",
            "javascript": "javascript",
            "typescript": "javascript",  # Depends treats TS as JS
            "ruby": "ruby",
            "go": "go",
            "c_sharp": "csharp",
            "php": "php",
        }

        dep_lang = depends_lang_map.get(language)
        if not dep_lang:
            return None

        output_file = os.path.join(output_dir, f"depends-{language}.json")
        cmd = [
            "java", "-jar", self.depends_jar,
            dep_lang, codebase_root,
            "--output", output_file,
            "--format", "json",
        ]

        try:
            subprocess.run(cmd, capture_output=True, timeout=300, check=True)
            with open(output_file) as f:
                return json.load(f)
        except (subprocess.SubprocessError, json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Warning: depends extraction failed for {language}: {e}")
            return None

    def merge_with_treesitter(
        self,
        depends_edges: dict,
        ts_results: list[dict],
    ) -> list[dict]:
        """Merge depends' file-level edges with tree-sitter's symbol-level data.

        Depends catches dependency edges that tree-sitter queries may miss
        (e.g., implicit dependencies, build system references, transitive imports).
        Tree-sitter provides the rich per-symbol data that depends lacks.

        The merge strategy:
        1. Start with tree-sitter results (symbol-rich)
        2. For each depends edge not already present, add it as an import
           with a "source": "depends" marker
        3. Validate: if depends found an edge and tree-sitter didn't,
           flag it for review (may indicate a query gap)
        """
        # Build set of edges already found by tree-sitter
        ts_edges = set()
        for result in ts_results:
            src = result["file"]
            for imp in result.get("imports", []):
                ts_edges.add((src, imp["module"]))

        # Add depends-only edges
        depends_only_count = 0
        for edge in depends_edges.get("dependencies", []):
            src = edge.get("src", "")
            dst = edge.get("dest", "")
            if (src, dst) not in ts_edges:
                # Find the source file's result and inject the import
                for result in ts_results:
                    if result["file"] == src:
                        result["imports"].append({
                            "module": dst,
                            "names": [],
                            "line": 0,
                            "is_from_import": False,
                            "file": src,
                            "source": "depends",
                        })
                        depends_only_count += 1
                        break

        if depends_only_count:
            print(f"  Depends found {depends_only_count} edges tree-sitter missed")

        return ts_results
```

The two-tool approach: depends is fast and catches file-level dependencies that tree-sitter queries might miss (build system references, transitive imports, dynamic imports). Tree-sitter provides the rich symbol-level data (function signatures, class hierarchies, call relationships) that depends doesn't have. When both are available, we get the most complete graph. When depends isn't installed (no JRE), tree-sitter alone still works fine.

### 5. Universal Extractor (`universal_extractor.py`)

Runs tree-sitter queries against a parsed tree and normalizes results.

```python
class UniversalExtractor:
    """Extract code relationships from any language using tree-sitter."""

    def __init__(self, ts_parser: TreeSitterParser, queries_dir: str):
        self.parser = ts_parser
        self.queries_dir = queries_dir
        self._query_cache: dict[str, Query] = {}

    def extract(self, filepath: str, source: bytes, language: str) -> dict:
        tree = self.parser.parse(source, language)

        imports  = self._run_query(tree, language, "imports")
        defs     = self._run_query(tree, language, "definitions")
        calls    = self._run_query(tree, language, "calls")

        return {
            "file": filepath,
            "language": language,
            "parse_success": not tree.root_node.has_error,
            "imports": self._normalize_imports(imports, filepath, language),
            "symbols": self._normalize_definitions(defs, language),
            "calls": self._normalize_calls(calls, language),
            "metrics": self._compute_metrics(tree, source, language),
            "findings": [],
            "error": None,
        }

    def _run_query(self, tree, language, query_type):
        key = f"{language}_{query_type}"
        if key not in self._query_cache:
            scm_path = os.path.join(
                self.queries_dir, f"{language}_{query_type}.scm"
            )
            if not os.path.exists(scm_path):
                return []
            with open(scm_path) as f:
                self._query_cache[key] = self.parser.query(language, f.read())
        return self._query_cache[key].matches(tree.root_node)

    def _normalize_imports(self, matches, filepath, language) -> list[dict]:
        """Convert query matches into the standard import dict format.

        Output shape matches Py2PatternVisitor._add_import():
        {"module": str, "names": list, "line": int,
         "is_from_import": bool, "file": str}
        """
        ...

    def _normalize_definitions(self, matches, language) -> list[dict]:
        """Extract symbol definitions.
        {"name": str, "type": "class"|"function"|"method"|"interface",
         "line": int, "end_line": int, "params": list, "bases": list}
        """
        ...

    def _normalize_calls(self, matches, language) -> list[dict]:
        """Extract call relationships.
        {"caller_context": str, "callee": str, "line": int,
         "type": "function"|"method"|"constructor"}
        """
        ...

    def _compute_metrics(self, tree, source: bytes, language: str) -> dict:
        """Compute basic metrics from the syntax tree."""
        lines = source.count(b"\n") + 1

        # Node type names vary by grammar — map to generic types
        func_types = {
            "python": "function_definition",
            "java": "method_declaration",
            "javascript": "function_declaration",
            "typescript": "function_declaration",
            "c": "function_definition",
            "cpp": "function_definition",
            "rust": "function_item",
            "go": "function_declaration",
            "ruby": "method",
        }
        class_types = {
            "python": "class_definition",
            "java": "class_declaration",
            "javascript": "class_declaration",
            "typescript": "class_declaration",
            "c": "struct_specifier",
            "cpp": "class_specifier",
            "rust": "struct_item",
            "go": "type_declaration",
            "ruby": "class",
        }

        func_type = func_types.get(language, "function_definition")
        class_type = class_types.get(language, "class_definition")

        return {
            "lines": lines,
            "functions": self._count_node_type(tree.root_node, func_type),
            "classes": self._count_node_type(tree.root_node, class_type),
        }

    def _count_node_type(self, node, type_name: str) -> int:
        count = 1 if node.type == type_name else 0
        for child in node.children:
            count += self._count_node_type(child, type_name)
        return count
```

### 6. Python 2 Pattern Detector (`py2_patterns_ts.py`)

Tree-sitter queries for every Python 2 pattern currently detected by `Py2PatternVisitor`. Produces identical `findings` dicts so risk scoring and reporting work unchanged.

```python
class Py2PatternDetectorTS:
    """Detect Python 2 patterns using tree-sitter.

    Produces the same findings format as Py2PatternVisitor.
    """

    PATTERN_QUERIES = {
        # Builtin function calls
        "has_key":         '(call function: (attribute attribute: (identifier) @m (#eq? @m "has_key")))',
        "iteritems":       '(call function: (attribute attribute: (identifier) @m (#match? @m "^iter(items|values|keys)$")))',
        "xrange":          '(call function: (identifier) @f (#eq? @f "xrange"))',
        "raw_input":       '(call function: (identifier) @f (#eq? @f "raw_input"))',
        "unicode_builtin": '(call function: (identifier) @f (#eq? @f "unicode"))',
        "apply_builtin":   '(call function: (identifier) @f (#eq? @f "apply"))',
        "execfile_builtin":'(call function: (identifier) @f (#eq? @f "execfile"))',
        "cmp_builtin":     '(call function: (identifier) @f (#eq? @f "cmp"))',
        "long_builtin":    '(call function: (identifier) @f (#eq? @f "long"))',
        "buffer_builtin":  '(call function: (identifier) @f (#eq? @f "buffer"))',
        "file_builtin":    '(call function: (identifier) @f (#eq? @f "file"))',
        "reload_builtin":  '(call function: (identifier) @f (#eq? @f "reload"))',
        "reduce_builtin":  '(call function: (identifier) @f (#eq? @f "reduce"))',

        # Magic methods
        "cmp_method":      '(function_definition name: (identifier) @n (#eq? @n "__cmp__"))',
        "nonzero_method":  '(function_definition name: (identifier) @n (#eq? @n "__nonzero__"))',
        "unicode_method":  '(function_definition name: (identifier) @n (#eq? @n "__unicode__"))',
        "getslice_method": '(function_definition name: (identifier) @n (#match? @n "^__(get|set|del)slice__$"))',
        "div_method":      '(function_definition name: (identifier) @n (#eq? @n "__div__"))',
        "metaclass_attribute": '(assignment left: (identifier) @n (#eq? @n "__metaclass__"))',

        # Data layer
        "struct_usage":    '(call function: (attribute object: (identifier) @obj (#eq? @obj "struct") attribute: (identifier) @m (#match? @m "^(pack|unpack|pack_into|unpack_from)$")))',
        "pickle_usage":    '(call function: (attribute object: (identifier) @obj (#match? @obj "^(pickle|cPickle)$") attribute: (identifier) @m (#match? @m "^(load|loads|dump|dumps)$")))',
        "socket_recv":     '(call function: (attribute attribute: (identifier) @m (#eq? @m "recv")))',

        # Encode/decode
        "encode_decode":   '(call function: (attribute attribute: (identifier) @m (#match? @m "^(encode|decode)$")))',
    }

    def detect(self, tree, language_obj, source_lines, filepath) -> list[dict]:
        """Run all pattern queries and return findings."""
        findings = []
        for pattern_key, query_str in self.PATTERN_QUERIES.items():
            info = AST_PATTERNS[pattern_key]
            query = language_obj.query(query_str)
            for match_id, captures in query.matches(tree.root_node):
                for capture_name, nodes in captures.items():
                    for node in (nodes if isinstance(nodes, list) else [nodes]):
                        line = node.start_point[0]
                        findings.append({
                            "pattern": pattern_key,
                            "file": filepath,
                            "line": line + 1,
                            "category": info["category"],
                            "risk": info["risk"],
                            "description": info["description"],
                            "py3_fix": info["py3_fix"],
                            "source": source_lines[line].rstrip() if line < len(source_lines) else "",
                            "detection": "tree-sitter",
                        })
        return findings
```

### 7. Enhanced Analyzer (`analyze_universal.py`)

Orchestrates both pipelines. For Python files: try `ast` first, fall back to tree-sitter. For everything else: tree-sitter directly. Optionally merge with depends.

```python
def analyze_codebase_universal(
    codebase_root: str,
    output_dir: str,
    exclude_patterns: list[str],
    target_versions: list[str] = None,
):
    """Analyze a codebase using all available tools.

    1. Scan for languages present
    2. Preload only those tree-sitter grammars
    3. Analyze each file with best available parser
    4. Optionally run depends for additional dependency edges
    5. Write unified output in standard format
    """
    # Step 1: Discover languages
    print("Scanning codebase for languages...")
    languages = scan_codebase_languages(codebase_root, exclude_patterns)
    print(f"Languages detected: {', '.join(sorted(languages))}")

    # Step 2: Initialize parsers
    ts_parser = TreeSitterParser()
    ts_parser.preload(languages)
    extractor = UniversalExtractor(ts_parser, queries_dir=QUERIES_DIR)

    # Step 3: Walk and analyze each file
    all_results = []
    for filepath in walk_codebase_universal(codebase_root, exclude_patterns):
        language = detect_language(filepath)
        if not language:
            continue
        result = analyze_file_universal(
            filepath, codebase_root, language, ts_parser, extractor
        )
        result["risk_assessment"] = compute_risk_score(result)
        all_results.append(result)

    # Step 4: Depends enrichment (if available)
    depends = DependsRunner()
    if depends.is_available():
        print("Running depends for dependency validation...")
        for lang in languages:
            dep_data = depends.extract_dependencies(codebase_root, lang, output_dir)
            if dep_data:
                all_results = depends.merge_with_treesitter(dep_data, all_results)
    else:
        print("Depends not available (no JRE) — using tree-sitter only")

    # Step 5: Write outputs (same format as existing analyze.py)
    write_raw_scan(all_results, codebase_root, output_dir)
    write_inventory(all_results, output_dir)
    if target_versions:
        write_version_matrix(all_results, target_versions, output_dir)


def analyze_file_universal(filepath, codebase_root, language, ts_parser, extractor):
    """Analyze a single file using the best available parser."""
    rel_path = os.path.relpath(filepath, codebase_root)

    with open(filepath, "rb") as f:
        source_bytes = f.read()
    source_text = source_bytes.decode("utf-8", errors="replace")
    source_lines = source_text.split("\n")

    if language == "python":
        # Try ast first (richest analysis for Python 3-compatible code)
        try:
            tree = ast.parse(source_text, filename=filepath)
            visitor = Py2PatternVisitor(source_lines, rel_path)
            visitor.visit(tree)

            result = {
                "file": rel_path,
                "language": "python",
                "findings": visitor.findings,
                "imports": visitor.imports,
                "metrics": visitor.metrics,
                "symbols": [],  # TODO: extract from ast too
                "calls": [],    # TODO: extract from ast too
                "parse_success": True,
                "parser": "ast",
            }

            # Supplement with regex
            regex_findings = analyze_file_regex(rel_path, source_text)
            ast_lines = {(f["pattern"], f["line"]) for f in visitor.findings}
            for rf in regex_findings:
                if (rf["pattern"], rf["line"]) not in ast_lines:
                    result["findings"].append(rf)
            return result

        except SyntaxError:
            pass  # Fall through to tree-sitter

    # Tree-sitter path
    ts_result = extractor.extract(rel_path, source_bytes, language)

    if language == "python":
        # Run Py2 pattern detection
        tree = ts_parser.parse(source_bytes, "python")
        lang_obj = get_language("python")
        py2_detector = Py2PatternDetectorTS()
        ts_result["findings"] = py2_detector.detect(tree, lang_obj, source_lines, rel_path)

        # Supplement with regex
        regex_findings = analyze_file_regex(rel_path, source_text)
        existing = {(f["pattern"], f["line"]) for f in ts_result["findings"]}
        for rf in regex_findings:
            if (rf["pattern"], rf["line"]) not in existing:
                ts_result["findings"].append(rf)
        ts_result["parser"] = "tree-sitter+regex"
    else:
        ts_result["parser"] = "tree-sitter"

    return ts_result
```

### 8. Migration Dashboard (`dashboard/`)

A local HTML application (single self-contained file or locally served) that provides real-time migration status tracking. This is a natural consumer of the graph data the skill produces.

**Core concept:** Side-by-side force-directed graphs. Left pane shows the source codebase (old). Right pane shows the target codebase (new, as it's being built). Nodes are color-coded by migration status.

**Data source:** `migration-state.json` — a file that tracks per-module status, updated by the migration skills as they run.

```json
{
  "project": "acme-scada-system",
  "source_scan": "migration-analysis/raw-scan.json",
  "target_scan": "migration-analysis/target-raw-scan.json",
  "dependency_graph": "migration-analysis/dependency-graph.json",
  "modules": {
    "src.core.config": {
      "status": "migrated",
      "migrated_at": "2026-02-10T14:30:00Z",
      "tested": true,
      "test_pass": true,
      "evaluated": true,
      "deployed": false,
      "notes": "Converted by automated-converter, no manual fixes needed",
      "converter_skill": "py2to3-automated-converter",
      "risk_before": "low",
      "risk_after": "none"
    },
    "src.io.modbus_reader": {
      "status": "in_progress",
      "blocked_by": ["src.io.serial_protocol"],
      "risk_before": "critical",
      "notes": "Heavy struct.pack/unpack usage, EBCDIC codecs"
    },
    "src.io.serial_protocol": {
      "status": "not_started",
      "risk_before": "critical"
    }
  }
}
```

**Status color scheme:**

| Status | Color | Meaning |
|--------|-------|---------|
| `not_started` | Gray | Not yet migrated |
| `in_progress` | Yellow | Migration underway |
| `blocked` | Red | Waiting on dependency |
| `migrated` | Blue | Code converted, not yet tested |
| `tested` | Green | Tests pass |
| `evaluated` | Dark green | Reviewed and approved |
| `deployed` | Purple | In production |

**Dashboard features:**

- Left/right synchronized graphs — clicking a node on the left highlights it and its counterpart on the right
- Status filter toggles — show/hide by status
- Progress bar — "45/120 modules migrated"
- Cluster view — collapse tightly-coupled modules into single super-nodes
- Risk heatmap overlay — node size or border intensity by risk score
- Blockers list — modules that block the most downstream work
- Timeline — estimated completion based on velocity (modules migrated per week)
- Detail panel — click any module to see its full analysis, findings, and migration history

The dashboard reads the graph JSON files and `migration-state.json` directly from disk (via `file://` protocol or a tiny local HTTP server). No backend needed — it's all client-side JavaScript reading JSON files.

The existing `dependency-graph-template.html` (Canvas-based force-directed graph) is the starting point. We enhance it with the split-pane layout and status color-coding. The graph rendering code (physics simulation, drag/zoom, hover tooltips) is already written and working — we add the status dimension.

### 9. Behavioral Analysis & Verification (`behavioral_analyzer.py`)

There are three levels at which code can be migrated:

**Level 1 — Syntactic translation.** Mechanical conversion: `print "hello"` → `print("hello")`. Safe, automatable, produces working code. This is what 2to3 and futurize do. It's what our existing automated-converter does.

**Level 2 — Structural translation.** The class hierarchy, module layout, and patterns get reorganized to fit the target language's idioms. The shape changes but the behavior is preserved. This is what most of our skills do when they work together.

**Level 3 — Functional/behavioral translation.** Understand *what* the code does — "reads a CSV, validates rows, sends an email per row" — and rewrite that behavior idiomatically in the target language. A 40-line Python 2 function becomes 8 lines of Rust using `serde` and `lettre`. The highest-quality outcome, but also the highest risk of subtle behavioral drift.

Most migration tools stop at Level 1. Our skill suite currently operates at Levels 1-2. Level 3 is where the real quality gains live — and where the real risks hide.

**The two-track model:**

The primary migration path remains structural (safe). The behavioral analysis runs as a parallel track that produces two things: **verification** (does the translated code satisfy the same behavioral contract as the original?) and **opportunities** (where could the target language do this simpler, better, or more idiomatically?).

```
┌──────────────────────┐     ┌──────────────────────┐
│  Track A: Structural  │     │  Track B: Behavioral  │
│  (tree-sitter + ast)  │     │  (contract extraction) │
│                        │     │                        │
│  Parse → extract →     │     │  For each function:    │
│  translate → generate  │     │  - What does it read?  │
│                        │     │  - What does it write?  │
│  Preserves shape,      │     │  - What errors arise?  │
│  safe, mechanical      │     │  - What side effects?  │
└───────────┬────────────┘     └───────────┬────────────┘
            │                              │
            ▼                              ▼
┌─────────────────────────────────────────────────────┐
│               Verification Layer                     │
│                                                     │
│  - Generate test cases from behavioral contracts    │
│  - Run against source → establish baseline          │
│  - Run against target → verify equivalence          │
│  - Surface discrepancies in dashboard               │
│  - Flag modernization opportunities                 │
└─────────────────────────────────────────────────────┘
```

**Behavioral contracts.** For each function or method, the analyzer produces a contract that captures observable behavior without requiring understanding of implementation:

```json
{
  "function": "src.io.csv_mailer.send_csv_emails",
  "language": "python",
  "contract": {
    "inputs": {
      "parameters": ["csv_path: str", "smtp_host: str", "port: int = 587"],
      "reads": ["filesystem:csv_path", "network:smtp_host:port"],
      "env_vars": ["SMTP_USER", "SMTP_PASS"]
    },
    "outputs": {
      "returns": "int",
      "return_semantics": "count of successfully sent emails",
      "writes": ["network:smtp (sends emails)"],
      "mutations": []
    },
    "side_effects": [
      "logging.info per email sent",
      "logging.error on send failure"
    ],
    "error_conditions": [
      {"exception": "FileNotFoundError", "when": "csv_path does not exist"},
      {"exception": "smtplib.SMTPAuthenticationError", "when": "bad credentials"},
      {"exception": "csv.Error", "when": "malformed CSV"}
    ],
    "implicit_behaviors": [
      "relies on dict ordering (Python 3.7+)",
      "assumes UTF-8 encoding for CSV",
      "retries SMTP connection 3 times (hidden in _connect helper)"
    ],
    "complexity": "low",
    "pure": false
  },
  "modernization_opportunities": [
    {
      "target": "rust",
      "suggestion": "serde + csv crate for parsing, lettre for SMTP",
      "estimated_reduction": "40 lines → 15 lines",
      "risk": "low — well-mapped standard library equivalents"
    },
    {
      "target": "go",
      "suggestion": "encoding/csv + net/smtp, idiomatic error returns",
      "estimated_reduction": "40 lines → 25 lines",
      "risk": "low"
    }
  ],
  "verification_hints": [
    "test with: empty CSV, single row, 1000 rows, malformed row, unicode in fields",
    "test with: unreachable SMTP, auth failure, timeout",
    "compare: return value, emails actually sent (use mock SMTP)"
  ]
}
```

**What gets lost in functional translation — and how we catch it:**

| Risk | Example | Detection method |
|------|---------|-----------------|
| Error handling drift | Python `except Exception, e` has different semantics than Rust `Result<T,E>` | Contract lists specific error conditions; verification tests each one |
| Side effect omission | Logging, metrics, state mutation dropped in rewrite | Contract lists side effects; behavioral diff catches missing log lines |
| Implicit behavior | Python dict ordering, GIL thread safety, default encoding | `implicit_behaviors` field flags these for human review |
| Performance characteristics | Hot-path function needs to stay <1ms | `complexity` field + performance-benchmarker skill validates |
| Platform workarounds | That weird `sleep(0.1)` exists because of a race condition | Flagged as `implicit_behaviors` with "investigate" marker |

**Integration with existing skills.** The behavioral-diff-generator already compares Py2 vs Py3 outputs by running test suites under both interpreters. The behavioral analyzer extends this concept: instead of just comparing outputs, it generates the *contracts* that explain why the outputs should match, and produces targeted test cases for areas the existing test suite doesn't cover.

### 10. Atomic Work Decomposition (`work_decomposer.py`)

A critical design goal: every unit of work should be small enough for a fast, cheap model (Haiku-class) to execute reliably. Opus plans the project. Sonnet handles complex analysis. Haiku does the volume work — and there's a lot of volume work in a migration.

**Why atomic decomposition matters:**

A 500-file migration isn't one task. It's thousands of small tasks, most of which are routine. If each task is self-contained and well-specified, a Haiku-class model can handle it with high accuracy at a fraction of the cost and latency of a larger model. The key is making each work item carry enough context to be done independently, without requiring the model to understand the full codebase.

**Work item granularity:**

```
Project level    (Opus plans)     "Migrate acme-scada from Python 2.7 to 3.12"
  │
  ├─ Wave level  (Sonnet plans)   "Wave 3: migrate src.io cluster (8 modules, critical risk)"
  │   │
  │   ├─ Module level             "Migrate src.io.modbus_reader (42 findings, 3 dependencies)"
  │   │   │
  │   │   ├─ Function level       "Convert read_registers(): 3 py2 patterns, 12 lines"
  │   │   │   │
  │   │   │   ├─ Pattern level    "Replace has_key() call on line 47 with 'in' operator"
  │   │   │   ├─ Pattern level    "Replace xrange() call on line 52 with range()"
  │   │   │   └─ Pattern level    "Fix except clause syntax on line 61"
  │   │   │
  │   │   ├─ Function level       "Convert write_coils(): 1 py2 pattern, 8 lines"
  │   │   └─ Function level       "Convert _pack_registers(): struct.pack, critical risk"
  │   │
  │   └─ Module level             "Migrate src.io.serial_protocol ..."
  │
  └─ Wave level                   "Wave 4: ..."
```

**Haiku-executable work items.** Each work item at the pattern and function level is a self-contained packet:

```json
{
  "work_item_id": "wave3-modbus_reader-read_registers-001",
  "type": "pattern_fix",
  "model_tier": "haiku",
  "context": {
    "file": "src/io/modbus_reader.py",
    "function": "read_registers",
    "function_source": "def read_registers(self, unit_id, start, count):\n    ...",
    "function_lines": [42, 67],
    "language_source": "python2",
    "language_target": "python3",
    "dependencies_context": ["src.io.serial_protocol.SerialConnection"],
    "imports_used": ["struct", "logging"]
  },
  "task": {
    "pattern": "has_key",
    "line": 47,
    "current_code": "if self._cache.has_key(register_addr):",
    "fix_description": "Replace dict.has_key(k) with 'k in dict'",
    "expected_result": "if register_addr in self._cache:",
    "category": "builtin_changes",
    "risk": "low"
  },
  "verification": {
    "behavioral_contract": "read_registers returns list[int], raises ModbusError on timeout",
    "test_command": "pytest tests/test_modbus.py::test_read_registers -x",
    "rollback": "git checkout -- src/io/modbus_reader.py"
  }
}
```

Notice: the work item includes the function source, the specific line, what to do, what the result should look like, how to verify it, and how to roll back. Haiku doesn't need to understand the whole codebase. It needs to make one targeted change and verify it.

**Model tier routing:**

| Task type | Model | Rationale |
|-----------|-------|-----------|
| Project planning, wave sequencing, risk assessment | Opus | Needs full-codebase reasoning, architectural judgment |
| Behavioral contract extraction | Sonnet | Needs to infer intent from code, moderate reasoning |
| Complex pattern fixes (metaclass, descriptors, C extensions) | Sonnet | Edge cases, multiple valid approaches |
| Module-level orchestration, integration checks | Sonnet | Needs to reason about dependencies |
| Simple pattern fixes (has_key, xrange, print statement) | Haiku | Mechanical, well-specified, high volume |
| Test generation from contracts | Haiku | Template-driven, one function at a time |
| Import rewrites (stdlib renames) | Haiku | Lookup table, no reasoning needed |
| Report generation | Haiku | Formatting existing data |
| Behavioral contract verification (run tests, compare) | Haiku | Execute command, check output, report |
| Code review of Haiku output | Sonnet | Spot-check quality, catch edge cases |

**Estimated cost impact.** In a typical Python 2→3 migration, roughly 70% of findings are mechanical pattern fixes (has_key, print, except syntax, xrange, iteritems). These are all Haiku-tier. Another 15% are moderate (string/bytes, stdlib renames, metaclass changes) — Sonnet-tier. The remaining 15% are complex (C extensions, dynamic patterns, encoding issues) — Sonnet or Opus. By routing correctly, a 500-file migration that would cost $X with Opus-for-everything costs roughly $X/10 with tiered routing.

**The decomposer pipeline:**

```python
class WorkDecomposer:
    """Break a migration project into atomic, model-appropriate work items.

    Uses the dependency graph (topological order), the raw scan (findings),
    behavioral contracts, and the conversion unit plan to produce a stream
    of self-contained work items, each tagged with the appropriate model tier.
    """

    # Patterns that Haiku can handle reliably
    HAIKU_PATTERNS = {
        "has_key", "iteritems", "itervalues", "iterkeys",
        "xrange", "raw_input", "print_statement", "print_function",
        "unicode_builtin", "long_builtin", "buffer_builtin",
        "apply_builtin", "execfile_builtin", "cmp_builtin",
        "reduce_builtin", "file_builtin", "reload_builtin",
        "dict_keys_list", "dict_values_list", "dict_items_list",
        "except_syntax", "raise_syntax", "octal_literal",
        "backtick_repr", "inequality_operator",
        "stdlib_rename",  # When target module is known
        "future_import",  # Adding __future__ imports
    }

    # Patterns that need Sonnet
    SONNET_PATTERNS = {
        "metaclass_attribute", "metaclass_syntax",
        "string_bytes_mixing", "encode_decode",
        "struct_usage", "pickle_usage",
        "unicode_method", "cmp_method",
        "descriptor_protocol", "exec_statement",
        "relative_import_implicit",
        "dynamic_import", "dynamic_attribute",
    }

    # Everything else gets Opus review
    OPUS_PATTERNS = {
        "c_extension_usage", "ctypes_usage",
        "custom_codec", "ebcdic_encoding",
        "thread_safety_concern", "monkey_patching",
    }

    def decompose(
        self,
        raw_scan: dict,
        dependency_graph: dict,
        conversion_plan: dict,
        behavioral_contracts: dict,
    ) -> list[dict]:
        """Produce ordered work items from analysis outputs.

        Returns work items in dependency-safe order (leaf modules first),
        each tagged with model_tier, full context, and verification steps.
        """
        work_items = []

        for wave in conversion_plan["waves"]:
            for unit in wave["units"]:
                for module in unit["modules"]:
                    module_scan = self._get_module_scan(raw_scan, module)
                    contract = behavioral_contracts.get(module, {})

                    # Group findings by function
                    by_function = self._group_by_function(module_scan)

                    for func_name, findings in by_function.items():
                        func_contract = contract.get("functions", {}).get(func_name, {})

                        for finding in findings:
                            work_items.append(self._make_work_item(
                                wave=wave,
                                module=module,
                                function=func_name,
                                finding=finding,
                                contract=func_contract,
                                module_scan=module_scan,
                            ))

        return work_items

    def _assign_model_tier(self, pattern: str, risk: str, context: dict) -> str:
        """Route work to the cheapest model that can handle it reliably."""
        if pattern in self.HAIKU_PATTERNS and risk in ("low", "medium"):
            return "haiku"
        if pattern in self.SONNET_PATTERNS or risk == "high":
            return "sonnet"
        if pattern in self.OPUS_PATTERNS or risk == "critical":
            # Opus plans, Sonnet executes with Opus review
            return "sonnet+opus_review"
        # Default: Sonnet for anything unrecognized
        return "sonnet"
```

**Relationship to behavioral analysis.** The behavioral contracts feed directly into work item context. When Haiku fixes a `has_key` call inside `read_registers()`, the work item includes: "this function's contract says it returns `list[int]` and raises `ModbusError` on timeout — your change must preserve that." Haiku doesn't need to figure out what the function does; the contract tells it. This is what makes small-model execution reliable — the reasoning happened upstream (in Sonnet, during contract extraction), and the execution is mechanical.

**Verification cascade.** After Haiku makes a change:

1. Run the function's test (if one exists) — Haiku can do this
2. Check the behavioral contract — does the output still match? — Haiku can do this
3. Spot-check: periodically, Sonnet reviews a sample of Haiku's work — catches systematic errors
4. Integration check: after all functions in a module are done, Sonnet runs the full module test suite
5. Wave-level verification: after all modules in a wave are done, the behavioral-diff-generator runs

### 11. Dependencies

```
# Core (required)
tree-sitter>=0.23.0
tree-sitter-language-pack>=0.2.0
identify>=2.6.0

# Graph analysis (required)
networkx>=3.0

# Language detection fallback (optional, improves ambiguous file handling)
pygments>=2.17.0

# Interactive visualization (optional)
pyvis>=0.3.0

# Depends integration (optional, requires JRE)
# Install separately: download depends.jar from https://github.com/multilang-depends/depends
```

## New Skill Structure (updated)

```
skills/
  universal-code-graph/
    SKILL.md
    scripts/
      analyze_universal.py        # Entry point, orchestrates everything
      ts_parser.py                # tree-sitter wrapper with lazy loading
      universal_extractor.py      # Query-driven extraction engine
      py2_patterns_ts.py          # Py2 patterns via tree-sitter queries
      language_detect.py           # Two-pass language detection
      depends_runner.py           # multilang-depends integration
      graph_builder.py            # Enhanced graph builder (extends build_dep_graph.py)
      behavioral_analyzer.py     # Contract extraction per function
      work_decomposer.py         # Atomic work item generation with model routing
      visualize.py                # PyVis + enhanced HTML visualization
    queries/
      python_imports.scm
      python_definitions.scm
      python_calls.scm
      python_py2_patterns.scm     # Consolidated Py2 pattern queries
      java_imports.scm
      java_definitions.scm
      java_calls.scm
      javascript_imports.scm
      javascript_definitions.scm
      javascript_calls.scm
      c_includes.scm
      c_definitions.scm
      c_calls.scm
      cpp_includes.scm
      cpp_definitions.scm
      cpp_calls.scm
      rust_imports.scm
      rust_definitions.scm
      rust_calls.scm
      ruby_imports.scm
      ruby_definitions.scm
      ruby_calls.scm
      go_imports.scm
      go_definitions.scm
      go_calls.scm
    dashboard/
      index.html                  # Migration tracking dashboard
      migration-state-schema.json
    assets/
      dependency-graph-template.html
    tools/
      README.md                   # Instructions for installing depends.jar
    references/
      tree-sitter-query-syntax.md
      supported-languages.md
```

## Integration with Existing Skills

The universal-code-graph skill produces the same output files as py2to3-codebase-analyzer:

| Output | Format | Compatibility |
|--------|--------|---------------|
| `raw-scan.json` | JSON | Same schema, new optional fields (`language`, `symbols`, `calls`, `parser`) |
| `dependency-graph.json` | JSON | Same schema, nodes now have `language` property |
| `dependency-graph.html` | HTML | Enhanced with language color-coding |
| `migration-order.json` | JSON | Same schema, unchanged |

All downstream skills continue to work without modification. New fields are additive.

New outputs:

| Output | Format | Purpose |
|--------|--------|---------|
| `call-graph.json` | JSON | Function/method-level call relationships |
| `codebase-graph.graphml` | GraphML | NetworkX export for external tools |
| `migration-state.json` | JSON | Dashboard status tracking |
| `behavioral-contracts.json` | JSON | Per-function behavioral contracts |
| `work-items.json` | JSON | Atomic work items with model-tier routing |

## Impact on Existing Skill Suite

The 28 existing skills fall into four categories relative to this architecture:

### Skills that gain new capabilities (modify)

These skills currently use `ast` and would gain tree-sitter as a fallback/alternative path. Each gets a conditional import: if tree-sitter is available, use it; otherwise fall back to `ast` exactly as today.

| Skill | Current AST usage | Change |
|-------|-------------------|--------|
| `py2to3-codebase-analyzer` | `Py2PatternVisitor(ast.NodeVisitor)`, 20+ patterns | Add tree-sitter fallback path for files that fail `ast.parse()`. Biggest win — this is where Python 2 files currently fall to regex. |
| `py2to3-dead-code-detector` | 8 node types, READ-ONLY | Add tree-sitter queries for unused function/class detection. Enables dead code detection in non-Python files. |
| `py2to3-type-annotation-adder` | 6+ node types, READ-ONLY | Add tree-sitter extraction of function signatures for files ast can't parse. |
| `py2to3-dynamic-pattern-resolver` | 10 node types, READ-ONLY | Tree-sitter queries for `getattr`, `eval`, `exec`, `__import__` detection. Better coverage of Py2 files. |
| `py2to3-automated-converter` | `ast.NodeTransformer`, MODIFIES tree | Hardest to augment — tree-sitter produces a CST, not an AST. For now, this skill stays ast-only for Python. For other languages, translation is LLM-driven using behavioral contracts, not tree transformations. |

### Skills that consume new outputs (extend)

These skills read JSON outputs from the analyzer. They get richer data automatically because the new fields are additive.

| Skill | What it reads | What changes |
|-------|---------------|--------------|
| `py2to3-conversion-unit-planner` | `dependency-graph.json`, `migration-order.json` | Nodes now have `language` property. Planner can create cross-language waves. Also receives `work_items.json` from the decomposer for model-tier routing. |
| `py2to3-behavioral-diff-generator` | Runs tests under Py2 and Py3 | Gains behavioral contracts as an additional comparison source. Can now generate targeted test cases for uncovered code paths. |
| `py2to3-migration-state-tracker` | `migration-state.json` | Schema gets new fields: `behavioral_equivalence_confidence`, `modernization_opportunities`, `model_tier_used`. Dashboard reads this directly. |
| `py2to3-gate-checker` | Various analysis outputs | Add gate: "behavioral contract verification passed" as a new gate criterion. |
| `py2to3-performance-benchmarker` | Runs timing comparisons | Behavioral contracts include performance expectations. Benchmarker can validate against contract. |
| `py2to3-rollback-plan-generator` | Dependency graph, conversion plan | Work items include per-function rollback commands. Rollback plans become more granular. |

### New skills to create

| Skill | Purpose | Model tier |
|-------|---------|------------|
| `universal-code-graph` | Core skill: tree-sitter parsing, language detection, universal extraction, graph building. The foundation everything else builds on. | N/A (infrastructure) |
| `behavioral-contract-extractor` | Extract behavioral contracts for functions/modules. Uses tree-sitter structural data + LLM reasoning (Sonnet) to produce contracts. Feeds work decomposer and verification. | Sonnet for extraction |
| `work-item-generator` | Takes raw scan + dependency graph + contracts + conversion plan → produces atomic work items with model-tier routing. This is the "project manager" skill that feeds items to other skills. | Sonnet for planning |
| `haiku-pattern-fixer` | Executes simple pattern-level fixes from work items. Self-contained: receives work item, applies fix, runs verification, reports result. Designed to be called thousands of times with Haiku. | Haiku |
| `translation-verifier` | Runs behavioral contract verification after translation. Compares source behavior vs target behavior, reports confidence score. Extends behavioral-diff-generator concept. | Haiku for execution, Sonnet for analysis |
| `modernization-advisor` | Given a behavioral contract and target language, suggests idiomatic alternatives. "This 40-line function could be 8 lines with serde." Runs per-function, outputs opportunities for dashboard. | Sonnet |
| `migration-dashboard` | Standalone skill that generates/serves the HTML dashboard. Reads all JSON outputs, renders the split-pane graph with status colors. | N/A (HTML/JS) |

### Skills that need no changes

The remaining skills are either downstream consumers that already work with the existing JSON schemas, or they handle concerns orthogonal to code analysis:

`py2to3-bytes-string-fixer`, `py2to3-c-extension-flagger`, `py2to3-canary-deployment-planner`, `py2to3-ci-dual-interpreter`, `py2to3-compatibility-shim-remover`, `py2to3-completeness-checker`, `py2to3-custom-lint-rules`, `py2to3-data-format-analyzer`, `py2to3-encoding-stress-tester`, `py2to3-future-imports-injector`, `py2to3-library-replacement`, `py2to3-lint-baseline-generator`, `py2to3-project-initializer`, `py2to3-serialization-detector`, `py2to3-test-scaffold-generator`

These all continue working unchanged. As the universal graph adds new languages and richer data, they'll gradually gain utility for non-Python files, but they don't *require* changes.

## Implementation Phases

**Phase 1: Core infrastructure**
- `language_detect.py` with two-pass detection
- `ts_parser.py` with lazy grammar loading
- `universal_extractor.py` with query engine
- Python query files (imports, definitions, calls)
- `analyze_universal.py` with ast-first-then-tree-sitter orchestration
- Verify output compatibility with existing `build_dep_graph.py`

**Phase 2: Python 2 pattern detection**
- `py2_patterns_ts.py` with all 20+ pattern queries
- Test against real Python 2 codebases
- Measure: how many more findings vs regex-only fallback?
- Grammar fidelity testing — if <90% parse success, evaluate fork

**Phase 3: Depends integration**
- `depends_runner.py` with subprocess management
- Merge logic: depends edges + tree-sitter symbols
- Benchmark: does the two-pass approach find edges tree-sitter misses?

**Phase 4: Multi-language query files**
- Java, C, C++, Rust, Ruby, Go query files
- One language at a time, tested against real codebases
- Enhanced graph builder with language-aware node properties

**Phase 5: Call graph + NetworkX**
- Function-level call graph extraction
- NetworkX graph export
- GraphML output for external visualization tools

**Phase 6: Behavioral analysis & work decomposition**
- `behavioral_analyzer.py` — contract extraction per function (Sonnet-driven)
- `work_decomposer.py` — atomic work items with model-tier routing
- New skill: `behavioral-contract-extractor`
- New skill: `work-item-generator`
- New skill: `haiku-pattern-fixer` (high-volume, low-cost pattern fixes)
- New skill: `translation-verifier` (contract-based equivalence checking)
- New skill: `modernization-advisor` (idiomatic target suggestions)
- Integration: behavioral contracts feed into conversion-unit-planner
- Integration: work items carry verification steps and rollback commands

**Phase 7: Migration dashboard**
- `migration-state.json` schema (extended with behavioral confidence + model tier)
- Split-pane HTML dashboard
- Status color-coding on force-directed graph
- Progress tracking, blockers list, modernization opportunities panel
- Behavioral equivalence confidence per module
- Cost tracking: model-tier usage and estimated savings
- New skill: `migration-dashboard`
- Integration with migration-state-tracker skill

**Phase 8: Skill suite updates**
- Update py2to3-codebase-analyzer with tree-sitter fallback
- Update py2to3-dead-code-detector to optionally use tree-sitter
- Update py2to3-dynamic-pattern-resolver to optionally use tree-sitter
- Update py2to3-type-annotation-adder to optionally use tree-sitter
- Extend py2to3-behavioral-diff-generator with contract-based verification
- Extend py2to3-gate-checker with behavioral verification gate
- Extend py2to3-conversion-unit-planner with work-item awareness
- Each updated skill checks for tree-sitter availability and falls back gracefully

**Phase 9: Cross-language migration support**
- Generalize skill naming: drop `py2to3-` prefix for language-agnostic skills
- Create target-language template skills (e.g., `migration-to-rust`, `migration-to-go`)
- Each target-language skill bundles: idiomatic patterns, standard library mappings, ecosystem equivalents
- The haiku-pattern-fixer becomes language-aware (fix patterns in any source→target pair)
- The modernization-advisor uses target-language skills for specific suggestions

## Resolved Decisions

1. **Grammar per language:** We maintain tree-sitter query files for every target language. The language-pack provides grammars for all of them. For Python 2, we start with the Python 3 grammar + error recovery. If fidelity is too low on real Py2 code, we fork.

2. **Cross-language boundaries:** Dropped as a separate concept. The unified graph treats all files equally regardless of language. API routes, RPC definitions, and config-based connections are just another query pattern to extract — same as imports.

3. **Depends integration:** Included as an optional enrichment layer. Tree-sitter alone is sufficient; depends adds validation and catches edges tree-sitter queries may miss. Requires JRE but fails gracefully without it.

4. **Grammar loading:** Two-pass detection with `identify` + `pygments`, then lazy-load only detected language grammars via `tree-sitter-language-pack.get_parser()`.

5. **Functional vs structural translation:** Both, in parallel. Structural translation (Track A) is the safe primary path. Behavioral analysis (Track B) runs alongside for verification and modernization opportunities. Neither replaces the other.

6. **Model tier routing:** Atomic work decomposition enables Haiku for ~70% of volume work (mechanical pattern fixes), Sonnet for ~25% (complex patterns, contract extraction, integration), Opus for ~5% (project planning, architectural decisions). This applies to all migration directions, not just Py2→Py3.

7. **Skill proliferation strategy:** New skills are fine. Each skill should do one thing well at one level of granularity. A skill that's called 1,000 times by Haiku (haiku-pattern-fixer) is fundamentally different from one called once by Opus (conversion-unit-planner), and they should be separate. The work-item-generator acts as the orchestrator that knows which skill to invoke at which tier.
