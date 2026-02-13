#!/usr/bin/env python3
"""
Rollback Plan Report Generator

Reads rollback-plan.json and generates a human-readable Markdown runbook
with step-by-step procedures, time estimates, and risk assessment.

Usage:
    python3 generate_rollback_report.py \
        <output_dir>/rollback-plan.json \
        --output <output_dir>/rollback-runbook.md
"""

import json
import sys
import argparse
import os
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any


# ── Helper Functions ─────────────────────────────────────────────────────────

def load_json(path: str) -> Dict:
    """Load JSON file, return empty dict if not found."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def format_risk_level(level: str) -> str:
    """Format risk level with emoji/highlight."""
    risk_map = {
        "LOW": "🟢 LOW",
        "MEDIUM": "🟡 MEDIUM",
        "HIGH": "🔴 HIGH",
    }
    return risk_map.get(level, level)


def format_feasibility(feasibility: str) -> str:
    """Format feasibility status."""
    feasibility_map = {
        "FULLY_FEASIBLE": "✅ Fully Feasible",
        "PARTIALLY_FEASIBLE": "⚠️ Partially Feasible",
        "DIFFICULT": "🔴 Difficult",
        "NOT_FEASIBLE": "❌ Not Feasible",
        "NOT_APPLICABLE": "⊘ Not Applicable",
    }
    return feasibility_map.get(feasibility, feasibility)


# ── Report Generation ────────────────────────────────────────────────────────

def generate_report(plan_data: Dict) -> str:
    """Generate Markdown runbook from rollback plan."""
    output = []

    # Header
    output.append("# Rollback Runbook\n")
    output.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.append(f"**Codebase**: {plan_data.get('codebase_path', 'unknown')}\n")
    output.append("")

    # Executive Summary
    phases = plan_data.get("phases", {})
    module_rollbacks = plan_data.get("module_rollbacks", {})

    output.append("## Executive Summary\n")
    output.append(
        f"This runbook provides step-by-step procedures for rolling back a Python 2→3 migration. "
        f"It covers {len(phases)} phases and {len(module_rollbacks)} modules.\n\n"
    )

    # Quick Reference Table
    output.append("### Rollback Time Estimates\n\n")
    output.append("| Phase | Name | Feasibility | Time (min) | Modules |\n")
    output.append("|-------|------|-------------|-----------|----------|\n")

    total_time = 0
    for phase_num in sorted(phases.keys(), key=lambda x: int(x)):
        phase = phases[phase_num]
        name = phase.get("name", "")
        feasibility = format_feasibility(phase.get("feasibility", ""))
        time_est = phase.get("estimated_time_minutes", 0)
        modules = phase.get("modules_affected", 0)
        total_time += time_est

        output.append(
            f"| {phase_num} | {name} | {feasibility} | {time_est} | {modules} |\n"
        )

    output.append(f"\n**Total Estimated Time**: {total_time} minutes\n\n")

    # Detailed Phase-by-Phase Rollback Procedures
    output.append("## Detailed Rollback Procedures\n\n")

    for phase_num in sorted(phases.keys(), key=lambda x: int(x)):
        phase = phases[phase_num]
        output.append(_generate_phase_section(phase_num, phase))

    # Module-Level Rollback
    if module_rollbacks:
        output.append("## Module-Level Rollback\n\n")
        output.append(
            "Roll back individual modules to previous phases. "
            "Respect dependency order (modules with no dependents first).\n\n"
        )

        output.append(_generate_module_rollback_section(module_rollbacks))

    # Risk Assessment
    output.append("## Risk Assessment\n\n")
    output.append(_generate_risk_section(phases))

    # Prerequisites and Preparations
    output.append("## Prerequisites\n\n")
    output.append("""
Before executing any rollback, ensure you have:

1. **Git access**: Full git history available in working directory
2. **Deployment access**: Permissions to revert deployments (if Phase 5)
3. **Database backups**: Recent backups of all databases (not touched by rollback, but precaution)
4. **Communication**: Notify team members of rollback attempt
5. **Monitoring**: Have monitoring dashboard open during execution
6. **Incident response**: Have incident commander on standby

### Preparation Checklist

- [ ] Verify git history is complete: `git log --oneline | head -20`
- [ ] Confirm current deployment: `kubectl describe deployment api`
- [ ] Check Py2 image is available: `docker images | grep py2`
- [ ] Review this runbook thoroughly
- [ ] Brief team on rollback plan
- [ ] Open monitoring dashboard

