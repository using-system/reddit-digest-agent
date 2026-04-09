from __future__ import annotations

import logging
from typing import Any

import asyncpraw

from reddit_digest.config import AppConfig, SecretsConfig
from reddit_digest.models import RedditPost

logger = logging.getLogger(__name__)


async def collect_posts(
    state: dict[str, Any], config: AppConfig, secrets: SecretsConfig
) -> dict[str, Any]:
    reddit = asyncpraw.Reddit(
        client_id=secrets.reddit_client_id,
        client_secret=secrets.reddit_client_secret,
        user_agent=secrets.reddit_user_agent,
    )

    all_posts: list[RedditPost] = []

    try:
        for sub_name in state["subreddits"]:
            try:
                subreddit = await reddit.subreddit(sub_name)
                fetch_method = {
                    "hot": subreddit.hot,
                    "top": subreddit.top,
                    "rising": subreddit.rising,
                    "new": subreddit.new,
                }.get(config.reddit.sort, subreddit.hot)

                kwargs: dict[str, Any] = {"limit": config.reddit.limit}
                if config.reddit.sort == "top":
                    kwargs["time_filter"] = config.reddit.time_filter

                async for submission in fetch_method(**kwargs):
                    all_posts.append(
                        RedditPost(
                            reddit_id=submission.id,
                            subreddit=sub_name,
                            title=submission.title,
                            url=submission.url,
                            score=submission.score,
                            num_comments=submission.num_comments,
                            selftext=submission.selftext or "",
                            created_utc=submission.created_utc,
                        )
                    )
            except Exception:
                logger.exception("Failed to fetch posts from r/%s", sub_name)
    finally:
        await reddit.close()

    logger.info(
        "Collected %d posts from %d subreddits",
        len(all_posts),
        len(state["subreddits"]),
    )
    return {"raw_posts": all_posts}
