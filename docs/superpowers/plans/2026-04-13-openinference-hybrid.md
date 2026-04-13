# OpenInference Hybrid Instrumentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add OpenInference instrumentation as an additive layer so Phoenix can categorize spans by type (LLM/CHAIN/TOOL) and group runs by session, while keeping OTel GenAI compatibility for Tempo/Grafana.

**Architecture:** The existing `opentelemetry-instrumentation-openai` stays in place for OTel GenAI spans. We add `openinference-instrumentation-langchain` which hooks into LangGraph's `ainvoke()` to produce OpenInference-typed spans. A `session_id` (UUID v4) is generated per digest run and propagated via `using_attributes(session_id=...)`.

**Tech Stack:** openinference-instrumentation-langchain, openinference-instrumentation (for `using_attributes`), Python 3.11+

---

### Task 1: Add OpenInference dependencies

**Files:**
- Modify: `pyproject.toml:6-21`

- [ ] **Step 1: Add openinference dependencies to pyproject.toml**

Add `openinference-instrumentation-langchain` to the dependencies list. This package transitively pulls in `openinference-instrumentation` (which provides `using_attributes`).

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
    "openinference-instrumentation-langchain",
]
```

- [ ] **Step 2: Install dependencies**

Run: `uv sync --all-extras`
Expected: all dependencies resolve and install successfully, including `openinference-instrumentation-langchain` and its transitive dependency `openinference-instrumentation`.

- [ ] **Step 3: Verify the packages are importable**

Run: `uv run python -c "from openinference.instrumentation.langchain import LangChainInstrumentor; from openinference.instrumentation import using_attributes; print('OK')"`
Expected: prints `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add openinference-instrumentation-langchain"
```

---

### Task 2: Add LangChain instrumentor to telemetry setup

**Files:**
- Modify: `src/reddit_digest/telemetry.py:62-65`
- Test: `tests/test_telemetry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_telemetry.py` (or append to it if it exists):

```python
from unittest.mock import patch, MagicMock
import os
import pytest

from reddit_digest.telemetry import setup_telemetry, _initialized


@pytest.fixture(autouse=True)
def reset_telemetry():
    """Reset telemetry state between tests."""
    import reddit_digest.telemetry as mod
    mod._initialized = False
    yield
    mod._initialized = False


@patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"})
@patch("reddit_digest.telemetry.BatchSpanProcessor")
@patch("reddit_digest.telemetry.OTLPSpanExporter")
@patch("reddit_digest.telemetry.OTLPMetricExporter")
@patch("reddit_digest.telemetry.PeriodicExportingMetricReader")
def test_setup_telemetry_instruments_langchain(
    mock_metric_reader, mock_metric_exp, mock_span_exp, mock_processor
):
    with patch(
        "openinference.instrumentation.langchain.LangChainInstrumentor"
    ) as mock_lc:
        mock_instance = MagicMock()
        mock_lc.return_value = mock_instance
        setup_telemetry()
        mock_instance.instrument.assert_called_once()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_telemetry.py::test_setup_telemetry_instruments_langchain -v`
Expected: FAIL — `LangChainInstrumentor` is not called yet in `setup_telemetry()`.

- [ ] **Step 3: Add LangChainInstrumentor to telemetry.py**

In `src/reddit_digest/telemetry.py`, after the `OpenAIInstrumentor().instrument()` call (line 65), add:

```python
    from openinference.instrumentation.langchain import LangChainInstrumentor

    LangChainInstrumentor().instrument()
```

The imports section at the top of `setup_telemetry()` needs refactoring to use lazy imports inside the function. The full block after `OpenAIInstrumentor().instrument()` should be:

```python
    # Auto-instrumentation for OpenAI SDK (used by langchain-openai)
    from opentelemetry.instrumentation.openai import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()

    # OpenInference instrumentation for LangChain/LangGraph
    # Adds span.kind (CHAIN/LLM/TOOL) attributes for Phoenix
    from openinference.instrumentation.langchain import LangChainInstrumentor

    LangChainInstrumentor().instrument()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_telemetry.py::test_setup_telemetry_instruments_langchain -v`
Expected: PASS

- [ ] **Step 5: Run all tests to check for regressions**

Run: `uv run pytest -v --tb=short`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add src/reddit_digest/telemetry.py tests/test_telemetry.py
git commit -m "feat(telemetry): add OpenInference LangChain instrumentor"
```

---

### Task 3: Add session ID per digest run

