# Observability Stack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a self-contained Docker Compose stack at `docker-compose/observability-stack/` that wires the reddit-digest-agent to a full observability backend (OTel Collector, Arize Phoenix, Tempo, Prometheus, Grafana).

**Architecture:** OTel Collector receives all telemetry from the agent via OTLP HTTP and fans out: traces go to both Tempo (gRPC) and Phoenix (HTTP), metrics are exposed via a Prometheus exporter endpoint scraped by Prometheus. Grafana is pre-provisioned with Tempo and Prometheus datasources.

**Tech Stack:** Docker Compose, OpenTelemetry Collector Contrib, Grafana Tempo, Arize Phoenix, Prometheus, Grafana

**Spec:** `docs/superpowers/specs/2026-04-12-observability-stack-design.md`

---

## File Structure

```
docker-compose/observability-stack/
├── README.md                         # Usage docs
├── docker-compose.yml                # All 6 services
└── config/
    ├── otel-collector.yaml           # Collector pipelines
    ├── prometheus.yaml               # Scrape config
    ├── tempo.yaml                    # Tempo monolithic config
    └── grafana/
        └── datasources.yaml          # Auto-provision datasources
```

---

### Task 1: Tempo Configuration

**Files:**
- Create: `docker-compose/observability-stack/config/tempo.yaml`

- [ ] **Step 1: Create Tempo config**

```yaml
# Tempo monolithic mode configuration
server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: "0.0.0.0:4317"

storage:
  trace:
    backend: local
    local:
      path: /tmp/tempo/blocks
    wal:
      path: /tmp/tempo/wal

metrics_generator:
  storage:
    path: /tmp/tempo/metrics
  traces_storage:
    path: /tmp/tempo/blocks
```

This configures Tempo in monolithic mode with:
- HTTP API on `:3200` (for Grafana queries)
- OTLP gRPC receiver on `:4317` (for Collector export)
- Local filesystem storage (ephemeral, no volumes)

- [ ] **Step 2: Commit**

```bash
git add docker-compose/observability-stack/config/tempo.yaml
git commit -m "feat(observability): add Tempo monolithic configuration"
```

---

### Task 2: Prometheus Configuration

**Files:**
- Create: `docker-compose/observability-stack/config/prometheus.yaml`

- [ ] **Step 1: Create Prometheus scrape config**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "otel-collector"
    static_configs:
      - targets: ["otel-collector:8889"]
```

Single scrape job: Prometheus pulls metrics from the OTel Collector's Prometheus exporter on port `8889` every 15 seconds.

- [ ] **Step 2: Commit**

```bash
git add docker-compose/observability-stack/config/prometheus.yaml
git commit -m "feat(observability): add Prometheus scrape configuration"
```

---

### Task 3: OTel Collector Configuration

**Files:**
- Create: `docker-compose/observability-stack/config/otel-collector.yaml`

- [ ] **Step 1: Create OTel Collector config**

```yaml
receivers:
  otlp:
    protocols:
      http:
        endpoint: "0.0.0.0:4318"

exporters:
  otlp/tempo:
    endpoint: "tempo:4317"
    tls:
      insecure: true

  otlphttp/phoenix:
    endpoint: "http://phoenix:6006"
    tls:
      insecure: true

  prometheus:
    endpoint: "0.0.0.0:8889"

processors:
  batch:
    timeout: 5s
    send_batch_size: 1024

extensions:
  health_check:
    endpoint: "0.0.0.0:13133"

service:
  extensions: [health_check]
  pipelines:
    traces:
      receivers: [otlp]
      processors: [batch]
      exporters: [otlp/tempo, otlphttp/phoenix]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus]
```

Key details:
- Receives OTLP HTTP on `:4318` (matches agent's `OTEL_EXPORTER_OTLP_ENDPOINT`)
- Fan-out traces to Tempo (gRPC) and Phoenix (HTTP)
- Metrics exposed as Prometheus endpoint on `:8889`
- Healthcheck on `:13133` for `depends_on` conditions
- Batch processor for efficiency

- [ ] **Step 2: Commit**

```bash
git add docker-compose/observability-stack/config/otel-collector.yaml
git commit -m "feat(observability): add OTel Collector pipeline configuration"
```

---

### Task 4: Grafana Datasource Provisioning

**Files:**
- Create: `docker-compose/observability-stack/config/grafana/datasources.yaml`

- [ ] **Step 1: Create Grafana datasources provisioning file**

```yaml
apiVersion: 1

datasources:
  - name: Tempo
    type: tempo
    access: proxy
    url: http://tempo:3200
    isDefault: true
    editable: false

  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    editable: false
