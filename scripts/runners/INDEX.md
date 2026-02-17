# Phase Runners Index

## Overview

Phase runners are zero-token orchestration scripts that automate Python 2→3 migration by chaining skill scripts. Each runner executes a sequence of skills, passing outputs between them, and produces comprehensive JSON reports and markdown summaries.

**Location:** `/sessions/stoic-practical-faraday/mnt/code-translation-skills/scripts/runners/`

**Total:** 7 executable runners + 3 documentation files

---

## Executable Runners

### 1. run_express.py (Main Entry Point)
**Lines:** 303 | **Size:** 12K | **Mode:** -rwx

Fast-track migration for small/medium projects. Chains 4 phases (0→1→2→4) in a single command.

**Usage:**
```bash
python3 run_express.py /path/to/project -o ./output
python3 run_express.py /path/to/project -o ./output --with-cutover
```

**Outputs:**
- `migration-summary.md` - Executive summary with phase results
- `remaining-issues.md` - Action items requiring attention
- `express-workflow-results.json` - Consolidated JSON from all phases
- Phase-specific reports (sizing, work items, verification, etc.)

**Time:** 2-5 minutes | **LLM Cost:** 0 tokens

---

### 2. phase0_discovery.py
**Lines:** 159 | **Size:** 6.1K | **Mode:** -rwx

Project analysis phase. Scans codebase for size, dependencies, and Python 2 patterns.

**Chains:**
1. `py2to3-project-initializer/scripts/quick_size_scan.py`
2. `universal-code-graph/scripts/analyze_universal.py` (optional)
3. `py2to3-codebase-analyzer/scripts/analyze.py` (optional)

**Usage:**
```bash
python3 phase0_discovery.py /path/to/project -o ./output
```

**Inputs:**
- `project_root` - Path to analyze

**Outputs:**
- `sizing-report.json` - File counts, LOC, complexity metrics
- `dependency-graph.json` - Module dependencies
- `raw-scan.json` - Detected Python 2 patterns
- `discovery-summary.json` - Phase summary

**Exit Codes:** 0 (success) | 1 (partial) | 2 (failure)

---

### 3. phase1_foundation.py
**Lines:** 169 | **Size:** 6.4K | **Mode:** -rwx

Foundation setup phase. Prepares codebase with compatibility shims and baselines.

**Chains:**
1. `py2to3-future-imports-injector/scripts/inject_futures.py`
2. `py2to3-lint-baseline-generator/scripts/run_lint.py` (optional)
3. `py2to3-test-scaffold-generator/scripts/generate_tests.py` (optional)

**Usage:**
```bash
python3 phase1_foundation.py /path/to/project -o ./output
python3 phase1_foundation.py /path/to/project -s ./output/raw-scan.json -o ./output
```

**Inputs:**
- `project_root` - Project directory
- `-s` / `--raw-scan` - raw-scan.json from Phase 0 (optional)

**Outputs:**
- `injection-report.json` - __future__ imports applied
- `lint-baseline.json` - Baseline lint report
- `test-scaffolds.json` - Generated test structure
- `foundation-summary.json` - Phase summary

**Metrics Captured:**
- Files modified with __future__ imports
- Test files generated
- Baseline lint issues

---

### 4. phase2_mechanical.py
**Lines:** 193 | **Size:** 7.2K | **Mode:** -rwx

Mechanical fixes phase. Applies automated transformations to simple patterns.

**Chains:**
1. `work-item-generator/scripts/generate_work_items.py` → work-items.json
2. `haiku-pattern-fixer/scripts/apply_fix.py` (loop over HAIKU tier items)
3. `py2to3-library-replacement/scripts/replace_libs.py` (optional)

**Usage:**
```bash
python3 phase2_mechanical.py /path/to/project -o ./output
python3 phase2_mechanical.py /path/to/project -s ./output/raw-scan.json -o ./output
```

**Inputs:**
- `project_root` - Project directory
- `-s` / `--raw-scan` - raw-scan.json from Phase 0 (default: raw-scan.json)

**Outputs:**
- `work-items.json` - Generated work items (HAIKU/SONNET/OPUS tiers)
- `library-replacement-report.json` - Stdlib import replacements
- `mechanical-summary.json` - Phase summary

**Key Metrics:**
- Total work items generated
- HAIKU-tier items fixed
- Library imports replaced

**Note:** Loops over all HAIKU-tier items and applies fixes individually.

---

### 5. phase3_semantic.py
**Lines:** 162 | **Size:** 5.9K | **Mode:** -rwx

Semantic brief preparation. Curates work items for LLM review without execution.

