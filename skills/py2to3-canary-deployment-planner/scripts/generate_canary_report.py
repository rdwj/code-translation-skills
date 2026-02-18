#!/usr/bin/env python3
"""
Canary Deployment Report Generator

Reads canary-plan.json and generates human-readable markdown reports:
- canary-plan.md: Deployment architecture, ramp-up schedule, monitoring setup
- canary-rollback-runbook.md: Manual and automated rollback procedures

Usage:
    python3 generate_canary_report.py canary-plan.json \
        --output ./canary-deployment/

Output:
    canary-plan.md — Step-by-step cutover runbook
    canary-rollback-runbook.md — Rollback procedures
"""

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ── Helper Functions ──────────────────────────────────────────────────────────

def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def write_file(path: str, content: str) -> None:
    """Write content to file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


# ── Markdown Report Generation ────────────────────────────────────────────────

def generate_canary_plan_report(plan: Dict[str, Any]) -> str:
    """Generate comprehensive canary deployment plan markdown."""

    app_name = plan['metadata']['app_name']
    target_version = plan['metadata']['target_version']
    detected_infra = plan['detected_infrastructure']
    ramp_schedule = plan['ramp_schedule']['stages']
    rollback_config = plan['rollback_config']

    # Build detected infrastructure summary
    detected_list = [k.replace('_', ' ').title() for k, v in detected_infra.items() if v]
    detected_text = ', '.join(detected_list) if detected_list else 'None detected (configure manually)'

    report = f"""# Canary Deployment Plan: {app_name}

**Target Python Version**: {target_version}
**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Estimated Total Duration**: {plan['metadata']['estimated_total_duration_days']} days

---

## Executive Summary

This document describes the gradual rollout strategy for migrating **{app_name}** from **Python 2 to Python 3** in production using a **canary deployment** approach.

### What is a Canary Deployment?

A canary deployment runs Py2 and Py3 **side-by-side** in production, gradually shifting traffic from Py2 to Py3 while monitoring key metrics (error rates, latency, resource usage). If any metric degrades, the system automatically or manually rolls back to Py2.

### Key Benefits

1. **Low Risk**: Real traffic and data expose issues tests miss
2. **Visibility**: Metrics show exact where differences emerge
3. **Automation**: Automatic rollback if error rates spike
4. **Gradual Confidence**: Each stage confirms Py3 stability

---

## Infrastructure Overview

### Detected Infrastructure

- **Kubernetes**: {'✓ Detected' if detected_infra['kubernetes'] else '✗ Not detected'}
- **Docker Compose**: {'✓ Detected' if detected_infra['docker_compose'] else '✗ Not detected'}
- **Dockerfile**: {'✓ Detected' if detected_infra['dockerfile'] else '✗ Not detected'}
- **Systemd**: {'✓ Detected' if detected_infra['systemd'] else '✗ Not detected'}
- **Supervisor**: {'✓ Detected' if detected_infra['supervisor'] else '✗ Not detected'}
- **Ansible**: {'✓ Detected' if detected_infra['ansible'] else '✗ Not detected'}
- **Terraform**: {'✓ Detected' if detected_infra['terraform'] else '✗ Not detected'}

### Deployment Configurations Generated

{generate_infra_configs_section(plan)}

---

## Ramp-up Schedule

This schedule gradually increases traffic to Py3 over time. **Each stage must complete its success criteria before advancing.**

### Stage Timeline

| Stage | Py3 Traffic | Duration | Success Criteria | Go/No-Go Decision |
|-------|------------|----------|------------------|-------------------|
"""

    for i, stage in enumerate(ramp_schedule, 1):
        report += f"| {i}. **{stage['name']}** | {stage['py3_traffic_pct']}% | {stage['duration_hours']}h | {stage['success_criteria']} | [Decision Gate {i}] |\n"

    report += f"""
### Stage Descriptions

"""

    for stage in ramp_schedule:
        report += f"""#### Stage: {stage['name']}

**Traffic Split**: {stage['py3_traffic_pct']}% to Py3, {100-stage['py3_traffic_pct']}% to Py2
**Duration**: {stage['duration_hours']} hours
**Success Criteria**: {stage['success_criteria']}

**Automated Checks**:
"""
        for check in stage.get('automated_checks', []):
            report += f"- {check}\n"

        report += f"""
