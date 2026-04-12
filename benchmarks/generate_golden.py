#!/usr/bin/env python3
"""Generate the golden dataset for LLM benchmarking.

Usage:
    uv run python benchmarks/generate_golden.py [--model MODEL] [--output PATH]

Requires GITHUB_TOKEN or OPENAI_API_KEY env var.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from curl_cffi import requests as cffi_requests
from langchain_openai import ChatOpenAI

from reddit_digest.config import Settings
from reddit_digest.nodes.scorer import SCORE_PROMPT
from reddit_digest.nodes.scorer import _build_post_block as scorer_build_block
from reddit_digest.nodes.summarizer import PROMPT_TEMPLATE
from reddit_digest.nodes.summarizer import _build_post_block as summarizer_build_block
from reddit_digest.models import RedditPost

logger = logging.getLogger(__name__)

GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
DEFAULT_REF_MODEL = "openai/gpt-4o"


def fetch_posts(subreddits: list[str], limit: int = 5) -> list[RedditPost]:
    """Fetch top posts from Reddit public JSON endpoints."""
    session = cffi_requests.Session(impersonate="chrome")
    session.get("https://www.reddit.com/", timeout=30)

    posts: list[RedditPost] = []
    for i, sub in enumerate(subreddits):
        if i > 0:
            time.sleep(0.5)
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json"
            resp = session.get(url, params={"limit": limit, "raw_json": 1}, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            for child in data["data"]["children"]:
                pd = child["data"]
                post_id = pd["id"]

                # Fetch comments
                top_comments: list[str] = []
                time.sleep(0.3)
                try:
                    c_url = f"https://www.reddit.com/r/{sub}/comments/{post_id}.json"
                    c_resp = session.get(
                        c_url, params={"limit": 5, "raw_json": 1}, timeout=30
                    )
                    c_resp.raise_for_status()
                    c_data = c_resp.json()
                    if len(c_data) >= 2:
                        for c in c_data[1]["data"]["children"]:
                            if c["kind"] == "t1":
                                body = c["data"].get("body", "").strip()
                                if body:
                                    top_comments.append(body)
                                if len(top_comments) >= 5:
                                    break
                except Exception:
                    logger.warning("Failed to fetch comments for %s", post_id)

                posts.append(
                    RedditPost(
                        reddit_id=post_id,
                        subreddit=sub,
                        title=pd["title"],
                        url=pd["url"],
                        score=pd["score"],
                        num_comments=pd["num_comments"],
                        selftext=pd.get("selftext", ""),
                        created_utc=pd["created_utc"],
                        top_comments=top_comments,
                    )
                )
        except Exception:
            logger.exception("Failed to fetch posts from r/%s", sub)

    session.close()
    return posts


async def generate_reference_outputs(
    posts: list[RedditPost],
    model: str,
    api_key: str,
    language: str = "fr",
) -> dict:
    """Call the reference model to produce gold standard scores and summaries."""
    from collections import defaultdict

    llm = ChatOpenAI(
        base_url=GITHUB_MODELS_BASE_URL,
        model=model,
        api_key=api_key,
    )

    by_sub: dict[str, list[RedditPost]] = defaultdict(list)
    for post in posts:
        by_sub[post.subreddit].append(post)

    all_scores: dict[str, int] = {}
    all_summaries: dict[str, str] = {}

    for subreddit, sub_posts in by_sub.items():
        # Score
        posts_block = "\n\n---\n\n".join(scorer_build_block(p) for p in sub_posts)
        score_prompt = SCORE_PROMPT.format(subreddit=subreddit, posts_block=posts_block)
        score_resp = await llm.ainvoke(score_prompt)
        score_data = json.loads(score_resp.content)
        all_scores.update(score_data.get("scores", {}))

        # Summarize
        posts_block = "\n\n---\n\n".join(summarizer_build_block(p) for p in sub_posts)
        sum_prompt = PROMPT_TEMPLATE.format(
            language=language, subreddit=subreddit, posts_block=posts_block
        )
        sum_resp = await llm.ainvoke(sum_prompt)
        sum_data = json.loads(sum_resp.content)
        all_summaries.update(sum_data.get("summaries", {}))

    return {"scores": all_scores, "summaries": all_summaries}


async def main() -> None:
    import os

    parser = argparse.ArgumentParser(description="Generate golden benchmark dataset")
    parser.add_argument("--model", default=DEFAULT_REF_MODEL, help="Reference model")
    parser.add_argument(
        "--output",
        default="benchmarks/fixtures/golden_posts.json",
        help="Output path",
    )
    parser.add_argument("--language", default="fr", help="Summary language")
    args = parser.parse_args()

    api_key = os.environ.get("GITHUB_TOKEN") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: set GITHUB_TOKEN or OPENAI_API_KEY env var", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)

    # Use project defaults for subreddits
    subreddits = Settings.model_fields["reddit_subreddits"].default
    logger.info("Fetching posts from: %s", subreddits)

    posts = fetch_posts(subreddits)
    logger.info("Fetched %d posts", len(posts))

    logger.info("Generating reference outputs with %s...", args.model)
    ref_outputs = await generate_reference_outputs(
        posts, args.model, api_key, args.language
    )

    golden = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "reference_model": args.model,
            "subreddits": subreddits,
        },
        "posts": [p.model_dump() for p in posts],
        "reference_outputs": ref_outputs,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(golden, indent=2, ensure_ascii=False))
    logger.info("Written golden dataset to %s (%d posts)", output_path, len(posts))


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
