# Phase Runners - Quick Start Guide

## TL;DR

Run the Express workflow for instant Python 2→3 migration (4 phases, zero LLM cost):

```bash
python3 run_express.py /path/to/project -o ./migration_output
```

Done! Check `migration_output/migration-summary.md` and `remaining-issues.md`.

---

## Choose Your Workflow

### Express (🚀 Fastest - Small/Medium Projects)
Perfect for projects < 10K LOC with simple Python 2 patterns.

```bash
python3 run_express.py ~/my-project -o ./output
```

**Phases:** 0 → 1 → 2 → 4 (skips semantic review)
**LLM Cost:** 0 tokens
**Time:** ~2-5 minutes

---

### Full (🏢 Complete - Large/Complex Projects)
For enterprise projects requiring expert semantic review.

```bash
# Run phases in sequence
python3 phase0_discovery.py ~/big-project -o ./output
python3 phase1_foundation.py ~/big-project -o ./output
python3 phase2_mechanical.py ~/big-project -s ./output/raw-scan.json -o ./output
python3 phase3_semantic.py -w ./output/work-items.json -s ./output/raw-scan.json -o ./output

# Now use Claude Sonnet/Opus to review ./output/semantic-review-brief.json
# [LLM applies semantic fixes]

python3 phase4_verification.py ~/big-project -o ./output
python3 phase5_cutover.py ~/big-project -o ./output
```

**Phases:** 0 → 1 → 2 → 3 → 4 → 5 (all phases)
**LLM Cost:** ~1000-5000 tokens (Sonnet/Opus review of semantic-review-brief.json)
**Time:** ~30-60 minutes

---

### Standard (⚡ Lean - Minimal Projects)
Skip foundation phase for tiny projects.

```bash
python3 phase0_discovery.py ~/tiny-project -o ./output
python3 phase2_mechanical.py ~/tiny-project -s ./output/raw-scan.json -o ./output
python3 phase4_verification.py ~/tiny-project -o ./output
```

**Phases:** 0 → 2 → 4 (skips foundation, semantic, cutover)
**LLM Cost:** 0 tokens
**Time:** ~5-10 minutes

---

## What Each Phase Does

