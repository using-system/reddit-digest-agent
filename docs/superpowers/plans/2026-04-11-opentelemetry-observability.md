# OpenTelemetry Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional OpenTelemetry instrumentation with GenAI semantic conventions, custom traces for the pipeline, and custom metrics for agent-specific operations.

**Architecture:** Centralized `telemetry.py` module that configures OTel providers when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, activates OpenAI auto-instrumentation for LLM spans, and exposes a tracer/meter for custom spans and metrics in nodes.

**Tech Stack:** `opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`, `opentelemetry-instrumentation-openai`

**Spec:** `docs/superpowers/specs/2026-04-11-opentelemetry-observability-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/reddit_digest/telemetry.py` | Create | Centralized OTel setup, provider config, auto-instrumentation activation, tracer/meter accessors |
| `src/reddit_digest/main.py` | Modify | Call `setup_telemetry()` at startup |
| `src/reddit_digest/graphs/digest.py` | Modify | Add spans per node wrapper |
| `src/reddit_digest/graphs/feedback.py` | Modify | Add spans per node wrapper |
| `src/reddit_digest/nodes/collector.py` | Modify | Emit `posts.collected` counter + `fetch.duration` histogram |
| `src/reddit_digest/nodes/filterer.py` | Modify | Emit `posts.filtered` counter |
| `src/reddit_digest/nodes/scorer.py` | Modify | Emit `posts.scored` counter |
| `src/reddit_digest/nodes/deliverer.py` | Modify | Emit `messages.sent` / `messages.errors` counters |
| `src/reddit_digest/nodes/feedback.py` | Modify | Emit `preference_updates` counter |
| `src/reddit_digest/telegram/bot.py` | Modify | Emit `reactions` counter |
| `pyproject.toml` | Modify | Add OTel dependencies |
| `README.md` | Modify | Add Observability section |
| `.env.example` | Modify | Add commented OTel variables |
| `tests/test_telemetry.py` | Create | Tests for telemetry module |

---

### Task 1: Add OTel dependencies

**Files:**
- Modify: `pyproject.toml:6-17`

- [ ] **Step 1: Add dependencies to pyproject.toml**

In `pyproject.toml`, add the four OTel packages to the `dependencies` list:

```toml
dependencies = [
    "langchain-openai",
    "langgraph",
    "httpx",
    "python-telegram-bot",
    "apscheduler>=3.10,<4",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "python-dotenv",
    "aiosqlite",
    "curl-cffi>=0.15.0",
    "opentelemetry-api",
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp-proto-http",
    "opentelemetry-instrumentation-openai",
]
```

- [ ] **Step 2: Run dependency install**

Run: `uv sync --all-extras`
Expected: all dependencies resolve and install successfully.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add OpenTelemetry dependencies"
```

---

### Task 2: Create telemetry module with tests

**Files:**
- Create: `src/reddit_digest/telemetry.py`
- Create: `tests/test_telemetry.py`

- [ ] **Step 1: Write the tests**

Create `tests/test_telemetry.py`:

```python
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from opentelemetry import metrics, trace


class TestSetupTelemetryDisabled:
    """When OTEL_EXPORTER_OTLP_ENDPOINT is not set, telemetry is a no-op."""

    def test_no_op_when_endpoint_unset(self):
        env = os.environ.copy()
        env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        with patch.dict(os.environ, env, clear=True):
            from reddit_digest.telemetry import setup_telemetry

            setup_telemetry()

            tracer = trace.get_tracer("test")
            assert tracer is not None
            # NoOp tracer produces non-recording spans
            with tracer.start_as_current_span("test-span") as span:
                assert not span.is_recording()

    def test_get_tracer_returns_tracer(self):
        from reddit_digest.telemetry import get_tracer

        tracer = get_tracer("test")
        assert tracer is not None

    def test_get_meter_returns_meter(self):
        from reddit_digest.telemetry import get_meter

        meter = get_meter("test")
        assert meter is not None


