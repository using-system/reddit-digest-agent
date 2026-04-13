# MCP Reddit Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace direct Reddit scraping (`curl_cffi`) with the reddit-mcp-server via MCP stdio transport in anonymous mode.

**Architecture:** A new MCP client in `collector.py` launches `npx reddit-mcp-server` as a subprocess, calls `get_top_posts` and `get_post_comments` tools, and a dedicated `mcp_parser.py` module parses text responses into `RedditPost` objects. Native OTel instrumentation via `opentelemetry-instrumentation-mcp`.

**Tech Stack:** `mcp` (Python SDK), `opentelemetry-instrumentation-mcp`, Node.js/npx (runtime for MCP server)

**Spec:** `docs/superpowers/specs/2026-04-13-mcp-reddit-source-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/reddit_digest/nodes/mcp_parser.py` | Create | Parse MCP text responses into `RedditPost` fields and comment lists |
| `tests/test_mcp_parser.py` | Create | Unit tests for parser with fixture text data |
| `src/reddit_digest/nodes/collector.py` | Rewrite | MCP client lifecycle, tool calls, rate limiting |
| `tests/test_collector.py` | Rewrite | Mock MCP session, verify orchestration |
| `src/reddit_digest/telemetry.py` | Modify | Add `McpInstrumentor().instrument()` |
| `tests/test_telemetry.py` | Modify | Assert `McpInstrumentor` is called |
| `src/reddit_digest/config.py` | Modify | Remove `reddit_fetch_delay` |
| `tests/test_config.py` | Modify | Remove `reddit_fetch_delay` assertions if any |
| `tests/conftest.py` | Modify | Remove `reddit_fetch_delay` from settings fixture |
| `pyproject.toml` | Modify | Add `mcp`, `opentelemetry-instrumentation-mcp`; remove `curl-cffi` |

---

### Task 1: Update dependencies in pyproject.toml

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update dependencies**

In `pyproject.toml`, replace `curl-cffi` with `mcp` and `opentelemetry-instrumentation-mcp`:

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
    "mcp",
    "opentelemetry-api",
    "opentelemetry-sdk",
    "opentelemetry-exporter-otlp-proto-http",
    "opentelemetry-instrumentation-openai",
    "opentelemetry-instrumentation-httpx",
    "opentelemetry-instrumentation-sqlite3",
    "opentelemetry-instrumentation-mcp",
]
```

Note: `curl-cffi` is removed, `mcp` and `opentelemetry-instrumentation-mcp` are added.

- [ ] **Step 2: Sync dependencies**

Run: `uv sync --all-extras`
Expected: dependencies install successfully, `mcp` and `opentelemetry-instrumentation-mcp` are resolved.

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): replace curl-cffi with mcp and otel-mcp instrumentation"
```

---

### Task 2: Create MCP response parser with tests (TDD)

**Files:**
- Create: `src/reddit_digest/nodes/mcp_parser.py`
- Create: `tests/test_mcp_parser.py`

To write accurate parser code, we first need to capture real MCP server output. The parser tests will use these fixtures.

- [ ] **Step 1: Capture real MCP server output**

Run the MCP server manually to get real output for `get_top_posts` and `get_post_comments`. Use the `mcp` CLI or a quick script:

```bash
npx reddit-mcp-server
```

Call `get_top_posts` with `{"subreddit": "python", "limit": 2}` and `get_post_comments` with a post ID from the results. Save the raw text output as test fixtures. If `npx` is not available, use `WebFetch` to fetch example output from the server's tests or source code:
- `https://raw.githubusercontent.com/jordanburke/reddit-mcp-server/main/src/tools/post-tools.ts` (look at the formatting template strings)
- `https://raw.githubusercontent.com/jordanburke/reddit-mcp-server/main/src/tools/comment-tools.ts`

Use the formatting patterns found in the source to craft realistic fixture strings.

- [ ] **Step 2: Write failing tests for `parse_top_posts`**

Create `tests/test_mcp_parser.py`:

