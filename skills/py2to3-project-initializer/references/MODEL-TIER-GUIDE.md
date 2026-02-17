# Model Tier Guide

This guide specifies which model tier (Haiku, Sonnet, Opus) to use for each skill and task type in the migration suite. When running on an API token plan, model selection directly impacts cost and speed. Use the cheapest model that produces correct results.

## Principles

1. **Default to Haiku.** Most migration work is mechanical — pattern matching, template generation, file manipulation, state tracking. Haiku handles all of this.

2. **Escalate to Sonnet for semantic reasoning.** When a task requires understanding what code means (not just what it looks like), use Sonnet. This includes bytes/string boundary decisions, behavioral contract extraction, and dynamic pattern resolution.

3. **Reserve Opus for architectural decisions.** Opus is for novel problems that require full-codebase reasoning: C extension migration strategy, custom codec design, thread safety analysis. These are rare (~5% of work items).

4. **Decompose before escalating.** Before deciding a task needs Sonnet, ask: can this be split into a Haiku-friendly detection step and a smaller Sonnet-friendly decision step? Often the answer is yes.

## Per-Skill Model Tier Table

### Always Haiku (no reasoning required)

These skills do mechanical work — pattern matching, template generation, file manipulation, state tracking, configuration. They should always run on Haiku, including when delegated as sub-agents.

| Skill | What it does | Why Haiku is sufficient |
|-------|-------------|----------------------|
| py2to3-project-initializer | Directory creation, template generation | Pure scaffolding |
| py2to3-migration-state-tracker | JSON state management | Read/write/query operations |
| py2to3-gate-checker | Threshold comparison against evidence files | Checklist verification |
| py2to3-build-system-updater | Config file transformation | Template substitution |
| py2to3-ci-dual-interpreter | CI config generation | Template substitution |
| py2to3-future-imports-injector | Import statement insertion | Mechanical AST manipulation |
| py2to3-library-replacement | Import rewriting (Py2→Py3 stdlib) | Pattern-based replacement |
| py2to3-lint-baseline-generator | Tool invocation and output parsing | Metric collection |
| py2to3-custom-lint-rules-generator | Rule generation from templates | Template-based |
| py2to3-c-extension-flagger | Pattern scan of build files | Grep-level detection |
| py2to3-completeness-checker | Pattern scan for Py2 remnants | Pattern matching |
| py2to3-encoding-stress-tester | Test generation and execution | Test infrastructure |
| py2to3-performance-benchmarker | Benchmark execution and comparison | Statistical computation |
| migration-dashboard | HTML generation from JSON data | No LLM reasoning |
| haiku-pattern-fixer | Mechanical pattern fixes at scale | Designed for Haiku |
| work-item-generator | Work item creation and tier routing | Classification from known patterns |

### Haiku with Sonnet Escalation (split the work)

These skills have a mix of mechanical and semantic work. The recommended approach is to decompose: Haiku handles the mechanical parts, Sonnet handles the reasoning parts.

| Skill | Haiku portion | Sonnet portion | Estimated split |
|-------|--------------|----------------|-----------------|
| py2to3-codebase-analyzer | File scanning, pattern detection, graph assembly | Risk assessment narrative, executive summary | 90/10 |
| py2to3-automated-converter | lib2to3 fixer execution, diff generation | Reviewing transformation conflicts | 85/15 |
| py2to3-conversion-unit-planner | Dependency graph analysis, unit formation | Risk ordering, wave strategy | 80/20 |
| py2to3-dead-code-detector | Pattern matching (code after return, unused imports) | Call graph reachability for complex cases | 75/25 |
| py2to3-serialization-detector | Pattern matching for pickle/marshal/struct calls | Protocol compatibility assessment | 80/20 |
| py2to3-compatibility-shim-remover | Simple shim removal (six, __future__) | Complex compat module interdependency analysis | 70/30 |
| py2to3-rollback-plan-generator | Dependency graph reversal, ordering | Feasibility assessment for complex rollbacks | 70/30 |
| py2to3-test-scaffold-generator | Basic input/output test pairs | Adversarial encoding test vectors | 60/40 |
| modernization-advisor | Simple library mapping (six→removal, etc.) | Architectural modernization suggestions | 50/50 |
| translation-verifier | Contract clause checking, test execution | Discrepancy analysis for complex failures | 60/40 |

**How to decompose in practice:**

