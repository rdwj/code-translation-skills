# Script Offload Plan — Moving Work Out of the LLM

## Problem

We're hitting API usage limits. Every time the LLM reads a file, counts patterns, runs a tool, builds a graph, or generates a report from a template, that consumes tokens. Much of this work is deterministic — it follows explicit rules, not judgment. Deterministic work should run as Python/bash scripts at zero token cost, with the LLM only involved for decisions that require reasoning.

## Principle

**The LLM is the orchestrator and decision-maker, not the worker.** Scripts do the heavy lifting. The LLM reads script output and decides what to do next.

Think of it this way: the LLM should never traverse a directory, parse a file, count occurrences, compare strings, do arithmetic, or fill in a template. Those are script jobs. The LLM should decide strategy, handle ambiguous cases, and communicate with the human.

## The Token Tax

Every skill invocation currently costs tokens in three ways:

1. **Skill prompt loading** — The SKILL.md itself consumes context tokens when loaded
2. **Work execution** — The LLM reading/writing files, running tools, processing output
3. **Orchestration overhead** — The LLM deciding what to run next, tracking state, generating handoffs

Scripts eliminate #2 entirely. Good skill design minimizes #1 (concise SKILL.md) and #3 (scripts that output clear next-step recommendations).

## Offload Categories

### Category A: Fully Scriptable (LLM cost → zero)

These tasks follow deterministic rules. A script can do 100% of the work. The LLM just runs the script and reports the result to the user.

| Task | Current token cost | Script approach |
|------|-------------------|-----------------|
| File/LOC counting, project sizing | Medium | `quick_size_scan.py` — grep + wc |
| Pattern inventory (Py2-isms) | Very High | `analyze.py` — AST + regex + tree-sitter |
| Dependency graph construction | Very High | `build_dep_graph.py` — import parsing + NetworkX |
| Migration state updates | Medium | `update_state.py` — JSON read/write |
| Gate checks | Medium | `check_gate.py` — threshold comparison |
| Lint execution and baseline | Medium | `run_lint.py` — subprocess + output parsing |
| Future import injection | Medium | `inject_futures.py` — AST manipulation |
| Library replacement | Medium | `replace_libs.py` — import rewriting from mapping |
| CI config generation | Low | `generate_ci.py` — template filling |
| Build system updates | Low | `update_build.py` — config file transformation |
| Completeness scanning | Medium | `check_completeness.py` — pattern grep |
| Work item generation | High | `generate_work_items.py` — pattern→tier routing |
| Tree-sitter analysis pipeline | Very High | `analyze_universal.py` — parse + extract + graph |
| Confidence scoring | Medium | `score_confidence.py` — formula application |
| Test execution + output capture | High | `run_tests_dual.py` — subprocess Py2 + Py3 |
| Report generation from templates | Medium | `generate_report.py` — Jinja2 templates |

### Category B: Mostly Scriptable (LLM cost reduced 70-90%)

These tasks have a large mechanical portion and a small reasoning portion. Scripts do the bulk work and produce a focused summary for the LLM to reason about.

| Task | Script does | LLM does | Savings |
|------|-----------|----------|---------|
| Diff classification | Run tests, capture diffs, classify against known patterns | Review "uncertain" diffs only | ~80% |
| Dead code detection | AST scan, call graph, confidence scoring | Analyze ambiguous reachability cases | ~75% |
| Contract extraction | Extract signatures, return types, exceptions, call graph | Infer implicit behaviors, validate contracts | ~60% |
| Test scaffold generation | Generate characterization tests from templates | Generate adversarial edge-case tests | ~60% |
| Serialization risk assessment | Detect patterns, apply risk rules | Assess complex protocol compatibility | ~80% |
| Conversion unit planning | SCC detection, topological sort, effort estimation | Strategy decisions for wave parallelism | ~80% |
| Type annotation | Add obvious types from docstrings/defaults | Infer complex types through control flow | ~50% |

### Category C: LLM-Essential (minimal script offload)

These tasks fundamentally require semantic reasoning. Scripts can provide context preparation but the core work is LLM.