```python
import pytest

from reddit_digest.nodes.mcp_parser import parse_top_posts, parse_post_comments


# Fixture: realistic output from get_top_posts (adapt after Step 1)
TOP_POSTS_FIXTURE = """\
Top Posts from r/python (hot)

1. Building a CLI Tool with Click
   Author: u/dev_user
   Score: 234 | Comments: 45
   Link: https://reddit.com/r/python/comments/abc123/building_a_cli_tool/
   https://blog.example.com/click-cli

2. Python 3.13 Release Notes
   Author: u/py_news
   Score: 892 | Comments: 120
   Link: https://reddit.com/r/python/comments/def456/python_313_release/
   Self post content here about the release.
"""

COMMENTS_FIXTURE = """\
Post: Building a CLI Tool with Click
Author: u/dev_user | Subreddit: r/python
Score: 234 | Upvote Ratio: 0.95
Created: 2026-04-12T10:00:00Z
Permalink: /r/python/comments/abc123/building_a_cli_tool/

Content:
Check out my new CLI tool built with Click...

Comments (sorted by best):

u/commenter1 | Score: 89 | 2026-04-12T11:00:00Z
Great tutorial! I've been looking for something like this.

  u/dev_user [OP] | Score: 45 | 2026-04-12T11:30:00Z
  Thanks! Let me know if you have questions.

u/commenter2 | Score: 67 | 2026-04-12T12:00:00Z
Have you considered using Typer instead? It's built on Click.

u/commenter3 | Score: 23 | 2026-04-12T13:00:00Z
Nice work, bookmarked for later.
"""


class TestParseTopPosts:
    def test_parses_multiple_posts(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert len(posts) == 2

    def test_extracts_title(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[0].title == "Building a CLI Tool with Click"

    def test_extracts_score(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[0].score == 234

    def test_extracts_num_comments(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[0].num_comments == 45

    def test_extracts_reddit_id_from_permalink(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[0].reddit_id == "abc123"

    def test_extracts_url(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        # URL is the external link (not the reddit permalink)
        assert posts[0].url == "https://blog.example.com/click-cli"

    def test_sets_subreddit(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        assert posts[0].subreddit == "python"

    def test_self_post_url_is_permalink(self):
        posts = parse_top_posts(TOP_POSTS_FIXTURE, "python")
        # Post 2 is a self post - url should be the reddit permalink
        assert "def456" in posts[1].url

    def test_empty_input(self):
        posts = parse_top_posts("", "python")
        assert posts == []

    def test_malformed_input(self):
        posts = parse_top_posts("No posts found", "python")
        assert posts == []


class TestParsePostComments:
    def test_extracts_top_level_comments(self):
        comments = parse_post_comments(COMMENTS_FIXTURE)
        assert len(comments) >= 3

    def test_comment_bodies_only(self):
        comments = parse_post_comments(COMMENTS_FIXTURE)
        assert "Great tutorial!" in comments[0]

    def test_empty_input(self):
        comments = parse_post_comments("")
        assert comments == []

    def test_respects_limit(self):
        comments = parse_post_comments(COMMENTS_FIXTURE, limit=2)
        assert len(comments) <= 2
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_mcp_parser.py -v`
Expected: ImportError — `mcp_parser` module does not exist yet.

- [ ] **Step 4: Implement `mcp_parser.py`**

Create `src/reddit_digest/nodes/mcp_parser.py`:

```python
from __future__ import annotations

import logging
import re

from reddit_digest.models import RedditPost

logger = logging.getLogger(__name__)


def parse_top_posts(text: str, subreddit: str) -> list[RedditPost]:
    """Parse the text output of get_top_posts into RedditPost objects."""
    if not text or not text.strip():
        return []

    posts: list[RedditPost] = []
    # Split into numbered post blocks: "1. Title\n   ...\n\n2. Title\n   ..."
    blocks = re.split(r"\n(?=\d+\.\s)", text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # Match "N. Title"
        title_match = re.match(r"\d+\.\s+(.+)", block)
        if not title_match:
            continue

        title = title_match.group(1).strip()

        # Extract score and comments: "Score: 234 | Comments: 45"
        score_match = re.search(r"Score:\s*(\d+)", block)
        comments_match = re.search(r"Comments:\s*(\d+)", block)
        score = int(score_match.group(1)) if score_match else 0
        num_comments = int(comments_match.group(1)) if comments_match else 0

        # Extract permalink: "Link: https://reddit.com/r/.../comments/ID/..."
        link_match = re.search(
            r"Link:\s*(https?://[^\s]+/comments/([^/]+)/[^\s]*)", block
        )
        reddit_id = link_match.group(2) if link_match else ""
        permalink = link_match.group(1) if link_match else ""

        if not reddit_id:
            logger.warning("Could not extract reddit_id from block: %s", block[:80])
            continue

        # Lines after the Link line that aren't metadata are the URL or selftext
        lines = block.split("\n")
        content_lines = []
        past_link = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Link:"):
                past_link = True
                continue
            if past_link and stripped:
                content_lines.append(stripped)

        # Determine if external link or self post
        external_url = ""
        selftext = ""
        if content_lines:
            first_content = content_lines[0]
            if re.match(r"https?://", first_content):
                external_url = first_content
                selftext = "\n".join(content_lines[1:])
            else:
                selftext = "\n".join(content_lines)

        url = external_url if external_url else permalink

        posts.append(
            RedditPost(
                reddit_id=reddit_id,
                subreddit=subreddit,
                title=title,
                url=url,
                score=score,
                num_comments=num_comments,
                selftext=selftext,
                created_utc=0.0,
                top_comments=[],
            )
        )

    return posts


def parse_post_comments(text: str, limit: int | None = None) -> list[str]:
    """Parse the text output of get_post_comments into comment body strings.

    Extracts all comment bodies (top-level and replies).
    """
    if not text or not text.strip():
        return []

    comments: list[str] = []

    # Comments section starts after "Comments (sorted by ...)"
    comments_section_match = re.search(r"Comments\s*\(sorted by[^)]*\):\s*\n", text)
    if not comments_section_match:
        return []

    comments_text = text[comments_section_match.end() :]

    # Each comment starts with "u/username" (possibly indented)
    # The body is on the next line(s) until the next "u/" or end
    comment_blocks = re.split(r"\n(?=\s*u/\w+)", comments_text)

    for block in comment_blocks:
        block = block.strip()
        if not block:
            continue

        # First line is metadata: "u/user | Score: N | date"
        lines = block.split("\n")
        if len(lines) < 2:
            continue

        # Body is everything after the first line
        body = "\n".join(line.strip() for line in lines[1:] if line.strip())
        if body:
            comments.append(body)

        if limit and len(comments) >= limit:
            break

    return comments
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_mcp_parser.py -v`
Expected: All tests PASS.

**Important:** The fixture strings above are approximations based on the MCP server source code. After Step 1 (capturing real output), update both the fixtures in the test file AND the regex patterns in `mcp_parser.py` to match the actual format. The test structure stays the same.

- [ ] **Step 6: Commit**

```bash
git add src/reddit_digest/nodes/mcp_parser.py tests/test_mcp_parser.py
git commit -m "feat(collector): add MCP response parser with tests"
```

---

### Task 3: Remove `reddit_fetch_delay` from config

**Files:**
- Modify: `src/reddit_digest/config.py:39` (remove `reddit_fetch_delay` field)
- Modify: `tests/conftest.py` (remove from settings fixture if present)

- [ ] **Step 1: Remove `reddit_fetch_delay` from Settings**

In `src/reddit_digest/config.py`, remove line 39:

```python
    reddit_fetch_delay: int = 200
```

- [ ] **Step 2: Update conftest.py if needed**

Check `tests/conftest.py` — the `settings` fixture does not include `reddit_fetch_delay` (it uses the default), so no change needed.

- [ ] **Step 3: Run config tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: All tests PASS (none test `reddit_fetch_delay`).

- [ ] **Step 4: Commit**

```bash
git add src/reddit_digest/config.py
git commit -m "refactor(config): remove reddit_fetch_delay (replaced by MCP rate limit)"
```

---

### Task 4: Add McpInstrumentor to telemetry (TDD)

**Files:**
- Modify: `src/reddit_digest/telemetry.py:63-68`
- Modify: `tests/test_telemetry.py:66-100`

- [ ] **Step 1: Write failing test**

In `tests/test_telemetry.py`, update the existing `test_setup_telemetry_instruments_openai` test to also assert `McpInstrumentor` is called. Rename it to `test_setup_telemetry_instruments_all`:

```python
@patch.dict(os.environ, {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4318"})
def test_setup_telemetry_instruments_all():
    """All instrumentors must be called during setup_telemetry()."""
    import reddit_digest.telemetry as tel

    mock_openai = MagicMock()
    mock_openai_cls = MagicMock(return_value=mock_openai)
    mock_mcp = MagicMock()
    mock_mcp_cls = MagicMock(return_value=mock_mcp)

    patches = [
        patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"),
        patch(
            "opentelemetry.exporter.otlp.proto.http.metric_exporter.OTLPMetricExporter"
        ),
        patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
        patch("opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader"),
        patch(
            "opentelemetry.instrumentation.openai.OpenAIInstrumentor", mock_openai_cls
        ),
        patch("opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor"),
        patch("opentelemetry.instrumentation.sqlite3.SQLite3Instrumentor"),
        patch("opentelemetry.instrumentation.mcp.McpInstrumentor", mock_mcp_cls),
    ]

    tel._initialized = False
    with (
        patches[0],
        patches[1],
        patches[2],
        patches[3],
        patches[4],
        patches[5],
        patches[6],
        patches[7],
    ):
        tel.setup_telemetry()

    mock_openai.instrument.assert_called_once()
    mock_mcp.instrument.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_telemetry.py::test_setup_telemetry_instruments_all -v`
Expected: FAIL — `McpInstrumentor` is not imported or called in `telemetry.py`.

- [ ] **Step 3: Add McpInstrumentor to telemetry.py**

In `src/reddit_digest/telemetry.py`, after the SQLite3Instrumentor block (line 72), add:

```python
    from opentelemetry.instrumentation.mcp import McpInstrumentor

    McpInstrumentor().instrument()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_telemetry.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/reddit_digest/telemetry.py tests/test_telemetry.py
git commit -m "feat(telemetry): add MCP instrumentation for tool call tracing"
```

---

### Task 5: Rewrite collector with MCP client (TDD)

**Files:**
- Rewrite: `src/reddit_digest/nodes/collector.py`
- Rewrite: `tests/test_collector.py`

- [ ] **Step 1: Write failing collector tests**

Rewrite `tests/test_collector.py` to mock the MCP session:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reddit_digest.nodes.collector import collect_posts


def _make_top_posts_response(subreddit: str, posts: list[dict]) -> str:
    """Build a fake MCP get_top_posts text response."""
    lines = [f"Top Posts from r/{subreddit} (hot)\n"]
    for i, p in enumerate(posts, 1):
        lines.append(f"{i}. {p['title']}")
        lines.append(f"   Author: u/{p.get('author', 'testuser')}")
        lines.append(f"   Score: {p['score']} | Comments: {p['num_comments']}")
        lines.append(
            f"   Link: https://reddit.com/r/{subreddit}/comments/{p['id']}/{p['title'].lower().replace(' ', '_')}/"
        )
        if p.get("url"):
            lines.append(f"   {p['url']}")
        lines.append("")
    return "\n".join(lines)


def _make_comments_response(comments: list[str]) -> str:
    """Build a fake MCP get_post_comments text response."""
    lines = [
        "Post: Test Post",
        "Author: u/test | Subreddit: r/python",
        "Score: 42 | Upvote Ratio: 0.95",
        "Created: 2026-04-12T10:00:00Z",
        "Permalink: /r/python/comments/abc123/test_post/",
        "",
        "Content:",
        "Test content",
        "",
        "Comments (sorted by best):",
        "",
    ]
    for i, c in enumerate(comments):
        lines.append(f"u/commenter{i} | Score: {10 - i} | 2026-04-12T10:00:00Z")
        lines.append(c)
        lines.append("")
    return "\n".join(lines)


def _make_tool_result(text: str) -> MagicMock:
    """Simulate an MCP CallToolResult."""
    content_item = MagicMock()
    content_item.text = text
    result = MagicMock()
    result.content = [content_item]
    return result


@pytest.fixture
def mock_mcp_session():
    """Mock the MCP client session context managers."""
    session = AsyncMock()
    # list_tools returns available tools
    tool1 = MagicMock()
    tool1.name = "get_top_posts"
    tool2 = MagicMock()
    tool2.name = "get_post_comments"
    tool3 = MagicMock()
    tool3.name = "create_post"
    session.list_tools.return_value = MagicMock(tools=[tool1, tool2, tool3])

    return session


async def test_collect_posts_basic(mock_mcp_session, settings):
    settings.reddit_comments_limit = 0
    posts_data = [
        {"id": "abc123", "title": "Test Post", "score": 42, "num_comments": 5},
    ]
    top_posts_text = _make_top_posts_response("python", posts_data)
    mock_mcp_session.call_tool.return_value = _make_tool_result(top_posts_text)

    mock_conn = MagicMock()
    mock_conn.connect = AsyncMock(return_value=mock_mcp_session)
    mock_conn.close = AsyncMock()
    with patch(
        "reddit_digest.nodes.collector._MCPConnection",
        return_value=mock_conn,
    ):
        state = {"subreddits": ["python"]}
        result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 1
    assert result["raw_posts"][0].reddit_id == "abc123"
    assert result["raw_posts"][0].subreddit == "python"


