---
name: work-item-generator
description: >
  Decompose migration analysis outputs into atomic, executable work items tagged with
  optimal model tiers (Haiku/Sonnet/Opus). Use this skill whenever you need to break a
  migration into the smallest possible executable units, determine which model can safely
  handle each item, generate cost projections by model, or produce a work queue that can
  be distributed to sub-agents with full context and verification. Also trigger when someone
  says "decompose the work," "generate work items," "what can haiku handle," "break down the
  migration," "route to models," "estimate migration cost," "create the work queue," or
  "how many opus-tier tasks are there." This is the tactical bridge between strategic
  planning and mechanical execution.
---

# Work Item Generator

The Conversion Unit Planner (Skill 1.0) groups modules into waves and identifies critical
paths. This skill takes that further: it breaks each conversion unit into the smallest atomic
work items, routes each item to the cheapest model that can handle it reliably, orders items
for optimal context reuse, and produces a work queue with full task description, verification
steps, and rollback instructions.

## Why Atomic Decomposition Matters

A "conversion unit" might contain 10 files with 200 Python 2-isms. Converting the whole unit
at once creates context bloat, reduces verification accuracy, and wastes expensive model
invocations on tasks that cheaper models could handle. Decomposing into atomic items:

- Each item is small enough to fit in a Haiku context window with full surrounding code
- Verification is precise (one behavioral contract per item, not 200)
- Failed items can be re-routed to Sonnet or Opus without losing passed items
- Parallel execution becomes practical (N agents on N work items simultaneously)
- Cost is minimized (70% of items run on Haiku, 25% on Sonnet, 5% on Opus)

## Inputs

- **raw-scan.json**: From Skill 0.1 (Codebase Analyzer). Contains pattern inventory with file locations and severity.
- **dependency-graph.json**: From Skill 0.1. Module dependency structure and call graph.
- **conversion-plan.json**: From Skill 1.0 (Conversion Unit Planner). Ordered conversion units with module groupings.
- **behavioral-contracts.json** (optional): From behavioral-contract-extractor. Per-function behavioral specifications. If not provided, work items use pattern-based verification.

## Outputs

| File | Format | Purpose |
|------|--------|---------|
| `work-items.json` | JSON | Ordered list of atomic work items with full context and routing |
| `work-item-summary.md` | Markdown | Human-readable queue overview with per-model breakdown |
| `model-tier-estimate.json` | JSON | Cost and effort projection by model tier |

## Work Item Structure

Each work item is a complete, self-contained task:

```json
{
  "id": "wi-0001-utils-common-print-statements",
  "unit": "utils-common",
  "wave": 1,
  "type": "pattern_fix",
  "model_tier": "haiku",
  "priority": 1,
  "context": {
    "file": "src/utils/common.py",
    "function": "format_message",
    "function_source": "def format_message(msg, level):\n    print 'Level:', level\n    print msg",
    "dependencies": [],
    "imports": ["sys", "os"]
  },
  "task": {
    "pattern": "print_statement",
    "line": 5,
    "current_code": "    print 'Level:', level",
    "fix_description": "Convert Python 2 print statement to print() function call",
    "expected_result": "    print('Level:', level)"
  },
  "verification": {
    "behavioral_contract": "Input string 'test' with level='INFO' outputs 'Level: INFO\\ntest' to stdout",
    "test_command": "python -m pytest test/test_utils.py::test_format_message -xvs",
    "rollback_command": "git checkout src/utils/common.py"
  },
  "context_budget": 4096,
  "estimated_tokens": 850,
  "tags": ["stdlib_fix", "syntax_only", "automatable"]
}
```

### Field Descriptions

