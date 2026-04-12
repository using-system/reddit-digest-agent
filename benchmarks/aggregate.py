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

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"


def _strip_code_fences(text: str) -> str:
    """Strip markdown code fences and whitespace from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        first_newline = text.index("\n") if "\n" in text else len(text)
        text = text[first_newline + 1 :]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


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
    base_url = os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)

    llm = ChatOpenAI(
        base_url=base_url,
        model=judge_model,
        api_key=api_key,
    )

    posts = fixture["posts"]
    model_names = [r["model"] for r in results]
    model_summaries = {
        r["model"]: r["raw_outputs"].get("summaries", {}) for r in results
    }

    # Build per-post evaluation blocks, batch by ~5 posts
    all_evaluations: dict[str, dict[str, dict[str, int]]] = {}
    batch_size = 5

    for batch_start in range(0, len(posts), batch_size):
        batch_posts = posts[batch_start : batch_start + batch_size]

        posts_block_parts = []
        for post in batch_posts:
            pid = post["reddit_id"] if isinstance(post, dict) else post.reddit_id
            title = post["title"] if isinstance(post, dict) else post.title
            selftext = (
                post.get("selftext", "") if isinstance(post, dict) else post.selftext
            )

            lines = [f'Post "{pid}" - "{title}"']
            lines.append(f'Original content: "{selftext[:500]}"')
            for model_name in model_names:
                summary = model_summaries[model_name].get(pid, "(no summary)")
                safe_name = model_name.replace("/", "_")
                lines.append(f'- {safe_name}: "{summary}"')
            posts_block_parts.append("\n".join(lines))

        posts_block = "\n\n".join(posts_block_parts)

        # Build schema hint
        post_ids = [
            p["reddit_id"] if isinstance(p, dict) else p.reddit_id for p in batch_posts
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
            data = json.loads(_strip_code_fences(response.content))
            evals = data.get("evaluations", {})
            all_evaluations.update(evals)
        except Exception:
            logger.exception("Judge failed for batch starting at %d", batch_start)

    # Aggregate per model
    model_scores: dict[str, dict[str, list]] = {
        m.replace("/", "_"): {"fidelity": [], "clarity": [], "concision": []}
        for m in model_names
    }

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
        fidelity_list = scores.get("fidelity", [])
        clarity_list = scores.get("clarity", [])
        concision_list = scores.get("concision", [])
        avg_fidelity = sum(fidelity_list) / len(fidelity_list) if fidelity_list else 0.0
        avg_clarity = sum(clarity_list) / len(clarity_list) if clarity_list else 0.0
        avg_concision = (
            sum(concision_list) / len(concision_list) if concision_list else 0.0
        )
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
        ranked.append(
            {
                "model": r["model"],
                "metrics": r["metrics"],
                "judge": judge_scores.get(r["model"], {}),
                "composite": round(composite, 4),
                "raw_outputs": r.get("raw_outputs", {}),
                "errors": r.get("errors", []),
            }
        )

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
        lines.append("### Summaries")
        lines.append("| Post | Summary | Fidelity | Clarity | Concision |")
        lines.append("|------|---------|----------|---------|-----------|")
        model_summaries = r.get("raw_outputs", {}).get("summaries", {})
        for post in fixture.get("posts", []):
            pid = post["reddit_id"] if isinstance(post, dict) else post.reddit_id
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
    parser.add_argument(
        "--results-dir", required=True, help="Directory with result artifacts"
    )
    parser.add_argument(
        "--fixture",
        default="benchmarks/fixtures/golden_posts.json",
        help="Path to golden dataset",
    )
    parser.add_argument(
        "--judge-model", default=DEFAULT_JUDGE_MODEL, help="Judge model"
    )
    parser.add_argument("--output", default="summary.md", help="Output markdown path")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: set OPENAI_API_KEY env var", file=sys.stderr)
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