class TestSetupTelemetryEnabled:
    """When OTEL_EXPORTER_OTLP_ENDPOINT is set, providers are configured."""

    def test_tracer_provider_configured(self):
        env = {
            "OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318",
            "OTEL_SERVICE_NAME": "test-service",
        }
        with patch.dict(os.environ, env, clear=False):
            from reddit_digest.telemetry import setup_telemetry

            # Reset providers to defaults before test
            trace.set_tracer_provider(trace.ProxyTracerProvider())
            metrics.set_meter_provider(metrics.NoOpMeterProvider())

            setup_telemetry()

            tracer = trace.get_tracer("test")
            with tracer.start_as_current_span("test-span") as span:
                assert span.is_recording()

            # Cleanup: shutdown to avoid leaking resources
            provider = trace.get_tracer_provider()
            if hasattr(provider, "shutdown"):
                provider.shutdown()
            meter_provider = metrics.get_meter_provider()
            if hasattr(meter_provider, "shutdown"):
                meter_provider.shutdown()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_telemetry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reddit_digest.telemetry'`

- [ ] **Step 3: Write the telemetry module**

Create `src/reddit_digest/telemetry.py`:

```python
from __future__ import annotations

import atexit
import logging
import os

from opentelemetry import metrics, trace

logger = logging.getLogger(__name__)

_initialized = False


def setup_telemetry() -> None:
    """Configure OTel providers and auto-instrumentation.

    No-op when OTEL_EXPORTER_OTLP_ENDPOINT is not set.
    """
    global _initialized
    if _initialized:
        return

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.info("OTel export disabled (OTEL_EXPORTER_OTLP_ENDPOINT not set)")
        _initialized = True
        return

    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    service_name = os.environ.get("OTEL_SERVICE_NAME", "reddit-digest-agent")
    resource = Resource.create({"service.name": service_name})

    # Traces
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    # Metrics
    metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Auto-instrumentation for OpenAI SDK (used by langchain-openai)
    from opentelemetry.instrumentation.openai import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()

    def _shutdown() -> None:
        tracer_provider.shutdown()
        meter_provider.shutdown()

    atexit.register(_shutdown)
    _initialized = True
    logger.info("OTel telemetry configured (endpoint=%s)", endpoint)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    return metrics.get_meter(name)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_telemetry.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `uv run pytest -v --tb=short`
Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/reddit_digest/telemetry.py tests/test_telemetry.py
git commit -m "feat(telemetry): add centralized OpenTelemetry module with auto-instrumentation"
```

---

### Task 3: Call setup_telemetry at startup

**Files:**
- Modify: `src/reddit_digest/main.py:1-14,29-37,44-51`

- [ ] **Step 1: Add the import and call in main.py**

Add the import at the top of `main.py` (after the existing imports):

```python
from reddit_digest.telemetry import setup_telemetry
```

Add `setup_telemetry()` as the first call in both `run_once()` and `main()`, right after `logging.basicConfig(...)`:

In `run_once()` (after line 34):
```python
async def run_once() -> None:
    """Run a single digest immediately and exit."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    setup_telemetry()

    settings = load_settings()
    # ... rest unchanged
```

In `main()` (after line 48):
```python
async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    setup_telemetry()

    settings = load_settings()
    # ... rest unchanged
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest -v --tb=short`
Expected: all tests pass (setup_telemetry is a no-op without the env var).

- [ ] **Step 3: Commit**

```bash
git add src/reddit_digest/main.py
git commit -m "feat(telemetry): call setup_telemetry at startup in main"
```

---

### Task 4: Add pipeline spans to digest graph

**Files:**
- Modify: `src/reddit_digest/graphs/digest.py:1-79`

- [ ] **Step 1: Add tracing to each node wrapper**

Add the import at the top:

```python
from reddit_digest.telemetry import get_tracer
```

Replace each node wrapper to add spans. The tracer is obtained inside `build_digest_graph` so it's created after `setup_telemetry()` runs:

