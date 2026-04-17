# LLM Benchmark

Automated benchmark system to compare LLM models for the reddit-digest-agent pipeline. Tests each model's ability to score and summarize Reddit posts using the project's real prompts.

## Latest Results (2026-04-17)

> Run: [GitHub Actions #24556985945](https://github.com/using-system/reddit-digest-agent/actions/runs/24556985945)
> 25 models tested across 7 providers via OpenRouter
> Judge: openai/gpt-4o

### Ranking

| Model | Cost | JSON OK | Latency (avg) | Summaries | Scoring MAE | **Composite** |
|-------|------|---------|---------------|-----------|-------------|---------------|
| google/gemma-3-27b-it | $0.0012 | 100% | 3336ms | 7.9/10 | 1.1 | **0.9819** |
| google/gemma-3-12b-it | $0.0005 | 100% | 4296ms | 7.9/10 | 1.4 | **0.9781** |
| openai/gpt-4o-mini | $0.0015 | 100% | 2156ms | 7.6/10 | 0.9 | **0.9746** |
| google/gemma-4-31b-it | $0.0016 | 100% | 8232ms | 8.0/10 | 1.0 | **0.9693** |
| x-ai/grok-4-fast | $0.0042 | 100% | 3791ms | 7.9/10 | 1.5 | **0.966** |
| meta-llama/llama-4-maverick | $0.0033 | 100% | 3196ms | 7.7/10 | 1.2 | **0.9657** |
| openai/gpt-4.1-mini | $0.0045 | 100% | 3130ms | 7.8/10 | 1.5 | **0.9636** |
| openai/gpt-5.4-nano | $0.0026 | 100% | 1951ms | 7.4/10 | 1.1 | **0.9606** |
| mistralai/mistral-medium-3.1 | $0.0064 | 100% | 4736ms | 8.0/10 | 1.5 | **0.96** |
| mistralai/mistral-small-3.1-24b-instruct | $0.0037 | 100% | 5644ms | 7.6/10 | 1.3 | **0.9506** |
| meta-llama/llama-4-scout | $0.0022 | 100% | 7142ms | 7.6/10 | 1.3 | **0.9505** |
| deepseek/deepseek-chat-v3-0324 | $0.0029 | 100% | 13163ms | 7.9/10 | 1.0 | **0.9432** |
| anthropic/claude-haiku-4.5 | $0.0156 | 100% | 2846ms | 7.7/10 | 1.0 | **0.9271** |
| openai/gpt-4.1 | $0.0192 | 100% | 2684ms | 7.8/10 | 1.1 | **0.9185** |
| openai/gpt-5.4 | $0.0181 | 100% | 3066ms | 7.2/10 | 1.1 | **0.8947** |
| openai/gpt-oss-120b | $0.0029 | 100% | 29202ms | 7.7/10 | 0.9 | **0.8794** |
| google/gemma-3-4b-it | $0.0004 | 100% | 2302ms | 3.5/10 | 1.2 | **0.7919** |
| microsoft/phi-4 | $0.0009 | 67% | 7588ms | 7.8/10 | 10.0 | **0.7686** |
| deepseek/deepseek-v3.2 | $0.0027 | 100% | 12455ms | 3.8/10 | 1.3 | **0.7612** |
| openai/gpt-4o | $0.0245 | 100% | 2358ms | 3.8/10 | 1.0 | **0.7252** |
| anthropic/claude-opus-4.6 | $0.0778 | 100% | 5298ms | 7.5/10 | 0.7 | **0.7014** |
| x-ai/grok-3-mini | $0.0057 | 100% | 30198ms | 3.7/10 | 1.5 | **0.6821** |
| openai/gpt-oss-20b | $0.0013 | 67% | 10371ms | 3.8/10 | 0.7 | **0.6795** |
| anthropic/claude-opus-4.7 | $0.1031 | 100% | 4006ms | 7.7/10 | 0.7 | **0.6283** |
| openai/gpt-4.1-nano | $0.0011 | 17% | 1614ms | 3.8/10 | 10.0 | **0.4611** |

### Recommendation

**Best quality/price self-hostable: `google/gemma-3-12b-it`** — composite 0.9781 at $0.0005 per run, 100% valid JSON, ~4.3s latency, 7.9/10 summary quality. Second overall in the ranking, trailing only its bigger sibling `gemma-3-27b-it` while costing less than half and running on consumer hardware.

### Key takeaways

- **Best overall**: `google/gemma-3-27b-it` — top composite (0.9819), 100% JSON, 7.9/10 summary, fast at ~3.3s and only $0.0012 per run
- **Best self-hostable**: `google/gemma-3-12b-it` — same summary quality as the 27B (7.9/10), half the cost ($0.0005 vs $0.0012), runs on a single consumer GPU
- **Gemma family dominates**: three Gemma 3 variants and the Gemma 4-31B fill 4 of the top 5 spots, beating every proprietary model except `gpt-4o-mini`
- **Cost vs quality**: models above $0.01 per run (Claude Opus 4.6/4.7, GPT-4o, GPT-4.1, GPT-5.4) deliver no benefit over Gemma 3-12B; `claude-opus-4.7` is the most expensive of the panel ($0.103) and still ranks last on composite
- **Anomalies to watch**: judge gave a 3.5–3.8/10 summary score to `gemma-3-4b-it`, `deepseek-v3.2`, `gpt-4o`, `grok-3-mini`, `gpt-oss-20b` and `gpt-4.1-nano` despite valid JSON — likely judge variance worth re-running. Hard failures: `gpt-4.1-nano` (17% JSON), `microsoft/phi-4` and `gpt-oss-20b` (67% JSON)

### Composite score formula

Weighted by priority: cost (35%) > JSON reliability (25%) > latency (10%) > summary quality (20%) > scoring accuracy (10%).

Each metric is min-max normalized across all models. For cost, latency, and MAE, lower is better (inverse normalization).

## How to run

### From GitHub Actions (recommended)

Go to **Actions > LLM Benchmark > Run workflow**. The default runs all 25 models. You can pass a custom JSON array of model IDs.

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