| Field | Type | Purpose |
|-------|------|---------|
| `id` | string | Unique work item ID: `wi-NNNN-unit-pattern` |
| `unit` | string | Conversion unit this item belongs to |
| `wave` | integer | Conversion wave (1, 2, 3, ...) from conversion plan |
| `type` | string | `pattern_fix`, `import_rewrite`, `test_generation`, `report_generation`, or `complex_refactor` |
| `model_tier` | string | `haiku`, `sonnet`, or `sonnet+opus_review` |
| `priority` | integer | 1 (highest) to N. Within a wave, execute in priority order. |
| `context` | object | Code context: file, function, source, dependencies, imports |
| `task` | object | What to fix: pattern, line number, current code, fix description, expected result |
| `verification` | object | How to verify: contract summary, test command, rollback command |
| `context_budget` | integer | Recommended context window size for this item (bytes) |
| `estimated_tokens` | integer | Estimated Claude token count for full item (input + generation) |
| `tags` | array | Categorization: `[syntax_only, semantic, data_layer, automatable, requires_review, ...]` |

## Work Item Types

### 1. `pattern_fix`
Single pattern occurrence in a single location. Examples: one `print` statement, one `has_key()`, one `except` comma syntax.

**Model tiers**: Haiku (90%), Sonnet (10%)

**Example**:
```json
{
  "type": "pattern_fix",
  "task": {
    "pattern": "has_key",
    "current_code": "if d.has_key('name'):",
    "expected_result": "if 'name' in d:"
  }
}
```

### 2. `import_rewrite`
Single import statement rewrite (rename or replace). Examples: `ConfigParser` → `configparser`, `__future__` addition, relative import fix.

**Model tiers**: Haiku (85%), Sonnet (15%)

**Example**:
```json
{
  "type": "import_rewrite",
  "task": {
    "pattern": "stdlib_rename",
    "current_code": "from ConfigParser import ConfigParser",
    "expected_result": "from configparser import ConfigParser"
  }
}
```

### 3. `test_generation`
Generate or adapt tests for a pattern fix. May involve creating new test files or adding assertions.

**Model tiers**: Sonnet (60%), Opus (40%)

**Example**:
```json
{
  "type": "test_generation",
  "task": {
    "pattern": "string_bytes_mixing_test",
    "fix_description": "Create test_encode_decode.py to verify string/bytes handling",
    "expected_result": "Test file with 5 encoding scenarios and assertions"
  }
}
```

### 4. `report_generation`
Syntactic validation or impact reporting. Examples: "List all files using `cmp()`," "Report files with no encoding declaration," "Check for deprecated urllib usage."

**Model tiers**: Haiku (70%), Sonnet (30%)

**Example**:
```json
{
  "type": "report_generation",
  "task": {
    "fix_description": "Scan src/ for cmp() calls and produce CSV of locations",
    "expected_result": "CSV: file,line,context"
  }
}
```

### 5. `complex_refactor`
Multi-step refactoring that affects multiple files or requires architectural reasoning. Examples: metaclass migration, division operator fix with test suite validation, C extension wrapper creation.

**Model tiers**: Sonnet (30%), Opus (70%)

**Example**:
```json
{
  "type": "complex_refactor",
  "task": {
    "pattern": "metaclass_migration",
    "fix_description": "Convert 3 metaclass definitions from __metaclass__ syntax to metaclass= keyword, update all subclasses",
    "expected_result": "All subclasses inherit correctly, tests pass"
  }
}
```

## Model Routing Rules

Work items are routed to the cheapest model that can reliably handle them. These percentages
are empirical — based on analysis of the raw patterns and test results from similar migrations.

### Haiku-Tier Patterns (~70% of work items)

Haiku can handle these reliably because they are mechanical, single-pattern, syntax-only fixes
with no semantic reasoning required:

- `has_key()` → `in` operator
- `iteritems()` / `iterkeys()` / `itervalues()` → `.items()` / `.keys()` / `.values()`
- `xrange()` → `range()`
- `raw_input()` → `input()`
- `print` statement → `print()` function
- `unicode` builtin → `str`
- `long` builtin → `int` (suffix removal)
- `except Error, e:` → `except Error as e:`
- `raise ValueError, msg` → `raise ValueError(msg)`
- Octal literal `0777` → `0o777`
- Stdlib renames: `urllib2` → `urllib.request`, `ConfigParser` → `configparser`, etc.
- `from __future__ import` additions
- String repr with backticks → `repr()`
- `<>` operator → `!=`

**Verification**: Pattern matching + simple test execution

