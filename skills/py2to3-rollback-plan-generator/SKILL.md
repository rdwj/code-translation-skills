---
name: py2to3-rollback-plan-generator
description: >
  Generates detailed rollback procedures per module per phase for a Python 2→3 migration.
  Maintains the ability to undo migration work at each phase. Analyzes git history, migration state,
  and module dependencies to create phase-specific rollback runbooks with exact commands, estimated
  time, dependency order, and risk assessment. Use this skill when you need to plan rollback procedures,
  assess rollback feasibility, understand migration state per module, or prepare emergency response
  to migration issues. Also trigger when someone says "create rollback plan," "prepare rollback,"
  "how do we undo the migration," "migration failed," or "rollback strategy."
---

# Skill X.2: Rollback Plan Generator

## Why Rollback Planning Matters for Py2→Py3 Migration

Rollback capability is critical because:

- **Migrations are complex multi-phase operations**: Each phase (Foundation, Conversion, Semantic Fixes,
  Verification, Cutover) has different rollback requirements. Not all work can be simply reverted.

- **Module-level rollback is essential**: Some modules migrate faster than others. You need to roll back
  individual modules to a safe state without affecting the entire codebase.

- **Git history is your lifeline**: Rollback relies on identifying exactly which commits belong to
  which migration phase and module. This requires careful analysis of migration-state.json and git history.

- **Dependencies create ordering constraints**: If Module B was fixed based on changes in Module A,
  rolling back A requires first rolling back B. Missing this breaks the codebase.

- **Feasibility matters**: Some rollbacks are impossible post-migration (e.g., if database schemas changed,
  or Py2-only dependencies were removed from PyPI). The skill assesses what's actually reversible.

- **Time estimates help prioritization**: Knowing rollback will take 2 hours vs. 10 minutes informs
  decision-making during an incident. Estimates help SLAs and incident response planning.

- **Risk identification prevents surprises**: Rollback runbooks should flag known risks (e.g.,
  "some files were manually edited post-conversion") so operators don't get blindsided.

This skill generates phase-aware, module-aware, dependency-aware rollback procedures with exact commands
and risk assessment.

---

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| **state_file** | User | migration-state.json (from Phase Planning skill) |
| **codebase_path** | User | Root directory of migrated codebase |
| **--output** | User | Output directory for rollback plan (default: current dir) |
| **--phase** | User | Specific phase to rollback (1-5, or all) |
| **--git-dir** | User | Git repository root (default: codebase_path) |
| **--test-rollback** | User | Simulate rollback without execution (dry-run) |

---

## Outputs

All outputs go into the `--output` directory:

| File | Format | Purpose |
|------|--------|---------|
| `rollback-plan.json` | JSON | Structured rollback procedures per phase and module |
| `rollback-runbook.md` | Markdown | Human-readable step-by-step rollback procedures |
| `rollback-test-results.json` | JSON | Results of `--test-rollback` simulation (if enabled) |

---

## Workflow

### Step 1: Load Migration State

Run the main rollback script:

```bash
python3 scripts/generate_rollback.py \
    --state-file migration-state.json \
    <codebase_path> \
    --output ./rollback-output/ \
    --phase 3
```

This reads:
- `migration-state.json`: Current phase and per-module progress
- Git history: Commits per module per phase (via `git log` filtering)
- Codebase structure: Module dependencies and file organization

### Step 2: Map Migration Commits

For each module and phase, identify commits:

**Phase 1 (Foundation)**:
- Commits adding `from __future__ import ...`
- Commits creating/modifying test scaffolding
- Commits updating CI configuration

**Phase 2 (Conversion)**:
- Commits from automated conversion tool (e.g., lib2to3, 2to3-ai)
- Commits per module (tracked by conversion unit)

**Phase 3 (Semantic Fixes)**:
- Commits with manual semantic fixes (tracked by git message patterns)
- Commits fixing issues surfaced by migration (e.g., unicode handling, exception syntax)

**Phase 4 (Verification)**:
- No code changes (read-only phase)
- Only configuration and documentation changes

**Phase 5 (Cutover)**:
- Commits switching traffic to Py3
- Commits disabling Py2 CI
- Commits updating deployment configs

### Step 3: Analyze Dependencies

Build a dependency graph:
- Which modules import from which?
- Which semantic fixes depend on other semantic fixes?
- Cross-module dependencies constrain rollback order

For Phase 3 semantic fixes, analyze:
- Fix A depends on Fix B (e.g., "fix exception syntax in module X" depends on "fix string handling")
- If reversing A, must first reverse B

### Step 4: Generate Phase-Specific Rollback Procedures

For each phase:

**Phase 1 Rollback** (Foundation):
- Delete generated test files
- Revert `from __future__ import ...` additions
- Restore original CI configuration
- Time: ~10-30 minutes
- Risk: Low (mostly deletions and simple reverts)

