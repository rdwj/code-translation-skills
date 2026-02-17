# Code Examples and Pattern Tables

**This file supports:** `/sessions/stoic-practical-faraday/mnt/code-translation-skills/skills/modernization-advisor/SKILL.md`

## Complete Opportunity Object Example

Below is a full JSON example of a modernization opportunity output by the skill:

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
    }
  ],
  "effort_estimate": {
    "rewrite_hours": 4,
    "testing_hours": 3,
    "review_hours": 1,
    "total_hours": 8,
    "notes": "Effort is primarily async structuring and error mapping. Domain logic is straightforward."
  }
}
```

## Sample Modernization Report (Markdown)

Example of a human-readable modernization report:

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
  - Goroutines enable parallel email sending
  - All libraries are stdlib or well-established
  - Simple error handling
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

## Per-Function Analysis Examples

**Function**: `send_csv_emails(csv_path, smtp_host)`
- **Lines**: 45
- **Risk**: Medium (async restructuring)
- **Best target**: Rust (73% reduction) vs Go (38% reduction)

## Recommendations

1. **If prioritizing code simplification**: Rewrite in Rust with `serde` + `lettre` (73% reduction, async I/O gains)
2. **If prioritizing concurrency gains**: Rewrite in Go with goroutines (parallel email sending, simpler model)
3. **If maintaining Python**: Upgrade to Python 3.12+ with `asyncio` + `aiosmtplib` (minor simplification)
```

## Ecosystem Mapping by Language

### Rust Ecosystem Mappings
- **CSV**: `csv` crate (polars for data analysis)
- **SMTP**: `lettre` (async-first, modern)
- **Async runtime**: `tokio` (de facto standard)
- **Logging**: `tracing` (structured logging)
- **Error handling**: `anyhow` or `thiserror` for ergonomic errors

### Go Ecosystem Mappings
- **CSV**: `encoding/csv` (stdlib)
- **SMTP**: `net/smtp` (stdlib)
- **Concurrency**: `goroutines` + `channels` (language primitives)
- **Logging**: `log` (stdlib) or `logrus` (popular third-party)

## Opportunity for Simplification Example

**Original (45 lines Python):**
```python
import csv, smtplib, logging
def send_csv_emails(csv_path, smtp_host):
    count = 0
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        server = smtplib.SMTP(smtp_host)
        try:
            for row in reader:
                email = row['email']
                # ... email building logic
                server.sendmail(from_addr, email, msg)
                count += 1
                logging.info(f"Sent to {email}")
        except smtplib.SMTPAuthenticationError as e:
            logging.error(f"Auth failed: {e}")
        finally:
            server.quit()
    return count
```

**Rust equivalent (12 lines with idiomatic patterns):**
Uses `serde` for CSV parsing (eliminating manual dict access) and `lettre` for async SMTP (eliminating imperative connection management).

## Risk Assessment Levels

| Risk Level | Example | Confidence | Migration Feasibility |
|---|---|---|---|
| **Low** | Direct library equivalents (csv → csv, logging → logging) | 0.9+ | Proceed immediately |
| **Medium** | Requires async restructuring (smtplib → lettre) | 0.75–0.85 | Proceed with testing |
| **High** | Significant architectural changes (threading → goroutines) | 0.5–0.75 | Requires careful review |
| **Critical** | Language-specific semantics, no equivalent (pickle → ?) | <0.5 | Not recommended |
