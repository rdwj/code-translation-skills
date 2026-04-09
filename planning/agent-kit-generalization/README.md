# Agent Kit Generalization

Ideation notes for a language-agnostic agent kit that helps migrate old codebases to new versions or different languages. Designed for coding agents (Claude Code, OpenCode) and agent-loop-native from day one.

## Current state (2026-04-08)

This `ideas/` directory sits inside the `code-translation-skills` project — a first-try effort that worked well on a real Python 2→3 engagement but couldn't scale to other languages. The approach tried to make an agent loop behave like a deterministic agentic workflow (phase runners, gate checkers, 34 fine-grained skills). That was the wrong shape.

**Decision:** Archive the current project as posterity in a peer repo. Start the new kit fresh with an agent-loop-native design. Don't let the past be the enemy of the future.

The good stuff from the old project (domain insights, reference docs, behavioral contract concept, workspace peer-directory strategy, dashboard HTML design) gets drawn forward deliberately. The orchestration machinery gets left behind.

## Core design principles

1. **Agent-loop-native.** Skills describe intent and verification. The agent loop handles sequencing, recovery, and iteration. No phase runners. No gate checkers that block thinking. If the agent drifts from the "right" process, sharpen the skill — don't add rails.

2. **Delegate to purpose-built tools.** The user maintains five PyPI packages (treeloom, greploom, veripak, sanicode, stigcode) that collectively solve most of the foundation work. Use them. OpenRewrite handles Java mechanical conversion. libcst handles Python mechanical conversion. We don't reimplement what already exists.

3. **Two modes: transform and rewrite.**
   - **Mode A — Transform migration.** Source preserved in structure, mechanically/semantically updated. Py2→3, Java 8→17.
   - **Mode B — Spec-driven rewrite.** Source read for intent, distilled into spec hierarchy, new code generated in target language. Structure may differ.

4. **The killer feature is proposing alternative module decompositions.** Old codebases often have bad boundaries. Graph clustering + LLM scoring proposes better ones. Humans pick. This is what generates demand for the kit.

5. **Profiles are data, not code.** A YAML file declares the engines and tool configurations for a source→target pair. Adding a new language pair is a profile + adapter, not new skills.

6. **CLI default, MCP optional.** Skills invoke tools via CLI. Works in disconnected environments (OpenCode). Teams on OpenShift can optionally run `greploom serve` / `veripak serve` for shared indexes — but skills don't depend on it.

## Foundation tools

| Concern | Tool | Languages |
|---|---|---|
| Code graph (AST + CFG + DFG + call graph) | **treeloom** | Python, JS/TS, Go, Java, C, C++, Rust |
| Context retrieval for the agent | **greploom** | Whatever treeloom supports |
| Dependency health audit | **veripak** | All major ecosystems |
| SAST with compliance mapping | **sanicode** | Python, JS/TS, PHP |
| SARIF → STIG/NIST compliance artifacts | **stigcode** | Any SARIF input |
| Java mechanical conversion | **OpenRewrite** | Java (see `openrewrite-findings.md`) |
| Python mechanical conversion | **libcst** | Python |
| JS/TS mechanical conversion | jscodeshift or ts-morph | JS/TS |

## Files in this directory

- `README.md` — this file
- `research.md` — the five PyPI packages: what each does, how each fits
- `openrewrite-findings.md` — Java AST transformation engine research (OpenRewrite is the answer for Java)
- `architecture.md` — agent-loop-native design, two modes, spec hierarchy, foundation tool strategy, skill shape
- `roadmap.md` — fresh-start milestone plan (archive old project, build new kit from Milestone 0)
- `open-questions.md` — unresolved design decisions, organized by when they need resolution
- `conversation-20260408-154028.md` — full dialog narrative from the 2026-04-08 session

## Decisions recorded (2026-04-08)

| Decision | Resolution |
|---|---|
| Scope | Both Java unblock and broad kit, originally phased — now a fresh-start reset |
| Mode A vs Mode B priority | Equal weight |
| Approach to existing py2to3-* skills | Archive current project, draw forward deliberately into new kit |
| greploom deployment | Dual-mode: CLI default, MCP optional |
| Subsystem boundary detector | Propose alternatives, not mirror — this is the killer feature |
| Java mechanical engine | OpenRewrite (confirmed by research session) |
| Python mechanical engine | libcst (OpenRewrite does not cover Py2→3) |
| Orchestration approach | Agent-loop-native; no phase runners, no gate-blocking |
| Sequencing pressure | None — project not in active use, take time to get it right |

## Next session starting points

- **Pick a name for the new repo.** This is a conversation, not a solo decision. Candidates in `roadmap.md` Milestone 0.
- **Archive the current project** to a peer repo with an `ARCHIVE.md` explaining the reset.
- **Dedicated research session on `propose-decomposition`** — clustering algorithms, scoring rubrics, presentation format. This is the killer feature and deserves the attention.
- **Prototype Milestone 1** (Java discovery end-to-end) to validate the foundation-tool-delegation approach works in practice before committing to the rest of the roadmap.

See `roadmap.md` for the full milestone plan and `open-questions.md` for the list of unresolved decisions.
