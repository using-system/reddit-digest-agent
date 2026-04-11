import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.graphs.digest import build_digest_graph


def _make_post_data(id_: str):
    return {
        "kind": "t3",
        "data": {
            "id": id_,
            "title": f"Post {id_}",
            "url": f"https://reddit.com/{id_}",
            "score": 10,
            "num_comments": 2,
            "selftext": "content",
            "created_utc": 1700000000.0,
        },
    }


def _reddit_response(posts):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": {"children": posts}}
    resp.raise_for_status = MagicMock()
    return resp


@pytest.fixture
def mock_reddit():
    with patch("reddit_digest.nodes.collector.cffi_requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        yield session


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
    posts = [_make_post_data("g1")]
    mock_reddit.get.side_effect = [_reddit_response([]), _reddit_response(posts)]

    graph = build_digest_graph(settings, db_conn)
    result = await graph.ainvoke({"subreddits": ["python"]})

    assert len(result["raw_posts"]) == 1
    assert len(result["filtered_posts"]) == 1
    assert len(result["summaries"]) == 1
    assert result["delivered_ids"] == ["42"]


async def test_digest_graph_empty_subreddit(
    mock_reddit, mock_llm, mock_bot, db_conn, settings
):
    mock_reddit.get.side_effect = [_reddit_response([]), _reddit_response([])]

    graph = build_digest_graph(settings, db_conn)
    result = await graph.ainvoke({"subreddits": ["empty"]})

    assert result["raw_posts"] == []
    assert result["summaries"] == []
    assert result["delivered_ids"] == []