When using Claude Code's Task tool for sub-agent delegation:
- Spawn the Haiku sub-agent with `model: "haiku"` for the detection/mechanical step
- If the Haiku sub-agent flags items needing deeper analysis, spawn a Sonnet sub-agent for just those items
- The Sonnet sub-agent receives only the flagged items + relevant context, not the full codebase

Example for py2to3-dead-code-detector:
```
Step 1 (Haiku): Scan all files, flag obviously dead code (after return, unused imports,
                 if PY2 blocks). Output: dead-code-candidates.json
Step 2 (Sonnet): For candidates marked "uncertain" — analyze call graph reachability,
                  determine if code is truly dead or reachable through dynamic dispatch.
                  Input: only the uncertain candidates + their call contexts.
```

### Sonnet Required (semantic reasoning)

These skills fundamentally require understanding code semantics. They cannot be fully decomposed into Haiku-friendly steps because the core task is reasoning about meaning.

| Skill | Why Sonnet is needed | Can any part use Haiku? |
|-------|---------------------|----------------------|
| py2to3-bytes-string-fixer | Must understand data semantics — is this variable bytes or text? | Yes: Haiku identifies byte/str boundary locations. Sonnet decides the fix. |
| py2to3-dynamic-pattern-resolver | Metaclass, __cmp__, iterator semantics require context | Yes: Haiku identifies patterns. Sonnet determines transformation. |
| py2to3-type-annotation-adder | Type inference requires control flow analysis | Yes: Haiku adds obvious types from docstrings. Sonnet infers complex types. |
| py2to3-data-format-analyzer | Protocol and encoding semantics | Yes: Haiku inventories data layer code. Sonnet analyzes semantics. |
| behavioral-contract-extractor | Inferring behavioral specs from code | Yes: Haiku extracts signatures/docstrings. Sonnet infers contracts. |
| py2to3-behavioral-diff-generator | Interpreting behavioral differences | Yes: Haiku runs tests and collects output. Sonnet classifies diffs. |

### Opus (rare, architectural)

Opus is needed only for decisions that require reasoning about the entire codebase architecture simultaneously. In a typical migration, Opus invocations are < 5% of total work.

| Task | When Opus is needed |
|------|-------------------|
| C extension migration strategy | Custom C API usage, ABI changes across Python versions |
| Custom codec design | EBCDIC, proprietary binary protocols |
| Thread safety analysis | GIL behavior changes affecting concurrent code |
| Monkey-patching resolution | Dynamic code modification affecting multiple modules |
| Migration strategy for novel patterns | Patterns not covered by any skill's known pattern list |

**Opus should never be used for sub-agent delegation.** Instead, Opus decisions happen in the main conversation where the human can review them.

## Cost Impact Estimates

Approximate token costs per 1000 lines of code migrated (as of 2025 pricing):

| Approach | Estimated cost/1K LOC | Notes |
|----------|----------------------|-------|
| Opus for everything | ~$2.50 | Baseline — what happens with no tier routing |
| Sonnet for everything | ~$0.75 | Better, but still 3x what's needed for mechanical work |
| Tiered (70/25/5 Haiku/Sonnet/Opus) | ~$0.15 | 15–17x cheaper than Opus-only |
| Tiered with Express for small projects | ~$0.05 | Near-zero for simple projects |

## Quick Decision Tree

```
Is this task mechanical (pattern match, template, config, state)?
  → YES → Haiku
  → NO → Does it require understanding code meaning?
    → YES → Can the semantic part be isolated to < 30% of the work?
      → YES → Haiku for mechanical part, Sonnet for semantic part
      → NO → Sonnet for the whole task
    → NO → Does it require whole-codebase architectural reasoning?
      → YES → Opus (in main conversation, not sub-agent)
      → NO → Sonnet
```

## Sub-Agent Model Selection

When spawning sub-agents via the Task tool in Claude Code, specify the model:

```
Task(prompt="...", model="haiku")    # For mechanical work
Task(prompt="...", model="sonnet")   # For semantic reasoning
# Never spawn Opus sub-agents — keep Opus decisions in the main conversation
```

Match the work increment size to the model:
- **Haiku sub-agents**: 1 file or 1 small conversion unit per agent. Keep context tight.
- **Sonnet sub-agents**: 1 conversion unit or 1 complex function per agent. Include relevant context (contracts, call graph excerpt).
