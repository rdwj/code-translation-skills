# Architecture Notes

Design thinking for the language-agnostic agent kit. Updated 2026-04-08 after the framing shift to a fresh-start approach.

## The core insight that changes everything

The current `code-translation-skills` suite (the project this `ideas/` directory sits in) was built as "skills plus phase runners plus gate checkers." Over rounds 1-7, it accumulated increasingly elaborate orchestration: phase runner scripts to chain skills, gate checkers to block progression, state trackers to persist progress across sessions, TODO templates to prescribe which skill runs next.

**This was the wrong shape.** It was trying to make an agent loop behave like a deterministic agentic workflow — the exact thing the user explicitly wanted to avoid. The reason it kept accumulating orchestration is that agents *kept drifting from the prescribed process*, and each round of fixes added more rails. Those rails fought the agent's nature instead of leveraging it.

The right shape is **agent-loop-native**: skills are structured prompts that describe intent, inputs, outputs, and verification criteria. Tool invocations go through CLI commands. The agent loop handles sequencing, recovery, and iteration — that's what it's good at. No phase runners. No orchestration scripts. No gate checkers that block the agent from thinking.

If an agent drifts from the "prescribed process," either (a) the process was wrong for the situation and the agent knew better, or (b) the skill description wasn't clear enough about what success looks like. Both are fixable at the skill level. Neither is fixable by adding a runner script.

## What to keep from the old project

