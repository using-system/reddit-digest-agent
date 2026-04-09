import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.graphs.digest import build_digest_graph


def _make_submission(id_: str):
    sub = MagicMock()
    sub.id = id_
    sub.title = f"Post {id_}"
    sub.url = f"https://reddit.com/{id_}"
    sub.score = 10
    sub.num_comments = 2
    sub.selftext = "content"
    sub.created_utc = 1700000000.0
    return sub


@pytest.fixture
def mock_reddit():
    with patch("reddit_digest.nodes.collector.asyncpraw.Reddit") as mock_cls:
        instance = AsyncMock()
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def mock_llm():
    with patch("reddit_digest.nodes.summarizer.ChatOpenAI") as mock_cls:
        instance = AsyncMock()
        data = {"summary": "Test summary", "category": "tech", "keywords": ["test"]}
        instance.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(data)))
        mock_cls.return_value = instance
        yield instance


@pytest.fixture
def mock_bot():
    with patch("reddit_digest.nodes.deliverer.Bot") as mock_cls:
        instance = AsyncMock()
        fake_msg = MagicMock()
        fake_msg.message_id = 42
        instance.send_message = AsyncMock(return_value=fake_msg)
        mock_cls.return_value = instance
        yield instance


async def test_digest_graph_full_flow(
    mock_reddit, mock_llm, mock_bot, db_conn, settings
):
    submissions = [_make_submission("g1")]
    sub_obj = AsyncMock()

    async def fake_hot(**kwargs):
        for s in submissions:
            yield s

    sub_obj.hot = fake_hot
    mock_reddit.subreddit = AsyncMock(return_value=sub_obj)

    graph = build_digest_graph(settings, db_conn)
    result = await graph.ainvoke({"subreddits": ["python"]})

    assert len(result["raw_posts"]) == 1
    assert len(result["filtered_posts"]) == 1
    assert len(result["summaries"]) == 1
    assert result["delivered_ids"] == ["42"]


async def test_digest_graph_empty_subreddit(
    mock_reddit, mock_llm, mock_bot, db_conn, settings
):
    sub_obj = AsyncMock()

    async def fake_hot(**kwargs):
        return
        yield  # make it an async generator

    sub_obj.hot = fake_hot
    mock_reddit.subreddit = AsyncMock(return_value=sub_obj)

    graph = build_digest_graph(settings, db_conn)
    result = await graph.ainvoke({"subreddits": ["empty"]})

    assert result["raw_posts"] == []
    assert result["summaries"] == []
    assert result["delivered_ids"] == []
