#!/usr/bin/env python3
"""
Canary Deployment Planner — Main Planning Script

Plans gradual rollout from Python 2→3 in production. Generates infrastructure
configuration for running side-by-side with traffic routing, monitoring setup,
ramp-up schedules, and automatic rollback triggers.

Usage:
    python3 plan_canary.py <codebase_path> \
        --target-version 3.11 \
        --infra-type auto \
        --output ./canary-deployment/ \
        --rollback-threshold 1.0

Output:
    canary-plan.json — Master deployment plan
    Deployment manifests for detected infrastructure (K8s, Docker, Systemd, etc.)
    Monitoring configs (Prometheus alerts, Grafana dashboards)
    Runbooks (canary-plan.md, canary-rollback-runbook.md)
"""

import json
import os
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple
from collections import defaultdict
import yaml

import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).resolve().parents[3] / 'scripts' / 'lib'))
from migration_logger import setup_logging, log_execution
logger = setup_logging(__name__)

# ── Helper Functions ──────────────────────────────────────────────────────────

def load_json(path: str) -> Dict[str, Any]:
    """Load JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def save_json(data: Dict[str, Any], path: str) -> None:
    """Save data to JSON file."""
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def read_file(path: str) -> str:
    """Read file contents."""
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception:
        return ""


def write_file(path: str, content: str) -> None:
    """Write content to file."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        f.write(content)


# ── Infrastructure Detection ──────────────────────────────────────────────────

def detect_kubernetes(codebase_path: str) -> bool:
    """Detect Kubernetes manifests."""
    for root, dirs, files in os.walk(codebase_path):
        # Skip hidden directories and common non-infra directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith('.yaml') or file.endswith('.yml'):
                content = read_file(os.path.join(root, file))
                if 'apiVersion' in content and ('kind' in content):
                    if any(k in content for k in ['Deployment', 'Service', 'Pod', 'StatefulSet']):
                        return True
    return False


def detect_docker_compose(codebase_path: str) -> bool:
    """Detect Docker Compose configuration."""
    for name in ['docker-compose.yml', 'docker-compose.yaml']:
        if os.path.exists(os.path.join(codebase_path, name)):
            return True
    return False