```python
def build_digest_graph(settings: Settings, conn: aiosqlite.Connection):
    tracer = get_tracer("reddit_digest.digest")

    async def collector_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.collector") as span:
            result = await collect_posts(state, settings)
            raw_posts = result.get("raw_posts", [])
            span.set_attribute("reddit.subreddits.count", len(state.get("subreddits", [])))
            span.set_attribute("reddit.posts.collected", len(raw_posts))
            return result

    async def filterer_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.filterer") as span:
            span.set_attribute("posts.input_count", len(state.get("raw_posts", [])))
            result = await filter_posts(state, conn, settings)
            span.set_attribute("posts.output_count", len(result.get("filtered_posts", [])))
            return result

    async def scorer_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.scorer") as span:
            span.set_attribute("posts.input_count", len(state.get("filtered_posts", [])))
            result = await score_posts(state, settings)
            span.set_attribute("posts.output_count", len(result.get("scored_posts", [])))
            return result

    async def summarizer_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.summarizer") as span:
            result = await summarize_posts(state, settings)
            span.set_attribute("summaries.count", len(result.get("summaries", [])))
            return result

    async def deliverer_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.deliverer") as span:
            result = await deliver_summaries(state, settings, conn)
            span.set_attribute("telegram.messages.sent", len(result.get("delivered_ids", [])))
            return result

    async def mark_all_seen_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.mark_all_seen"):
            raw_posts: list[RedditPost] = state.get("raw_posts", [])
            summaries: list[Summary] = state.get("summaries", [])

            delivered_reddit_ids = {s.reddit_id for s in summaries}

            for post in raw_posts:
                status = "sent" if post.reddit_id in delivered_reddit_ids else "seen"
                await save_seen_post(conn, post, status=status)

            logger.info(
                "Marked %d posts as seen (%d sent)",
                len(raw_posts),
                len(delivered_reddit_ids),
            )
            return {}

    # builder setup unchanged...
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_digest_graph.py -v --tb=short`
Expected: all digest graph tests pass (spans are NoOp without OTel configured).

- [ ] **Step 3: Commit**

```bash
git add src/reddit_digest/graphs/digest.py
git commit -m "feat(telemetry): add pipeline spans to digest graph nodes"
```

---

### Task 5: Add pipeline spans to feedback graph

**Files:**
- Modify: `src/reddit_digest/graphs/feedback.py:1-43`

- [ ] **Step 1: Add tracing to each node wrapper**

Add the import:

```python
from reddit_digest.telemetry import get_tracer
```

Update the node wrappers:

```python
def build_feedback_graph(settings: Settings, conn: aiosqlite.Connection):
    tracer = get_tracer("reddit_digest.feedback")

    async def receive_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("feedback.receive_reaction"):
            return await receive_reaction(state, conn)

    async def analyze_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("feedback.analyze"):
            return await analyze_reaction(state, settings)

    async def update_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("feedback.update_preferences"):
            return await update_preferences(state, conn)

    # builder setup unchanged...
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_feedback_graph.py -v --tb=short`
Expected: all feedback graph tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/reddit_digest/graphs/feedback.py
git commit -m "feat(telemetry): add pipeline spans to feedback graph nodes"
```

---

### Task 6: Add root span and digest metrics to main.py

**Files:**
- Modify: `src/reddit_digest/main.py:19-26`

- [ ] **Step 1: Add root span and metrics to run_digest**

Add the import at the top (alongside the existing `setup_telemetry` import):

```python
from reddit_digest.telemetry import get_meter, get_tracer, setup_telemetry
```

Replace `run_digest`:

```python
async def run_digest(settings, db_conn) -> None:
    tracer = get_tracer("reddit_digest.main")
    meter = get_meter("reddit_digest.main")
    runs_counter = meter.create_counter(
        "reddit_digest.digest.runs",
        description="Number of digest runs",
    )
    duration_histogram = meter.create_histogram(
        "reddit_digest.digest.duration",
        unit="s",
        description="Total duration of a digest run",
    )

    import time

    start = time.monotonic()
    logger.info("Running scheduled digest...")

    with tracer.start_as_current_span("digest.run") as span:
        span.set_attribute("digest.subreddits", settings.reddit_subreddits)
        span.set_attribute("digest.cron_expression", settings.digest_cron)
        try:
            graph = build_digest_graph(settings, db_conn)
            result = await graph.ainvoke({"subreddits": settings.reddit_subreddits})
            delivered = len(result.get("delivered_ids", []))
            logger.info("Digest complete: delivered %d summaries", delivered)
            runs_counter.add(1, {"status": "success"})
        except Exception:
            logger.exception("Digest run failed")
            runs_counter.add(1, {"status": "error"})
            raise
        finally:
            elapsed = time.monotonic() - start
            duration_histogram.record(elapsed)
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest -v --tb=short`
Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/reddit_digest/main.py
git commit -m "feat(telemetry): add root span and digest run metrics"
```

---

### Task 7: Add metrics to collector node

**Files:**
- Modify: `src/reddit_digest/nodes/collector.py:1-107`

- [ ] **Step 1: Add metrics instrumentation**