""")

    # Command Reference
    output.append("## Command Reference\n\n")
    output.append("""
### Common Git Commands

```bash
# View commits matching pattern
git log --oneline --grep="pattern"

# Revert a commit
git revert <commit_hash>

# Revert multiple commits (oldest first)
git revert <commit_1> <commit_2> <commit_3>

# Check what changed in a commit
git show <commit_hash>

# Revert to a specific file state
git checkout <commit_hash> -- <filepath>

# Preview revert (dry-run)
git revert --dry-run <commit_hash>
```

### Kubernetes/Deployment Commands

```bash
# Switch deployment to Py2 image
kubectl set image deployment/api api=api:py2-<date> --namespace prod

# Wait for deployment to be ready
kubectl wait --for=condition=Ready pod -l app=api --timeout=300s

# Check deployment status
kubectl rollout status deployment/api -n prod

# Check pod logs
kubectl logs deployment/api -n prod --tail=50

# Check health
curl https://api.example.com/health
```

### Testing Commands

```bash
# Run unit tests
python2 -m pytest tests/ --tb=short

# Run integration tests
python2 -m pytest tests/integration/ --tb=short

# Check specific module
python2 -c "import mymodule; print(mymodule.__version__)"
```

""")

    # Post-Rollback Verification
    output.append("## Post-Rollback Verification\n\n")
    output.append("""
After completing rollback, verify everything is working:

### Immediate Checks (within minutes)

1. **Deployment health**
   ```bash
   kubectl get pods -l app=api -n prod
   kubectl logs deployment/api -n prod --tail=20
   ```

2. **Basic connectivity**
   ```bash
   curl https://api.example.com/health
   ```

3. **Error logs**
   ```bash
   kubectl logs deployment/api -n prod | grep -i error
   ```

### Short-term Verification (within 1 hour)

1. **Run test suite**
   ```bash
   python2 -m pytest tests/ --tb=short
   ```

2. **Smoke tests**
   - Manual API calls to critical endpoints
   - Database connectivity check
   - Cache connectivity check

3. **Monitoring**
   - Check error rates
   - Check latency
   - Check database query performance

### Longer-term Verification (within 24 hours)

1. **Full test suite with coverage**
   ```bash
   python2 -m pytest tests/ --cov=mymodule --tb=short
   ```

2. **Performance baselines**
   - Compare metrics to pre-migration values
   - Identify any regressions

3. **Data integrity**
   - Spot-check critical data
   - Verify recent user actions were preserved

""")

    # Troubleshooting
    output.append("## Troubleshooting\n\n")
    output.append("""
### Git Revert Conflicts

If a `git revert` fails due to conflicts:

```bash
# Check status
git status

# Review conflict markers
cat <conflicted_file>

# Resolve manually, then
git add <resolved_file>
git revert --continue
```

### Failed Deployment Switch

If Kubernetes deployment fails:

```bash
# Rollback the deployment itself
kubectl rollout undo deployment/api -n prod

# Or manually switch back
kubectl set image deployment/api api=<previous_image> --namespace prod
```

### Py2 Compatibility Issues

If Py2 code fails after rollback:

- Check imports: `python2 -m py_compile <file>`
- Run syntax check: `python2 -m tabnanny <file>`
- Check for Py3-only syntax accidentally left in code
- Search for missing imports: `grep -r "from __future__" src/`

### Data Migration Rollback

If data schema changed during Py3 migration:

- Restore database from pre-migration backup
- Or manually migrate data back to previous schema
- Coordinate with DBA for complex scenarios

""")

    # Rollback Decision Tree
    output.append("## Rollback Decision Tree\n\n")
    output.append("""
Use this to determine what to rollback:

```
Are any users affected?
├─ NO  → Proceed with Phase 5 rollback only (traffic control)
└─ YES → What phase introduced the bug?
    ├─ Phase 1 (Foundation)
    │  └─ Rollback Phase 1 only (15 min, safe)
    ├─ Phase 2 (Conversion)
    │  ├─ Identify affected module
    │  └─ Rollback Phase 2 for that module (30 min per module)
    ├─ Phase 3 (Semantic Fixes)
    │  ├─ Identify problematic fix
    │  ├─ Check fix dependencies
    │  └─ Rollback in reverse dependency order (45-90 min)
    ├─ Phase 4 (Verification)
    │  └─ This phase has no code changes; skip Phase 4
    └─ Phase 5 (Cutover)
       ├─ Switch deployment back to Py2 (15 min)
       └─ Identify root cause
```