**Actions**:
1. Deploy configuration changes (see deployment configs)
2. Monitor metrics dashboard (Grafana)
3. Check alert rules in Prometheus
4. Review logs for errors/warnings
5. Approve advancement to next stage

**Advance to Next Stage When**:
- All success criteria are met
- No critical alerts are firing
- Team has reviewed logs and metrics
- Stakeholders approve advancement

---

"""

    report += f"""## Monitoring Setup

### Metrics to Track

The following metrics are collected and compared between Py2 and Py3:

1. **Error Rate**: Percentage of 5xx responses
   - Target: Py3 error rate ≤ Py2 error rate + threshold
   - Threshold: {rollback_config['automatic_triggers']['error_rate_exceeded']['threshold']}

2. **Latency (p99)**: 99th percentile response time
   - Target: Py3 p99 ≤ 2x Py2 p99 in early stages
   - Target: Within 10% of Py2 in final stage

3. **Request Throughput**: Requests per second
   - Target: Stable or increasing over time
   - Indicator: Py3 can handle assigned traffic

4. **Memory Usage**: Per-instance memory consumption
   - Target: Stable, no memory leaks
   - Alert: > 90% of limit

5. **CPU Usage**: Per-instance CPU consumption
   - Target: Similar to Py2
   - Alert: > 80% sustained

6. **Health Checks**: Service health status
   - Target: All health checks pass
   - Alert: 3 consecutive failures trigger rollback

### Prometheus Alert Rules

The following alerts are configured in `prometheus-alerts.yaml`:

- `Py3ErrorRateSpike` — Fires if Py3 error rate exceeds Py2 by 50% or > 1%
- `Py3LatencySpike` — Fires if Py3 p99 > 2x Py2 p99 for 10 minutes
- `Py3HealthCheckFailure` — Fires if Py3 health checks fail
- `Py3MemoryUsageHigh` — Fires if memory > 90% of limit
- `Py3CpuUsageHigh` — Fires if CPU > 80% sustained
- `Py2Py3ResponseTimeDivergence` — Fires if response times diverge > 20%

### Grafana Dashboard

A Grafana dashboard (`monitoring-dashboard.json`) is included showing:

- **Error Rates**: Py2 vs. Py3 side-by-side
- **Response Times**: p50, p95, p99 latency comparison
- **Request Rates**: Traffic distribution over time
- **Resource Usage**: Memory and CPU comparison
- **Health Status**: Both versions' health indicators

---

## Automatic Rollback Triggers

The system will **automatically rollback** to 100% Py2 if:

### Error Rate Exceeded

- **Condition**: Py3 error rate > {rollback_config['automatic_triggers']['error_rate_exceeded']['threshold']}
- **Window**: {rollback_config['automatic_triggers']['error_rate_exceeded']['window']}
- **Action**: Immediately set traffic to 0% Py3

### Latency Spike

- **Condition**: Py3 p99 latency > 2x Py2 baseline for {rollback_config['automatic_triggers']['latency_spike']['window']}
- **Action**: Immediately set traffic to 0% Py3

### Health Check Failure

- **Condition**: 3 consecutive health check failures on Py3
- **Action**: Immediately set traffic to 0% Py3

### Memory Exhaustion

- **Condition**: Memory usage > 90% of allocated limit
- **Action**: Immediately set traffic to 0% Py3

---

## Cutover Runbook (Step-by-Step)

### Pre-Deployment (Day 0)

1. **Prepare Py3 Build**
   - Build Docker image with Python {target_version}
   - Tag as `myregistry/myapp:py3`
   - Push to registry

2. **Configure Monitoring**
   - Import `monitoring-dashboard.json` into Grafana
   - Import `prometheus-alerts.yaml` into Prometheus
   - Verify all alerts are active