async def test_collect_posts_with_comments(mock_mcp_session, settings):
    settings.reddit_comments_limit = 3
    posts_data = [
        {"id": "abc123", "title": "Test Post", "score": 42, "num_comments": 5},
    ]
    top_posts_text = _make_top_posts_response("python", posts_data)
    comments_text = _make_comments_response(["Great post", "I agree", "Nice work"])

    mock_mcp_session.call_tool.side_effect = [
        _make_tool_result(top_posts_text),
        _make_tool_result(comments_text),
    ]

    mock_conn = MagicMock()
    mock_conn.connect = AsyncMock(return_value=mock_mcp_session)
    mock_conn.close = AsyncMock()
    with patch(
        "reddit_digest.nodes.collector._MCPConnection",
        return_value=mock_conn,
    ):
        state = {"subreddits": ["python"]}
        result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 1
    assert len(result["raw_posts"][0].top_comments) == 3
    assert "Great post" in result["raw_posts"][0].top_comments[0]


async def test_collect_posts_multiple_subreddits(mock_mcp_session, settings):
    settings.reddit_comments_limit = 0
    posts_py = [{"id": "py1", "title": "Py Post", "score": 10, "num_comments": 2}]
    posts_ml = [{"id": "ml1", "title": "ML Post", "score": 20, "num_comments": 4}]

    mock_mcp_session.call_tool.side_effect = [
        _make_tool_result(_make_top_posts_response("python", posts_py)),
        _make_tool_result(_make_top_posts_response("machinelearning", posts_ml)),
    ]

    mock_conn = MagicMock()
    mock_conn.connect = AsyncMock(return_value=mock_mcp_session)
    mock_conn.close = AsyncMock()
    with patch(
        "reddit_digest.nodes.collector._MCPConnection",
        return_value=mock_conn,
    ):
        state = {"subreddits": ["python", "machinelearning"]}
        result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 2
    subreddits = {p.subreddit for p in result["raw_posts"]}
    assert subreddits == {"python", "machinelearning"}


async def test_collect_posts_error_one_subreddit(mock_mcp_session, settings):
    settings.reddit_comments_limit = 0
    good_text = _make_top_posts_response(
        "python", [{"id": "ok1", "title": "OK", "score": 5, "num_comments": 1}]
    )

    mock_mcp_session.call_tool.side_effect = [
        _make_tool_result(good_text),
        Exception("MCP error"),
    ]

    mock_conn = MagicMock()
    mock_conn.connect = AsyncMock(return_value=mock_mcp_session)
    mock_conn.close = AsyncMock()
    with patch(
        "reddit_digest.nodes.collector._MCPConnection",
        return_value=mock_conn,
    ):
        state = {"subreddits": ["python", "badsubreddit"]}
        result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 1


async def test_collect_posts_passes_sort_params(mock_mcp_session, settings):
    settings.reddit_comments_limit = 0
    settings.reddit_sort = "top"
    settings.reddit_time_filter = "week"
    posts_data = [{"id": "t1", "title": "Top", "score": 100, "num_comments": 10}]
    mock_mcp_session.call_tool.return_value = _make_tool_result(
        _make_top_posts_response("python", posts_data)
    )

    mock_conn = MagicMock()
    mock_conn.connect = AsyncMock(return_value=mock_mcp_session)
    mock_conn.close = AsyncMock()
    with patch(
        "reddit_digest.nodes.collector._MCPConnection",
        return_value=mock_conn,
    ):
        state = {"subreddits": ["python"]}
        await collect_posts(state, settings)

    call_args = mock_mcp_session.call_tool.call_args_list[0]
    assert call_args.kwargs["arguments"]["time_filter"] == "week"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_collector.py -v`
Expected: FAIL — `_MCPConnection` does not exist, collector still uses `curl_cffi`.

- [ ] **Step 3: Rewrite collector.py**

Replace `src/reddit_digest/nodes/collector.py` entirely:

```python
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost
from reddit_digest.nodes.mcp_parser import parse_post_comments, parse_top_posts
from reddit_digest.telemetry import get_meter

logger = logging.getLogger(__name__)

MCP_RATE_LIMIT_DELAY = 6  # seconds between calls (~10 req/min anonymous)

