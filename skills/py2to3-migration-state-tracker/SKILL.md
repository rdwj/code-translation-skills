---
name: py2to3-migration-state-tracker
description: >
  Track the migration state of every module in a Python 2→3 migration project. Use this
  skill whenever you need to initialize migration tracking from a Phase 0 codebase analysis,
  update a module's phase or record a decision, check whether a module can advance to the
  next phase, view overall migration progress, or generate a progress dashboard for
  stakeholders. Also trigger when someone says "what's the migration status," "which modules
  are in phase 2," "can we advance the SCADA modules," "record this decision," or "show me
  the migration dashboard." This is the central coordination point — every other skill in
  the migration suite reads from and writes to the state file this skill manages. This skill's schema now includes language detection, behavioral equivalence confidence, modernization opportunities, and model-tier tracking to support multi-language migration and atomic work decomposition.
---

# Migration State Tracker

The single source of truth for migration progress. This skill maintains a persistent
`migration-state.json` file that records where every module is in the Py2→Py3 pipeline,
what decisions have been made, what's blocking progress, and how the overall project is
trending.

Every other skill in the suite interacts with this state:
- **Phase 0 skills** initialize it (one module per file, all starting at phase 0)
- **Phase 1–4 skills** update it as they complete work on modules
- **Gate Checker** reads it to determine if phase advancement criteria are met
- **Rollback Plan Generator** reads it to understand what needs undoing
- Stakeholders read the generated dashboard to track progress

## Why Central State Matters

In a large migration with no original developers, institutional knowledge evaporates fast.
The state tracker captures not just *where* things are but *why* decisions were made. Six
months from now, when someone asks "why did we decide to keep Modbus register data as bytes
all the way to the display layer?" — the answer is in the state tracker, not in someone's
head.

## State File Location

The state file lives at `<codebase_root>/migration-analysis/migration-state.json`. This
is the same directory where the Codebase Analyzer (Skill 0.1) writes its outputs, keeping
all migration artifacts together.

## Data Model

The state file has this top-level structure:

```json
{
  "project": {
    "name": "string",
    "codebase_path": "/absolute/path/to/codebase",
    "target_version": "3.12",
    "created": "ISO-8601 datetime",
    "last_updated": "ISO-8601 datetime"
  },
  "modules": {
    "relative/path/to/module.py": { ... module state ... }
  },
  "conversion_units": {
    "unit-name": { ... unit state ... }
  },
  "global_decisions": [ ... ],
  "waivers": [ ... ],
  "rollbacks": [ ... ],
  "summary": {
    "total_modules": 0,
    "by_phase": { "0": 0, "1": 0, "2": 0, "3": 0, "4": 0, "5": 0 },
    "by_risk": { "low": 0, "medium": 0, "high": 0, "critical": 0 },
    "by_language": {},
    "behavioral_confidence_avg": null,
    "model_tier_usage": {"haiku": 0, "sonnet": 0, "opus": 0}
  }
}
```

See `references/state-schema.md` for the complete schema with all fields documented.

## Module State

Each module entry tracks:

```json
{
  "current_phase": 0,
  "phase_history": [
    {
      "phase": 0,
      "started": "ISO-8601",
      "completed": "ISO-8601 or null",
      "gate_passed": true,
      "gate_report": "path/to/gate-check-report.json or null",
      "skill_outputs": ["list of output files produced by skills for this module at this phase"]
    }
  ],
  "conversion_unit": "unit-name or null",
  "risk_score": "low|medium|high|critical",
  "risk_factors": ["binary_protocol_handling", "no_existing_tests", ...],
  "blockers": [
    {
      "id": "unique-id",
      "description": "Module depends on scada-utils which is still in phase 1",
      "blocking_since": "ISO-8601",
      "resolved": null,
      "resolution": null
    }
  ],
  "decisions": [
    {
      "date": "ISO-8601",
      "decision": "Modbus register data stays as bytes until display layer",
      "rationale": "Protocol data is binary; only text representation needed at UI",
      "made_by": "human|skill",
      "skill_name": "bytes-string-fixer or null",
      "reversible": true
    }
  ],
  "notes": ["Free-form notes added during migration"],
  "py2_ism_counts": {
    "syntax": 12,
    "semantic_iterator": 3,
    "semantic_bytes_str": 8,
    "semantic_division": 1,
    "semantic_import": 2,
    "metaclass": 0
  },
  "metrics": {
    "lines_of_code": 450,
    "num_functions": 23,
    "num_classes": 4,
    "test_coverage_percent": null,
    "dependency_fan_in": 7,
    "dependency_fan_out": 3
  },
  "language": "python",
  "behavioral_equivalence_confidence": null,
  "modernization_opportunities": [],
  "model_tier_used": null,
  "behavioral_contract_summary": null
}
```

