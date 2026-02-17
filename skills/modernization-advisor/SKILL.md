---
name: modernization-advisor
description: >
  Given a behavioral contract and target language, suggest idiomatic alternatives that leverage target-language
  idioms, libraries, and patterns — with specific examples and risk assessment. Use this skill whenever you need to
  recommend how code could be simplified or made idiomatic in a target language, identify target-language libraries
  that could replace source-language dependencies, estimate effort reduction for idiomatic rewrites, or generate
  a modernization opportunities report. Also trigger when someone says "modernize this," "how would this look in
  rust," "idiomatic alternatives," "simplify in target language," "what libraries should we use," "modernization
  opportunities," "are there better patterns in go," or "what's the idiomatic way to do this in python 3."
  This skill is advisory only — it suggests opportunities but doesn't do the rewriting itself.
---

# Modernization Advisor

Given a function's behavioral contract and a target language, suggest specific idiomatic alternatives that
leverage target-language libraries, patterns, and paradigms. This skill identifies opportunities to simplify
code, replace dependencies, and use target-language idioms — with risk assessment, library equivalents, and
concrete code sketches.

This skill operates at the strategic level: "Your 40-line Python function that reads a CSV file and sends
emails could be 8 lines in Rust using `serde` + `lettre`, assuming you're willing to accept medium-risk
architectural changes around error handling." It's advisory — the decision to rewrite and the actual rewrite
belong to humans or dedicated translation skills.

## When to Use

- After extracting behavioral contracts (behavioral-contract-extractor)
- When exploring whether a module could be simplified in a target language
- When planning a migration to evaluate modernization opportunities alongside pure translation
- When stakeholders ask "could we improve this while we migrate?"
- When you need to estimate the value of a full rewrite vs. mechanical translation
- When identifying which dependencies have idiomatic equivalents in the target language
- When evaluating language-specific patterns that could reduce code size or improve maintainability

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| **behavioral_contract** | behavioral-contract-extractor | Contract file (`behavioral-contracts.json`) or individual contract JSON. Defines what the code does, not how. |
| **source_code** | User / file system | Path to source code file(s) or function(s) being evaluated |
| **target_language** | User | Target language (e.g., `rust`, `go`, `python3`, `java`, `typescript`) |
| **target_ecosystem_knowledge** (optional) | User / embedded | Key libraries and idioms in target language. Defaults to built-in knowledge. |
| **output_dir** | User | Where to write modernization analysis (defaults to `./modernization-analysis/`) |

## Outputs

All outputs go to `<output_dir>/`:

| File | Format | Purpose |
|------|--------|---------|
| `modernization-opportunities.json` | JSON | Per-function suggestions with risk, effort, and ecosystem mapping |
| `modernization-report.md` | Markdown | Human-readable summary of opportunities, organized by risk level and domain |
| `ecosystem-mapping.json` | JSON | Source language dependencies mapped to target language equivalents with confidence scores |

## Workflow

### Step 1: Load Behavioral Contract

Read the behavioral contract produced by the behavioral-contract-extractor. The contract is the specification:
"this function takes a file path and SMTP host, returns an int count of emails sent, raises FileNotFoundError
if the file doesn't exist."

```bash
python3 scripts/analyze_modernization.py \
    --contract <behavioral_contract.json> \
    --source-code <source_file> \
    --target-language <target> \
    --output <output_dir>
```

### Step 2: Identify Source Patterns

From the contract and source code, identify:
- **Input/output patterns**: What types of data does this function handle?
- **Dependencies**: What external libraries does it use (csv, smtplib, logging, etc.)?
- **Implicit behaviors**: Does it rely on language-specific semantics (dict ordering, GIL, encoding)?
- **Error handling**: How are errors handled?
- **Side effects**: What side effects does it have (I/O, logging, mutations)?
- **Data transformations**: What domain-specific patterns (CSV parsing, email formatting, retries)?

### Step 3: Match Against Target Language Ecosystem

