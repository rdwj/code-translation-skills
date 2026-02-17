# Universal Code Graph - Usage Examples

Practical examples for using each script as CLI and library.

## 1. Language Detection

### CLI Usage

```bash
# Basic detection
python3 language_detect.py /path/to/codebase

# Exclude patterns
python3 language_detect.py /path/to/codebase \
  --exclude "**/vendor/**" "**/node_modules/**" "**/test/**"

# Custom output file
python3 language_detect.py /path/to/codebase --output my-lang-map.json
```

### CLI Output

```json
{
  "status": "success",
  "files_by_language": {
    "python": 42,
    "javascript": 15,
    "java": 8,
    "c": 3,
    "unknown": 2
  },
  "total_files": 70,
  "unknown_count": 2,
  "detected_languages": ["c", "java", "javascript", "python"]
}
```

### Library Usage

```python
from language_detect import detect_languages

# Detect all languages in codebase
languages, language_map = detect_languages('/path/to/codebase')

print(f"Found languages: {languages}")
# Output: Found languages: {'python', 'javascript', 'java'}

# Inspect per-file detection
for filepath, lang in list(language_map.items())[:5]:
    print(f"{filepath}: {lang}")
# Output:
# src/main.py: python
# src/utils.js: javascript
# src/Main.java: java
# src/helpers.py: python
# src/api.js: javascript

# Save for later use
import json
with open('language-map.json', 'w') as f:
    json.dump(language_map, f, indent=2)
```

---

## 2. Tree-Sitter Parsing

### CLI Usage

```bash
# Parse a Python file
python3 ts_parser.py src/main.py python --output parsed-main.json

# Parse a Java file
python3 ts_parser.py src/Main.java java

# Parse with output to stdout
python3 ts_parser.py src/utils.js javascript | jq .root_node.children
```

### CLI Output

```json
{
  "filepath": "/abs/path/src/main.py",
  "language": "python",
  "root_node": {
    "type": "module",
    "start_point": [0, 0],
    "end_point": [42, 0],
    "start_byte": 0,
    "end_byte": 1250,
    "children": [
      {
        "type": "import_statement",
        "start_point": [0, 0],
        "end_point": [0, 8],
        "children": []
      },
      {
        "type": "function_definition",
        "start_point": [2, 0],
        "end_point": [10, 0],
        "children": [...]
      }
    ]
  },
  "error_nodes": [],
  "parse_success": true
}
```

### Library Usage

```python
from ts_parser import parse_file
import json

# Parse a file
try:
    result = parse_file('src/main.py', 'python')

    if result['parse_success']:
        print(f"Parsed {result['filepath']} successfully")
        print(f"Root node type: {result['root_node']['type']}")
        print(f"Error nodes: {len(result['error_nodes'])}")
    else:
        print(f"Parse failed: {result.get('error', 'unknown error')}")

except ValueError as e:
    print(f"Language not supported: {e}")
except FileNotFoundError as e:
    print(f"File not found: {e}")

# Process tree structure
def count_nodes(node):
    """Recursively count all nodes in tree."""
    count = 1
    for child in node.get('children', []):
        count += count_nodes(child)
    return count

root = result['root_node']
total_nodes = count_nodes(root)
print(f"Total nodes in tree: {total_nodes}")

# Find specific node types
def find_nodes(node, target_type):
    """Find all nodes of a specific type."""
    results = []
    if node.get('type') == target_type:
        results.append(node)
    for child in node.get('children', []):
        results.extend(find_nodes(child, target_type))
    return results

functions = find_nodes(result['root_node'], 'function_definition')
print(f"Found {len(functions)} function definitions")
```

---

## 3. Universal Symbol Extraction

### CLI Usage

```bash
# Extract symbols from parsed tree
python3 universal_extractor.py parsed-main.json python \
  --query-dir queries/ \
  --output symbols-main.json

# Extract from multiple files
for file in parsed-*.json; do
  python3 universal_extractor.py "$file" python --query-dir queries/
done

# Pipe from parser directly (shell example)
python3 ts_parser.py src/main.py python | \
  python3 universal_extractor.py /dev/stdin python --query-dir queries/
```

### CLI Output

```json
{
  "definitions": [
    {
      "name": "main",
      "type": "function",
      "file": "/abs/path/src/main.py",
      "line": 15,
      "column": 0
    },
    {
      "name": "DataProcessor",
      "type": "class",
      "file": "/abs/path/src/main.py",
      "line": 3,
      "column": 0
    }
  ],
  "imports": [
    {
      "name": "os",
      "type": "import",
      "file": "/abs/path/src/main.py",
      "line": 1,
      "column": 0
    },
    {
      "name": "json",
      "type": "import",
      "file": "/abs/path/src/main.py",
      "line": 2,
      "column": 0
    }
  ],
  "calls": [
    {
      "name": "process",
      "type": "call",
      "file": "/abs/path/src/main.py",
      "line": 20,
      "column": 4
    }
  ]
}
```