Add the import at the top:

```python
from reddit_digest.telemetry import get_meter
```

In `collect_posts`, add the meter and instruments at the start of the function, then record metrics at appropriate points:

```python
async def collect_posts(state: dict[str, Any], settings: Settings) -> dict[str, Any]:
    meter = get_meter("reddit_digest.collector")
    posts_counter = meter.create_counter(
        "reddit_digest.reddit.posts.collected",
        description="Posts collected from Reddit",
    )
    fetch_histogram = meter.create_histogram(
        "reddit_digest.reddit.fetch.duration",
        unit="s",
        description="Reddit fetch duration per subreddit",
    )

    all_posts: list[RedditPost] = []

    session = cffi_requests.Session(impersonate="chrome")
    session.get("https://www.reddit.com/", timeout=30)

    for i, sub_name in enumerate(state["subreddits"]):
        if i > 0 and settings.reddit_fetch_delay > 0:
            time.sleep(settings.reddit_fetch_delay / 1000)
        sub_start = time.monotonic()
        sub_post_count = 0
        try:
            params: dict[str, Any] = {
                "limit": settings.reddit_limit,
                "raw_json": 1,
            }
            if settings.reddit_sort == "top":
                params["t"] = settings.reddit_time_filter

            url = f"https://www.reddit.com/r/{sub_name}/{settings.reddit_sort}.json"
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for child in data["data"]["children"]:
                post_data = child["data"]
                post_id = post_data["id"]

                top_comments: list[str] = []
                if settings.reddit_comments_limit > 0:
                    if settings.reddit_fetch_delay > 0:
                        time.sleep(settings.reddit_fetch_delay / 1000)
                    try:
                        top_comments = _fetch_top_comments(
                            session,
                            sub_name,
                            post_id,
                            settings.reddit_comments_limit,
                        )
                    except Exception:
                        logger.warning(
                            "Failed to fetch comments for %s in r/%s",
                            post_id,
                            sub_name,
                        )

                all_posts.append(
                    RedditPost(
                        reddit_id=post_id,
                        subreddit=sub_name,
                        title=post_data["title"],
                        url=post_data["url"],
                        score=post_data["score"],
                        num_comments=post_data["num_comments"],
                        selftext=post_data.get("selftext", ""),
                        created_utc=post_data["created_utc"],
                        top_comments=top_comments,
                    )
                )
                sub_post_count += 1
        except Exception:
            logger.exception("Failed to fetch posts from r/%s", sub_name)
        finally:
            elapsed = time.monotonic() - sub_start
            fetch_histogram.record(elapsed, {"subreddit": sub_name})
            posts_counter.add(sub_post_count, {"subreddit": sub_name})

    session.close()

    logger.info(
        "Collected %d posts from %d subreddits",
        len(all_posts),
        len(state["subreddits"]),
    )
    return {"raw_posts": all_posts}
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_collector.py -v --tb=short`
Expected: all collector tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/reddit_digest/nodes/collector.py
git commit -m "feat(telemetry): add Reddit collection metrics"
```

---

### Task 8: Add metrics to filterer node

**Files:**
- Modify: `src/reddit_digest/nodes/filterer.py:1-75`

- [ ] **Step 1: Add metrics instrumentation**

Add the import:

```python
from reddit_digest.telemetry import get_meter
```

At the end of `filter_posts`, after the filtering loop and before the return, add:

```python
    meter = get_meter("reddit_digest.filterer")
    filtered_counter = meter.create_counter(
        "reddit_digest.reddit.posts.filtered",
        description="Posts retained after filtering",
    )
    filtered_counter.add(len(filtered))

    logger.info("Filtered %d → %d posts", len(raw_posts), len(filtered))
    return {"filtered_posts": filtered}
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_filterer.py -v --tb=short`
Expected: all filterer tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/reddit_digest/nodes/filterer.py
git commit -m "feat(telemetry): add filtering metrics"
```

---

### Task 9: Add metrics to scorer node

**Files:**
- Modify: `src/reddit_digest/nodes/scorer.py:1-95`

- [ ] **Step 1: Add metrics instrumentation**

Add the import:

```python
from reddit_digest.telemetry import get_meter
```

At the end of `score_posts`, before the return, add:

```python
    meter = get_meter("reddit_digest.scorer")
    scored_counter = meter.create_counter(
        "reddit_digest.reddit.posts.scored",
        description="Posts retained after LLM scoring",
    )
    scored_counter.add(len(scored))

    logger.info("Scored %d → %d posts", len(filtered_posts), len(scored))
    return {"scored_posts": scored}
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_scorer.py -v --tb=short`
Expected: all scorer tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/reddit_digest/nodes/scorer.py
git commit -m "feat(telemetry): add scoring metrics"
```

---

### Task 10: Add metrics to deliverer node

**Files:**
- Modify: `src/reddit_digest/nodes/deliverer.py:53-99`

- [ ] **Step 1: Add metrics instrumentation**

Add the import:

```python
from reddit_digest.telemetry import get_meter
```

In `deliver_summaries`, add the meter and counters at the start of the function, increment on success/error:

```python
async def deliver_summaries(
    state: dict[str, Any],
    settings: Settings,
    conn: aiosqlite.Connection,
) -> dict[str, Any]:
    meter = get_meter("reddit_digest.deliverer")
    sent_counter = meter.create_counter(
        "reddit_digest.telegram.messages.sent",
        description="Telegram messages sent",
    )
    error_counter = meter.create_counter(
        "reddit_digest.telegram.messages.errors",
        description="Telegram send errors",
    )

    summaries: list[Summary] = state["summaries"]
    scored_posts: list[RedditPost] = state.get("scored_posts", [])

    bot = Bot(token=settings.telegram_bot_token)

    if not summaries:
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text="Aucun thread pertinent pour aujourd'hui.",
        )
        return {"delivered_ids": []}

    by_sub: dict[str, list[Summary]] = defaultdict(list)
    for s in summaries:
        by_sub[s.subreddit].append(s)

    delivered_ids: list[str] = []

    for i, (subreddit, sub_summaries) in enumerate(by_sub.items()):
        if i > 0 and settings.telegram_send_delay > 0:
            await asyncio.sleep(settings.telegram_send_delay / 1000)

        try:
            text = _format_subreddit_message(subreddit, sub_summaries, scored_posts)
            keyboard = _build_keyboard(sub_summaries)

            msg = await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            delivered_ids.append(str(msg.message_id))
            sent_counter.add(1, {"subreddit": subreddit})
        except Exception:
            logger.exception("Failed to deliver digest for r/%s", subreddit)
            error_counter.add(1)

    logger.info(
        "Delivered %d messages for %d subreddits",
        len(delivered_ids),
        len(by_sub),
    )
    return {"delivered_ids": delivered_ids}
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_deliverer.py -v --tb=short`
Expected: all deliverer tests pass.

- [ ] **Step 3: Commit**

```bash
git add src/reddit_digest/nodes/deliverer.py
git commit -m "feat(telemetry): add Telegram delivery metrics"
```

---

### Task 11: Add metrics to feedback node and Telegram bot

**Files:**
- Modify: `src/reddit_digest/nodes/feedback.py:83-103`
- Modify: `src/reddit_digest/telegram/bot.py:1-65`

- [ ] **Step 1: Add preference update counter to feedback node**

Add the import in `src/reddit_digest/nodes/feedback.py`:

```python
from reddit_digest.telemetry import get_meter
```

In `update_preferences`, add the counter before the return:

```python
async def update_preferences(
    state: dict[str, Any], conn: aiosqlite.Connection
) -> dict[str, Any]:
    pref_update = state["preference_update"]
    if not pref_update:
        return {}

    subreddit = pref_update["subreddit"]
    topics = pref_update["topics"]
    score_delta = pref_update["score_delta"]

    for topic in topics:
        await update_preference(conn, subreddit, topic, score_delta)

    meter = get_meter("reddit_digest.feedback")
    pref_counter = meter.create_counter(
        "reddit_digest.feedback.preference_updates",
        description="Preference updates from feedback",
    )
    pref_counter.add(1)

    logger.info(
        "Updated preferences for r/%s: %d topics, delta=%d",
        subreddit,
        len(topics),
        score_delta,
    )
    return {}
