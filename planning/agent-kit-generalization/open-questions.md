# Open Questions

Updated 2026-04-08 after the framing reset and OpenRewrite research.

## Resolved

- ✓ Java mechanical conversion engine: **OpenRewrite** (see `openrewrite-findings.md`)
- ✓ Java AST transformation approach: Maven plugin `rewrite:dryRun` producing unified diff patch, wrapped by a thin JSON adapter
- ✓ Python 2 → 3 mechanical engine: **libcst** (OpenRewrite archived its Python support)
- ✓ JS/TS mechanical engine candidates: jscodeshift or ts-morph (choose later, after a real need)
- ✓ Java SAST: Semgrep until sanicode adds Java support
- ✓ Generalization approach: fresh start in a new repo, not incremental refactor of the existing project
- ✓ Orchestration model: agent-loop-native, no phase runners, no blocking gate checkers
- ✓ Foundation tools: treeloom, greploom, veripak, sanicode, stigcode (delegate, don't reimplement)
- ✓ Mode priority: Mode A and Mode B equal weight
- ✓ Killer feature identified: `propose-decomposition` — graph clustering + LLM scoring to suggest alternative module boundaries
- ✓ Deployment: CLI default, MCP optional
- ✓ Sequencing pressure: none — project not in active use

## Blocking for Milestone 0 (new repo setup)

1. **Name the new repo.** Candidates to discuss: `migration-agent-kit`, `code-translation-kit`, `polyglot-migration-kit`, `reforge`, `reshape`, `transplant`. Probably a conversation to have fresh, not a decision to make in this session.

2. **Where does the archive of the current project live?** Options:
   - New public GitHub repo: `code-translation-skills-v1-archive`
   - Tag + branch on existing repo, no new repo
   - Private archive only
   - **Leaning toward:** public peer repo with a clear README explaining it's a posterity archive and pointing to the new kit. Preserves visibility of the good ideas for anyone who finds it.

3. **How much of `code-translation-skills/docs/references/shared/` gets copied forward?** The Py2→3 syntax and semantic change catalogs, the bytes/str patterns reference, the SUB-AGENT-GUIDE — these are codified expert knowledge worth preserving verbatim in the new kit's `references/` directory.

## Blocking for Milestone 1 (Java discovery end-to-end)

4. **Dependency manifest detection.** How does the profile declare where dependency files live? Glob patterns in profile.yaml are probably enough. Needs a concrete schema.

5. **Test runner abstraction.** Probably "shell command string in profile." But: how does the agent know if tests failed meaningfully vs a test runner startup error vs a missing dependency? The agent needs enough signal to decide whether to retry, narrow scope, or escalate. Needs design.

6. **Treeloom invocation format.** Does the adapter shell out to a `treeloom` CLI command, or import treeloom as a Python library? CLI is agent-friendly; library is Python-specific. Probably CLI with JSON output.

## Blocking for Milestone 5 (propose-decomposition — killer feature)

7. **Clustering algorithm selection.** Candidates:
   - **Louvain** — modularity optimization, classic choice for community detection in graphs, fast, deterministic results given same seed
   - **Label propagation** — very fast, less stable
   - **Hierarchical agglomerative** — produces a tree of decompositions at different granularities, arguably most useful for letting humans choose scale
   - **Girvan-Newman** — slower, more interpretable, based on edge betweenness
   - **Leiden** — Louvain's successor, better guarantees on community quality
   - **Needs a dedicated research session.** Start with Louvain (or Leiden) + hierarchical agglomerative as the two default options, let LLM score both.

8. **Scoring rubric for alternatives.** What does "better decomposition" mean mechanically?
   - Cohesion: density of intra-cluster edges
   - Coupling: count and weight of inter-cluster edges
   - Size balance: avoid trivially small or massively large clusters
   - Domain naming: can a short semantic label be assigned to each cluster (LLM judgment)
   - Stability: does small perturbation of the graph produce wildly different clusterings (robustness signal)
   - Needs to produce a comparable score between alternatives, not just a pass/fail

9. **Presentation format for humans.** When the agent proposes three alternative decompositions, how does the human review and choose? Dashboard view with side-by-side module diagrams? Text report with named clusters and coupling metrics? Probably both — dashboard as primary, text report as handoff artifact.

## Blocking for Milestone 6 (spec extraction at module+ levels)

10. **Spec format.** Leaning JSON as source of truth + Markdown as derived artifact for humans. Needs a concrete schema. C4 model might inform subsystem and system levels but doesn't map directly to module-level specs.

11. **Architecture doc format.** Leaning Mermaid diagrams embedded in Markdown — works in GitHub, VS Code, Obsidian, anywhere. No separate rendering tooling. Needs confirmation once we see what the graph output actually looks like.

## Blocking for Milestone 7 (spec-driven code generation)

12. **Target-language scaffolder opinionation.** How opinionated should `scaffold-target` be about project structure in the target language? Probably: ship reasonable defaults per language (Maven layout for Java, src layout for Python, etc.) with overrides in the profile.

13. **Module generation granularity.** Does the agent generate whole modules in one shot, or function-by-function? Whole modules lose context cheaper but make verification harder. Function-by-function is slower but each unit is verifiable. Probably function-by-function within a module, with the module spec as the binding contract.

## Parked

14. **Dashboard extensions for Mode B artifacts.** Decide after first Mode B skill produces real artifacts.

15. **MCP deployment guide.** Post-v1. Not needed until a team asks for it.

16. **Profile versioning scheme.** Once the schema is stable enough that backward compatibility matters.

17. **Incremental re-analysis.** When source commits land during a migration, how does the kit incorporate changes without re-running everything? Treeloom supports incremental rebuild; the skill layer above it would need to too. Future enhancement.

18. **Cross-profile composition.** Can someone chain "Python 2 → Python 3" + "Python 3 → modern idiomatic Python" as two profiles in sequence? Or is that one combined profile? Defer.

## Items needing verification (from OpenRewrite research)

19. Whether general `ClassToRecord` recipe has landed in `rewrite-migrate-java` (issue #391 was open at time of research)
20. Whether JPMS `module-info.java` generator recipe exists in OpenRewrite
21. Per-recipe Apache vs MSAL license on specific recipes the kit depends on (check source file headers)
22. Moderne CLI licensing terms for automated/agent use against private customer repos

## Questions to raise with user in the next session

- Repo name (conversation)
- Does the archive live as a new public peer repo, or as a branch/tag on the current repo?
- Is there a specific Java 8 codebase we want to use as the Milestone 1 reference project? (Having a concrete target will sharpen the design)
- Is there a specific Python 2 codebase we want to use as the Milestone 3 reference project?
- Does the user want to do the `propose-decomposition` deep-dive session next, or prefer to prototype Milestone 1 first and come back to the killer feature once the foundation is proven?