### Library Usage

```python
from ts_parser import parse_file
from universal_extractor import extract_symbols
import json

# Full pipeline: parse then extract
parsed = parse_file('src/main.py', 'python')
if parsed['parse_success']:
    symbols = extract_symbols(parsed, 'python', 'queries/')

    print(f"Functions: {[d['name'] for d in symbols['definitions'] if d['type'] == 'function']}")
    # Output: Functions: ['main', 'process', 'validate']

    print(f"Imports: {[i['name'] for i in symbols['imports']]}")
    # Output: Imports: ['os', 'json', 'sys']

    print(f"Calls to extract: {len(symbols['calls'])}")
    # Output: Calls to extract: 12

# Save for downstream processing
with open('symbols.json', 'w') as f:
    json.dump(symbols, f, indent=2)

# Analyze dependencies
def analyze_dependencies(symbols):
    """Get import statistics."""
    imports = symbols['imports']
    stdlib = {
        'os', 'sys', 'json', 'pickle', 'math', 're', 'time',
        'datetime', 'collections', 'itertools', 'functools',
        'pathlib', 'typing', 'logging', 'unittest'
    }

    local_imports = [i for i in imports if i['name'] not in stdlib]
    external_imports = [i for i in imports if i['name'] not in stdlib]

    return {
        'total_imports': len(imports),
        'local_imports': local_imports,
        'external_imports': external_imports,
        'local_count': len(local_imports),
        'external_count': len(external_imports)
    }

analysis = analyze_dependencies(symbols)
print(f"Local imports: {analysis['local_count']}")
print(f"External imports: {analysis['external_count']}")
```

---

## 4. Dependency Graph Building

### CLI Usage - Directory Mode

```bash
# Build graph from extracted symbols
python3 graph_builder.py ./symbols/ \
  --language-map language-map.json \
  --output ./analysis/

# Include GraphML export for visualization
python3 graph_builder.py ./symbols/ \
  --language-map language-map.json \
  --output ./analysis/ \
  --graphml
```

### CLI Usage - Merge Mode

```bash
# Merge multiple raw-scan files into single graph
python3 graph_builder.py \
  --merge analysis/*/raw-scan.json \
  --output ./combined-analysis/ \
  --graphml
```

### CLI Output

```json
{
  "status": "success",
  "output_dir": "./analysis/",
  "nodes": 47,
  "edges": 82,
  "languages": ["python", "javascript", "java"]
}
```

### Output Files

**dependency-graph.json:**
```json
{
  "nodes": [
    {
      "id": "src/main.py",
      "type": "module",
      "language": "python",
      "loc": 250,
      "definitions": [
        {"name": "main", "type": "function", "line": 15}
      ]
    }
  ],
  "edges": [
    {
      "source": "src/main.py",
      "target": "src/utils.py",
      "type": "import",
      "imported_name": "process"
    }
  ],
  "metrics": {
    "nodes": 12,
    "edges": 18,
    "languages": ["python", "javascript"],
    "is_dag": true,
    "topological_order": ["src/utils.py", "src/main.py"],
    "clusters": [
      {"size": 1, "nodes": ["src/utils.py"]},
      {"size": 11, "nodes": [...]}
    ],
    "fan_in": {"src/utils.py": 3, "src/main.py": 1},
    "fan_out": {"src/utils.py": 0, "src/main.py": 1}
  }
}
```

### Library Usage

```python
from graph_builder import build_dependency_graph, CodebaseGraph
import json

# Load extracted symbols and language map
with open('language-map.json', 'r') as f:
    language_map = json.load(f)

symbol_results = []
for file in Path('symbols/').glob('*.json'):
    with open(file, 'r') as f:
        symbol_results.append(json.load(f))

# Build graph
graph = build_dependency_graph(symbol_results, language_map)

# Analyze graph
metrics = graph.compute_metrics()
print(f"Total modules: {metrics['nodes']}")
print(f"Total dependencies: {metrics['edges']}")
print(f"Is acyclic? {metrics['is_dag']}")

# Find circular dependencies
if not metrics['is_dag']:
    cycles = metrics['clusters']
    for cycle in cycles:
        if cycle['size'] > 1:
            print(f"Cycle detected: {' -> '.join(cycle['nodes'])}")

# Find high-impact modules (high fan-in)
fan_in = metrics['fan_in']
high_impact = sorted(fan_in.items(), key=lambda x: x[1], reverse=True)[:5]
print("Top 5 most imported modules:")
for module, count in high_impact:
    print(f"  {module}: {count} importers")

# Export for external tools
graph.to_graphml('codebase-analysis.graphml')

# Programmatic access to graph structure
for node in graph.nodes.values():
    if node['type'] == 'module':
        print(f"{node['id']}: {len(node['definitions'])} definitions")

for edge in graph.edges:
    if edge['type'] == 'import':
        print(f"{edge['source']} imports {edge['target']}")
```

