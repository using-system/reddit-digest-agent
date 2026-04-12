# LLM Benchmark

Automated benchmark system to compare LLM models for the reddit-digest-agent pipeline. Tests each model's ability to score and summarize Reddit posts using the project's real prompts.

## Latest Results (2026-04-12)

> Run: [GitHub Actions #24308576896](https://github.com/using-system/reddit-digest-agent/actions/runs/24308576896)
> 20 models tested across 7 providers via OpenRouter
> Judge: openai/gpt-4o

### Ranking

| Model | Cost | JSON OK | Latency (avg) | Summaries | Scoring MAE | **Composite** |
|-------|------|---------|---------------|-----------|-------------|---------------|
| openai/gpt-4o-mini | $0.0014 | 100% | 1818ms | 7.8/10 | 1.1 | **0.9813** |
| google/gemma-3-12b-it | $0.0005 | 100% | 4206ms | 8.1/10 | 1.4 | **0.9793** |
| google/gemma-3-27b-it | $0.0012 | 100% | 5178ms | 8.0/10 | 1.3 | **0.9679** |
| openai/gpt-4.1-mini | $0.0044 | 100% | 1852ms | 7.7/10 | 1.6 | **0.9638** |
| mistralai/mistral-medium-3.1 | $0.0064 | 100% | 4052ms | 7.6/10 | 1.5 | **0.9391** |
| mistralai/mistral-small-3.1-24b-instruct | $0.0037 | 100% | 5478ms | 7.4/10 | 1.3 | **0.938** |
| anthropic/claude-haiku-4.5 | $0.0153 | 100% | 2788ms | 7.6/10 | 0.6 | **0.9078** |
| openai/gpt-4.1 | $0.0183 | 100% | 2128ms | 7.9/10 | 1.1 | **0.9054** |
| google/gemma-4-31b-it | $0.0016 | 100% | 18314ms | 7.9/10 | 0.9 | **0.8882** |
| x-ai/grok-3-mini | $0.0048 | 100% | 15890ms | 7.5/10 | 1.3 | **0.8759** |
| deepseek/deepseek-chat-v3-0324 | $0.0030 | 83% | 10821ms | 7.3/10 | 0.8 | **0.8588** |
| deepseek/deepseek-v3.2 | $0.0046 | 100% | 6031ms | 7.3/10 | 45.6 | **0.8297** |
| google/gemma-3-4b-it | $0.0005 | 100% | 4327ms | 1.0/10 | 1.2 | **0.7794** |
| x-ai/grok-4-fast | $0.0043 | 100% | 4731ms | 1.0/10 | 0.7 | **0.7607** |
| meta-llama/llama-4-maverick | $0.0041 | 50% | 8480ms | 7.5/10 | 10.0 | **0.7526** |
| microsoft/phi-4 | $0.0009 | 33% | 4598ms | 7.9/10 | 10.0 | **0.7505** |
| openai/gpt-4o | $0.0253 | 100% | 1424ms | 1.0/10 | 0.7 | **0.6844** |
| anthropic/claude-opus-4.6 | $0.0775 | 100% | 5674ms | 7.7/10 | 0.7 | **0.6115** |
| openai/gpt-4.1-nano | $0.0009 | 33% | 986ms | 1.0/10 | 10.0 | **0.577** |
| meta-llama/llama-4-scout | $0.0019 | 17% | 5013ms | 1.0/10 | 10.0 | **0.4991** |

### Key takeaways

- **Best overall**: `openai/gpt-4o-mini` — cheapest top-tier option with 100% JSON reliability and good summary quality
- **Best self-hostable**: `google/gemma-3-12b-it` — nearly identical composite score (0.9793 vs 0.9813), highest summary quality (8.1/10), lowest cost ($0.0005), and can run on consumer hardware
- **Gemma 3 family**: The 12B variant hits the sweet spot. The 27B is marginally worse and slower, the 4B drops dramatically in summary quality
- **Cost vs quality**: Models costing >$0.01 per run (Claude Opus, GPT-4o, GPT-4.1) don't justify the price — cheaper models match or beat them on summary quality
- **JSON reliability**: Most models achieve 100%. Notable failures: Llama 4 Scout (17%), Phi-4 (33%), GPT-4.1-nano (33%)

### Composite score formula

Weighted by priority: cost (35%) > JSON reliability (25%) > latency (10%) > summary quality (20%) > scoring accuracy (10%).

Each metric is min-max normalized across all models. For cost, latency, and MAE, lower is better (inverse normalization).

## How to run

### From GitHub Actions (recommended)

Go to **Actions > LLM Benchmark > Run workflow**. The default runs all 20 models. You can pass a custom JSON array of model IDs.

### Locally

```bash
# Generate golden dataset (one-time, needs Reddit access + LLM API)
uv run python benchmarks/generate_golden.py

# Benchmark a single model
OPENAI_API_KEY=... uv run python benchmarks/bench_model.py \
  --model google/gemma-3-12b-it \
  --fixture benchmarks/fixtures/golden_posts.json \
  --output results.json

# Aggregate multiple results
uv run python benchmarks/aggregate.py \
  --results-dir ./results/ \
  --fixture benchmarks/fixtures/golden_posts.json \
  --output summary.md
```

## Architecture

```
workflow_dispatch / PR on benchmarks/**
        |
        v
  [bench job x N] ──parallel (max 5)──> results.json artifacts
        |
        v
  [report job] ──> LLM judge + composite score + Markdown report
        |
        v
  $GITHUB_STEP_SUMMARY
```

## Files

| File | Description |
|------|-------------|
| `bench_model.py` | Benchmark one model: runs scorer + summarizer, measures latency/cost/JSON validity |
| `aggregate.py` | Aggregates results, runs LLM-as-Judge for summary quality, generates report |
| `generate_golden.py` | Bootstraps golden dataset from live Reddit + reference model |
| `fixtures/golden_posts.json` | 15 posts with reference scores and summaries |
