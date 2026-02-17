---
name: behavioral-contract-extractor
description: >
  Extract behavioral contracts for functions and modules that capture what code does, not how
  it does it. Use this skill whenever you need to understand the observable behavior of code
  before translating it, generate verification criteria for migration, identify what a function
  reads/writes/mutates, surface implicit behaviors that could break during translation, or
  produce specifications for idiomatic rewrites in a target language. Also trigger when someone
  says "what does this function do," "extract the contract," "what are the side effects,"
  "what should the translated version preserve," "generate behavioral specs," or "what would
  break if we rewrote this." This skill is the bridge between structural analysis (what the
  code looks like) and functional verification (what the code does).
---

# Behavioral Contract Extractor

For each function or module in a codebase, extract a behavioral contract that captures
observable behavior: what it reads, what it produces, what side effects it has, what errors
it raises, and what implicit behaviors exist that could break during translation.

This skill operates on the principle that code migration has three levels: syntactic (change
the syntax), structural (reorganize the patterns), and functional (preserve the behavior).
The behavioral contract captures the functional level — it's the specification that both
the source and target code must satisfy.

## Why Contracts Matter

A function that reads a CSV and sends emails has the same *behavior* regardless of whether
it's written in Python 2, Python 3, Rust, or Go. The contract captures this behavior
abstractly: "takes a file path and SMTP host, returns count of emails sent, raises
FileNotFoundError if the file doesn't exist."

Without contracts, migration is blind — you translate syntax and hope the behavior
survives. With contracts, you have a specification to verify against and a basis for
suggesting idiomatic alternatives in the target language.

Contracts also enable the atomic work decomposition strategy. When a Haiku-class model
fixes a `has_key()` call inside a function, the work item includes the contract: "this
function returns `list[int]` and raises `ModbusError` on timeout — your change must
preserve that." The reasoning happened upstream (here, in Sonnet), so the execution can
be mechanical.

## When to Use

- After running codebase analysis (universal-code-graph or py2to3-codebase-analyzer)
- Before any migration or translation work begins
- When you need to verify behavioral equivalence after translation
- When exploring whether a function could be simplified in the target language
- When decomposing work into atomic, model-appropriate items
- When generating targeted test cases for uncovered code paths

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| **raw-scan.json** | universal-code-graph / codebase-analyzer | Per-file analysis with imports, findings, metrics |
| **call-graph.json** | universal-code-graph | Function-level call relationships (provides neighborhood context) |
| **codebase_path** | User | Root directory (for reading source code of each function) |
| **output_dir** | User | Where to write contracts |
| **scope** (optional) | User | Restrict to specific modules/functions. Default: all. |
| **depth** (optional) | User | How deep to analyze: `shallow` (inputs/outputs only), `standard` (+ side effects, errors), `deep` (+ implicit behaviors, modernization hints). Default: `standard`. |

## Outputs

| File | Format | Purpose |
|------|--------|---------|
| `behavioral-contracts.json` | JSON | Per-function behavioral contracts |
| `contract-summary.md` | Markdown | Human-readable summary of key contracts |
| `uncovered-paths.json` | JSON | Code paths with no test coverage that the contract identified |
| `implicit-behaviors.json` | JSON | Behaviors that depend on language-specific semantics (dict ordering, GIL, encoding defaults) |

## Contract Format

Each function produces a contract like:

```json
{
  "function": "src.io.csv_mailer.send_csv_emails",
  "language": "python",
  "file": "src/io/csv_mailer.py",
  "line_range": [42, 87],
  "contract": {
    "inputs": {
      "parameters": [
        {"name": "csv_path", "type": "str", "semantics": "filesystem path to CSV file"},
        {"name": "smtp_host", "type": "str", "semantics": "SMTP server hostname"},
        {"name": "port", "type": "int", "default": 587, "semantics": "SMTP port"}
      ],
      "reads": ["filesystem:csv_path", "network:smtp_host:port"],
      "env_vars": ["SMTP_USER", "SMTP_PASS"]
    },
    "outputs": {
      "returns": {"type": "int", "semantics": "count of successfully sent emails"},
      "writes": ["network:smtp (sends MIME emails)"],
      "mutations": []
    },
    "side_effects": [
      "logging.info per email sent",
      "logging.error on send failure with traceback"
    ],
    "error_conditions": [
      {"exception": "FileNotFoundError", "when": "csv_path does not exist"},
      {"exception": "smtplib.SMTPAuthenticationError", "when": "bad SMTP credentials"},
      {"exception": "csv.Error", "when": "malformed CSV (missing headers or bad quoting)"}
    ],
    "implicit_behaviors": [
      {"behavior": "relies on dict ordering", "since": "Python 3.7+", "risk": "medium"},
      {"behavior": "assumes UTF-8 encoding for CSV", "risk": "high for non-ASCII data"},
      {"behavior": "retries SMTP connection 3 times", "location": "_connect() helper", "risk": "low"}
    ],
    "complexity": "low",
    "pure": false,
    "test_coverage": "partial"
  },
  "verification_hints": [
    "test with: empty CSV, single row, 1000 rows, malformed row, unicode in fields",
    "test with: unreachable SMTP, auth failure, timeout",
    "compare: return value, emails actually sent (use mock SMTP)"
  ],
  "modernization_opportunities": [
    {
      "target": "rust",
      "suggestion": "serde + csv crate for parsing, lettre for SMTP",
      "estimated_reduction": "45 lines → 15 lines",
      "risk": "low — well-mapped standard library equivalents"
    }
  ]
}
```

