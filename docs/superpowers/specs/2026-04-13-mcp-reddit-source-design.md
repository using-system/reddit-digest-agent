# MCP Reddit Source — Design Spec

**Date:** 2026-04-13
**Status:** Approved

## Objective

Replace the current direct Reddit scraping (`curl_cffi`) with the [reddit-mcp-server](https://github.com/jordanburke/reddit-mcp-server) running in anonymous mode (no credentials required). Communication happens over the MCP stdio transport. The rest of the digest pipeline (filterer, scorer, summarizer, deliverer) remains unchanged.

## Motivation

- Decouple Reddit data fetching from implementation details (HTTP endpoints, browser impersonation, JSON parsing)
- Leverage a maintained MCP server that handles Reddit API quirks
- Align with the MCP ecosystem for tool-based data sourcing
- Zero-setup anonymous mode — no Reddit API credentials needed

## Architecture

### Data Flow

```
collector_node
  └─ MCP Client (stdio transport)
       │  subprocess: npx reddit-mcp-server
       │  auth mode: anonymous (~10 req/min)
       │
       ├─ call_tool("get_top_posts", {subreddit, time_filter, limit})
       │    └─ mcp_parser.parse_top_posts() → list[RedditPost]
       │
       └─ call_tool("get_post_comments", {post_id, subreddit, limit})
            └─ mcp_parser.parse_post_comments() → list[str]
```

### MCP Client Lifecycle

1. At the start of `collect_posts()`, spawn the MCP server subprocess via `StdioServerParameters(command="npx", args=["reddit-mcp-server"], env={"REDDIT_AUTH_MODE": "anonymous"})`
2. Connect using `stdio_client()` from the `mcp` SDK
3. List available tools, select only `get_top_posts` and `get_post_comments` to minimize context
4. Execute tool calls with rate limiting (~6s between calls to stay within 10 req/min)
5. Close the session and terminate the subprocess at the end

### Tool Schemas (from reddit-mcp-server)

**get_top_posts:**
- `subreddit` (string, required): Subreddit name
- `time_filter` (string, optional, default "week"): Time range
- `limit` (number, optional, default 10): Max posts

**get_post_comments:**
- `post_id` (string, required): Reddit post ID
- `subreddit` (string, required): Subreddit name
- `sort` (string, optional, default "best"): Comment sort
- `limit` (number, optional, default 100): Max comments

### Response Parsing

The MCP server returns formatted text (not structured JSON). A dedicated `mcp_parser.py` module handles extraction:

**`parse_top_posts(text: str, subreddit: str) -> list[RedditPost]`**
- Extracts: title, author, score, comment count, permalink, selftext excerpt, reddit_id
- The `reddit_id` is derived from the permalink (e.g., `/r/python/comments/abc123/...` → `abc123`)
- Fields not available from the listing (`created_utc`) default to `0.0` (consistent with `RedditPost` model default)

**`parse_post_comments(text: str) -> list[str]`**
- Extracts top-level comment bodies from the threaded text output
- Strips metadata (author, score, timestamps) — only the body text is kept
- Respects `reddit_comments_limit` from settings

### Rate Limiting

Anonymous mode allows ~10 requests per minute. For a typical run with 3 subreddits × 5 posts:
- 3 `get_top_posts` calls + 15 `get_post_comments` calls = 18 calls
- At ~6s spacing: ~108s total fetch time
- Implemented via `asyncio.sleep(6)` between each `call_tool` invocation

## OpenTelemetry Instrumentation

Native instrumentation via the `opentelemetry-instrumentation-mcp` package:

```python
from opentelemetry.instrumentation.mcp import McpInstrumentor
McpInstrumentor().instrument()
```

- Automatically instruments all `call_tool()` invocations with spans
- Added alongside existing instrumentors (OpenAI, HTTPX, SQLite3) in `telemetry.py`
- Content tracing controllable via `TRACELOOP_TRACE_CONTENT=false` env var

## Configuration Changes

### Settings (config.py)

- **Removed:** `reddit_fetch_delay` — replaced by fixed ~6s rate limit for MCP anonymous mode
- **Unchanged:** `reddit_subreddits`, `reddit_sort`, `reddit_limit`, `reddit_time_filter`, `reddit_comments_limit`, `reddit_min_score`, `reddit_min_comments`

### Dependencies (pyproject.toml)

| Action | Package |
|--------|---------|
| Add | `mcp` |
| Add | `opentelemetry-instrumentation-mcp` |
| Remove | `curl-cffi` |

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/reddit_digest/nodes/collector.py` | Rewrite | MCP client replaces curl_cffi |
| `src/reddit_digest/nodes/mcp_parser.py` | New | Parse MCP text responses → RedditPost |
| `src/reddit_digest/telemetry.py` | Modify | Add McpInstrumentor |
| `src/reddit_digest/config.py` | Modify | Remove reddit_fetch_delay |
| `pyproject.toml` | Modify | Update dependencies |
| `tests/test_mcp_parser.py` | New | Unit tests for parser with fixture data |
| `tests/test_collector.py` | Update | Adapt to MCP-based collector |

## Unchanged

- `src/reddit_digest/models.py` — `RedditPost` model stays identical
- `src/reddit_digest/graphs/digest.py` — Graph topology unchanged
- `src/reddit_digest/nodes/filterer.py` — No changes
- `src/reddit_digest/nodes/scorer.py` — No changes
- `src/reddit_digest/nodes/summarizer.py` — No changes
- `src/reddit_digest/nodes/deliverer.py` — No changes

## Testing Strategy

- **Unit tests:** `test_mcp_parser.py` with fixture text responses covering normal posts, edge cases (empty subreddit, missing fields, malformed text)
- **Collector tests:** Mock the MCP session to verify the collector orchestrates calls correctly and maps parsed results to `RedditPost` objects
- **Integration:** Manual run with `--once` flag against live reddit-mcp-server

## Risks

- **Text parsing fragility:** If reddit-mcp-server changes its output format, the parser breaks. Mitigated by comprehensive test fixtures and isolated parser module.
- **Rate limiting:** Anonymous mode is capped at ~10 req/min. Large subreddit lists will be slow. Acceptable for a daily digest use case.
- **npx dependency:** Requires Node.js/npm on the host. Already implicit for MCP server usage.
