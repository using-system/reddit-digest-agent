# Observability Stack — Docker Compose

**Date:** 2026-04-12
**Status:** Approved

## Goal

Provide a self-contained Docker Compose stack under `docker-compose/observability-stack/` that spins up the full observability backend for the reddit-digest-agent: OpenTelemetry Collector, Arize Phoenix, Grafana Tempo, Prometheus, and Grafana — all wired together and ready to receive telemetry from a single `--once` agent run.

## Context

The agent already has full OpenTelemetry instrumentation (traces + metrics in all pipeline nodes, LLM auto-instrumentation via `OpenAIInstrumentor`). It exports via OTLP HTTP when `OTEL_EXPORTER_OTLP_ENDPOINT` is set. What's missing is the backend infrastructure to collect, store, and visualize that telemetry locally.

## Architecture

```
┌─────────────┐    OTLP/HTTP     ┌──────────────────┐
│   Agent      │───────:4318────▶│  OTel Collector   │
│ (--once)     │                  │                   │
└─────────────┘                  │  pipelines:       │
                                  │   traces ──┬──▶ Tempo (:4317 gRPC)
                                  │            └──▶ Phoenix (:6006 OTLP)
                                  │   metrics ────▶ Prometheus (scrape :8889)
                                  └──────────────────┘

┌───────────┐       ┌───────────┐
│  Grafana   │◀─────│ Prometheus│
│  :3000     │      │  :9090    │
│ datasources│      └───────────┘
│  - Tempo   │
│  - Prom    │      ┌───────────┐
│            │◀─────│  Tempo    │
└───────────┘       │  :3200    │
                    └───────────┘

┌───────────┐
│  Phoenix   │  (standalone UI :6006)
└───────────┘
```

### Data Flow

1. The agent exports traces and metrics via OTLP HTTP to the OTel Collector on `:4318`.
2. The Collector runs two pipelines:
   - **traces**: fan-out to Tempo (OTLP gRPC `:4317`) AND Phoenix (OTLP HTTP `http://phoenix:6006/v1/traces`).
   - **metrics**: exposes a Prometheus exporter endpoint on `:8889`, scraped by Prometheus every 15s.
3. Grafana is auto-provisioned with Tempo and Prometheus datasources.
4. Phoenix provides its own UI for LLM-centric trace exploration.

### Startup Order

Tempo, Phoenix, Prometheus → OTel Collector → Agent. Enforced via `depends_on` with `condition: service_healthy` where healthchecks are available.

## Services

| Service | Image | Exposed Ports | Role |
|---------|-------|---------------|------|
| `agent` | Build from root `Dockerfile` | none | Runs `python -m reddit_digest.main --once`, depends on full stack |
| `otel-collector` | `otel/opentelemetry-collector-contrib` | `4318:4318` (OTLP HTTP) | Central hub, fan-out traces + metrics |
| `tempo` | `grafana/tempo:latest` | `3200:3200` (API) | Distributed tracing backend (monolithic mode) |
| `phoenix` | `arizephoenix/phoenix:latest` | `6006:6006` | LLM observability UI + OTLP trace backend |
| `prometheus` | `prom/prometheus:latest` | `9090:9090` | Metrics backend, scrapes Collector |
| `grafana` | `grafana/grafana:latest` | `3000:3000` | Visualization, pre-provisioned datasources |

## Agent Service Details

- **Build context**: `../..` (repository root)
- **Dockerfile**: `../../Dockerfile`
- **env_file**: `../../.env` (loads all credentials: Reddit, LLM, Telegram)
- **OTel override**: `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318` set directly in the compose environment section.
- **Command**: `python -m reddit_digest.main --once`
- **depends_on**: all observability services (collector with healthcheck).

## File Structure

```
docker-compose/observability-stack/
├── README.md                    # Usage instructions, service table, ports
├── docker-compose.yml           # All 6 services
└── config/
    ├── otel-collector.yaml      # Receivers, exporters, pipelines
    ├── prometheus.yaml          # Scrape config targeting collector:8889
    ├── tempo.yaml               # Monolithic mode, local storage, OTLP gRPC receiver
    └── grafana/
        └── datasources.yaml     # Auto-provision Tempo + Prometheus
```

## Configuration Files

### otel-collector.yaml

- **Receivers**: `otlp` with HTTP on `:4318`
- **Exporters**:
  - `otlp/tempo`: gRPC to `tempo:4317`
  - `otlphttp/phoenix`: HTTP to `http://phoenix:6006/v1/traces`
  - `prometheus`: endpoint `:8889`
- **Pipelines**:
  - `traces`: receiver `otlp` → exporters `otlp/tempo`, `otlphttp/phoenix`
  - `metrics`: receiver `otlp` → exporter `prometheus`

### prometheus.yaml

- Single scrape job targeting `otel-collector:8889` with 15s interval.

### tempo.yaml

- Monolithic mode with local filesystem storage.
- OTLP gRPC receiver on `:4317`.
- Metrics generator disabled (Prometheus handles metrics).

### grafana/datasources.yaml

- Tempo datasource: `http://tempo:3200`
- Prometheus datasource: `http://prometheus:9090`
- Both set as provisioned (non-editable in UI).

## README.md

The README at `docker-compose/observability-stack/README.md` will contain:

- Stack description and architecture overview
- Prerequisites (Docker + Docker Compose, configured `.env` at repo root)
- Quick start commands (`docker compose up`, `docker compose down -v`)
- Service table with ports and access URLs
- Notes on `--once` mode and how to re-trigger a run

## Out of Scope

- Pre-built Grafana dashboards (planned for later).
- Persistent volumes for Tempo/Prometheus data (ephemeral for local dev).
- Production deployment considerations.
- Alerting rules.