For each identified pattern, search the target language ecosystem for:

1. **Direct library equivalents**: Does the target language have a library that handles the same domain?
   - Python `csv` + `smtplib` → Rust `csv` + `lettre`
   - Python `requests` → Rust `reqwest`, Go `net/http`, TypeScript `axios`
   - Python `threading` → Go `goroutines`, Rust `tokio`, Java `Thread`

2. **Idiomatic patterns**: How would this code be written idiomatically in the target language?
   - Python imperative loop → Rust iterator chains and `filter_map`
   - Python try/except → Go `error` return values vs Rust `Result<T, E>`
   - Python class with state → Rust `struct` with `impl` blocks
   - Python context managers → Go `defer`, Rust RAII

3. **Opportunity for simplification**: Can the target language express the same contract more concisely?
   - Stronger type system → catch errors at compile time
   - Closures and functional patterns → eliminate boilerplate
   - Zero-copy semantics → avoid data copying
   - Pattern matching → replace conditional chains

### Step 4: Generate Per-Function Suggestions

For each function, produce a suggestion object with:
- Opportunity ID and title
- Pattern matching (source pattern → target pattern)
- Library equivalents with confidence scores
- Estimated code reduction (lines before/after, percentage)
- Risk assessment (level, reasons, mitigations)
- Code sketch (minimal idiomatic example)
- Contract preservation (inputs, outputs, errors, side effects)
- Ecosystem equivalents (full library mapping)
- Effort estimate (hours for rewrite, testing, review)

See `references/EXAMPLES.md` for complete opportunity object structure and sample Rust/Go opportunities.

### Step 5: Rate by Risk and Confidence

For each suggestion, assess both adoption and technical risk:

- **Low risk**: 1:1 library equivalents, clear error mapping, no architectural changes. Confidence: 0.9+
- **Medium risk**: Restructuring needed, async/concurrency differs, idioms differ. Confidence: 0.75–0.85
- **High risk**: No direct equivalent, significant architectural change required. Confidence: 0.5–0.75
- **Critical risk**: Language-specific behavior, not portable. Confidence: <0.5 (not recommended)

See `references/EXAMPLES.md` for risk level examples and assessment patterns.

### Step 6: Generate Human-Readable Report

Create `modernization-report.md` with:
- Executive summary (module, functions analyzed, opportunities, recommended language)
- High-confidence opportunities (risk, confidence, code reduction, effort, benefits/concerns)
- Dependency mapping table (source library → target equivalents)
- Per-function analysis
- Recommendations by priority (simplification, concurrency, performance)
- Risk summary aggregated by opportunity

See `references/EXAMPLES.md` for sample report structure and ecosystem mappings.

### Step 7: Integration with Migration Dashboard

The `modernization-opportunities.json` feeds into the migration dashboard's **Opportunities panel**, displaying each opportunity with ID, title, risk level, confidence score, estimated reduction, and effort hours. This allows stakeholders to view all modernization opportunities for the codebase, filter by risk level or target language, and make informed decisions about which opportunities to pursue.

Update the migration-state-tracker:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py <state_file> \
    record-output \
    --module "src/io/csv_mailer.py" \
    --output-path <output_dir>/modernization-opportunities.json \
    --field "modernization_opportunities"