## Workflow

### Step 1: Load Analysis Data

Read `raw-scan.json` and `call-graph.json` from a previous codebase analysis run.
Build an index of all functions with their source locations, import context, and
call graph neighborhood.

```bash
python3 scripts/extract_contracts.py <codebase_path> \
    --raw-scan <analysis_dir>/raw-scan.json \
    --call-graph <analysis_dir>/call-graph.json \
    --output <output_dir> \
    [--scope "src/io/*.py"] \
    [--depth standard]
```

### Step 2: Process Functions in Topological Order

Functions are processed leaf-first (callees before callers) so that when we analyze
a function, we already have contracts for the functions it calls. This gives us:

- Return type information from callees
- Error propagation chains
- Side effect accumulation

### Step 3: Extract Contract per Function

For each function, the extractor:

1. **Reads the function source** from disk (bounded by line range from analysis).
2. **Gathers neighborhood context** from the call graph: what does this function call?
   What calls this function? What are its imports?
3. **Sends to LLM (Sonnet tier)** with a structured prompt:
   - "Here is a function and its call context. Extract the behavioral contract."
   - The prompt includes the contract JSON schema as the expected output format.
   - Sonnet infers: parameter semantics, return semantics, side effects, error
     conditions, and implicit behaviors.
4. **Validates the contract** against the source code: do the listed parameters match
   the function signature? Are the listed imports actually used? Are the error types
   actually raised or caught?
5. **Tags implicit behaviors** that depend on language-specific semantics (dict ordering,
   GIL, encoding defaults, integer overflow).

### Step 4: Identify Uncovered Paths

Compare the contract's verification hints against any existing tests. Code paths
listed in the contract but not covered by tests become entries in `uncovered-paths.json`.
These feed into the test-scaffold-generator for targeted test creation.

### Step 5: Generate Summary

Produce `contract-summary.md` with:
- Total functions analyzed
- Functions with critical implicit behaviors
- Functions with no test coverage for key error paths
- Top modernization opportunities across the codebase

## What Gets Lost — and How Contracts Catch It

| Risk | Example | Contract field that catches it |
|------|---------|-------------------------------|
| Error handling drift | Python `except` vs Rust `Result<T,E>` | `error_conditions` — lists specific exceptions |
| Side effect omission | Logging dropped in rewrite | `side_effects` — lists every observable effect |
| Implicit behavior | Dict ordering, GIL, encoding defaults | `implicit_behaviors` — flags with risk level |
| Performance drift | Hot-path function slows down | `complexity` + verification hints |
| Platform workarounds | `sleep(0.1)` for race condition | `implicit_behaviors` with "investigate" marker |

## Integration with Other Skills

| Skill | Relationship |
|-------|-------------|
| universal-code-graph | **Upstream** — provides raw-scan.json and call-graph.json |
| work-item-generator | **Downstream** — contracts provide context for each work item |
| haiku-pattern-fixer | **Downstream** — work items include contract for verification |
| translation-verifier | **Downstream** — contracts are the verification specification |
| modernization-advisor | **Downstream** — contracts include modernization hints |
| py2to3-behavioral-diff-generator | **Peer** — contracts add targeted test generation |
| migration-dashboard | **Downstream** — contract confidence scores feed dashboard |

## Important Considerations

**Contracts are approximations.** LLM-extracted contracts may miss subtle behaviors
or hallucinate behaviors that don't exist. The validation step catches obvious errors,
but human review of critical-path function contracts is recommended.

**Processing order matters.** Leaf functions first, then their callers. This gives
callers access to callee contracts for better inference of error propagation and
return type semantics.

**Scope management.** For large codebases, extract contracts incrementally — one
package at a time, or only for modules in the current migration wave. The `--scope`
flag supports glob patterns.

**Not all functions need deep contracts.** Simple getters, setters, and trivial
utility functions can use `shallow` depth. Reserve `deep` analysis for functions
that handle I/O, binary data, encoding, or complex state.

## Model Tier

**Sonnet** (with Haiku pre-processing). Inferring behavioral specifications from code requires understanding what functions do, not just what they look like.

Decomposition: Haiku extracts function signatures, docstrings, parameter types, return types, and test assertions — the raw material for contracts. Sonnet synthesizes these into behavioral contracts, inferring implicit behaviors (side effects, error conditions, ordering assumptions). Process one function per Sonnet call, topological order, so downstream functions can reference upstream contracts.

## References

- `ARCHITECTURE-universal-code-graph.md` — Behavioral Analysis & Verification section
- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents
