from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

import aiosqlite
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost, Summary
from reddit_digest.telemetry import get_meter

logger = logging.getLogger(__name__)


def _format_subreddit_message(
    subreddit: str,
    summaries: list[Summary],
    posts: list[RedditPost],
) -> str:
    posts_by_id = {p.reddit_id: p for p in posts}
    lines = [f"📌 <b>r/{subreddit}</b>\n"]

    for i, summary in enumerate(summaries, 1):
        post = posts_by_id.get(summary.reddit_id)
        url = post.url if post else ""
        lines.append(f"{i}. {summary.summary_text}")
        if url:
            display_url = url.replace("https://", "")
            lines.append(f"   🔗 {display_url}")
        lines.append("")

    return "\n".join(lines).strip()


def _build_keyboard(summaries: list[Summary]) -> InlineKeyboardMarkup:
    rows = []
    for i, summary in enumerate(summaries, 1):
        rows.append(
            [
                InlineKeyboardButton(
                    f"{i} 👍", callback_data=f"up:{i}:{summary.reddit_id}"
                ),
                InlineKeyboardButton(
                    f"{i} 👎", callback_data=f"down:{i}:{summary.reddit_id}"
                ),
            ]
        )
    return InlineKeyboardMarkup(rows)


async def deliver_summaries(
    state: dict[str, Any],
    settings: Settings,
    conn: aiosqlite.Connection,
) -> dict[str, Any]:
    meter = get_meter("reddit_digest.deliverer")
    sent_counter = meter.create_counter(
        "reddit_digest.telegram.messages.sent",
        description="Telegram messages sent",
    )
    error_counter = meter.create_counter(
        "reddit_digest.telegram.messages.errors",
        description="Telegram send errors",
    )

    summaries: list[Summary] = state["summaries"]
    scored_posts: list[RedditPost] = state.get("scored_posts", [])

    bot = Bot(token=settings.telegram_bot_token)

    if not summaries:
        await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text="Aucun thread pertinent pour aujourd'hui.",
        )
        return {"delivered_ids": []}

    by_sub: dict[str, list[Summary]] = defaultdict(list)
    for s in summaries:
        by_sub[s.subreddit].append(s)

    delivered_ids: list[str] = []

    for i, (subreddit, sub_summaries) in enumerate(by_sub.items()):
        if i > 0 and settings.telegram_send_delay > 0:
            await asyncio.sleep(settings.telegram_send_delay / 1000)

        try:
            text = _format_subreddit_message(subreddit, sub_summaries, scored_posts)
            keyboard = _build_keyboard(sub_summaries)

            msg = await bot.send_message(
                chat_id=settings.telegram_chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            delivered_ids.append(str(msg.message_id))
            sent_counter.add(1, {"subreddit": subreddit})
        except Exception:
            logger.exception("Failed to deliver digest for r/%s", subreddit)
            error_counter.add(1)

    logger.info(
        "Delivered %d messages for %d subreddits",
        len(delivered_ids),
        len(by_sub),
    )
    return {"delivered_ids": delivered_ids}
