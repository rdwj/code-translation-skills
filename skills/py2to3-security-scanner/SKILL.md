---
name: py2to3-security-scanner
description: >
  Security scanning and SBOM generation for Python 2→3 migrations. Runs at three
  points in the migration lifecycle: baseline scan during discovery (Phase 0),
  regression check after mechanical conversion (Phase 2), and final audit before
  cutover (Phase 5). Produces a CycloneDX SBOM, runs vulnerability scans against
  known CVE databases, performs static analysis for security anti-patterns, checks
  for hardcoded secrets, and verifies dependency pinning. Trigger when someone says
  "security scan," "vulnerability check," "SBOM," "software bill of materials,"
  "dependency audit," "CVE check," "secret detection," "bandit," "pip audit,"
  "security review," or "is this migration secure?"
---

# Security Scanner

Migrations introduce security risk. Upgrading a library for Py3 compatibility might pull in a vulnerable version. Mechanical transformations can introduce patterns that static analyzers flag. Pickle protocol changes can widen deserialization attack surfaces. This skill catches all of that.

**Design principle: the script does the scanning, the LLM reviews the flags.** The scan script runs Bandit, pip-audit, and custom checks deterministically. It produces a structured report with findings classified by severity. The LLM only gets involved for ambiguous findings that need codebase context to triage.

## When to Run

This skill is invoked at three points — not as a standalone phase, but woven into existing phases:

| Invocation | Phase | Purpose | What it produces |
|------------|-------|---------|-----------------|
| **Baseline** | Phase 0 (Discovery) | Establish security posture before any changes | Initial SBOM, baseline vulnerability report, secrets scan |
| **Regression** | After Phase 2 (Mechanical) | Catch issues introduced by conversion | Delta report vs baseline, new vulnerability check on updated deps |
| **Final audit** | Phase 5 (Pre-cutover) | Sign-off artifact for deployment | Final SBOM, full vulnerability report, security gate pass/fail |

The baseline scan gives you a picture of what you're starting with — many Py2 codebases already have known vulnerabilities in pinned dependencies. The regression scan catches problems introduced by the migration itself. The final audit is the deliverable: a clean SBOM and security report that can go to your security team.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `codebase_path` | Yes | Path to the workspace (the `-py3` copy) |
| `--mode` | No | `baseline`, `regression`, or `final` (default: `baseline`) |
| `--baseline-report` | For regression/final | Path to baseline security-report.json for delta comparison |
| `--output` | No | Output directory (default: `migration-analysis/<phase>/security/`) |
| `--sbom-format` | No | `cyclonedx` or `spdx` (default: `cyclonedx`) |
| `--skip-bandit` | No | Skip Bandit static analysis (faster, less thorough) |
| `--skip-secrets` | No | Skip secret/credential detection |
| `--severity-threshold` | No | Minimum severity to report: `low`, `medium`, `high`, `critical` (default: `low`) |

## Outputs

| File | Format | Description |
|------|--------|-------------|
| `sbom.json` | CycloneDX JSON | Software Bill of Materials — all dependencies with versions, licenses, hashes |
| `security-report.json` | JSON | Structured findings: vulnerabilities, secrets, anti-patterns, with severity and location |
| `security-report.md` | Markdown | Human-readable summary with remediation guidance |
| `security-delta.json` | JSON | (regression/final only) New findings vs baseline, resolved findings, changed dependencies |
| `flagged-for-review.json` | JSON | Ambiguous findings that need LLM or human triage |

## What Gets Scanned

### 1. SBOM Generation (all modes)

Parses dependency sources to build a complete inventory:

- `requirements.txt`, `requirements/*.txt` (all variants)
- `setup.py` / `setup.cfg` `install_requires` and `extras_require`
- `pyproject.toml` `[project.dependencies]` and `[project.optional-dependencies]`
- `Pipfile` / `Pipfile.lock`
- `poetry.lock` / `pyproject.toml` `[tool.poetry.dependencies]`
- `conda` environment files (`environment.yml`)
- Vendored packages (detected by `*.dist-info` or `*.egg-info` in tree)

Output is CycloneDX 1.5 JSON by default. Includes package name, version, resolved version (from lock files), license (from PyPI metadata), and SHA256 hash where available.

### 2. Known Vulnerability Scan (all modes)

Checks all dependencies against vulnerability databases:

- `pip-audit` (uses OSV database — covers PyPI advisories, CVEs)
- Falls back to PyPI JSON API + OSV API if pip-audit not installed
- Reports: CVE ID, severity (CVSS), affected version range, fixed version, description

### 3. Static Security Analysis (all modes)

Runs Bandit on the codebase for Python-specific security issues:

- **B101**: `assert` used for security checks (removed in optimized bytecode)
- **B102**: `exec()` usage
- **B301-B303**: Pickle, marshal, md5/sha1 for security purposes
- **B501-B502**: SSL/TLS issues (no cert verification, weak protocols)
- **B601-B602**: Shell injection (`subprocess` with `shell=True`, `os.system`)
- **B701**: Jinja2 autoescape disabled

Falls back to regex-based pattern matching if Bandit is not installed.

