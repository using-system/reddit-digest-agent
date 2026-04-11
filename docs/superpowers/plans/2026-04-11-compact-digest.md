# Compact Digest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the digest pipeline to send one compact Telegram message per subreddit with numbered threads, hybrid filtering (metrics + LLM scoring), comment-aware summaries, and per-thread thumbs up/down buttons.

**Architecture:** Add a `scorer` node between filterer and summarizer for LLM-based relevance scoring. Add a `mark_all_seen` node at the end to mark all fetched posts in the DB. Rewrite the deliverer to group summaries by subreddit into single messages. Change feedback to use `up`/`down` callback format.

**Tech Stack:** Python 3.11+, LangGraph, LangChain (ChatOpenAI), python-telegram-bot, aiosqlite, pydantic, curl_cffi

---

### Task 1: Config — Update Settings and .env.example

**Files:**
- Modify: `src/reddit_digest/config.py`
- Modify: `.env.example`
- Modify: `tests/test_config.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing tests for new config fields**

In `tests/test_config.py`, update `test_settings_defaults` to check the new default for `reddit_limit` (5 instead of 20), and add a test for the new settings:

```python
def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot:t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    s = Settings(_env_file=None)
    assert s.reddit_sort == "hot"
    assert s.reddit_limit == 5
    assert s.reddit_comments_limit == 5
    assert s.reddit_min_score == 10
    assert s.reddit_min_comments == 3
    assert s.llm_model == "google/gemini-2.5-flash"
    assert s.digest_cron == "0 8 * * *"
    assert s.digest_language == "fr"


