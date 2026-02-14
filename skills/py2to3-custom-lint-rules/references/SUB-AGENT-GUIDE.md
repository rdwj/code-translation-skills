# Sub-Agent Delegation Guide

When executing migration work, the main agent can spawn sub-agents (via the Task tool) to parallelize work or isolate tasks that don't need the full conversation context. Sub-agents cannot discover or load skills on their own — the main agent must inject the relevant instructions into the sub-agent's prompt.

## When to Use Sub-Agents

Sub-agents are useful for:

- **Parallelizable file-level work**: Processing multiple conversion units or file batches simultaneously
- **Bounded, mechanical tasks**: Lint runs, syntax checks, file scanning, import injection — tasks with clear inputs and outputs
- **Isolating large outputs**: Running a scan that produces large output, then having the sub-agent summarize before returning

Sub-agents are not useful for:

- **Tasks requiring human judgment**: Bytes/string boundary decisions, architectural choices — keep these in the main conversation
- **Tasks requiring cross-file reasoning**: Dependency graph analysis, dead code detection — these need full codebase visibility
- **Tasks where the output IS the value**: Gate check reports, handoff prompts — these belong in the main conversation

## How to Inject Skill Context

Since sub-agents can't load skills, the main agent must include the relevant instructions in the sub-agent prompt. Follow this pattern:

1. **Extract the relevant portion** of the SKILL.md — not the whole file. Include the workflow steps and output format for the specific task, skip the background/rationale sections.

2. **Include the script path and invocation** — tell the sub-agent exactly which script to run with which arguments.

3. **Include relevant reference material** only if the sub-agent needs it for the task. Most reference docs are consumed by scripts, not by the agent directly.

4. **Specify the output contract** — tell the sub-agent exactly what to produce and where to save it. Be explicit about file paths.

Example prompt structure for a sub-agent:

```
Process conversion unit CU-03 (io-protocols) for Phase 2 mechanical conversion.

Files in this unit: src/io_protocols/serial_sensor.py, src/io_protocols/modbus_client.py,
src/io_protocols/mqtt_listener.py

For each file:
1. Run: python skills/py2to3-automated-converter/scripts/convert_module.py <file> --target-version 3.12
2. Verify the converted file parses: python3 -c "import ast; ast.parse(open('<file>').read())"
3. Save conversion report to migration-analysis/phase-2-mechanical/cu03-report.json

Output format: JSON with keys "files_converted", "changes_per_file", "warnings", "errors"

Return a summary of what was converted and any warnings or errors encountered.
```

## Context Budget

Be mindful of the capabilities of the model you choose for the sub-agent and size the increment of work and the prompt context accordingly:

- **Keep sub-agent prompts focused.** Include only what the sub-agent needs for its specific task. A sub-agent processing one conversion unit doesn't need the full migration state or the complete dependency graph — just the file list, the script to run, and the output format.

- **Summarize, don't dump.** If the sub-agent needs context from a previous phase's output, summarize the relevant findings rather than including the entire JSON file. For example: "CU-03 contains 3 high-risk I/O modules. serial_sensor.py has binary packet parsing. modbus_client.py has register read/write. Focus on bytes/str correctness."

- **Match work size to model capability.** Smaller, simpler models handle mechanical tasks well but struggle with nuanced semantic reasoning. Larger models handle complex reasoning but are slower and more expensive. Choose the model that matches the task complexity, and size the work increment to fit comfortably within that model's effective context window.

- **One task per sub-agent.** Don't ask a sub-agent to "process CU-03, then CU-04, then CU-05." Spawn three sub-agents, one per unit. This keeps each prompt focused and allows parallel execution.

## Output Handling

Sub-agents return their results to the main agent. To manage context:

- **Have sub-agents write detailed output to files** and return only a summary to the main conversation.
- **Define the summary format in the prompt**: "Return: number of files processed, number of changes, any errors. Do not include the full diff."
- **Use sub-agent output to update the migration state** in the main conversation, then move on.

## Parallel Execution Patterns

Common patterns for parallelizing migration work:

**Phase 0 — Discovery**: Run codebase-analyzer, data-format-analyzer, and serialization-detector as parallel sub-agents (they read the codebase independently). Merge their outputs in the main agent.

**Phase 2 — Mechanical Conversion**: Spawn one sub-agent per conversion unit within a wave (units in the same wave have no dependencies on each other).

**Phase 4 — Verification**: Run behavioral-diff-generator and encoding-stress-tester as parallel sub-agents scoped to different conversion units.

**Phase 5 — Cutover**: Run compatibility-shim-remover and dead-code-detector as parallel sub-agents (they analyze independently, though removal should be sequential).
