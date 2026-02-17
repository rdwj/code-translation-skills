---
name: py2to3-dynamic-pattern-resolver
description: >
  Resolve semantic Python 2→3 patterns that require code understanding to fix correctly.
  Trigger on metaclass, exec, eval, dynamic import, __cmp__, __nonzero__, __unicode__,
  __div__, integer division, map/filter/zip returning iterators, dict views, sorted
  cmp parameter, buffer, apply, reduce, __hash__, comparison operators, __getslice__,
  __setslice__, __delslice__, and other dynamic language features that changed between
  Python 2 and 3.
---

# Dynamic Pattern Resolver

Handle Python language features that changed semantically between Py2 and Py3, where
the Automated Converter (Skill 2.2) cannot determine the correct fix without understanding
code semantics. This skill patterns that require semantic analysis — not just syntax
transformation — to migrate correctly.

These are patterns that the regex-based Automated Converter skipped, or patterns that
need context-aware AST transformation to fix safely.

## When to Use

- When the Automated Converter marks files as needing semantic analysis
- After Phase 1 (print fix) and Phase 2 (imports) are complete
- When you need to resolve class transformation patterns (__metaclass__, __cmp__, etc.)
- When you need to fix iterator vs list issues (map/filter/zip)
- When you need to handle division operator changes intelligently
- When you need to audit dynamic features (eval, exec, getattr, etc.)

## Inputs

The user provides:
- **conversion_unit_path**: Path to a single Python file or directory of files
- **--target-version**: Python 3 version target (e.g., `3.9`, `3.11`)
- **--state-file**: JSON state file from previous phases (tracks decisions)
- **--output**: Directory to write fixed files and reports
- **--phase0-dir**: Path to Phase 0 discovery output (for risk context)
- **--dry-run**: Show what would be changed without modifying files
- **--auto-only**: Only auto-fix high-confidence patterns; skip ambiguous ones
- **--conversion-plan**: Path to conversion plan JSON (from skill 2.2)

## Outputs

All outputs go into the `--output` directory:

| File | Format | Purpose |
|------|--------|---------|
| Fixed source files | Python | Modified files with semantic patterns resolved |
| `dynamic-pattern-report.json` | JSON | Every pattern found, resolution method, and context |
| `manual-review-needed.json` | JSON | Ambiguous patterns requiring human decision |
| `dynamic-pattern-summary.md` | Markdown | Human-readable summary of changes |

## Pattern Categories & Transformation Rules

This skill handles the following pattern categories:

**1. Class Transformation Patterns**: __metaclass__, __nonzero__, __unicode__, __div__, __getslice__/__setslice__/__delslice__, __cmp__, __hash__

**2. Builtin Function Changes**: map(), filter(), zip(), dict.keys/values/items(), sorted(cmp=), reduce(), apply(), buffer(), cmp(), execfile(), reload()

**3. Integer Division**: / operator on int operands

**4. exec Statement Edge Cases**: exec with old statement syntax

**5. Comparison Operators with Mixed Types**: Comparing incompatible types

For each pattern category:
- Understand the Py2 vs Py3 semantic difference
- Determine if auto-fixable (YES/PARTIAL/CONDITIONAL/NO)
- Apply systematic transformation or flag for review

See `references/EXAMPLES.md` for:
- Detailed before/after code examples for all patterns
- Pattern detection matrix (type, auto-fixability, confidence levels)
- Complete workflow state tracking

## Workflow

### Step 1: Scan Files for Dynamic Patterns

```bash
python3 scripts/resolve_patterns.py <path> \
    --target-version 3.9 \
    --output <output_dir> \
    --dry-run
```

The script uses AST analysis to find all dynamic patterns:
1. Walk AST of each file.
2. Identify all pattern types (see categories above).
3. Classify each as auto-fixable or needs-review.
4. Generate context (surrounding code, usage analysis).

### Step 2: Auto-Fix High-Confidence Patterns

For patterns classified as auto-fixable:
1. Generate AST transformation.
2. Apply transformation to source.
3. Record in `dynamic-pattern-report.json`.

### Step 3: Flag Ambiguous Patterns

For patterns that need human decision:
1. Capture full context (function/class scope, surrounding code).
2. Record in `manual-review-needed.json` with explanation.
3. Suggest possible fixes.

### Step 4: Generate Reports

Run `scripts/generate_pattern_report.py` to produce human-readable markdown summary:

```bash
python3 scripts/generate_pattern_report.py <output_dir>
```

## Integration with State Tracker

The skill records all decisions in `--state-file` (JSON) including:
- Skill name, phase, timestamp
- Pattern counts by type (metaclass, nonzero, __cmp__, map_filter_zip, dict_views, etc.)
- Counts of auto-fixed and manual review patterns
- Per-decision records (file, line, pattern, action, details)

See `references/EXAMPLES.md` for complete dynamic pattern report structure and workflow state tracking.

## Files Modified

This skill modifies source files in-place (or to --output directory):
- All patterns in target files are transformed
- Original files backed up to `{file}.py2` if desired
- All changes tracked in state file

## Notes & Limitations

- **Type inference**: Uses AST and heuristics; may have false positives on ambiguous code.
- **Dynamic code**: Cannot analyze code in strings (eval, exec'd code, etc.) — flagged for review.
- **Complex logic**: Patterns with intricate semantics (e.g., custom `__cmp__` with side effects)
  are flagged for human review.
- **Test coverage**: Recommend running tests after each skill to validate transformations.


## Model Tier

**Sonnet** (with Haiku pre-processing). Resolving metaclass transformations, `__cmp__` to rich comparison methods, and iterator semantic changes requires understanding what the code intends, not just what it looks like.

Decomposition: Haiku identifies all dynamic patterns (metaclass usage, __cmp__, map/filter/zip consumption patterns). Sonnet receives each pattern with its call context and determines the correct transformation. One Sonnet call per pattern, not per file.

## References

- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
