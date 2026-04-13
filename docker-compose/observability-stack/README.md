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
