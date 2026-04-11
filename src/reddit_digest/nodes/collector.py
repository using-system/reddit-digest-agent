from __future__ import annotations

import logging
import time
from typing import Any

from curl_cffi import requests as cffi_requests

from reddit_digest.config import Settings
from reddit_digest.models import RedditPost
from reddit_digest.telemetry import get_meter

logger = logging.getLogger(__name__)


def _fetch_top_comments(
    session: cffi_requests.Session,
    subreddit: str,
    post_id: str,
    limit: int,
) -> list[str]:
    url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json"
    resp = session.get(url, params={"limit": limit, "raw_json": 1}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if len(data) < 2:
        return []
    children = data[1]["data"]["children"]
    comments = []
    for child in children:
        if child["kind"] != "t1":
            continue
        body = child["data"].get("body", "").strip()
        if body:
            comments.append(body)
        if len(comments) >= limit:
            break
    return comments


async def collect_posts(state: dict[str, Any], settings: Settings) -> dict[str, Any]:
    meter = get_meter("reddit_digest.collector")
    posts_counter = meter.create_counter(
        "reddit_digest.reddit.posts.collected",
        description="Posts collected from Reddit",
    )
    fetch_histogram = meter.create_histogram(
        "reddit_digest.reddit.fetch.duration",
        unit="s",
        description="Reddit fetch duration per subreddit",
    )

    all_posts: list[RedditPost] = []

    session = cffi_requests.Session(impersonate="chrome")
    session.get("https://www.reddit.com/", timeout=30)

    for i, sub_name in enumerate(state["subreddits"]):
        if i > 0 and settings.reddit_fetch_delay > 0:
            time.sleep(settings.reddit_fetch_delay / 1000)
        sub_start = time.monotonic()
        sub_post_count = 0
        try:
            params: dict[str, Any] = {
                "limit": settings.reddit_limit,
                "raw_json": 1,
            }
            if settings.reddit_sort == "top":
                params["t"] = settings.reddit_time_filter

            url = f"https://www.reddit.com/r/{sub_name}/{settings.reddit_sort}.json"
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for child in data["data"]["children"]:
                post_data = child["data"]
                post_id = post_data["id"]

                top_comments: list[str] = []
                if settings.reddit_comments_limit > 0:
                    if settings.reddit_fetch_delay > 0:
                        time.sleep(settings.reddit_fetch_delay / 1000)
                    try:
                        top_comments = _fetch_top_comments(
                            session,
                            sub_name,
                            post_id,
                            settings.reddit_comments_limit,
                        )
                    except Exception:
                        logger.warning(
                            "Failed to fetch comments for %s in r/%s",
                            post_id,
                            sub_name,
                        )

                all_posts.append(
                    RedditPost(
                        reddit_id=post_id,
                        subreddit=sub_name,
                        title=post_data["title"],
                        url=post_data["url"],
                        score=post_data["score"],
                        num_comments=post_data["num_comments"],
                        selftext=post_data.get("selftext", ""),
                        created_utc=post_data["created_utc"],
                        top_comments=top_comments,
                    )
                )
                sub_post_count += 1
        except Exception:
            logger.exception("Failed to fetch posts from r/%s", sub_name)
        finally:
            elapsed = time.monotonic() - sub_start
            fetch_histogram.record(elapsed, {"subreddit": sub_name})
            posts_counter.add(sub_post_count, {"subreddit": sub_name})

    session.close()

    logger.info(
        "Collected %d posts from %d subreddits",
        len(all_posts),
        len(state["subreddits"]),
    )
    return {"raw_posts": all_posts}