| Phase | Name | What It Does | LLM? |
|-------|------|-------------|------|
| **0** | Discovery | Scans project, identifies Python 2 patterns | No |
| **1** | Foundation | Adds __future__ imports, baselines lint, creates tests | No |
| **2** | Mechanical | Applies automated Haiku-tier fixes | No |
| **3** | Semantic | Prepares brief for LLM review (doesn't execute) | Brief only |
| **4** | Verification | Tests, checks completeness, verifies gates | No |
| **5** | Cutover | Removes shims, updates build, generates CI | No |

---

## Typical Workflow

### Step 1: Run Express
```bash
python3 run_express.py /path/to/project -o ./output
```

### Step 2: Review Results
```bash
cat output/migration-summary.md
cat output/remaining-issues.md
```

### Step 3: Fix Remaining Issues (if any)
```bash
# Issues typically include:
# - Bytes/string handling
# - Dynamic type patterns
# - Protocol definitions
# - Metaclass usage

# Use these to decide: Manual fixes or LLM review?
```

### Step 4 (Optional): Get LLM Review
If Express showed semantic issues:

```bash
python3 phase3_semantic.py \
  -w ./output/work-items.json \
  -s ./output/raw-scan.json \
  -o ./output

# Review output/semantic-review-brief.json in Claude Sonnet/Opus
# Get recommendations for complex patterns
```

### Step 5: Finalize (Optional)
```bash
python3 phase5_cutover.py /path/to/project -o ./output
# Now ready for Python 3-only deployment!
```

---

## Output Files Guide

| File | Purpose | Read When |
|------|---------|-----------|
| `migration-summary.md` | Overview of changes | After any phase |
| `remaining-issues.md` | Action items | Planning next steps |
| `raw-scan.json` | Detected patterns | Debugging issues |
| `work-items.json` | Items to fix (tiered) | Prioritizing work |
| `semantic-review-brief.json` | Items for LLM review | Before manual review |
| `verification-report.json` | Test results | Validating fixes |

---

## Common Commands

```bash
# Quick scan only
python3 phase0_discovery.py /project -o ./out

# Full analysis without LLM
python3 run_express.py /project -o ./out

# Just verify (assumes phases 0-2 already run)
python3 phase4_verification.py /project -o ./out

# See how many items need each tier of review
jq '.summary | {sonnet: .sonnet_tier.count, opus: .opus_tier.count}' \
  out/semantic-review-brief.json

# Check tests passed
jq '.tests_passed, .tests_run' out/verification-report.json
```

---

## Troubleshooting

### Runner fails with "Script not found"
**Normal!** Some optional skills may not be installed.
- Runner skips missing scripts gracefully
- Check stderr for which skills were skipped
- Everything else continues running

### Phase takes too long
- Large projects (>100K LOC) may take 10+ minutes per phase
- Check CPU/disk usage - might be I/O bound
- Consider splitting project into modules

### Want to see detailed logs?
```bash
# Capture both stdout (JSON) and stderr (human-readable)
python3 phase0_discovery.py /project -o ./out 2>&1 | tee phase0.log
jq '.' phase0.log  # Parse JSON results
```

### Need to re-run a phase?
Just run it again - it overwrites output files:
```bash
python3 phase2_mechanical.py /project -s ./out/raw-scan.json -o ./out
```

---

## When to Use Each Workflow

### Use **Express** if:
- Project < 10K lines
- Simple Python 2 code (no bytes/strings issues)
- Want results fast
- Don't need LLM involvement

### Use **Full** if:
- Project > 100K lines
- Complex patterns (bytes, strings, serialization)
- C extension wrapping needed
- Can afford LLM tokens for semantic review
- Need cutover planning

### Use **Standard** if:
- Project 10-50K lines
- Skip foundation phase to save time
- No build system updates needed

---

## Example: Express Workflow in Action

```bash
$ python3 run_express.py ~/myapp -o ./migration
╔═══════════════════════════════════════════════════════╗
║  PYTHON 2→3 MIGRATION - EXPRESS WORKFLOW             ║
║  Fast-track for small/medium projects                ║
╚═══════════════════════════════════════════════════════╝

Project: /home/user/myapp
Output:  /home/user/migration

[1/4] PHASE 0: Project Discovery...
  ✓ Phase 0 complete

[2/4] PHASE 1: Foundation Setup...
  ✓ Phase 1 complete

[3/4] PHASE 2: Mechanical Fixes...
  ✓ Phase 2 complete

[!] PHASE 3: Semantic Review - SKIPPED

[4/4] PHASE 4: Verification...
  ✓ Phase 4 complete

╔═══════════════════════════════════════════════════════╗
║  EXPRESS WORKFLOW COMPLETE                           ║
╚═══════════════════════════════════════════════════════╝

Duration: 247.3s
Generated files:
  • migration-summary.md
  • remaining-issues.md
  • express-workflow-results.json
  + all phase-specific reports

$ cat migration/remaining-issues.md
# Remaining Issues

1. **Python 2 Artifacts:** 3 remaining patterns
2. **Dead Code:** 2 unused code blocks detected

## Recommended Actions

1. Address high-priority issues first
2. For semantic issues (bytes/strings, protocols):
   - Run Phase 3 with Claude Sonnet/Opus
3. Re-run Phase 4 verification after fixes
4. Proceed to Phase 5 (Cutover) when ready
```

---

## File Locations

All scripts are located at:
```
/sessions/stoic-practical-faraday/mnt/code-translation-skills/scripts/runners/

phase0_discovery.py      - Project analysis
phase1_foundation.py      - Setup phase
phase2_mechanical.py      - Automated fixes
phase3_semantic.py        - LLM prep (no execution)
phase4_verification.py    - Testing & validation
phase5_cutover.py         - Finalization
run_express.py            - All-in-one for small projects
```

Skills are at:
```
/sessions/stoic-practical-faraday/mnt/code-translation-skills/skills/
```

---

## Next Steps

1. **Choose workflow** based on project size
2. **Run first phase** (discovery)
3. **Review output** files
4. **Run next phases** in sequence
5. **Apply manual fixes** for items needing LLM review
6. **Verify** with phase 4
7. **Deploy** using phase 5

Happy migrating! 🎉