3. **Prepare Load Balancer**
   - Review load balancer config (see generated files)
   - Stage configuration (don't apply yet)
   - Test configuration in dev environment

4. **Notify Team**
   - Announce deployment schedule
   - Ensure on-call team is aware
   - Establish escalation contacts

### Stage 1: Canary 1% (Day 1-2)

1. **Apply Deployment Configs**
   - Deploy Py3 with 1 replica (K8s) or 1 process (Systemd)
   - Apply load balancer config: 1% to Py3, 99% to Py2
   - Verify both services are healthy

2. **Monitor Closely**
   - Watch dashboard every hour
   - Check alerts every 30 minutes
   - Review logs for errors

3. **Success Criteria Check**
   - Error rate < 0.1%
   - Latency stable
   - Health checks passing

4. **Advance Decision**
   - Team reviews metrics
   - Stakeholders approve advancement
   - Proceed to Stage 2

### Stage 2: Canary 5% (Day 3-4)

1. **Update Traffic Split**
   - Increase Py3 traffic to 5%
   - Scale up Py3 replicas to 2-3

2. **Monitor Carefully**
   - Watch for latency changes
   - Monitor memory and CPU
   - Check for log anomalies

3. **Success Criteria Check**
   - Error rate < 0.5%
   - Latency within 1.5x baseline
   - Memory usage stable

4. **Advance Decision**
   - Review 48-hour metrics
   - Approve to Stage 3

### Stage 3: Canary 25% (Day 5-7)

1. **Update Traffic Split**
   - Increase Py3 traffic to 25%
   - Ensure adequate Py3 replicas

2. **Expand Monitoring**
   - Check database query performance
   - Monitor external API calls
   - Verify caching behavior

3. **Success Criteria Check**
   - Error rate < 0.5%
   - Latency within 2x baseline
   - No unexpected errors in logs

4. **Advance Decision**
   - Team review with domain experts
   - Approve to Stage 4

### Stage 4: Canary 50% (Day 8-14)

1. **Update Traffic Split**
   - Increase Py3 traffic to 50%
   - Equal load on both versions

2. **Week-Long Soak**
   - Run for 7 full days
   - Observe daily patterns
   - Check end-of-day batch jobs
   - Verify weekly jobs if applicable

3. **Success Criteria Check**
   - All metrics within 10% of baseline
   - No degradation trends
   - Team confidence high

4. **Advance Decision**
   - Executive sign-off required
   - Team celebration
   - Proceed to Stage 5

### Stage 5: Full Cutover (Day 15+)

1. **Final Traffic Split**
   - Set Py3 traffic to 100%
   - Prepare to remove Py2

2. **Extended Soak Period**
   - Run Py3 only for 1-2 weeks
   - Monitor all metrics
   - Ensure stability

3. **Post-Deployment Tasks**
   - Decommission Py2 services
   - Archive Py2 code
   - Celebrate with team!

---

## Kubernetes-Specific Deployment

If Kubernetes detected:

### 1. Create Namespaces and ConfigMaps

```bash
kubectl create namespace canary
kubectl create configmap {app_name}-config-py2 --from-file=config/ -n canary
kubectl create configmap {app_name}-config-py3 --from-file=config/ -n canary
```

### 2. Deploy Both Versions

```bash
kubectl apply -f k8s-deployment-py2.yaml -n canary
kubectl apply -f k8s-deployment-py3.yaml -n canary
kubectl apply -f k8s-hpa-py2.yaml -n canary
kubectl apply -f k8s-hpa-py3.yaml -n canary
```

### 3. Configure Traffic Splitting

**If using Istio:**
```bash
kubectl apply -f k8s-virtual-service.yaml -n canary
```

**If using Nginx Ingress:**
```bash
kubectl apply -f k8s-ingress.yaml -n canary
```

### 4. Adjust Traffic (Per Stage)

**Using Istio** (edit k8s-virtual-service.yaml weights):
```bash
kubectl patch vs {app_name}-canary -n canary --type merge -p \
  '{{\"spec\":{{\"http\":[{{\"route\":[{{\"destination\":{{\"host\":\"{app_name}-py2\"}},\"weight\":95}},{{\"destination\":{{\"host\":\"{app_name}-py3\"}},\"weight\":5}}]}}]}}}}'
```

**Using Nginx Ingress** (edit k8s-ingress.yaml):
```bash
kubectl patch ing {app_name}-canary -n canary --type merge -p \
  '{{\"metadata\":{{\"annotations\":{{\"nginx.ingress.kubernetes.io/canary-weight\":\"5\"}}}}}}'
```

---

## Docker Compose-Specific Deployment

If Docker Compose detected:

### 1. Build Images

```bash
docker build -t myregistry/myapp:py2 -f Dockerfile.py2 .
docker build -t myregistry/myapp:py3 -f Dockerfile.py3 .
docker push myregistry/myapp:py2
docker push myregistry/myapp:py3
```

### 2. Start Services

```bash
docker-compose -f docker-compose-canary.yml up -d
```

### 3. Adjust Load Balancer Weights (Per Stage)

Edit `haproxy-canary.cfg`, update server weights:

```
backend canary_backend
    balance roundrobin
    server py2 {app_name}-py2:8080 check weight 99
    server py3 {app_name}-py3:8080 check weight 1
```

Then reload:
```bash
docker exec {app_name}-lb haproxy -f /usr/local/etc/haproxy/haproxy.cfg -p /var/run/haproxy.pid -sf $(cat /var/run/haproxy.pid)
```

---

## Systemd-Specific Deployment

If systemd detected:

### 1. Deploy Both Services

```bash
sudo cp {app_name}-py2.service /etc/systemd/system/
sudo cp {app_name}-py3.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start {app_name}-py2.service {app_name}-py3.service
```

### 2. Configure Load Balancer

```bash
sudo cp haproxy-canary.cfg /etc/haproxy/
sudo systemctl reload haproxy
```

### 3. Adjust Traffic Weights (Per Stage)

Edit `/etc/haproxy/haproxy.cfg`, update backend weights, then:

```bash
sudo systemctl reload haproxy
```

---

## Rollback Procedures

See `canary-rollback-runbook.md` for detailed rollback instructions.

---

## Troubleshooting

### "Py3 keeps crashing"

1. Check Py3 logs for import errors
2. Verify all dependencies are installed
3. Check Python version compatibility
4. Review canary-rollback-runbook.md for rollback steps

### "Error rate is high but stable"

1. Verify this is expected from code changes
2. Confirm Py2 and Py3 have same configuration
3. Check for timing-dependent failures
4. Run targeted tests on Py3 subset of traffic

### "Latency is higher on Py3"

1. Profile Py3 code for hot paths
2. Check for inefficient imports or initializations
3. Compare dependency versions
4. Review garbage collection settings

### "Memory is growing on Py3"

1. Check for memory leaks (use memory profiler)
2. Verify cache implementations are compatible
3. Review long-lived connection handling
4. Check for unbounded data structures

---

## Success and Next Steps

### Post-Deployment

Once Stage 5 (Full Cutover) is complete and stable:

1. **Archive Py2 Code**
   - Tag final Py2 version in Git
   - Move to separate branch/repo if needed
   - Document historical location

2. **Cleanup**
   - Remove Py2 Docker images from registry
   - Decommission Py2 Kubernetes resources
   - Shutdown Py2 systemd services

3. **Modernization**
   - Remove compatibility shims (use Compatibility Shim Remover skill)
   - Upgrade to latest Python 3.x patch version
   - Modernize deprecated patterns
   - Optimize Py3-specific features

4. **Team Learning**
   - Document lessons learned
   - Share monitoring setup with other teams
   - Contribute canary deployment patterns to organization

---

## References

- Skill: Canary Deployment Planner (this document)
- Skill: Compatibility Shim Remover (remove dual-compatibility code)
- Generated Config Files:
  - `prometheus-alerts.yaml` — Alert rules
  - `monitoring-dashboard.json` — Grafana dashboard
  - `k8s-*.yaml` — Kubernetes manifests (if K8s detected)
  - `docker-compose-canary.yml` — Docker Compose (if Docker detected)
  - `*-py*.service` — Systemd units (if systemd detected)
  - `haproxy-canary.cfg` — Load balancer config

---

*Generated by Canary Deployment Planner Skill*
*For questions or issues, contact the Python 3 migration team*
"""

    return report


def generate_rollback_runbook(plan: Dict[str, Any]) -> str:
    """Generate detailed rollback procedures."""

    app_name = plan['metadata']['app_name']
    rollback_config = plan['rollback_config']
    stages = plan['ramp_schedule']['stages']

    report = f"""# Canary Deployment Rollback Runbook

**Application**: {app_name}
**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## When to Rollback

Rollback is **automatic** if:

"""

    for trigger, details in rollback_config['automatic_triggers'].items():
        report += f"- **{trigger}**: {details.get('condition', details.get('metric', 'condition'))}\n"

    report += f"""

Rollback is **manual** if:

"""

    for trigger in rollback_config['manual_triggers']:
        report += f"- {trigger}\n"

    report += f"""

---

## Automatic Rollback

When automatic rollback triggers:

1. **Alert fires** in Prometheus
2. **Operator notified** via alert channel
3. **Traffic redirects** to 100% Py2 (load balancer config change)
4. **Py3 instances** continue running (for log inspection)
5. **All-hands update** sent within 15 minutes

### Automatic Rollback Timing

| Trigger | Detection | Rollback Action | Message |
|---------|-----------|-----------------|---------|
| Error rate spike | 5 minutes | Immediate | "Py3 error rate > threshold" |
| Latency spike | 10 minutes | Immediate | "Py3 latency 2x higher" |
| Health check failure | 1 minute | Immediate | "Py3 health check failed" |
| Memory exhaustion | 5 minutes | Immediate | "Py3 memory > 90%" |

---

## Manual Rollback (Step-by-Step)

### Quick Rollback (< 2 minutes)

**Goal**: Redirect all traffic back to Py2 immediately

#### Kubernetes

**Using Istio:**
```bash
kubectl patch vs {app_name}-canary -n canary --type merge -p \
  '{{\"spec\":{{\"http\":[{{\"route\":[{{\"destination\":{{\"host\":\"{app_name}-py2\"}},\"weight\":100}},{{\"destination\":{{\"host\":\"{app_name}-py3\"}},\"weight\":0}}]}}]}}}}'

# Verify
kubectl get vs {app_name}-canary -n canary -o yaml | grep weight
```

**Using Nginx Ingress:**
```bash
kubectl patch ing {app_name}-canary -n canary --type merge -p \
  '{{\"metadata\":{{\"annotations\":{{\"nginx.ingress.kubernetes.io/canary-weight\":\"0\"}}}}}}'

# Verify
kubectl get ing {app_name}-canary -n canary -o yaml
```

#### Docker Compose

```bash
# Edit haproxy-canary.cfg, change weights:
# server py2 {app_name}-py2:8080 check weight 100
# server py3 {app_name}-py3:8080 check weight 0

docker exec {app_name}-lb haproxy -f /usr/local/etc/haproxy/haproxy.cfg \\
  -p /var/run/haproxy.pid -sf $(cat /var/run/haproxy.pid)

# Verify
docker logs {app_name}-lb | tail -10
```

#### Systemd/Bare Metal

```bash
# Edit /etc/haproxy/haproxy.cfg:
# server py2 {app_name}-py2:8080 check weight 100
# server py3 {app_name}-py3:8080 check weight 0

sudo systemctl reload haproxy

# Verify
curl http://localhost:8080/health
```

### Full Rollback (< 5 minutes)

**Goal**: Complete traffic redirect + pause Py3

#### Kubernetes

```bash
# 1. Redirect traffic (see Quick Rollback above)

# 2. Pause Py3 Deployment
kubectl patch deployment {app_name}-py3 -n canary -p \
  '{{\"spec\":{{\"paused\":true}}}}'

# 3. Delete Py3 pods to force re-creation upon unpause
kubectl delete pods -l app={app_name},version=py3 -n canary

# 4. Verify only Py2 pods running
kubectl get pods -n canary -l app={app_name}

# 5. Check all traffic is going to Py2
kubectl logs -f deployment/{app_name}-py2 -n canary | grep -E 'ERROR|5[0-9][0-9]'
```

#### Docker Compose

```bash
# 1. Redirect traffic (see Quick Rollback above)

# 2. Stop Py3 container
docker-compose -f docker-compose-canary.yml stop {app_name}-py3

# 3. Verify only Py2 running
docker-compose -f docker-compose-canary.yml ps

# 4. Check logs
docker logs {app_name}-py2 | grep -E 'ERROR|5[0-9][0-9]'
```

#### Systemd

```bash
# 1. Redirect traffic (see Quick Rollback above)

# 2. Stop Py3 service
sudo systemctl stop {app_name}-py3.service

# 3. Verify status
sudo systemctl status {app_name}-py2.service {app_name}-py3.service

# 4. Check logs
sudo journalctl -u {app_name}-py2.service -n 50
```

---

## Rollback Decision Tree

```
Is traffic affected? (errors, timeouts, etc.)
├─ Yes → Quick Rollback (< 2 minutes)
├─ Investigate root cause while rolled back
│  ├─ Py3 code bug? → Fix and redeploy
│  ├─ Environment issue? → Fix infrastructure and retry
│  ├─ Dependency incompatibility? → Update dependencies
│  └─ Cannot fix quickly? → Full Rollback (< 5 minutes)
└─ No → Investigate metrics, may not need rollback
   ├─ High resource usage? → Scale up Py3 and retry
   ├─ Gradual latency increase? → Profile and optimize
   └─ Isolated errors? → Investigate logs for context
```

---

## Post-Rollback Actions (Immediate)

1. **Notify Stakeholders**
   - Send alert to on-call team
   - Update status page (if applicable)
   - Post to incident channel

2. **Secure the Scene**
   - Save logs from Py3 pods/containers
   - Capture metrics snapshot
   - Do NOT delete Py3 yet (need logs for investigation)

3. **Initial Investigation**
   - Review last 100 error logs from Py3
   - Check Prometheus metrics for anomalies
   - Review Py3 version differences vs. Py2

4. **Incident Timeline**
   - Note when issue started
   - Note when rollback occurred
   - Track mean time to recovery (MTTR)

---

## Post-Rollback Analysis (Next Day)

### Log Review

```bash
# Kubernetes
kubectl logs deployment/{app_name}-py3 -n canary \\
  --timestamps=true --since=1h > py3-logs.txt

# Docker
docker logs {app_name}-py3 > py3-logs.txt

# Systemd
sudo journalctl -u {app_name}-py3.service -n 1000 > py3-logs.txt
```

### Metrics Analysis

1. Open Grafana dashboard
2. Set time range to incident window
3. Identify metric divergence point
4. Screenshot for postmortem

### Error Pattern Analysis

1. Extract error messages from logs
2. Group by error type
3. Identify common thread
4. Search code for pattern

---

## Common Rollback Scenarios

### Scenario 1: Database Query Errors

**Symptom**: Py3 version fails on specific database queries

**Investigation**:
```bash
# Check error logs
grep "DatabaseError\\|QueryError" py3-logs.txt

# Compare query handling
grep -n "execute\\|query" app/db.py | head -20
```

**Remediation**:
1. Analyze query differences (string encoding, parameter passing)
2. Check if database driver version is compatible
3. Test query with same Py3 version locally
4. Fix query handling and redeploy

### Scenario 2: Memory Leak

**Symptom**: Py3 memory usage climbs over time, eventually crashes

**Investigation**:
```bash
# Check memory trend in Grafana
# Look for sustained upward slope

# Check Py3 logs for warnings
grep "Memory\\|Allocation" py3-logs.txt
```

**Remediation**:
1. Enable Python memory profiler on Py3
2. Identify which objects are not being freed
3. Check for circular references, unclosed connections
4. Fix memory leak and redeploy

### Scenario 3: Third-Party API Incompatibility

**Symptom**: Py3 calls to external API fail, Py2 succeeds

**Investigation**:
```bash
# Check API error logs
grep "ConnectionError\\|AuthenticationError" py3-logs.txt

# Compare HTTP client code
grep -A 5 "requests\\|urllib" app/api.py
```

**Remediation**:
1. Check if API client library version is Py3 compatible
2. Test API call with Py3 version locally
3. Update API client to Py3-compatible version
4. Test and redeploy

### Scenario 4: Import or Dependency Error

**Symptom**: Py3 fails to import modules, crashes on startup

**Investigation**:
```bash
# Check startup errors
grep "ImportError\\|ModuleNotFoundError" py3-logs.txt
```

**Remediation**:
1. Review requirements.txt or setup.py
2. Check if all dependencies are Py3 compatible
3. Test imports locally with Py3
4. Update or replace incompatible dependencies
5. Rebuild and redeploy

---

## Preventing Future Rollbacks

### Pre-Deployment Checklist

- [ ] All unit tests pass on Py3
- [ ] All integration tests pass on Py3
- [ ] Code review completed by Py3 expert
- [ ] Performance profiling done (no obvious regressions)
- [ ] Dependency versions verified as compatible
- [ ] Database schema compatible with both Py2 and Py3
- [ ] Configuration files support both versions
- [ ] Monitoring setup complete and verified

### Testing Strategy

1. **Unit Tests**: Run on both Py2 and Py3
2. **Integration Tests**: Against staging environment
3. **Load Tests**: Py3 at expected stage traffic level
4. **Soak Tests**: Py3 running for several hours
5. **Chaos Tests**: Kill Py3 pods, verify recovery
6. **Comparison Tests**: Run same traffic against Py2 and Py3, compare results

### Monitoring Best Practices

1. **Structured Logging**: JSON format for easy filtering
2. **Version Tags**: All logs tagged with `version=py2` or `version=py3`
3. **Baselines**: Establish Py2 baseline before Py3 deployment
4. **Dashboards**: Side-by-side Py2/Py3 metrics always visible
5. **Alerting**: Conservative thresholds (false positives OK)

---

## Escalation

### Level 1: On-Call Engineer (15 minutes)

- Acknowledge alert
- Verify automated rollback completed
- Begin initial investigation
- Update incident channel

### Level 2: Team Lead (30 minutes)

- Review incident details
- Assess severity
- Decide: retry after fix or complete rollback
- Communicate timeline to stakeholders

### Level 3: Engineering Manager (60 minutes)

- Review root cause analysis
- Approve timeline for next rollback attempt
- Decide if alternate approach needed (e.g., more testing, slower ramp)
- Communicate to business stakeholders

---

## Post-Incident Review

After any rollback, schedule a blameless postmortem:

1. **Timeline**: When did issue occur? When was it detected? When was it fixed?
2. **Root Cause**: What exactly went wrong?
3. **Detection**: How was the issue caught?
4. **Prevention**: How do we prevent this in future?
5. **Detection Improvement**: Can we catch this faster next time?

### Action Items Template

- [ ] Fix code issue (assign owner, target date)
- [ ] Improve test coverage (specific test case)
- [ ] Update runbook (document lesson learned)
- [ ] Improve monitoring (add alert or dashboard)
- [ ] Schedule follow-up (verify fix in next rollback attempt)

---

## References

- Canary Deployment Plan: `canary-plan.md`
- Monitoring Dashboard: `monitoring-dashboard.json`
- Alert Rules: `prometheus-alerts.yaml`
- Deployment Configs: `k8s-*.yaml`, `docker-compose-canary.yml`, `*.service`

---

*This runbook should be reviewed and updated after each deployment cycle.*
*For questions or updates, contact the Python 3 migration team.*
"""

    return report


def generate_infra_configs_section(plan: Dict[str, Any]) -> str:
    """Generate infrastructure configs section."""
    infra_configs = plan['infrastructure_configs']

    if not infra_configs:
        return "No deployment configurations generated (no infrastructure detected)."

    section = ""

    if 'kubernetes' in infra_configs:
        section += """### Kubernetes

Generated files:
- `k8s-deployment-py2.yaml` — Python 2 Deployment and Service
- `k8s-deployment-py3.yaml` — Python 3 Deployment and Service
- `k8s-virtual-service.yaml` — Istio VirtualService for traffic splitting
- `k8s-ingress.yaml` — Nginx Ingress with canary annotations
- `k8s-hpa-py2.yaml` — HorizontalPodAutoscaler for Py2
- `k8s-hpa-py3.yaml` — HorizontalPodAutoscaler for Py3

"""

    if 'docker_compose' in infra_configs:
        section += """### Docker Compose

Generated files:
- `docker-compose-canary.yml` — Dual services + load balancer
- `haproxy-canary.cfg` — HAProxy load balancer configuration

"""

    if 'systemd' in infra_configs:
        section += """### Systemd

Generated files:
- `{app_name}-py2.service` — Python 2 systemd unit
- `{app_name}-py3.service` — Python 3 systemd unit
- `haproxy-canary.cfg` — HAProxy load balancer configuration

"""

    return section


# ── Main Entry Point ──────────────────────────────────────────────────────────

@log_execution
def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate canary deployment reports from plan"
    )
    parser.add_argument('plan_file', help='Path to canary-plan.json')
    parser.add_argument('--output', default='.',
                       help='Output directory for reports')

    args = parser.parse_args()

    if not os.path.exists(args.plan_file):
        print(f"Error: {args.plan_file} not found", file=sys.stderr)
        sys.exit(1)

    print(f"Loading plan from {args.plan_file}...")
    plan = load_json(args.plan_file)

    # Generate reports
    print("Generating canary-plan.md...")
    canary_report = generate_canary_plan_report(plan)
    write_file(os.path.join(args.output, 'canary-plan.md'), canary_report)

    print("Generating canary-rollback-runbook.md...")
    rollback_report = generate_rollback_runbook(plan)
    write_file(os.path.join(args.output, 'canary-rollback-runbook.md'), rollback_report)

    print(f"✓ Reports generated in {args.output}")
    print(f"  - canary-plan.md ({len(canary_report)} chars)")
    print(f"  - canary-rollback-runbook.md ({len(rollback_report)} chars)")


if __name__ == '__main__':
    main()
