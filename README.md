# py2to3 Migration Skill Suite

**26 skills | 6 phases | 52 scripts | 12 reference docs**

A skill suite for [Claude](https://claude.ai) that guides large-scale Python 2 to Python 3 migrations. Built on the [skill-creator](https://github.com/anthropics/courses/tree/master/skill-creator) framework, each skill is a self-contained unit that an AI agent can load to perform a specific migration task — from initial codebase analysis through final cutover.

## Why this exists

Python 2 reached end of life in January 2020, but significant Py2 codebases remain in production — particularly in industries where software life cycles are measured in decades. Industrial control systems, financial platforms, scientific infrastructure, and government systems all contain Python 2 code that has run reliably enough that rewriting was never prioritized.

These migrations are harder than typical web application conversions. The codebases are larger, older, and less well-tested. The original developers may be gone. The data flows span binary protocols, legacy encodings, and serialization formats never designed for cross-version compatibility. This skill suite encodes the patterns and procedures needed to handle that complexity systematically.

## Architecture

The suite follows a six-phase pipeline with explicit gate criteria between phases. Three orchestration skills cut across all phases to track state, enforce gates, and generate rollback plans.

```
Phase 0        Phase 1          Phase 2          Phase 3        Phase 4           Phase 5
Discovery  --> Foundation  -->  Mechanical  -->  Semantic  -->  Verification  --> Cutover
(5 skills)     (4 skills)       (3 skills)       (4 skills)     (4 skills)        (3 skills)

                    Orchestration (3 skills: State Tracker, Gate Checker, Rollback)
```

Each phase transition requires meeting specific gate criteria — there is no skipping ahead. Every phase includes rollback procedures so work can be unwound safely if issues surface downstream.

All code-generating skills accept a `--target-version` parameter (3.9, 3.11, 3.12, or 3.13) and adjust their output for version-specific breaking changes like `distutils` removal in 3.12 and module deprecations across releases.

## Skills

### Phase 0 — Discovery

| Skill | Directory | Purpose |
|-------|-----------|---------|
| 0.1 Codebase Analyzer | `py2to3-codebase-analyzer` | Scans the codebase for Py2 constructs, builds dependency graphs, determines migration order |
| 0.2 Data Format Analyzer | `py2to3-data-format-analyzer` | Maps bytes/string boundaries, binary protocols, encoding hotspots across the data layer |
| 0.3 Serialization Detector | `py2to3-serialization-detector` | Finds pickle, marshal, shelve, and custom serialization that will break across versions |
| 0.4 C Extension Flagger | `py2to3-c-extension-flagger` | Identifies C extensions, SWIG bindings, ctypes usage, and Cython modules needing ABI updates |
| 0.5 Lint Baseline Generator | `py2to3-lint-baseline-generator` | Captures the current lint state so regressions can be detected during migration |

### Phase 1 — Foundation

| Skill | Directory | Purpose |
|-------|-----------|---------|
| 1.1 Future Imports Injector | `py2to3-future-imports-injector` | Adds `from __future__` imports to make Py2 code forward-compatible |
| 1.2 Test Scaffold Generator | `py2to3-test-scaffold-generator` | Generates characterization tests that capture current behavior before conversion |
| 1.3 CI Dual-Interpreter Config | `py2to3-ci-dual-interpreter` | Configures CI pipelines to run tests under both Py2 and Py3 simultaneously |
| 1.4 Custom Lint Rules | `py2to3-custom-lint-rules` | Generates project-specific lint rules that block Py2 regressions in converted code |

### Phase 2 — Mechanical Conversion

| Skill | Directory | Purpose |
|-------|-----------|---------|
| 2.1 Conversion Unit Planner | `py2to3-conversion-unit-planner` | Groups modules into atomic conversion units based on dependency coupling |
| 2.2 Automated Converter | `py2to3-automated-converter` | Applies mechanical syntax transforms (print, exceptions, imports, dict methods, etc.) |
| 2.3 Build System Updater | `py2to3-build-system-updater` | Updates setup.py, requirements, tox configs, and packaging for Py3 compatibility |

### Phase 3 — Semantic Fixes

| Skill | Directory | Purpose |
|-------|-----------|---------|
| 3.1 Bytes/String Fixer | `py2to3-bytes-string-fixer` | Resolves bytes/str boundary issues — the hardest part of any Py2→3 migration |
| 3.2 Library Replacement | `py2to3-library-replacement` | Advises on replacing removed stdlib modules and deprecated third-party libraries |
| 3.3 Dynamic Pattern Resolver | `py2to3-dynamic-pattern-resolver` | Handles metaclasses, `__slots__`, descriptor protocols, and dynamic attribute patterns |
| 3.4 Type Annotation Adder | `py2to3-type-annotation-adder` | Adds type annotations to public interfaces, with encoding-aware types for data boundaries |

### Phase 4 — Verification

| Skill | Directory | Purpose |
|-------|-----------|---------|
| 4.1 Behavioral Diff Generator | `py2to3-behavioral-diff-generator` | Produces side-by-side behavioral diffs between Py2 and Py3 execution |
| 4.2 Performance Benchmarker | `py2to3-performance-benchmarker` | Benchmarks Py3 performance against Py2 baseline with statistical analysis |
| 4.3 Encoding Stress Tester | `py2to3-encoding-stress-tester` | Throws adversarial encoding inputs (EBCDIC, mixed encodings, binary protocols) at converted code |
| 4.4 Completeness Checker | `py2to3-completeness-checker` | Audits the entire codebase to verify nothing was missed across 10 migration categories |

### Phase 5 — Cutover

| Skill | Directory | Purpose |
|-------|-----------|---------|
| 5.1 Canary Deployment Planner | `py2to3-canary-deployment-planner` | Plans staged rollout with traffic splitting, monitoring, and automatic rollback triggers |
| 5.2 Compatibility Shim Remover | `py2to3-compatibility-shim-remover` | Identifies and removes `six`, `future`, and `__future__` compatibility layers post-migration |
| 5.3 Dead Code Detector | `py2to3-dead-code-detector` | Finds Py2-only code paths, unused compatibility wrappers, and unreachable branches |

### Orchestration (cross-cutting)

| Skill | Directory | Purpose |
|-------|-----------|---------|
| X.1 Migration State Tracker | `py2to3-migration-state-tracker` | Maintains per-module migration state, tracks phase progression, generates dashboards |
| X.2 Rollback Plan Generator | `py2to3-rollback-plan-generator` | Produces phase-specific rollback runbooks with git, K8s, and infrastructure commands |
| X.3 Gate Checker | `py2to3-gate-checker` | Enforces gate criteria for all 5 phase transitions, blocks progression until requirements are met |

## Getting Started

Each skill follows the skill-creator framework's three-level progressive disclosure:

1. **Metadata** (YAML frontmatter in `SKILL.md`) — always visible to the agent for routing
2. **Instructions** (SKILL.md body) — loaded when the skill is triggered
3. **Resources** (`scripts/` and `references/`) — loaded as needed during execution

To install, use the included installer script:

```bash
# Install all 26 skills to ~/.claude/skills/
./scripts/install-skills.sh

# Install to a specific project
./scripts/install-skills.sh /path/to/your/project

# Install specific skills only
./scripts/install-skills.sh --skill py2to3-codebase-analyzer --skill py2to3-gate-checker

# See what's available
./scripts/install-skills.sh --list

# Preview without copying
./scripts/install-skills.sh --dry-run
```

The agent reads the SKILL.md, understands the inputs and outputs, and runs the Python scripts in `scripts/` against your codebase. Each skill produces structured JSON output and a human-readable markdown report.

Reference documents (encoding patterns, syntax change catalogs, test vectors, etc.) are bundled in each skill's own `references/` directory — no external dependencies between skills.

## Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](GETTING-STARTED.md) | Suggested prompt and walkthrough for starting a migration |
| [PLAN.md](PLAN.md) | Authoritative specification for all 26 skills — inputs, outputs, capabilities, gate criteria, rollback procedures |
| [Migration Guide](docs/MIGRATION-GUIDE.md) | Practitioner's guide to the "why" behind the migration approach — read this first for strategic context |
| [docs/process/](docs/process/) | Build history: tracker, review reports, exploration chat log, prompt templates |

## Project Structure

```
.
├── README.md
├── LICENSE
├── PLAN.md
├── GETTING-STARTED.md
├── scripts/
│   └── install-skills.sh
├── docs/
│   ├── MIGRATION-GUIDE.md
│   └── process/
│       ├── BUILD-TRACKER.md
│       ├── EXPLORATION-CHAT.md
│       ├── NEXT-CHAT-PROMPT.md
│       ├── REVIEW-PROMPT.md
│       └── REVIEW-REPORT.md
└── skills/
    ├── py2to3-automated-converter/
    ├── py2to3-behavioral-diff-generator/
    ├── py2to3-build-system-updater/
    ├── py2to3-bytes-string-fixer/
    ├── py2to3-c-extension-flagger/
    ├── py2to3-canary-deployment-planner/
    ├── py2to3-ci-dual-interpreter/
    ├── py2to3-codebase-analyzer/
    ├── py2to3-compatibility-shim-remover/
    ├── py2to3-completeness-checker/
    ├── py2to3-conversion-unit-planner/
    ├── py2to3-custom-lint-rules/
    ├── py2to3-data-format-analyzer/
    ├── py2to3-dead-code-detector/
    ├── py2to3-dynamic-pattern-resolver/
    ├── py2to3-encoding-stress-tester/
    ├── py2to3-future-imports-injector/
    ├── py2to3-gate-checker/
    ├── py2to3-library-replacement/
    ├── py2to3-lint-baseline-generator/
    ├── py2to3-migration-state-tracker/
    ├── py2to3-performance-benchmarker/
    ├── py2to3-rollback-plan-generator/
    ├── py2to3-serialization-detector/
    ├── py2to3-test-scaffold-generator/
    └── py2to3-type-annotation-adder/
```

## License

[MIT](LICENSE)
