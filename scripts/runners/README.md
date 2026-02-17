# Phase Runner Scripts - Python 2→3 Migration Automation

## Overview

Phase runners automate the orchestration of skill scripts across migration phases, eliminating LLM orchestration overhead. Instead of requiring an LLM to coordinate multiple skills, these runners chain skill scripts sequentially, passing outputs from one skill as inputs to the next.

**Token Cost:** 0 tokens (fully automated execution)
**Architecture:** Each runner chains skills from `/sessions/stoic-practical-faraday/mnt/code-translation-skills/skills/*/scripts/`

## Directory Structure

```
/scripts/runners/
├── phase0_discovery.py       # Project sizing & codebase analysis
├── phase1_foundation.py       # Foundation setup (__future__, lint, tests)
├── phase2_mechanical.py       # Mechanical fixes & library replacement
├── phase3_semantic.py         # Prepare brief for LLM semantic review
├── phase4_verification.py     # Testing & validation
├── phase5_cutover.py          # Finalization & deployment prep
├── run_express.py             # Express workflow (0→1→2→4)
└── README.md                  # This file
```

## Workflow Types

### Full Workflow (6 phases)
Use for complex, large projects requiring semantic LLM review:

```bash
python3 phase0_discovery.py /path/to/project -o ./output
python3 phase1_foundation.py /path/to/project -o ./output
python3 phase2_mechanical.py /path/to/project -s ./output/raw-scan.json -o ./output
python3 phase3_semantic.py -w ./output/work-items.json -s ./output/raw-scan.json -o ./output
# [LLM review using semantic-review-brief.json]
python3 phase4_verification.py /path/to/project -o ./output
python3 phase5_cutover.py /path/to/project -o ./output
```

### Express Workflow (4 phases)
Use for small/medium projects where LLM semantic review isn't needed:

```bash
python3 run_express.py /path/to/project -o ./output
# Or with cutover included:
python3 run_express.py /path/to/project -o ./output --with-cutover
```

### Standard Workflow (3 phases)
Use for minimal migration projects:

```bash
python3 phase0_discovery.py /path/to/project -o ./output
python3 phase2_mechanical.py /path/to/project -s ./output/raw-scan.json -o ./output
python3 phase4_verification.py /path/to/project -o ./output
```

## Phase Details

### Phase 0: Discovery
**Purpose:** Analyze project structure and identify Python 2 patterns

**Chains:**
- `py2to3-project-initializer/scripts/quick_size_scan.py` → sizing-report.json
- `universal-code-graph/scripts/analyze_universal.py` → dependency-graph.json
- `py2to3-codebase-analyzer/scripts/analyze.py` → raw-scan.json

**Outputs:**
- `sizing-report.json` - Project statistics (files, LOC, complexity)
- `dependency-graph.json` - Module dependencies
- `raw-scan.json` - Detected Python 2 patterns
- `discovery-summary.json` - Phase summary

**Example:**
```bash
python3 phase0_discovery.py ~/my-project -o ./migration
```

---

### Phase 1: Foundation
**Purpose:** Prepare codebase for migration with compatibility shims

**Chains:**
- `py2to3-future-imports-injector/scripts/inject_futures.py` → injection-report.json
- `py2to3-lint-baseline-generator/scripts/run_lint.py` → lint-baseline.json
- `py2to3-test-scaffold-generator/scripts/generate_tests.py` → test-scaffolds.json

**Inputs:**
- `project_root` - Path to project
- `raw-scan.json` (optional) - From Phase 0

**Outputs:**
- `injection-report.json` - Files modified with __future__ imports
- `lint-baseline.json` - Baseline lint report
- `test-scaffolds.json` - Generated test structure
- `foundation-summary.json` - Phase summary

**Example:**
```bash
python3 phase1_foundation.py ~/my-project -s ./migration/raw-scan.json -o ./migration
```

---

### Phase 2: Mechanical
**Purpose:** Apply automated fixes to resolve simple patterns

**Chains:**
- `work-item-generator/scripts/generate_work_items.py` → work-items.json
- `haiku-pattern-fixer/scripts/apply_fix.py` (loop over HAIKU tier items)
- `py2to3-library-replacement/scripts/replace_libs.py` → library-replacement-report.json

**Inputs:**
- `project_root` - Path to project
- `raw-scan.json` - From Phase 0

**Outputs:**
- `work-items.json` - Generated work items (HAIKU, SONNET, OPUS tiers)
- `library-replacement-report.json` - Import replacements performed
- `mechanical-summary.json` - Phase summary

**Example:**
```bash
python3 phase2_mechanical.py ~/my-project -s ./migration/raw-scan.json -o ./migration
```

---

### Phase 3: Semantic
**Purpose:** Prepare brief for LLM semantic analysis (zero execution cost)

