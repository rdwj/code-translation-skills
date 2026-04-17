---
name: library-replacement
description: >
  Identify imports that need replacement during a code migration and advise on
  replacements. Language-agnostic: works for any migration pair that has a
  mapping file (Python 2->3, Java 8->17, etc.). Uses treeloom for import
  extraction and YAML mapping files for replacement knowledge.
triggers:
  - library replacement
  - import migration
  - removed module
  - deprecated import
  - namespace migration
  - javax to jakarta
  - stdlib removal
inputs:
  - codebase_path: Root directory or specific files to analyze
  - migration_pair: ID of the mapping to use (e.g., "py2to3", "java8to17")
  - target_version: (optional) Target language version, for filtering version-gated entries
outputs:
  - library-replacements.json: Per-file import replacements with old->new mappings
  - library-replacements.md: Human-readable summary with next steps
model_tier: haiku
---

# Library Replacement Advisor

Identifies imports in a codebase that need replacement for a given migration,
and advises on what to replace them with. Works for any source->target pair
that has a mapping file in `skills/library-replacement/mappings/`.

## When to Use

- When migrating a codebase between language versions (Python 2->3, Java 8->17)
- When a platform removes bundled libraries (JDK module removals, Python stdlib removals)
- When a framework renames its namespace (javax -> jakarta)
- When you need a structured inventory of import changes before starting migration work

## Workflow

### Step 1: Build the code graph

Use treeloom to parse the codebase and extract all imports.

```bash
treeloom build <codebase_path> -o cpg.json --language <language>
```

For multi-language repos, omit `--language` and treeloom will auto-detect.

### Step 2: Extract imports

Query the CPG for import nodes:

```bash
treeloom query cpg.json --kind import --json > imports.json
```

Each import node has this structure:
```json
{
  "kind": "import",
  "name": "from ConfigParser",
  "file": "src/config.py",
  "line": 3,
  "attrs": {
    "module": "ConfigParser",
    "names": ["ConfigParser", "SafeConfigParser"],
    "is_from": true,
    "aliases": {}
  }
}
```

The `attrs.module` field is the key for matching against the mapping file.

### Step 3: Load the mapping file

Load `skills/library-replacement/mappings/<migration_pair>.yaml`. The mapping file declares the
source/target migration pair and a dictionary of module replacements.

### Step 4: Match imports against the mapping

For each import in `imports.json`:

1. Extract the `attrs.module` value
2. Look it up in the mapping's `mappings` dictionary
3. Use the mapping's `match_strategy` to control matching:
   - `exact`: module must equal the mapping key
   - `prefix`: module must start with the mapping key (for hierarchical packages like Java's `javax.servlet.http` matching a `javax.servlet` rule)

**Parent-module fallback for exact matching:** treeloom stores the full dotted
module path (e.g., `distutils.core` not `distutils`). Under exact matching, if
no key matches the full module, try progressively shorter parent prefixes:
`distutils.core` -> `distutils`. This catches submodule imports like
`import distutils.core` against a `distutils` mapping key without switching to
prefix matching (which is unsafe for flat namespaces where `thread` must not
match `threading`).

### Step 5: Classify each match

Each matched import falls into one of these categories based on the mapping
entry's `action` field:

| Action | Meaning | What to do |
|--------|---------|------------|
| `rename` | Module exists under a different name | Update import to `target_module` |
| `removed` | Module was removed in a specific version | Check `removed_in` vs target version; use `replacements` list |
| `split` | Module was split into multiple modules | Use `import_transforms` to route each symbol to its new module |
| `choice` | Replacement depends on usage context | Present alternatives; agent or human must analyze usage to pick |

For `removed` entries with a `removed_in` field: if the target version is
lower than `removed_in`, downgrade the finding to advisory (the module still
works but will break in a future version).

### Step 6: Produce output

Generate two artifacts:

**library-replacements.json** — Structured report:
```json
{
  "metadata": {
    "migration_pair": "py2to3",
    "source": {"language": "python", "version": "2.7"},
    "target": {"language": "python", "version": "3.11"},
    "codebase_path": "/path/to/project",
    "total_files_scanned": 42
  },
  "findings": [
    {
      "file": "src/config.py",
      "line": 3,
      "module": "ConfigParser",
      "names": ["ConfigParser"],
      "action": "rename",
      "target_module": "configparser",
      "notes": "Config file parsing"
    }
  ],
  "summary": {
    "total_imports_scanned": 150,
    "matches": 12,
    "by_action": {"rename": 8, "removed": 3, "choice": 1}
  }
}
```

**library-replacements.md** — Human-readable report listing findings grouped by
action type, any new dependencies needed, and items requiring manual review
(choice actions, unresolved imports).

### Verification

The skill succeeded if:
- Every import in the codebase was checked against the mapping
- All `rename` and `removed` findings have a concrete replacement recommendation
- All `choice` findings are flagged for human/agent review with the alternatives listed
- The JSON report parses cleanly and the summary counts are consistent

## Mapping File Format

Mapping files live in `skills/library-replacement/mappings/` and use YAML. Each file defines replacements
for one source->target migration pair.

### Top-level fields

```yaml
migration:
  id: py2to3                              # unique identifier, used with --migration-pair
  source: { language: python, version: "2.7" }
  target: { language: python, version: "3.11" }
  description: "Human-readable description"

match_strategy: exact | prefix            # how to match import modules against keys

mappings:                                 # the replacement dictionary
  <module_key>:
    action: rename | removed | split | choice
    # ... action-specific fields
```

### Action: rename

The module exists in the target under a different name.

```yaml
ConfigParser:
  action: rename
  target_module: configparser
  notes: "Config file parsing"
  import_transforms:                      # optional: per-symbol routing
    ConfigParser.ConfigParser: configparser.ConfigParser
    ConfigParser.SafeConfigParser: configparser.ConfigParser
```

**Note on `import_transforms`:** This field supports two formats:
- **Dict format** `{old_path: new_path}` for simple 1:1 symbol mappings
- **List format** `[{from_import, to_import, condition?, notes?}]` for context-dependent replacements (used with `split` and `choice` actions)

Implementations should detect the format from the data type (dict vs list), not from the action type.

### Action: removed

The module was removed from the standard library or platform in a specific version.

```yaml
distutils:
  action: removed
  removed_in: "3.12"
  replacements:
    - library: setuptools
      install: "pip install setuptools"   # or Maven coordinates for Java
      import_transforms:                  # optional
        distutils.core.setup: setuptools.setup
      notes: "Critical blocker for 3.12+"
```

### Action: split

The module was split into multiple target modules.

```yaml
urllib2:
  action: split
  description: "urllib2 split into urllib.request, urllib.error, urllib.parse"
  import_transforms:
    - from_import: urllib2.Request
      to_import: urllib.request.Request
    - from_import: urllib2.HTTPError
      to_import: urllib.error.HTTPError
```

### Action: choice

The replacement depends on usage context. The agent (or human) must analyze
how the import is used to pick the right replacement.

```yaml
cStringIO:
  action: choice
  description: "cStringIO -> io.StringIO or io.BytesIO depending on usage"
  import_transforms:
    - from_import: cStringIO.StringIO
      to_import: io.BytesIO
      condition: "if handling bytes data"
    - from_import: cStringIO.StringIO
      to_import: io.StringIO
      condition: "if handling text data"
```

## Available Mappings

| File | Migration | Entries | Match Strategy |
|------|-----------|---------|----------------|
| `py2to3.yaml` | Python 2.7 -> 3.11 | 40 | exact |
| `java8to17.yaml` | Java 8 -> 17 | 7 | prefix |

## Adding a New Mapping

To support a new migration pair:

1. Create `skills/library-replacement/mappings/<id>.yaml` following the format above
2. Populate the `migration` header with source/target metadata
3. Choose `match_strategy` based on the language's import model:
   - `exact` for flat namespaces (Python, Ruby, Go)
   - `prefix` for hierarchical packages (Java, C#, Kotlin)
4. Add entries for known library changes. Start with the highest-impact
   removals and renames; completeness can come later.
5. Test by running treeloom against a sample codebase and matching manually

## Tool Dependencies

- **treeloom** (>= 0.4.0): Code property graph builder with multi-language import extraction
- **PyYAML** or equivalent: For loading mapping files (or use JSON-compatible YAML subset)

## References

- `skills/library-replacement/mappings/py2to3.yaml` — Full Python 2->3 stdlib replacement mapping
- `skills/library-replacement/mappings/java8to17.yaml` — Java 8->17 Jakarta EE + JDK removal mapping (starter)