**Does NOT execute skills.** Filters work items by tier and generates a focused brief.

**Usage:**
```bash
python3 phase3_semantic.py -w ./output/work-items.json -s ./output/raw-scan.json -o ./output
```

**Inputs:**
- `-w` / `--work-items` - work-items.json from Phase 2 (default: work-items.json)
- `-s` / `--raw-scan` - raw-scan.json from Phase 0 (default: raw-scan.json)

**Outputs:**
- `semantic-review-brief.json` - Curated work items for LLM review
  - SONNET_PATTERNS - Items for Claude Sonnet
  - OPUS_PATTERNS - Items for Claude Opus

**Key Features:**
- Estimates LLM tokens needed (~300 per Sonnet item, ~500 per Opus item)
- Recommends tier (Sonnet first, escalate Opus if needed)
- Limits output to 20 items per tier for brevity

**Note:** Zero execution cost - just curation. Pass brief to Claude for manual review.

---

### 6. phase4_verification.py
**Lines:** 208 | **Size:** 8.7K | **Mode:** -rwx

Verification phase. Tests migration and validates completeness.

**Chains:**
1. `translation-verifier/scripts/verify_translation.py`
2. `py2to3-completeness-checker/scripts/check_completeness.py` (optional)
3. `py2to3-dead-code-detector/scripts/detect_dead_code.py` (optional)
4. `py2to3-gate-checker/scripts/check_gate.py` (optional)

**Usage:**
```bash
python3 phase4_verification.py /path/to/project -o ./output
```

**Inputs:**
- `project_root` - Project directory

**Outputs:**
- `verification-report.json` - Test results and confidence scores
- `completeness-report.json` - Remaining Python 2 artifacts
- `dead-code-report.json` - Unused code analysis
- `gate-check-report.json` - Migration gate validation
- `verification-summary.json` - Phase summary

**Key Metrics:**
- Tests run / passed ratio
- Confidence score (0-100)
- Remaining Python 2 artifacts
- Dead code blocks found
- Gates passed/failed status

---

### 7. phase5_cutover.py
**Lines:** 207 | **Size:** 8.2K | **Mode:** -rwx

Cutover phase. Finalizes migration and prepares for deployment.

**Chains:**
1. `py2to3-compatibility-shim-remover/scripts/remove_shims.py`
2. `py2to3-build-system-updater/scripts/update_build.py`
3. `py2to3-ci-dual-interpreter/scripts/generate_ci.py` (optional)
4. `migration-dashboard/scripts/generate_dashboard.py` (optional)

**Usage:**
```bash
python3 phase5_cutover.py /path/to/project -o ./output
```

**Inputs:**
- `project_root` - Project directory

**Outputs:**
- `shim-removal-report.json` - Compatibility shims removed
- `build-update-report.json` - Build system changes (setup.py, pyproject.toml)
- `ci-config-report.json` - Generated CI/CD configuration
- `dashboard-report.json` - Final migration dashboard
- `cutover-summary.json` - Phase summary

**Key Metrics:**
- Shims removed
- Build configs updated
- CI files generated
- Dashboard HTML file location

---

## Documentation Files

### README.md
**Size:** 14K

Comprehensive documentation covering:
- Phase details and dependencies
- Workflow types (Full, Express, Standard)
- Error handling and exit codes
- JSON output format reference
- Integration with skills
- Troubleshooting guide
- Customization options

**Read:** For complete phase reference and advanced usage.

---

### QUICKSTART.md
**Size:** 8.1K

Quick reference guide covering:
- TL;DR (one-liner for Express)
- Workflow comparison matrix
- What each phase does
- Typical workflow steps
- Output files guide
- Common commands
- When to use each workflow
- Example outputs
- Troubleshooting quick answers

**Read:** For getting started quickly or choosing a workflow.

---

### INDEX.md (This File)
**Size:** ~12K

Index of all files with:
- Quick reference for each script
- Usage examples
- Input/output specifications
- Key metrics captured
- Exit codes and behaviors

**Read:** For quickly finding what you need or understanding file purposes.

---

## Workflow Comparison

| Workflow | Phases | LLM Cost | Time | Use Case |
|----------|--------|----------|------|----------|
| **Express** | 0→1→2→4 | 0 tokens | 2-5 min | Small/medium projects |
| **Full** | 0→1→2→3→4→5 | 1K-5K tokens | 30-60 min | Large/complex projects |
| **Standard** | 0→2→4 | 0 tokens | 5-10 min | Minimal projects |

---

## File Statistics

