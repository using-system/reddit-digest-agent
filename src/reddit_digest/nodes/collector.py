from __future__ import annotations

import logging
from typing import Any

import httpx

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "reddit-digest-agent/1.0"}


async def collect_posts(state: dict[str, Any], settings: Settings) -> dict[str, Any]:
    all_posts: list[RedditPost] = []

    async with httpx.AsyncClient(headers=_HEADERS, timeout=30) as client:
        for sub_name in state["subreddits"]:
            try:
                params: dict[str, Any] = {
                    "limit": settings.reddit_limit,
                    "raw_json": 1,
                }
                if settings.reddit_sort == "top":
                    params["t"] = settings.reddit_time_filter

                url = f"https://www.reddit.com/r/{sub_name}/{settings.reddit_sort}.json"
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()

                for child in data["data"]["children"]:
                    post = child["data"]
                    all_posts.append(
                        RedditPost(
                            reddit_id=post["id"],
                            subreddit=sub_name,
                            title=post["title"],
                            url=post["url"],
                            score=post["score"],
                            num_comments=post["num_comments"],
                            selftext=post.get("selftext", ""),
                            created_utc=post["created_utc"],
                        )
                    )
            except Exception:
                logger.exception("Failed to fetch posts from r/%s", sub_name)

    logger.info(
        "Collected %d posts from %d subreddits",
        len(all_posts),
        len(state["subreddits"]),
    )
    return {"raw_posts": all_posts}
