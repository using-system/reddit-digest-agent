# LLM Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a benchmark system that compares LLM models for the reddit-digest-agent using GitHub Actions matrix strategy, hybrid evaluation, and GitHub Models.

**Architecture:** GitHub Actions workflow with matrix strategy runs `bench_model.py` per model in parallel, each producing a `results.json` artifact. A final `report` job runs `aggregate.py` which downloads all artifacts, calls an LLM-judge for summary quality, computes a weighted composite score, and writes the full report to `$GITHUB_STEP_SUMMARY`.

**Tech Stack:** Python 3.11+, langchain-openai (ChatOpenAI), GitHub Actions (matrix + artifacts), GitHub Models API (`https://models.inference.ai.azure.com`), pydantic for data models, pytest + pytest-asyncio for tests.

---

## File Structure

```
benchmarks/
├── __init__.py                    # Package marker
├── fixtures/
│   └── golden_posts.json          # Static golden dataset (committed after generation)
├── model_pricing.yaml             # Cost per model (committed)
├── generate_golden.py             # Bootstrap the golden dataset (manual use)
├── bench_model.py                 # Benchmark one model (called by matrix job)
├── aggregate.py                   # Aggregation + LLM-judge + report (called by report job)
.github/workflows/
└── benchmark.yml                  # GitHub Actions workflow
tests/
└── test_benchmark.py              # Tests for bench_model and aggregate
```

---

### Task 1: Model pricing YAML

**Files:**
- Create: `benchmarks/model_pricing.yaml`

- [ ] **Step 1: Create the pricing file**

```yaml
# Pricing per 1M tokens (USD) — GitHub Models / Azure AI
# Source: https://github.com/marketplace/models
models:
  openai/gpt-4o:
    prompt_per_1m: 2.50
    completion_per_1m: 10.00
  openai/gpt-4o-mini:
    prompt_per_1m: 0.15
    completion_per_1m: 0.60
  openai/gpt-4.1:
    prompt_per_1m: 2.00
    completion_per_1m: 8.00
  openai/gpt-4.1-mini:
    prompt_per_1m: 0.40
    completion_per_1m: 1.60
  openai/gpt-4.1-nano:
    prompt_per_1m: 0.10
    completion_per_1m: 0.40
  mistral-ai/mistral-large:
    prompt_per_1m: 2.00
    completion_per_1m: 6.00
  mistral-ai/mistral-small:
    prompt_per_1m: 0.10
    completion_per_1m: 0.30
  meta/llama-4-scout:
    prompt_per_1m: 0.15
    completion_per_1m: 0.40
  microsoft/phi-4:
    prompt_per_1m: 0.07
    completion_per_1m: 0.14
```

- [ ] **Step 2: Create package marker**

Create `benchmarks/__init__.py` as an empty file and `benchmarks/fixtures/` directory.

- [ ] **Step 3: Commit**

```bash
git add benchmarks/__init__.py benchmarks/model_pricing.yaml
git commit -m "chore(benchmark): add model pricing yaml and package init"
```

---

### Task 2: Golden dataset generator

**Files:**
- Create: `benchmarks/generate_golden.py`
- Create: `benchmarks/fixtures/.gitkeep`

This script is run manually to bootstrap `golden_posts.json`. It fetches real Reddit posts and calls a reference model to produce gold standard scores and summaries.

- [ ] **Step 1: Write the generator script**

```python
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
```

- [ ] **Step 2: Create fixtures directory marker**

Create `benchmarks/fixtures/.gitkeep` (empty file) so the directory exists in git before the golden dataset is generated.

- [ ] **Step 3: Commit**

```bash
git add benchmarks/generate_golden.py benchmarks/fixtures/.gitkeep
git commit -m "feat(benchmark): add golden dataset generator script"
```

---

### Task 3: Per-model benchmark script

**Files:**
- Create: `benchmarks/bench_model.py`

- [ ] **Step 1: Write bench_model.py**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add benchmarks/bench_model.py
git commit -m "feat(benchmark): add per-model benchmark script"
```

---

### Task 4: Aggregation and LLM-as-Judge script

**Files:**
- Create: `benchmarks/aggregate.py`

- [ ] **Step 1: Write aggregate.py**

```python
#!/usr/bin/env python3
"""Aggregate benchmark results and produce a comparison report.

Usage:
    python benchmarks/aggregate.py --results-dir DIR --fixture PATH [--judge-model MODEL] [--output PATH]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
DEFAULT_JUDGE_MODEL = "openai/gpt-4o"

JUDGE_PROMPT = """You are evaluating the quality of AI-generated summaries of Reddit posts.
The summaries are in French. For each post, multiple models produced a summary.