**Files:**
- Modify: `src/reddit_digest/main.py:21-53`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_main.py` (create if it doesn't exist):

```python
from unittest.mock import patch, MagicMock, AsyncMock
import pytest


@pytest.mark.asyncio
@patch("reddit_digest.main.build_digest_graph")
@patch("reddit_digest.main.get_tracer")
@patch("reddit_digest.main.get_meter")
async def test_run_digest_uses_session_id(mock_meter, mock_tracer, mock_build):
    """run_digest should wrap graph invocation with using_attributes(session_id=...)."""
    from reddit_digest.main import run_digest

    # Setup mocks
    mock_meter_instance = MagicMock()
    mock_meter.return_value = mock_meter_instance
    mock_meter_instance.create_counter.return_value = MagicMock()
    mock_meter_instance.create_histogram.return_value = MagicMock()

    mock_span = MagicMock()
    mock_tracer_instance = MagicMock()
    mock_tracer.return_value = mock_tracer_instance
    mock_tracer_instance.start_as_current_span.return_value.__enter__ = lambda _: mock_span
    mock_tracer_instance.start_as_current_span.return_value.__exit__ = MagicMock(return_value=False)

    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {"delivered_ids": []}
    mock_build.return_value = mock_graph

    settings = MagicMock()
    settings.reddit_subreddits = ["r/test"]
    settings.digest_cron = "0 8 * * *"
    db_conn = MagicMock()

    with patch("reddit_digest.main.using_attributes") as mock_using:
        mock_using.return_value.__enter__ = MagicMock()
        mock_using.return_value.__exit__ = MagicMock(return_value=False)
        await run_digest(settings, db_conn)

        mock_using.assert_called_once()
        call_kwargs = mock_using.call_args
        session_id = call_kwargs.kwargs.get("session_id") or call_kwargs[1].get("session_id")
        assert session_id is not None
        assert len(session_id) == 36  # UUID v4 format
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_main.py::test_run_digest_uses_session_id -v`
Expected: FAIL — `using_attributes` is not imported/used in `main.py` yet.

- [ ] **Step 3: Add session ID to run_digest**

In `src/reddit_digest/main.py`, add the import at the top:

```python
from uuid import uuid4

from openinference.instrumentation import using_attributes
```

Then modify the `run_digest` function to wrap the graph invocation with `using_attributes`:

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

    start = time.monotonic()
    session_id = str(uuid4())
    logger.info("Running scheduled digest (session_id=%s)...", session_id)

    with tracer.start_as_current_span("digest.run") as span:
        span.set_attribute("digest.subreddits", settings.reddit_subreddits)
        span.set_attribute("digest.cron_expression", settings.digest_cron)
        span.set_attribute("session.id", session_id)
        try:
            graph = build_digest_graph(settings, db_conn)
            with using_attributes(session_id=session_id):
                result = await graph.ainvoke(
                    {"subreddits": settings.reddit_subreddits}
                )
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

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_main.py::test_run_digest_uses_session_id -v`
Expected: PASS

- [ ] **Step 5: Run all tests to check for regressions**

Run: `uv run pytest -v --tb=short`
Expected: all tests pass

- [ ] **Step 6: Run lint**

Run: `uv run ruff check src/ tests/ && uv run ruff format src/ tests/`
Expected: no errors

- [ ] **Step 7: Commit**

```bash
git add src/reddit_digest/main.py tests/test_main.py
git commit -m "feat(telemetry): add OpenInference session ID per digest run"
```

---

### Task 4: Integration verification with observability stack

**Files:** None (manual verification)

- [ ] **Step 1: Rebuild and run the agent with the observability stack**

```bash
cd docker-compose/observability-stack
docker compose up --build agent -d
```

Wait for the agent to finish (`docker compose logs -f agent`).

- [ ] **Step 2: Verify spans in Phoenix**

Open http://localhost:6006. Check:
- Traces tab: spans should show `openinference.span.kind` values (CHAIN, LLM, TOOL)
- The trace tree should show the LangGraph pipeline with typed nodes
- Sessions tab: a session entry should appear with the UUID from the agent logs

- [ ] **Step 3: Verify spans in Grafana/Tempo**

Open http://localhost:3000. Navigate to Explore → Tempo. Check:
- The `digest.run` trace still shows with all child spans
- `openai.chat` spans from the OTel GenAI instrumentation are still present
- The `session.id` attribute is visible on the root span

- [ ] **Step 4: Commit final state**

If any adjustments were needed, commit them. Then push:

```bash
git push origin feature/observability-stack
```