**Does NOT execute skills.** Instead, curates work items requiring LLM reasoning.

**Inputs:**
- `work-items.json` - From Phase 2
- `raw-scan.json` - From Phase 0

**Outputs:**
- `semantic-review-brief.json` - Curated list of items needing LLM review
  - SONNET_PATTERNS (bytes/strings, protocols, metaclasses)
  - OPUS_PATTERNS (complex serialization, C extensions, reflection)

**Example:**
```bash
python3 phase3_semantic.py -w ./migration/work-items.json -s ./migration/raw-scan.json -o ./migration
```

**Next:** Pass `semantic-review-brief.json` to Claude Sonnet or Opus for review.

---

### Phase 4: Verification
**Purpose:** Test and validate migration completeness

**Chains:**
- `translation-verifier/scripts/verify_translation.py` → verification-report.json
- `py2to3-completeness-checker/scripts/check_completeness.py` → completeness-report.json
- `py2to3-dead-code-detector/scripts/detect_dead_code.py` → dead-code-report.json
- `py2to3-gate-checker/scripts/check_gate.py` → gate-check-report.json

**Outputs:**
- `verification-report.json` - Test results and confidence scores
- `completeness-report.json` - Remaining Python 2 artifacts
- `dead-code-report.json` - Unused code detected
- `gate-check-report.json` - Migration gate validation
- `verification-summary.json` - Phase summary

**Example:**
```bash
python3 phase4_verification.py ~/my-project -o ./migration
```

---

### Phase 5: Cutover
**Purpose:** Finalize migration and prepare for deployment

**Chains:**
- `py2to3-compatibility-shim-remover/scripts/remove_shims.py` → shim-removal-report.json
- `py2to3-build-system-updater/scripts/update_build.py` → build-update-report.json
- `py2to3-ci-dual-interpreter/scripts/generate_ci.py` → ci-config-report.json
- `migration-dashboard/scripts/generate_dashboard.py` → dashboard-report.json

**Outputs:**
- `shim-removal-report.json` - Removed compatibility shims
- `build-update-report.json` - Updated build configs (setup.py, pyproject.toml)
- `ci-config-report.json` - Generated CI configuration
- `dashboard-report.json` - Final migration dashboard
- `cutover-summary.json` - Phase summary

**Example:**
```bash
python3 phase5_cutover.py ~/my-project -o ./migration
```

---

### Express Workflow
**Purpose:** Complete migration in 4 phases (0→1→2→4) for small/medium projects

**Skips:** Phase 3 (semantic review) and Phase 5 (cutover)

**Example:**
```bash
python3 run_express.py ~/my-project -o ./migration
# Or with cutover:
python3 run_express.py ~/my-project -o ./migration --with-cutover
```

**Outputs:**
- All phase-specific reports
- `migration-summary.md` - Executive summary
- `remaining-issues.md` - Issues requiring attention
- `express-workflow-results.json` - Consolidated results

---

## Error Handling

All runners use consistent exit codes:

| Code | Status | Meaning |
|------|--------|---------|
| 0 | SUCCESS | All steps completed successfully |
| 1 | PARTIAL | Some steps completed, others skipped or had non-fatal issues |
| 2 | FAILURE | Critical errors encountered |

### Graceful Degradation

