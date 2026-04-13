from __future__ import annotations

import argparse
import asyncio
import logging
import time
from uuid import uuid4

from openinference.instrumentation import using_attributes

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from reddit_digest.config import load_settings
from reddit_digest.db import init_db
from reddit_digest.graphs.digest import build_digest_graph
from reddit_digest.graphs.feedback import build_feedback_graph
from reddit_digest.telegram.bot import create_bot
from reddit_digest.telemetry import get_meter, get_tracer, setup_telemetry

logger = logging.getLogger(__name__)


async def run_digest(settings, db_conn) -> None:
    tracer = get_tracer("reddit_digest.main")
    meter = get_meter("reddit_digest.main")
    runs_counter = meter.create_counter(
        "reddit_digest.digest.runs",
        description="Number of digest runs",
    )
    duration_histogram = meter.create_histogram(
        "reddit_digest.digest.duration",
        unit="s",
        description="Total duration of a digest run",
    )

    start = time.monotonic()
    session_id = str(uuid4())
    logger.info("Running scheduled digest (session_id=%s)...", session_id)

    with tracer.start_as_current_span("digest.run") as span:
        span.set_attribute("digest.subreddits", settings.reddit_subreddits)
        span.set_attribute("digest.cron_expression", settings.digest_cron)
        span.set_attribute("session.id", session_id)
        try:
            graph = build_digest_graph(settings, db_conn)
            with using_attributes(session_id=session_id):
                result = await graph.ainvoke({"subreddits": settings.reddit_subreddits})
            delivered = len(result.get("delivered_ids", []))
            logger.info("Digest complete: delivered %d summaries", delivered)
            runs_counter.add(1, {"status": "success"})
        except Exception:
            logger.exception("Digest run failed")
            runs_counter.add(1, {"status": "error"})
            raise
        finally:
            elapsed = time.monotonic() - start
            duration_histogram.record(elapsed)


async def run_once() -> None:
    """Run a single digest immediately and exit."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    setup_telemetry()

    settings = load_settings()
    db_conn = await init_db(settings.db_path)
    try:
        await run_digest(settings, db_conn)
    finally:
        await db_conn.close()


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    setup_telemetry()

    settings = load_settings()
    db_conn = await init_db(settings.db_path)

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
    parser = argparse.ArgumentParser(description="Reddit Digest Agent")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single digest immediately and exit (no scheduler, no bot)",
    )
    args = parser.parse_args()

    if args.once:
        asyncio.run(run_once())
    else:
        asyncio.run(main())


if __name__ == "__main__":
    main_sync()