## Conversion Units

Modules that must be migrated together (mutual imports, shared state) are grouped into
conversion units. The Conversion Unit Planner (Skill 2.1) creates these, but the state
tracker manages them:

```json
{
  "modules": ["path/to/mod_a.py", "path/to/mod_b.py"],
  "languages": ["python"],
  "current_phase": 2,
  "dependencies": ["other-unit-name"],
  "risk_score": "high",
  "assigned_to": null,
  "notes": []
}
```

A conversion unit can only advance when ALL its member modules meet the gate criteria,
and all units it depends on are at the same phase or higher.

## Workflows

### Initialize State from Phase 0

After running the Codebase Analyzer (Skill 0.1), initialize the state tracker:

```bash
python3 scripts/init_state.py <analysis_dir> \
    --project-name "Legacy SCADA System" \
    --target-version 3.12 \
    --output <analysis_dir>/migration-state.json
```

This reads `raw-scan.json`, `dependency-graph.json`, and `migration-order.json` from the
analysis directory and creates the initial state with every module at phase 0.

### Update Module State

As skills complete work on modules, update the state:

```bash
# Advance a module to the next phase (records timestamp, validates dependencies)
python3 scripts/update_state.py <state_file> advance \
    --module "src/scada/modbus_reader.py" \
    --gate-report "path/to/gate-report.json"

# Record a decision
python3 scripts/update_state.py <state_file> decision \
    --module "src/scada/modbus_reader.py" \
    --decision "Keep Modbus data as bytes until display layer" \
    --rationale "Protocol data is binary, only text representation needed at UI" \
    --made-by human

# Add a blocker
python3 scripts/update_state.py <state_file> blocker \
    --module "src/scada/modbus_reader.py" \
    --description "Depends on scada-utils which is still in phase 1"

# Resolve a blocker
python3 scripts/update_state.py <state_file> resolve-blocker \
    --module "src/scada/modbus_reader.py" \
    --blocker-id "blocker-001" \
    --resolution "scada-utils advanced to phase 2"

# Record a rollback
python3 scripts/update_state.py <state_file> rollback \
    --module "src/scada/modbus_reader.py" \
    --from-phase 3 \
    --to-phase 2 \
    --reason "Encoding bug found in EBCDIC handling path"

# Add a note
python3 scripts/update_state.py <state_file> note \
    --module "src/scada/modbus_reader.py" \
    --text "Found undocumented dependency on cp1047 codec via manual byte manipulation"

# Set conversion unit membership
python3 scripts/update_state.py <state_file> set-unit \
    --module "src/scada/modbus_reader.py" \
    --unit "scada-core"

# Record a waiver (accepting risk for a gate criterion)
python3 scripts/update_state.py <state_file> waiver \
    --phase 2 \
    --criterion "test_coverage >= 80%" \
    --actual-value "62%" \
    --justification "Module handles deprecated hardware no longer available for integration testing" \
    --approved-by "Wes Jackson"

# Set behavioral equivalence confidence
python3 scripts/update_state.py <state_file> set-behavioral-confidence \
    --module "src/scada/modbus_reader.py" \
    --confidence 0.92

# Record a modernization opportunity
python3 scripts/update_state.py <state_file> add-modernization-opportunity \
    --module "src/scada/modbus_reader.py" \
    --target-language rust \
    --suggestion "Replace struct.pack/unpack with serde for safer binary handling" \
    --risk medium

# Record which model tier was used for migration
python3 scripts/update_state.py <state_file> set-model-tier \
    --module "src/scada/modbus_reader.py" \
    --tier sonnet
```

### Query State

