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

For each function, produce a suggestion object:

```json
{
  "function": "src.io.csv_mailer.send_csv_emails",
  "source_lines": 45,
  "target_language": "rust",
  "modernization_opportunities": [
    {
      "opportunity_id": "opp_1",
      "title": "Use serde + lettre for CSV parsing and SMTP",
      "description": "Replace csv + smtplib with Rust idioms: serde for structured data parsing, lettre for async SMTP",
      "pattern_match": {
        "source_pattern": "csv.DictReader + smtplib.SMTP in loop",
        "target_pattern": "serde::Deserialize + lettre::SmtpTransport"
      },
      "libraries": [
        {
          "source_lib": "csv",
          "target_lib": "csv",
          "confidence": 0.95,
          "notes": "Direct equivalent, well-maintained"
        },
        {
          "source_lib": "smtplib",
          "target_lib": "lettre",
          "confidence": 0.85,
          "notes": "Async-first, requires restructuring for tokio runtime"
        },
        {
          "source_lib": "logging",
          "target_lib": "tracing",
          "confidence": 0.90,
          "notes": "Idiomatic Rust logging with structured output"
        }
      ],
      "estimated_reduction": {
        "source_lines": 45,
        "target_lines": 12,
        "reduction_percent": 73
      },
      "risk_assessment": {
        "level": "medium",
        "reasons": [
          "Requires restructuring for async I/O (tokio runtime)",
          "Error handling changes: Python exceptions → Rust Result<T, E>",
          "smtplib.SMTPAuthenticationError → lettre::transport::smtp::error::Error with pattern matching"
        ],
        "mitigations": [
          "Lettre has well-defined error types, easier to test",
          "Async SMTP is more performant and allows batch operations",
          "Type safety catches many edge cases at compile time"
        ]
      },
      "code_sketch": {
        "description": "Minimal idiomatic Rust implementation",
        "code": "use csv::ReaderBuilder;\nuse lettre::{SmtpTransport, Transport};\nuse lettre::message::MultiPart;\n\n#[tokio::main]\nasync fn send_csv_emails(csv_path: &str, smtp_host: &str, port: u16) -> Result<usize, Box<dyn std::error::Error>> {\n    let file = std::fs::File::open(csv_path)?;\n    let mut reader = ReaderBuilder::new().has_headers(true).from_reader(file);\n    \n    let transport = SmtpTransport::builder_dangerous(smtp_host).port(port).build()?;\n    let mut count = 0;\n    \n    for result in reader.deserialize() {\n        let (email, _): (String, String) = result?;\n        let msg = MultiPart::alternative().build();\n        match transport.send(&msg) {\n            Ok(_) => { count += 1; tracing::info!(target: email); },\n            Err(e) => { tracing::error!(target: email, error: ?e); }\n        }\n    }\n    Ok(count)\n}\n"
      },
      "contract_preservation": {
        "input_semantics": "str (filesystem path, SMTP host) → preserved as &str",
        "output_semantics": "int (count of emails) → preserved as usize",
        "error_conditions": [
          { "source": "FileNotFoundError", "target": "std::io::Error via File::open", "preserved": true },
          { "source": "smtplib.SMTPAuthenticationError", "target": "lettre::transport::smtp::Error with pattern match", "preserved": true }
        ],
        "side_effects": [
          { "source": "logging.info per email", "target": "tracing::info! macro", "preserved": true }
        ]
      },
      "ecosystem_equivalents": [
        {
          "source_crate": "csv",
          "target_crate": "csv",
          "mapping_type": "direct",
          "version_compat": "csv 1.3+ compatible with lettre 0.11+"
        },
        {
          "source_crate": "smtplib (stdlib)",
          "target_crate": "lettre",
          "mapping_type": "library_replacement",
          "version_compat": "lettre 0.11+ has async support"
        },
        {
          "source_crate": "logging (stdlib)",
          "target_crate": "tracing",
          "mapping_type": "idiomatic_upgrade",
          "version_compat": "tracing 0.1+"
        }
      ],
      "effort_estimate": {
        "rewrite_hours": 4,
        "testing_hours": 3,
        "review_hours": 1,
        "total_hours": 8,
        "notes": "Mostly effort is async structuring and error mapping. Domain logic is straightforward."
      }
    },
    {
      "opportunity_id": "opp_2",
      "title": "Go alternative: csv + net/smtp with goroutines",
      "target_language": "go",
      "description": "Leverage Go's concurrency model with goroutines for parallel email sending",
      "pattern_match": {
        "source_pattern": "Sequential loop: for row in csv.DictReader",
        "target_pattern": "Parallel: for range rows with worker goroutines + buffered channel"
      },
      "estimated_reduction": {
        "source_lines": 45,
        "target_lines": 28,
        "reduction_percent": 38
      },
      "risk_assessment": {
        "level": "low",
        "reasons": [
          "Go's net/smtp and encoding/csv are stdlib, well-tested",
          "Goroutines are idiomatic for I/O-bound workloads",
          "Error handling via return values is familiar to Python developers"
        ],
        "benefits": [
          "Parallel email sending (goroutines) beats Python's serial approach + GIL",
          "Single executable binary, cross-platform",
          "Simpler deployment than Python + dependencies"
        ]
      },
      "code_sketch": {
        "code": "package main\nimport (\n\t\"encoding/csv\"\n\t\"fmt\"\n\t\"net/smtp\"\n\t\"os\"\n)\n\nfunc sendCSVEmails(csvPath, smtpHost string, port int) (int, error) {\n\tfile, err := os.Open(csvPath)\n\tif err != nil { return 0, err }\n\tdefer file.Close()\n\t\n\treadCloser := csv.NewReader(file)\n\trecords, err := readCloser.ReadAll()\n\tif err != nil { return 0, err }\n\t\n\tcount := 0\n\tfor _, record := range records {\n\t\tauth := smtp.PlainAuth(\"\", os.Getenv(\"SMTP_USER\"), os.Getenv(\"SMTP_PASS\"), smtpHost)\n\t\taddr := fmt.Sprintf(\"%s:%d\", smtpHost, port)\n\t\terr := smtp.SendMail(addr, auth, from, []string{record[0]}, []byte(msg))\n\t\tif err == nil { count++ }\n\t}\n\treturn count, nil\n}\n"
      }
    }
  ]
}
```

