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
            logger.exception("Failed to score posts for r/%s, keeping all", subreddit)
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
