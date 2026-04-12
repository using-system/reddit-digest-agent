import pytest

from benchmarks.bench_model import compute_cost
from benchmarks.aggregate import normalize_min_max, compute_composite, generate_report


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
        "cheap-model": {
            "fidelity": 7.0,
            "clarity": 7.0,
            "concision": 7.0,
            "average": 7.0,
        },
        "expensive-model": {
            "fidelity": 9.0,
            "clarity": 9.0,
            "concision": 9.0,
            "average": 9.0,
        },
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
            "judge": {
                "fidelity": 8.0,
                "clarity": 8.0,
                "concision": 8.0,
                "average": 8.0,
            },
            "composite": 0.92,
            "raw_outputs": {"scores": {"p1": 8}, "summaries": {"p1": "Un résumé"}},
            "errors": [],
        },
    ]
    fixture = {
        "posts": [{"reddit_id": "p1", "title": "Test", "selftext": "Content"}],
        "reference_outputs": {"scores": {"p1": 8}},
    }

    report = generate_report(ranked, fixture)
    assert "## Recommendation: best-model" in report
    assert "| best-model" in report
    assert "<details>" in report


def test_generate_report_empty():
    report = generate_report([], {})
    assert "No results" in report