| Task | Script prep | LLM core work |
|------|-----------|---------------|
| Bytes/string boundary decisions | Identify all boundary locations | Decide: is this variable bytes or text? |
| Dynamic pattern resolution | Identify metaclass/iterator patterns | Determine correct transformation semantics |
| Behavioral contract validation | Execute tests, collect output | Interpret why behavior changed |
| Canary deployment planning | Collect infrastructure inventory | Design rollout strategy |
| Data format semantic analysis | Inventory data layer code | Understand protocol semantics |

## Script Implementation Priorities

### P0 — Scripts That Don't Exist Yet (highest token waste)

These skills describe deterministic work but have no implementation scripts. Every invocation burns LLM tokens on work a script could do for free.

**1. `work-item-generator/scripts/generate_work_items.py`**

The entire skill is deterministic: pattern inventory in → work items out, routed by known rules. Zero LLM reasoning needed.

```
Input:  raw-scan.json, dependency-graph.json, conversion-plan.json
Output: work-items.json, work-item-queue.json, cost-estimate.json
Logic:  Pattern category → model tier (HAIKU_PATTERNS/SONNET_PATTERNS/OPUS_PATTERNS)
        Pattern + context → token estimate
        Sort by wave, then file affinity, then line number
        Aggregate costs by tier
```

**2. `universal-code-graph/scripts/analyze_universal.py`**

Orchestrates tree-sitter + NetworkX. The entire pipeline is tool invocation, not reasoning.

```
Input:  codebase path, optional language filter
Output: call-graph.json, dependency-graph.json, language-summary.json, codebase-graph.graphml
Logic:  Detect languages → load grammars → parse files → run .scm queries → build graph → export
```

**3. `translation-verifier/scripts/verify_translation.py`**

Test execution + output comparison + confidence scoring. The scoring formula is literally an algorithm.

```
Input:  source code, target code, behavioral-contracts.json, test suite
Output: verification-result.json, contract-violation-report.json
Logic:  Run tests on source → capture output
        Run tests on target → capture output
        Compare per-clause → pass/fail/unverifiable
        Score = passed / (passed + failed) * weight
        Classify failures against known expected-difference patterns
        Flag uncertain failures for LLM review
```

**4. `behavioral-contract-extractor/scripts/extract_contracts.py`**

The infrastructure layer is AST-based. LLM only needed for inferring implicit behaviors.

```
Input:  raw-scan.json, call-graph.json, test files
Output: behavioral-contracts.json (with confidence flags)
Logic:  For each function (topological order):
          Extract signature → inputs
          Extract return statements → outputs
          Extract raise statements → error_conditions
          Track calls to I/O, logging, network → side_effects
          Check for py2-specific behaviors → implicit_behaviors
          Flag low-confidence contracts for LLM review
```

**5. `haiku-pattern-fixer/scripts/apply_fix.py`**

Each fix follows a known pattern transformation. Could be a sed-like script.

```
Input:  work-item.json (single item with pattern, location, context)
Output: fixed source code, verification result
Logic:  Apply known transformation (has_key → in, xrange → range, etc.)
        Run quick syntax check on result
        If test exists, run it
```

**6. `modernization-advisor/scripts/check_modernization.py`**

Simple library mapping is a lookup table, not reasoning.

```
Input:  raw-scan.json, dependency-graph.json
Output: modernization-opportunities.json
Logic:  Check imports against known modernization table:
          six → remove
          old-style format strings → f-strings
          os.path → pathlib
          urllib2 → requests (if available)
          manual context management → with statement
        Flag complex opportunities for Sonnet review
```

**7. `migration-dashboard/scripts/generate_dashboard.py`**

HTML generation from JSON data. Pure templating.

```
Input:  migration-state.json, gate-check-report.json, dependency-graph.json
Output: migration-dashboard.html
Logic:  Read JSON → inject into HTML template → output self-contained HTML with embedded JS
```

### P1 — Scripts That Exist But May Punt Logic to LLM

These skills have scripts but the SKILL.md describes rules that should be IN the scripts, not left for the LLM to interpret at runtime.

**8. `behavioral-diff-generator/scripts/generate_diffs.py`** — Add diff classification rules. The known expected-difference patterns (repr changes, dict ordering, bytes repr) should be in the script's classification logic, not handled by Sonnet.

