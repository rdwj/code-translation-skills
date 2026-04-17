# Agent Workflow: Foundation Tool Testing

Writeup of how the Round 3 tool testing was structured using parallel sub-agents. This documents the actual decomposition, prompting, and coordination pattern for future reference when designing the `discover` skill's agent workflow.

## Task decomposition

The task was: "install latest versions of all four tools in a venv, run the complete test suite against both codebases, report what's fixed and what's still broken."

**Step 1 (sequential, main agent):** Create the venv and install packages. This had to run first because all subsequent work depends on the venv being ready. The main agent did this directly — it's a single command with no ambiguity.

**Step 2 (parallel, three sub-agents):** Run the tools. Three independent workstreams with no dependencies between them:

| Agent | Tools | Codebases | Tests |
|-------|-------|-----------|-------|
| Agent 1 | treeloom 0.8.0 + greploom 0.4.0 | jsoup + dateutil | CLI help, CPG builds, source text, edge queries, greploom index, --node lookup, semantic search |
| Agent 2 | sanicode 0.12.1 | jsoup + dateutil | CLI help, language rules count, config init, Java safety/, Java parser/ (timeout test), Python full, --cwe filter, config set scan.*, LLM scan |
| Agent 3 | veripak 0.6.1 | jsoup + dateutil | CLI help, config set/get/list, jsoup (simple name), jsoup (Maven coord), dateutil, ecosystem inference |

**Step 3 (sequential, main agent):** Synthesize results. As each agent completed, the main agent extracted key findings and built the integrated assessment.

## Why this split

Treeloom and greploom were grouped because greploom depends on treeloom's CPG — the agent needed to build the CPG first, then index it, then query it. Running them separately would have required passing the CPG path between agents or duplicating the build.

Sanicode was isolated because it has the most complex test matrix (two languages, multiple flags, timeout testing, config mutations) and the highest risk of long-running commands. Isolating it meant a slow Java scan wouldn't block the other agents.

Veripak was isolated because it's completely independent (no file-system artifacts to share) and its tests are all network calls to registries + LLM. Fast but latency-bound.

## Prompting pattern

Each agent received:

1. **Activation prefix**: Every command was prefixed with `source /Users/wjackson/Developer/code-translation-skills/.venv/bin/activate &&` because the tools were only in the venv, not globally installed.

2. **Numbered test steps**: Each test was a numbered step with an explicit bash command. The agent didn't have to figure out what to run — the commands were spelled out. This is important because the agent doesn't have context about what changed between versions; the main agent does.

3. **Expected vs actual framing**: Where relevant, the prompt included what the previous version did so the agent could compare. Example: "the `--cwe` filter was bugged in 0.12.0 — returned all findings instead of filtering." This told the agent what to look for without requiring it to have read prior conversations.

4. **Timeout handling**: For the known-slow Java scan, the prompt included a Python subprocess wrapper with an explicit 120-second timeout, so the agent wouldn't hang indefinitely.

5. **Output parsing inline**: Each bash command included a piped Python one-liner to parse JSON and print the relevant fields. This kept agent output concise — it reported structured findings, not raw JSON dumps.

6. **"Report ALL output" instruction**: The prompt explicitly asked for full output so the main agent could spot things the sub-agent might not flag. Sub-agents don't know what's interesting; they just run commands and report.

## What the main agent did vs didn't delegate

**Main agent handled:**
- Environment setup (venv creation, pip install)
- Task decomposition and agent prompting
- Synthesis across all three agent results
- Determining what's a skill-level fix vs package-level fix
- Writing the final assessment

**Main agent did NOT handle:**
- Running any tool commands after venv setup (all delegated)
- Interpreting individual tool outputs (agents reported findings)
- The actual testing (agents ran every command)

## Coordination timing

All three agents were launched in a single message (parallel). The main agent then waited for completion notifications. As each agent finished, the main agent incorporated its results into the running synthesis. After all three completed, the main agent ran one additional quick check (verifying `--relative-root` made paths relative) and then wrote the final assessment.

Total wall-clock time was bounded by the slowest agent (sanicode, ~8 minutes due to the LLM scan test). Treeloom+greploom took ~14 minutes (dominated by the jsoup CPG build with inter-procedural DFG at 451s). Veripak took ~4 minutes (network calls to registries).

## Relevance to the discover skill

The `discover` skill will orchestrate these same four tools. The agent split maps directly to the skill's workflow:

1. **Sequential first step:** Build the CPG with treeloom (everything depends on it)
2. **Parallel second step:** Run greploom index, sanicode scan, and veripak audit concurrently (all independent once the CPG exists; veripak doesn't even need the CPG)
3. **Sequential final step:** Assemble the skeleton spec from all outputs

The key insight: treeloom is the bottleneck (minutes for a large codebase), but once it's done, everything else can run in parallel. Veripak can actually start even earlier since it only needs the dependency manifest, not the CPG.

```
                        ┌─ greploom index ──────┐
treeloom build ─────────┤                       ├─── assemble spec.json
                        ├─ sanicode scan ───────┤
    parse manifests ────┼─ veripak check (×N) ──┘
                        └───────────────────────
```

The `discover` skill should encode this DAG rather than running tools sequentially.