""")

    # Contact and Escalation
    output.append("## Escalation Contacts\n\n")
    output.append("""
| Role | Contact | Priority |
|------|---------|----------|
| Incident Commander | on-call@company.com | P1 |
| Deployment Engineer | deploy@company.com | P1 |
| Database Administrator | dba@company.com | P1 (for data issues) |
| Infrastructure | infra@company.com | P1 (for infrastructure) |
| Release Manager | release@company.com | P2 |

### Escalation Procedure

1. Notify Incident Commander immediately
2. Open incident in incident tracking system
3. Post in #incidents Slack channel
4. If rollback will take > 30 minutes, notify VP Engineering
5. Keep incident updated every 15 minutes

""")

    # Rollback Scenarios
    output.append("## Rollback Scenarios\n\n")
    output.append("""
### Scenario 1: Bug Found in Phase 2 (Conversion)

**Symptom**: A specific module's converted code has a critical bug

**Decision**: Roll back that module only

**Procedure**:
1. Identify the affected module (e.g., `src/api/parser.py`)
2. Find Phase 2 conversion commits for that module
3. Revert those commits in reverse order
4. Run module-specific tests: `python3 -m pytest tests/test_parser.py`
5. Keep other modules on Py3
6. Proceed with Phase 2 rollback for that module only

**Time**: 15-30 minutes
**Risk**: LOW (isolated to one module)

### Scenario 2: Interdependent Semantic Fixes Issue

**Symptom**: Fix A works, but Fix B depends on Fix A and breaks

**Decision**: Roll back Fix B, then diagnose and re-apply

**Procedure**:
1. Identify Fix B commit
2. Identify all fixes that depend on Fix B
3. Revert dependent fixes first (reverse dependency order)
4. Revert Fix B itself
5. Review and re-fix the issue
6. Re-apply in correct order

**Time**: 45-90 minutes
**Risk**: HIGH (dependency management is critical)

### Scenario 3: Deployment Switch Failed (Phase 5)

**Symptom**: Traffic switched to Py3 but Py3 deployment has critical issue

**Decision**: Immediately switch traffic back to Py2

**Procedure**:
1. Trigger emergency traffic switch to Py2 deployment
2. Monitor error rates immediately
3. Verify Py2 deployment is healthy
4. Open incident post-mortem
5. Identify root cause in Py3 code
6. Schedule re-attempt

**Time**: 5-15 minutes
**Risk**: MEDIUM (deployment control is critical)

### Scenario 4: Data Consistency Issue

**Symptom**: Some data is corrupted or inconsistent after Py3 migration

**Decision**: Restore from backup, then re-migrate with fixes

**Procedure**:
1. Identify what data is corrupted
2. Estimate blast radius (how many users affected)
3. Decide: restore from backup or roll back code + fix data
4. If rolling back:
   - Restore database from pre-migration backup
   - Switch traffic back to Py2
   - Identify root cause
   - Re-migrate with fix
5. If fixing forward:
   - Write data migration script
   - Apply script
   - Verify data consistency
   - Continue on Py3

**Time**: 30 minutes - 2 hours (depends on backup restore time)
**Risk**: HIGH (data consistency is critical)

""")

    # Success Metrics
    output.append("## Success Metrics\n\n")
    output.append("""
### After Successful Rollback, Verify:

| Metric | Target | How to Check |
|--------|--------|--------------|
| Deployment Health | 100% pods ready | `kubectl get pods -l app=api` |
| Error Rate | < 0.1% | Monitoring dashboard |
| Latency | < 10% increase | Monitoring dashboard |
| Tests Pass | 100% | `python2 -m pytest tests/` |
| API Health | Responding | `curl https://api.example.com/health` |
| Database Integrity | OK | Run consistency checks |
| Logs Clean | No critical errors | `kubectl logs deployment/api` |
| Users Unaffected | No reports | Check support tickets |

### Post-Rollback Tasks (within 24 hours)

1. [ ] Write incident post-mortem
2. [ ] Identify root cause of issue
3. [ ] Schedule fix and re-attempt
4. [ ] Update this runbook with lessons learned
5. [ ] Brief team on findings
6. [ ] Plan preventive measures
7. [ ] Update monitoring/alerting

