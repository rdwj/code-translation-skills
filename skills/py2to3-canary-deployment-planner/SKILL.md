---
name: py2to3-canary-deployment-planner
description: >
  Plans gradual rollout from Python 2→3 in production with infrastructure-aware configurations.
  Generates deployment manifests for running side-by-side services with intelligent traffic routing.
  Includes monitoring setup, ramp-up schedules, and automatic rollback triggers. Use this skill
  when you need to plan production cutover, design canary deployments, set up traffic splitting,
  configure monitoring for Py2/Py3 comparison, or establish rollback procedures. Trigger on
  "plan canary deployment," "gradual rollout strategy," "setup traffic splitting," "compare Py2 vs Py3,"
  or "production cutover plan."
---

# Skill 5.1: Canary Deployment Planner

## Why Canary Deployments Matter for Py2→Py3 Migration

A direct cutover from Python 2 to Python 3 is risky because:

- **Unexpected runtime differences**: Code may pass all tests but behave differently in production (dependencies, configuration, environment specifics).
- **Performance regressions**: Py3 may have different performance characteristics (string handling, memory usage, GIL behavior).
- **Data compatibility**: Database queries, serialization, file I/O may have subtle differences in Py3.
- **Third-party dependency versions**: Production dependencies may have different behavior in Py3.
- **Traffic patterns**: Real traffic reveals edge cases tests miss (rare request types, unusual data, concurrency patterns).

A **canary deployment** mitigates these risks by:

1. Running Py2 and Py3 **side-by-side** in production.
2. Routing a **small percentage of traffic** to Py3 initially (1%, 5%, 25%, 50%, 100%).
3. **Monitoring for errors, latency, and anomalies** during each stage.
4. **Automatic rollback** if error rates exceed thresholds.
5. **Gradual ramp-up** to full Py3 only when metrics are healthy.

This skill generates the infrastructure code (Kubernetes, Docker Compose, systemd, etc.) and monitoring setup needed to execute this strategy safely.

---

## Inputs

| Input | Source | Notes |
|-------|--------|-------|
| **codebase_path** | User | Root directory of Python 2 codebase |
| **--target-version** | User | Python 3.x target (3.9, 3.11, 3.12, 3.13); default: 3.11 |
| **--output** | User | Output directory for deployment configs (default: current dir) |
| **--infra-type** | User | Infrastructure type: `auto`, `kubernetes`, `docker-compose`, `bare-metal`; default: `auto` |
| **--rollback-threshold** | User | Error rate threshold (%) to trigger rollback; default: 1.0 |

---

## Outputs

All outputs go into the `--output` directory:

| File | Format | Purpose |
|------|--------|---------|
| `canary-plan.json` | JSON | Master deployment plan with stages, configs, and monitoring rules |
| `canary-plan.md` | Markdown | Human-readable cutover runbook and architecture |
| `k8s-deployment-py2.yaml` | Kubernetes YAML | Py2 Deployment/Service (if K8s detected) |
| `k8s-deployment-py3.yaml` | Kubernetes YAML | Py3 Deployment/Service (if K8s detected) |
| `k8s-virtual-service.yaml` | Kubernetes YAML | Istio VirtualService for traffic splitting (if Istio) |
| `k8s-ingress.yaml` | Kubernetes YAML | Nginx Ingress with canary annotations (if not Istio) |
| `docker-compose-canary.yml` | Docker Compose | Dual services + load balancer (if Docker Compose detected) |
| `systemd-py2.service` | Systemd Unit | Py2 service configuration (if bare metal) |
| `systemd-py3.service` | Systemd Unit | Py3 service configuration (if bare metal) |
| `haproxy-canary.cfg` | HAProxy Config | Load balancer setup (if bare metal) |
| `prometheus-alerts.yaml` | Prometheus | Alerting rules for error rate, latency, health |
| `monitoring-dashboard.json` | Grafana JSON | Dashboard for Py2 vs. Py3 metrics comparison |
| `canary-rollback-runbook.md` | Markdown | Step-by-step rollback procedures |