```

- [ ] **Step 2: Add reaction counter to Telegram bot**

Add the import in `src/reddit_digest/telegram/bot.py`:

```python
from reddit_digest.telemetry import get_meter
```

In `handle_callback`, after `await save_reaction(db_conn, message_id, reaction_type)`, add the counter:

```python
        await save_reaction(db_conn, message_id, reaction_type)

        meter = get_meter("reddit_digest.bot")
        reaction_counter = meter.create_counter(
            "reddit_digest.feedback.reactions",
            description="Reactions received",
        )
        reaction_counter.add(1, {"reaction_type": reaction_type})
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/test_feedback.py tests/test_feedback_graph.py -v --tb=short`
Expected: all feedback tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/reddit_digest/nodes/feedback.py src/reddit_digest/telegram/bot.py
git commit -m "feat(telemetry): add feedback reaction and preference metrics"
```

---

### Task 12: Update README and .env.example

**Files:**
- Modify: `README.md:131-146`
- Modify: `.env.example:30-31`

- [ ] **Step 1: Add Observability section to README**

Insert a new section after the Configuration table (after line 131) and before the "Deploy with Docker" section:

```markdown
## Observability (OpenTelemetry)

The agent supports optional [OpenTelemetry](https://opentelemetry.io/) instrumentation. When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, traces and metrics are exported via OTLP. When unset, telemetry is completely disabled with zero overhead.

### Configuration

All configuration uses standard OpenTelemetry environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | _(unset = disabled)_ | OTLP collector endpoint (e.g. `http://localhost:4318`) |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | no | `http/protobuf` | Export protocol (`http/protobuf` or `grpc`) |
| `OTEL_EXPORTER_OTLP_HEADERS` | no | | Auth headers (e.g. `Authorization=Bearer xxx`) |
| `OTEL_SERVICE_NAME` | no | `reddit-digest-agent` | Service name in traces and metrics |
| `OTEL_RESOURCE_ATTRIBUTES` | no | | Additional resource attributes |

### GenAI traces (auto-instrumented)

LLM calls (scoring, summarization, feedback analysis) are automatically traced following the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/), including:

- `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.response.model`
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- `gen_ai.client.operation.duration`

### Pipeline traces

Each digest run produces a trace with spans for every pipeline stage:

`digest.run` → `digest.collector` → `digest.filterer` → `digest.scorer` → `digest.summarizer` → `digest.deliverer` → `digest.mark_all_seen`

Feedback reactions produce: `feedback.receive_reaction` → `feedback.analyze` → `feedback.update_preferences`

### Custom metrics

| Metric | Type | Unit | Description |
|--------|------|------|-------------|
| `reddit_digest.digest.runs` | Counter | | Digest runs (`status`: `success`/`error`) |
| `reddit_digest.digest.duration` | Histogram | `s` | Total digest run duration |
| `reddit_digest.reddit.posts.collected` | Counter | | Posts collected (`subreddit`) |
| `reddit_digest.reddit.posts.filtered` | Counter | | Posts retained after filtering |
| `reddit_digest.reddit.posts.scored` | Counter | | Posts retained after LLM scoring |
| `reddit_digest.reddit.fetch.duration` | Histogram | `s` | Reddit fetch duration per subreddit |
| `reddit_digest.telegram.messages.sent` | Counter | | Telegram messages sent (`subreddit`) |
| `reddit_digest.telegram.messages.errors` | Counter | | Telegram send errors |
| `reddit_digest.feedback.reactions` | Counter | | Reactions received (`reaction_type`: `like`/`dislike`) |
| `reddit_digest.feedback.preference_updates` | Counter | | Preference updates from feedback |

### Example: Docker Compose with OpenTelemetry Collector

```yaml
services:
  reddit-digest:
    image: ghcr.io/using-system/reddit-digest-agent:latest
    env_file: .env
    environment:
      OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4318
      OTEL_SERVICE_NAME: reddit-digest-agent

  otel-collector:
    image: otel/opentelemetry-collector-contrib:latest
    ports:
      - "4318:4318"
```
```

- [ ] **Step 2: Update .env.example**

Add at the end of `.env.example`:

```
# OpenTelemetry (optional — disabled when OTEL_EXPORTER_OTLP_ENDPOINT is unset)
# OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
# OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
# OTEL_EXPORTER_OTLP_HEADERS=
# OTEL_SERVICE_NAME=reddit-digest-agent
# OTEL_RESOURCE_ATTRIBUTES=
```

- [ ] **Step 3: Run linter**

Run: `uv run ruff check src/ tests/`
Expected: no lint errors.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add README.md .env.example
git commit -m "docs(telemetry): add OpenTelemetry observability section to README"
```
