from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from reddit_digest.db import get_post_by_reddit_id, save_reaction
from reddit_digest.telemetry import get_meter

if TYPE_CHECKING:
    import aiosqlite
    from langgraph.graph.state import CompiledStateGraph

logger = logging.getLogger(__name__)


def create_bot(
    token: str,
    feedback_graph: CompiledStateGraph,
    db_conn: aiosqlite.Connection,
) -> Application:
    app = Application.builder().token(token).build()

    async def handle_callback(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if not query or not query.data:
            return

        await query.answer()

        # Format: "up:1:reddit_id" or "down:2:reddit_id"
        parts = query.data.split(":", 2)
        if len(parts) != 3:
            return

        reaction_type, _num, reddit_id = parts
        if reaction_type not in ("up", "down"):
            return

        message_id = query.message.message_id

        post_meta = await get_post_by_reddit_id(db_conn, reddit_id)
        if not post_meta:
            logger.warning("No post found for reddit_id=%s", reddit_id)
            return

        await save_reaction(db_conn, message_id, reaction_type)

        meter = get_meter("reddit_digest.bot")
        reaction_counter = meter.create_counter(
            "reddit_digest.feedback.reactions",
            description="Reactions received",
        )
        reaction_counter.add(1, {"reaction_type": reaction_type})

        try:
            await feedback_graph.ainvoke(
                {
                    "message_id": message_id,
                    "reaction_type": reaction_type,
                    "post_metadata": post_meta.model_dump(),
                    "preference_update": {},
                }
            )
        except Exception:
            logger.exception("Feedback graph failed for reddit_id=%s", reddit_id)

    app.add_handler(CallbackQueryHandler(handle_callback))
    return app