**Context needed**: File + function source + surrounding imports

**Cost per item**: ~$0.001–0.002 (10K tokens)

### Sonnet-Tier Patterns (~25% of work items)

Sonnet needed for patterns requiring moderate semantic reasoning or multi-file changes:

- `__metaclass__` → `metaclass=` keyword (with subclass validation)
- String/bytes mixing: decode/encode logic, file I/O encoding declaration
- `struct.pack()` / `unpack()` mixed with string operations
- `pickle` / serialization compatibility
- Division operator `/` → `//` (requires dataflow analysis to determine when true division is needed)
- Dynamic imports: `__import__()`, `importlib` usage with conditional logic
- `map()` / `filter()` wrapping in `list()` calls (requires checking if indexing needed)
- Encoding detection and declaration across a module
- Test suite adaptation for removed builtins
- C extension wrapper generation

**Verification**: Behavioral contract validation + test suite run

**Context needed**: File + related modules + test files + behavioral contract

**Cost per item**: ~$0.004–0.01 (40K tokens)

### Opus-Tier Patterns (~5% of work items)

Opus needed for architectural decisions or patterns requiring full-codebase reasoning:

- C extension usage and replacement strategy
- Custom codec implementation and maintenance
- Thread safety concerns in migration (GIL changes, lock semantics)
- Monkey patching detection and refactoring
- Dynamic metaclass generation with runtime dispatch
- Complex data serialization formats (EBCDIC, mainframe protocols)
- Performance-critical patterns (list vs. iterator decisions with measurement)
- Security implications (pickle security, code injection risks)

**Verification**: Full behavioral contract + integration test suite + security review

**Context needed**: Full module graph + test suite + behavioral contracts + performance benchmarks

**Cost per item**: ~$0.02–0.05 (100K+ tokens)

## Ordering and Dependency Safety

Work items are ordered within each wave to maximize context reuse and minimize rework:

1. **Leaf-module first**: Items from modules with no dependencies come before gateway modules
2. **File affinity**: Items from the same file are grouped (context reuse)
3. **Function affinity**: Items affecting the same function are adjacent
4. **Dependency-aware**: If item A modifies imports and item B uses them, A comes first
5. **Type clustering**: Pattern fixes before import rewrites before test generation

Example ordering:
```
Wave 1, Priority 1: src/utils/common.py:print_statements (3 items)
Wave 1, Priority 2: src/utils/common.py:has_key_calls (2 items)
Wave 1, Priority 3: src/utils/helpers.py:stdlib_renames (5 items)
Wave 1, Priority 4: tests/test_utils.py:test_generation (2 items)
...
Wave 2, Priority 1: src/data/models.py:metaclass_migration (1 complex_refactor)
```

## Cost Estimation

The `model-tier-estimate.json` output projects total cost:

```json
{
  "summary": {
    "total_work_items": 427,
    "total_estimated_tokens": 2840000,
    "total_estimated_cost_usd": 28.40,
    "estimated_time_serial_hours": 12.5,
    "estimated_time_parallel_hours": 2.1
  },
  "by_tier": {
    "haiku": {
      "count": 299,
      "percent": 70,
      "estimated_tokens": 2000000,
      "estimated_cost_usd": 4.00,
      "avg_tokens_per_item": 6688,
      "avg_time_minutes": 1.8
    },
    "sonnet": {
      "count": 107,
      "percent": 25,
      "estimated_tokens": 700000,
      "estimated_cost_usd": 21.00,
      "avg_tokens_per_item": 6542,
      "avg_time_minutes": 3.2
    },
    "opus": {
      "count": 21,
      "percent": 5,
      "estimated_tokens": 140000,
      "estimated_cost_usd": 3.40,
      "avg_tokens_per_item": 6667,
      "avg_time_minutes": 6.5
    }
  },
  "by_type": {
    "pattern_fix": {
      "count": 289,
      "percent": 68,
      "estimated_cost_usd": 3.50
    },
    "import_rewrite": {
      "count": 94,
      "percent": 22,
      "estimated_cost_usd": 18.40
    },
    "test_generation": {
      "count": 32,
      "percent": 8,
      "estimated_cost_usd": 4.80
    },
    "report_generation": {
      "count": 10,
      "percent": 2,
      "estimated_cost_usd": 1.20
    },
    "complex_refactor": {
      "count": 2,
      "percent": 0.5,
      "estimated_cost_usd": 0.50
    }
  },
  "wave_breakdown": [
    {
      "wave": 1,
      "items": 89,
      "cost_usd": 2.30,
      "critical_path_items": true
    },
    {
      "wave": 2,
      "items": 156,
      "cost_usd": 4.80,
      "critical_path_items": false
    }
  ]
}
```