### Step 5: Rate by Risk and Confidence

For each suggestion:

**Risk assessment** rates both adoption risk and technical risk:

- **Low risk**: Source and target libraries are well-mapped (1:1 equivalents). Error types map clearly. No architectural
  changes needed. Domain logic is portable without modification.
  - Example: Python `csv` → Rust `csv` crate
  - Confidence: 0.9+

- **Medium risk**: Target library exists but requires some restructuring. Error handling changes. Async/concurrency
  model differs. Idioms differ but domain logic is portable.
  - Example: Python `csv` + `smtplib` → Rust `csv` + `lettre` (requires tokio async restructuring)
  - Confidence: 0.75–0.85

- **High risk**: No direct equivalent library. Requires significant architectural change. New idioms, patterns, or
  concurrency model. Test coverage must expand.
  - Example: Python `threading` + custom job queue → Go goroutines + channels (different concurrency model, no
    shared memory)
  - Confidence: 0.5–0.75

- **Critical risk**: Behavior is language-specific and not portable. Requires redesign or domain change. Not
  recommended without major refactoring.
  - Example: Python `pickle` (language-specific serialization) has no safe Go/Rust equivalent. Use protobuf/JSON
    instead.
  - Confidence: <0.5 (not recommended)

### Step 6: Generate Human-Readable Report

Create `modernization-report.md` with:

```markdown
# Modernization Opportunities Report

## Executive Summary
- Module: `src.io.csv_mailer`
- Total functions analyzed: 3
- Modernization opportunities identified: 5
- Recommended language: Rust (low risk, 65% code reduction)
- Alternative: Go (low risk, 38% code reduction + concurrency benefits)

## High-Confidence Opportunities (Low Risk)

### Opportunity 1: Rust with serde + lettre
- **Risk**: Medium
- **Confidence**: 0.85
- **Code reduction**: 45 → 12 lines (73%)
- **Effort**: ~8 hours (4 rewrite, 3 test, 1 review)
- **Benefits**:
  - Type safety catches encoding/parsing errors at compile time
  - Async SMTP is more efficient than Python's blocking I/O
  - Single executable binary
- **Concerns**:
  - Must restructure for tokio async runtime
  - Error handling is more verbose (Result<T, E> pattern matching)
- **Libraries to learn**:
  - `csv` (CSV parsing)
  - `lettre` (SMTP)
  - `tokio` (async runtime)

### Opportunity 2: Go with stdlib + goroutines
- **Risk**: Low
- **Confidence**: 0.90
- **Code reduction**: 45 → 28 lines (38%)
- **Effort**: ~6 hours (3 rewrite, 2 test, 1 review)
- **Benefits**:
  - Goroutines enable parallel email sending (faster than Python's serial approach)
  - All libraries are stdlib or well-established
  - Simple error handling (error return values)
  - Single executable, cross-platform
- **Concerns**:
  - Less code reduction than Rust
  - Concurrency requires careful channel management

## Dependency Mapping

| Source Library | Target (Rust) | Target (Go) | Confidence | Notes |
|---|---|---|---|---|
| `csv` | `csv` crate | `encoding/csv` | 0.95 | Direct equivalents |
| `smtplib` | `lettre` | `net/smtp` | 0.85–0.90 | Both solid, lettre is async |
| `logging` | `tracing` | `log` | 0.90 | Both idiomatic |
| `os` (env vars) | `std::env` | `os` | 0.95 | Direct equivalents |

## Ecosystem Knowledge Summary

### Rust Ecosystem
- **CSV**: `csv` crate (polars for data analysis)
- **SMTP**: `lettre` (async-first, modern)
- **Async runtime**: `tokio` (de facto standard)
- **Logging**: `tracing` (structured logging)
- **Error handling**: `anyhow` or `thiserror` for ergonomic errors

### Go Ecosystem
- **CSV**: `encoding/csv` (stdlib)
- **SMTP**: `net/smtp` (stdlib)
- **Concurrency**: `goroutines` + `channels` (language primitives)
- **Logging**: `log` (stdlib) or `logrus` (popular third-party)

## Per-Function Analysis

[Detailed analysis of send_csv_emails, _connect_smtp, _parse_csv_row, etc.]

## Recommendations

1. **If prioritizing code simplification**: Rewrite in Rust with `serde` + `lettre` (73% reduction, async I/O gains)
2. **If prioritizing concurrency gains**: Rewrite in Go with goroutines (parallel email sending, simpler model)
3. **If maintaining Python**: Upgrade to Python 3.12+ with `asyncio` + `aiosmtplib` (minor simplification)

## Risk Summary by Opportunity
- Low risk: 2 (Go + stdlib, Python + asyncio)
- Medium risk: 2 (Rust + tokio, Java + Spring)
- High risk: 0
- Critical risk: 0

→ **All opportunities are viable.** Choice depends on team expertise and deployment constraints.
```

### Step 7: Integration with Migration Dashboard

The `modernization-opportunities.json` feeds into the migration dashboard's **Opportunities panel**:

```json
{
  "module": "src.io.csv_mailer",
  "opportunities": [
    {
      "id": "opp_1",
      "title": "Rust (73% reduction, medium risk)",
      "risk": "medium",
      "confidence": 0.85,
      "estimated_reduction": "45 → 12 lines",
      "effort_hours": 8
    },
    {
      "id": "opp_2",
      "title": "Go (38% reduction + concurrency, low risk)",
      "risk": "low",
      "confidence": 0.90,
      "estimated_reduction": "45 → 28 lines",
      "effort_hours": 6
    }
  ]
}
```

And updates the migration-state-tracker:

```bash
python3 ../py2to3-migration-state-tracker/scripts/update_state.py <state_file> \
    record-output \
    --module "src/io/csv_mailer.py" \
    --output-path <output_dir>/modernization-opportunities.json \
    --field "modernization_opportunities"
```

## Suggestion Format Details

### Per-Function Opportunity Format

