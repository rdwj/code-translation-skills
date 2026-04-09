# Roadmap

Updated 2026-04-08 after the framing shift. The earlier Phase 1 (Java unblock via rename + parameterize) / Phase 2 (refactor) roadmap is **obsolete**.

## New approach: fresh start in a new repo

The existing `code-translation-skills` project is archived to a peer repo as posterity. We draw nuggets from it (domain insights, reference docs, behavioral contract concept, dashboard design) but do not carry its structure forward. The new kit is built from scratch with the agent-loop-native design from day one.

**Why the reset:**
- The old approach kept accumulating orchestration (phase runners, gate checkers, TODO templates) to force the agent through a prescribed process. That's fighting the agent instead of leveraging it.
- Trying to incrementally rename and parameterize 34 skills that are built on the wrong shape would drag the wrong mental model forward.
- The project isn't in active use — there's no live engagement depending on its current structure. The cost of a clean slate is almost zero; the cost of carrying forward the wrong foundation is significant.
- The user said it clearly: "don't want the past to be the enemy of the future."

## Archive step

Before starting the new repo, preserve the current state.

1. Create peer repo (suggested name: `code-translation-skills-v1-archive` or similar)
2. Push current `main` branch to the archive repo
3. Leave `code-translation-skills` directory as-is locally; treat it as read-only reference while building the new kit
4. Document the archive in a top-level `ARCHIVE.md` in the current repo explaining the decision, the key insights preserved in `ideas/agent-kit-generalization/`, and pointing at the new repo once it exists

## New repo setup (Milestone 0)

Stand up the new kit's repository:

- Choose name (candidates to discuss: `migration-agent-kit`, `code-translation-kit`, `polyglot-migration-kit`, `reforge`, `reshape`, `transplant` — naming is a conversation to have, not a solo decision)
- Initialize with standard scaffolding (LICENSE, README, CONTRIBUTING, .gitignore, .gitleaks.toml) — the `project-setup` skill can handle this
- Establish the directory layout:
  ```
  <new-repo>/
  ├── skills/                # SKILL.md files, one per skill
  ├── profiles/              # YAML profiles per source→target pair
  │   ├── java-8-to-17/
  │   ├── python-2-to-3/
  │   └── _schema/           # profile schema + validation
  ├── adapters/              # thin wrappers around external tools
  │   ├── openrewrite/       # patch+CSV → JSON adapter
  │   ├── treeloom/
  │   ├── greploom/
  │   ├── veripak/
  │   ├── sanicode/
  │   ├── semgrep/
  │   └── stigcode/
  ├── references/            # migration knowledge (drawn from old project)
  │   ├── java/
  │   └── python/
  ├── dashboard/             # HTML dashboard template (drawn from old project)
  ├── docs/                  # user-facing kit documentation
  └── examples/              # small reference codebases per profile for testing
  ```
- Commit the `ideas/agent-kit-generalization/` notes into the new repo as the design origin

## Build milestones

Rough order, not rigid sequencing. Each milestone produces something testable on a real (small) codebase.

### Milestone 1 — Discovery on Java

Goal: agent can point at a Java 8 codebase and get back a treeloom graph, veripak dependency audit, and Semgrep security baseline. Nothing fancy, just proves the foundation tools work end-to-end from an agent invocation.

Skills to build:
- `discover` (first version, Java-focused)
- `retrieve-context` (greploom wrapper)
- `audit-dependencies` (veripak wrapper)
- `scan-security` (Semgrep → SARIF → stigcode-ready)

Adapters:
- treeloom thin JSON wrapper
- greploom thin JSON wrapper
- veripak thin JSON wrapper
- Semgrep SARIF output already machine-readable

Profile:
- `profiles/java-8-to-17/profile.yaml` (first pass — probably incomplete, gets refined)

Verification: run end-to-end on a small open-source Java 8 project. Inspect outputs. Adjust.

### Milestone 2 — Mechanical conversion on Java via OpenRewrite

Goal: agent can invoke OpenRewrite in dry-run mode, parse the patch, present it for review, apply it.

Skills to build:
- `convert-mechanical` (dispatches to OpenRewrite for Java)