**9. `dead-code-detector/scripts/detect_dead_code.py`** — Ensure all confidence categorization rules are implemented. HIGH/MEDIUM/LOW confidence is defined by explicit rules in the SKILL.md.

**10. `completeness-checker/scripts/check_completeness.py`** — Verify all 10 artifact categories are fully implemented with all subcategories.

**11. `test-scaffold-generator/scripts/generate_tests.py`** — Ensure Jinja2 templates exist for all test categories. The SKILL.md provides literal Python test templates that should be .jinja2 files, not LLM-generated each time.

**12. `serialization-detector/scripts/detect_serialization.py`** — Verify all 10 serialization categories and risk rules are implemented.

### P2 — Existing Scripts That Are Fine

These skills already have complete scripts and correct model tier guidance. No changes needed.

- migration-state-tracker (init_state.py, update_state.py, query_state.py)
- gate-checker (check_gate.py, generate_gate_report.py)
- lint-baseline-generator (scripts handle tool invocation)
- c-extension-flagger (scripts handle pattern detection)
- encoding-stress-tester (scripts handle test generation)
- performance-benchmarker (scripts handle benchmark execution)
- future-imports-injector (scripts handle AST manipulation)
- library-replacement (scripts handle import rewriting)
- build-system-updater (scripts handle config transformation)
- ci-dual-interpreter (scripts handle CI config generation)
- custom-lint-rules-generator (scripts handle rule generation)

## Script Design Pattern

All new scripts should follow this pattern to minimize LLM involvement:

```python
#!/usr/bin/env python3
"""
Script: <name>
Purpose: <what it does>
Inputs: <what files it reads>
Outputs: <what files it writes>
LLM involvement: NONE (or: FLAGS items for LLM review)
"""

import argparse
import json
import sys

def main():
    parser = argparse.ArgumentParser(description="...")
    parser.add_argument("input", help="Path to input file")
    parser.add_argument("--output", "-o", help="Output directory", default=".")
    args = parser.parse_args()

    # 1. Read inputs
    # 2. Process deterministically
    # 3. Write outputs
    # 4. Print summary to stdout (this is what the LLM sees)
    #    Keep summary SHORT — just key metrics and any items flagged for review

    # Example summary output:
    print(json.dumps({
        "status": "complete",
        "items_processed": 42,
        "items_flagged_for_review": 3,
        "flagged_items": ["func_a (uncertain contract)", "func_b (ambiguous type)", "module_c (complex shim)"],
        "output_files": ["work-items.json", "cost-estimate.json"]
    }, indent=2))

if __name__ == "__main__":
    main()
```

Key design rules:

1. **Print a JSON summary to stdout.** The LLM reads this, not the full output files. Keep it under 50 lines.
2. **Write detailed output to files on disk.** Downstream scripts read from disk, not from conversation.
3. **Flag items for LLM review** rather than trying to handle ambiguity. A list of 3 flagged items costs far fewer tokens than processing 100 items through the LLM.
4. **Exit codes matter.** 0 = success, 1 = partial (some items flagged), 2 = failure. The LLM checks the exit code before reading output.
5. **No interactive prompts.** Scripts run unattended.

## Estimated Token Savings

If all P0 and P1 scripts are implemented:

| Workflow | Before (est. tokens) | After (est. tokens) | Savings |
|----------|---------------------|---------------------|---------|
| Express (small project) | ~50K | ~10K | 80% |
| Standard (medium project) | ~300K | ~80K | 73% |
| Full (large project) | ~2M+ | ~500K | 75% |

The savings come from:
- No LLM file traversal (scripts walk the codebase)
- No LLM pattern matching (scripts grep and AST-parse)
- No LLM arithmetic (scripts compute scores and estimates)
- No LLM report generation (scripts use templates)
- Focused LLM input (scripts output summaries, not raw data)

## Relationship to Model Tier Guide

The MODEL-TIER-GUIDE.md defines which model to use when the LLM IS involved. This plan defines when the LLM should NOT be involved at all. They complement each other:

1. Script runs → produces output + flags
2. If no flags: LLM just reports result (Haiku, minimal tokens)
3. If flags: LLM reviews flagged items (model tier per the guide)
4. LLM decides next step (always Haiku for orchestration)
