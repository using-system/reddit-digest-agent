from __future__ import annotations

import json
import logging
from typing import Any

import aiosqlite
from langchain_openai import ChatOpenAI

from reddit_digest.config import Settings
from reddit_digest.db import get_post_by_message_id, update_preference
from reddit_digest.nodes.llm_utils import extract_json
from reddit_digest.telemetry import get_meter

logger = logging.getLogger(__name__)

SCORE_DELTAS = {
    "up": 1,
    "down": -1,
}

ANALYZE_PROMPT = """Analyze this Reddit post and extract its main themes/topics.

Post from r/{subreddit}: {title}
Category: {category}
Keywords: {keywords}

Return ONLY valid JSON (no markdown, no code fences):
{{"topics": ["topic1", "topic2"]}}"""


async def receive_reaction(
    state: dict[str, Any], conn: aiosqlite.Connection
) -> dict[str, Any]:
    # Bot may pass post_metadata pre-filled (looked up by reddit_id)
    if state.get("post_metadata"):
        return {"post_metadata": state["post_metadata"]}

    message_id = state["message_id"]
    post_meta = await get_post_by_message_id(conn, message_id)
    if post_meta is None:
        logger.warning("No post metadata for message_id=%d", message_id)
        return {"post_metadata": {}}
    return {"post_metadata": post_meta.model_dump()}


async def analyze_reaction(state: dict[str, Any], settings: Settings) -> dict[str, Any]:
    post_meta = state["post_metadata"]
    reaction_type = state["reaction_type"]

    if not post_meta:
        return {"preference_update": {}}

    score_delta = SCORE_DELTAS.get(reaction_type, 0)

    llm = ChatOpenAI(
        base_url=settings.openai_base_url,
        model=settings.llm_model,
        api_key=settings.openai_api_key,
    )

    try:
        prompt = ANALYZE_PROMPT.format(
            subreddit=post_meta.get("subreddit", ""),
            title=post_meta.get("title", ""),
            category=post_meta.get("category", ""),
            keywords=json.dumps(post_meta.get("keywords", [])),
        )
        response = await llm.ainvoke(prompt)
        data = extract_json(response.content)
        topics = data.get("topics", [])
    except Exception:
        logger.exception("Failed to analyze reaction topics")
        topics = [post_meta.get("category", "general")]

    return {
        "preference_update": {
            "subreddit": post_meta.get("subreddit", ""),
            "topics": topics,
            "score_delta": score_delta,
        }
    }


async def update_preferences(
    state: dict[str, Any], conn: aiosqlite.Connection
) -> dict[str, Any]:
    pref_update = state["preference_update"]
    if not pref_update:
        return {}

    subreddit = pref_update["subreddit"]
    topics = pref_update["topics"]
    score_delta = pref_update["score_delta"]

    for topic in topics:
        await update_preference(conn, subreddit, topic, score_delta)

    meter = get_meter("reddit_digest.feedback")
    pref_counter = meter.create_counter(
        "reddit_digest.feedback.preference_updates",
        description="Preference updates from feedback",
    )
    pref_counter.add(1)

    logger.info(
        "Updated preferences for r/%s: %d topics, delta=%d",
        subreddit,
        len(topics),
        score_delta,
    )
    return {}
