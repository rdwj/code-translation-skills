---
name: migration-dashboard
description: >
  Generate a self-contained HTML dashboard for tracking migration progress with split-pane
  dependency graph visualization. Use this skill whenever you need to visualize migration
  progress across a codebase, present status to stakeholders, track module conversion state,
  understand project risks and blockers, or examine architectural dependencies before and
  after migration. Also trigger when someone says "show the dashboard," "migration status,"
  "project progress," "visualize the migration," "show dependency graph status," or "generate
  the dashboard." This is the primary communication tool for migration progress — an interactive,
  self-contained HTML artifact that requires no backend and works offline.
---

# Migration Dashboard

Generate a self-contained HTML dashboard that visualizes migration progress with side-by-side
source and target dependency graphs, status rollup, risk analysis, blockers, timeline projections,
and per-module behavioral confidence indicators.

The dashboard is the primary tool for communicating migration status to stakeholders. It answers:
- How far along are we? (progress bar, phase distribution)
- What's at risk? (risk heatmap, critical modules)
- What's blocking us? (blocker list with impact analysis)
- How fast are we moving? (velocity metrics, completion ETA)
- What modules should we focus on next? (priority scoring)
- How confident are we in each module's migration? (behavioral contracts, findings, testing coverage)
- What's the cost? (model tier usage, token counts, cost per module)

## Design Philosophy

**No backend required.** The dashboard is a single `index.html` file with embedded JSON data
and client-side JavaScript. Deploy it anywhere — local file system, S3, Confluence, Slack,
wherever stakeholders can open a browser.

**Split-pane comparison.** Left side shows the source codebase dependency graph. Right side
shows the target codebase as built. This makes architectural changes visible and validates that
dependencies aren't accumulating during migration.

**Color-coded by status.** Every node in both graphs is colored by module phase: gray (not started),
yellow (in progress), red (blocked), blue (migrated), green (tested), dark green (evaluated),
purple (deployed).

**Risk is visible.** Node size or border intensity reflects risk score. Hover over a node to see
risk factors (no tests, binary protocols, etc.) and decision history.

**Blockers bubble up.** A dedicated panel lists what's blocking the most downstream work. Click
any blocker to see which modules can't advance because of it.

**Timeline is realistic.** Based on actual velocity (modules migrated per day), compute estimated
completion date with confidence intervals.

## Inputs

| File | Source | Purpose |
|------|--------|---------|
| `migration-state.json` | migration-state-tracker | Module phases, decisions, blockers, risk scores, metrics |
| `dependency-graph.json` | universal-code-graph or codebase-analyzer | Node and edge definitions for source codebase graph |
| `behavioral-contracts.json` | behavioral-contract-extractor (optional) | Per-function behavioral specs, confidence indicators |
| `work-items.json` | work-item-generator (optional) | Work queue with model tier routing and cost estimates |

All inputs are JSON files. The dashboard script reads them, merges them into a data model,
and generates a single `index.html` with embedded data and visualization code.

## Outputs

| File | Format | Purpose |
|------|--------|---------|
| `dashboard/index.html` | HTML + embedded JS | Self-contained, interactive, offline-capable dashboard |

The HTML file is completely self-contained: all data is embedded as JSON in a `<script>` block,
all CSS is inline in `<style>` tags, and all JavaScript is inline. Open it in any modern browser
(Chrome, Firefox, Safari, Edge) with `file://` protocol — no server needed.

## Core Features

### 1. Split-Pane Dependency Graphs

**Left pane**: Source codebase dependency graph. Shows the structure before migration started.
Helps stakeholders understand the architectural baseline.

**Right pane**: Target codebase dependency graph. Shows modules as migrated. Reveals how the
architecture changes during migration.

**Nodes**: Represent modules (files or packages). Size reflects lines of code or complexity.
Color reflects phase (gray → blue → green → purple as migration progresses).

**Edges**: Represent import/dependency relationships. Thickness reflects number of relationships.
Direction shows dependency flow.