""")

    # Appendix
    output.append("## Appendix: Phase Descriptions\n\n")
    output.append("""
### Phase 1: Foundation

What was done:
- Added `from __future__ import ...` to prepare code for Py3
- Created test scaffolding and verification framework
- Updated CI to run tests on both Py2 and Py3

Rollback impact:
- Code loses Py3 compatibility features
- Some tests may fail without scaffolding
- CI will only run on Py2

Risk: LOW

### Phase 2: Mechanical Conversion

What was done:
- Automated conversion tool (lib2to3) converted syntax
- Updated print statements to functions
- Updated dict methods (keys(), values(), items())
- Updated exception syntax

Rollback impact:
- Code reverts to Py2-only syntax
- Must be paired with Phase 1 rollback (or at least remove `from __future__`)
- Some files may have manual edits post-conversion that are lost

Risk: MEDIUM (some manual edits may be lost)

### Phase 3: Semantic Fixes

What was done:
- Manual fixes for Py2/Py3 semantic differences
- Fixed unicode/bytes handling
- Fixed string type assumptions
- Fixed division behavior (true division vs floor division)

Rollback impact:
- Code loses semantic fixes
- Must manage fix dependencies carefully
- Some fixes may depend on Phase 2 conversion

Risk: HIGH (interdependencies are complex)

### Phase 4: Verification

What was done:
- Comprehensive testing on Py3
- Performance benchmarking
- Behavioral diff generation
- Documentation updates

Rollback impact:
- Read-only phase, no code changes
- No actual rollback needed
- If issues found, roll back to Phase 3

Risk: LOW (no code changes)

### Phase 5: Cutover

What was done:
- Switched traffic to Py3 deployment
- Disabled Py2 CI
- Updated monitoring and alerting for Py3
- Updated deployment configurations

Rollback impact:
- Traffic switches back to Py2 deployment
- Py2 CI is re-enabled
- Monitoring returns to Py2 baseline
- Requires deployment system coordination

Risk: MEDIUM (deployment control is critical)

""")

    return "\n".join(output)


def _generate_phase_section(phase_num: str, phase: Dict) -> str:
    """Generate section for a single phase."""
    output = []

    name = phase.get("name", "")
    description = phase.get("description", "")
    feasibility = format_feasibility(phase.get("feasibility", ""))
    time_est = phase.get("estimated_time_minutes", 0)
    modules = phase.get("modules_affected", 0)

    output.append(f"### Phase {phase_num}: {name}\n")
    output.append(f"**Description**: {description}\n\n")
    output.append(f"**Feasibility**: {feasibility}\n")
    output.append(f"**Estimated Time**: {time_est} minutes\n")
    output.append(f"**Modules Affected**: {modules}\n\n")

    if "notes" in phase:
        output.append(f"**Notes**: {phase['notes']}\n\n")

    # Steps
    if "steps" in phase:
        output.append("#### Rollback Steps\n\n")
        for step in phase.get("steps", []):
            order = step.get("order", "?")
            action = step.get("action", "")
            description = step.get("description", "")
            time = step.get("time_estimate_minutes", "?")
            risk = format_risk_level(step.get("risk_level", "MEDIUM"))

            output.append(f"**Step {order}: {action}**\n\n")
            output.append(f"- Description: {description}\n")
            output.append(f"- Time: {time} minutes\n")
            output.append(f"- Risk: {risk}\n\n")

            # Commands
            if "commands" in step:
                output.append("Commands:\n")
                for cmd in step.get("commands", []):
                    output.append(f"```bash\n{cmd}\n```\n")
                output.append("")

    # Strategy
    if "rollback_strategy" in phase:
        output.append("#### Rollback Strategy\n\n")
        output.append(f"{phase['rollback_strategy']}\n\n")

    # Verification
    if "verification" in phase:
        output.append("#### Verification\n\n")
        verification = phase.get("verification", "")
        output.append(f"Run this command to verify successful rollback:\n\n")
        output.append(f"```bash\n{verification}\n```\n\n")

    # Risks
    if "risks" in phase:
        output.append("#### Known Risks\n\n")
        for risk in phase.get("risks", []):
            output.append(f"- ⚠️ {risk}\n")
        output.append("\n")

    return "".join(output)


def _generate_module_rollback_section(module_rollbacks: Dict[str, Dict]) -> str:
    """Generate module-level rollback section."""
    output = []

    # Sort by rollback order
    sorted_modules = sorted(
        module_rollbacks.items(),
        key=lambda x: x[1].get("estimated_time_minutes", 0),
    )

    output.append("### Module Rollback Order\n\n")
    output.append("Roll back in this order (fastest first):\n\n")

    for i, (module, info) in enumerate(sorted_modules[:20], 1):
        current_phase = info.get("current_phase", 0)
        rollback_to = info.get("rollback_to_phase", 0)
        time = info.get("estimated_time_minutes", "?")
        feasibility = format_feasibility(info.get("feasibility", ""))

        output.append(
            f"{i}. `{module}` "
            f"(Phase {current_phase} → {rollback_to}, {time} min, {feasibility})\n"
        )

    if len(sorted_modules) > 20:
        output.append(f"\n... and {len(sorted_modules) - 20} more modules\n")

    output.append("\n#### Per-Module Procedure\n\n")
    output.append("For each module:\n\n")
    output.append("""