```bash
# Show overall progress dashboard
python3 scripts/query_state.py <state_file> dashboard

# Show a specific module's state
python3 scripts/query_state.py <state_file> module --path "src/scada/modbus_reader.py"

# List all modules at a given phase
python3 scripts/query_state.py <state_file> by-phase --phase 2

# List all blockers
python3 scripts/query_state.py <state_file> blockers

# Check if a module can advance (dependency check)
python3 scripts/query_state.py <state_file> can-advance --module "src/scada/modbus_reader.py"

# Show all decisions for a module or globally
python3 scripts/query_state.py <state_file> decisions --module "src/scada/modbus_reader.py"
python3 scripts/query_state.py <state_file> decisions --global

# Generate the markdown dashboard file
python3 scripts/query_state.py <state_file> dashboard --output migration-dashboard.md

# Show modules by risk score
python3 scripts/query_state.py <state_file> by-risk --risk high

# Show timeline projection based on velocity
python3 scripts/query_state.py <state_file> timeline

# Show modules by language
python3 scripts/query_state.py <state_file> by-language --language python

# Show modernization opportunities
python3 scripts/query_state.py <state_file> modernization-opportunities

# Show modules with low behavioral confidence
python3 scripts/query_state.py <state_file> behavioral-confidence --threshold 0.8

# Show model tier usage and cost estimate
python3 scripts/query_state.py <state_file> model-tier-usage
```

## Integration with Other Skills

Every skill in the suite should update the state tracker when it completes work. The
pattern is:

1. **Before starting**: Query the state to understand the module's current phase and any
   blockers or decisions that affect the work.
2. **During work**: Record decisions as they're made (especially for semantic choices in
   Phase 3 — bytes vs str, encoding selection, library replacements).
3. **After completion**: Record skill outputs in the module's phase_history and, if the
   skill's work represents phase completion, note that the phase work is done (the Gate
   Checker still needs to formally advance the phase).

Skills should read the state file directly (it's JSON) and use `update_state.py` to write
changes. This avoids concurrent-write issues since migration work is typically sequential
per module.

## Dashboard Output

The `dashboard` command produces a markdown summary like:

```markdown
# Migration Dashboard — [Project Name]
## Overall Progress
- Target version: Python 3.12
- Total modules: 147
- Phase 0 (Discovery): 12 modules (8%)
- Phase 1 (Foundation): 45 modules (31%)
- Phase 2 (Mechanical): 68 modules (46%)
- Phase 3 (Semantic): 18 modules (12%)
- Phase 4 (Verification): 4 modules (3%)
- Phase 5 (Cutover): 0 modules (0%)

## Risk Summary
- Critical: 8 modules (all in data layer)
- High: 23 modules
- Medium: 67 modules
- Low: 49 modules

## Active Blockers: 3
1. src/mainframe/ebcdic_handler.py — Waiting for encoding-patterns.md reference
2. ...

## Recent Decisions (last 7 days)
...

## Velocity
- Modules advanced this week: 12
- Average time per module (Phase 1→2): 2.3 days
- Projected completion: [date estimate]

## Language Breakdown
- Python: 135 modules (92%)
- C: 8 modules (5%)
- Java: 4 modules (3%)

## Behavioral Confidence
- High (>0.8): 45 modules
- Moderate (0.5-0.8): 12 modules
- Low (<0.5): 3 modules
- Not assessed: 87 modules

## Model Tier Usage
- Haiku: 1,247 work items (68%)
- Sonnet: 423 work items (23%)
- Opus: 87 work items (5%)
- Estimated cost savings vs Opus-only: ~85%
```

## Important Design Choices

**Why JSON and not a database?** The state file is JSON because:
- It's human-readable and diffable in git
- Other skills can read it without any dependencies
- It's small enough (even for hundreds of modules) that loading the whole file is fine
- It can be version-controlled alongside the codebase being migrated

**Why per-module, not per-file?** A "module" here means a `.py` file. The state tracks at
file granularity because that's the unit of analysis from Phase 0 and the unit of
conversion in Phase 2. Conversion units group files that must move together.

**Why record decisions?** This is an archaeology project. The original developers are gone.
Every decision about how to handle an encoding, which library to replace with what, or
why a particular bytes/str boundary was resolved a certain way needs to be recorded. Future
maintainers will thank us.

## References

- `references/SUB-AGENT-GUIDE.md` — How to delegate work to sub-agents: prompt injection, context budgeting, parallel execution
