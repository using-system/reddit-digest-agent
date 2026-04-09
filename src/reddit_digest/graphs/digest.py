from __future__ import annotations

from typing import Any, TypedDict

import aiosqlite
from langgraph.graph import END, START, StateGraph

from reddit_digest.config import AppConfig, SecretsConfig
from reddit_digest.models import RedditPost, Summary
from reddit_digest.nodes.collector import collect_posts
from reddit_digest.nodes.deliverer import deliver_summaries
from reddit_digest.nodes.filterer import filter_posts
from reddit_digest.nodes.summarizer import summarize_posts


class DigestState(TypedDict, total=False):
    subreddits: list[str]
    raw_posts: list[RedditPost]
    filtered_posts: list[RedditPost]
    summaries: list[Summary]
    delivered_ids: list[str]


def build_digest_graph(
    config: AppConfig, secrets: SecretsConfig, conn: aiosqlite.Connection
):
    async def collector_node(state: dict[str, Any]) -> dict[str, Any]:
        return await collect_posts(state, config, secrets)

    async def filterer_node(state: dict[str, Any]) -> dict[str, Any]:
        return await filter_posts(state, conn)

    async def summarizer_node(state: dict[str, Any]) -> dict[str, Any]:
        return await summarize_posts(state, config, secrets)

    async def deliverer_node(state: dict[str, Any]) -> dict[str, Any]:
        return await deliver_summaries(state, config, secrets, conn)

    builder = StateGraph(DigestState)
    builder.add_node("collector", collector_node)
    builder.add_node("filterer", filterer_node)
    builder.add_node("summarizer", summarizer_node)
    builder.add_node("deliverer", deliverer_node)

    builder.add_edge(START, "collector")
    builder.add_edge("collector", "filterer")
    builder.add_edge("filterer", "summarizer")
    builder.add_edge("summarizer", "deliverer")
    builder.add_edge("deliverer", END)

    return builder.compile()
