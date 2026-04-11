# Compact Digest Design

## Problem

Currently, one Telegram message is sent per Reddit thread. With 20 posts per subreddit across multiple subreddits, this spams the chat. The feedback buttons (3 per message) are tied to individual messages, making the experience noisy and hard to manage.

## Goals

1. One Telegram message per subreddit with numbered threads (short description + link)
2. Per-thread thumbs up/down reaction buttons
3. Reduce REDDIT_LIMIT (default 5, max 8)
4. Mark all fetched threads as seen in DB to prevent reprocessing
5. Show "no relevant threads" message when nothing passes filters
6. Only show truly impactful threads (hybrid metric + LLM filtering)
7. Fetch top comments per thread to improve summarization quality

## Config Changes (`Settings`)

| Setting | Old | New |
|---------|-----|-----|
| `reddit_limit` | `20` | `5` (default), validated `max(1, min(value, 8))` |
| `reddit_comments_limit` | — | `5` (new, top N comments per post) |
| `reddit_min_score` | — | `10` (new, minimum Reddit score) |
| `reddit_min_comments` | — | `3` (new, minimum comment count) |

## Pipeline Changes

### New Digest Graph

```
START → collector → filterer → scorer → summarizer → deliverer → mark_all_seen → END
```

Previous graph: `collector → filterer → summarizer → deliverer`

### Collector (modified)

- Fetches `reddit_limit` posts per subreddit (down from 20)
- For each post, fetches top comments via `https://www.reddit.com/r/{sub}/comments/{id}.json`
- Extracts top `reddit_comments_limit` comments sorted by score
- `RedditPost` model gains `top_comments: list[str]` field
- Respects `reddit_fetch_delay` between all HTTP requests (posts + comments)

### Filterer (modified)

Existing behavior preserved, plus new metric filter:

1. Exclude posts already in DB (`status` = `seen` or `sent`)
2. Exclude subreddits with preference score ≤ -3
3. **New:** Exclude posts with `score < reddit_min_score` OR `num_comments < reddit_min_comments`

### Scorer (new node)

New LangGraph node between filterer and summarizer:

- Groups filtered posts by subreddit
- **One LLM call per subreddit** (batch) — sends all posts (title + content excerpt + top comments)
- LLM rates each post 1-10 on relevance/impact
- Only posts with score ≥ 7 are kept
- `RedditPost` model gains `relevance_score: int | None` field
- If no posts pass for a subreddit, that subreddit produces no message

### Summarizer (modified)

- Receives scored posts (≥ 7), grouped by subreddit
- **One LLM call per subreddit** (batch) instead of one per post
- Prompt requests a **single short sentence** per post based on content + comments, in `digest_language`
- `Summary` model simplified: `reddit_id`, `subreddit`, `summary_text` (no more category/keywords)

### Deliverer (rewritten)

**One message per subreddit**, format:

```
📌 r/python

1. Les contributions open-source explosent en 2026 grâce aux agents IA
   🔗 reddit.com/r/python/comments/abc123

2. Un nouveau framework async 10x plus rapide que FastAPI
   🔗 reddit.com/r/python/comments/def456

3. Guide complet pour migrer de Poetry vers uv
   🔗 reddit.com/r/python/comments/ghi789
```

**Inline buttons** — 2 per thread, on the same row:
- `1 👍` / `1 👎` — callback data: `up:1:{reddit_id}` / `down:1:{reddit_id}`
- `2 👍` / `2 👎`
- etc.

**Empty case:** If no posts pass scoring for any subreddit, send a single message: "Aucun thread pertinent pour aujourd'hui."

### Mark All Seen (new node)

- Saves **all** posts from `raw_posts` (fetched by collector) to `sent_posts` table
- Posts that were delivered get `status = 'sent'`
- Posts that were filtered/scored out get `status = 'seen'`
- Prevents reprocessing on subsequent runs

## Database Changes

### `sent_posts` table

- Add column `status TEXT NOT NULL DEFAULT 'sent'` — values: `seen`, `sent`
- Rename check function: `is_post_sent()` → `is_post_seen()` (checks for any status)
- `save_sent_post()` → `save_seen_post()` accepting a `status` parameter
- Migration: existing rows get `status = 'sent'` (backward compatible)

## Feedback Changes

### Callback data format

- Old: `more:{reddit_id}`, `less:{reddit_id}`, `irrelevant:{reddit_id}`
- New: `up:{num}:{reddit_id}`, `down:{num}:{reddit_id}`

### Score mapping

- Old: `more` → +1, `less` → -1, `irrelevant` → -2
- New: `up` → +1, `down` → -1

### Telegram bot handler

- Parse new callback format `{reaction}:{num}:{reddit_id}`
- Rest of feedback graph (LLM topic extraction, preference update) unchanged

## State Changes

### `DigestState` (TypedDict)

```python
class DigestState(TypedDict):
    subreddits: list[str]
    raw_posts: list[RedditPost]        # all fetched posts
    filtered_posts: list[RedditPost]   # after metric filtering
    scored_posts: list[RedditPost]     # after LLM scoring (relevance ≥ 7)
    summaries: list[Summary]           # one short sentence per post
    delivered_ids: list[int]           # telegram message IDs
```

### Model changes

- `RedditPost`: add `top_comments: list[str]`, add `relevance_score: int | None`
- `Summary`: simplified to `reddit_id`, `subreddit`, `summary_text`

## `.env.example` updates

```
REDDIT_LIMIT=5
REDDIT_COMMENTS_LIMIT=5
REDDIT_MIN_SCORE=10
REDDIT_MIN_COMMENTS=3
```