## Workflow

### Step 1: Parse Inputs

Load the four input files:
- `raw-scan.json`: Extract per-file pattern inventory with line numbers and severity
- `dependency-graph.json`: Extract module structure, imports, call graph
- `conversion-plan.json`: Extract unit groupings and wave ordering
- `behavioral-contracts.json` (optional): Extract per-function specifications

### Step 2: Explode Patterns into Work Items

For each conversion unit in order:
  For each file in the unit:
    For each pattern occurrence in the file:
      Create a `pattern_fix` work item with full context
      If pattern affects imports: create an `import_rewrite` item
    For each function modified: create or link to a `test_generation` item

### Step 3: Route to Models

For each work item:
  1. Look up pattern type in the routing table (see Model Routing Rules)
  2. Check if behavioral contract exists (prefer Sonnet/Opus)
  3. If pattern complexity > medium, upgrade to Sonnet
  4. If pattern requires multi-file reasoning, upgrade to Opus
  5. If verification is complex (encoding, thread safety), upgrade tier
  6. Set `model_tier` and `estimated_tokens`

### Step 4: Order Work Items

Within each wave, sort by:
  1. File (group by file)
  2. Pattern type (fixes before rewrites before generation)
  3. Line number (top to bottom within file)

Assign ascending `priority` values.

### Step 5: Generate Outputs

1. Write `work-items.json` with all items
2. Generate `work-item-summary.md` with per-model breakdown and sample items
3. Generate `model-tier-estimate.json` with cost projection

## Work Item Summary (Example)

The `work-item-summary.md` provides a human-readable overview:

```markdown
# Work Item Summary

## Overview
- **Total work items**: 427
- **Conversion units**: 23
- **Conversion waves**: 8
- **Estimated duration (serial)**: 12.5 hours
- **Estimated duration (parallel, 3 agents)**: 2.1 hours
- **Estimated cost**: $28.40

## Work Items by Model Tier

### Haiku Tier (70% of work)
- **Count**: 299 items
- **Estimated cost**: $4.00
- **Average time per item**: 1.8 minutes
- **Patterns**: print statements, has_key, xrange, except syntax, stdlib renames, etc.

**Top 5 patterns**:
1. print_statement (89 items)
2. has_key (67 items)
3. stdlib_rename (45 items)
4. except_syntax (43 items)
5. xrange (55 items)

### Sonnet Tier (25% of work)
- **Count**: 107 items
- **Estimated cost**: $21.00
- **Average time per item**: 3.2 minutes
- **Patterns**: metaclass migration, string/bytes mixing, struct usage, encoding, etc.

**Top 5 patterns**:
1. string_bytes_mixing (34 items)
2. encode_decode (28 items)
3. import_dynamic (22 items)
4. metaclass (15 items)
5. struct_usage (8 items)

### Opus Tier (5% of work)
- **Count**: 21 items
- **Estimated cost**: $3.40
- **Average time per item**: 6.5 minutes
- **Patterns**: C extensions, custom codecs, thread safety, monkey patching

**Items**:
1. c_extension_wrapper_protocol_handler (1 item)
2. thread_safety_scada_queue (1 item)
3. monkey_patch_datetime (1 item)
... (18 more)

## Work Items by Type

| Type | Count | Percent | Examples |
|------|-------|---------|----------|
| pattern_fix | 289 | 68% | print statement, has_key, xrange fixes |
| import_rewrite | 94 | 22% | stdlib renames, future imports |
| test_generation | 32 | 8% | Adapting test suites for removed builtins |
| report_generation | 10 | 2% | Inventory of deprecated patterns |
| complex_refactor | 2 | 0.5% | Metaclass migration with subclass updates |

## Sample Work Items

### Haiku: Print Statement Fix
```
ID: wi-0001-utils-common-print-statements
Unit: utils-common
Type: pattern_fix
Model: Haiku
Priority: 1
File: src/utils/common.py
Line: 45
Current: print "Warning:", msg
Expected: print("Warning:", msg)
Verification: test_utils.py::test_format_message
```

### Sonnet: Metaclass Migration
```
ID: wi-0180-data-models-metaclass
Unit: data-models
Type: complex_refactor
Model: Sonnet
Priority: 1
Files: src/data/models.py (3 classes), src/data/base.py (5 subclasses)
Current: class Meta(object):
           __metaclass__ = MyMeta
