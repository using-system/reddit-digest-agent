from __future__ import annotations

import logging
import time
from typing import Any

from curl_cffi import requests as cffi_requests

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost

logger = logging.getLogger(__name__)


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

    session.close()

    logger.info(
        "Collected %d posts from %d subreddits",
        len(all_posts),
        len(state["subreddits"]),
    )
    return {"raw_posts": all_posts}
