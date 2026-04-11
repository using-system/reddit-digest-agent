import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.models import RedditPost
from reddit_digest.nodes.scorer import score_posts

SCORE_PROMPT_MODULE = "reddit_digest.nodes.scorer.ChatOpenAI"


def _post(
    reddit_id: str = "p1",
    subreddit: str = "python",
    title: str = "Test Post",
    score: int = 50,
) -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit=subreddit,
        title=title,
        url=f"https://reddit.com/{reddit_id}",
        score=score,
        num_comments=10,
        selftext="Content here",
        top_comments=["Great post", "I agree"],
    )


def _llm_scores_response(scores: dict[str, int]):
    data = {"scores": scores}
    return AIMessage(content=json.dumps(data))


@pytest.fixture
def mock_llm():
    with patch(SCORE_PROMPT_MODULE) as mock_cls:
        instance = AsyncMock()
        mock_cls.return_value = instance
        yield instance


async def test_score_posts_filters_low_relevance(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(
        return_value=_llm_scores_response({"p1": 8, "p2": 4, "p3": 7})
    )

    posts = [_post("p1"), _post("p2"), _post("p3")]
    state = {"filtered_posts": posts}
    result = await score_posts(state, settings)

    scored = result["scored_posts"]
    ids = [p.reddit_id for p in scored]
    assert "p1" in ids
    assert "p3" in ids
    assert "p2" not in ids


async def test_score_posts_empty_input(mock_llm, settings):
    state = {"filtered_posts": []}
    result = await score_posts(state, settings)
    assert result["scored_posts"] == []
    mock_llm.ainvoke.assert_not_called()


async def test_score_posts_multiple_subreddits(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(
        side_effect=[
            _llm_scores_response({"p1": 9}),
            _llm_scores_response({"p2": 3}),
        ]
    )

    posts = [_post("p1", subreddit="python"), _post("p2", subreddit="rust")]
    state = {"filtered_posts": posts}
    result = await score_posts(state, settings)

    assert len(result["scored_posts"]) == 1
    assert result["scored_posts"][0].reddit_id == "p1"


async def test_score_posts_llm_error_keeps_all(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM down"))

    posts = [_post("p1")]
    state = {"filtered_posts": posts}
    result = await score_posts(state, settings)

    assert len(result["scored_posts"]) == 1


async def test_score_posts_sets_relevance_score(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(
        return_value=_llm_scores_response({"p1": 9})
    )

    state = {"filtered_posts": [_post("p1")]}
    result = await score_posts(state, settings)

    assert result["scored_posts"][0].relevance_score == 9
