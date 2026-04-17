---
name: discover
description: >
  Orchestrate foundation tools (treeloom, greploom, sanicode, veripak) to produce
  a skeleton spec.json from a codebase. The M1 entry point for the vertical plane
  model. Populates cpg_ref, ecosystem_dependencies, security_findings, and stub
  elements for every module, class, and function. Contracts are left empty for M2.
triggers:
  - discover codebase
  - build spec
  - extract spec
  - skeleton spec
  - codebase analysis
  - initial extraction
inputs:
  - codebase_path: Root directory of the codebase to analyze
  - language: Primary language (java, python, javascript, go, etc.)
  - source_root: (optional) Relative path to source tree, auto-detected if omitted
outputs:
  - spec.json: Skeleton specification conforming to spec-schema/spec.schema.json
  - greploom.db: Semantic search index (side artifact for M2 agents)
model_tier: sonnet
---

# Discover: Skeleton Spec Extraction

Orchestrates treeloom, greploom, sanicode, and veripak to produce a `spec.json`
skeleton from a codebase. This is the M1 (machine extraction) step in the
vertical plane model — it builds the structural scaffold that M2 enriches with
behavioral contracts.

## When to Use

When starting a migration or doing first-time analysis of a codebase. Produces
the initial spec skeleton (all elements, no contracts) that M2 (LLM extraction)
enriches with behavioral contracts. Run once per codebase, or re-run after
significant structural changes.

## Workflow

The four tools form a partial DAG — treeloom must finish first, then greploom,
sanicode, and veripak run in parallel:

```
                        +-- greploom index ------+
treeloom build ---------+                        +--- assemble spec.json
                        +-- sanicode scan -------+
    parse manifests ----+-- veripak check (xN) --+
```

### Step 1: Detect project structure

Identify the source root and dependency manifests before running any tools.

- **Java**: source root is typically `src/main/java`. Manifests: `pom.xml` or `build.gradle`.
- **Python**: source root is typically `src` or the package directory. Manifests: `requirements.txt`, `setup.cfg`, `pyproject.toml`, or `setup.py`.

Auto-detect by checking for these common paths. Ask the user if the layout is
ambiguous — do not guess.

### Step 2: Build the CPG (or reuse cached)

The treeloom CPG is the foundation — everything else depends on it.

Cache check: if `cpg.json` exists and is newer than all source files, skip this
step.

```bash
treeloom build <codebase_path>/<source_root> \
  --language <language> \
  -o cpg.json \
  --include-source \
  --relative-root <codebase_path>
```

Flags:
- `--include-source` embeds source text in each node (needed for greploom and for LLM context in M2)
- `--relative-root` makes node IDs portable (relative paths instead of absolute)

Build times: jsoup (Java, 91 files) ~8–9 minutes; dateutil (Python, 17 files)
~2 minutes.

### Step 3: Parallel tool runs

These three tasks are independent once the CPG exists. Run them in parallel.
veripak does not need the CPG at all — it only needs the dependency manifest.

#### Step 3a: Build greploom index

Cache check: if `greploom.db` exists and is newer than `cpg.json`, skip.

```bash
greploom index cpg.json \
  --db greploom.db \
  --ollama-url http://localhost:11434 \
  --tier enhanced
```

Prerequisite: Ollama must be running locally. Verify with:

```bash
curl -s http://localhost:11434/api/tags | head -c 100
```

The greploom index is a side artifact for M2 extraction agents. It is NOT stored
in the spec itself.

#### Step 3b: Run sanicode scan

```bash
sanicode scan <codebase_path>/<source_root> \
  -f json --quiet --no-llm \
  -o sanicode-result.json
```

`--no-llm` produces fast, deterministic results. LLM enrichment is optional and
can be done in a separate pass later.

Java note: sanicode 0.12.2 fixed a performance regression. Full jsoup (91 files)
completes in ~12s with `--no-llm`.

#### Step 3c: Parse manifests and run veripak

First, extract package names from the dependency manifest.

**Java (pom.xml):**
```bash
python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('pom.xml')
root = tree.getroot()
ns = {'m': 'http://maven.apache.org/POM/4.0.0'}
deps = root.findall('.//m:dependency', ns) or root.findall('.//dependency')
for dep in deps:
    g = dep.find('m:groupId', ns) if dep.find('m:groupId', ns) is not None else dep.find('groupId')
    a = dep.find('m:artifactId', ns) if dep.find('m:artifactId', ns) is not None else dep.find('artifactId')
    scope = dep.find('m:scope', ns) if dep.find('m:scope', ns) is not None else dep.find('scope')
    if g is not None and a is not None:
        s = scope.text if scope is not None else 'compile'
        if s not in ('test', 'provided'):
            print(f'{g.text}:{a.text}')
"
```

Use `groupId:artifactId` format for Java — plain artifact names resolve to a
different data source with less accurate results.

**Python (setup.cfg):**
```bash
python3 -c "
import configparser
c = configparser.ConfigParser()
c.read('setup.cfg')
reqs = c.get('options', 'install_requires', fallback='')
for line in reqs.strip().splitlines():
    pkg = line.strip().split('>')[0].split('<')[0].split('=')[0].split('!')[0].split(';')[0].strip()
    if pkg:
        print(pkg)
"
```

