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

                for post in posts:
                    if settings.reddit_comments_limit > 0:
                        try:
                            comments_text, last_call_time = await _call_tool_with_delay(
                                session,
                                "get_post_comments",
                                {
                                    "post_id": post.reddit_id,
                                    "subreddit": sub_name,
                                    "limit": settings.reddit_comments_limit,
                                },
                                last_call_time,
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