Expected: class Meta(object, metaclass=MyMeta):
Verification: test_data.py::test_metaclass_dispatch (15 assertions)
```

### Opus: C Extension Wrapper
```
ID: wi-0397-extensions-protocol-handler
Unit: extensions
Type: complex_refactor
Model: Opus
Priority: 1
Files: src/extensions/protocol_handler.c, src/extensions/wrapper.py, test/test_extensions.py
Task: Verify C extension compatibility with Py3.12 ABI, update PyObject handling
Verification: Full integration test suite + performance benchmark
```

## Per-Wave Cost Breakdown

| Wave | Items | Haiku | Sonnet | Opus | Total Cost |
|------|-------|-------|--------|------|-----------|
| 1 | 89 | $1.20 | $0.80 | $0.30 | $2.30 |
| 2 | 156 | $2.10 | $2.10 | $0.60 | $4.80 |
| ... | ... | ... | ... | ... | ... |
| 8 | 34 | $0.40 | $0.50 | $0.10 | $1.00 |
| **Total** | **427** | **$4.00** | **$21.00** | **$3.40** | **$28.40** |
```

## Integration with Other Skills

This skill feeds into:

- **haiku-pattern-fixer**: Executes all Haiku-tier work items in batch
- **automated-converter**: Processes Sonnet/Opus items with context and verification
- **modernization-advisor**: Suggests idiomatic alternatives for converted patterns
- **translation-verifier**: Uses work item verification steps to validate behavior preservation
- **migration-dashboard**: Displays work item queue and progress by model tier

This skill consumes:

- **py2to3-codebase-analyzer** (Skill 0.1): `raw-scan.json`, `dependency-graph.json`
- **py2to3-conversion-unit-planner** (Skill 1.0): `conversion-plan.json`
- **behavioral-contract-extractor** (optional): `behavioral-contracts.json`

## Important Notes

**Context is a first-class concern.** Each work item includes enough surrounding code that
a model can understand the fix in isolation. A Haiku fixing a `print` statement doesn't need
to know the entire module — just the function and its imports. This is why we decompose.

**Verification is per-item, not per-unit.** Rather than running the full test suite after
converting an entire unit, each work item includes its own test command. This enables
parallel execution and fast failure detection.

**Cost/quality trade-off is explicit.** The routing rules balance cost and quality empirically.
If Haiku produces poor results on a pattern, the rules are updated to route that pattern to
Sonnet instead. The percentages (70/25/5) are starting points, not gospel.

**Rollback is always possible.** Each work item includes a `rollback_command`. If a Haiku fix
fails its test, the agent can roll back and re-route to Sonnet without losing other fixes.
This creates a safe testing loop for routing rules.

## Model Tier

**Haiku.** Work item generation classifies patterns against known category lists and assigns model tiers. The classification rules are deterministic. For edge cases where pattern categorization is ambiguous, flag for human review rather than escalating to Sonnet.

## References

- `ARCHITECTURE-universal-code-graph.md` — Dependency graph structure and call graphs
- `references/SUB-AGENT-GUIDE.md` — How to delegate work items to sub-agents
- Behavioral contract extractor SKILL.md — Inferring per-function specifications
- Conversion unit planner SKILL.md — Planning conversion order and unit formation