- **Domain insights** captured in skill descriptions (what does "Phase 4 Verification" mean, what are the gate criteria for Phase 2→3, what's the bytes/string problem really about)
- **Reference documents** in `docs/references/python-migration/` (Py2→3 syntax changes, semantic changes, bytes/str patterns — these are codified expert knowledge)
- **Behavioral contract concept** (the idea, not the current implementation)
- **Workspace peer-directory strategy** (still correct)
- **Migration dashboard HTML** (the visual design works)
- **The 6-phase mental model** as a loose taxonomy, not a rigid pipeline

## What to leave behind

- Phase runner scripts (`phase0_discovery.py` through `phase5_cutover.py`)
- `run_express.py` orchestrator
- Gate checker as a blocking mechanism
- The 34-skill decomposition — it's too fine-grained, forces the agent through too many hops
- Python-specific `ast.NodeTransformer` pipelines
- Custom pattern catalogs for things external tools already handle (treeloom, OpenRewrite, sanicode, veripak)
- Hand-rolled security scanning (sanicode replaces it)
- Hand-rolled dependency analysis (veripak replaces it)
- Hand-rolled graph building (treeloom replaces it)
- Hand-rolled context retrieval (greploom replaces it)

The existing project gets archived to a peer repo as posterity. We draw nuggets from it but don't carry its structure forward.

## The two modes

### Mode A — Transform migration

Source code is preserved in structure, mechanically and semantically updated. Py2→3, Java 8→17, Ruby 2→3.

### Mode B — Spec-driven rewrite

Source code is read for *intent*, distilled into a spec hierarchy, and new code is generated from the spec in a target language. Structure may differ significantly. The "propose alternative decompositions" capability lives here — and it's the killer feature.

Both modes share the discovery layer (code graph, behavioral contracts, dependency audit, security baseline). They diverge in execution.

## The spec hierarchy (Mode B)

```
System spec           ← what the whole thing does, in business terms
  ↑
Subsystem specs       ← bounded contexts, data ownership, inter-system contracts
  ↑
Module specs          ← public API, invariants, data shape, state ownership
  ↑
Function contracts    ← behavioral contracts (observable behavior)
  ↑
Code graph            ← treeloom output
```

Each level is extracted from the one below plus LLM reasoning. Each level serves a different consumer:

- **Function contracts** → test oracle for translation-verifier
- **Module specs** → generation target for spec-driven code generator
- **Subsystem specs** → architectural decisions, bounded contexts
- **System spec** → stakeholder-facing artifact, business-terms description

### The killer feature: propose alternative decompositions

Old codebases often have bad module boundaries. A spec extractor that mirrors them inherits the mess.

**Approach:**
1. Treeloom produces the call graph + data flow
2. Classical graph clustering (Louvain, label propagation, hierarchical agglomerative) proposes candidate decompositions
3. LLM scores candidates against cohesion, coupling, domain-naming heuristics
4. Output two artifacts: `specs/as-is/` (mirrors current modules) and `specs/proposed/` (alternative decompositions, ranked)
5. Human picks which drives the rewrite

This is what generates demand. It's also the piece that deserves a full research session of its own (clustering algorithm selection, scoring rubric design, how to present alternatives to humans).

## Foundation tools

The kit delegates to purpose-built packages rather than reimplementing them. User already maintains all five:

| Concern | Tool | Languages |
|---|---|---|
| Code graph + AST + CFG + DFG + call graph | **treeloom** | Python, JS/TS, Go, Java, C, C++, Rust |
| Context retrieval for the agent | **greploom** | Whatever treeloom supports |
| Dependency health audit | **veripak** | PyPI, npm, Maven, Go, NuGet, MetaCPAN, Packagist, non-registry |
| SAST with compliance mapping | **sanicode** | Python, JS/TS, PHP |
| SARIF → STIG/NIST artifacts | **stigcode** | Any SARIF input |
| Java mechanical conversion | **OpenRewrite** | Java (see `openrewrite-findings.md`) |

**Gap inventory:**
- Java SAST: sanicode doesn't cover Java yet. Use Semgrep (SARIF-native, flows into stigcode).
- Python 2 → 3 mechanical: not OpenRewrite's territory. Use libcst.
- JS/TS mechanical: jscodeshift or ts-morph.
- C# mechanical: Roslyn + analyzers.
- Go mechanical: `gofmt -r`, gopls, dst.

## Skills as structured prompts

A skill in the new kit is a SKILL.md file with:
- **Frontmatter:** name, when-to-use, required inputs, produced outputs
- **Body:** what the agent should do, in what order, and how to know it succeeded
- **Tool references:** which CLI commands to invoke (treeloom, greploom, OpenRewrite, sanicode, etc.)
- **Verification criteria:** how the agent knows the step worked — not a gate that blocks progress, but a check the agent uses to decide what to do next

Skills do NOT contain:
- Scripts that chain other skills (no phase runners)
- Scripts that implement transformations that external tools already handle
- Enforcement that blocks the agent from thinking

**Think fewer, larger skills.** The old suite had 34 skills. The new kit probably has 10-15, with each doing more and leaving the agent more room to improvise within. Rough first-cut:

1. `discover` — run treeloom, veripak, security baseline; produce the foundation artifacts
2. `retrieve-context` — wraps greploom; the agent's eyes into the codebase
3. `extract-contracts` — bottom-up from function → module → subsystem → system
4. `propose-decomposition` — the killer feature; graph clustering + LLM scoring
5. `document-architecture` — C4-style docs from graph + specs
6. `plan-migration` — produces a migration plan tailored to the specific codebase and profile
7. `convert-mechanical` — dispatches to OpenRewrite (Java), libcst (Python), etc. based on profile
8. `convert-semantic` — LLM-driven transforms for things external tools can't handle
9. `verify-translation` — run source + target, compare against contracts, confidence score
10. `scaffold-target` — project skeleton in target language from spec (Mode B)
11. `generate-from-spec` — module-by-module code generation from spec (Mode B)
12. `audit-dependencies` — wraps veripak
13. `scan-security` — wraps sanicode + fallback + stigcode
14. `generate-compliance` — wraps stigcode for DISA STIG / NIST artifacts
15. `dashboard` — generate self-contained HTML view of the migration

Subject to refinement once we start building.

## Profiles as declarative config

A migration profile is a YAML file declaring the engine choices and tool configurations for a specific source→target pair. It's data, not code. Example:

```yaml
profile:
  id: java-8-to-17
  source: { language: java, version: "8" }
  target: { language: java, version: "17" }

engines:
  mechanical: openrewrite
  semantic: llm-driven
  sast: semgrep   # sanicode doesn't support Java yet
  dependency_audit: veripak
  compliance: stigcode

mechanical_config:
  recipes:
    - org.openrewrite.java.migrate.UpgradeToJava17
    - org.openrewrite.java.migrate.jakarta.JavaxMigrationToJakarta
  invocation: maven-plugin-dry-run

semantic_targets:
  - sealed-class-conversion
  - module-info-generation
  - class-to-record

build:
  test_command: "mvn -q test"
  compile_command: "mvn -q compile"
  dependency_manifests: ["pom.xml", "**/pom.xml"]
```

```yaml
profile:
  id: python-2-to-3
  source: { language: python, version: "2.7" }
  target: { language: python, version: "3.11" }

engines:
  mechanical: libcst
  semantic: llm-driven
  sast: sanicode
  dependency_audit: veripak
  compliance: stigcode

mechanical_config:
  patterns_catalog: profiles/python-2-to-3/patterns/
  invocation: libcst-codemod

semantic_targets:
  - bytes-str-boundaries
  - unicode-literal-cleanup
  - stdlib-module-replacements

build:
  test_command: "pytest -q"
  compile_command: "python -c 'import py_compile; ...'"
  dependency_manifests: ["requirements*.txt", "pyproject.toml", "setup.py"]
```

**What stays out of profiles:**
- The skill set (shared across all profiles)
- The workspace strategy (peer directory, shared)
- The dashboard (reads profile-agnostic JSON)
- The agent loop itself

## Deployment: CLI default, MCP optional

Per prior decision, dual-mode from day one:

- **CLI default** — skills invoke treeloom/greploom/veripak/sanicode/stigcode/OpenRewrite as CLI commands. State lives in the workspace. Works offline. Works with Claude Code, OpenCode, anything.
- **MCP optional** — `greploom serve` and `veripak serve` can run on OpenShift for teams that want shared persistent indexes. Skills still call CLI. MCP is a deployment option, not a dependency.

Disconnected environments (OpenCode case) get the CLI path. Connected teams can opt into the MCP path if the shared-index benefit matters.

## What the agent loop looks like

Loose flow, not a pipeline:

1. User drops the agent into a repo with a target language in mind
2. Agent reads the profile (from user or auto-detects)
3. Agent runs `discover` to build foundation artifacts — treeloom graph, dependency audit, security baseline
4. Agent uses `retrieve-context` to read the codebase (via greploom) — not by loading giant JSON blobs into context
5. Agent decides (based on profile and user intent) whether it's doing Mode A transform or Mode B rewrite
6. Agent runs the relevant skills in whatever order makes sense for the situation
7. Agent verifies as it goes — translation-verifier provides confidence scores, not blocking gates
8. Agent produces artifacts and a dashboard; hands back to user for review

**The agent decides order.** The skills describe intent and verification. The loop is the agent's to manage. This is the opposite of the old project's phase runner approach.

## Open design questions (not blocking)

- Exactly which skills to build first (see `roadmap.md`)
- Clustering algorithm selection for `propose-decomposition` (Louvain + hierarchical seems likely, but deserves its own research session)
- Spec format (leaning JSON as source of truth + Markdown as derived artifact for humans)
- Architecture doc format (leaning Mermaid in Markdown)
- How profiles handle tool gaps per language (Java SAST, Python mechanical)
- When to introduce MCP deployment guide
- Repository layout for the new kit
