from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from reddit_digest.config import load_settings
from reddit_digest.db import init_db
from reddit_digest.graphs.digest import build_digest_graph
from reddit_digest.graphs.feedback import build_feedback_graph
from reddit_digest.telegram.bot import create_bot

logger = logging.getLogger(__name__)


async def run_digest(settings, db_conn) -> None:
    logger.info("Running scheduled digest...")
    graph = build_digest_graph(settings, db_conn)
    result = await graph.ainvoke({"subreddits": settings.reddit_subreddits})
    logger.info(
        "Digest complete: delivered %d summaries",
        len(result.get("delivered_ids", [])),
    )


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    settings = load_settings()
    db_conn = await init_db()

    feedback_graph = build_feedback_graph(settings, db_conn)
    app = create_bot(settings.telegram_bot_token, feedback_graph, db_conn)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_digest,
        CronTrigger.from_crontab(settings.digest_cron),
        args=[settings, db_conn],
        id="daily_digest",
        name="Daily Reddit Digest",
    )
    scheduler.start()
    logger.info("Scheduler started: digest cron=%s", settings.digest_cron)

    async with app:
        await app.start()
        logger.info("Telegram bot started, listening for reactions...")
        await app.updater.start_polling()

        try:
            while True:
                await asyncio.sleep(3600)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Shutting down...")
        finally:
            await app.updater.stop()
            await app.stop()
            scheduler.shutdown()
            await db_conn.close()


def main_sync() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