def detect_dockerfile(codebase_path: str) -> bool:
    """Detect Dockerfile."""
    for root, dirs, files in os.walk(codebase_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        if 'Dockerfile' in files:
            return True
    return False


def detect_systemd(codebase_path: str) -> bool:
    """Detect systemd configuration."""
    for root, dirs, files in os.walk(codebase_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith('.service') or file == 'Procfile':
                return True
    return False


def detect_supervisor(codebase_path: str) -> bool:
    """Detect supervisor configuration."""
    if os.path.exists(os.path.join(codebase_path, 'supervisord.conf')):
        return True
    return False


def detect_ansible(codebase_path: str) -> bool:
    """Detect Ansible playbooks."""
    for name in ['roles', 'playbooks']:
        if os.path.isdir(os.path.join(codebase_path, name)):
            return True
    return False


def detect_terraform(codebase_path: str) -> bool:
    """Detect Terraform files."""
    for root, dirs, files in os.walk(codebase_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if file.endswith('.tf'):
                return True
    return False


def detect_infrastructure(codebase_path: str) -> Dict[str, bool]:
    """Detect all infrastructure types in codebase."""
    return {
        'kubernetes': detect_kubernetes(codebase_path),
        'docker_compose': detect_docker_compose(codebase_path),
        'dockerfile': detect_dockerfile(codebase_path),
        'systemd': detect_systemd(codebase_path),
        'supervisor': detect_supervisor(codebase_path),
        'ansible': detect_ansible(codebase_path),
        'terraform': detect_terraform(codebase_path),
    }


# ── Ramp-up Schedule Generation ───────────────────────────────────────────────

def generate_ramp_schedule() -> Dict[str, Any]:
    """Generate default ramp-up schedule."""
    return {
        "stages": [
            {
                "name": "canary-1pct",
                "py3_traffic_pct": 1,
                "duration_hours": 24,
                "success_criteria": "error_rate < 0.1%, latency_p99 < baseline",
                "automated_checks": [
                    "error_rate_below_0.1pct",
                    "latency_stable",
                    "health_checks_pass"
                ]
            },
            {
                "name": "canary-5pct",
                "py3_traffic_pct": 5,
                "duration_hours": 48,
                "success_criteria": "error_rate < 0.5%, latency_p99 < 1.5x baseline",
                "automated_checks": [
                    "error_rate_below_0.5pct",
                    "latency_within_1.5x",
                    "memory_usage_stable",
                    "no_critical_logs"
                ]
            },
            {
                "name": "canary-25pct",
                "py3_traffic_pct": 25,
                "duration_hours": 72,
                "success_criteria": "error_rate < 0.5%, latency_p99 < 2x baseline",
                "automated_checks": [
                    "error_rate_below_0.5pct",
                    "latency_within_2x",
                    "throughput_consistent",
                    "no_memory_leaks"
                ]
            },
            {
                "name": "canary-50pct",
                "py3_traffic_pct": 50,
                "duration_hours": 168,
                "success_criteria": "all metrics within 10% of baseline",
                "automated_checks": [
                    "error_rate_within_10pct",
                    "latency_within_10pct",
                    "cpu_usage_stable",
                    "database_performance_equal"
                ]
            },
            {
                "name": "full-cutover",
                "py3_traffic_pct": 100,
                "duration_hours": 336,
                "success_criteria": "7-day soak period complete, stakeholder sign-off required",
                "automated_checks": [
                    "all_metrics_nominal",
                    "7_day_soak_complete"
                ]
            }
        ]
    }


# ── Rollback Configuration ────────────────────────────────────────────────────

def generate_rollback_config(rollback_threshold: float) -> Dict[str, Any]:
    """Generate rollback trigger configuration."""
    return {
        "automatic_triggers": {
            "error_rate_exceeded": {
                "metric": "error_rate",
                "threshold": f"{rollback_threshold}%",
                "window": "5m",
                "action": "immediate_rollback"
            },
            "latency_spike": {
                "metric": "latency_p99",
                "condition": "2x baseline for 10 minutes",
                "action": "immediate_rollback"
            },
            "health_check_failure": {
                "metric": "health_check_status",
                "condition": "3 consecutive failures",
                "action": "immediate_rollback"
            },
            "memory_exhaustion": {
                "metric": "memory_usage",
                "condition": "> 90% of available",
                "action": "immediate_rollback"
            }
        },
        "manual_triggers": [
            "Unexpected errors in logs",
            "Data inconsistency detected",
            "Third-party service incompatibility",
            "Performance degradation not caught by metrics",
            "Operational concerns raised by team"
        ]
    }


# ── Kubernetes Config Generation ──────────────────────────────────────────────

def generate_k8s_py2_deployment(app_name: str, image_tag: str, target_version: str) -> str:
    """Generate Kubernetes Deployment for Py2."""
    yaml_content = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}-py2
  labels:
    app: {app_name}
    version: py2
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: {app_name}
      version: py2
  template:
    metadata:
      labels:
        app: {app_name}
        version: py2
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      containers:
      - name: {app_name}
        image: {image_tag}:py2
        imagePullPolicy: Always
        ports:
        - containerPort: 8080
          name: http
          protocol: TCP
        - containerPort: 8081
          name: metrics
          protocol: TCP
        env:
        - name: PYTHON_VERSION
          value: "2"
        - name: ENVIRONMENT
          value: "production"
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2
        volumeMounts:
        - name: config
          mountPath: /etc/config
          readOnly: true
      volumes:
      - name: config
        configMap:
          name: {app_name}-config-py2
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - {app_name}
              topologyKey: kubernetes.io/hostname

---
apiVersion: v1
kind: Service
metadata:
  name: {app_name}-py2
  labels:
    app: {app_name}
    version: py2
spec:
  type: ClusterIP
  selector:
    app: {app_name}
    version: py2
  ports:
  - port: 80
    targetPort: 8080
    name: http
  - port: 8081
    targetPort: 8081
    name: metrics
"""
    return yaml_content


def generate_k8s_py3_deployment(app_name: str, image_tag: str, target_version: str) -> str:
    """Generate Kubernetes Deployment for Py3."""
    yaml_content = f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {app_name}-py3
  labels:
    app: {app_name}
    version: py3
spec:
  replicas: 1
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: {app_name}
      version: py3
  template:
    metadata:
      labels:
        app: {app_name}
        version: py3
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "8080"
        prometheus.io/path: "/metrics"
    spec:
      containers:
      - name: {app_name}
        image: {image_tag}:py3
        imagePullPolicy: Always
        ports:
        - containerPort: 8080
          name: http
          protocol: TCP
        - containerPort: 8081
          name: metrics
          protocol: TCP
        env:
        - name: PYTHON_VERSION
          value: "3.{target_version.split('.')[1]}"
        - name: ENVIRONMENT
          value: "production"
        - name: CANARY_DEPLOYMENT
          value: "true"
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 1000m
            memory: 1Gi
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
          timeoutSeconds: 5
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /ready
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
          timeoutSeconds: 3
          failureThreshold: 2
        volumeMounts:
        - name: config
          mountPath: /etc/config
          readOnly: true
      volumes:
      - name: config
        configMap:
          name: {app_name}-config-py3
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
          - weight: 100
            podAffinityTerm:
              labelSelector:
                matchExpressions:
                - key: app
                  operator: In
                  values:
                  - {app_name}
              topologyKey: kubernetes.io/hostname

---
apiVersion: v1
kind: Service
metadata:
  name: {app_name}-py3
  labels:
    app: {app_name}
    version: py3
spec:
  type: ClusterIP
  selector:
    app: {app_name}
    version: py3
  ports:
  - port: 80
    targetPort: 8080
    name: http
  - port: 8081
    targetPort: 8081
    name: metrics
"""
    return yaml_content


def generate_k8s_istio_virtual_service(app_name: str) -> str:
    """Generate Istio VirtualService for traffic splitting."""
    yaml_content = f"""apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
metadata:
  name: {app_name}-canary
spec:
  hosts:
  - {app_name}
  http:
  # Stage 1: 1% traffic to Py3
  - name: "canary-1pct"
    match:
    - withoutHeaders:
        canary:
          exact: "disabled"
    route:
    - destination:
        host: {app_name}-py2
        port:
          number: 80
      weight: 99
    - destination:
        host: {app_name}-py3
        port:
          number: 80
      weight: 1
    timeout: 30s
    retries:
      attempts: 3
      perTryTimeout: 10s
  # Fallback to Py2
  - route:
    - destination:
        host: {app_name}-py2
        port:
          number: 80
      weight: 100

---
apiVersion: networking.istio.io/v1alpha3
kind: DestinationRule
metadata:
  name: {app_name}
spec:
  host: {app_name}
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
      http:
        http1MaxPendingRequests: 100
        http2MaxRequests: 100
        maxRequestsPerConnection: 2
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 30s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
      minRequestVolume: 50
"""
    return yaml_content


def generate_k8s_nginx_ingress(app_name: str) -> str:
    """Generate Nginx Ingress with canary annotations."""
    yaml_content = f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {app_name}-canary
  annotations:
    kubernetes.io/ingress.class: nginx
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-by-header: "X-Canary"
    nginx.ingress.kubernetes.io/canary-by-header-value: "py3"
    nginx.ingress.kubernetes.io/canary-weight: "1"
spec:
  rules:
  - host: {app_name}.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {app_name}-py3
            port:
              number: 80

---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {app_name}-stable
spec:
  rules:
  - host: {app_name}.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {app_name}-py2
            port:
              number: 80
"""
    return yaml_content


def generate_k8s_hpa(app_name: str, version: str) -> str:
    """Generate HorizontalPodAutoscaler configuration."""
    yaml_content = f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {app_name}-{version}-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {app_name}-{version}
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 100
        periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 600
      policies:
      - type: Percent
        value: 50
        periodSeconds: 60
"""
    return yaml_content


# ── Docker Compose Generation ────────────────────────────────────────────────

def generate_docker_compose_canary(app_name: str) -> str:
    """Generate Docker Compose with dual services and load balancer."""
    yaml_content = f"""version: '3.8'

services:
  {app_name}-py2:
    image: {{image}}:py2
    container_name: {app_name}-py2
    environment:
      PYTHON_VERSION: "2"
      ENVIRONMENT: production
    ports:
      - "8001:8080"
      - "8101:8081"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    volumes:
      - ./config:/etc/config:ro
      - ./logs/py2:/var/log
    networks:
      - canary-network
    restart: unless-stopped
    labels:
      - "version=py2"

  {app_name}-py3:
    image: {{image}}:py3
    container_name: {app_name}-py3
    environment:
      PYTHON_VERSION: "3"
      ENVIRONMENT: production
      CANARY_DEPLOYMENT: "true"
    ports:
      - "8002:8080"
      - "8102:8081"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    volumes:
      - ./config:/etc/config:ro
      - ./logs/py3:/var/log
    networks:
      - canary-network
    restart: unless-stopped
    labels:
      - "version=py3"

  # Load balancer for traffic splitting
  loadbalancer:
    image: haproxy:2.8-alpine
    container_name: {app_name}-lb
    volumes:
      - ./haproxy-canary.cfg:/usr/local/etc/haproxy/haproxy.cfg:ro
    ports:
      - "80:80"
      - "8404:8404"  # HAProxy stats
    depends_on:
      - {app_name}-py2
      - {app_name}-py3
    networks:
      - canary-network
    restart: unless-stopped

networks:
  canary-network:
    driver: bridge
"""
    return yaml_content


# ── Systemd Configuration ────────────────────────────────────────────────────

def generate_systemd_py2_service(app_name: str) -> str:
    """Generate systemd unit file for Py2 service."""
    content = f"""[Unit]
Description={app_name} Python 2 Service
After=network.target

[Service]
Type=notify
User={app_name}
WorkingDirectory=/opt/{app_name}
Environment="PYTHONUNBUFFERED=1"
Environment="PYTHON_VERSION=2"
ExecStart=/opt/{app_name}/bin/gunicorn --workers 4 --bind 127.0.0.1:8001 app:app
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    return content


def generate_systemd_py3_service(app_name: str, target_version: str) -> str:
    """Generate systemd unit file for Py3 service."""
    content = f"""[Unit]
Description={app_name} Python 3 Service (Canary)
After=network.target

[Service]
Type=notify
User={app_name}
WorkingDirectory=/opt/{app_name}
Environment="PYTHONUNBUFFERED=1"
Environment="PYTHON_VERSION=3.{target_version.split('.')[1]}"
Environment="CANARY_DEPLOYMENT=true"
ExecStart=/opt/{app_name}-py3/bin/gunicorn --workers 2 --bind 127.0.0.1:8002 app:app
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
    return content


def generate_haproxy_canary_config(app_name: str) -> str:
    """Generate HAProxy configuration with canary routing."""
    content = f"""global
    log stdout local0
    log stdout local1 notice
    chroot /var/lib/haproxy
    stats socket /run/haproxy/admin.sock mode 660 level admin
    stats timeout 30s
    daemon

defaults
    log global
    mode http
    option httplog
    option dontlognull
    timeout connect 5000
    timeout client  50000
    timeout server  50000
    errorfile 400 /etc/haproxy/errors/400.http
    errorfile 403 /etc/haproxy/errors/403.http
    errorfile 408 /etc/haproxy/errors/408.http
    errorfile 500 /etc/haproxy/errors/500.http
    errorfile 502 /etc/haproxy/errors/502.http
    errorfile 503 /etc/haproxy/errors/503.http
    errorfile 504 /etc/haproxy/errors/504.http

frontend stats
    bind *:8404
    stats enable
    stats uri /stats
    stats refresh 30s

# Canary deployment frontend
frontend canary_frontend
    bind *:80
    default_backend canary_backend

# Backend with traffic splitting: 99% Py2, 1% Py3 (adjust as needed)
backend canary_backend
    balance roundrobin
    option httpchk GET /health HTTP/1.1\\r\\nHost:\ {app_name}
    server py2 {app_name}-py2:8080 check weight 99
    server py3 {app_name}-py3:8080 check weight 1
    # Stick tables for session persistence if needed
    # stick-table type string len 32 size 100k expire 30m
    # stick on cookie(SERVERID)
"""
    return content


# ── Monitoring Configuration ─────────────────────────────────────────────────

def generate_prometheus_alerts(app_name: str, rollback_threshold: float) -> str:
    """Generate Prometheus alerting rules."""
    yaml_content = f"""groups:
- name: canary-deployment
  interval: 30s
  rules:
  - alert: Py3ErrorRateSpike
    expr: |
      (rate(http_requests_total{{job="{app_name}-py3",status=~"5.."}}[5m]) >
       rate(http_requests_total{{job="{app_name}-py2",status=~"5.."}}[5m]) * 1.5) or
      (rate(http_requests_total{{job="{app_name}-py3",status=~"5.."}}[5m]) > 0.01)
    for: 5m
    labels:
      severity: critical
      version: py3
    annotations:
      summary: "Py3 error rate exceeded threshold"
      description: "Py3 error rate is {{{{$value}}}} - consider rollback"

  - alert: Py3LatencySpike
    expr: |
      histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{job="{app_name}-py3"}}[5m]))
      >
      histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{job="{app_name}-py2"}}[5m])) * 2
    for: 10m
    labels:
      severity: critical
      version: py3
    annotations:
      summary: "Py3 latency 2x higher than Py2"
      description: "Py3 p99 latency: {{{{$value}}}} - investigate performance"

  - alert: Py3HealthCheckFailure
    expr: up{{job="{app_name}-py3"}} == 0
    for: 1m
    labels:
      severity: critical
      version: py3
    annotations:
      summary: "Py3 health check failed"
      description: "Py3 instance is down or unresponsive"

  - alert: Py3MemoryUsageHigh
    expr: |
      container_memory_usage_bytes{{pod_label_version="py3",namespace="default"}}
      / container_spec_memory_limit_bytes{{pod_label_version="py3",namespace="default"}}
      > 0.9
    for: 5m
    labels:
      severity: warning
      version: py3
    annotations:
      summary: "Py3 memory usage > 90%"
      description: "Memory usage: {{{{$value}}}}%"

  - alert: Py3CpuUsageHigh
    expr: |
      rate(container_cpu_usage_seconds_total{{pod_label_version="py3",namespace="default"}}[5m]) * 100
      > 80
    for: 5m
    labels:
      severity: warning
      version: py3
    annotations:
      summary: "Py3 CPU usage > 80%"
      description: "CPU usage: {{{{$value}}}}%"

  - alert: Py2Py3ResponseTimeDivergence
    expr: |
      abs(
        histogram_quantile(0.50, rate(http_request_duration_seconds_bucket{{job="{app_name}-py3"}}[5m]))
        -
        histogram_quantile(0.50, rate(http_request_duration_seconds_bucket{{job="{app_name}-py2"}}[5m]))
      )
      / histogram_quantile(0.50, rate(http_request_duration_seconds_bucket{{job="{app_name}-py2"}}[5m]))
      > 0.2
    for: 15m
    labels:
      severity: warning
    annotations:
      summary: "Py2/Py3 response time divergence > 20%"
      description: "Investigate performance difference between versions"
"""
    return yaml_content


def generate_grafana_dashboard(app_name: str) -> str:
    """Generate Grafana dashboard JSON for Py2/Py3 comparison."""
    json_content = {{
        "dashboard": {{
            "title": f"{app_name} Canary Deployment - Py2 vs Py3",
            "tags": ["canary", "python-migration"],
            "timezone": "UTC",
            "panels": [
                {{
                    "title": "Error Rate Comparison",
                    "type": "graph",
                    "targets": [
                        {{
                            "expr": 'rate(http_requests_total{{job="{app_name}-py2",status=~"5.."}}[5m])',
                            "legendFormat": "Py2 Error Rate"
                        }},
                        {{
                            "expr": 'rate(http_requests_total{{job="{app_name}-py3",status=~"5.."}}[5m])',
                            "legendFormat": "Py3 Error Rate"
                        }}
                    ]
                }},
                {{
                    "title": "Response Time (p99)",
                    "type": "graph",
                    "targets": [
                        {{
                            "expr": 'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{job="{app_name}-py2"}}[5m]))',
                            "legendFormat": "Py2 p99"
                        }},
                        {{
                            "expr": 'histogram_quantile(0.99, rate(http_request_duration_seconds_bucket{{job="{app_name}-py3"}}[5m]))',
                            "legendFormat": "Py3 p99"
                        }}
                    ]
                }},
                {{
                    "title": "Request Rate",
                    "type": "graph",
                    "targets": [
                        {{
                            "expr": 'rate(http_requests_total{{job="{app_name}-py2"}}[5m])',
                            "legendFormat": "Py2 RPS"
                        }},
                        {{
                            "expr": 'rate(http_requests_total{{job="{app_name}-py3"}}[5m])',
                            "legendFormat": "Py3 RPS"
                        }}
                    ]
                }}
            ]
        }}
    }}
    return json.dumps(json_content, indent=2)


# ── Main Planning Logic ───────────────────────────────────────────────────────

def plan_canary_deployment(
    codebase_path: str,
    target_version: str,
    output_dir: str,
    rollback_threshold: float,
    infra_type: str = "auto"
) -> Dict[str, Any]:
    """Main canary deployment planning function."""

    os.makedirs(output_dir, exist_ok=True)

    # Extract app name from codebase path
    app_name = os.path.basename(codebase_path.rstrip('/')) or 'app'
    app_name = re.sub(r'[^a-z0-9-]', '', app_name.lower())

    # Detect infrastructure
    infra = detect_infrastructure(codebase_path)

    plan = {
        "metadata": {
            "app_name": app_name,
            "target_version": target_version,
            "generated_at": __import__('datetime').datetime.now().isoformat(),
            "estimated_total_duration_days": 15
        },
        "detected_infrastructure": infra,
        "deployment_strategy": {
            "type": "canary",
            "approach": "side-by-side with traffic splitting"
        },
        "ramp_schedule": generate_ramp_schedule(),
        "rollback_config": generate_rollback_config(rollback_threshold),
        "monitoring": {
            "prometheus_alerts": "prometheus-alerts.yaml",
            "grafana_dashboard": "monitoring-dashboard.json",
            "metrics_to_track": [
                "error_rate (5xx responses)",
                "latency (p50, p99)",
                "request throughput",
                "memory usage",
                "cpu usage",
                "health check status"
            ]
        },
        "infrastructure_configs": {}
    }

    # Generate K8s configs if detected
    if infra['kubernetes']:
        plan['infrastructure_configs']['kubernetes'] = {
            'py2_deployment': 'k8s-deployment-py2.yaml',
            'py3_deployment': 'k8s-deployment-py3.yaml',
            'istio_vs': 'k8s-virtual-service.yaml',
            'nginx_ingress': 'k8s-ingress.yaml',
            'py2_hpa': 'k8s-hpa-py2.yaml',
            'py3_hpa': 'k8s-hpa-py3.yaml'
        }

        # Write K8s configs
        write_file(
            os.path.join(output_dir, 'k8s-deployment-py2.yaml'),
            generate_k8s_py2_deployment(app_name, 'myregistry/myapp', target_version)
        )
        write_file(
            os.path.join(output_dir, 'k8s-deployment-py3.yaml'),
            generate_k8s_py3_deployment(app_name, 'myregistry/myapp', target_version)
        )
        write_file(
            os.path.join(output_dir, 'k8s-virtual-service.yaml'),
            generate_k8s_istio_virtual_service(app_name)
        )
        write_file(
            os.path.join(output_dir, 'k8s-ingress.yaml'),
            generate_k8s_nginx_ingress(app_name)
        )
        write_file(
            os.path.join(output_dir, 'k8s-hpa-py2.yaml'),
            generate_k8s_hpa(app_name, 'py2')
        )
        write_file(
            os.path.join(output_dir, 'k8s-hpa-py3.yaml'),
            generate_k8s_hpa(app_name, 'py3')
        )

    # Generate Docker Compose configs if detected
    if infra['docker_compose'] or infra['dockerfile']:
        plan['infrastructure_configs']['docker_compose'] = {
            'compose_file': 'docker-compose-canary.yml',
            'load_balancer_config': 'haproxy-canary.cfg'
        }

        write_file(
            os.path.join(output_dir, 'docker-compose-canary.yml'),
            generate_docker_compose_canary(app_name)
        )
        write_file(
            os.path.join(output_dir, 'haproxy-canary.cfg'),
            generate_haproxy_canary_config(app_name)
        )

    # Generate Systemd configs if detected
    if infra['systemd'] or infra['supervisor']:
        plan['infrastructure_configs']['systemd'] = {
            'py2_service': f'{app_name}-py2.service',
            'py3_service': f'{app_name}-py3.service',
            'load_balancer_config': 'haproxy-canary.cfg'
        }

        write_file(
            os.path.join(output_dir, f'{app_name}-py2.service'),
            generate_systemd_py2_service(app_name)
        )
        write_file(
            os.path.join(output_dir, f'{app_name}-py3.service'),
            generate_systemd_py3_service(app_name, target_version)
        )
        write_file(
            os.path.join(output_dir, 'haproxy-canary.cfg'),
            generate_haproxy_canary_config(app_name)
        )

    # Always generate monitoring configs
    write_file(
        os.path.join(output_dir, 'prometheus-alerts.yaml'),
        generate_prometheus_alerts(app_name, rollback_threshold)
    )
    write_file(
        os.path.join(output_dir, 'monitoring-dashboard.json'),
        generate_grafana_dashboard(app_name)
    )

    return plan


@log_execution
def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Plan canary deployment for Py2→Py3 migration"
    )
    parser.add_argument('codebase_path', help='Root directory of Python 2 codebase')
    parser.add_argument('--target-version', default='3.11',
                       help='Python 3 target version (3.9, 3.11, 3.12, 3.13)')
    parser.add_argument('--output', default='.',
                       help='Output directory for deployment configs')
    parser.add_argument('--infra-type', default='auto',
                       choices=['auto', 'kubernetes', 'docker-compose', 'bare-metal'],
                       help='Infrastructure type to target')
    parser.add_argument('--rollback-threshold', type=float, default=1.0,
                       help='Error rate threshold (%) for automatic rollback')

    args = parser.parse_args()

    if not os.path.isdir(args.codebase_path):
        print(f"Error: {args.codebase_path} is not a valid directory", file=sys.stderr)
        sys.exit(1)

    print(f"Planning canary deployment for {args.codebase_path}...")
    print(f"Target Python version: {args.target_version}")
    print(f"Output directory: {args.output}")

    plan = plan_canary_deployment(
        args.codebase_path,
        args.target_version,
        args.output,
        args.rollback_threshold,
        args.infra_type
    )

    # Save master plan
    save_json(plan, os.path.join(args.output, 'canary-plan.json'))
    print(f"✓ Saved canary-plan.json")
    print(f"✓ Generated deployment configs for: {', '.join(k.replace('_', ' ').title() for k, v in plan['detected_infrastructure'].items() if v)}")
    print(f"✓ Estimated cutover timeline: {plan['metadata']['estimated_total_duration_days']} days")


if __name__ == '__main__':
    main()
