# Backlog

Canonical list of remaining work for the code-translation-skills suite.
Completed rounds are documented in `SKILL-UPDATE-PLAN.md`.

---

## 1. Code Sanitization

Redact sensitive values from all generated outputs before they're shared with stakeholders or committed to repos.

**What to sanitize:** credentials, API keys, tokens, internal hostnames, database connection strings, PII (emails, IPs, usernames found in code comments or log entries).

**Where it shows up:**
- Dashboard HTML files (embedded JSON data contains source file paths and code snippets)
- `dependency-graph.json` / `call-graph.json` (node IDs are file paths, definitions may contain sensitive names)
- `migration-audit.log` / `skill-invocations.jsonl` (log entries may echo sensitive values from scanned code)
- `migration-state.json` (decision history, notes fields)

**Approach:**
- Create `scripts/lib/sanitize_outputs.py` — a shared module that scrubs a file or string against a set of patterns (regex + entropy-based detection for high-entropy strings like keys/tokens)
- Reuse detection patterns from `security_scan.py` (which already finds secrets in source code)
- Add `--sanitize` flag to all dashboard generation scripts (`generate_dashboard.py`, `generate_skill_usage_dashboard.py`, `generate_run_status.py`) that runs the scrubber on the HTML before writing
- Optionally produce a `sanitization-report.json` listing what was redacted and where, so users can verify nothing important was lost

---

## 2. Standalone Skill Agents

The current architecture has a general-purpose LLM agent invoking skill scripts via phase runners. This works but is slow — the agent spends context and time figuring out which script to call and how to interpret results. A dedicated agent per skill would be faster and more reliable.

**The idea:** Turn high-value individual skills into self-contained agents that can be invoked directly. Each agent knows its own inputs/outputs, handles its own error recovery, and returns structured results. No general-purpose agent in the loop for routine work.

**Candidate skills for agent-ification (start with the heaviest):**
- `py2to3-codebase-analyzer` — currently the longest-running skill, could run as a background agent
- `haiku-pattern-fixer` — loops over many work items; a dedicated agent could batch and parallelize
- `universal-code-graph` — graph building is pure computation, agent could manage incremental updates
- `behavioral-contract-extractor` — LLM-heavy, would benefit from its own context management
- `py2to3-semantic-equivalence-checker` — needs careful reasoning, dedicated agent avoids context pollution

**Implementation approach:**
- Frameworkless first — plain Python agents with a simple invoke/respond protocol (no LangGraph/LangChain dependency unless there's a clear benefit)
- Each agent: reads inputs from disk, does its work, writes outputs to disk, returns a JSON status summary
- A thin orchestrator (replacing or wrapping `run_express.py`) dispatches agents and collects results
- Consider whether agents can run in parallel where phase dependencies allow (e.g., security scan + graph analysis in Phase 0)

**Open questions:**
- What's the right invocation protocol? Subprocess with JSON stdout (current pattern) vs. something more structured?
- Should agents maintain their own state across retries, or is the current "run from scratch" model fine?
- How do we handle agent failures — retry with backoff, skip and flag, or halt the phase?

---

## 3. Expand Beyond Python — General-Purpose Migration Framework

The suite currently targets Python 2 → Python 3 migrations, but the architecture (universal code graph, tree-sitter parsing, phased workflow, skill-based decomposition) is language-agnostic by design. Expand to support arbitrary source → target migrations.

**Source-language expansions (migrating FROM older versions):**
- Java 8 → 17+ (javax.* namespace changes, module system, records, sealed classes, pattern matching)
- Ruby 2 → 3 (keyword argument changes, string freezing, removed methods)
- Node.js CommonJS → ESM (require → import, module.exports → export)
- C++ standards upgrades (C++11/14 → C++20, smart pointers, ranges, concepts)
- .NET Framework → .NET 6+ (namespace changes, async patterns, nullable reference types)

**Target-language expansions (migrating TO a different language):**
- Python → Go (for performance-critical services)
- Python → Rust (for systems-level code, safety-critical paths)
- Java → Kotlin (Android modernization)
- JavaScript → TypeScript (type safety adoption)

**What needs to change:**
- Tree-sitter queries: add `.scm` query files per language (3 queries × N languages). The `universal-code-graph` skill already supports this — it's query-file-driven.
- Pattern catalogs: each migration pair needs a catalog of known patterns (like the existing `py2_patterns.py` but for Java→Java17, etc.). These drive the work item generator and haiku fixer.
- Skill templates: generalize the py2to3-specific skills into templates. e.g., `library-replacement` becomes parameterized by a mapping file, not hardcoded to Python stdlib.
- Naming: some skills have `py2to3` in the name. Either rename or create parallel skills per migration type.
- Phase semantics: the 6-phase workflow (Discovery → Foundation → Mechanical → Semantic → Verification → Cutover) is migration-agnostic, but the specific scripts within each phase are Python-focused. Make them pluggable.

**Incremental path:**
1. Start with one non-Python migration (Java 8→17 is probably highest demand)
2. Build the pattern catalog and tree-sitter queries for it
3. Validate that the existing phase runner + skill architecture works without Python-specific assumptions
4. Extract the common framework, parameterize the Python-specific parts
5. Add more languages as needed

---

## 4. Tree-sitter Query Expansion

Fill out the tree-sitter query coverage for languages already partially supported.

**Python 2 patterns (`py2_patterns_ts.py`):**
- Currently has basic pattern detection. Needs all 20+ Python 2 patterns covered (print statements, except syntax, division, string/bytes, dict methods, unicode literals, etc.)
- These are the fallback when `ast.parse()` fails on legacy code

**New language queries (3 query files per language):**
- Go: imports, function definitions, type definitions
- Rust: use statements, fn definitions, struct/enum definitions
- Ruby: require statements, method definitions, class definitions
- C/C++: include directives, function definitions, class definitions
- Each language needs: `imports.scm`, `definitions.scm`, `calls.scm`

---

## 5. Integration and Polish

Remaining work to make the suite production-ready for real migrations.

- `depends_runner.py` — integrate multilang-depends for cross-language dependency analysis (requires JRE)
- Tree-sitter fallback paths — update existing skill scripts to gracefully fall back to tree-sitter when ast.parse() fails
- End-to-end integration test — run `run_express.py` against a real Python 2 codebase and validate the full pipeline
- Generalize naming — create target-language template skills so adding a new migration pair doesn't require copying/renaming 35 skills
- Error recovery — improve phase runners to handle partial failures gracefully (currently a failed script can stall the whole phase)
- Documentation — ensure every skill's SKILL.md is current after all the rounds of changes