```
phase0_discovery.py      159 lines   6.1K
phase1_foundation.py     169 lines   6.4K
phase2_mechanical.py     193 lines   7.2K
phase3_semantic.py       162 lines   5.9K
phase4_verification.py   208 lines   8.7K
phase5_cutover.py        207 lines   8.2K
run_express.py           303 lines  12.0K
─────────────────────────────────────────
Total:                 1,401 lines  54.5K

Documentation:
README.md                          14K
QUICKSTART.md                       8K
INDEX.md                           12K
─────────────────────────────────────────
Total docs:                        34K

GRAND TOTAL:                        9 files, 88.5K
```

---

## Quick Navigation

### I want to...

**Run a quick migration**
→ See `QUICKSTART.md`, run `run_express.py`

**Understand all phases**
→ See `README.md` for comprehensive reference

**Find a specific script**
→ See this INDEX.md file

**Debug a phase**
→ Check stderr output, review JSON files, see README.md troubleshooting

**Customize a runner**
→ See "Customization" in README.md

**Check a specific phase**
→ Run individual phase0_discovery.py through phase5_cutover.py

**Prepare for LLM review**
→ Run phase3_semantic.py, review semantic-review-brief.json

**Validate migration**
→ Run phase4_verification.py, check verification-report.json

**Finalize deployment**
→ Run phase5_cutover.py, review migration-dashboard

---

## Script Relationships

```
run_express.py (orchestrator)
├── phase0_discovery.py     → sizes project, finds patterns
├── phase1_foundation.py    → adds shims
├── phase2_mechanical.py    → applies Haiku fixes
└── phase4_verification.py  → validates

phase3_semantic.py (standalone)
└── Filters work items for LLM (no execution)

phase5_cutover.py (standalone)
└── Finalizes after phase 4

Full workflow:
phase0 → phase1 → phase2 → phase3 → [LLM] → phase4 → phase5
```

---

## Error Recovery

If a phase fails:

1. **Check stderr** - See which skill failed
2. **Review JSON output** - Error details in phase report
3. **Re-run phase** - Fix causes and retry
4. **Continue** - Most phases can run independently
5. **Skip** - Missing skills are gracefully skipped

Example:
```bash
python3 phase2_mechanical.py /project -s ./output/raw-scan.json -o ./output 2>&1 | tee phase2.log
# Review phase2.log for errors
# Fix issues in project
python3 phase2_mechanical.py /project -s ./output/raw-scan.json -o ./output  # Retry
```

---

## Integration Points

### Input from Skills
```
Skills directory:
/sessions/stoic-practical-faraday/mnt/code-translation-skills/skills/
├── py2to3-project-initializer/scripts/
├── universal-code-graph/scripts/
├── py2to3-codebase-analyzer/scripts/
├── py2to3-future-imports-injector/scripts/
├── ... (15+ more skills)
└── migration-dashboard/scripts/
```

### Output to Users
```
Output directory (specified with -o flag):
├── sizing-report.json
├── raw-scan.json
├── work-items.json
├── semantic-review-brief.json  (for LLM)
├── verification-report.json
├── migration-summary.md
├── remaining-issues.md
└── ... (per-phase reports)
```

---

## Performance Characteristics

| Phase | Size Impact | Time |
|-------|-------------|------|
| Phase 0 | None (read-only) | 5-30s |
| Phase 1 | Adds imports to files | 10-60s |
| Phase 2 | Modifies files | 30-300s |
| Phase 3 | None (read-only) | <1s |
| Phase 4 | None (read-only) | 20-120s |
| Phase 5 | Modifies config files | 10-30s |

**Express Total:** 100-500s depending on project size

---

## Version Info

- **Created:** 2026-02-17
- **Python:** 3.6+
- **Dependencies:** json, subprocess, pathlib, argparse (all stdlib)
- **Status:** Production-ready

---

## Support

For issues or questions:
1. Check QUICKSTART.md for common answers
2. Review README.md troubleshooting section
3. Examine JSON output files in output directory
4. Check phase stderr logs for detailed errors

---

## Files at a Glance

```
runners/
├── phase0_discovery.py           ✓ Ready
├── phase1_foundation.py          ✓ Ready
├── phase2_mechanical.py          ✓ Ready
├── phase3_semantic.py            ✓ Ready
├── phase4_verification.py        ✓ Ready
├── phase5_cutover.py             ✓ Ready
├── run_express.py                ✓ Ready
├── README.md                     ✓ Ready
├── QUICKSTART.md                 ✓ Ready
└── INDEX.md                      ✓ Ready (you are here)
```

All files syntax-checked and ready for use.

---

**Last Updated:** 2026-02-17 21:28 UTC
