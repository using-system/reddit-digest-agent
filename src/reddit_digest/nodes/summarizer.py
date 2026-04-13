from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from langchain_openai import ChatOpenAI

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost, Summary
from reddit_digest.nodes.llm_utils import extract_json

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
            data = extract_json(response.content)
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
