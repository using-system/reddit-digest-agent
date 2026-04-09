import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.models import RedditPost
from reddit_digest.nodes.summarizer import summarize_posts


def _post(reddit_id: str = "p1") -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit="python",
        title="Test Post",
        url="https://reddit.com/p1",
        selftext="Some content about Python",
    )


def _llm_response(
    summary: str = "Résumé du post",
    category: str = "tech",
    keywords: list[str] | None = None,
):
    data = {
        "summary": summary,
        "category": category,
        "keywords": keywords or ["python", "test"],
    }
    return AIMessage(content=json.dumps(data))


@pytest.fixture
def mock_llm():
    with patch("reddit_digest.nodes.summarizer.ChatOpenAI") as mock_cls:
        instance = AsyncMock()
        instance.ainvoke = AsyncMock(return_value=_llm_response())
        mock_cls.return_value = instance
        yield instance


async def test_summarize_posts_basic(mock_llm, sample_config, sample_secrets):
    state = {"filtered_posts": [_post()]}
    result = await summarize_posts(state, sample_config, sample_secrets)
    assert len(result["summaries"]) == 1
    assert result["summaries"][0].summary_text == "Résumé du post"
    assert result["summaries"][0].category == "tech"
    assert result["summaries"][0].reddit_id == "p1"


async def test_summarize_posts_empty(mock_llm, sample_config, sample_secrets):
    state = {"filtered_posts": []}
    result = await summarize_posts(state, sample_config, sample_secrets)
    assert result["summaries"] == []
    mock_llm.ainvoke.assert_not_called()


async def test_summarize_posts_llm_error_graceful(
    mock_llm, sample_config, sample_secrets
):
    mock_llm.ainvoke = AsyncMock(side_effect=[_llm_response(), Exception("LLM error")])
    state = {"filtered_posts": [_post("p1"), _post("p2")]}
    result = await summarize_posts(state, sample_config, sample_secrets)
    assert len(result["summaries"]) == 1
    assert result["summaries"][0].reddit_id == "p1"


async def test_summarize_posts_uses_configured_language(
    mock_llm, sample_config, sample_secrets
):
    sample_config.digest.language = "en"
    state = {"filtered_posts": [_post()]}
    await summarize_posts(state, sample_config, sample_secrets)
    call_args = mock_llm.ainvoke.call_args[0][0]
    assert "en" in call_args
