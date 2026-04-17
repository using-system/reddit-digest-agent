# LLM Benchmark

Automated benchmark system to compare LLM models for the reddit-digest-agent pipeline. Tests each model's ability to score and summarize Reddit posts using the project's real prompts.

## Latest Results (2026-04-17)

> Run: [GitHub Actions #24556347098](https://github.com/using-system/reddit-digest-agent/actions/runs/24556347098)
> 25 models tested across 7 providers via OpenRouter
> Judge: openai/gpt-4o

### Ranking

| Model | Cost | JSON OK | Latency (avg) | Summaries | Scoring MAE | **Composite** |
|-------|------|---------|---------------|-----------|-------------|---------------|
| openai/gpt-5.4-nano | $0.0026 | 100% | 1519ms | 7.1/10 | 1.2 | **0.9734** |
| openai/gpt-4o-mini | $0.0016 | 100% | 2207ms | 7.1/10 | 1.3 | **0.9715** |
| x-ai/grok-4-fast | $0.0041 | 100% | 3586ms | 7.6/10 | 1.4 | **0.9684** |
| google/gemma-4-31b-it | $0.0016 | 100% | 4869ms | 7.2/10 | 0.9 | **0.9649** |
| google/gemma-3-27b-it | $0.0012 | 100% | 4790ms | 7.2/10 | 1.2 | **0.9632** |
| google/gemma-3-12b-it | $0.0009 | 100% | 3980ms | 7.1/10 | 1.5 | **0.9627** |
| google/gemma-3-4b-it | $0.0004 | 100% | 1958ms | 6.4/10 | 1.2 | **0.9597** |
| meta-llama/llama-4-maverick | $0.0027 | 100% | 3784ms | 7.0/10 | 1.3 | **0.9569** |
| mistralai/mistral-medium-3.1 | $0.0066 | 100% | 4272ms | 7.6/10 | 1.9 | **0.9516** |
| openai/gpt-4.1-mini | $0.0042 | 100% | 4014ms | 7.1/10 | 1.7 | **0.949** |
| meta-llama/llama-4-scout | $0.0017 | 100% | 5388ms | 6.7/10 | 1.1 | **0.9457** |
| mistralai/mistral-small-3.1-24b-instruct | $0.0037 | 100% | 5398ms | 7.0/10 | 1.3 | **0.9456** |
| anthropic/claude-haiku-4.5 | $0.0156 | 100% | 2846ms | 7.2/10 | 0.6 | **0.9327** |
| openai/gpt-5.4 | $0.0179 | 100% | 2870ms | 7.3/10 | 1.1 | **0.9224** |
| deepseek/deepseek-v3.2 | $0.0047 | 100% | 11709ms | 7.5/10 | 1.3 | **0.9207** |
| openai/gpt-4.1 | $0.0189 | 100% | 2571ms | 7.1/10 | 1.1 | **0.9148** |
| openai/gpt-4o | $0.0252 | 100% | 1886ms | 7.1/10 | 0.6 | **0.9037** |
| deepseek/deepseek-chat-v3-0324 | $0.0027 | 100% | 18976ms | 7.4/10 | 1.3 | **0.8865** |
| openai/gpt-oss-20b | $0.0013 | 100% | 20130ms | 7.1/10 | 1.2 | **0.8776** |
| x-ai/grok-3-mini | $0.0041 | 100% | 18508ms | 6.9/10 | 1.4 | **0.8697** |
| microsoft/phi-4 | $0.0009 | 67% | 6152ms | 7.0/10 | 10.0 | **0.7578** |
| openai/gpt-oss-120b | $0.0029 | 100% | 16742ms | 0.0/10 | 0.6 | **0.7103** |
| anthropic/claude-opus-4.6 | $0.0779 | 100% | 7131ms | 7.3/10 | 0.6 | **0.7075** |
| anthropic/claude-opus-4.7 | $0.1070 | 100% | 4497ms | 7.5/10 | 0.7 | **0.6306** |
| openai/gpt-4.1-nano | $0.0010 | 17% | 1619ms | 0.0/10 | 1.0 | **0.5434** |

### Recommandation

**Meilleur qualité/prix self-hostable : `google/gemma-3-12b-it`** — composite 0.9627 à $0.0009 par run, 100 % de JSON valide, latence ~4 s, qualité de résumé 7.1/10. Quasi à égalité avec les meilleurs modèles propriétaires tout en restant exécutable sur du matériel grand public.

### Key takeaways

- **Best overall**: `openai/gpt-5.4-nano` — premier composite (0.9734), 100 % JSON, latence la plus basse (~1.5 s)
- **Best self-hostable**: `google/gemma-3-12b-it` — meilleur compromis hostable : coût le plus bas de la famille hostable utile, latence raisonnable, qualité comparable aux variantes 27B / 31B sans le besoin de GPU haut de gamme
- **Famille Gemma**: 4B / 12B / 27B / 4-31B sont toutes en haut du classement ; le 12B reste le sweet spot entre coût, latence et qualité
- **Coût vs qualité**: les modèles à >$0.01 par run (Claude Opus 4.6/4.7, GPT-4o, GPT-4.1, GPT-5.4) n'apportent pas un gain qui justifie le prix — `claude-opus-4.7` est même le plus cher du panel ($0.107) sans dépasser les modèles légers
- **Anomalies à surveiller**: `openai/gpt-oss-120b` (résumé évalué 0.0/10 par le judge malgré 100 % JSON), `openai/gpt-4.1-nano` (17 % JSON seulement), `microsoft/phi-4` (67 % JSON, MAE de scoring à 10.0)

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