**Phase 2 Rollback** (Conversion):
- Revert conversion commits per module in reverse dependency order
- Commands: `git revert <commit_hash>` for each conversion commit
- Alternative: `git checkout HEAD~N -- <file>` to restore original files
- Time: Depends on number of modules (5-30 minutes per large module)
- Risk: Medium (some files may have been manually edited post-conversion)

**Phase 3 Rollback** (Semantic Fixes):
- Revert semantic fix commits in reverse dependency order
- Must handle fix dependencies: if Fix A depends on Fix B, revert A first
- Commands: `git revert <commit_hash>` with careful ordering
- Time: Depends on number of fixes (10-60 minutes)
- Risk: High (fixes are interdependent; reverting one may break another)

**Phase 4 Rollback** (Verification):
- Flag modules that need Phase 3 rollback (verification doesn't have code changes)
- No actual rollback code for this phase
- Time: ~5 minutes (config changes only)
- Risk: Low

**Phase 5 Rollback** (Cutover):
- Switch traffic back to Py2 deployment
- Re-enable Py2 CI
- Restore requirements files to include six, future, etc.
- Update deployment configuration
- Commands: Git reverts + deployment/config changes
- Time: 5-15 minutes (mostly deployment config)
- Risk: Medium (requires coordinating with deployment system)

### Step 5: Assess Feasibility

For each phase and module, determine if rollback is actually feasible:

**Feasibility Check**:
- Can we revert commits? (Check if commits exist in history)
- Do Py2-only dependencies still exist? (Check PyPI for six, future, etc.)
- Have database schemas changed? (If yes, some rollbacks are impossible)
- Were files manually edited? (If yes, simple revert may lose manual changes)
- Are there post-migration deployments that depend on Py3? (If yes, traffic switch is complex)

**Feasibility Levels**:
- **FULLY FEASIBLE**: All commits can be reverted, no external dependencies
- **PARTIALLY FEASIBLE**: Most work can be rolled back, some manual steps needed
- **DIFFICULT**: Several interdependencies and external factors
- **NOT FEASIBLE**: Some aspects can't be undone (flag clearly)

### Step 6: Generate Runbook

Create step-by-step rollback procedure with:
- Exact `git revert` commands
- Manual steps (config, deployment changes)
- Dependency order (which steps must complete before others)
- Estimated time per step
- Risk warnings for each step
- Verification commands to confirm rollback succeeded

### Step 7: Optional: Test Rollback (Dry-Run)

With `--test-rollback`:
- Simulate `git revert` commands without modifying working tree
- Check if all commits exist and can be reverted
- Identify any merge conflicts
- Estimate actual rollback time
- Output results to rollback-test-results.json

---

## JSON Structure

### rollback-plan.json

```json
{
  "generated": "2024-02-12T10:30:00Z",
  "codebase_path": "/path/to/codebase",
  "total_phases": 5,
  "phases": {
    "1": {
      "name": "Foundation",
      "description": "Rollback __future__ imports and test scaffolding",
      "modules_affected": 147,
      "estimated_time_minutes": 20,
      "feasibility": "FULLY_FEASIBLE",
      "steps": [
        {
          "order": 1,
          "action": "revert_commits",
          "commits": ["abc123", "def456"],
          "description": "Remove __future__ import additions",
          "time_estimate_minutes": 5,
          "risk_level": "LOW",
          "commands": ["git revert abc123", "git revert def456"]
        },
        {
          "order": 2,
          "action": "delete_files",
          "files": ["tests/generated/*.py"],
          "description": "Remove generated test scaffolding",
          "time_estimate_minutes": 3,
          "risk_level": "LOW",
          "commands": ["rm tests/generated/*.py"]
        }
      ],
      "verification": "python2 -m pytest tests/ --tb=short",
      "risks": [
        "Generated tests may have been manually edited — check git diff before deleting"
      ]
    },
    "2": {
      "name": "Conversion",
      "description": "Revert automated conversion changes per module",
      "modules_affected": 47,
      "estimated_time_minutes": 45,
      "feasibility": "PARTIALLY_FEASIBLE",
      "notes": "Some modules may have manual edits post-conversion; check carefully",
      "step_groups_by_module": {
        "src/core/parser.py": {
          "conversion_commits": ["conv001", "conv002"],
          "dependent_modules": ["src/core/rules.py", "src/api/parser_api.py"],
          "rollback_order": 5,
          "time_estimate_minutes": 8
        }
      }
    }
  },
  "module_rollbacks": {
    "src/scada/modbus.py": {
      "current_phase": 3,
      "rollback_to_phase": 2,
      "commits_to_revert": ["def456", "ghi789"],
      "dependencies": {
        "blocks_rollback_of": ["src/scada/utils.py"],
        "depends_on_rollback_of": []
      },
      "estimated_time_minutes": 5,
      "feasibility": "FULLY_FEASIBLE"
    }
  },
  "global_dependencies": [
    {
      "dependent": "src/api/parser_api.py",
      "dependency": "src/core/parser.py",
      "reason": "Direct import from parser module"
    }
  ]
}
```

---

## Rollback Procedures

### Phase 1: Foundation Rollback

**What was done**:
- Added `from __future__ import ...` to all files
- Created test scaffolding for migration
- Updated CI configuration

**How to rollback**:
1. Identify commits adding __future__ imports (git log with patterns)
2. Revert those commits in reverse order
3. Delete generated test files (match patterns: tests/generated/*, tests/test_py2_compat_*)
4. Restore original CI configuration from git history

**Commands**:
```bash
git revert <commit_for_future_imports>
rm -rf tests/generated/
git revert <commit_for_ci_changes>
```

**Time**: 15-30 minutes
**Risk**: LOW (reversions are straightforward)

### Phase 2: Conversion Rollback

**What was done**:
- Automated conversion tool (lib2to3) applied to each module
- Some manual fixes post-conversion

**How to rollback**:
1. Identify conversion commits per module (git log --grep patterns)
2. Revert in reverse dependency order (modules with no dependents first)
3. For modules with manual edits, use `git show <commit>` to inspect changes
4. Use `git revert` if confident, or manual restoration

**Commands**:
```bash
git revert <conversion_commit_module_a>  # No dependents, safe first
git revert <conversion_commit_module_b>  # Depends on A, do after
```

**Time**: 30-60 minutes (depends on number of modules)
**Risk**: MEDIUM (files may have manual edits; use `git diff HEAD <original_branch>` to verify)

### Phase 3: Semantic Fixes Rollback

**What was done**:
- Manual fixes for Py2/Py3 semantic differences (unicode, exceptions, etc.)
- Fixes often depend on other fixes

**How to rollback**:
1. Identify fix commits and their dependencies
2. Build reverse dependency order (fixes with no dependents first)
3. Revert fixes one by one in order
4. After each revert, verify no dependent fix breaks

**Commands**:
```bash
git revert <fix_commit_with_no_dependents>
python3 -m pytest <module_tests>  # Verify no breakage
git revert <fix_commit_dependent_on_above>
```

**Time**: 45-90 minutes (depends on number of interdependent fixes)
**Risk**: HIGH (must carefully manage fix dependencies)

### Phase 4: Verification Rollback

**What was done**:
- Read-only phase; mostly configuration and documentation

**How to rollback**:
1. No code rollback needed
2. Flag modules requiring Phase 3 rollback
3. Restore configuration if necessary

**Time**: 5 minutes
**Risk**: LOW

### Phase 5: Cutover Rollback

**What was done**:
- Traffic switched to Py3 deployment
- Py2 CI disabled
- Requirements.txt updated to remove six/future

**How to rollback**:
1. Switch traffic back to Py2 deployment (deployment config change)
2. Restore Py2 requirements (git revert or manual update)
3. Re-enable Py2 CI configuration
4. Optionally revert cutover-related code commits

**Commands**:
```bash
# Switch deployment
kubectl set image deployment/api api=api:py2-2024-02-01 --namespace prod

# Restore requirements
git revert <requirements_change_commit>

# Re-enable Py2 CI
git revert <ci_disable_commit>
```

**Time**: 10-20 minutes
**Risk**: MEDIUM (deployment changes require careful coordination)

---

## Success Criteria

The skill has succeeded when:

1. All migration phases are analyzed for rollback requirements
2. For each phase, exact git commits are identified (via git log and pattern matching)
3. Module-level rollback procedures are generated with dependency ordering
4. Feasibility assessment is performed (flag impossible rollbacks clearly)
5. Estimated rollback time is provided (per phase, per module)
6. Risk warnings are included (e.g., "files may have manual edits")
7. Rollback runbook includes exact commands (git revert, file operations)
8. Dependency graph is built (which module rollbacks block which others)
9. Verification procedures are provided (tests to run, deployment checks)
10. Optional: --test-rollback simulates rollback and reports feasibility

---

## References

- `references/migration-phases.md` — Detailed description of each migration phase
- `references/git-commit-patterns.md` — How to identify migration commits in git history
- `references/module-dependency-analysis.md` — Techniques for building module dependency graphs
- `references/rollback-risk-matrix.md` — Risk assessment for different rollback scenarios
- [Git revert documentation](https://git-scm.com/docs/git-revert)
- [Git cherry-pick documentation](https://git-scm.com/docs/git-cherry-pick)
