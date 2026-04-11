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
