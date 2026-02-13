---
name: py2to3-conversion-unit-planner
description: >
  Take the dependency graph from Phase 0 and produce an ordered Python 2→3 conversion plan that groups
  tightly-coupled modules into conversion units and schedules them for safe dependency-order
  conversion. Use this skill whenever you need to plan the conversion order, figure out which
  modules can be converted in parallel, identify gateway modules that block large subgraphs,
  group mutually-importing modules into conversion units, or produce a human-reviewable
  conversion timeline. Also trigger when someone says "plan the conversion," "what order
  should we convert," "which modules go first," "show me the conversion schedule," "what's
  the critical path," "identify the gateway modules," or "group the modules for conversion."
  This is the strategic planning step before the mechanical conversion begins.
---

# Conversion Unit Planner

The Codebase Analyzer (Skill 0.1) produces the dependency graph and a basic topological
sort. This skill takes that further: it groups modules into conversion units, scores them
by risk, schedules them in safe dependency order, identifies the critical path, and
produces a plan that humans can review and approve before conversion begins.

## Why Planning Matters

Converting modules in the wrong order creates cascading failures. If module A imports
module B, and we convert A before B, then A's tests may fail not because of A's conversion
but because of incompatibilities with unconverted B. Converting leaf-first (modules with
no internal dependencies) and working up the tree avoids this.

Tightly-coupled modules (mutual imports) can't be converted one at a time — they must
move together as a unit. The planner identifies these clusters and creates conversion
units that respect these constraints.

## Inputs

- **dependency_graph**: Path to `dependency-graph.json` from Skill 0.1
- **migration_order**: Path to `migration-order.json` from Skill 0.1
- **state_file** (optional): Path to `migration-state.json` for risk score integration
- **target_version**: Target Python 3 version (affects risk scoring)
- **max_unit_size**: Maximum modules per conversion unit (default: 10)
- **parallelism**: How many units can be converted simultaneously (default: 3)

## Outputs

| File | Format | Purpose |
|------|--------|---------|
| `conversion-plan.json` | JSON | Ordered conversion units with deps and risk scores |
| `conversion-plan.md` | Markdown | Human-readable plan with timeline estimates |
| `critical-path.json` | JSON | Longest dependency chain (minimum migration time) |

## Workflow

### Step 1: Generate the Plan

```bash
python3 scripts/plan_conversion.py \
    --dep-graph <analysis_dir>/dependency-graph.json \
    --migration-order <analysis_dir>/migration-order.json \
    --output <output_dir> \
    --target-version 3.12 \
    [--state-file <analysis_dir>/migration-state.json] \
    [--max-unit-size 10] \
    [--parallelism 3]
```

### Step 2: Generate the Report

```bash
python3 scripts/generate_plan_report.py <output_dir>/conversion-plan.json \
    --output <output_dir>/conversion-plan.md \
    --project-name "Legacy SCADA System"
```

## What the Planner Does

### 1. Cluster Detection
Finds groups of modules with mutual (circular) imports that must be converted together.
Uses Tarjan's algorithm for strongly connected components.

### 2. Conversion Unit Formation
Groups modules into conversion units:
- Each strongly connected component (cluster) becomes one unit
- Remaining modules are grouped by directory/package affinity
- Units are capped at `max_unit_size` (split large groups by sub-package)
- Each unit gets a descriptive name based on its package path

### 3. Dependency Ordering
Builds a DAG of conversion units (not individual modules) and topologically sorts it.
Units are scheduled in waves:
- **Wave 1**: Leaf units (no dependencies on other unconverted units)
- **Wave 2**: Units that depend only on Wave 1 units
- **Wave N**: Units that depend on Wave 1–(N-1) units

Within each wave, up to `parallelism` units can run simultaneously.

### 4. Risk Scoring
Each unit gets a composite risk score based on:
- Maximum risk score of its member modules (from Phase 0)
- Total Py2-ism count across members
- Data layer involvement (binary protocols, encoding, serialization)
- Test coverage of members
- Fan-in (how many other units depend on this one)

### 5. Critical Path Analysis
Identifies the longest dependency chain through the conversion unit DAG. This determines
the minimum possible migration time regardless of parallelism.

### 6. Effort Estimation
Rough effort estimates per unit based on:
- Lines of code
- Number and severity of Py2-isms
- Whether semantic fixes are expected (data layer involvement)
- Automatable fraction from the lint baseline

## Conversion Plan Structure

```json
{
  "timestamp": "ISO-8601",
  "target_version": "3.12",
  "total_modules": 147,
  "total_units": 23,
  "total_waves": 8,
  "estimated_effort_days": 45,
  "waves": [
    {
      "wave": 1,
      "units": [
        {
          "name": "utils-common",
          "modules": ["src/utils/common.py", "src/utils/helpers.py"],
          "dependencies": [],
          "risk_score": "low",
          "risk_factors": [],
          "py2_ism_count": 12,
          "lines_of_code": 340,
          "estimated_effort_hours": 4,
          "automatable_percent": 85
        }
      ]
    }
  ],
  "critical_path": {
    "length": 8,
    "units": ["utils-common", "data-models", "scada-core", ...],
    "estimated_days": 32
  },
  "gateway_units": [
    {
      "name": "data-models",
      "fan_in": 15,
      "wave": 2,
      "risk_score": "high",
      "notes": "Blocks 15 downstream units. Convert with extra care."
    }
  ]
}
```

## Gateway Modules

Gateway modules are the bottlenecks: many other modules depend on them. If a gateway
module's conversion breaks, it cascades to everything downstream. The plan identifies
these and recommends:
- Extra test coverage before conversion
- Extra review after conversion
- Conversion in smaller, more cautious batches

## Integration with Other Skills

This skill depends on:
- **Skill 0.1 (Codebase Analyzer)**: `dependency-graph.json` and `migration-order.json`
- **Skill X.1 (Migration State Tracker)**: Risk scores and metrics per module

This skill's outputs feed into:
- **Skill 2.2 (Automated Converter)**: Conversion plan determines the order of work
- **Skill X.1 (Migration State Tracker)**: Unit assignments are written back to state

After running, register units in the migration state:

```bash
for unit in conversion_plan.units:
    for module in unit.modules:
        python3 ../py2to3-migration-state-tracker/scripts/update_state.py \
            <state_file> set-unit \
            --module <module> \
            --unit <unit.name>
```

## Important Notes

**The plan is a starting point, not a decree.** Real-world dependencies and constraints
will require adjustments. The plan should be reviewed by someone who understands the
codebase's domain (SCADA protocols, mainframe interfaces, etc.) before conversion begins.

**Gateway units deserve disproportionate attention.** A gateway unit with high fan-in and
high risk is the single most important thing to get right. Budget extra time for these.

**Wave parallelism is bounded by team capacity.** The planner assumes `N` units can be
worked on simultaneously, but in practice this depends on how many people are available
and how familiar they are with the code.