**Python (requirements.txt):**
```bash
python3 -c "
with open('requirements.txt') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('-'):
            pkg = line.split('>')[0].split('<')[0].split('=')[0].split('!')[0].split(';')[0].strip()
            if pkg:
                print(pkg)
"
```

Then for each package, run veripak:

```bash
veripak check <package_name> -e <ecosystem> --json > veripak-<package_name>.json
```

Where `<ecosystem>` is `java`, `python`, `javascript`, etc.

### Step 4: Assemble the spec

```bash
python skills/discover/assemble.py \
  --cpg cpg.json \
  --project-name <project_name> \
  --language <language> \
  --source-root <source_root> \
  [--source-version <version>] \
  [--sanicode sanicode-result.json] \
  [--veripak veripak-pkg1.json --veripak veripak-pkg2.json ...] \
  -o spec.json
```

The assemble script reads all tool outputs and produces a `spec.json` conforming
to the schema. It:

- Creates a stub element for every module, class, and function in the CPG
- Maps sanicode findings to the `security_findings` section
- Maps veripak audits to the `ecosystem_dependencies` section
- Computes CPG stats for the `cpg_ref` section
- Leaves all contracts empty (`{}`) — that is M2's job

Note: the assemble script reads the raw CPG JSON directly to walk all edges.
`treeloom edges --kind contains --json` returns at most ~50 edges and cannot be
used here.

### Step 5: Validate and render

```bash
# Validate against schema and render to Markdown
python spec-schema/render.py spec.json -o spec-review.md
```

Quick sanity check on element counts:

```bash
python3 -c "
import json
spec = json.load(open('spec.json'))
els = spec['elements']
by_level = {}
for e in els.values():
    by_level.setdefault(e['hierarchy_level'], []).append(e)
for level, items in sorted(by_level.items()):
    print(f'{level}: {len(items)}')
print(f'Total elements: {len(els)}')
if 'security_findings' in spec:
    print(f'Security findings: {len(spec[\"security_findings\"])}')
if 'ecosystem_dependencies' in spec:
    print(f'Ecosystem dependencies: {len(spec[\"ecosystem_dependencies\"])}')
"
```

Expected counts:
- jsoup (Java, 91 files): ~2200+ elements (modules + classes + functions)
- dateutil (Python, 17 files): ~370 elements

## Tool-Specific Workarounds

1. **sanicode severity field.** The summary's `by_severity` uses `derived_severity`,
   but individual findings carry both `severity` and `derived_severity`. The
   assemble script prefers `derived_severity`.

2. **veripak Maven coordinates.** For Java packages, always use `groupId:artifactId`
   format (e.g., `org.jsoup:jsoup`). Plain artifact names resolve to different
   data sources with less accurate results.

3. **veripak urgency with 0 CVEs.** veripak may report `urgency: high` for packages
   with 0 CVEs — it factors in EOL uncertainty. The assemble script passes this
   through unchanged.

4. **greploom query result shape.** Query results wrap in
   `{"metadata": {...}, "results": [...]}`. Parse the `results` key, not the
   top-level object. This applies to M2 agents using greploom for context lookup,
   not to discover (which only builds the index).

5. **treeloom edges CLI limit.** `treeloom edges --kind contains --json` returns
   at most ~50 edges. The assemble script reads the raw CPG JSON directly to get
   all edges.

## Verification

The skill succeeded if:

- `spec.json` validates against `spec-schema/spec.schema.json` with zero errors
- `spec.json` renders to readable Markdown via `spec-schema/render.py`
- Every module, class, and function in the CPG has a corresponding element in the spec
- All elements have `metadata.source: static_analysis`, `metadata.status: extracted`, `metadata.confidence: high`
- All elements have empty contracts (`{}`)
- Security findings are present when sanicode was run
- Ecosystem dependencies are present when veripak was run
- `cpg_ref.stats` matches `treeloom info` output

## Tool Dependencies

- **treeloom** >= 0.8.1: Code property graph builder
- **greploom** >= 0.4.0: Semantic search over CPGs (requires Ollama for embeddings)
- **sanicode** >= 0.12.2: SAST scanner with compliance mapping
- **veripak** >= 0.6.2: Dependency auditing across ecosystems
- **Python 3.10+**: For assemble.py (uses match statements and type union syntax)
- **jsonschema**: For spec validation (installed in project venv)
- **Jinja2**: For spec rendering (installed in project venv)
- **Ollama**: Required by greploom for embedding generation

## References

- `spec-schema/spec.schema.json` — the schema discover's output must conform to
- `spec-schema/examples/jsoup-safety.spec.json` — example filled spec (jsoup safety module)
- `spec-schema/examples/dateutil-parser.spec.json` — example filled spec (dateutil parser)
- `spec-schema/render.py` — validation and rendering script
- `planning/code-translation-kit/roadmap.md` — full project design, M1 section
- `planning/code-translation-kit/tool-feedback.md` — tool status and workarounds from Round 3
