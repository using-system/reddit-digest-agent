# LocalAI Stack

Local Docker Compose stack that runs the reddit-digest-agent against a self-hosted [LocalAI](https://localai.io/) inference server serving `google/gemma-3-4b-it`.

## Architecture

```
Agent --OpenAI API--> LocalAI (gemma-3-4b-it)
```

The agent talks to LocalAI over its OpenAI-compatible endpoint, so no external LLM provider is required.

## Prerequisites

- Docker and Docker Compose
- A configured `.env` file at the repository root (see `.env.example`). `OPENAI_BASE_URL` and `LLM_MODEL` from the file are overridden by this stack.
- ~3 GB of free disk space for the gemma-3-4b-it model weights (downloaded on first start and cached in the `localai-models` volume).

## Quick Start

```bash
# From this directory
docker compose up --build

# Or from the repository root
docker compose -f docker-compose/localai-stack/docker-compose.yml up --build
```

On the first run LocalAI downloads the `gemma-3-4b-it` weights from its gallery — expect a few minutes before the healthcheck turns green. The agent is blocked on `localai: service_healthy` and will only start once the model is ready.

The agent runs a single digest iteration (`--once`) and exits. LocalAI keeps running so you can query it directly or trigger another digest.

## Services

| Service | URL | Description |
|---------|-----|-------------|
| LocalAI | http://localhost:8080 | OpenAI-compatible inference API (`/v1/chat/completions`, `/v1/models`, …) |

## Re-run the Agent

```bash
docker compose run --rm agent
```

## Probe LocalAI directly

```bash
curl http://localhost:8080/v1/models
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma-3-4b-it","messages":[{"role":"user","content":"Hello"}]}'
```

## Tear Down

```bash
# Stop the stack (keeps the model cache)
docker compose down

# Stop and also remove the model cache volume
docker compose down -v
```
