#!/usr/bin/env python3
"""
Migration Dashboard Generator

Generates a self-contained HTML dashboard from JSON migration data.
Pure templating — zero LLM tokens.

Usage:
    python generate_dashboard.py --state migration-state.json \\
        [--gate-report gate-check-report.json] \\
        [--dependency-graph dependency-graph.json] \\
        [--work-items work-item-summary.json] \\
        [--output migration-dashboard.html] \\
        [--title "Migration Dashboard"]
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)


def load_json(path: Optional[str]) -> Optional[Dict[str, Any]]:
    """Load JSON file if path is provided."""
    if not path:
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load {path}: {e}", file=sys.stderr)
        return None


def extract_modules(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract module data from migration state."""
    modules = []
    if 'modules' in state:
        for module_name, module_data in state['modules'].items():
            module = {
                'name': module_name,
                'phase': module_data.get('phase', 0),
                'risk_score': module_data.get('risk_score', 0),
                'behavioral_confidence': module_data.get('behavioral_confidence', 0),
                'model_tier': module_data.get('model_tier', 'unknown'),
                'blockers': module_data.get('blockers', []),
                'findings': module_data.get('findings', {}),
            }
            modules.append(module)
    return modules


def compute_phase_distribution(modules: List[Dict[str, Any]]) -> Dict[int, int]:
    """Count modules by phase."""
    distribution = {i: 0 for i in range(6)}
    for module in modules:
        phase = module['phase']
        if phase in distribution:
            distribution[phase] += 1
    return distribution


def compute_completion_percentage(modules: List[Dict[str, Any]]) -> float:
    """Compute overall completion percentage (modules in phase 5)."""
    if not modules:
        return 0.0
    completed = sum(1 for m in modules if m['phase'] >= 5)
    return (completed / len(modules)) * 100


def compute_risk_distribution(modules: List[Dict[str, Any]]) -> Dict[str, int]:
    """Categorize modules by risk level."""
    risks = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
    for module in modules:
        score = module.get('risk_score', 0)
        if score >= 90:
            risks['critical'] += 1
        elif score >= 70:
            risks['high'] += 1
        elif score >= 40:
            risks['medium'] += 1
        else:
            risks['low'] += 1
    return risks


def get_phase_name(phase: int) -> str:
    """Map phase number to name."""
    names = {
        0: "Not Started",
        1: "Foundation",
        2: "Mechanical",
        3: "Semantic",
        4: "Verification",
        5: "Cutover",
    }
    return names.get(phase, "Unknown")


def get_phase_color(phase: int) -> str:
    """Map phase to color."""
    colors = {
        0: "#4a5568",  # gray (discovery)
        1: "#4cc9f0",  # light blue (foundation)
        2: "#4361ee",  # blue (mechanical)
        3: "#3a0ca3",  # dark blue (semantic)
        4: "#7209b7",  # purple (verification)
        5: "#f72585",  # pink (cutover)
    }
    return colors.get(phase, "#718096")


def get_risk_color(score: int) -> str:
    """Map risk score to color."""
    if score >= 90:
        return "#dc2626"  # red
    elif score >= 70:
        return "#f97316"  # orange
    elif score >= 40:
        return "#eab308"  # yellow
    else:
        return "#22c55e"  # green