**Interaction**:
- Click a node to open the detail panel and see analysis
- Hover over a node to see module name, phase, risk score, found issues
- Click an edge to highlight the dependency path
- Double-click to zoom into a region
- Drag to pan, scroll to zoom

### 2. Color Coding by Status

Every node is colored to show its current phase:

| Color | Phase | Meaning |
|-------|-------|---------|
| Gray | 0: Not Started | Awaiting analysis or planning |
| Yellow | 1: Foundation | Core migration work started |
| Orange | 2: Mechanical | Automated conversions applied |
| Blue | 3: Semantic | Manual analysis and refactoring done |
| Light Green | 4: Verification | Tests written and passing |
| Dark Green | 5: Evaluated | Integration testing complete |
| Purple | 6: Deployed | Live in production |

### 3. Progress Bar and Summary

Top of dashboard shows:
- **Overall progress**: "45/120 modules migrated" (42%)
- **Phase breakdown**: Pie or bar chart showing count by phase
- **Risk summary**: Count of critical, high, medium, low risk modules
- **Velocity**: "3.2 modules/day, projected completion in 22 days"
- **Cost**: Total tokens, cost by model tier, savings vs manual migration

### 4. Cluster View

Tightly-coupled modules can be collapsed into super-nodes:

- Click "Show Clusters" to collapse modules with high mutual dependencies
- Each cluster shows a representative module name (e.g., "data-layer" containing
  `models.py`, `serializers.py`, `validators.py`)
- Click to expand and drill into individual modules
- Helps stakeholders understand architecture without drowning in detail

### 5. Risk Heatmap

Node size or border intensity reflects risk score:

- **Node size**: Larger nodes = higher risk
- **Border color**: Bright red = critical, darker red = high, orange = medium, gray = low
- **Hover**: See specific risk factors (no tests, binary protocol, undocumented, C extension, etc.)
- **Risk factors sorted by impact**: Helps teams prioritize mitigation

### 6. Blockers List

Dedicated panel showing what's preventing progress:

```
Active Blockers (3)
1. src/scada/modbus_reader.py ← Blocks 12 downstream modules
   Reason: Depends on src/utils/encoding.py still in phase 1
   Duration: 3 days, 8 hours
   Resolution: encoding.py advancement blocked by test suite failure

2. src/data/ebcdic_handler.py ← Blocks 8 downstream modules
   Reason: Requires decision on EBCDIC codec replacement strategy
   Duration: 5 days, 2 hours
   Assigned to: [unassigned]

3. test/integration/ ← Blocks 4 downstream modules
   Reason: Integration tests depend on in-flight refactoring of src/api/
```

Each blocker shows:
- Which module is blocked
- Why
- How long it's been blocking
- How many downstream modules are affected
- Suggested resolution
- Click to see modules affected

### 7. Timeline and Velocity

Based on actual migration pace, compute estimated completion:

```
Velocity: 2.8 modules/day (rolling 7-day average)
Last 7 days: 19 modules migrated
Estimated phases remaining: 65 modules
Time remaining: 23.2 days
Projected completion: Mar 12, 2026

Confidence: High (velocity stable, no trend toward slowdown)
Risk factors: Testing bottleneck expected in phase 4 (add 2 days buffer)
```

Recalculates as new modules advance. Shows trend line (accelerating/stable/decelerating).

### 8. Detail Panel

Click any module to open a side panel:

```
Module: src/scada/modbus_reader.py
Phase: 3 (Semantic analysis)
Risk: High
File size: 387 LOC, 12 functions, 4 classes

Phase History:
  Phase 0: Started Jan 15, completed Jan 17 (2 days)
  Phase 1: Started Jan 18, completed Jan 22 (4 days)
  Phase 2: Started Jan 23, completed Jan 31 (8 days, delayed by design review)
  Phase 3: Started Feb 1, in progress for 3 days

Findings (raw-scan.json):
  - 4 except syntax issues (print-like errors)
  - 8 string/bytes mixing (protocol data)
  - 2 division operators (requires investigation)
  - 1 C extension dependency (socket module)

Risk factors:
  - No existing tests (legacy code)
  - Binary protocol handling (Modbus frames)
  - Undocumented state management

Decisions recorded:
  - Jan 20: "Keep Modbus data as bytes until display layer"
    Rationale: Protocol frames are binary, only text representation at UI
    Made by: [human] Elena Rodriguez

Metrics:
  - Lines of code: 387
  - Functions: 12
  - Classes: 4
  - Test coverage: 0%
  - Dependency fan-in: 3
  - Dependency fan-out: 6

Blockers:
  None currently

Notes:
  - Found undocumented caching layer on line 200
  - Original author left company in 2019, no institutional knowledge
  - Potential for performance refactoring post-migration

Behavioral Contracts (if available):
  - modbus_decode_frame(): Takes 8-byte input, returns dict with address/value/crc
    Confidence: 82% (behavior matches protocol spec)
  - register_write(): State changes validated across 3 test vectors
    Confidence: 76% (missing real-time constraints test)
```

### 9. Behavioral Confidence Indicators

If behavioral-contracts.json is available, show per-module behavioral confidence:

```
Behavioral Confidence: 78%

Confident functions (≥80%):
  - modbus_decode_frame(): 82%
  - register_read(): 85%

Uncertain functions (<80%):
  - register_write(): 76% (missing RT constraint validation)
  - cache_invalidate(): 64% (undocumented cache invalidation)

Overall: 5 of 8 functions have high-confidence contracts
Next step: Add integration test for register_write() RT constraints
```

### 10. Model-Tier Cost Tracking

Show work item distribution and cost:

```
Work Distribution by Model:
Haiku:   185 items (68%), $2.80 (10% of cost)
Sonnet:  68 items (25%), $24.50 (80% of cost)
Opus:    14 items (5%), $2.80 (10% of cost)

Total: 267 work items, $30.10 estimated cost

Savings:
If entire codebase handled by Opus: $155.00
Actual cost via tiered routing: $30.10
Savings: $124.90 (80% cost reduction)
```

### 11. Language Breakdown

Summary of codebase composition (from language-summary.json):

```
Languages in codebase:
Python:      890 files, 145K lines (primary migration target)
Java:         12 files, 23K lines (dependent library, not migrated)
C:             3 files, 8K lines (extensions)
Makefiles:     4 files
YAML:         23 files (config, not code)

Lines per language:
[visualization with stacked bar or pie]
```

## Technical Approach

The dashboard is built using:

1. **Dependency graph visualization**: Canvas-based force-directed graph (extends existing
   `dependency-graph-template.html`). Uses Coulomb repulsion and spring attraction to create
   a readable layout.

2. **Data embedding**: All JSON inputs are read by the generation script and embedded as
   JavaScript objects in `<script type="application/json">` tags. This avoids CORS issues
   and makes the file truly self-contained.

3. **Status dimension**: The force-directed layout is enhanced with a third dimension:
   phase (0–6). Modules in later phases are pulled toward the right side of the canvas,
   creating a visual left→right progression.

4. **Client-side JavaScript**: D3.js or vanilla Canvas API renders the graph. On-demand
   queries and filtering happen in the browser without server round-trips.

5. **No backend**: The script (`scripts/generate_dashboard.py`) runs once to produce
   `index.html`. After that, zero infrastructure is needed.

## Workflow

### Step 1: Gather Inputs

Ensure these files exist in the migration analysis directory:
- `migration-state.json` (required): Generated by migration-state-tracker
- `dependency-graph.json` (required): From universal-code-graph or codebase-analyzer
- `behavioral-contracts.json` (optional): From behavioral-contract-extractor
- `work-items.json` (optional): From work-item-generator

### Step 2: Run Generation Script

```bash
python3 scripts/generate_dashboard.py \
    <analysis_dir>/migration-state.json \
    <analysis_dir>/dependency-graph.json \
    --behavioral-contracts <analysis_dir>/behavioral-contracts.json \
    --work-items <analysis_dir>/work-items.json \
    --output <analysis_dir>/dashboard/index.html
```

### Step 3: Open Dashboard