def test_settings_reddit_limit_clamped(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot:t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("REDDIT_LIMIT", "50")
    s = Settings(_env_file=None)
    assert s.reddit_limit == 8


def test_settings_reddit_limit_min(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot:t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("REDDIT_LIMIT", "0")
    s = Settings(_env_file=None)
    assert s.reddit_limit == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `reddit_limit` is still 20, new fields don't exist

- [ ] **Step 3: Update Settings class**

In `src/reddit_digest/config.py`, change the Settings class:

```python
from pydantic import field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Reddit
    reddit_subreddits: list[str] = ["python", "machinelearning", "selfhosted"]
    reddit_sort: str = "hot"
    reddit_limit: int = 5
    reddit_time_filter: str = "day"
    reddit_comments_limit: int = 5
    reddit_min_score: int = 10
    reddit_min_comments: int = 3

    # ... rest unchanged ...

    @field_validator("reddit_limit", mode="before")
    @classmethod
    def clamp_reddit_limit(cls, v: int) -> int:
        return max(1, min(int(v), 8))
```

- [ ] **Step 4: Update conftest.py settings fixture**

In `tests/conftest.py`, update the fixture to include new fields and the new default:

```python
@pytest.fixture
def settings() -> Settings:
    return Settings(
        reddit_subreddits=["python", "machinelearning"],
        reddit_sort="hot",
        reddit_limit=5,
        reddit_time_filter="day",
        reddit_comments_limit=5,
        reddit_min_score=10,
        reddit_min_comments=3,
        openai_api_key="sk-test",
        openai_base_url="https://openrouter.ai/api/v1",
        llm_model="test-model",
        telegram_bot_token="bot:test-token",
        telegram_chat_id="123",
        digest_cron="0 8 * * *",
        digest_language="fr",
        _env_file=None,
    )
```

- [ ] **Step 5: Update .env.example**

Replace `REDDIT_LIMIT=20` with new settings:

```
REDDIT_LIMIT=5
# REDDIT_COMMENTS_LIMIT=5
# REDDIT_MIN_SCORE=10
# REDDIT_MIN_COMMENTS=3
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_config.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/reddit_digest/config.py .env.example tests/test_config.py tests/conftest.py
git commit -m "feat(config): add compact digest settings (limit=5, comments, min_score, min_comments)"
```

---

### Task 2: Models — Update RedditPost and Summary

**Files:**
- Modify: `src/reddit_digest/models.py`

- [ ] **Step 1: Update models**

In `src/reddit_digest/models.py`:

```python
from __future__ import annotations

from pydantic import BaseModel


class RedditPost(BaseModel):
    reddit_id: str
    subreddit: str
    title: str
    url: str
    score: int = 0
    num_comments: int = 0
    selftext: str = ""
    created_utc: float = 0.0
    top_comments: list[str] = []
    relevance_score: int | None = None


class Summary(BaseModel):
    reddit_id: str
    subreddit: str
    summary_text: str


class PostMetadata(BaseModel):
    reddit_id: str
    subreddit: str
    title: str
    url: str
    category: str = ""
    keywords: list[str] = []
```

Key changes:
- `RedditPost`: add `top_comments: list[str] = []` and `relevance_score: int | None = None`
- `Summary`: remove `title`, `category`, `keywords` fields — simplified to just `reddit_id`, `subreddit`, `summary_text`
- `PostMetadata`: unchanged (still needed for feedback graph on existing data)

- [ ] **Step 2: Run all tests to check for breakage**

Run: `uv run pytest -v --tb=short`
Expected: Some tests will fail due to Summary constructor changes (tests pass `title`, `category`, `keywords`). Note which tests fail — we will fix them in later tasks when we rewrite those modules.

- [ ] **Step 3: Commit**

```bash
git add src/reddit_digest/models.py
git commit -m "feat(models): add top_comments and relevance_score to RedditPost, simplify Summary"
```

---

### Task 3: Database — Add status column and rename functions

**Files:**
- Modify: `src/reddit_digest/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for new DB functions**

Replace the content of `tests/test_db.py`:

```python
import pytest

from reddit_digest.db import (
    get_post_by_message_id,
    get_preference_score,
    get_preferences,
    init_db,
    is_post_seen,
    save_reaction,
    save_seen_post,
    update_preference,
)
from reddit_digest.models import RedditPost


@pytest.fixture
async def db():
    conn = await init_db(":memory:")
    yield conn
    await conn.close()


def _make_post(**overrides) -> RedditPost:
    defaults = {
        "reddit_id": "abc123",
        "subreddit": "python",
        "title": "Test Post",
        "url": "https://reddit.com/r/python/abc123",
    }
    return RedditPost(**{**defaults, **overrides})


async def test_tables_created(db):
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]
    assert "preferences" in tables
    assert "reactions" in tables
    assert "sent_posts" in tables


async def test_save_seen_post_default_status(db):
    post = _make_post()
    assert not await is_post_seen(db, post.reddit_id)
    await save_seen_post(db, post, status="seen")
    assert await is_post_seen(db, post.reddit_id)


async def test_save_seen_post_sent_status(db):
    post = _make_post()
    await save_seen_post(db, post, telegram_message_id=100, status="sent")
    assert await is_post_seen(db, post.reddit_id)
    cursor = await db.execute(
        "SELECT status, telegram_message_id FROM sent_posts WHERE reddit_id = ?",
        (post.reddit_id,),
    )
    row = await cursor.fetchone()
    assert row[0] == "sent"
    assert row[1] == 100


async def test_get_post_by_message_id(db):
    post = _make_post()
    await save_seen_post(db, post, telegram_message_id=200, status="sent")
    meta = await get_post_by_message_id(db, 200)
    assert meta is not None
    assert meta.reddit_id == "abc123"


async def test_get_post_by_message_id_not_found(db):
    meta = await get_post_by_message_id(db, 999)
    assert meta is None


async def test_save_reaction(db):
    post = _make_post()
    await save_seen_post(db, post, telegram_message_id=300, status="sent")
    await save_reaction(db, 300, "up")
    cursor = await db.execute(
        "SELECT reaction_type FROM reactions WHERE telegram_message_id = 300"
    )
    row = await cursor.fetchone()
    assert row[0] == "up"


async def test_update_preference_insert(db):
    await update_preference(db, "python", "web", 1)
    score = await get_preference_score(db, "python", "web")
    assert score == 1


async def test_update_preference_upsert(db):
    await update_preference(db, "python", "web", 1)
    await update_preference(db, "python", "web", 1)
    await update_preference(db, "python", "web", -2)
    score = await get_preference_score(db, "python", "web")
    assert score == 0


async def test_get_preferences(db):
    await update_preference(db, "python", "web", 3)
    await update_preference(db, "ml", "nlp", -1)
    prefs = await get_preferences(db)
    assert len(prefs) == 2
    by_topic = {p["topic"]: p for p in prefs}
    assert by_topic["web"]["score"] == 3
    assert by_topic["nlp"]["score"] == -1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL — `is_post_seen` and `save_seen_post` don't exist

- [ ] **Step 3: Update db.py**

Replace `src/reddit_digest/db.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from reddit_digest.models import PostMetadata, RedditPost

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sent_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reddit_id TEXT UNIQUE NOT NULL,
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    telegram_message_id INTEGER,
    category TEXT DEFAULT '',
    keywords TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'sent',
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_message_id INTEGER NOT NULL,
    reaction_type TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subreddit TEXT NOT NULL,
    topic TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subreddit, topic)
);
"""


async def init_db(db_path: str = "digest.db") -> aiosqlite.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    await conn.executescript(_SCHEMA)
    # Migration: add status column if missing (existing DBs)
    try:
        await conn.execute("SELECT status FROM sent_posts LIMIT 1")
    except Exception:
        await conn.execute(
            "ALTER TABLE sent_posts ADD COLUMN status TEXT NOT NULL DEFAULT 'sent'"
        )
        await conn.commit()
    return conn


async def is_post_seen(conn: aiosqlite.Connection, reddit_id: str) -> bool:
    cursor = await conn.execute(
        "SELECT 1 FROM sent_posts WHERE reddit_id = ?", (reddit_id,)
    )
    return await cursor.fetchone() is not None


async def save_seen_post(
    conn: aiosqlite.Connection,
    post: RedditPost,
    *,
    telegram_message_id: int | None = None,
    status: str = "seen",
) -> None:
    await conn.execute(
        """INSERT OR IGNORE INTO sent_posts
           (reddit_id, subreddit, title, url, telegram_message_id, status, sent_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            post.reddit_id,
            post.subreddit,
            post.title,
            post.url,
            telegram_message_id,
            status,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await conn.commit()


async def get_post_by_message_id(
    conn: aiosqlite.Connection, telegram_message_id: int
) -> PostMetadata | None:
    cursor = await conn.execute(
        """SELECT reddit_id, subreddit, title, url, category, keywords
           FROM sent_posts WHERE telegram_message_id = ?""",
        (telegram_message_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return PostMetadata(
        reddit_id=row[0],
        subreddit=row[1],
        title=row[2],
        url=row[3],
        category=row[4],
        keywords=json.loads(row[5]),
    )


async def save_reaction(
    conn: aiosqlite.Connection, telegram_message_id: int, reaction_type: str
) -> None:
    await conn.execute(
        "INSERT INTO reactions (telegram_message_id, reaction_type) VALUES (?, ?)",
        (telegram_message_id, reaction_type),
    )
    await conn.commit()


async def get_preferences(conn: aiosqlite.Connection) -> list[dict]:
    cursor = await conn.execute("SELECT subreddit, topic, score FROM preferences")
    rows = await cursor.fetchall()
    return [{"subreddit": r[0], "topic": r[1], "score": r[2]} for r in rows]


async def update_preference(
    conn: aiosqlite.Connection, subreddit: str, topic: str, score_delta: int
) -> None:
    await conn.execute(
        """INSERT INTO preferences (subreddit, topic, score, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(subreddit, topic)
           DO UPDATE SET score = score + ?, updated_at = ?""",
        (
            subreddit,
            topic,
            score_delta,
            datetime.now(timezone.utc).isoformat(),
            score_delta,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await conn.commit()


async def get_preference_score(
    conn: aiosqlite.Connection, subreddit: str, topic: str
) -> int:
    cursor = await conn.execute(
        "SELECT score FROM preferences WHERE subreddit = ? AND topic = ?",
        (subreddit, topic),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/reddit_digest/db.py tests/test_db.py
git commit -m "feat(db): add status column to sent_posts, rename to is_post_seen/save_seen_post"
```

---

### Task 4: Collector — Fetch top comments per post

**Files:**
- Modify: `src/reddit_digest/nodes/collector.py`
- Modify: `tests/test_collector.py`

- [ ] **Step 1: Write failing test for comment fetching**

Add to `tests/test_collector.py`:

```python
def _make_comments_response(comments, status_code=200):
    """Simulate Reddit comments endpoint which returns [post_data, comments_data]."""
    children = [
        {"kind": "t1", "data": {"body": c, "score": 10 - i}}
        for i, c in enumerate(comments)
    ]
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = [
        {"data": {"children": []}},  # post listing
        {"data": {"children": children}},  # comments listing
    ]
    resp.raise_for_status = MagicMock()
    return resp


async def test_collect_posts_fetches_comments(mock_session, settings):
    settings.reddit_comments_limit = 3
    posts = [_make_post("id1", "python")]
    comments_resp = _make_comments_response(["Great post", "I agree", "Nice", "Meh"])

    mock_session.get.side_effect = [
        _make_response([]),       # homepage
        _make_response(posts),    # subreddit listing
        comments_resp,            # comments for id1
    ]

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 1
    assert len(result["raw_posts"][0].top_comments) == 3
    assert result["raw_posts"][0].top_comments[0] == "Great post"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_collector.py::test_collect_posts_fetches_comments -v`
Expected: FAIL — `top_comments` is empty because collector doesn't fetch comments yet

- [ ] **Step 3: Update collector to fetch comments**

Replace `src/reddit_digest/nodes/collector.py`:

```python
from __future__ import annotations

import logging
import time
from typing import Any

from curl_cffi import requests as cffi_requests

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost

logger = logging.getLogger(__name__)


def _fetch_top_comments(
    session: cffi_requests.Session,
    subreddit: str,
    post_id: str,
    limit: int,
) -> list[str]:
    url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json"
    resp = session.get(url, params={"limit": limit, "raw_json": 1}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    # Reddit returns [post_listing, comments_listing]
    if len(data) < 2:
        return []
    children = data[1]["data"]["children"]
    comments = []
    for child in children:
        if child["kind"] != "t1":
            continue
        body = child["data"].get("body", "").strip()
        if body:
            comments.append(body)
        if len(comments) >= limit:
            break
    return comments


async def collect_posts(state: dict[str, Any], settings: Settings) -> dict[str, Any]:
    all_posts: list[RedditPost] = []

    session = cffi_requests.Session(impersonate="chrome")
    # Acquire session cookies to bypass Reddit bot detection
    session.get("https://www.reddit.com/", timeout=30)

    for i, sub_name in enumerate(state["subreddits"]):
        if i > 0 and settings.reddit_fetch_delay > 0:
            time.sleep(settings.reddit_fetch_delay / 1000)
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

                # Fetch top comments
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
        except Exception:
            logger.exception("Failed to fetch posts from r/%s", sub_name)

    session.close()

    logger.info(
        "Collected %d posts from %d subreddits",
        len(all_posts),
        len(state["subreddits"]),
    )
    return {"raw_posts": all_posts}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_collector.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/reddit_digest/nodes/collector.py tests/test_collector.py
git commit -m "feat(collector): fetch top comments per Reddit post"
```

---

### Task 5: Filterer — Add metric-based filtering

**Files:**
- Modify: `src/reddit_digest/nodes/filterer.py`
- Modify: `tests/test_filterer.py`

- [ ] **Step 1: Write failing tests for metric filtering**

Add to `tests/test_filterer.py` — update `_post` helper and add new tests:

```python
from reddit_digest.db import save_seen_post, update_preference
from reddit_digest.models import RedditPost
from reddit_digest.nodes.filterer import filter_posts


def _post(
    reddit_id: str,
    subreddit: str = "python",
    score: int = 50,
    num_comments: int = 10,
) -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit=subreddit,
        title=f"Post {reddit_id}",
        url=f"https://reddit.com/{reddit_id}",
        score=score,
        num_comments=num_comments,
    )


async def test_filter_removes_already_seen(db_conn):
    post = _post("sent1")
    await save_seen_post(db_conn, post, status="seen")

    state = {"raw_posts": [post, _post("new1")]}
    result = await filter_posts(state, db_conn)
    assert len(result["filtered_posts"]) == 1
    assert result["filtered_posts"][0].reddit_id == "new1"


async def test_filter_removes_negative_subreddit(db_conn):
    await update_preference(db_conn, "badsubr", "general", -4)

    state = {"raw_posts": [_post("p1", "badsubr"), _post("p2", "python")]}
    result = await filter_posts(state, db_conn)
    assert len(result["filtered_posts"]) == 1
    assert result["filtered_posts"][0].subreddit == "python"


async def test_filter_keeps_neutral_and_positive(db_conn):
    await update_preference(db_conn, "python", "web", 2)

    state = {"raw_posts": [_post("p1", "python"), _post("p2", "rust")]}
    result = await filter_posts(state, db_conn)
    assert len(result["filtered_posts"]) == 2


async def test_filter_empty_input(db_conn):
    state = {"raw_posts": []}
    result = await filter_posts(state, db_conn)
    assert result["filtered_posts"] == []


async def test_filter_removes_low_score(db_conn, settings):
    low = _post("low1", score=5, num_comments=10)
    high = _post("high1", score=50, num_comments=10)

    state = {"raw_posts": [low, high]}
    result = await filter_posts(state, db_conn, settings)
    assert len(result["filtered_posts"]) == 1
    assert result["filtered_posts"][0].reddit_id == "high1"


async def test_filter_removes_few_comments(db_conn, settings):
    few = _post("few1", score=50, num_comments=1)
    many = _post("many1", score=50, num_comments=10)

    state = {"raw_posts": [few, many]}
    result = await filter_posts(state, db_conn, settings)
    assert len(result["filtered_posts"]) == 1
    assert result["filtered_posts"][0].reddit_id == "many1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_filterer.py -v`
Expected: FAIL — `filter_posts` doesn't accept `settings` param, no metric filtering

- [ ] **Step 3: Update filterer**

Replace `src/reddit_digest/nodes/filterer.py`:

```python
from __future__ import annotations

import logging
from typing import Any

import aiosqlite

from reddit_digest.config import Settings
from reddit_digest.db import get_preferences, is_post_seen
from reddit_digest.models import RedditPost

logger = logging.getLogger(__name__)

NEGATIVE_THRESHOLD = -3


async def filter_posts(
    state: dict[str, Any],
    conn: aiosqlite.Connection,
    settings: Settings | None = None,
) -> dict[str, Any]:
    raw_posts: list[RedditPost] = state["raw_posts"]
    preferences = await get_preferences(conn)

    min_score = settings.reddit_min_score if settings else 0
    min_comments = settings.reddit_min_comments if settings else 0

    # Build a lookup: subreddit -> min score across all topics
    sub_scores: dict[str, int] = {}
    for pref in preferences:
        sub = pref["subreddit"]
        if sub not in sub_scores:
            sub_scores[sub] = pref["score"]
        else:
            sub_scores[sub] = min(sub_scores[sub], pref["score"])

    filtered: list[RedditPost] = []
    for post in raw_posts:
        if await is_post_seen(conn, post.reddit_id):
            logger.debug("Skipping already-seen post %s", post.reddit_id)
            continue

        sub_score = sub_scores.get(post.subreddit, 0)
        if sub_score <= NEGATIVE_THRESHOLD:
            logger.debug(
                "Skipping post %s from r/%s (score %d <= %d)",
                post.reddit_id,
                post.subreddit,
                sub_score,
                NEGATIVE_THRESHOLD,
            )
            continue

        if post.score < min_score:
            logger.debug(
                "Skipping post %s: Reddit score %d < %d",
                post.reddit_id,
                post.score,
                min_score,
            )
            continue

        if post.num_comments < min_comments:
            logger.debug(
                "Skipping post %s: %d comments < %d",
                post.reddit_id,
                post.num_comments,
                min_comments,
            )
            continue

        filtered.append(post)

    logger.info("Filtered %d → %d posts", len(raw_posts), len(filtered))
    return {"filtered_posts": filtered}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_filterer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/reddit_digest/nodes/filterer.py tests/test_filterer.py
git commit -m "feat(filterer): add metric-based filtering (min score, min comments)"
```

---

### Task 6: Scorer — New LLM relevance scoring node

**Files:**
- Create: `src/reddit_digest/nodes/scorer.py`
- Create: `tests/test_scorer.py`

- [ ] **Step 1: Write failing test for scorer**

Create `tests/test_scorer.py`:

```python
import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.models import RedditPost
from reddit_digest.nodes.scorer import score_posts

SCORE_PROMPT_MODULE = "reddit_digest.nodes.scorer.ChatOpenAI"


def _post(
    reddit_id: str = "p1",
    subreddit: str = "python",
    title: str = "Test Post",
    score: int = 50,
) -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit=subreddit,
        title=title,
        url=f"https://reddit.com/{reddit_id}",
        score=score,
        num_comments=10,
        selftext="Content here",
        top_comments=["Great post", "I agree"],
    )


def _llm_scores_response(scores: dict[str, int]):
    data = {"scores": scores}
    return AIMessage(content=json.dumps(data))


@pytest.fixture
def mock_llm():
    with patch(SCORE_PROMPT_MODULE) as mock_cls:
        instance = AsyncMock()
        mock_cls.return_value = instance
        yield instance


async def test_score_posts_filters_low_relevance(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(
        return_value=_llm_scores_response({"p1": 8, "p2": 4, "p3": 7})
    )

    posts = [_post("p1"), _post("p2"), _post("p3")]
    state = {"filtered_posts": posts}
    result = await score_posts(state, settings)

    scored = result["scored_posts"]
    ids = [p.reddit_id for p in scored]
    assert "p1" in ids
    assert "p3" in ids
    assert "p2" not in ids


async def test_score_posts_empty_input(mock_llm, settings):
    state = {"filtered_posts": []}
    result = await score_posts(state, settings)
    assert result["scored_posts"] == []
    mock_llm.ainvoke.assert_not_called()


async def test_score_posts_multiple_subreddits(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(
        side_effect=[
            _llm_scores_response({"p1": 9}),
            _llm_scores_response({"p2": 3}),
        ]
    )

    posts = [_post("p1", subreddit="python"), _post("p2", subreddit="rust")]
    state = {"filtered_posts": posts}
    result = await score_posts(state, settings)

    assert len(result["scored_posts"]) == 1
    assert result["scored_posts"][0].reddit_id == "p1"


async def test_score_posts_llm_error_keeps_all(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM down"))

    posts = [_post("p1")]
    state = {"filtered_posts": posts}
    result = await score_posts(state, settings)

    # On LLM failure, keep all posts (fail open)
    assert len(result["scored_posts"]) == 1


async def test_score_posts_sets_relevance_score(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(
        return_value=_llm_scores_response({"p1": 9})
    )

    state = {"filtered_posts": [_post("p1")]}
    result = await score_posts(state, settings)

    assert result["scored_posts"][0].relevance_score == 9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scorer.py -v`
Expected: FAIL — module `reddit_digest.nodes.scorer` doesn't exist

- [ ] **Step 3: Implement scorer node**

Create `src/reddit_digest/nodes/scorer.py`:

```python
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from langchain_openai import ChatOpenAI

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 7

SCORE_PROMPT = """You are a content relevance scorer. Rate each Reddit post from 1 to 10 based on how impactful, insightful, or noteworthy it is.

Score 7+ = truly interesting, surprising, or useful content that people would want to hear about.
Score <7 = routine, low-effort, repetitive, or niche content.

Posts from r/{subreddit}:

{posts_block}

Return ONLY valid JSON (no markdown, no code fences):
{{"scores": {{"post_id_1": 8, "post_id_2": 3, ...}}}}"""


def _build_post_block(post: RedditPost) -> str:
    comments_str = ""
    if post.top_comments:
        comments_str = "\nTop comments:\n" + "\n".join(
            f"  - {c[:200]}" for c in post.top_comments[:5]
        )
    return (
        f"[{post.reddit_id}] {post.title}\n"
        f"Score: {post.score} | Comments: {post.num_comments}\n"
        f"Content: {post.selftext[:500]}"
        f"{comments_str}"
    )


async def score_posts(state: dict[str, Any], settings: Settings) -> dict[str, Any]:
    filtered_posts: list[RedditPost] = state["filtered_posts"]
    if not filtered_posts:
        return {"scored_posts": []}

    llm = ChatOpenAI(
        base_url=settings.openai_base_url,
        model=settings.llm_model,
        api_key=settings.openai_api_key,
    )

    # Group by subreddit
    by_sub: dict[str, list[RedditPost]] = defaultdict(list)
    for post in filtered_posts:
        by_sub[post.subreddit].append(post)

    scored: list[RedditPost] = []

    for subreddit, posts in by_sub.items():
        posts_block = "\n\n---\n\n".join(_build_post_block(p) for p in posts)
        prompt = SCORE_PROMPT.format(subreddit=subreddit, posts_block=posts_block)

        try:
            response = await llm.ainvoke(prompt)
            data = json.loads(response.content)
            scores = data.get("scores", {})
        except Exception:
            logger.exception(
                "Failed to score posts for r/%s, keeping all", subreddit
            )
            scored.extend(posts)
            continue

        for post in posts:
            post_score = scores.get(post.reddit_id)
            if post_score is None:
                logger.warning(
                    "No score returned for post %s, keeping it", post.reddit_id
                )
                scored.append(post)
                continue

            post = post.model_copy(update={"relevance_score": post_score})
            if post_score >= RELEVANCE_THRESHOLD:
                scored.append(post)
            else:
                logger.debug(
                    "Dropping post %s: relevance %d < %d",
                    post.reddit_id,
                    post_score,
                    RELEVANCE_THRESHOLD,
                )

    logger.info("Scored %d → %d posts", len(filtered_posts), len(scored))
    return {"scored_posts": scored}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_scorer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/reddit_digest/nodes/scorer.py tests/test_scorer.py
git commit -m "feat(scorer): add LLM-based relevance scoring node"
```

---

### Task 7: Summarizer — Batch per subreddit, short sentences

**Files:**
- Modify: `src/reddit_digest/nodes/summarizer.py`
- Modify: `tests/test_summarizer.py`

- [ ] **Step 1: Write failing tests for new summarizer**

Replace `tests/test_summarizer.py`:

```python
import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.models import RedditPost
from reddit_digest.nodes.summarizer import summarize_posts


def _post(reddit_id: str = "p1", subreddit: str = "python") -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit=subreddit,
        title="Test Post",
        url=f"https://reddit.com/{reddit_id}",
        selftext="Some content about Python",
        top_comments=["Great stuff", "Interesting read"],
    )


def _llm_response(summaries: dict[str, str]):
    data = {"summaries": summaries}
    return AIMessage(content=json.dumps(data))


@pytest.fixture
def mock_llm():
    with patch("reddit_digest.nodes.summarizer.ChatOpenAI") as mock_cls:
        instance = AsyncMock()
        mock_cls.return_value = instance
        yield instance


async def test_summarize_posts_batch(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(
        return_value=_llm_response({"p1": "Résumé du post p1", "p2": "Résumé du post p2"})
    )
    state = {"scored_posts": [_post("p1"), _post("p2")]}
    result = await summarize_posts(state, settings)

    assert len(result["summaries"]) == 2
    assert result["summaries"][0].summary_text == "Résumé du post p1"
    assert result["summaries"][1].summary_text == "Résumé du post p2"
    # Only one LLM call for the batch
    assert mock_llm.ainvoke.call_count == 1


async def test_summarize_posts_empty(mock_llm, settings):
    state = {"scored_posts": []}
    result = await summarize_posts(state, settings)
    assert result["summaries"] == []
    mock_llm.ainvoke.assert_not_called()


async def test_summarize_posts_multiple_subreddits(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(
        side_effect=[
            _llm_response({"p1": "Python summary"}),
            _llm_response({"p2": "Rust summary"}),
        ]
    )
    state = {"scored_posts": [_post("p1", "python"), _post("p2", "rust")]}
    result = await summarize_posts(state, settings)

    assert len(result["summaries"]) == 2
    assert mock_llm.ainvoke.call_count == 2


async def test_summarize_posts_llm_error_graceful(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
    state = {"scored_posts": [_post("p1")]}
    result = await summarize_posts(state, settings)
    assert result["summaries"] == []


async def test_summarize_posts_uses_configured_language(mock_llm, settings):
    settings.digest_language = "en"
    mock_llm.ainvoke = AsyncMock(
        return_value=_llm_response({"p1": "English summary"})
    )
    state = {"scored_posts": [_post()]}
    await summarize_posts(state, settings)
    call_args = mock_llm.ainvoke.call_args[0][0]
    assert "en" in call_args
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_summarizer.py -v`
Expected: FAIL — summarizer still reads `filtered_posts` and uses old prompt format

- [ ] **Step 3: Rewrite summarizer**

Replace `src/reddit_digest/nodes/summarizer.py`:

```python
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

from langchain_openai import ChatOpenAI

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost, Summary

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are a content curator. For each Reddit post below, write a single short sentence summary in {language}. The summary should capture the key insight or news from the post and its comments.

Posts from r/{subreddit}:

{posts_block}

Return ONLY valid JSON (no markdown, no code fences):
{{"summaries": {{"post_id_1": "one sentence summary", "post_id_2": "one sentence summary"}}}}"""


def _build_post_block(post: RedditPost) -> str:
    comments_str = ""
    if post.top_comments:
        comments_str = "\nTop comments:\n" + "\n".join(
            f"  - {c[:200]}" for c in post.top_comments[:5]
        )
    return (
        f"[{post.reddit_id}] {post.title}\n"
        f"Content: {post.selftext[:1000]}"
        f"{comments_str}"
    )


async def summarize_posts(state: dict[str, Any], settings: Settings) -> dict[str, Any]:
    scored_posts: list[RedditPost] = state["scored_posts"]
    if not scored_posts:
        return {"summaries": []}

    llm = ChatOpenAI(
        base_url=settings.openai_base_url,
        model=settings.llm_model,
        api_key=settings.openai_api_key,
    )

    # Group by subreddit
    by_sub: dict[str, list[RedditPost]] = defaultdict(list)
    for post in scored_posts:
        by_sub[post.subreddit].append(post)

    summaries: list[Summary] = []

    for subreddit, posts in by_sub.items():
        posts_block = "\n\n---\n\n".join(_build_post_block(p) for p in posts)
        prompt = PROMPT_TEMPLATE.format(
            language=settings.digest_language,
            subreddit=subreddit,
            posts_block=posts_block,
        )

        try:
            response = await llm.ainvoke(prompt)
            data = json.loads(response.content)
            raw_summaries = data.get("summaries", {})
        except Exception:
            logger.exception("Failed to summarize posts for r/%s", subreddit)
            continue

        for post in posts:
            text = raw_summaries.get(post.reddit_id)
            if text:
                summaries.append(
                    Summary(
                        reddit_id=post.reddit_id,
                        subreddit=subreddit,
                        summary_text=text,
                    )
                )
            else:
                logger.warning("No summary for post %s", post.reddit_id)

    logger.info("Summarized %d/%d posts", len(summaries), len(scored_posts))
    return {"summaries": summaries}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_summarizer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/reddit_digest/nodes/summarizer.py tests/test_summarizer.py
git commit -m "feat(summarizer): batch summarization per subreddit with comment context"
```

---

### Task 8: Deliverer — One message per subreddit with numbered threads

**Files:**
- Modify: `src/reddit_digest/nodes/deliverer.py`
- Modify: `tests/test_deliverer.py`

- [ ] **Step 1: Write failing tests for new deliverer**

Replace `tests/test_deliverer.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from reddit_digest.models import RedditPost, Summary
from reddit_digest.nodes.deliverer import (
    _build_keyboard,
    _format_subreddit_message,
    deliver_summaries,
)


def _summary(reddit_id: str = "p1", subreddit: str = "python") -> Summary:
    return Summary(
        reddit_id=reddit_id,
        subreddit=subreddit,
        summary_text=f"Summary of {reddit_id}",
    )


def _post(reddit_id: str = "p1", subreddit: str = "python") -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit=subreddit,
        title="Test Post",
        url=f"https://reddit.com/r/{subreddit}/comments/{reddit_id}",
    )


def test_format_subreddit_message():
    summaries = [_summary("p1"), _summary("p2")]
    posts = [_post("p1"), _post("p2")]
    msg = _format_subreddit_message("python", summaries, posts)
    assert "📌 r/python" in msg
    assert "1." in msg
    assert "Summary of p1" in msg
    assert "2." in msg
    assert "Summary of p2" in msg
    assert "reddit.com/r/python/comments/p1" in msg


def test_build_keyboard():
    summaries = [_summary("p1"), _summary("p2")]
    kb = _build_keyboard(summaries)
    # 2 rows (one per thread), 2 buttons each
    assert len(kb.inline_keyboard) == 2
    row1 = kb.inline_keyboard[0]
    assert len(row1) == 2
    assert row1[0].text == "1 👍"
    assert row1[0].callback_data == "up:1:p1"
    assert row1[1].text == "1 👎"
    assert row1[1].callback_data == "down:1:p1"
    row2 = kb.inline_keyboard[1]
    assert row2[0].text == "2 👍"
    assert row2[0].callback_data == "up:2:p2"


async def test_deliver_summaries_grouped(db_conn, settings):
    fake_msg = MagicMock()
    fake_msg.message_id = 100

    with patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls:
        bot_instance = AsyncMock()
        bot_instance.send_message = AsyncMock(return_value=fake_msg)
        mock_bot_cls.return_value = bot_instance

        state = {
            "summaries": [_summary("p1", "python"), _summary("p2", "python")],
            "scored_posts": [_post("p1", "python"), _post("p2", "python")],
        }
        result = await deliver_summaries(state, settings, db_conn)

    # One message for one subreddit
    assert bot_instance.send_message.call_count == 1
    assert len(result["delivered_ids"]) == 1


async def test_deliver_summaries_multiple_subreddits(db_conn, settings):
    fake_msg = MagicMock()
    fake_msg.message_id = 100

    with patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls:
        bot_instance = AsyncMock()
        bot_instance.send_message = AsyncMock(return_value=fake_msg)
        mock_bot_cls.return_value = bot_instance

        state = {
            "summaries": [_summary("p1", "python"), _summary("p2", "rust")],
            "scored_posts": [_post("p1", "python"), _post("p2", "rust")],
        }
        result = await deliver_summaries(state, settings, db_conn)

    # Two messages — one per subreddit
    assert bot_instance.send_message.call_count == 2


async def test_deliver_summaries_empty_sends_no_threads(db_conn, settings):
    with patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls:
        bot_instance = AsyncMock()
        bot_instance.send_message = AsyncMock()
        mock_bot_cls.return_value = bot_instance

        state = {"summaries": [], "scored_posts": []}
        result = await deliver_summaries(state, settings, db_conn)

    bot_instance.send_message.assert_called_once()
    call_kwargs = bot_instance.send_message.call_args.kwargs
    assert "Aucun thread pertinent" in call_kwargs["text"]
    assert result["delivered_ids"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_deliverer.py -v`
Expected: FAIL — old functions, old format

- [ ] **Step 3: Rewrite deliverer**

Replace `src/reddit_digest/nodes/deliverer.py`:

```python
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

import aiosqlite
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost, Summary

logger = logging.getLogger(__name__)


def _format_subreddit_message(
    subreddit: str,
    summaries: list[Summary],
    posts: list[RedditPost],
) -> str:
    posts_by_id = {p.reddit_id: p for p in posts}
    lines = [f"📌 <b>r/{subreddit}</b>\n"]

    for i, summary in enumerate(summaries, 1):
        post = posts_by_id.get(summary.reddit_id)
        url = post.url if post else ""
        lines.append(f"{i}. {summary.summary_text}")
        if url:
            # Strip https:// for cleaner display
            display_url = url.replace("https://", "")
            lines.append(f"   🔗 {display_url}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_keyboard(summaries: list[Summary]) -> InlineKeyboardMarkup:
    rows = []
    for i, summary in enumerate(summaries, 1):
        rows.append(
            [
                InlineKeyboardButton(
                    f"{i} 👍", callback_data=f"up:{i}:{summary.reddit_id}"
                ),
                InlineKeyboardButton(
                    f"{i} 👎", callback_data=f"down:{i}:{summary.reddit_id}"
                ),
            ]
        )
    return InlineKeyboardMarkup(rows)


async def deliver_summaries(
    state: dict[str, Any],
    settings: Settings,
    conn: aiosqlite.Connection,
) -> dict[str, Any]:
    summaries: list[Summary] = state["summaries"]
    scored_posts: list[RedditPost] = state.get("scored_posts", [])

    bot = Bot(token=settings.telegram_bot_token)

    if not summaries:
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text="Aucun thread pertinent pour aujourd'hui.",
        )
        return {"delivered_ids": []}

    # Group summaries by subreddit (preserve order)
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
        except Exception:
            logger.exception("Failed to deliver digest for r/%s", subreddit)

    logger.info(
        "Delivered %d messages for %d subreddits",
        len(delivered_ids),
        len(by_sub),
    )
    return {"delivered_ids": delivered_ids}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_deliverer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/reddit_digest/nodes/deliverer.py tests/test_deliverer.py
git commit -m "feat(deliverer): one message per subreddit with numbered threads and up/down buttons"
```

---

### Task 9: Feedback — Update callback format and score mapping

**Files:**
- Modify: `src/reddit_digest/nodes/feedback.py`
- Modify: `src/reddit_digest/telegram/bot.py`
- Modify: `tests/test_feedback.py`

- [ ] **Step 1: Update feedback tests**

In `tests/test_feedback.py`, update score deltas and reaction types:

Change `SCORE_DELTAS` references:
- Replace `"more"` → `"up"` in test reaction types
- Replace `"less"` → `"down"` in test reaction types
- Remove `"irrelevant"` tests
- Update expected score deltas: `"up"` → +1, `"down"` → -1

```python
import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.db import get_preference_score, save_seen_post
from reddit_digest.models import RedditPost
from reddit_digest.nodes.feedback import (
    analyze_reaction,
    receive_reaction,
    update_preferences,
)


def _post() -> RedditPost:
    return RedditPost(
        reddit_id="fb1",
        subreddit="python",
        title="Feedback Test Post",
        url="https://reddit.com/fb1",
    )


@pytest.fixture
def mock_llm():
    with patch("reddit_digest.nodes.feedback.ChatOpenAI") as mock_cls:
        instance = AsyncMock()
        data = {"topics": ["web", "frameworks"]}
        instance.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(data)))
        mock_cls.return_value = instance
        yield instance


async def test_receive_reaction(db_conn):
    post = _post()
    await save_seen_post(
        db_conn, post, telegram_message_id=500, status="sent",
    )

    state = {
        "message_id": 500,
        "reaction_type": "up",
        "post_metadata": {},
        "preference_update": {},
    }
    result = await receive_reaction(state, db_conn)
    assert result["post_metadata"]["reddit_id"] == "fb1"
    assert result["post_metadata"]["subreddit"] == "python"


async def test_receive_reaction_not_found(db_conn):
    state = {
        "message_id": 999,
        "reaction_type": "up",
        "post_metadata": {},
        "preference_update": {},
    }
    result = await receive_reaction(state, db_conn)
    assert result["post_metadata"] == {}


async def test_analyze_reaction_up(mock_llm, settings):
    state = {
        "message_id": 1,
        "reaction_type": "up",
        "post_metadata": {
            "subreddit": "python",
            "title": "Test",
            "category": "tech",
            "keywords": ["python"],
        },
        "preference_update": {},
    }
    result = await analyze_reaction(state, settings)
    assert result["preference_update"]["score_delta"] == 1
    assert result["preference_update"]["topics"] == ["web", "frameworks"]


async def test_analyze_reaction_down(mock_llm, settings):
    state = {
        "message_id": 1,
        "reaction_type": "down",
        "post_metadata": {
            "subreddit": "python",
            "title": "Test",
            "category": "tech",
            "keywords": [],
        },
        "preference_update": {},
    }
    result = await analyze_reaction(state, settings)
    assert result["preference_update"]["score_delta"] == -1


async def test_analyze_reaction_llm_error(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM down"))
    state = {
        "message_id": 1,
        "reaction_type": "down",
        "post_metadata": {
            "subreddit": "python",
            "title": "Test",
            "category": "tech",
            "keywords": [],
        },
        "preference_update": {},
    }
    result = await analyze_reaction(state, settings)
    assert result["preference_update"]["topics"] == ["tech"]
    assert result["preference_update"]["score_delta"] == -1


async def test_update_preferences(db_conn):
    state = {
        "message_id": 1,
        "reaction_type": "up",
        "post_metadata": {},
        "preference_update": {
            "subreddit": "python",
            "topics": ["web", "frameworks"],
            "score_delta": 1,
        },
    }
    await update_preferences(state, db_conn)
    assert await get_preference_score(db_conn, "python", "web") == 1
    assert await get_preference_score(db_conn, "python", "frameworks") == 1


async def test_update_preferences_empty(db_conn):
    state = {
        "message_id": 1,
        "reaction_type": "up",
        "post_metadata": {},
        "preference_update": {},
    }
    result = await update_preferences(state, db_conn)
    assert result == {}
```

- [ ] **Step 2: Update feedback node score mapping**

In `src/reddit_digest/nodes/feedback.py`, change:

```python
SCORE_DELTAS = {
    "up": 1,
    "down": -1,
}
```

No other changes needed to the feedback node — it already uses `SCORE_DELTAS.get(reaction_type, 0)`.

- [ ] **Step 3: Update Telegram bot callback handler**

Replace `src/reddit_digest/telegram/bot.py`:

```python
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from reddit_digest.db import get_post_by_message_id, save_reaction

if TYPE_CHECKING:
    import aiosqlite
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


def create_bot(
    token: str,
    feedback_graph: CompiledStateGraph,
    db_conn: aiosqlite.Connection,
) -> Application:
    app = Application.builder().token(token).build()

    async def handle_callback(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()

        # Format: "up:1:reddit_id" or "down:2:reddit_id"
        parts = query.data.split(":", 2)
        if len(parts) != 3:
            return

        reaction_type, _num, reddit_id = parts
        if reaction_type not in ("up", "down"):
            return

        message_id = query.message.message_id

        post_meta = await get_post_by_message_id(db_conn, message_id)
        if not post_meta:
            logger.warning("No post found for message_id=%d", message_id)
            return

        await save_reaction(db_conn, message_id, reaction_type)

        try:
            await feedback_graph.ainvoke(
                {
                    "message_id": message_id,
                    "reaction_type": reaction_type,
                    "post_metadata": {},
                    "preference_update": {},
                }
            )
        except Exception:
            logger.exception("Feedback graph failed for message_id=%d", message_id)

    app.add_handler(CallbackQueryHandler(handle_callback))
    return app
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_feedback.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/reddit_digest/nodes/feedback.py src/reddit_digest/telegram/bot.py tests/test_feedback.py
git commit -m "feat(feedback): update to up/down reaction format"
```

---

### Task 10: Digest Graph — Add scorer, mark_all_seen, wire new pipeline

**Files:**
- Modify: `src/reddit_digest/graphs/digest.py`
- Modify: `tests/test_digest_graph.py`

- [ ] **Step 1: Write failing test for new graph**

Replace `tests/test_digest_graph.py`:

```python
import json
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from reddit_digest.db import is_post_seen
from reddit_digest.graphs.digest import build_digest_graph


def _make_collector_response(posts):
    children = [
        {
            "data": {
                "id": p["id"],
                "subreddit": p["sub"],
                "title": p.get("title", "Test"),
                "url": f"https://reddit.com/{p['id']}",
                "score": p.get("score", 100),
                "num_comments": p.get("num_comments", 20),
                "selftext": "content",
                "created_utc": 1700000000.0,
            }
        }
        for p in posts
    ]
    resp = MagicMock()
    resp.json.return_value = {"data": {"children": children}}
    resp.raise_for_status = MagicMock()
    return resp


def _make_comments_response():
    resp = MagicMock()
    resp.json.return_value = [
        {"data": {"children": []}},
        {"data": {"children": [{"kind": "t1", "data": {"body": "Nice", "score": 5}}]}},
    ]
    resp.raise_for_status = MagicMock()
    return resp


async def test_digest_graph_full_flow(db_conn, settings):
    posts = [{"id": "x1", "sub": "python", "score": 100, "num_comments": 20}]
    homepage_resp = MagicMock()
    homepage_resp.json.return_value = {"data": {"children": []}}
    homepage_resp.raise_for_status = MagicMock()

    scores_resp = AIMessage(content=json.dumps({"scores": {"x1": 9}}))
    summaries_resp = AIMessage(
        content=json.dumps({"summaries": {"x1": "Great Python post"}})
    )

    fake_msg = MagicMock()
    fake_msg.message_id = 42

    with (
        patch("reddit_digest.nodes.collector.cffi_requests.Session") as mock_session_cls,
        patch("reddit_digest.nodes.scorer.ChatOpenAI") as mock_scorer_llm_cls,
        patch("reddit_digest.nodes.summarizer.ChatOpenAI") as mock_sum_llm_cls,
        patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls,
    ):
        session = MagicMock()
        mock_session_cls.return_value = session
        session.get.side_effect = [
            homepage_resp,
            _make_collector_response(posts),
            _make_comments_response(),
        ]

        scorer_llm = AsyncMock()
        scorer_llm.ainvoke = AsyncMock(return_value=scores_resp)
        mock_scorer_llm_cls.return_value = scorer_llm

        sum_llm = AsyncMock()
        sum_llm.ainvoke = AsyncMock(return_value=summaries_resp)
        mock_sum_llm_cls.return_value = sum_llm

        bot = AsyncMock()
        bot.send_message = AsyncMock(return_value=fake_msg)
        mock_bot_cls.return_value = bot

        graph = build_digest_graph(settings, db_conn)
        result = await graph.ainvoke({"subreddits": ["python"]})

    assert len(result["delivered_ids"]) == 1
    # All posts should be marked as seen
    assert await is_post_seen(db_conn, "x1")


async def test_digest_graph_no_relevant_posts(db_conn, settings):
    posts = [{"id": "x1", "sub": "python", "score": 100, "num_comments": 20}]
    homepage_resp = MagicMock()
    homepage_resp.json.return_value = {"data": {"children": []}}
    homepage_resp.raise_for_status = MagicMock()

    # Scorer gives low score
    scores_resp = AIMessage(content=json.dumps({"scores": {"x1": 2}}))

    with (
        patch("reddit_digest.nodes.collector.cffi_requests.Session") as mock_session_cls,
        patch("reddit_digest.nodes.scorer.ChatOpenAI") as mock_scorer_llm_cls,
        patch("reddit_digest.nodes.summarizer.ChatOpenAI") as mock_sum_llm_cls,
        patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls,
    ):
        session = MagicMock()
        mock_session_cls.return_value = session
        session.get.side_effect = [
            homepage_resp,
            _make_collector_response(posts),
            _make_comments_response(),
        ]

        scorer_llm = AsyncMock()
        scorer_llm.ainvoke = AsyncMock(return_value=scores_resp)
        mock_scorer_llm_cls.return_value = scorer_llm

        sum_llm = AsyncMock()
        mock_sum_llm_cls.return_value = sum_llm

        bot = AsyncMock()
        bot.send_message = AsyncMock()
        mock_bot_cls.return_value = bot

        graph = build_digest_graph(settings, db_conn)
        result = await graph.ainvoke({"subreddits": ["python"]})

    # "Aucun thread pertinent" message sent
    bot.send_message.assert_called_once()
    call_kwargs = bot.send_message.call_args.kwargs
    assert "Aucun thread pertinent" in call_kwargs["text"]
    # Post still marked as seen
    assert await is_post_seen(db_conn, "x1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_digest_graph.py -v`
Expected: FAIL — graph doesn't have scorer or mark_all_seen nodes

- [ ] **Step 3: Rewrite digest graph**

Replace `src/reddit_digest/graphs/digest.py`:

```python
from __future__ import annotations

import logging
from typing import Any, TypedDict

import aiosqlite
from langgraph.graph import END, START, StateGraph

from reddit_digest.config import Settings
from reddit_digest.db import save_seen_post
from reddit_digest.models import RedditPost, Summary
from reddit_digest.nodes.collector import collect_posts
from reddit_digest.nodes.deliverer import deliver_summaries
from reddit_digest.nodes.filterer import filter_posts
from reddit_digest.nodes.scorer import score_posts
from reddit_digest.nodes.summarizer import summarize_posts

logger = logging.getLogger(__name__)


class DigestState(TypedDict, total=False):
    subreddits: list[str]
    raw_posts: list[RedditPost]
    filtered_posts: list[RedditPost]
    scored_posts: list[RedditPost]
    summaries: list[Summary]
    delivered_ids: list[str]


def build_digest_graph(settings: Settings, conn: aiosqlite.Connection):
    async def collector_node(state: dict[str, Any]) -> dict[str, Any]:
        return await collect_posts(state, settings)

    async def filterer_node(state: dict[str, Any]) -> dict[str, Any]:
        return await filter_posts(state, conn, settings)

    async def scorer_node(state: dict[str, Any]) -> dict[str, Any]:
        return await score_posts(state, settings)

    async def summarizer_node(state: dict[str, Any]) -> dict[str, Any]:
        return await summarize_posts(state, settings)

    async def deliverer_node(state: dict[str, Any]) -> dict[str, Any]:
        return await deliver_summaries(state, settings, conn)

    async def mark_all_seen_node(state: dict[str, Any]) -> dict[str, Any]:
        raw_posts: list[RedditPost] = state.get("raw_posts", [])
        delivered_ids: list[str] = state.get("delivered_ids", [])
        summaries: list[Summary] = state.get("summaries", [])

        # Build set of reddit_ids that were actually delivered
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

    builder = StateGraph(DigestState)
    builder.add_node("collector", collector_node)
    builder.add_node("filterer", filterer_node)
    builder.add_node("scorer", scorer_node)
    builder.add_node("summarizer", summarizer_node)
    builder.add_node("deliverer", deliverer_node)
    builder.add_node("mark_all_seen", mark_all_seen_node)

    builder.add_edge(START, "collector")
    builder.add_edge("collector", "filterer")
    builder.add_edge("filterer", "scorer")
    builder.add_edge("scorer", "summarizer")
    builder.add_edge("summarizer", "deliverer")
    builder.add_edge("deliverer", "mark_all_seen")
    builder.add_edge("mark_all_seen", END)

    return builder.compile()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_digest_graph.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/reddit_digest/graphs/digest.py tests/test_digest_graph.py
git commit -m "feat(graph): add scorer and mark_all_seen nodes to digest pipeline"
```

---

### Task 11: Integration tests and remaining test fixes

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `tests/test_feedback_graph.py`

- [ ] **Step 1: Update integration tests**

Replace `tests/test_integration.py` to match the new pipeline (scorer node, new callback format, save_seen_post, `scored_posts` state key). The integration tests need to mock the scorer LLM in addition to the summarizer LLM and use the new DB functions.

Read the current file, then update it to:
- Use `save_seen_post` instead of `save_sent_post`
- Use `is_post_seen` instead of `is_post_sent`
- Mock `reddit_digest.nodes.scorer.ChatOpenAI` alongside summarizer
- Use `scored_posts` in state where needed
- Use new callback format `up:1:reddit_id` / `down:1:reddit_id`

- [ ] **Step 2: Update feedback graph tests**

In `tests/test_feedback_graph.py`, change reaction types from `more`/`less`/`irrelevant` to `up`/`down` and update expected score deltas.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v --tb=short`
Expected: ALL PASS

- [ ] **Step 4: Run linter**

Run: `uv run ruff check src/ tests/`
Fix any issues.

Run: `uv run ruff format src/ tests/`

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: update integration and feedback graph tests for compact digest"
```

---

### Task 12: Final verification

- [ ] **Step 1: Run full test suite one last time**

Run: `uv run pytest -v`
Expected: ALL PASS, no warnings

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/ tests/`
Expected: No errors

- [ ] **Step 3: Final commit if needed**

Only if linter required fixes.
