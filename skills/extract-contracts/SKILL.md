---
name: extract-contracts
description: >
  Enrich skeleton spec elements with LLM-extracted behavioral contracts (purpose,
  pre/postconditions, invariants, side effects, error conditions, trust boundaries).
  M2 step in the vertical plane model. Reads the skeleton spec.json produced by M1
  discover, queries greploom for source code and structural context per element,
  prompts an LLM via OpenAI-compatible API, and writes contracts back with
  metadata: confidence=medium, source=llm_inference, status=needs_review.
triggers:
  - extract contracts
  - behavioral contracts
  - enrich spec
  - populate contracts
  - contract extraction
inputs:
  - spec_path: Path to skeleton spec.json (produced by M1 discover)
  - greploom_db: Path to greploom.db (semantic index from M1)
  - cpg_path: Path to cpg.json (code property graph from M1)
  - llm_endpoint: OpenAI-compatible API endpoint URL
  - llm_model: Model name to pass in the API request (default: inferred from endpoint)
  - scope: "(optional) Element ID prefix to limit extraction (e.g., 'mod:dateutil.parser' for parser module only)"
outputs:
  - spec.json: Enriched specification with populated contracts
model_tier: sonnet
---

# Extract-Contracts: LLM Behavioral Contract Enrichment

Enriches a skeleton `spec.json` with behavioral contracts for each element.
This is the M2 (LLM extraction) step in the vertical plane model — it fills in
the contracts that M1 (discover) left empty, using greploom for context
retrieval and an LLM for inference.

## When to Use

After running the M1 discover skill on a codebase. Takes the skeleton spec
(all elements, no contracts) and produces an enriched spec (all elements,
contracts populated). Run on the full spec or with `--scope` to process a
module at a time. Contracts are marked `needs_review` — human review is the
M3 step.

## Workflow

```
read spec.json → group elements → for each group:
    query greploom (--node, --include-source) → build LLM prompt → call LLM → parse response → write contracts
→ validate enriched spec.json
```

### Step 1: Load spec and filter scope

Read `spec.json`. If `scope` is provided, filter elements to those whose ID
starts with the scope prefix. Group elements by class — class methods are
extracted together with their parent class for coherence. Standalone functions
and modules each get their own extraction call.

If `scope` is omitted, all elements in the spec are processed.

### Step 2: Retrieve context via greploom

For each element or element group, query greploom for source code and
structural context:

```bash
greploom query --db greploom.db --cpg cpg.json --node "<node_ref>" --include-source --format json
```

For class groups, query the class node — greploom returns the class and its
methods together with callers/callees.

The `--node` flag does direct CPG lookup (no semantic search needed since the
exact node reference is already known from the spec). `--include-source` fetches
the source code text embedded in the CPG by treeloom's `--include-source` flag
at build time.

Note greploom query result shape: JSON wraps in `{"metadata": {...}, "results": [...]}`.
Parse the `results` key, not the top-level object.

### Step 3: Prompt LLM for contract extraction

For each element or group, construct a prompt containing:
- Source code from greploom
- Structural context (callers, callees, parameters)
- Any security findings from the spec that reference this element
- The contract schema fields to populate

Call the LLM via OpenAI-compatible API (`/v1/chat/completions`). Request JSON
output.

Contract fields to extract (defined in `spec-schema/spec.schema.json`):

| Field | Type | Description |
|-------|------|-------------|
| `purpose` | string | What this element does, in one paragraph |
| `preconditions` | array of strings | What must be true before invocation |
| `postconditions` | array of strings | What is guaranteed after completion |
| `invariants` | array of strings | Properties that hold throughout |
| `side_effects` | array of strings | Observable effects beyond return value |
| `error_conditions` | array of objects `{condition, behavior, severity}` | Error behaviors |
| `state_transitions` | array of objects `{from_state, to_state, trigger}` | For stateful elements |
| `trust_boundary` | object `{input_trust, output_trust, sanitization}` | Trust and sanitization |
| `thread_safety` | string | Thread safety properties (when relevant) |
| `performance` | string | Performance characteristics (when relevant) |

`state_transitions`, `thread_safety`, and `performance` are optional — omit
them if not applicable to the element.

### Step 4: Parse and validate response

Parse the LLM JSON response. Validate each contract field against expected
types. If parsing fails for an element, log the error and skip that element —
do not crash the whole run.

Update element metadata on success:

```json
{
  "confidence": "medium",
  "source": "llm_inference",
  "status": "needs_review",
  "updated_at": "<ISO 8601 timestamp>",
  "updated_by": "extract-contracts/<model_name>"
}
```

### Step 5: Write enriched spec

Write the updated spec.json back to disk. The script modifies in-place (same
file path as input). Serialize with `indent=2` for human-readable diffs.

### Step 6: Validate

```bash
python spec-schema/render.py spec.json -o spec-review.md
```

Renders the enriched spec to Markdown and validates against the schema. Check
the rendered output for obviously missing or malformed contracts.

## Execution

```bash
python skills/extract-contracts/extract.py \
  --spec dateutil-example/spec.json \
  --greploom-db dateutil-example/greploom.db \
  --cpg dateutil-example/cpg.json \
  --llm-endpoint https://gpt-oss-20b-gpt-oss-model.apps.cluster-n7pd5.n7pd5.sandbox5167.opentlc.com \
  [--scope "mod:dateutil.parser"] \
  [--dry-run]
```

The `--dry-run` flag shows what would be extracted (elements, groupings, prompt
previews) without calling the LLM.

## Available LLM Endpoints

| Model | Endpoint |
|-------|----------|
| RedHatAI/granite-3.3-8b-instruct (8B) | `https://granite-3-3-8b-instruct-granite-model.apps.cluster-n7pd5.n7pd5.sandbox5167.opentlc.com` |
| RedHatAI/gpt-oss-20b (20B) | `https://gpt-oss-20b-gpt-oss-model.apps.cluster-n7pd5.n7pd5.sandbox5167.opentlc.com` |
| RedHatAI/gpt-oss-20b replica (20B) | `https://gpt-oss-20b-2-gpt-oss-model-2.apps.cluster-n7pd5.n7pd5.sandbox5167.opentlc.com` |
| mistralai/Ministral-3-14B-Instruct-2512 (14B) | `https://ministral-3-14b-instruct-mistral-model.apps.cluster-n7pd5.n7pd5.sandbox5167.opentlc.com` |

Start with the 20B model for best contract quality. Use the 8B model for rapid
iteration or when endpoint capacity is constrained.

## Tool-Specific Workarounds

1. **greploom query result shape.** Results wrap in `{"metadata": {...}, "results": [...]}`.
   Parse the `results` key, not the top-level object. Same pattern noted in M1's
   tool-feedback for M2 agents.

2. **LLM JSON output reliability.** Not all models reliably output valid JSON on
   first try. Wrap the parse step in a try/except and log the raw response on
   failure. Consider a retry with an explicit "Output ONLY valid JSON" instruction.

3. **Class method grouping.** Extracting methods individually loses class-level
   context (shared state, invariants). Always group methods with their parent
   class in a single extraction call.

4. **Security findings cross-reference.** Some elements will have associated
   `security_findings` entries from M1 sanicode. Pass these into the prompt so
   the LLM can incorporate known vulnerabilities into `trust_boundary` and
   `error_conditions`.

5. **Scope prefix matching.** Element IDs follow the pattern `<kind>:<dotted.path>`,
   e.g. `mod:dateutil.parser`, `cls:dateutil.parser.parser`, `fn:dateutil.parser.parse`.
   A scope of `mod:dateutil.parser` matches all three because all start with that
   prefix. Use this for module-by-module incremental runs on large codebases.

## Verification

The skill succeeded if:

- Enriched `spec.json` validates against `spec-schema/spec.schema.json` with zero errors
- All in-scope elements have non-empty contracts (at minimum `purpose` is populated)
- All extracted contracts have metadata: `source=llm_inference`, `confidence=medium`, `status=needs_review`
- Elements outside scope retain their original (empty) contracts
- `spec.json` renders to readable Markdown via `spec-schema/render.py`

## Tool Dependencies

- **greploom** >= 0.4.0: Context retrieval (source code + structural graph context)
- **Python 3.10+**: For extract.py
- **requests** or **httpx**: For LLM API calls
- **jsonschema**: For spec validation
- **Ollama**: Required by greploom for embedding generation

## References

- `spec-schema/spec.schema.json` — contract schema definition
- `spec-schema/examples/dateutil-parser.spec.json` — hand-crafted contracts for quality comparison
- `skills/discover/SKILL.md` — the M1 skill that produces inputs for this skill
- `planning/code-translation-kit/roadmap.md` — M2 section
- `planning/code-translation-kit/tool-feedback.md` — greploom CLI reference