```

## Suggestion Format Details

### Per-Function Opportunity Format

Each opportunity includes:
- Function name, source language, line count, target language, opportunity ID
- Title and description
- Pattern match (source → target pattern)
- Libraries array (source → target mapping with confidence and notes)
- Estimated reduction (lines, percentage, confidence level)
- Risk assessment (level, confidence, reasons, mitigations)
- Contract preservation (input/output/error/side-effect mapping)
- Code sketch (minimal idiomatic example)
- Ecosystem equivalents (full library mapping with version compatibility)
- Effort estimate (rewrite, testing, review hours)

See `references/EXAMPLES.md` for complete JSON structure with all fields populated.

## Model Tier

**Haiku (50%) + Sonnet (50%).** Simple library modernization (six→removal, old-style classes→new-style) is pattern matching — use Haiku. Architectural modernization suggestions (refactoring to context managers, replacing custom implementations with stdlib, async opportunities) require Sonnet.

## Old Model Tier Documentation

**Sonnet.** This skill requires deep reasoning about target-language idioms, ecosystem knowledge, and capability
matching. Haiku cannot reliably infer idiomatic patterns or assess risk. Each opportunity is independent,
keeping context bounded.

**Cost model**: For a function, send to Sonnet with:
- The behavioral contract (100–200 tokens)
- Source code (200–500 tokens)
- Target language context (ecosystem libraries, idioms — 300–500 tokens from embedded knowledge)
- Per-function prompt (~100 tokens)

Result: 700–1300 tokens in, ~500–1000 tokens out. A 500-function codebase at 2–3 opportunities per function
is ~2500 Sonnet calls, which is expensive but parallelizable.

## Integration with Other Skills

### Upstream: behavioral-contract-extractor

This skill consumes the behavioral contract produced by the behavioral-contract-extractor. The contract is the
specification that both source and target code must satisfy.

### Downstream: migration-state-tracker

After analysis, modernization opportunities feed into the migration-state-tracker's `opportunities` field:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py <state_file> \
    record-output \
    --module "src/io/csv_mailer.py" \
    --output-path <output_dir>/modernization-opportunities.json
```

### Integration with migration-dashboard

The dashboard displays opportunities in an **Opportunities panel**, allowing stakeholders to:
1. See all modernization opportunities for the codebase
2. Filter by risk level, target language, code reduction
3. Review sketches and ecosystem mappings
4. Decide which opportunities to pursue

## Important Considerations

### This Skill is Advisory Only

This skill **does not translate code**. It suggests opportunities and provides sketches. The actual rewriting
is done by:
- Human developers (manual rewrite)
- Specialized translation skills (py2to3-automated-converter, universal-code-translator, etc.)
- Bespoke tools (for language-specific migrations)

### Risk Assessment is Critical

Never recommend a modernization without assessing risk. A high-risk suggestion can derail a migration if adopted
naively. Always pair the suggestion with:
- Specific risks (async restructuring, error handling changes, library maturity)
- Mitigations (test coverage, gradual rollout, fallback plan)
- Effort estimates (hours to execute the rewrite)
- Alternative languages if the primary choice is high-risk

### Library Equivalents Must Be Validated

The ecosystem_equivalents section maps source to target libraries. These mappings are **not automatic**. For
each mapping, validate:
- Does the target library handle the same domain? (e.g., `csv` → `csv` is 1:1, but `smtplib` → `lettre` requires
  async restructuring)
- Are there any behavioral differences? (e.g., `requests` blocking vs `reqwest` async)
- Is the target library well-maintained? (no abandoned projects)
- What's the learning curve for the team?

### Code Sketches Must Be Realistic

The code_sketch section provides a brief example. It should:
- Demonstrate the idiomatic pattern in the target language
- Preserve the contract (same inputs, outputs, error conditions)
- Be runnable (at least compile/syntax-check)
- Be brief (under 30 lines ideally)

It's not a production implementation, but it should be plausible.

### Contracts Drive Everything

All suggestions are rooted in the behavioral contract. If the contract says "this function returns an int count
of items processed," the target language suggestion must also return a count (int, usize, etc.). Don't suggest
a rewrite that changes the contract — that's a redesign, not a modernization.

## References

- `behavioral-contract-extractor` — Produces the behavioral contracts this skill consumes
- `ARCHITECTURE-universal-code-graph.md` — Describes the code graph system and language ecosystem
- `migration-state-tracker` — Tracks state and consumes opportunity output
- `migration-dashboard` — Visualizes opportunities for stakeholder review
- `py2to3-automated-converter` — Can use modernization suggestions to guide translation
