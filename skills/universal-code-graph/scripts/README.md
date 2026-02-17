# Universal Code Graph Analysis Pipeline

Core tree-sitter analysis scripts for language-agnostic codebase parsing and dependency graph construction.

## Quick Start

### 1. Detect Languages
```bash
python3 scripts/language_detect.py /path/to/codebase --output language-map.json
```

### 2. Parse Files
```bash
python3 scripts/ts_parser.py /path/to/file.py python --output parsed-tree.json
```

### 3. Extract Symbols
```bash
python3 scripts/universal_extractor.py parsed-tree.json python --query-dir queries/ --output symbols.json
```

### 4. Build Graph
```bash
python3 scripts/graph_builder.py . --language-map language-map.json --output analysis/ --graphml
```

## Scripts

### language_detect.py
Detects programming languages in a codebase using two-pass analysis.

**Pass 1:** File extension mapping (covers 95%+ of files)
**Pass 2:** Shebang detection, identify library, pygments fallback

```bash
# CLI
python3 language_detect.py <codebase_path> [--exclude <patterns>] [--output <file>]

# Library
from language_detect import detect_languages
languages, language_map = detect_languages('/path')
```

**Output:**
- `language-map.json`: filepath → language mapping
- JSON summary to stdout

---

### ts_parser.py
Parses files using tree-sitter with lazy grammar loading.

**Features:**
- Lazy parser caching (loads grammars on demand)
- Multiple backend support (tree-sitter-language-pack, tree_sitter_languages, direct)
- JSON-serializable AST output
- Error node tracking

```bash
# CLI
python3 ts_parser.py <filepath> <language> [--output <file>]

# Library
from ts_parser import parse_file
result = parse_file('/path/file.py', 'python')
```

**Output:**
```json
{
  "filepath": "...",
  "language": "python",
  "root_node": { ... },
  "error_nodes": [ ... ],
  "parse_success": true
}
```

---

### universal_extractor.py
Extracts definitions, imports, and calls using tree-sitter queries.

**Supported query types per language:**
- `{lang}_definitions.scm` - Functions, classes, methods
- `{lang}_imports.scm` - Dependencies
- `{lang}_calls.scm` - Function/method invocations

**Fallback:** Generic node-type extraction when no queries available

```bash
# CLI
python3 universal_extractor.py <tree_file> <language> [--query-dir queries/] [--output <file>]

# Library
from universal_extractor import extract_symbols
symbols = extract_symbols(parsed_tree_dict, 'python', 'queries/')
```

**Output:**
```json
{
  "definitions": [{"name": "foo", "type": "function", "file": "...", "line": 10, "column": 0}],
  "imports": [{"name": "os", "type": "import", "file": "...", "line": 1, "column": 0}],
  "calls": [{"name": "bar", "type": "call", "file": "...", "line": 20, "column": 4}]
}
```

---

### graph_builder.py
Builds NetworkX dependency and call graphs.

**Computes:**
- Module-level import graph
- Function-level call graph
- Strongly connected components (SCC)
- Topological sort (if DAG)
- Fan-in/fan-out metrics

```bash
# Directory mode
python3 graph_builder.py /path/to/symbols/ --language-map language-map.json --output analysis/

# Merge mode
python3 graph_builder.py --merge raw-scan*.json --output analysis/ [--graphml]

# Library
from graph_builder import build_dependency_graph, CodebaseGraph
graph = build_dependency_graph(symbol_results, language_map)
graph.to_graphml('output.graphml')
```

**Output:**
- `dependency-graph.json` - Module-level graph
- `call-graph.json` - Function-level graph
- `codebase-graph.graphml` - GraphML export (optional)

---

## Dependencies

**Required:**
- Python 3.8+
- tree-sitter>=0.23.0
- tree-sitter-language-pack>=0.2.0 or tree_sitter_languages

**Optional but recommended:**
- identify>=2.6.0 - Robust shebang detection
- pygments>=2.17.0 - Fallback language detection
- networkx>=3.0 - Graph algorithms (enables SCC, topological sort, metrics)

## Supported Languages

- Python
- Java
- JavaScript
- TypeScript
- C
- C++
- Rust
- Go
- Ruby

Additional languages can be added by writing three `.scm` query files per language in the `queries/` directory.

## Design

### Zero LLM
All scripts use tree-sitter and pure Python analysis. No language model calls required.

### Dual Mode
Each script works as both:
1. **Standalone CLI** - Run from command line with argparse interface
2. **Library** - Import functions for integration into other tools

### Graceful Degradation
- Missing dependencies logged but don't crash
- Fallback extraction when query files unavailable
- Parser caching for efficiency

### Type Safety
Full type hints throughout for IDE support and code clarity.

## Pipeline Integration

The four scripts form a sequential analysis pipeline:

```
language_detect.py
    ↓ (produces: language-map.json)
ts_parser.py
    ↓ (produces: parsed-tree.json)
universal_extractor.py
    ↓ (produces: symbols.json with definitions/imports/calls)
graph_builder.py
    ↓ (produces: dependency-graph.json, call-graph.json, metrics)
[visualization & downstream analysis]
```

## Error Handling

All scripts include:
- Graceful fallbacks when dependencies missing
- Detailed logging (DEBUG, INFO, WARNING, ERROR)
- JSON error responses on failure
- Type-safe function signatures

## Limitations

- **ts_parser.py** requires grammar available for language
- **universal_extractor.py** uses fallback if queries unavailable
- **graph_builder.py** requires networkx for full metrics (degrades gracefully)
- Cross-language import resolution is heuristic-based (filename matching)

## Future Enhancements

1. Multi-file parsing with progress reporting
2. Incremental graph updates
3. Interactive visualization (pyvis integration)
4. Caching layer for large codebases
5. Parallel processing for multi-language files
6. Machine learning-based cross-language import resolution
