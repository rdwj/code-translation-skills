# Foundation Tool Feedback

Observations from running all four tools across four test rounds against real codebases: jsoup (Java, 91 files) and python-dateutil (Python, 17 files). All LLM-powered features used Granite 3.3 8b via local Ollama.

**Version history:**
- Round 1 (2026-04-09): treeloom 0.4.0, greploom pre-0.3.1, sanicode 0.10.0, veripak 0.3.1
- Round 2 (2026-04-10 AM): treeloom 0.7.0, greploom 0.3.1, sanicode 0.12.0, veripak 0.6.0
- Round 3 (2026-04-10 PM): treeloom 0.8.0, greploom 0.4.0, sanicode 0.12.1, veripak 0.6.1
- Round 4 (2026-04-17): treeloom 0.9.0, greploom 0.4.0, sanicode 0.12.3, veripak 0.6.3

Round 4 was driven by the `discover` skill build (M1). Issues found during integration were filed and fixed same-day.

## treeloom 0.9.0

**Status: All prior feedback addressed. No remaining issues.**

Everything works well: fast builds, high Java call resolution (82%, 5688/6889), source text embedding, edge queries, subgraph extraction.

Round 3 additions (0.8.0):
- `--relative-root DIR` makes node IDs portable.
- Edge JSON output now includes `file` and `line` on both source and target nodes.
- CPG is richer: jsoup went from 19981 nodes / 53517 edges to 22388 / 59546.

Round 4 additions (0.9.0):
- **Massive build speedup.** jsoup (91 Java files) builds in 1.5s, down from 8-9 minutes in 0.8.1. dateutil (17 Python files) builds in 0.5s, down from ~2 minutes. Node/edge counts are identical — the speedup is purely in the build pipeline.
- **`edges` command no longer truncated.** Previously returned at most ~50 edges silently; now returns the full set (7588 contains edges for dateutil, 20205 for jsoup). Filed as rdwj/treeloom#98, fixed same-day.
- **`query --json` now includes `scope`, `end_line`, `end_column`.** Previously flattened these out, making the query output structurally different from the raw CPG JSON. Filed as rdwj/treeloom#99, fixed same-day. The `scope` field gives direct parent linkage without needing to traverse `contains` edges; `end_line` enables accurate function line range resolution.

Remaining low-priority items:
- Python call resolution is still 34% vs 82% for Java. Expected due to dynamic dispatch.
- `treeloom config --init` creates `.treeloom.yaml` in CWD without confirmation. Minor UX nit.

## greploom 0.4.0

**Status: All prior feedback addressed. No remaining issues.**

Semantic search, graph-aware context, embeddings — all working well.

Round 3 additions:
- `--node` direct lookup and `--include-source` both confirmed working in 0.4.0.
- JSON output now wraps in `{"metadata": {...}, "results": [...]}` instead of a bare list. Not a bug — just a structural change the skill needs to handle.

Remaining low-priority item:
- Embedding model name isn't shown in query output. Would help with reproducibility.

## sanicode 0.12.3

**Status: All blockers resolved.**

Round 3 fixes confirmed (0.12.1):
- `--cwe` filter now works correctly. `--cwe 913` returns 9 findings (all CWE-913), not all 53.
- `config set scan.include_extensions ".py,.java,.js"` now works and writes a proper TOML array.

Round 4 fixes (0.12.2 → 0.12.3):
- **Java scanning performance fixed (0.12.2).** The Round 3 blocker — jsoup full codebase (91 files) not completing in 10+ minutes — is resolved. Full scan now completes in ~12s with `--no-llm`, producing 221 findings. Scaling is roughly linear.
- **`-o` flag now writes a file (0.12.3).** Previously, `-o sanicode-result.json` with `-f json` created a directory instead of a file. Filed as rdwj/sanicode#242, fixed same-day. Stdout redirect is no longer needed as a workaround.

Working well:
- 826 rules across 22 languages. Java has 76 rules.
- `--no-llm` mode: Python 17 files → 53 findings in ~2s; Java 91 files → 221 findings in ~12s.
- LLM enrichment on small scopes works (7 findings in 67.6s for dateutil/parser/).
- Compliance and remediation fields populated for all rule types.

### Minor: Severity aggregation inconsistency (still present)

The summary's `by_severity` uses `derived_severity`, but individual findings carry a separate `severity` field. The `discover` skill's assemble.py prefers `derived_severity` when available.

## veripak 0.6.3

**Status: All prior feedback addressed. No remaining issues that need package fixes.**

Round 3 fix confirmed (0.6.1):
- Ambiguous ecosystem now errors: `jsoup` without `-e` returns "exists in multiple ecosystems: python, javascript, dotnet, java. Please specify -e." Previously silently picked Python.

Round 4 fix (0.6.3):
- **`veripak_version` field added to JSON output.** Previously missing, making provenance tracking impossible without out-of-band recording. Filed as rdwj/veripak#27, fixed same-day.

Everything else working well:
- `config set/get/list` works correctly
- Maven coordinates resolve correctly (`org.jsoup:jsoup` → 1.22.1)
- CVE hallucination addressed via HITL drop mechanism
- `json_mode` support improves structured output quality

Remaining items (skill-level workarounds, all handled by assemble.py):
- Version discrepancy between `jsoup` (1.21.1) and `org.jsoup:jsoup` (1.22.1). Different data sources. Skill prefers Maven coordinate format for Java.
- `urgency: high` for python-dateutil despite 0 CVEs. LLM factors in EOL uncertainty. Skill passes through unchanged.
- Sparse summary fields (`_gaps`). Null-checked in assemble.py.