def extract_gate_status(gate_report: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract gate status data."""
    if not gate_report:
        return {}

    gates = {}
    if 'gates' in gate_report:
        for phase, phase_data in gate_report['gates'].items():
            gates[phase] = {
                'status': phase_data.get('status', 'unknown'),
                'criteria': phase_data.get('criteria', []),
                'waivers': phase_data.get('waivers', []),
            }
    return gates


def extract_work_items(work_items_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract work item and cost data."""
    if not work_items_data:
        return {}

    tier_counts = {'haiku': 0, 'sonnet': 0, 'opus': 0}
    tier_costs = {'haiku': 0.0, 'sonnet': 0.0, 'opus': 0.0}

    if 'work_items' in work_items_data:
        for item in work_items_data['work_items']:
            tier = item.get('model_tier', 'sonnet').lower()
            if tier in tier_counts:
                tier_counts[tier] += 1
            if 'cost' in item and tier in tier_costs:
                tier_costs[tier] += item['cost']

    total_items = sum(tier_counts.values())
    total_cost = sum(tier_costs.values())

    return {
        'tier_counts': tier_counts,
        'tier_costs': tier_costs,
        'total_items': total_items,
        'total_cost': total_cost,
    }


def generate_html(
    title: str,
    state: Dict[str, Any],
    gate_report: Optional[Dict[str, Any]],
    dependency_graph: Optional[Dict[str, Any]],
    work_items_data: Optional[Dict[str, Any]],
) -> tuple[str, List[str]]:
    """Generate complete self-contained HTML dashboard."""

    modules = extract_modules(state)
    phase_dist = compute_phase_distribution(modules)
    completion = compute_completion_percentage(modules)
    risk_dist = compute_risk_distribution(modules)
    gates = extract_gate_status(gate_report)
    work_info = extract_work_items(work_items_data)

    sections_rendered = []

    # Build sections
    if state:
        sections_rendered.append('state')
    if gate_report:
        sections_rendered.append('gates')
    if dependency_graph:
        sections_rendered.append('dependencies')
    if work_items_data:
        sections_rendered.append('work_items')

    # Prepare phase distribution chart data
    phase_labels = [get_phase_name(i) for i in range(6)]
    phase_colors = [get_phase_color(i) for i in range(6)]
    phase_counts = [phase_dist[i] for i in range(6)]

    # Build module rows
    module_rows = []
    for module in sorted(modules, key=lambda m: m['name']):
        risk_color = get_risk_color(module['risk_score'])
        phase_name = get_phase_name(module['phase'])
        blockers_text = ', '.join(module['blockers']) if module['blockers'] else 'None'

        module_rows.append({
            'name': module['name'],
            'phase': phase_name,
            'phase_num': module['phase'],
            'phase_color': get_phase_color(module['phase']),
            'risk_score': module['risk_score'],
            'risk_color': risk_color,
            'behavioral_confidence': module['behavioral_confidence'],
            'model_tier': module['model_tier'],
            'blockers': blockers_text,
        })

    # Build gate rows
    gate_rows = []
    for phase, gate_info in gates.items():
        status = gate_info.get('status', 'unknown')
        status_badge = f'<span class="badge badge-{status}">{status.upper()}</span>'
        criteria = gate_info.get('criteria', [])
        criteria_text = '<br>'.join([f"• {c}" for c in criteria]) if criteria else 'None'
        waivers = gate_info.get('waivers', [])
        waivers_text = '<br>'.join([f"• {w}" for w in waivers]) if waivers else 'None'

        gate_rows.append({
            'phase': phase,
            'status': status_badge,
            'criteria': criteria_text,
            'waivers': waivers_text,
        })

    # Build work tier rows
    tier_rows = []
    if work_info.get('total_items', 0) > 0:
        for tier_name in ['haiku', 'sonnet', 'opus']:
            count = work_info['tier_counts'].get(tier_name, 0)
            cost = work_info['tier_costs'].get(tier_name, 0)
            pct = (count / work_info['total_items'] * 100) if work_info['total_items'] > 0 else 0
            cost_pct = (cost / work_info['total_cost'] * 100) if work_info['total_cost'] > 0 else 0

            tier_rows.append({
                'tier': tier_name.capitalize(),
                'count': count,
                'percentage': f"{pct:.1f}%",
                'cost': f"${cost:.2f}",
                'cost_pct': f"{cost_pct:.1f}%",
            })

    # Embed data as JSON
    embedded_data = {
        'title': title,
        'generated': datetime.now().isoformat(),
        'project': state.get('project_name', 'Unknown'),
        'status': state.get('status', 'in_progress'),
        'completion': completion,
        'phase_distribution': phase_dist,
        'risk_distribution': risk_dist,
        'modules': module_rows,
        'gates': gate_rows,
        'work_tiers': tier_rows,
    }

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #1a1a2e;
            color: #eee;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }}

        header {{
            margin-bottom: 30px;
            border-bottom: 2px solid #0f3460;
            padding-bottom: 20px;
        }}

        header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            color: #e94560;
        }}

        header .subtitle {{
            color: #aaa;
            font-size: 1em;
        }}

        .status-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-card {{
            background: #16213e;
            padding: 20px;
            border-left: 4px solid #0f3460;
            border-radius: 4px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }}

        .stat-card h3 {{
            font-size: 0.9em;
            text-transform: uppercase;
            color: #aaa;
            margin-bottom: 10px;
            letter-spacing: 1px;
        }}

        .stat-card .value {{
            font-size: 2em;
            font-weight: bold;
            color: #e94560;
        }}

        .progress-bar {{
            width: 100%;
            height: 12px;
            background: #0a0a14;
            border-radius: 6px;
            overflow: hidden;
            margin-top: 10px;
        }}

        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #4cc9f0, #7209b7, #f72585);
            transition: width 0.3s ease;
        }}

        .phase-chart {{
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 10px;
            margin: 20px 0;
        }}

        .phase-bar {{
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 15px 10px;
            background: #0a0a14;
            border-radius: 4px;
            border: 1px solid #16213e;
        }}

        .phase-bar .count {{
            font-size: 1.8em;
            font-weight: bold;
            margin-bottom: 5px;
        }}

        .phase-bar .label {{
            font-size: 0.85em;
            color: #aaa;
            text-align: center;
        }}

        .section {{
            margin-bottom: 40px;
        }}

        .section h2 {{
            font-size: 1.8em;
            color: #e94560;
            margin-bottom: 20px;
            border-bottom: 2px solid #0f3460;
            padding-bottom: 10px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            background: #16213e;
            border-radius: 4px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        }}

        thead {{
            background: #0f3460;
        }}

        th {{
            padding: 15px;
            text-align: left;
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85em;
            letter-spacing: 0.5px;
        }}

        td {{
            padding: 12px 15px;
            border-top: 1px solid #243245;
        }}

        tbody tr:hover {{
            background: #1f2f4a;
        }}

        .module-name {{
            font-weight: 500;
            color: #4cc9f0;
        }}

        .phase-badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 0.85em;
            font-weight: 600;
            color: white;
        }}

        .risk-score {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-weight: 600;
            color: white;
            font-size: 0.85em;
        }}

        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 0.8em;
            font-weight: 600;
            color: white;
        }}

        .badge-pass {{
            background: #22c55e;
        }}

        .badge-fail {{
            background: #dc2626;
        }}

        .badge-warning {{
            background: #f97316;
        }}

        .risk-low {{
            background: #22c55e;
        }}

        .risk-medium {{
            background: #eab308;
        }}

        .risk-high {{
            background: #f97316;
        }}

        .risk-critical {{
            background: #dc2626;
        }}

        .grid-2 {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 30px;
        }}

        .pie-chart-container {{
            background: #16213e;
            padding: 20px;
            border-radius: 4px;
            display: flex;
            flex-direction: column;
            align-items: center;
            min-height: 300px;
        }}

        .pie-chart {{
            width: 200px;
            height: 200px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 20px 0;
            position: relative;
            box-shadow: 0 4px 8px rgba(0,0,0,0.4);
        }}

        .pie-segment {{
            position: absolute;
            clip-path: polygon(50% 50%, 50% 0, 100% 0);
        }}

        .legend {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            width: 100%;
            margin-top: 20px;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 10px;
        }}

        .legend-color {{
            width: 20px;
            height: 20px;
            border-radius: 3px;
        }}

        .no-data {{
            text-align: center;
            padding: 40px;
            color: #aaa;
            font-style: italic;
        }}

        footer {{
            text-align: center;
            color: #666;
            font-size: 0.85em;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #243245;
        }}

        @media (max-width: 768px) {{
            .phase-chart {{
                grid-template-columns: repeat(3, 1fr);
            }}

            .status-row {{
                grid-template-columns: 1fr;
            }}

            header h1 {{
                font-size: 1.8em;
            }}

            table {{
                font-size: 0.9em;
            }}

            th, td {{
                padding: 10px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>{title}</h1>
            <div class="subtitle">
                Project: <strong id="project-name">-</strong> |
                Status: <strong id="status">-</strong> |
                Generated: <span id="generated">-</span>
            </div>
        </header>

        <!-- Progress Overview -->
        <div class="status-row">
            <div class="stat-card">
                <h3>Completion</h3>
                <div class="value"><span id="completion-pct">0</span>%</div>
                <div class="progress-bar">
                    <div class="progress-fill" id="completion-bar" style="width: 0%;"></div>
                </div>
            </div>

            <div class="stat-card">
                <h3>Total Modules</h3>
                <div class="value" id="total-modules">0</div>
            </div>

            <div class="stat-card">
                <h3>Critical Risk</h3>
                <div class="value" id="critical-count">0</div>
            </div>

            <div class="stat-card">
                <h3>Active Blockers</h3>
                <div class="value" id="blocker-count">0</div>
            </div>
        </div>

        <!-- Phase Distribution -->
        <div class="section">
            <h2>Phase Distribution</h2>
            <div class="phase-chart" id="phase-chart">
            </div>
        </div>

        <!-- Module Status Table -->
        <div class="section">
            <h2>Module Status</h2>
            <table id="module-table">
                <thead>
                    <tr>
                        <th>Module Name</th>
                        <th>Phase</th>
                        <th>Risk Score</th>
                        <th>Confidence</th>
                        <th>Model Tier</th>
                        <th>Blockers</th>
                    </tr>
                </thead>
                <tbody id="module-tbody">
                    <tr><td colspan="6" class="no-data">No modules available</td></tr>
                </tbody>
            </table>
        </div>

        <!-- Gate Status -->
        <div class="section" id="gate-section" style="display: none;">
            <h2>Gate Status</h2>
            <table id="gate-table">
                <thead>
                    <tr>
                        <th>Phase</th>
                        <th>Status</th>
                        <th>Criteria</th>
                        <th>Waivers</th>
                    </tr>
                </thead>
                <tbody id="gate-tbody">
                </tbody>
            </table>
        </div>

        <!-- Work Items & Cost -->
        <div class="section" id="work-section" style="display: none;">
            <h2>Model Tier Usage & Cost</h2>
            <div class="grid-2">
                <div class="pie-chart-container">
                    <h3>Distribution by Count</h3>
                    <table style="margin-top: 20px; width: 100%;">
                        <tbody id="tier-tbody">
                        </tbody>
                    </table>
                </div>
                <div class="pie-chart-container">
                    <h3>Cost Summary</h3>
                    <div style="text-align: center; margin: 20px 0;">
                        <div style="font-size: 0.9em; color: #aaa;">Total Cost</div>
                        <div style="font-size: 2.5em; font-weight: bold; color: #e94560;" id="total-cost">$0.00</div>
                        <div style="font-size: 0.9em; color: #aaa; margin-top: 10px;" id="total-items">0 items</div>
                    </div>
                </div>
            </div>
        </div>

        <footer>
            <p>Migration Dashboard • Self-contained HTML • No backend required</p>
        </footer>
    </div>

    <script type="application/json" id="dashboard-data">
{json.dumps(embedded_data, indent=2)}
    </script>

    <script>
        function initDashboard() {{
            const dataScript = document.getElementById('dashboard-data');
            const data = JSON.parse(dataScript.textContent);

            // Header
            document.getElementById('project-name').textContent = data.project;
            document.getElementById('status').textContent = data.status;
            document.getElementById('generated').textContent = new Date(data.generated).toLocaleString();

            // Stats
            document.getElementById('completion-pct').textContent = Math.round(data.completion);
            document.getElementById('completion-bar').style.width = data.completion + '%';
            document.getElementById('total-modules').textContent = data.modules.length;
            document.getElementById('critical-count').textContent = data.risk_distribution.critical || 0;

            const blockerCount = data.modules.reduce((sum, m) => {{
                return sum + (m.blockers && m.blockers !== 'None' ? 1 : 0);
            }}, 0);
            document.getElementById('blocker-count').textContent = blockerCount;

            // Phase Chart
            const phaseChart = document.getElementById('phase-chart');
            const phaseNames = ['Not Started', 'Foundation', 'Mechanical', 'Semantic', 'Verification', 'Cutover'];
            const phaseColors = ['#4a5568', '#4cc9f0', '#4361ee', '#3a0ca3', '#7209b7', '#f72585'];

            for (let i = 0; i < 6; i++) {{
                const count = data.phase_distribution[i] || 0;
                const bar = document.createElement('div');
                bar.className = 'phase-bar';
                bar.style.borderLeftColor = phaseColors[i];
                bar.innerHTML = `
                    <div class="count" style="color: ${{phaseColors[i]}};">${{count}}</div>
                    <div class="label">${{phaseNames[i]}}</div>
                `;
                phaseChart.appendChild(bar);
            }}

            // Module Table
            const moduleTable = document.getElementById('module-tbody');
            moduleTable.innerHTML = '';

            if (data.modules.length === 0) {{
                moduleTable.innerHTML = '<tr><td colspan="6" class="no-data">No modules available</td></tr>';
            }} else {{
                data.modules.forEach(mod => {{
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td class="module-name">${{mod.name}}</td>
                        <td>
                            <span class="phase-badge" style="background-color: ${{mod.phase_color}};">
                                ${{mod.phase}}
                            </span>
                        </td>
                        <td>
                            <span class="risk-score risk-${{getRiskLevel(mod.risk_score)}}" style="background-color: ${{mod.risk_color}};">
                                ${{mod.risk_score}}
                            </span>
                        </td>
                        <td>${{mod.behavioral_confidence || 0}}%</td>
                        <td>${{mod.model_tier}}</td>
                        <td><code style="background: #0a0a14; padding: 2px 6px; border-radius: 3px; font-size: 0.85em;">${{mod.blockers}}</code></td>
                    `;
                    moduleTable.appendChild(row);
                }});
            }}

            // Gate Table
            if (data.gates && data.gates.length > 0) {{
                document.getElementById('gate-section').style.display = 'block';
                const gateTable = document.getElementById('gate-tbody');
                gateTable.innerHTML = '';

                data.gates.forEach(gate => {{
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td><strong>Phase ${{gate.phase}}</strong></td>
                        <td>${{gate.status}}</td>
                        <td><small>${{gate.criteria}}</small></td>
                        <td><small>${{gate.waivers}}</small></td>
                    `;
                    gateTable.appendChild(row);
                }});
            }}

            // Work Items Table
            if (data.work_tiers && data.work_tiers.length > 0) {{
                document.getElementById('work-section').style.display = 'block';
                const tierTable = document.getElementById('tier-tbody');
                tierTable.innerHTML = '';

                data.work_tiers.forEach(tier => {{
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <tr>
                            <td style="padding: 8px 0;"><strong>${{tier.tier}}</strong></td>
                            <td style="text-align: right; padding: 8px 0;">${{tier.count}} items (${{tier.cost}})</td>
                        </tr>
                    `;
                    tierTable.appendChild(row);
                }});

                document.getElementById('total-cost').textContent = '$' + data.work_tiers.reduce((sum, t) => {{
                    return sum + parseFloat(t.cost.replace('$', ''));
                }}, 0).toFixed(2);

                document.getElementById('total-items').textContent = data.work_tiers.reduce((sum, t) => sum + t.count, 0) + ' items';
            }}
        }}

        function getRiskLevel(score) {{
            if (score >= 90) return 'critical';
            if (score >= 70) return 'high';
            if (score >= 40) return 'medium';
            return 'low';
        }}

        document.addEventListener('DOMContentLoaded', initDashboard);
    </script>
</body>
</html>
"""

    return html, sections_rendered


@log_execution
def main():
    parser = argparse.ArgumentParser(
        description='Generate a self-contained HTML migration dashboard'
    )
    parser.add_argument('-s', '--state', help='Path to migration-state.json')
    parser.add_argument('-g', '--gate-report', help='Path to gate-check-report.json')
    parser.add_argument('-d', '--dependency-graph', help='Path to dependency-graph.json')
    parser.add_argument('-w', '--work-items', help='Path to work-item-summary.json')
    parser.add_argument('-o', '--output', default='migration-dashboard.html',
                        help='Output file path (default: migration-dashboard.html)')
    parser.add_argument('--title', default='Migration Dashboard',
                        help='Dashboard title (default: "Migration Dashboard")')

    args = parser.parse_args()

    # Load inputs
    state = load_json(args.state)
    gate_report = load_json(args.gate_report)
    dependency_graph = load_json(args.dependency_graph)
    work_items_data = load_json(args.work_items)

    if not state:
        print("Error: --state is required", file=sys.stderr)
        sys.exit(1)

    # Generate HTML
    html, sections_rendered = generate_html(
        args.title,
        state,
        gate_report,
        dependency_graph,
        work_items_data,
    )

    # Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        f.write(html)

    # Output JSON summary
    result = {
        'status': 'success',
        'sections_rendered': sections_rendered,
        'output_file': str(output_path.absolute()),
        'modules_count': len(extract_modules(state)),
    }

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