Rate each summary on 3 criteria (integer score 1-10):
- fidelity: does the summary accurately reflect the post content?
- clarity: is it well-written and understandable in French?
- concision: is it short enough without losing essentials?

{posts_block}

Return ONLY valid JSON (no markdown, no code fences):
{{"evaluations": {{{evaluations_schema}}}}}"""

# Composite weights aligned with user priorities:
# D (cost) > C (reliability) > B (summaries) > A (scoring)
WEIGHTS = {
    "cost": 0.35,
    "json_valid": 0.25,
    "latency": 0.10,
    "summary_quality": 0.20,
    "score_distance": 0.10,
}


def load_results(results_dir: str) -> list[dict]:
    """Load all results.json files from subdirectories."""
    results = []
    base = Path(results_dir)
    for path in sorted(base.rglob("results.json")):
        data = json.loads(path.read_text())
        results.append(data)
        logger.info("Loaded results for %s", data["model"])
    return results


def normalize_min_max(values: list[float], inverse: bool = False) -> list[float]:
    """Normalize values to 0-1 range. If inverse, lower raw values get higher scores."""
    if not values:
        return []
    min_v, max_v = min(values), max(values)
    if max_v == min_v:
        return [1.0] * len(values)
    normalized = [(v - min_v) / (max_v - min_v) for v in values]
    if inverse:
        normalized = [1.0 - n for n in normalized]
    return normalized


async def run_judge(
    results: list[dict],
    fixture: dict,
    judge_model: str,
    api_key: str,
) -> dict[str, dict[str, float]]:
    """Run LLM-as-Judge to evaluate summary quality across all models.

    Returns: {model: {"fidelity": avg, "clarity": avg, "concision": avg, "average": avg}}
    """
    llm = ChatOpenAI(
        base_url=GITHUB_MODELS_BASE_URL,
        model=judge_model,
        api_key=api_key,
    )

    posts = fixture["posts"]
    model_names = [r["model"] for r in results]
    model_summaries = {r["model"]: r["raw_outputs"].get("summaries", {}) for r in results}

    # Build per-post evaluation blocks, batch by ~5 posts
    all_evaluations: dict[str, dict[str, dict[str, int]]] = {}
    batch_size = 5

    for batch_start in range(0, len(posts), batch_size):
        batch_posts = posts[batch_start : batch_start + batch_size]

        posts_block_parts = []
        for post in batch_posts:
            pid = post["id"] if isinstance(post, dict) else post.reddit_id
            title = post["title"] if isinstance(post, dict) else post.title
            selftext = post.get("selftext", "") if isinstance(post, dict) else post.selftext

            lines = [f'Post "{pid}" - "{title}"']
            lines.append(f"Original content: \"{selftext[:500]}\"")
            for model_name in model_names:
                summary = model_summaries[model_name].get(pid, "(no summary)")
                safe_name = model_name.replace("/", "_")
                lines.append(f'- {safe_name}: "{summary}"')
            posts_block_parts.append("\n".join(lines))

        posts_block = "\n\n".join(posts_block_parts)

        # Build schema hint
        post_ids = [
            p["id"] if isinstance(p, dict) else p.reddit_id for p in batch_posts
        ]
        safe_models = [m.replace("/", "_") for m in model_names]
        schema_parts = []
        for pid in post_ids:
            model_parts = ", ".join(
                f'"{m}": {{"fidelity": N, "clarity": N, "concision": N}}'
                for m in safe_models
            )
            schema_parts.append(f'"{pid}": {{{model_parts}}}')
        evaluations_schema = ", ".join(schema_parts)

        prompt = JUDGE_PROMPT.format(
            posts_block=posts_block, evaluations_schema=evaluations_schema
        )

        try:
            response = await llm.ainvoke(prompt)
            data = json.loads(response.content)
            evals = data.get("evaluations", {})
            all_evaluations.update(evals)
        except Exception:
            logger.exception("Judge failed for batch starting at %d", batch_start)

    # Aggregate per model
    model_scores: dict[str, dict[str, float]] = {m.replace("/", "_"): {"fidelity": [], "clarity": [], "concision": []} for m in model_names}

    for pid, post_evals in all_evaluations.items():
        for safe_model, criteria in post_evals.items():
            if safe_model in model_scores:
                for key in ("fidelity", "clarity", "concision"):
                    val = criteria.get(key)
                    if isinstance(val, (int, float)):
                        model_scores[safe_model][key].append(val)

    result: dict[str, dict[str, float]] = {}
    for model_name in model_names:
        safe_name = model_name.replace("/", "_")
        scores = model_scores.get(safe_name, {})
        avg_fidelity = sum(scores.get("fidelity", [0])) / max(len(scores.get("fidelity", [0])), 1)
        avg_clarity = sum(scores.get("clarity", [0])) / max(len(scores.get("clarity", [0])), 1)
        avg_concision = sum(scores.get("concision", [0])) / max(len(scores.get("concision", [0])), 1)
        average = (avg_fidelity + avg_clarity + avg_concision) / 3
        result[model_name] = {
            "fidelity": round(avg_fidelity, 1),
            "clarity": round(avg_clarity, 1),
            "concision": round(avg_concision, 1),
            "average": round(average, 1),
        }

    return result


def compute_composite(
    results: list[dict],
    judge_scores: dict[str, dict[str, float]],
) -> list[dict]:
    """Compute weighted composite score for each model and return sorted list."""
    models = [r["model"] for r in results]

    costs = [r["metrics"]["estimated_cost_usd"] for r in results]
    json_rates = [r["metrics"]["json_valid_rate"] for r in results]
    latencies = [r["metrics"]["latency_avg_ms"] for r in results]
    summary_avgs = [judge_scores.get(m, {}).get("average", 0.0) for m in models]
    maes = [r["metrics"]["score_mae"] for r in results]

    norm_cost = normalize_min_max(costs, inverse=True)
    norm_json = normalize_min_max(json_rates, inverse=False)
    norm_latency = normalize_min_max(latencies, inverse=True)
    norm_summary = normalize_min_max(summary_avgs, inverse=False)
    norm_mae = normalize_min_max(maes, inverse=True)

    ranked = []
    for i, r in enumerate(results):
        composite = (
            WEIGHTS["cost"] * norm_cost[i]
            + WEIGHTS["json_valid"] * norm_json[i]
            + WEIGHTS["latency"] * norm_latency[i]
            + WEIGHTS["summary_quality"] * norm_summary[i]
            + WEIGHTS["score_distance"] * norm_mae[i]
        )
        ranked.append({
            "model": r["model"],
            "metrics": r["metrics"],
            "judge": judge_scores.get(r["model"], {}),
            "composite": round(composite, 4),
            "raw_outputs": r.get("raw_outputs", {}),
            "errors": r.get("errors", []),
        })

    ranked.sort(key=lambda x: x["composite"], reverse=True)
    return ranked


def generate_report(
    ranked: list[dict],
    fixture: dict,
) -> str:
    """Generate Markdown report for GitHub Step Summary."""
    if not ranked:
        return "## Benchmark Report\n\nNo results to report.\n"

    best = ranked[0]
    lines = [
        f"## Recommendation: {best['model']} (score: {best['composite']})",
        "",
        "| Model | Cost | JSON OK | Latency (avg) | Summaries | Scoring MAE | **Composite** |",
        "|-------|------|---------|---------------|-----------|-------------|---------------|",
    ]

    for r in ranked:
        m = r["metrics"]
        j = r.get("judge", {})
        summary_score = j.get("average", "N/A")
        if isinstance(summary_score, float):
            summary_score = f"{summary_score}/10"
        lines.append(
            f"| {r['model']} "
            f"| ${m['estimated_cost_usd']:.4f} "
            f"| {m['json_valid_rate']:.0%} "
            f"| {m['latency_avg_ms']:.0f}ms "
            f"| {summary_score} "
            f"| {m['score_mae']:.1f} "
            f"| **{r['composite']}** |"
        )

    lines.append("")

    # Expandable details per model
    ref_scores = fixture.get("reference_outputs", {}).get("scores", {})

    for r in ranked:
        model = r["model"]
        lines.append(f"<details><summary>{model} — details</summary>")
        lines.append("")

        # Scores table
        lines.append("### Scores")
        lines.append("| Post | Reference | Model | Delta |")
        lines.append("|------|-----------|-------|-------|")
        model_scores = r.get("raw_outputs", {}).get("scores", {})
        for pid, ref_score in ref_scores.items():
            model_score = model_scores.get(pid, "N/A")
            delta = ""
            if isinstance(model_score, (int, float)):
                delta = model_score - ref_score
                delta = f"{delta:+d}" if isinstance(delta, int) else f"{delta:+.0f}"
            lines.append(f"| {pid} | {ref_score} | {model_score} | {delta} |")

        lines.append("")

        # Summaries table
        j = r.get("judge", {})
        lines.append("### Summaries")
        lines.append("| Post | Summary | Fidelity | Clarity | Concision |")
        lines.append("|------|---------|----------|---------|-----------|")
        model_summaries = r.get("raw_outputs", {}).get("summaries", {})
        for post in fixture.get("posts", []):
            pid = post["id"] if isinstance(post, dict) else post.reddit_id
            summary = model_summaries.get(pid, "N/A")
            # Truncate long summaries for the table
            display = summary[:80] + "..." if len(summary) > 80 else summary
            lines.append(f"| {pid} | {display} | — | — | — |")

        lines.append("")

        # Errors
        lines.append("### Errors")
        if r.get("errors"):
            for err in r["errors"]:
                lines.append(f"- {err}")
        else:
            lines.append("None")

        lines.append("")
        lines.append("</details>")
        lines.append("")

    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate benchmark results")
    parser.add_argument("--results-dir", required=True, help="Directory with result artifacts")
    parser.add_argument(
        "--fixture",
        default="benchmarks/fixtures/golden_posts.json",
        help="Path to golden dataset",
    )
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="Judge model")
    parser.add_argument("--output", default="summary.md", help="Output markdown path")
    args = parser.parse_args()

    api_key = os.environ.get("GITHUB_TOKEN") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: set GITHUB_TOKEN or OPENAI_API_KEY env var", file=sys.stderr)
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)

    results = load_results(args.results_dir)
    if not results:
        print("No results found", file=sys.stderr)
        sys.exit(1)

    fixture = json.loads(Path(args.fixture).read_text())

    logger.info("Running LLM judge with %s...", args.judge_model)
    judge_scores = await run_judge(results, fixture, args.judge_model, api_key)

    logger.info("Computing composite scores...")
    ranked = compute_composite(results, judge_scores)

    report = generate_report(ranked, fixture)

    Path(args.output).write_text(report)
    logger.info("Report written to %s", args.output)

    # Also print for piping to GITHUB_STEP_SUMMARY
    print(report)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
```

- [ ] **Step 2: Commit**

```bash
git add benchmarks/aggregate.py
git commit -m "feat(benchmark): add aggregation and LLM-as-Judge report script"
```

---

### Task 5: Tests for benchmark scripts

**Files:**
- Create: `tests/test_benchmark.py`

- [ ] **Step 1: Write tests for bench_model metric computation**

```python
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from benchmarks.bench_model import compute_cost, load_fixture


def test_compute_cost_known_model():
    pricing = {
        "openai/gpt-4o-mini": {"prompt_per_1m": 0.15, "completion_per_1m": 0.60},
    }
    cost = compute_cost("openai/gpt-4o-mini", 1_000_000, 1_000_000, pricing)
    assert cost == pytest.approx(0.75)


def test_compute_cost_unknown_model():
    cost = compute_cost("unknown/model", 1000, 500, {})
    assert cost == 0.0


def test_compute_cost_zero_tokens():
    pricing = {
        "openai/gpt-4o": {"prompt_per_1m": 2.50, "completion_per_1m": 10.00},
    }
    cost = compute_cost("openai/gpt-4o", 0, 0, pricing)
    assert cost == 0.0
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/test_benchmark.py -v`
Expected: 3 PASS

- [ ] **Step 3: Write tests for aggregate normalization and composite**

Add to `tests/test_benchmark.py`:

```python
from benchmarks.aggregate import normalize_min_max, compute_composite, generate_report


def test_normalize_min_max_basic():
    result = normalize_min_max([10, 20, 30])
    assert result == [0.0, 0.5, 1.0]


def test_normalize_min_max_inverse():
    result = normalize_min_max([10, 20, 30], inverse=True)
    assert result == [1.0, 0.5, 0.0]


def test_normalize_min_max_equal_values():
    result = normalize_min_max([5, 5, 5])
    assert result == [1.0, 1.0, 1.0]


def test_normalize_min_max_empty():
    result = normalize_min_max([])
    assert result == []


def test_compute_composite_ranks_correctly():
    results = [
        {
            "model": "cheap-model",
            "metrics": {
                "json_valid_rate": 1.0,
                "latency_avg_ms": 500,
                "latency_p95_ms": 800,
                "estimated_cost_usd": 0.001,
                "score_mae": 1.5,
                "tokens_prompt": 1000,
                "tokens_completion": 200,
            },
            "raw_outputs": {"scores": {}, "summaries": {}},
            "errors": [],
        },
        {
            "model": "expensive-model",
            "metrics": {
                "json_valid_rate": 1.0,
                "latency_avg_ms": 3000,
                "latency_p95_ms": 5000,
                "estimated_cost_usd": 0.050,
                "score_mae": 0.5,
                "tokens_prompt": 1000,
                "tokens_completion": 200,
            },
            "raw_outputs": {"scores": {}, "summaries": {}},
            "errors": [],
        },
    ]
    judge_scores = {
        "cheap-model": {"fidelity": 7.0, "clarity": 7.0, "concision": 7.0, "average": 7.0},
        "expensive-model": {"fidelity": 9.0, "clarity": 9.0, "concision": 9.0, "average": 9.0},
    }

    ranked = compute_composite(results, judge_scores)
    # Cheap model should rank higher due to cost weight (35%)
    assert ranked[0]["model"] == "cheap-model"
    assert ranked[0]["composite"] > ranked[1]["composite"]


def test_generate_report_contains_recommendation():
    ranked = [
        {
            "model": "best-model",
            "metrics": {
                "json_valid_rate": 1.0,
                "latency_avg_ms": 500,
                "latency_p95_ms": 800,
                "estimated_cost_usd": 0.001,
                "score_mae": 1.0,
                "tokens_prompt": 1000,
                "tokens_completion": 200,
            },
            "judge": {"fidelity": 8.0, "clarity": 8.0, "concision": 8.0, "average": 8.0},
            "composite": 0.92,
            "raw_outputs": {"scores": {"p1": 8}, "summaries": {"p1": "Un résumé"}},
            "errors": [],
        },
    ]
    fixture = {
        "posts": [{"id": "p1", "title": "Test", "selftext": "Content"}],
        "reference_outputs": {"scores": {"p1": 8}},
    }

    report = generate_report(ranked, fixture)
    assert "## Recommendation: best-model" in report
    assert "| best-model" in report
    assert "<details>" in report


def test_generate_report_empty():
    report = generate_report([], {})
    assert "No results" in report
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/test_benchmark.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_benchmark.py
git commit -m "test(benchmark): add tests for bench_model and aggregate scripts"
```

---

### Task 6: GitHub Actions workflow

**Files:**
- Create: `.github/workflows/benchmark.yml`

- [ ] **Step 1: Write the workflow file**

```yaml
name: LLM Benchmark

on:
  workflow_dispatch:
    inputs:
      models:
        description: "JSON array of models to benchmark"
        required: false
        default: '["openai/gpt-4o","openai/gpt-4o-mini","openai/gpt-4.1","openai/gpt-4.1-mini","openai/gpt-4.1-nano","mistral-ai/mistral-large","mistral-ai/mistral-small","meta/llama-4-scout","microsoft/phi-4"]'
      judge_model:
        description: "Model used as LLM judge"
        required: false
        default: "openai/gpt-4o"
  pull_request:
    paths:
      - ".github/workflows/benchmark.yml"
      - "benchmarks/**"

jobs:
  bench:
    name: "Bench: ${{ matrix.model }}"
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      models: read
    strategy:
      fail-fast: false
      matrix:
        model: ${{ fromJson(inputs.models || '["openai/gpt-4o-mini","openai/gpt-4.1-nano"]') }}
    steps:
      - uses: actions/checkout@v6

      - uses: astral-sh/setup-uv@v8.0.0
        with:
          python-version: "3.13"

      - run: uv sync --all-extras

      - name: Run benchmark
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: |
          uv run python benchmarks/bench_model.py \
            --model "${{ matrix.model }}" \
            --fixture benchmarks/fixtures/golden_posts.json \
            --output "results.json"

      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: "benchmark-${{ strategy.job-index }}"
          path: results.json
          retention-days: 7

  report:
    name: "Aggregate & Report"
    needs: bench
    runs-on: ubuntu-latest
    timeout-minutes: 10
    permissions:
      contents: read
      models: read
    steps:
      - uses: actions/checkout@v6

      - uses: astral-sh/setup-uv@v8.0.0
        with:
          python-version: "3.13"

      - run: uv sync --all-extras

      - name: Download all results
        uses: actions/download-artifact@v4
        with:
          path: all-results
          pattern: "benchmark-*"

      - name: Aggregate and generate report
        env:
          GITHUB_TOKEN: ${{ github.token }}
        run: |
          JUDGE="${{ inputs.judge_model || 'openai/gpt-4o' }}"
          uv run python benchmarks/aggregate.py \
            --results-dir all-results \
            --fixture benchmarks/fixtures/golden_posts.json \
            --judge-model "$JUDGE" \
            --output summary.md
          cat summary.md >> "$GITHUB_STEP_SUMMARY"
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/benchmark.yml
git commit -m "ci(benchmark): add LLM benchmark workflow with matrix strategy"
```

---

### Task 7: Add pyyaml dependency and update pythonpath

**Files:**
- Modify: `pyproject.toml`

`bench_model.py` uses `yaml.safe_load` for pricing. It also needs `benchmarks/` on the Python path for test imports.

- [ ] **Step 1: Add pyyaml to dev dependencies and benchmarks to pythonpath**

In `pyproject.toml`, add `"pyyaml"` to `[project.optional-dependencies] dev` list, and add `"benchmarks"` to `pythonpath` in `[tool.pytest.ini_options]`.

Edit `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "ruff",
    "pyyaml",
]
```

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src", "benchmarks/.."]
```

Wait — `benchmarks/` is at the repo root, so we need to make sure `benchmarks` package is importable. Since `pythonpath = ["src"]` already exists and benchmarks is at root level, adding `"."` to pythonpath is the cleanest approach:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src", "."]
```

Also add `pyyaml` to main dependencies since `bench_model.py` uses it (not just dev):

```toml
dependencies = [
    ...existing...,
    "pyyaml",
]
```

Also add `"benchmarks"` to the ruff `src` list:

```toml
[tool.ruff]
src = ["src", "tests", "benchmarks"]
```

- [ ] **Step 2: Run uv sync**

Run: `uv sync --all-extras`

- [ ] **Step 3: Run all tests to verify nothing is broken**

Run: `uv run pytest -v --tb=short`
Expected: All existing tests + new benchmark tests PASS

- [ ] **Step 4: Run linter**

Run: `uv run ruff check src/ tests/ benchmarks/`
Expected: No errors (fix if any)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(benchmark): add pyyaml dependency and update pythonpath"
```

---

### Task 8: Generate golden dataset and commit fixture

**Files:**
- Create: `benchmarks/fixtures/golden_posts.json` (generated)

This task requires a `GITHUB_TOKEN` or `OPENAI_API_KEY` with access to GitHub Models.

- [ ] **Step 1: Run the golden dataset generator**

Run: `GITHUB_TOKEN=<token> uv run python benchmarks/generate_golden.py`

This fetches live Reddit posts and calls GPT-4o to produce reference scores/summaries. Review the output file.

- [ ] **Step 2: Review the generated file**

Open `benchmarks/fixtures/golden_posts.json` and verify:
- Posts are present from all configured subreddits
- Reference scores are reasonable integers (1-10)
- Reference summaries are in French and make sense
- No sensitive data or PII

- [ ] **Step 3: Commit**

```bash
git add benchmarks/fixtures/golden_posts.json
git commit -m "feat(benchmark): add golden dataset fixture"
```

---

### Task 9: Final integration verification

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run linter and formatter**

Run: `uv run ruff check src/ tests/ benchmarks/ && uv run ruff format --check src/ tests/ benchmarks/`
Expected: No issues

- [ ] **Step 3: Verify workflow YAML is valid**

Run: `cat .github/workflows/benchmark.yml | python3 -c "import sys,yaml; yaml.safe_load(sys.stdin.read()); print('Valid YAML')"` (requires pyyaml installed)
Expected: "Valid YAML"

- [ ] **Step 4: Push and create PR**

```bash
git push
```

Create PR with title: `feat(benchmark): add LLM model benchmarking system`