```json
{
  "function": "fully.qualified.function.name",
  "source_language": "python",
  "source_file": "path/to/source.py",
  "source_lines": 45,
  "target_language": "rust",
  "opportunity_id": "opp_1_rust_lettre",

  "title": "Use serde + lettre for CSV parsing and SMTP",
  "description": "Replace csv + smtplib with Rust idioms",

  "pattern_match": {
    "source_pattern": "csv.DictReader loop + smtplib.SMTP connection",
    "target_pattern": "serde::Deserialize + lettre::SmtpTransport"
  },

  "libraries": [
    {
      "source_lib": "csv",
      "target_lib": "csv",
      "confidence": 0.95,
      "mapping_type": "direct_equivalent",
      "notes": "Identical API, well-maintained"
    },
    {
      "source_lib": "smtplib (stdlib)",
      "target_lib": "lettre",
      "confidence": 0.85,
      "mapping_type": "library_replacement",
      "notes": "Async-first, requires tokio restructuring"
    },
    {
      "source_lib": "logging (stdlib)",
      "target_lib": "tracing",
      "confidence": 0.90,
      "mapping_type": "idiomatic_upgrade",
      "notes": "Structured logging, better for distributed systems"
    }
  ],

  "estimated_reduction": {
    "source_lines": 45,
    "target_lines": 12,
    "reduction_percent": 73,
    "confidence": 0.80,
    "notes": "Assumes serde macros eliminate manual parsing"
  },

  "risk_assessment": {
    "level": "medium",
    "confidence": 0.85,
    "reasons": [
      "Requires async restructuring (tokio runtime setup)",
      "Error types change from exceptions to Result<T, E>",
      "smtplib.SMTPAuthenticationError → lettre error types with pattern matching"
    ],
    "mitigations": [
      "Lettre's error types are well-defined",
      "Async SMTP is more performant and testable",
      "Type safety catches many edge cases at compile time"
    ]
  },

  "contract_preservation": {
    "input_semantics": [
      {
        "contract": "csv_path: str (filesystem path)",
        "source_impl": "str → File path",
        "target_impl": "&str → std::fs::File::open",
        "preserved": true
      }
    ],
    "output_semantics": [
      {
        "contract": "returns int (count of sent emails)",
        "source_impl": "int from counter",
        "target_impl": "usize (Rust's count type)",
        "preserved": true,
        "note": "usize is unsigned, intentional for count semantics"
      }
    ],
    "error_conditions": [
      {
        "contract": "FileNotFoundError when csv_path doesn't exist",
        "source_impl": "open() raises FileNotFoundError",
        "target_impl": "File::open() returns Err(io::Error)",
        "preserved": true,
        "pattern": "match File::open(csv_path) { Err(e) if e.kind() == io::ErrorKind::NotFound => ... }"
      }
    ],
    "side_effects": [
      {
        "contract": "logging.info per email sent",
        "source_impl": "logging.info() call in loop",
        "target_impl": "tracing::info!() macro",
        "preserved": true
      }
    ]
  },

  "code_sketch": {
    "description": "Minimal, idiomatic Rust implementation demonstrating the opportunity",
    "imports": ["csv", "lettre", "tokio"],
    "code": "use csv::ReaderBuilder;\nuse lettre::{SmtpTransport, Transport};\nuse lettre::message::Message;\n\n#[tokio::main]\nasync fn send_csv_emails(\n    csv_path: &str,\n    smtp_host: &str,\n    port: u16,\n) -> Result<usize, Box<dyn std::error::Error>> {\n    let file = std::fs::File::open(csv_path)?;\n    let mut reader = ReaderBuilder::new()\n        .has_headers(true)\n        .from_reader(file);\n    \n    let transport = SmtpTransport::builder_dangerous(smtp_host)\n        .port(port)\n        .build()?;\n    \n    let mut count = 0;\n    for result in reader.deserialize() {\n        let (email,): (String,) = result?;\n        let msg = Message::builder()\n            .from(\"from@example.com\".parse()?)\n            .to(email.parse()?)\n            .subject(\"Test\")\n            .body(String::from(\"Test\"))?;\n        \n        match transport.send(&msg) {\n            Ok(_) => {\n                tracing::info!(email = %email, \"Sent email\");\n                count += 1;\n            }\n            Err(e) => {\n                tracing::error!(email = %email, error = ?e, \"Failed to send\");\n            }\n        }\n    }\n    Ok(count)\n}\n"
  },

  "ecosystem_equivalents": [
    {
      "source_lib": "csv",
      "target_lib": "csv",
      "crate_version": "1.3+",
      "mapping_type": "direct",
      "feature_parity": 0.98,
      "notes": "Python csv module and Rust csv crate have nearly identical APIs"
    },
    {
      "source_lib": "smtplib",
      "target_lib": "lettre",
      "crate_version": "0.11+",
      "mapping_type": "library_replacement",
      "feature_parity": 0.90,
      "notes": "Lettre is more modern (async), handles more SMTP edge cases"
    },
    {
      "source_lib": "logging",
      "target_lib": "tracing",
      "crate_version": "0.1+",
      "mapping_type": "idiomatic_upgrade",
      "feature_parity": 0.95,
      "notes": "Tracing provides structured logging, better for spans and observability"
    }
  ],

  "effort_estimate": {
    "rewrite_hours": 4,
    "testing_hours": 3,
    "review_hours": 1,
    "total_hours": 8,
    "notes": "Effort is primarily async structuring and error mapping. Domain logic (CSV reading, email building) is straightforward.",
    "dependencies": "Assumes basic Rust proficiency"
  }
}
```

## Model Tier

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
