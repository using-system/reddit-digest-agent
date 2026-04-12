#!/usr/bin/env python3
"""Benchmark a single LLM model against the golden dataset.

Usage:
    python benchmarks/bench_model.py --model MODEL --fixture PATH --output PATH
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import yaml
from langchain_openai import ChatOpenAI

from reddit_digest.models import RedditPost
from reddit_digest.nodes.scorer import SCORE_PROMPT
from reddit_digest.nodes.scorer import _build_post_block as scorer_build_block
from reddit_digest.nodes.summarizer import PROMPT_TEMPLATE
from reddit_digest.nodes.summarizer import _build_post_block as summarizer_build_block

logger = logging.getLogger(__name__)

GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
PRICING_PATH = Path(__file__).parent / "model_pricing.yaml"


def load_fixture(path: str) -> dict:
    """Load golden dataset from JSON file."""
    return json.loads(Path(path).read_text())


def load_pricing() -> dict[str, dict[str, float]]:
    """Load model pricing from YAML."""
    data = yaml.safe_load(PRICING_PATH.read_text())
    return data.get("models", {})


def compute_cost(
    model: str,
    tokens_prompt: int,
    tokens_completion: int,
    pricing: dict[str, dict[str, float]],
) -> float:
    """Compute estimated cost in USD."""
    model_pricing = pricing.get(model)
    if not model_pricing:
        return 0.0
    prompt_cost = (tokens_prompt / 1_000_000) * model_pricing["prompt_per_1m"]
    completion_cost = (tokens_completion / 1_000_000) * model_pricing["completion_per_1m"]
    return prompt_cost + completion_cost


async def run_benchmark(
    model: str,
    fixture_path: str,
    output_path: str,
) -> None:
    api_key = os.environ.get("GITHUB_TOKEN") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: set GITHUB_TOKEN or OPENAI_API_KEY env var", file=sys.stderr)
        sys.exit(1)

    fixture = load_fixture(fixture_path)
    pricing = load_pricing()
    posts = [RedditPost(**p) for p in fixture["posts"]]
    ref_scores = fixture["reference_outputs"]["scores"]

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
    errors: list[str] = []
    latencies: list[float] = []
    json_valid_count = 0
    json_total_count = 0
    total_tokens_prompt = 0
    total_tokens_completion = 0

    for subreddit, sub_posts in by_sub.items():
        # --- Score ---
        posts_block = "\n\n---\n\n".join(scorer_build_block(p) for p in sub_posts)
        prompt = SCORE_PROMPT.format(subreddit=subreddit, posts_block=posts_block)

        json_total_count += 1
        start = time.monotonic()
        try:
            response = await llm.ainvoke(prompt)
            elapsed_ms = (time.monotonic() - start) * 1000
            latencies.append(elapsed_ms)

            # Extract token usage from response metadata
            usage = getattr(response, "response_metadata", {}).get("token_usage", {})
            total_tokens_prompt += usage.get("prompt_tokens", 0)
            total_tokens_completion += usage.get("completion_tokens", 0)

            data = json.loads(response.content)
            scores = data.get("scores", {})
            all_scores.update(scores)
            json_valid_count += 1
        except json.JSONDecodeError as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            latencies.append(elapsed_ms)
            errors.append(f"scorer/{subreddit}: JSON parse error: {e}")
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            latencies.append(elapsed_ms)
            errors.append(f"scorer/{subreddit}: {type(e).__name__}: {e}")

        # --- Summarize ---
        posts_block = "\n\n---\n\n".join(summarizer_build_block(p) for p in sub_posts)
        prompt = PROMPT_TEMPLATE.format(
            language="fr", subreddit=subreddit, posts_block=posts_block
        )

        json_total_count += 1
        start = time.monotonic()
        try:
            response = await llm.ainvoke(prompt)
            elapsed_ms = (time.monotonic() - start) * 1000
            latencies.append(elapsed_ms)

            usage = getattr(response, "response_metadata", {}).get("token_usage", {})
            total_tokens_prompt += usage.get("prompt_tokens", 0)
            total_tokens_completion += usage.get("completion_tokens", 0)

            data = json.loads(response.content)
            summaries = data.get("summaries", {})
            all_summaries.update(summaries)
            json_valid_count += 1
        except json.JSONDecodeError as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            latencies.append(elapsed_ms)
            errors.append(f"summarizer/{subreddit}: JSON parse error: {e}")
        except Exception as e:
            elapsed_ms = (time.monotonic() - start) * 1000
            latencies.append(elapsed_ms)
            errors.append(f"summarizer/{subreddit}: {type(e).__name__}: {e}")

    # Compute metrics
    json_valid_rate = json_valid_count / json_total_count if json_total_count > 0 else 0.0
    latency_avg = sum(latencies) / len(latencies) if latencies else 0.0
    sorted_lat = sorted(latencies)
    latency_p95 = (
        sorted_lat[int(len(sorted_lat) * 0.95)] if len(sorted_lat) >= 2 else latency_avg
    )

    # Score MAE vs reference
    score_diffs = []
    for post_id, ref_score in ref_scores.items():
        if post_id in all_scores:
            score_diffs.append(abs(all_scores[post_id] - ref_score))
    score_mae = sum(score_diffs) / len(score_diffs) if score_diffs else 10.0

    estimated_cost = compute_cost(model, total_tokens_prompt, total_tokens_completion, pricing)

    result = {
        "model": model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "json_valid_rate": round(json_valid_rate, 4),
            "latency_avg_ms": round(latency_avg, 1),
            "latency_p95_ms": round(latency_p95, 1),
            "estimated_cost_usd": round(estimated_cost, 6),
            "score_mae": round(score_mae, 2),
            "tokens_prompt": total_tokens_prompt,
            "tokens_completion": total_tokens_completion,
        },
        "raw_outputs": {
            "scores": all_scores,
            "summaries": all_summaries,
        },
        "errors": errors,
    }

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    logger.info("Benchmark complete for %s → %s", model, output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark a single LLM model")
    parser.add_argument("--model", required=True, help="Model identifier")
    parser.add_argument(
        "--fixture",
        default="benchmarks/fixtures/golden_posts.json",
        help="Path to golden dataset",
    )
    parser.add_argument("--output", default="results.json", help="Output path")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    import asyncio

    asyncio.run(run_benchmark(args.model, args.fixture, args.output))


if __name__ == "__main__":
    main()