---

## Complete Pipeline Example

Combining all four scripts:

```python
from language_detect import detect_languages
from ts_parser import parse_file
from universal_extractor import extract_symbols
from graph_builder import build_dependency_graph
import json
from pathlib import Path

# Step 1: Detect languages
print("Step 1: Detecting languages...")
languages, language_map = detect_languages('/path/to/codebase')
print(f"  Found: {languages}")

# Step 2: Parse all files
print("Step 2: Parsing files...")
parsed_trees = {}
for filepath in language_map.keys():
    lang = language_map[filepath]
    result = parse_file(filepath, lang)
    if result['parse_success']:
        parsed_trees[filepath] = result

print(f"  Successfully parsed: {len(parsed_trees)}/{len(language_map)}")

# Step 3: Extract symbols
print("Step 3: Extracting symbols...")
all_symbols = []
for filepath, tree in parsed_trees.items():
    lang = language_map[filepath]
    symbols = extract_symbols(tree, lang, 'queries/')
    all_symbols.append({
        'filepath': filepath,
        **symbols
    })

print(f"  Extracted from {len(all_symbols)} files")

# Step 4: Build graph
print("Step 4: Building dependency graph...")
graph = build_dependency_graph(all_symbols, language_map)
metrics = graph.compute_metrics()

print(f"\nAnalysis Summary:")
print(f"  Modules: {metrics['nodes']}")
print(f"  Dependencies: {metrics['edges']}")
print(f"  Languages: {', '.join(sorted(metrics['languages']))}")
print(f"  Circular dependencies: {'No' if metrics['is_dag'] else 'Yes'}")

# Save results
with open('dependency-graph.json', 'w') as f:
    json.dump(graph.to_dict(), f, indent=2)

print("\nComplete! Results saved to dependency-graph.json")
```

---

## Integration Examples

### With build system

```bash
#!/bin/bash
# Analyze codebase and generate reports

CODEBASE="/path/to/project"
OUTPUT="./analysis/"

mkdir -p "$OUTPUT"

# Run full pipeline
python3 language_detect.py "$CODEBASE" --output "$OUTPUT/language-map.json"
python3 graph_builder.py "$OUTPUT/symbols/" \
  --language-map "$OUTPUT/language-map.json" \
  --output "$OUTPUT/" \
  --graphml

# Generate reports
echo "Analysis complete!"
echo "  Dependency graph: $OUTPUT/dependency-graph.json"
echo "  Call graph: $OUTPUT/call-graph.json"
echo "  GraphML: $OUTPUT/codebase-graph.graphml"
```

### With CI/CD

```yaml
# .github/workflows/analyze.yml
name: Code Analysis

on: [push, pull_request]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Detect Languages
        run: python3 scripts/language_detect.py . --output lang-map.json

      - name: Build Dependency Graph
        run: |
          python3 scripts/graph_builder.py ./symbols/ \
            --language-map lang-map.json \
            --output ./analysis/ \
            --graphml

      - name: Upload Analysis
        uses: actions/upload-artifact@v2
        with:
          name: code-analysis
          path: analysis/
```

---

## Error Handling Examples

```python
from ts_parser import parse_file
from universal_extractor import extract_symbols

# Handle missing grammar
try:
    result = parse_file('src/file.exotic', 'exotic-lang')
except ValueError as e:
    print(f"Language not supported: {e}")
    # Fallback: use generic extraction

# Handle parse errors
result = parse_file('src/main.py', 'python')
if not result['parse_success']:
    print(f"Parse errors found at:")
    for error in result['error_nodes']:
        print(f"  Line {error['start_point'][0]}: {error}")
    # Proceed with partial tree or skip file

# Handle missing query files
symbols = extract_symbols(tree, 'rust', 'queries/')
if not symbols['definitions']:
    print("No definitions found. Using fallback extraction.")
    # Graph builder will use available data
```