---

## Workflow

### Step 1: Detect Infrastructure Type

Run the main planning script:

```bash
python3 scripts/plan_canary.py <codebase_path> \
    --target-version 3.11 \
    --infra-type auto \
    --output ./canary-deployment/ \
    --rollback-threshold 1.0
```

The script scans for:
- Kubernetes manifests (`*.yaml` with `apiVersion`)
- `docker-compose.yml` files
- `Dockerfile` (Docker images)
- `Procfile` (Heroku/systemd)
- `supervisord.conf` (systemd alternative)
- Ansible playbooks (infrastructure as code)
- Terraform files (`*.tf` files)

### Step 2: Generate Deployment Configs

For each detected infrastructure, generate parallel deployment configurations:

**Kubernetes**:
- Two separate Deployments (py2-app, py3-app) with identical specs except image/version
- Service exposing both deployments
- Istio VirtualService (if Istio installed) or Nginx Ingress with canary annotations
- HorizontalPodAutoscaler for both versions

**Docker Compose**:
- Dual services: `app-py2` and `app-py3`
- Load balancer service (HAProxy or Nginx) with traffic splitting config
- Shared volumes and networks

**Bare Metal/Systemd**:
- Two systemd unit files (py2-app.service, py3-app.service)
- HAProxy/Nginx frontend with canary routing configuration
- Log aggregation hints (structured logging)

### Step 3: Generate Ramp-up Schedule

Create a multi-stage canary schedule with success criteria for each stage:

```json
{
  "stages": [
    {
      "name": "canary-1pct",
      "py3_traffic_pct": 1,
      "duration_hours": 24,
      "success_criteria": "error_rate < 0.1%"
    },
    {
      "name": "canary-5pct",
      "py3_traffic_pct": 5,
      "duration_hours": 48,
      "success_criteria": "error_rate < 0.5%"
    },
    {
      "name": "canary-25pct",
      "py3_traffic_pct": 25,
      "duration_hours": 72,
      "success_criteria": "error_rate < 0.5%, latency_p99 < 2x baseline"
    },
    {
      "name": "canary-50pct",
      "py3_traffic_pct": 50,
      "duration_hours": 168,
      "success_criteria": "all metrics within 10% of baseline"
    },
    {
      "name": "full-cutover",
      "py3_traffic_pct": 100,
      "duration_hours": 336,
      "success_criteria": "soak period complete, stakeholder sign-off"
    }
  ]
}
```

Each stage defines:
- **py3_traffic_pct**: Percentage of traffic routed to Py3
- **duration_hours**: How long to run at this level before advancing
- **success_criteria**: Conditions to meet before advancing to next stage

### Step 4: Generate Monitoring Configuration

Create Prometheus alerting rules and Grafana dashboards:

**Alerting Rules**:
- `py3_error_rate_spike` — Alert if Py3 error rate exceeds baseline + threshold
- `py3_latency_p99_spike` — Alert if Py3 p99 latency > 2x baseline
- `py3_health_check_failures` — Alert if health checks fail
- `py2_py3_divergence` — Alert if responses differ unexpectedly

**Monitoring Setup**:
- Structured logging (JSON format) for easy comparison
- Health check endpoints returning Py2/Py3 identifier
- Metrics labeled with `version=py2` and `version=py3`
- Dashboard showing side-by-side comparison of error rates, latency, request counts

### Step 5: Generate Rollback Triggers

Define automatic and manual rollback conditions:

**Automatic Rollback**:
- Error rate exceeds `--rollback-threshold` (default 1.0%)
- Latency p99 exceeds 2x baseline for 10 minutes
- Health check failures on Py3 instances
- Memory/CPU exhaustion on Py3

**Manual Rollback**:
- Operator notices unexpected behavior in logs/metrics
- Database corruption or data inconsistency detected
- Third-party service incompatibility discovered

