import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.models import RedditPost
from reddit_digest.nodes.summarizer import summarize_posts


def _post(reddit_id: str = "p1", subreddit: str = "python") -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit=subreddit,
        title="Test Post",
        url=f"https://reddit.com/{reddit_id}",
        selftext="Some content about Python",
        top_comments=["Great stuff", "Interesting read"],
    )


def _llm_response(summaries: dict[str, str]):
    data = {"summaries": summaries}
    return AIMessage(content=json.dumps(data))


@pytest.fixture
def mock_llm():
    with patch("reddit_digest.nodes.summarizer.ChatOpenAI") as mock_cls:
        instance = AsyncMock()
        mock_cls.return_value = instance
        yield instance


async def test_summarize_posts_batch(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(
        return_value=_llm_response(
            {"p1": "Résumé du post p1", "p2": "Résumé du post p2"}
        )
    )
    state = {"scored_posts": [_post("p1"), _post("p2")]}
    result = await summarize_posts(state, settings)

    assert len(result["summaries"]) == 2
    assert result["summaries"][0].summary_text == "Résumé du post p1"
    assert result["summaries"][1].summary_text == "Résumé du post p2"
    assert mock_llm.ainvoke.call_count == 1


async def test_summarize_posts_empty(mock_llm, settings):
    state = {"scored_posts": []}
    result = await summarize_posts(state, settings)
    assert result["summaries"] == []
    mock_llm.ainvoke.assert_not_called()


async def test_summarize_posts_multiple_subreddits(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(
        side_effect=[
            _llm_response({"p1": "Python summary"}),
            _llm_response({"p2": "Rust summary"}),
        ]
    )
    state = {"scored_posts": [_post("p1", "python"), _post("p2", "rust")]}
    result = await summarize_posts(state, settings)

    assert len(result["summaries"]) == 2
    assert mock_llm.ainvoke.call_count == 2


async def test_summarize_posts_llm_error_graceful(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM error"))
    state = {"scored_posts": [_post("p1")]}
    result = await summarize_posts(state, settings)
    assert result["summaries"] == []


async def test_summarize_posts_uses_configured_language(mock_llm, settings):
    settings.digest_language = "en"
    mock_llm.ainvoke = AsyncMock(return_value=_llm_response({"p1": "English summary"}))
    state = {"scored_posts": [_post()]}
    await summarize_posts(state, settings)
    call_args = mock_llm.ainvoke.call_args[0][0]
    assert "en" in call_args