Adapters:
- OpenRewrite adapter: `adapters/openrewrite/run.py` that:
  - Writes a temporary `rewrite.yml` composing chosen recipes
  - Invokes `mvn -U org.openrewrite.maven:rewrite-maven-plugin:dryRun -Drewrite.activeRecipes=<list> -Drewrite.exportDatatables=true`
  - Parses `target/site/rewrite/rewrite.patch` and `target/rewrite/datatables/*.csv`
  - Emits normalized JSON: `{ files_changed, diffs_by_file, recipes_applied, stats_per_recipe }`
- Pre-check wrapper that runs `mvn compile` and fails fast if classpath is broken (OpenRewrite's biggest silent failure mode)

Verification: run `UpgradeToJava17` against a small Java 8 project, review the patch, apply, confirm tests still pass.

### Milestone 3 — Discovery on Python + mechanical via libcst

Goal: prove the profile abstraction actually generalizes. Second language, second mechanical engine, same skills.

Skills to extend:
- `discover` (add Python path)
- `convert-mechanical` (add libcst dispatch)

Adapters:
- libcst adapter producing the same normalized JSON shape as the OpenRewrite adapter
- sanicode wrapper (for Python SAST instead of Semgrep)

Profile:
- `profiles/python-2-to-3/profile.yaml`

Verification: run on a small Python 2 project. Confirm the agent kit does NOT need any Python-specific or Java-specific code in the skills themselves — everything language-specific is in the profile or the adapter.

This milestone is the critical test. If it reveals that skills need language-specific branching, the skill abstraction is wrong and needs redesign.

### Milestone 4 — Behavioral contracts + verification

Goal: extract function-level contracts, verify translations against them.

Skills to build:
- `extract-contracts` (function level first)
- `verify-translation` (confidence scoring)

This is the Mode A verification layer. Uses treeloom graph + LLM reasoning for contract extraction, then runs source and target code to compare.

### Milestone 5 — The killer feature: propose alternative decompositions

Goal: build the `propose-decomposition` skill that uses graph clustering on treeloom output to propose better module boundaries than the source has.

**This deserves a dedicated research session first** to settle:
- Which clustering algorithms to implement (Louvain, label propagation, hierarchical agglomerative, Girvan-Newman)
- How to score alternatives (cohesion, coupling, domain-naming heuristics)
- How to present alternatives to humans (dashboard view, comparison artifact)
- Where the LLM reasoning plugs in

Skills to build:
- `propose-decomposition`

This is the first Mode B skill and the thing that generates demand. Get it right.

### Milestone 6 — Module / subsystem / system spec extraction

Goal: build up the full spec hierarchy for Mode B.

Skills to build:
- Extend `extract-contracts` to module, subsystem, system levels
- `document-architecture` (C4-style docs in Mermaid/Markdown)

### Milestone 7 — Spec-driven code generation

Goal: generate target code from module specs, verified against function contracts.

Skills to build:
- `scaffold-target` (project skeleton in target language)
- `generate-from-spec` (module-by-module generation)

This closes the Mode B loop.

### Milestone 8 — Polish and publish

- Dashboard rebuild (draw from old project's HTML design)
- Documentation
- Example runs published
- First external user

## Explicit non-goals for v1

- Pattern catalogs for languages the external tools already cover (no Java pattern catalog — OpenRewrite owns that; no Python mechanical catalog — libcst owns that)
- Phase runner scripts (never again)
- Gate checkers that block agent progression
- Hand-rolled graph building, security scanning, dependency auditing
- Six-phase rigid pipeline — replaced by a loose taxonomy the agent navigates
- Porting all 34 old skills — the kit is smaller and does more per skill
- OpenShift MCP deployment (that's post-v1, once there's a reason)

## What makes a milestone "done"

A milestone is done when an agent can complete it on a real (small) open-source codebase without the user having to hand-hold the agent through the steps. The agent reads the skill, invokes the tools, interprets the output, and reports back. If the agent gets stuck or drifts, the fix is to sharpen the skill description or the verification criteria — not to add an orchestration script.

## Sequencing notes

- Milestones 1-3 are the critical path because they test whether the agent-loop-native approach and the profile abstraction actually hold up. If they don't, we learn it early and cheaply.
- Milestone 5 (propose-decomposition) is the demo-generating feature. It should happen before Milestone 6-7 because it's what teams will show off.
- Milestones 4 and 5 can be parallelized if multiple agents work on the kit.
- Nothing in this roadmap is urgent — there's no live engagement driving dates. The sequencing is about learning and validation, not delivery pressure.