### Step 6: Generate Report

The script produces human-readable reports:

- **canary-plan.md**: Architecture diagram, ramp-up schedule table, monitoring setup, step-by-step cutover runbook
- **canary-rollback-runbook.md**: How to manually rollback at each stage, automated rollback details

---

## Infrastructure Detection

### Kubernetes

Detected by:
- `*.yaml` files with `apiVersion: apps/v1` or `apiVersion: v1`
- `kind: Deployment`, `kind: Service`, `kind: StatefulSet`

Generates:
- Separate Deployments for Py2 and Py3
- Istio VirtualService (if `istio-system` namespace exists) or Nginx Ingress
- HPA for auto-scaling based on CPU/memory

### Docker Compose

Detected by:
- `docker-compose.yml` or `docker-compose.yaml`

Generates:
- Dual services with image tags `app:py2` and `app:py3`
- Load balancer service with traffic split config
- Example HAProxy/Nginx configs for traffic routing

### Bare Metal / Systemd

Detected by:
- `Procfile` (Heroku) or `*.service` files (systemd)
- `supervisord.conf` (supervisor)

Generates:
- Systemd unit files for both versions
- HAProxy frontend config with weight-based routing
- Example Nginx config for alternative setup

### Ansible / Terraform

Detected by:
- `*.yaml` files in `roles/`, `playbooks/` directories (Ansible)
- `*.tf` files (Terraform)

Outputs:
- Note in canary-plan.json: "Detected IaC; consider updating playbooks/TF files"
- Example variable definitions for both versions

---

## Monitoring Setup

### Prometheus Alerts

```yaml
- alert: Py3ErrorRateSpike
  expr: rate(http_requests_total{version="py3", status=~"5.."}[5m]) > 0.01
  for: 5m
  annotations:
    summary: "Py3 error rate exceeded threshold"

- alert: Py3LatencySpike
  expr: histogram_quantile(0.99, http_request_duration_seconds{version="py3"}) >
        2 * histogram_quantile(0.99, http_request_duration_seconds{version="py2"})
  for: 10m
  annotations:
    summary: "Py3 latency 2x higher than Py2"

- alert: Py3HealthCheckFailure
  expr: up{job="py3-app"} == 0
  for: 1m
  annotations:
    summary: "Py3 health check failed"
```

### Structured Logging

Recommended JSON log format:

```json
{
  "timestamp": "2024-01-15T10:30:45Z",
  "version": "py3",
  "status": 200,
  "response_time_ms": 45,
  "request_id": "abc123",
  "endpoint": "/api/users",
  "method": "GET"
}
```

This allows easy aggregation and comparison in monitoring systems.

---

## Success Criteria

The skill has succeeded when:

1. Infrastructure type is correctly detected (K8s, Docker Compose, bare metal, or combination)
2. Deployment manifests are generated for both Py2 and Py3 versions
3. Traffic splitting configuration is created for chosen infrastructure
4. Ramp-up schedule with realistic timelines and success criteria is defined
5. Monitoring setup includes error rate, latency, and health check comparisons
6. Automatic rollback triggers are configured (error rate threshold)
7. A step-by-step cutover runbook is generated (canary-plan.md)
8. A rollback runbook is generated with manual and automated procedures
9. All configs are production-ready (no placeholders, valid syntax)
10. A summary is provided showing estimated cutover timeline

---

## References

- `references/canary-deployment-patterns.md` — Industry best practices for canary deployments
- `references/kubernetes-traffic-splitting.md` — Istio VirtualService and Nginx Ingress canary setup
- `references/monitoring-dual-versions.md` — Structured logging and metrics for Py2 vs. Py3
- `references/rollback-runbook-template.md` — Rollback procedures for different infrastructure types
- [Kubernetes Canary Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#canary-deployment)
- [Istio Traffic Management](https://istio.io/latest/docs/tasks/traffic-management/)
- [HAProxy Configuration](http://www.haproxy.org/#docs)