If a skill script doesn't exist, the runner:
1. Skips that step (doesn't fail)
2. Logs a warning to stderr
3. Continues with remaining steps
4. Returns appropriate exit code

Example output:
```
  → Analyzing codebase graph analysis...
  {status: "skipped", reason: "Script not found: .../universal-code-graph/scripts/analyze_universal.py"}
```

---

## Output JSON Format

Each phase produces a JSON summary with:

```json
{
  "phase": "phase_number",
  "project_root": "/path/to/project",
  "output_dir": "/path/to/output",
  "steps": {
    "step_name": "complete|partial|skipped|error"
  },
  "metric_1": value,
  "metric_2": value
}
```

All phase outputs use consistent naming:
- Stdout: JSON summary (for scripting/parsing)
- Stderr: Human-readable progress (for CLI usage)
- Files: Detailed reports in output directory

---

## Integration with Skills

Each phase runner references skills from:
```
/sessions/stoic-practical-faraday/mnt/code-translation-skills/skills/
├── py2to3-project-initializer/scripts/
├── universal-code-graph/scripts/
├── py2to3-codebase-analyzer/scripts/
├── py2to3-future-imports-injector/scripts/
├── py2to3-lint-baseline-generator/scripts/
├── py2to3-test-scaffold-generator/scripts/
├── work-item-generator/scripts/
├── haiku-pattern-fixer/scripts/
├── py2to3-library-replacement/scripts/
├── translation-verifier/scripts/
├── py2to3-completeness-checker/scripts/
├── py2to3-dead-code-detector/scripts/
├── py2to3-gate-checker/scripts/
├── py2to3-compatibility-shim-remover/scripts/
├── py2to3-build-system-updater/scripts/
├── py2to3-ci-dual-interpreter/scripts/
└── migration-dashboard/scripts/
```

If a skill is not installed, the runner skips it gracefully.

---

## Usage Examples

### Analyze Large Enterprise Project
```bash
python3 phase0_discovery.py /enterprise/project -o ./migration
python3 phase1_foundation.py /enterprise/project -o ./migration
python3 phase2_mechanical.py /enterprise/project -s ./migration/raw-scan.json -o ./migration
python3 phase3_semantic.py -w ./migration/work-items.json -s ./migration/raw-scan.json -o ./migration
# [Manual LLM review of semantic-review-brief.json with Sonnet/Opus]
python3 phase4_verification.py /enterprise/project -o ./migration
python3 phase5_cutover.py /enterprise/project -o ./migration
```

### Quick Migration for Small Project
```bash
python3 run_express.py ~/small-project -o ./output
# Done! Review migration-summary.md and remaining-issues.md
```

### Skip Semantic Review for Medium Project
```bash
python3 phase0_discovery.py ~/medium-project -o ./output
python3 phase1_foundation.py ~/medium-project -o ./output
python3 phase2_mechanical.py ~/medium-project -s ./output/raw-scan.json -o ./output
python3 phase4_verification.py ~/medium-project -o ./output
python3 phase5_cutover.py ~/medium-project -o ./output
```

### Inspect Work Items Before LLM Review
```bash
python3 phase0_discovery.py /project -o ./output
python3 phase1_foundation.py /project -o ./output
python3 phase2_mechanical.py /project -s ./output/raw-scan.json -o ./output
python3 phase3_semantic.py -w ./output/work-items.json -s ./output/raw-scan.json -o ./output
# Review output/semantic-review-brief.json
jq '.sonnet_tier.items | length' output/semantic-review-brief.json  # Count Sonnet items
jq '.opus_tier.items | length' output/semantic-review-brief.json    # Count Opus items
```

---

## Customization

### Modify Phase Chain
To add or remove a skill from a phase, edit the phase runner:

```python
# Add a new script to the chain
script_path = SKILLS_DIR / "new-skill" / "scripts" / "new_script.py"
new_output = run_script(script_path, [args], "Description")
results["new_step"] = new_output
```

### Custom Filtering in Phase 3
Modify `phase3_semantic.py` to customize tier classification:

```python
sonnet_pattern_types = [
    "bytes_string_handling",
    "dynamic_type_checking",
    # Add custom patterns
]
```

### Skip Specific Phases in Express
Comment out unwanted phases in `run_express.py`.

---

## Troubleshooting

### Phase Fails: "Script not found"
- Verify skill is installed in `/sessions/stoic-practical-faraday/mnt/code-translation-skills/skills/`
- Check script path in runner matches actual script location
- Runner will skip missing scripts gracefully

### Phase Timeout
- Increase timeout in `run_script()` (default: 300s)
- Large projects may need more time for analysis

### Output Files Not Generated
- Check file write permissions in output directory
- Verify skill script produced valid JSON output
- Review stderr logs for errors

### Verify Migration State
```bash
# Check what phases have run
ls -la ./migration/*.json | grep summary

# Inspect phase outputs
jq '.phase' ./migration/*-summary.json
```

---

## Performance Notes

- **Phase 0 (Discovery):** ~5-30s (depends on project size)
- **Phase 1 (Foundation):** ~10-60s (file modifications)
- **Phase 2 (Mechanical):** ~30-300s (depends on work item count)
- **Phase 3 (Semantic):** <1s (just filtering, no execution)
- **Phase 4 (Verification):** ~20-120s (test execution)
- **Phase 5 (Cutover):** ~10-30s (configuration generation)

**Express Workflow:** ~100-500s total (zero LLM overhead)

---

## Exit Codes

```bash
#!/bin/bash
python3 run_express.py /project -o ./output
EXIT_CODE=$?

case $EXIT_CODE in
  0) echo "Success!" ;;
  1) echo "Partial success - review output" ;;
  2) echo "Failed - review errors" ;;
esac
```

---

## Design Pattern Reference

All runners follow this pattern:

1. **Parse arguments** - Project root, output directory
2. **Check script existence** - Gracefully skip missing scripts
3. **Run scripts in sequence** - Chain outputs as inputs
4. **Capture results** - JSON output and stderr messages
5. **Write summary files** - Per-phase and consolidated results
6. **Print progress** - Human-readable stderr output
7. **Return exit code** - 0=success, 1=partial, 2=failure

See `/scripts/runners/phase0_discovery.py` as reference implementation.

---

## License

Part of the Python 2→3 Migration Skill Suite.