```

Tempo is set as default datasource since traces are the primary observability signal for this agent.

- [ ] **Step 2: Commit**

```bash
git add docker-compose/observability-stack/config/grafana/datasources.yaml
git commit -m "feat(observability): add Grafana datasource provisioning"
```

---

### Task 5: Docker Compose File

**Files:**
- Create: `docker-compose/observability-stack/docker-compose.yml`

- [ ] **Step 1: Create Docker Compose file**

```yaml
services:
  tempo:
    image: grafana/tempo:latest
    ports:
      - "3200:3200"
    volumes:
      - ./config/tempo.yaml:/etc/tempo/tempo.yaml:ro
    command: ["-config.file=/etc/tempo/tempo.yaml"]
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:3200/ready"]
      interval: 10s
      timeout: 5s
      retries: 5

  phoenix:
    image: arizephoenix/phoenix:latest
    ports:
      - "6006:6006"
    environment:
      - PHOENIX_WORKING_DIR=/tmp/phoenix
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:6006/healthz')"]
      interval: 10s
      timeout: 5s
      retries: 5

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./config/prometheus.yaml:/etc/prometheus/prometheus.yml:ro
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:9090/-/healthy"]
      interval: 10s
      timeout: 5s
      retries: 5

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_AUTH_ANONYMOUS_ENABLED=true
      - GF_AUTH_ANONYMOUS_ORG_ROLE=Admin
      - GF_AUTH_DISABLE_LOGIN_FORM=true
    volumes:
      - ./config/grafana/datasources.yaml:/etc/grafana/provisioning/datasources/datasources.yaml:ro
    depends_on:
      tempo:
        condition: service_healthy
      prometheus:
        condition: service_healthy

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    ports:
      - "4318:4318"
    volumes:
      - ./config/otel-collector.yaml:/etc/otelcol-contrib/config.yaml:ro
    depends_on:
      tempo:
        condition: service_healthy
      phoenix:
        condition: service_healthy
      prometheus:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:13133/"]
      interval: 10s
      timeout: 5s
      retries: 5

  agent:
    build:
      context: ../..
      dockerfile: Dockerfile
    env_file:
      - ../../.env
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
      - OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
      - OTEL_SERVICE_NAME=reddit-digest-agent
    command: ["python", "-m", "reddit_digest.main", "--once"]
    depends_on:
      otel-collector:
        condition: service_healthy
```

Key design decisions:
- `env_file: ../../.env` loads all app credentials from root `.env`
- OTel env vars are overridden in `environment` to point to the Collector inside the Docker network
- Agent `depends_on` Collector with healthcheck — Collector itself depends on all backends
- Grafana anonymous admin access for frictionless local dev
- All config files mounted read-only (`:ro`)
- No persistent volumes — ephemeral local dev stack

- [ ] **Step 2: Commit**

```bash
git add docker-compose/observability-stack/docker-compose.yml
git commit -m "feat(observability): add Docker Compose for full observability stack"
```

---

### Task 6: README

**Files:**
- Create: `docker-compose/observability-stack/README.md`

- [ ] **Step 1: Create README**

```markdown
# Observability Stack

Local Docker Compose stack that wires the reddit-digest-agent to a full observability backend.

## Architecture

```
Agent --OTLP HTTP--> OTel Collector --+--> Tempo (traces)
                                      +--> Phoenix (LLM traces)
                                      +--> Prometheus (metrics, via scrape)
                                      
Grafana reads from Tempo + Prometheus
```

The agent exports traces and metrics via OTLP HTTP to the OTel Collector, which fans out:
- **Traces** to Tempo (distributed tracing) and Phoenix (LLM observability) in parallel
- **Metrics** exposed as a Prometheus endpoint, scraped by Prometheus

## Prerequisites

- Docker and Docker Compose
- A configured `.env` file at the repository root (see `.env.example`)

## Quick Start

```bash
# From this directory
docker compose up --build

# Or from the repository root
docker compose -f docker-compose/observability-stack/docker-compose.yml up --build
```

The agent runs a single digest iteration (`--once`) and exits. The observability backends remain running for inspection.

## Services

| Service | URL | Description |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | Dashboards (Tempo + Prometheus pre-configured) |
| Phoenix | http://localhost:6006 | LLM trace exploration |
| Prometheus | http://localhost:9090 | Metrics queries |
| Tempo | http://localhost:3200 | Trace API |
| OTel Collector | localhost:4318 | OTLP HTTP receiver |

## Re-run the Agent

To trigger another digest run after the initial one completes:

```bash
docker compose run --rm agent
```

## Tear Down

```bash
docker compose down -v
```
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose/observability-stack/README.md
git commit -m "docs(observability): add README for observability stack"
```

---

### Task 7: Integration Test — Smoke Test the Stack

This is a manual verification task, not an automated test.

- [ ] **Step 1: Start the stack**

```bash
cd docker-compose/observability-stack
docker compose up --build -d
```

- [ ] **Step 2: Verify all services are healthy**

```bash
docker compose ps
```

Expected: All services show `healthy` or `running`. The agent should eventually exit with code 0.

- [ ] **Step 3: Check Grafana datasources**

Open http://localhost:3000 → Connections → Data sources. Verify Tempo and Prometheus appear.

- [ ] **Step 4: Check Phoenix for traces**

Open http://localhost:6006. Verify traces from the agent run appear (spans like `digest.run`, `digest.collector`, etc.).

- [ ] **Step 5: Check Prometheus for metrics**

Open http://localhost:9090 and query `reddit_digest_digest_runs_total`. Verify at least 1 data point.

- [ ] **Step 6: Tear down**

```bash
docker compose down -v
```