SERVER_PARAMS = StdioServerParameters(
    command="npx",
    args=["reddit-mcp-server"],
    env={"REDDIT_AUTH_MODE": "anonymous"},
)


class _MCPConnection:
    """Manages MCP client session and transport lifecycle."""

    def __init__(self) -> None:
        self.session: ClientSession | None = None
        self._transport_cm: Any = None
        self._session_cm: Any = None

    async def connect(self) -> ClientSession:
        self._transport_cm = stdio_client(SERVER_PARAMS)
        read_stream, write_stream = await self._transport_cm.__aenter__()
        self._session_cm = ClientSession(read_stream, write_stream)
        self.session = await self._session_cm.__aenter__()
        await self.session.initialize()
        return self.session

    async def close(self) -> None:
        if self._session_cm:
            await self._session_cm.__aexit__(None, None, None)
        if self._transport_cm:
            await self._transport_cm.__aexit__(None, None, None)


async def _call_tool_with_delay(
    session: ClientSession,
    tool_name: str,
    arguments: dict[str, Any],
    last_call_time: float,
) -> tuple[str, float]:
    """Call an MCP tool, respecting rate limits. Returns (text, new_last_call_time)."""
    elapsed = time.monotonic() - last_call_time
    if elapsed < MCP_RATE_LIMIT_DELAY:
        await asyncio.sleep(MCP_RATE_LIMIT_DELAY - elapsed)

    result = await session.call_tool(tool_name, arguments=arguments)
    now = time.monotonic()

    text = ""
    if result.content:
        text = result.content[0].text
    return text, now


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
    conn = _MCPConnection()
    session = await conn.connect()

    try:
        last_call_time = 0.0

        for sub_name in state["subreddits"]:
            sub_start = time.monotonic()
            sub_post_count = 0
            try:
                # Fetch top posts
                arguments: dict[str, Any] = {
                    "subreddit": sub_name,
                    "limit": settings.reddit_limit,
                }
                if settings.reddit_sort == "top":
                    arguments["time_filter"] = settings.reddit_time_filter

                text, last_call_time = await _call_tool_with_delay(
                    session, "get_top_posts", arguments, last_call_time
                )
                posts = parse_top_posts(text, sub_name)

                # Fetch comments for each post
                for post in posts:
                    if settings.reddit_comments_limit > 0:
                        try:
                            comments_text, last_call_time = (
                                await _call_tool_with_delay(
                                    session,
                                    "get_post_comments",
                                    {
                                        "post_id": post.reddit_id,
                                        "subreddit": sub_name,
                                        "limit": settings.reddit_comments_limit,
                                    },
                                    last_call_time,
                                )
                            )
                            post.top_comments = parse_post_comments(
                                comments_text, limit=settings.reddit_comments_limit
                            )
                        except Exception:
                            logger.warning(
                                "Failed to fetch comments for %s in r/%s",
                                post.reddit_id,
                                sub_name,
                            )

                    all_posts.append(post)
                    sub_post_count += 1
            except Exception:
                logger.exception("Failed to fetch posts from r/%s", sub_name)
            finally:
                elapsed = time.monotonic() - sub_start
                fetch_histogram.record(elapsed, {"subreddit": sub_name})
                posts_counter.add(sub_post_count, {"subreddit": sub_name})
    finally:
        await conn.close()

    logger.info(
        "Collected %d posts from %d subreddits",
        len(all_posts),
        len(state["subreddits"]),
    )
    return {"raw_posts": all_posts}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_collector.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run all tests to check for regressions**

Run: `uv run pytest -v --tb=short`
Expected: All tests PASS. No import errors from removed `curl-cffi`.

- [ ] **Step 6: Lint and format**

Run: `uv run ruff check src/ tests/ && uv run ruff format src/ tests/`
Expected: No errors.

- [ ] **Step 7: Commit**

```bash
git add src/reddit_digest/nodes/collector.py tests/test_collector.py
git commit -m "feat(collector): replace curl-cffi scraping with MCP reddit server"
```

---

### Task 6: Final integration verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: All tests PASS.

- [ ] **Step 2: Lint check**

Run: `uv run ruff check src/ tests/`
Expected: No issues.

- [ ] **Step 3: Verify no curl-cffi references remain**

Run: `grep -r "curl_cffi\|cffi_requests" src/ tests/`
Expected: No matches.

- [ ] **Step 4: Commit any remaining fixes**

Only if Steps 1-3 revealed issues. Otherwise skip.
