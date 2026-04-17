# Retrospective: M2 Extract-Contracts Skill

**Date:** 2026-04-17
**Effort:** Build the `extract-contracts` skill — LLM behavioral contract extraction for spec elements
**Commits:** 817be14, 051d4e2

## What We Set Out To Do

From NEXT_SESSION.md, four required deliverables plus one optional:

1. `skills/extract-contracts/SKILL.md` — skill definition
2. Working run against dateutil parser module (~91 elements) producing contracts
3. Comparison of extracted contracts vs hand-crafted examples in `dateutil-parser.spec.json`
4. Enriched spec validates against schema and renders
5. (Optional) Multi-model comparison across granite-8B, gpt-oss-20B, ministral-14B

## What Changed

| Change | Type | Rationale |
|--------|------|-----------|
| Dropped Prometheus judge model from evaluation plan | Good pivot | User identified it's trained on public health tool evaluation data, not useful for code contract quality |
| Built compare.py (not in original plan) | Scope addition | Needed structured evaluation; reusable for future extraction work and multi-model comparison |
| Three extraction runs instead of one | Missed requirement | First run had zero source code due to reading wrong greploom field; required diagnosis and two fix cycles |
| Added `--max-group-size` to split large class groups | Good pivot | vLLM dropped connections on classes with 8+ methods; splitting into singles resolved most timeouts |
| Added ecosystem CVE injection into prompts | Scope addition | Discovered sanicode findings are CWE-level, not CVE-level; veripak CVEs needed separate plumbing |
| Multi-model comparison deferred | Scope deferral | Time invested in diagnosis and quality improvement was more valuable than breadth testing |

## What Went Well

- **Iterative diagnosis loop.** Each run's comparison data directly informed the next fix. Run 1 exposed the hallucination, which led to the `text` field discovery, which led to the prompt improvements. Disciplined cause-then-fix, not random changes.
- **compare.py paid off immediately.** Built during extraction wait time, used to quantify improvement across all three runs (86% → 93% field coverage, 0/2 → 2/2 invariants on `_parse`).
- **Good scope control.** Dropped Prometheus early (user insight), deferred multi-model (time box), focused on extraction quality over breadth.
- **Parallel work during long extractions.** compare.py written while run 2 executed (~40 min). No idle waiting.
- **Retry with backoff recovered isoparser.** The gold-standard element that failed in run 2 succeeded in run 3, completing all 7 comparison points.

## Gaps Identified

| Gap | Severity | Resolution |
|-----|----------|------------|
| greploom returns source in `text` field, not `source` — went undetected through full run 1 (90 contracts extracted blind) | Process gap — **recurring pattern** | Fixed in session. Same class as M1's "convenience view vs actual data." The M1 countermeasure ("inspect actual input files") was not applied. |
| dateutil CPG built with treeloom 0.7.0, which doesn't honor `--include-source` | Missed requirement | Installed treeloom is 0.7.0 despite M1 notes saying "rebuilt with 0.9.0." CPG needs rebuild with 0.9.0+. |
| No unit tests for extract.py or compare.py | Follow-up | Three live runs are evidence, but format changes will silently break extraction. |
| vLLM (gpt-oss-20B) drops ~15% of connections on larger prompts | Follow-up | Retry helps but doesn't eliminate. Could be server load, generation timeout, or prompt size. Needs investigation. |
| greploom `text` field naming is surprising — `source` and `structural_context` are absent | Follow-up | File improvement request on greploom for clearer field naming or documentation. |
| Module-level contracts are weak | Accept | Greploom returns minimal context for modules. May need child-element aggregation in a future pass. |

## Action Items

- [ ] Upgrade treeloom to 0.9.0+ and rebuild dateutil CPG with `--include-source`
- [ ] Rebuild greploom index after CPG rebuild
- [ ] Re-run extraction with source-populated CPG to measure quality improvement
- [ ] File issue: unit tests for extract.py (code-translation-skills)
- [ ] File issue: vLLM connection drops (code-translation-skills)
- [ ] File issue: greploom query result field naming (rdwj/greploom)

## Patterns

**Recurring (3rd instance): Explore the actual data source, not a convenience view of it.** M0: tool output format assumptions. M1: `treeloom query --json` vs raw CPG JSON. M2: assumed greploom returns `source`/`structural_context` fields without checking. Three retros, same pattern. The M1 countermeasure was stated but not applied. Need a stronger mechanism.

**Start:** Before writing code that reads a tool's output, run the tool once with representative input and dump/inspect the actual JSON structure. Not "check the docs" or "check the CLI help" — literally run it and read the output. Add this as a checklist item in SKILL.md templates.

**Stop:** Assuming field names from context or convention. `source` sounded right but didn't exist. `text` was the actual field. Always verify.

**Continue:** Iterative extraction → comparison → diagnosis → fix cycles. Three runs produced a meaningfully better result than one run would have.

**Continue:** Building evaluation tools (compare.py) alongside the thing being evaluated. Having quantitative comparison data made the fix cycles efficient and measurable.
