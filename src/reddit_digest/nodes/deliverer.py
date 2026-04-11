from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiosqlite
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from reddit_digest.config import Settings
from reddit_digest.db import save_sent_post
from reddit_digest.models import Summary

logger = logging.getLogger(__name__)


def _format_message(summary: Summary) -> str:
    return (
        f"<b>r/{summary.subreddit}</b>\n\n"
        f"<b>{summary.title}</b>\n\n"
        f"{summary.summary_text}\n\n"
        f"🏷 {summary.category}"
    )


def _build_keyboard(reddit_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔥 Plus de ça", callback_data=f"more:{reddit_id}"
                ),
                InlineKeyboardButton("👎 Moins", callback_data=f"less:{reddit_id}"),
                InlineKeyboardButton(
                    "🚫 Pas pertinent", callback_data=f"irrelevant:{reddit_id}"
                ),
            ]
        ]
    )


async def deliver_summaries(
    state: dict[str, Any],
    settings: Settings,
    conn: aiosqlite.Connection,
) -> dict[str, Any]:
    summaries: list[Summary] = state["summaries"]
    if not summaries:
        return {"delivered_ids": []}

    bot = Bot(token=settings.telegram_bot_token)

    delivered_ids: list[str] = []
    for i, summary in enumerate(summaries):
        if i > 0 and settings.telegram_send_delay > 0:
            await asyncio.sleep(settings.telegram_send_delay / 1000)
        try:
            msg = await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=_format_message(summary),
                reply_markup=_build_keyboard(summary.reddit_id),
                parse_mode="HTML",
            )
            matching_post = None
            for post in state.get("filtered_posts", []):
                if post.reddit_id == summary.reddit_id:
                    matching_post = post
                    break

            if matching_post:
                await save_sent_post(
                    conn,
                    matching_post,
                    telegram_message_id=msg.message_id,
                    category=summary.category,
                    keywords=summary.keywords,
                )

            delivered_ids.append(str(msg.message_id))
        except Exception:
            logger.exception("Failed to deliver summary for %s", summary.reddit_id)

    logger.info("Delivered %d/%d summaries", len(delivered_ids), len(summaries))
    return {"delivered_ids": delivered_ids}