```bash
# 1. Identify commits for this module
git log --oneline -- <module_path> | head -10

# 2. Review changes
git show <commit_hash>

# 3. Revert commits in reverse order
git revert <commit_1>
git revert <commit_2>
git revert <commit_3>

# 4. Verify module still works
python2 -c "import mymodule; print('OK')"

# 5. Run module tests
python2 -m pytest tests/<module>_test.py --tb=short
```
""")

    return "".join(output)


def _generate_risk_section(phases: Dict[str, Dict]) -> str:
    """Generate risk assessment section."""
    output = []

    output.append("### Risk Levels by Phase\n\n")

    risk_by_phase = {}
    for phase_num, phase in phases.items():
        high_risk_steps = []
        for step in phase.get("steps", []):
            if step.get("risk_level") == "HIGH":
                high_risk_steps.append(step.get("description", ""))

        risk_by_phase[int(phase_num)] = {
            "phase": phase.get("name", ""),
            "feasibility": phase.get("feasibility", ""),
            "high_risk_steps": high_risk_steps,
            "risks": phase.get("risks", []),
        }

    for phase_num in sorted(risk_by_phase.keys()):
        phase_info = risk_by_phase[phase_num]
        output.append(f"#### Phase {phase_num}: {phase_info['phase']}\n\n")
        output.append(f"**Feasibility**: {format_feasibility(phase_info['feasibility'])}\n\n")

        if phase_info["high_risk_steps"]:
            output.append("**High-Risk Steps**:\n")
            for step in phase_info["high_risk_steps"]:
                output.append(f"- 🔴 {step}\n")
            output.append("\n")

        if phase_info["risks"]:
            output.append("**Known Risks**:\n")
            for risk in phase_info["risks"]:
                output.append(f"- ⚠️ {risk}\n")
            output.append("\n")

    output.append("""
### Overall Risk Mitigation

- **Test the rollback**: Use `--test-rollback` flag before executing
- **Gradual rollback**: Consider rolling back one module at a time
- **Communication**: Notify stakeholders before starting
- **Monitoring**: Keep monitoring dashboard open throughout
- **Abort criteria**: Define conditions for aborting rollback
- **Post-rollback**: Verify everything works before declaring success

""")

    return "".join(output)


# ── Main Entry Point ────────────────────────────────────────────────────────

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Markdown rollback runbook from rollback plan"
    )
    parser.add_argument("plan_json", help="Path to rollback-plan.json")
    parser.add_argument("--output", default="rollback-runbook.md",
                       help="Output Markdown file (default: rollback-runbook.md)")

    args = parser.parse_args()

    # Load plan
    plan_data = load_json(args.plan_json)
    if not plan_data:
        print(f"Error: Could not load {args.plan_json}", file=sys.stderr)
        sys.exit(1)

    # Generate report
    markdown = generate_report(plan_data)

    # Write output
    with open(args.output, "w") as f:
        f.write(markdown)

    print(f"Wrote: {args.output}")
    print(f"Rollback runbook generated successfully")
    total_time = sum(p.get('estimated_time_minutes', 0)
                     for p in plan_data.get('phases', {}).values())
    print(f"Total time estimate: {total_time} minutes")

    sys.exit(0)


if __name__ == "__main__":
    main()
