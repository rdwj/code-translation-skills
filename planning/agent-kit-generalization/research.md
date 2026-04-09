# Research: PyPI Packages as Foundation

Analysis of the five PyPI packages the user maintains, and how each fits into the agent kit. Source: PyPI JSON metadata and package descriptions as of 2026-04-08.

## treeloom

**What it is:** Language-agnostic code property graph library. Parses source via tree-sitter, unifies AST + control flow + data flow + call graph into a single queryable graph. Supports Python, JavaScript, TypeScript, Go, Java, C, C++, Rust.

**Key capabilities:**
- Incremental rebuild preserving unchanged nodes
- Type-aware call resolution with MRO-based method dispatch (Python)
- Taint analysis with label-propagation engine, field-sensitive tracking
- Built-in stdlib data flow models for common Python libraries
- JSON serialization with round-trip support
- Graphviz DOT and Cytoscape.js HTML visualization

**Fit in kit:** Replaces the `universal-code-graph` skill's internals. The skill itself stays (it's the agent-facing interface) but its scripts delegate to treeloom instead of re-implementing tree-sitter orchestration, graph building, and query files from scratch. The existing `queries/*.scm` files in the skill can be contributed upstream to treeloom if the repo doesn't already have them.

**Risk:** If treeloom's Python API changes between versions, the skill breaks. Mitigation: pin treeloom version in the skill's declared dependencies, test against upgrades before bumping.

## greploom

**What it is:** Semantic code search built on treeloom CPGs. Hybrid vector + BM25 indexes, graph expansion to include callers/callees/imports/data flow, SQLite-backed, respects LLM token budgets. Has `greploom serve` MCP mode.

**Key capabilities:**
- Indexes code for hybrid search (vector + keyword)
- Expands results through graph traversal to include structurally-complete neighborhoods
- Single portable SQLite database per index
- Supports local Ollama or OpenAI-compatible embedding endpoints
- Token budget enforcement — returns what fits

**Fit in kit:** This is the most important addition. **Greploom is the agent's context retrieval layer.** The current skill suite expects the agent to load large JSON files (dependency-graph.json, call-graph.json, raw-scan.json) into context and reason over them. That burns tokens and doesn't scale. With greploom, the agent asks "what does `UserService.authenticate` touch?" and gets back a token-budgeted, graph-expanded chunk.

**New skill suggested:** `code-context-retriever` — wraps greploom CLI, provides agent-facing interface for:
- "Tell me everything relevant about function X"
- "Who calls X and who does X call, transitively, up to N hops or M tokens"
- "What data does X read/write"
- "What tests cover X"

**Deployment mode (per user decision):**
- Default: skills invoke `greploom` CLI, index lives in workspace's `migration-analysis/greploom.db`
- Optional: OpenShift deployment runs `greploom serve` as MCP server, index shared across agents/sessions. Document this as a deployment option, not a dependency.

**Critical for disconnected environments:** CLI mode works offline if using local Ollama embeddings. That covers the OpenCode use case the user mentioned.

## veripak

**What it is:** Open-source package health auditor. Evaluates dependencies across version staleness, EOL status, CVE exposure, replacement viability. Supports PyPI, npm, Maven Central, Go, NuGet, MetaCPAN, Packagist, plus non-registry packages (C/C++, system packages) via LLM inference. Has `veripak serve` MCP mode.

**Key capabilities:**
- Version gap analysis with migration difficulty assessment
- Urgency ratings
- Breaking-change warnings
- Reasons about "ambiguous signals" and flags for human review when data sources conflict

**Fit in kit:** Replaces the dependency analysis parts of `py2to3-library-replacement` and `py2to3-codebase-analyzer`. Also gives veripak-based upgrade recommendations for Java/Maven, Node, .NET, etc. without needing to write ecosystem-specific logic per profile.

**Integration point:** The profile's "dependency analysis tooling hook" calls `veripak check <package> --ecosystem <type>` per detected dependency. Results feed into work-item-generator for upgrade tasks and the migration dashboard for supply-chain health panels.

## sanicode

**What it is:** SAST scanner with field-sensitive taint analysis for Python, JavaScript/TypeScript, and PHP. Maps findings to OWASP ASVS 5.0, NIST 800-53, ASD STIG v4r11, PCI DSS 4.0, FedRAMP, CMMC 2.0. Outputs SARIF, JSON, Markdown, HTML, DISA STIG checklists.

**Key capabilities:**
- 21 security issues detected (path traversal, injection, XSS, weak crypto, hardcoded credentials, etc.)
- Distinguishes `request.args` from `request.form["name"]` as separate tracked taint sources
- OSV dependency scanning
- Optional LLM-assisted context reasoning
- API server mode for remote/hybrid scans

**Fit in kit:** Replaces the 935-line `security_scan.py` in `py2to3-security-scanner`. The skill becomes a thin wrapper: run sanicode, consume SARIF output, flag regressions vs. baseline, surface findings in the dashboard.

**Gap:** sanicode doesn't currently cover Java. For the Java engagement, the security scan skill needs a fallback path (Semgrep, SpotBugs, or similar) until sanicode adds Java support. Worth raising with the user whether to wait for sanicode Java support or add a pluggable scanner interface.

## stigcode

**What it is:** SARIF → DISA STIG checklist (.ckl) + ATO evidence + NIST 800-53 matrix generator. Accepts SARIF from any SAST tool (sanicode, Semgrep, CodeQL, etc.).

**Key capabilities:**
- DISA STIG Viewer .ckl files
- ATO evidence reports (PDF/Markdown)
- NIST 800-53 control matrices with coverage gaps
- OSCAL output (planned)

**Fit in kit:** Downstream of whichever SAST tool the profile selects. Takes SARIF in, produces compliance artifacts out. Directly addresses the "government / regulated industry migration" use case that the existing py2to3 suite already hints at with security gates.

**New skill suggested:** `compliance-artifact-generator` — invokes stigcode on SARIF outputs, produces deliverables for ISSOs/assessors.

## Summary table

| Package | Replaces (current skill) | New capability |
|---|---|---|
| treeloom | universal-code-graph internals | More mature multi-language graph, taint analysis |
| greploom | — | Agent context retrieval layer (new) |
| veripak | Parts of library-replacement, codebase-analyzer | Multi-ecosystem dependency health (new) |
| sanicode | py2to3-security-scanner internals | SAST with compliance mapping (Python/JS/PHP) |
| stigcode | — | Compliance artifact generation (new) |

## Key observation

**Three of the five packages are already multi-language.** treeloom, greploom, and sanicode don't need to be re-done per language. That's where the leverage is: by delegating to these, the skill suite inherits multi-language support instead of having to rewrite per profile.

The gaps (sanicode not covering Java yet, veripak's non-registry support needing LLM inference) are real but bounded. They don't invalidate the delegation approach — they just require the profile abstraction to allow pluggable alternative tools where the default doesn't cover the target language.
