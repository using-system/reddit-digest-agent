# Reddit Digest Agent — Design Spec

## Context

This project aims to create a Python agent that daily collects top posts from configurable subreddits, summarizes them via an LLM, and sends them to a Telegram channel. Users can react via inline buttons, and the system adapts to their preferences over time.

## Technical Decisions

| Component | Choice | Reason |
|-----------|--------|--------|
| Orchestration | LangChain + LangGraph | Multi-agent, composable graphs |
| Package manager | uv | Fast, modern |
| Reddit API | asyncpraw (direct access) | Simplicity, no MCP dependency |
| LLM | OpenAI-compatible API (generic) | Flexible: LocalAI, OpenRouter, OpenAI, etc. |
| Scheduler | APScheduler (built-in) | Long-running app, also listens for reactions |
| Storage | SQLite | Simple, zero config, sufficient for single-user |
| Config | YAML (business) + .env (secrets) | Clear separation |
| Reactions | Telegram inline buttons | Explicit, reliable, native |
| Scope | Single channel/user | Bootstrap, extensible architecture |

## Architecture

Two separate LangGraph graphs sharing SQLite state:

- **Digest Graph** (scheduled): collect → filter → summarize → deliver
- **Feedback Graph** (event-driven): receive reaction → analyze → update preferences

### Digest Graph

```
[Collector] → [Filterer] → [Summarizer] → [Deliverer]
```

**State:**

```python
class DigestState(TypedDict):
    subreddits: list[str]
    raw_posts: list[RedditPost]
    filtered_posts: list[RedditPost]
    summaries: list[Summary]
    delivered_ids: list[str]
```

**Nodes:**

- **Collector** — asyncpraw, fetches top posts (configurable sort: hot/top/rising, count and period) for each subreddit from config
- **Filterer** — excludes already-sent posts (SQLite `sent_posts` check), applies learned preferences (scores per subreddit/topic from `preferences` table). Optional LLM call for categorization
- **Summarizer** — LLM call via `langchain_openai.ChatOpenAI` with configurable `base_url`. Prompt in configured language (default: French). Generates one summary per post
- **Deliverer** — sends each summary to Telegram with 3 inline buttons: "🔥 More like this", "👎 Less of this", "🚫 Not relevant". Stores `telegram_message_id → post metadata` mapping in SQLite

### Feedback Graph

```
[Receive Reaction] → [Analyze] → [Update Preferences]
```

**State:**

```python
class FeedbackState(TypedDict):
    message_id: int
    reaction_type: str              # "more" | "less" | "irrelevant"
    post_metadata: PostMetadata
    preference_update: dict
```

**Nodes:**

- **Receive Reaction** — retrieves `post_metadata` associated with `message_id` from SQLite (subreddit, category, keywords)
- **Analyze** — LLM call to extract post themes and determine which preferences to adjust
- **Update Preferences** — updates `preferences` SQLite table: score per (subreddit, topic). Scores: "More" = +1, "Less" = -1, "Irrelevant" = -2

**Trigger:** each inline button callback invokes the Feedback Graph.

## SQLite Schema

### Table `sent_posts`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| reddit_id | TEXT UNIQUE | Reddit post ID |
| subreddit | TEXT | Subreddit name |
| title | TEXT | Post title |
| url | TEXT | Post URL |
| telegram_message_id | INTEGER | Sent Telegram message ID |
| category | TEXT | LLM-extracted category |
| keywords | TEXT | JSON keywords |
| sent_at | TIMESTAMP | Send date |

### Table `reactions`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| telegram_message_id | INTEGER FK | Message reference |
| reaction_type | TEXT | "more", "less", "irrelevant" |
| created_at | TIMESTAMP | Reaction date |

### Table `preferences`

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| subreddit | TEXT | Subreddit name |
| topic | TEXT | Extracted theme |
| score | INTEGER | Cumulative score (positive = interesting, negative = avoid) |
| updated_at | TIMESTAMP | Last update |

**Unique constraint** on `(subreddit, topic)` in `preferences`.

## Configuration

### config.yaml

```yaml
reddit:
  subreddits: ["python", "machinelearning", "selfhosted"]
  sort: "hot"
  limit: 20
  time_filter: "day"

llm:
  base_url: "http://localhost:8080/v1"
  model: "gpt-4o-mini"

telegram:
  chat_id: "123456789"

digest:
  schedule: "08:00"
  timezone: "Europe/Paris"
  language: "fr"
```

### .env

```
REDDIT_CLIENT_ID=xxx
REDDIT_CLIENT_SECRET=xxx
REDDIT_USER_AGENT=reddit-digest-agent
TELEGRAM_BOT_TOKEN=xxx
OPENAI_API_KEY=xxx
```

## Project Structure

```
reddit-digest-agent/
├── pyproject.toml
├── config.yaml
├── .env
├── SPEC.md                     # → links to this design spec
├── src/
│   └── reddit_digest/
│       ├── __init__.py
│       ├── main.py             # entry point, APScheduler, Telegram bot
│       ├── config.py           # YAML + .env loading (pydantic-settings)
│       ├── db.py               # SQLite init, queries
│       ├── models.py           # pydantic models
│       ├── graphs/
│       │   ├── __init__.py
│       │   ├── digest.py       # Digest Graph
│       │   └── feedback.py     # Feedback Graph
│       ├── nodes/
│       │   ├── __init__.py
│       │   ├── collector.py    # fetch Reddit posts
│       │   ├── filterer.py     # filter duplicates + preferences
│       │   ├── summarizer.py   # LLM summary
│       │   ├── deliverer.py    # Telegram delivery + inline buttons
│       │   └── feedback.py     # reaction analysis + pref update
│       └── telegram/
│           ├── __init__.py
│           └── bot.py          # bot setup (python-telegram-bot), handlers
└── tests/
    ├── conftest.py             # fixtures (SQLite :memory:, mock LLM, mock Reddit)
    ├── test_collector.py
    ├── test_filterer.py
    ├── test_summarizer.py
    ├── test_deliverer.py
    ├── test_feedback.py
    ├── test_digest_graph.py
    ├── test_config.py
    └── test_db.py
```

## Main Dependencies

- `langchain-openai` — OpenAI-compatible LLM interface
- `langgraph` — graph orchestration
- `asyncpraw` — async Reddit API
- `python-telegram-bot` — Telegram bot (async, inline buttons)
- `apscheduler` — built-in scheduling
- `pydantic` / `pydantic-settings` — models and config
- `pyyaml` — YAML parsing
- `python-dotenv` — .env loading
- `aiosqlite` — async SQLite
- `pytest` / `pytest-asyncio` — testing

## Testing Strategy

- **pytest** with `pytest-asyncio` for async functions
- **Mocks** for external APIs: asyncpraw (Reddit), python-telegram-bot (Telegram), ChatOpenAI (LLM)
- **In-memory SQLite** (`:memory:`) for DB tests
- **Unit tests** per node: each node tested in isolation with fixtures
- **Integration tests** per graph: digest and feedback graphs end-to-end with mocks
- **Config tests**: YAML + .env loading validation

## Entry Point (main.py)

The `main.py` orchestrates:

1. Config loading (YAML + .env)
2. SQLite initialization (create tables if needed)
3. Telegram bot startup (async, listens for button callbacks)
4. APScheduler startup (triggers Digest Graph at configured time)
5. Main async loop keeping bot + scheduler alive
