from __future__ import annotations

import json
import logging
from typing import Any

from langchain_openai import ChatOpenAI

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost, Summary

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """You are a content curator. Summarize the following Reddit post in {language}.

Post from r/{subreddit}: {title}
Content: {selftext}
URL: {url}

Respond ONLY with valid JSON (no markdown, no code fences):
{{"summary": "a concise summary in {language}", "category": "single-word category", "keywords": ["keyword1", "keyword2", "keyword3"]}}"""


async def summarize_posts(state: dict[str, Any], settings: Settings) -> dict[str, Any]:
    filtered_posts: list[RedditPost] = state["filtered_posts"]
    if not filtered_posts:
        return {"summaries": []}

    llm = ChatOpenAI(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
    )

    summaries: list[Summary] = []
    for post in filtered_posts:
        try:
            prompt = PROMPT_TEMPLATE.format(
                language=settings.digest_language,
                subreddit=post.subreddit,
                title=post.title,
                selftext=post.selftext[:2000],
                url=post.url,
            )
            response = await llm.ainvoke(prompt)
            data = json.loads(response.content)
            summaries.append(
                Summary(
                    reddit_id=post.reddit_id,
                    subreddit=post.subreddit,
                    title=post.title,
                    summary_text=data["summary"],
                    category=data.get("category", ""),
                    keywords=data.get("keywords", []),
                )
            )
        except Exception:
            logger.exception("Failed to summarize post %s", post.reddit_id)

    logger.info("Summarized %d/%d posts", len(summaries), len(filtered_posts))
    return {"summaries": summaries}