### 4. Secret/Credential Detection (all modes)

Scans for accidentally committed secrets:

- API keys (common patterns: `AKIA`, `sk-`, `ghp_`, `xoxb-`, etc.)
- Hardcoded passwords (assignment to variables named `password`, `passwd`, `secret`, `token`, `api_key`)
- Private keys (PEM headers)
- Connection strings with embedded credentials
- `.env` files committed to the repo

### 5. Migration-Specific Security Checks

These are unique to Py2→3 migrations and not covered by generic tools:

- **Pickle protocol changes**: Py2 pickle protocol 2 vs Py3 protocol 5 — cross-version deserialization risks
- **`input()` semantic change**: Py2 `input()` = `eval(raw_input())`. If code still calls `input()` in a Py2-compat path, it's an eval injection risk
- **`exec`/`execfile` conversions**: `execfile()` → `exec(open().read())` can change security properties (encoding handling, file descriptor lifecycle)
- **Hash randomization**: Py3 enables `PYTHONHASHSEED` randomization by default. Code that depends on dict ordering for security checks (e.g., signature computation) may break
- **Default encoding changes**: Py2 defaults to ASCII, Py3 to UTF-8. Encoding mismatches in security-sensitive paths (password hashing, HMAC computation) can cause silent failures
- **SSL/TLS defaults**: Py3.10+ changed default SSL context. Code that worked with Py2's permissive defaults may fail or, worse, fall back to insecure behavior silently

### 6. Dependency Pinning Verification

- Checks that all dependencies have pinned versions (not just `>=`)
- Flags dependencies that were unpinned in Py2 requirements but need specific Py3-compatible versions
- Warns about transitive dependency conflicts

## Workflow

### Baseline Scan (Phase 0)

```bash
python3 scripts/security_scan.py /path/to/project-py3 \
    --mode baseline \
    --output migration-analysis/phase-0-discovery/security/
```

After the scan, review `security-report.md` for any critical findings. Pre-existing vulnerabilities are noted but don't block migration — they go into the baseline for delta comparison later.

### Regression Scan (After Phase 2)

```bash
python3 scripts/security_scan.py /path/to/project-py3 \
    --mode regression \
    --baseline-report migration-analysis/phase-0-discovery/security/security-report.json \
    --output migration-analysis/phase-2-mechanical/security/
```

The regression scan focuses on what changed. It produces a `security-delta.json` showing new findings introduced by the migration, findings that were resolved (e.g., upgrading away from a vulnerable library), and dependency changes.

**Gate criterion**: No new `critical` or `high` severity findings introduced by migration. Pre-existing findings are acceptable (they were there before).

### Final Audit (Phase 5)

```bash
python3 scripts/security_scan.py /path/to/project-py3 \
    --mode final \
    --baseline-report migration-analysis/phase-0-discovery/security/security-report.json \
    --output migration-analysis/phase-5-cutover/security/
```

The final audit produces the deliverable SBOM and security report. This is what goes to the security team for review. It includes the full delta from baseline showing everything that changed during migration.

**Gate criterion**: No unacknowledged `critical` findings. All `high` findings either resolved or explicitly waived with rationale.

## Model Tier

**Haiku** for the script execution (it's all deterministic tool invocation).

**Sonnet** for reviewing `flagged-for-review.json` — ambiguous findings where the scanner couldn't determine if the pattern is a real vulnerability or a false positive given the codebase context. Typical items: Bandit findings in test code, pickle usage that's internal-only, hardcoded strings that look like keys but aren't.

## Scripts Reference

### `scripts/security_scan.py`

Main scanning script. Orchestrates SBOM generation, vulnerability scanning, static analysis, and secret detection. Zero LLM involvement.

```bash
# Baseline scan
python3 scripts/security_scan.py /path/to/workspace --mode baseline

# Regression scan with delta
python3 scripts/security_scan.py /path/to/workspace \
    --mode regression \
    --baseline-report path/to/baseline/security-report.json

# Final audit
python3 scripts/security_scan.py /path/to/workspace \
    --mode final \
    --baseline-report path/to/baseline/security-report.json
```

Exit codes: 0 = no critical findings, 1 = findings present (check report), 2 = scan error.

## Integration with Other Skills

| Skill | Relationship |
|-------|-------------|
| **py2to3-codebase-analyzer** | Baseline scan runs alongside or after initial analysis |
| **py2to3-serialization-detector** | Feeds pickle/marshal findings into migration-specific security checks |
| **py2to3-completeness-checker** | Security scan complements completeness check — different dimensions of "done" |
| **py2to3-gate-checker** | Security gate criteria added: no new critical/high findings post-migration |
| **py2to3-compatibility-shim-remover** | Removing shims may resolve some security findings (outdated compat libraries) |
| **py2to3-rollback-plan-generator** | If security findings are severe, rollback plan should account for reverting dependency changes |

## References

- `references/INDEX.md` — Pointers to shared reference documents
- [CycloneDX specification](https://cyclonedx.org/specification/overview/)
- [OSV vulnerability database](https://osv.dev/)
- [Bandit documentation](https://bandit.readthedocs.io/)
