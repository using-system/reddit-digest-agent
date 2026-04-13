from __future__ import annotations

from typing import Any, TypedDict

import aiosqlite
from langgraph.graph import END, START, StateGraph

from reddit_digest.config import Settings
from reddit_digest.nodes.feedback import (
    analyze_reaction,
    receive_reaction,
    update_preferences,
)
from reddit_digest.telemetry import get_tracer


class FeedbackState(TypedDict, total=False):
    message_id: int
    reaction_type: str
    post_metadata: dict
    preference_update: dict


def build_feedback_graph(settings: Settings, conn: aiosqlite.Connection):
    tracer = get_tracer("reddit_digest.feedback")

    async def receive_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("feedback.receive_reaction"):
            return await receive_reaction(state, conn)

    async def analyze_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("feedback.analyze"):
            return await analyze_reaction(state, settings)

    async def update_node(state: dict[str, Any]) -> dict[str, Any]:
        with tracer.start_as_current_span("feedback.update_preferences"):
            return await update_preferences(state, conn)

    builder = StateGraph(FeedbackState)
    builder.add_node("receive_reaction", receive_node)
    builder.add_node("analyze", analyze_node)
    builder.add_node("update_preferences", update_node)

    builder.add_edge(START, "receive_reaction")
    builder.add_edge("receive_reaction", "analyze")
    builder.add_edge("analyze", "update_preferences")
    builder.add_edge("update_preferences", END)

    return builder.compile()
