# OpenInference Hybrid Instrumentation Design

**Date:** 2026-04-13
**Status:** Approved

## Problem

Phoenix (Arize) cannot differentiate span types (LLM, AGENT, CHAIN, TOOL) because the app only emits standard OTel GenAI spans via `opentelemetry-instrumentation-openai`. Phoenix requires **OpenInference semantic conventions** (`openinference.span.kind`) to categorize spans in its UI. Additionally, Phoenix's Sessions tab is empty because no `session.id` attribute is set on spans.

## Goal

Add OpenInference instrumentation as an additive layer on top of the existing OTel GenAI instrumentation so that:

- Phoenix displays typed spans (LLM, CHAIN, TOOL) and groups runs by session
- Tempo, Grafana, Jaeger continue to work via standard OTel GenAI conventions
- Any OTel-compatible backend can consume the traces

## Design

### Dual instrumentation layers

| Layer | Library | Spans produced | Consumed by |
|-------|---------|---------------|-------------|
| OTel GenAI | `opentelemetry-instrumentation-openai` (existing) | `openai.chat` with tokens, model, duration | Tempo, Grafana, Jaeger |
| OpenInference | `openinference-instrumentation-langchain` (new) | `openinference.span.kind` = CHAIN / LLM / TOOL | Phoenix |

The OpenInference LangChain instrumentor hooks into LangGraph's `ainvoke()` and automatically creates typed spans for each graph node. Both layers write to the same `TracerProvider`, so all spans are exported to all backends. Backends that don't understand OpenInference attributes simply ignore them.

### Session ID

Each call to `run_digest()` generates a unique `session_id` (UUID v4). This ID is propagated to all spans within the run using OpenInference's `using_session()` context manager. In Phoenix, each run appears as a distinct session in the Sessions tab.

The `session_id` is also set as an attribute on the root span `digest.run` for visibility in non-Phoenix backends.

## Changes

### 1. `pyproject.toml`

Add dependency:

```
"openinference-instrumentation-langchain"
```

### 2. `src/reddit_digest/telemetry.py`

After the existing `OpenAIInstrumentor().instrument()` call, add:

```python
from openinference.instrumentation.langchain import LangChainInstrumentor
LangChainInstrumentor().instrument()
```

### 3. `src/reddit_digest/main.py`

In `run_digest()`:

- Generate `session_id = str(uuid4())` at the start of each run
- Wrap the graph invocation with `using_session(session_id)` from `openinference.instrumentation`
- Set `session.id` as an attribute on the root `digest.run` span

## What does NOT change

- Manual spans in graph nodes (`digest.collector`, `digest.filterer`, etc.) remain unchanged with their domain-specific attributes (post counts, subreddits)
- The `opentelemetry-instrumentation-openai` auto-instrumentation stays in place
- Custom metrics (counters, histograms) are unaffected
- OTel Collector, Tempo, Prometheus, Grafana configuration remains the same