```bash
# On local machine:
open dashboard/index.html

# Or serve via HTTP (if you need CORS):
python3 -m http.server 8000
# Then visit http://localhost:8000/dashboard/index.html
```

### Step 4: Share with Stakeholders

Copy or upload the single `index.html` file to:
- Slack (as an artifact attachment)
- Confluence (via page attachment or embedded iframe)
- S3 (make public or require authentication)
- Email (as attachment)
- Git (commit to a `dashboards/` directory)

The file works everywhere — no dependencies, no build step.

## Scripts Reference

### `scripts/generate_dashboard.py`

Main entry point. Reads all JSON inputs, merges data, and generates `index.html`.

```bash
python3 scripts/generate_dashboard.py <migration-state.json> <dependency-graph.json> \
    [--behavioral-contracts <path>] \
    [--work-items <path>] \
    [--output <path>]
```

**Algorithm**:
1. Load all JSON inputs
2. Build data model: merge module state with graph structure
3. Compute derived metrics: blockers impact, velocity, ETA
4. Render template with embedded data
5. Write `index.html`

**Output**: Self-contained HTML file (~5–15 MB for large codebases, mostly embedded JSON)

## Integration with Other Skills

This skill consumes outputs from:

| Source Skill | Output | How Used |
|--------------|--------|----------|
| migration-state-tracker | `migration-state.json` | Module phases, decisions, risk scores, blockers |
| universal-code-graph | `dependency-graph.json` | Graph structure (source baseline) |
| behavioral-contract-extractor | `behavioral-contracts.json` | Per-function confidence, behavioral specs |
| work-item-generator | `work-items.json` | Work queue, model tier routing, cost estimates |

This skill produces output consumed by:
- **Stakeholders**: Primary communication artifact
- **Migration team**: Progress tracking, blocker identification, velocity monitoring
- **Project manager**: ETA projection, risk assessment, cost tracking
- **Executive sponsor**: High-level status dashboard

## Important Design Choices

**Why embedded JSON, not API calls?**

The dashboard must work offline and require zero infrastructure. Embedding the data makes it
truly self-contained and fast (no network latency). For large codebases (1000+ modules),
the HTML file is typically 5–10 MB, which is acceptable for modern browsers and easily
transferable.

**Why Canvas, not SVG or D3.js library?**

Canvas gives fine-grained control over node rendering and zoom performance. SVG scales poorly
beyond 500 nodes. The existing `dependency-graph-template.html` uses Canvas successfully;
we extend rather than replace.

**Why split-pane graphs instead of animation?**

Side-by-side static graphs are easier to understand than animated transitions. Stakeholders
can see both states simultaneously and compare architecture. Animation adds little value and
complicates the visualization.

**Why color-coded by phase, not by team or owner?**

Phase is the most important dimension for migration progress. Team affiliation is useful but
secondary. We show team as a node attribute (hover/detail panel) rather than primary coloring.

## Stakeholder Value

This skill delivers on the core promise of the migration suite: **transparent, measurable progress
toward production readiness.**

- **Project sponsors**: See overall progress bar, velocity trend, and ETA
- **Technical leads**: Understand architecture changes, identify risks, plan next phases
- **QA team**: See test coverage gaps, behavioral confidence, and recommended next modules
- **Operations**: Understand deployment readiness, identify dependencies, plan rollout
- **Product**: Know when features can be validated on the new stack

The dashboard is updated after every phase advancement and distributed to all stakeholders.
It's the single source of truth for "where are we?"

## Model Tier

**Haiku.** Dashboard generation reads pre-computed JSON files and produces HTML. Pure template rendering with data binding. No LLM reasoning required. Always use Haiku.

## References

- `ARCHITECTURE-migration-dashboard.md` — Detailed rendering pipeline and performance tuning
- `references/DASHBOARD-TEMPLATE.html` — Base template with all visualization code
- `references/dependency-graph-template.html` — Canvas force-directed graph implementation
- `SKILL.md` for migration-state-tracker — State file structure and semantics
- `SKILL.md` for universal-code-graph — Graph structure and language coverage
