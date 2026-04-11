# OpenTelemetry Observability Design

## Overview

Add OpenTelemetry instrumentation to the Reddit digest agent following the [GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/). The integration is fully optional — when no `OTEL_EXPORTER_OTLP_ENDPOINT` is set, no telemetry is exported and there is zero runtime overhead beyond the import of the OTel API (NoOp providers).

## Approach

**Approach A — Centralized `telemetry.py` module** combining auto-instrumentation for LLM calls with custom metrics/traces for the agent pipeline.

## Architecture

### Module: `src/reddit_digest/telemetry.py`

Single entry point exposing:

- `setup_telemetry() -> None` — called once at startup in `main.py`
- `get_tracer(name: str) -> Tracer` — shortcut to `trace.get_tracer(name)`
- `get_meter(name: str) -> Meter` — shortcut to `metrics.get_meter(name)`

#### Activation logic

```python
import os

def setup_telemetry() -> None:
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        logger.info("OTel export disabled (OTEL_EXPORTER_OTLP_ENDPOINT not set)")
        return

    # Configure TracerProvider + MeterProvider with OTLP HTTP exporters
    # Activate auto-instrumentation
    # Register atexit shutdown hook
```

#### Provider setup (when enabled)

- `Resource` with `service.name` from `OTEL_SERVICE_NAME` (default: `reddit-digest-agent`) and `service.version` from package metadata.
- `TracerProvider` with `BatchSpanProcessor` + `OTLPSpanExporter` (HTTP).
- `MeterProvider` with `PeriodicExportingMetricReader` + `OTLPMetricExporter` (HTTP).
- `atexit.register()` for graceful shutdown (flush spans/metrics).

### Auto-instrumentation: GenAI spans

Package: `opentelemetry-instrumentation-openai`

Activated in `setup_telemetry()`:

```python
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
OpenAIInstrumentor().instrument()
```

This automatically instruments all `ChatOpenAI.ainvoke()` calls (scorer, summarizer, feedback nodes) since LangChain delegates to the OpenAI SDK. Produces spans with GenAI semantic convention attributes:

- `gen_ai.operation.name` ("chat")
- `gen_ai.request.model` / `gen_ai.response.model`
- `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`
- `gen_ai.client.operation.duration` (histogram)
- `gen_ai.client.token.usage` (histogram)

No `opentelemetry-instrumentation-langchain` — the OpenAI instrumentor suffices and avoids duplicate spans.

### Custom traces: pipeline spans

#### Root span

In `main.py:run_digest()`, a span `digest.run` wraps the entire `graph.ainvoke()` call.

Attributes: `digest.subreddits` (list), `digest.cron_expression`.

#### Per-node spans

Each node wrapper in `graphs/digest.py` and `graphs/feedback.py` is wrapped in a span named after the node:

**Digest graph:** `digest.collector`, `digest.filterer`, `digest.scorer`, `digest.summarizer`, `digest.deliverer`, `digest.mark_all_seen`

**Feedback graph:** `feedback.receive_reaction`, `feedback.analyze`, `feedback.update_preferences`

Attributes per span:

| Span | Attributes |
|---|---|
| `digest.collector` | `reddit.subreddits.count`, `reddit.posts.collected` |
| `digest.filterer` | `posts.input_count`, `posts.output_count` |
| `digest.scorer` | `posts.input_count`, `posts.output_count` |
| `digest.summarizer` | `summaries.count` |
| `digest.deliverer` | `telegram.messages.sent` |

Auto-instrumented LLM spans nest under `digest.scorer` and `digest.summarizer` naturally via context propagation.

### Custom metrics

All prefixed `reddit_digest.`, emitted via the `Meter` from `telemetry.py`.

#### Counters

| Metric | Description | Attributes |
|---|---|---|
| `reddit_digest.digest.runs` | Number of digest runs | `status` (`success` / `error`) |
| `reddit_digest.reddit.posts.collected` | Posts collected from Reddit | `subreddit` |
| `reddit_digest.reddit.posts.filtered` | Posts retained after filtering | |
| `reddit_digest.reddit.posts.scored` | Posts retained after LLM scoring | |
| `reddit_digest.telegram.messages.sent` | Telegram messages sent | `subreddit` |
| `reddit_digest.telegram.messages.errors` | Telegram send errors | |
| `reddit_digest.feedback.reactions` | Reactions received | `reaction_type` (`like` / `dislike`) |
| `reddit_digest.feedback.preference_updates` | Preference updates from feedback | |

#### Histograms

| Metric | Unit | Description |
|---|---|---|
| `reddit_digest.digest.duration` | `s` | Total duration of a digest run |
| `reddit_digest.reddit.fetch.duration` | `s` | Reddit fetch duration per subreddit |

## Dependencies

New entries in `pyproject.toml`:

```toml
"opentelemetry-api",
"opentelemetry-sdk",
"opentelemetry-exporter-otlp-proto-http",
"opentelemetry-instrumentation-openai",
```

Using `otlp-proto-http` (port 4318) rather than gRPC — lighter, no `grpcio` dependency. Users can switch to gRPC via `OTEL_EXPORTER_OTLP_PROTOCOL=grpc` and installing the gRPC exporter separately.

## Configuration

All via standard OTel environment variables. No custom settings in the `Settings` class.

| Variable | Description | Default |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | OTLP collector endpoint. **If unset, OTel is disabled.** | _(unset)_ |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | Export protocol (`http/protobuf`, `grpc`) | `http/protobuf` |
| `OTEL_EXPORTER_OTLP_HEADERS` | Auth headers (e.g., `Authorization=Bearer xxx`) | _(unset)_ |
| `OTEL_SERVICE_NAME` | Service name in traces/metrics | `reddit-digest-agent` |
| `OTEL_RESOURCE_ATTRIBUTES` | Additional resource attributes | _(unset)_ |

## Files to modify

| File | Change |
|---|---|
| `src/reddit_digest/telemetry.py` | **New** — centralized telemetry module |
| `src/reddit_digest/main.py` | Call `setup_telemetry()` at startup |
| `src/reddit_digest/graphs/digest.py` | Add spans per node wrapper |
| `src/reddit_digest/graphs/feedback.py` | Add spans per node wrapper |
| `src/reddit_digest/nodes/collector.py` | Emit `posts.collected` counter + `fetch.duration` histogram |
| `src/reddit_digest/nodes/filterer.py` | Emit `posts.filtered` counter |
| `src/reddit_digest/nodes/scorer.py` | Emit `posts.scored` counter |
| `src/reddit_digest/nodes/summarizer.py` | _(no change — auto-instrumented)_ |
| `src/reddit_digest/nodes/deliverer.py` | Emit `messages.sent` / `messages.errors` counters |
| `src/reddit_digest/nodes/feedback.py` | Emit `reactions` + `preference_updates` counters |
| `src/reddit_digest/telegram/bot.py` | Emit `reactions` counter on callback |
| `pyproject.toml` | Add OTel dependencies |
| `README.md` | Add "Observability (OpenTelemetry)" section with env vars + metrics table |
| `.env.example` | Add commented OTel variables |

## Testing

- Unit tests for `telemetry.py`: verify `setup_telemetry()` is a no-op when `OTEL_EXPORTER_OTLP_ENDPOINT` is unset.
- Existing tests remain unchanged — the NoOp providers ensure no side effects when OTel is not configured.
