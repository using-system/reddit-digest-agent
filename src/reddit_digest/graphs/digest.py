from __future__ import annotations

import logging
from typing import Any, TypedDict

import aiosqlite
from langgraph.graph import END, START, StateGraph

from reddit_digest.config import Settings
from reddit_digest.db import save_seen_post
from reddit_digest.models import RedditPost, Summary
from reddit_digest.nodes.collector import collect_posts
from reddit_digest.nodes.deliverer import deliver_summaries
from reddit_digest.nodes.filterer import filter_posts
from reddit_digest.nodes.scorer import score_posts
from reddit_digest.nodes.summarizer import summarize_posts
from reddit_digest.telemetry import get_tracer

logger = logging.getLogger(__name__)


class DigestState(TypedDict, total=False):
    subreddits: list[str]
    raw_posts: list[RedditPost]
    filtered_posts: list[RedditPost]
    scored_posts: list[RedditPost]
    summaries: list[Summary]
    delivered_ids: list[str]


def build_digest_graph(settings: Settings, conn: aiosqlite.Connection):
    tracer = get_tracer("reddit_digest.digest")

    async def collector_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.collector") as span:
            result = await collect_posts(state, settings)
            raw_posts = result.get("raw_posts", [])
            span.set_attribute(
                "reddit.subreddits.count", len(state.get("subreddits", []))
            )
            span.set_attribute("reddit.posts.collected", len(raw_posts))
            return result

    async def filterer_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.filterer") as span:
            span.set_attribute("posts.input_count", len(state.get("raw_posts", [])))
            result = await filter_posts(state, conn, settings)
            span.set_attribute(
                "posts.output_count", len(result.get("filtered_posts", []))
            )
            return result

    async def scorer_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.scorer") as span:
            span.set_attribute(
                "posts.input_count", len(state.get("filtered_posts", []))
            )
            result = await score_posts(state, settings)
            span.set_attribute(
                "posts.output_count", len(result.get("scored_posts", []))
            )
            return result

    async def summarizer_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.summarizer") as span:
            result = await summarize_posts(state, settings)
            span.set_attribute("summaries.count", len(result.get("summaries", [])))
            return result

    async def deliverer_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.deliverer") as span:
            result = await deliver_summaries(state, settings, conn)
            span.set_attribute(
                "telegram.messages.sent", len(result.get("delivered_ids", []))
            )
            return result

    async def mark_all_seen_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("digest.mark_all_seen"):
            raw_posts: list[RedditPost] = state.get("raw_posts", [])
            summaries: list[Summary] = state.get("summaries", [])

            delivered_reddit_ids = {s.reddit_id for s in summaries}

            for post in raw_posts:
                status = "sent" if post.reddit_id in delivered_reddit_ids else "seen"
                await save_seen_post(conn, post, status=status)

            logger.info(
                "Marked %d posts as seen (%d sent)",
                len(raw_posts),
                len(delivered_reddit_ids),
            )
            return {}

    builder = StateGraph(DigestState)
    builder.add_node("collector", collector_node)
    builder.add_node("filterer", filterer_node)
    builder.add_node("scorer", scorer_node)
    builder.add_node("summarizer", summarizer_node)
    builder.add_node("deliverer", deliverer_node)
    builder.add_node("mark_all_seen", mark_all_seen_node)

    builder.add_edge(START, "collector")
    builder.add_edge("collector", "filterer")
    builder.add_edge("filterer", "scorer")
    builder.add_edge("scorer", "summarizer")
    builder.add_edge("summarizer", "deliverer")
    builder.add_edge("deliverer", "mark_all_seen")
    builder.add_edge("mark_all_seen", END)

    return builder.compile()
