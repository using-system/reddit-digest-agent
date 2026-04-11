import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.db import get_preference_score, save_sent_post
from reddit_digest.graphs.feedback import build_feedback_graph
from reddit_digest.models import RedditPost


def _post() -> RedditPost:
    return RedditPost(
        reddit_id="fg1",
        subreddit="python",
        title="Feedback Graph Test",
        url="https://reddit.com/fg1",
    )


@pytest.fixture
def mock_llm():
    with patch("reddit_digest.nodes.feedback.ChatOpenAI") as mock_cls:
        instance = AsyncMock()
        data = {"topics": ["web", "api"]}
        instance.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(data)))
        mock_cls.return_value = instance
        yield instance


async def test_feedback_graph_more(mock_llm, db_conn, settings):
    await save_sent_post(
        db_conn, _post(), telegram_message_id=600, category="tech", keywords=["python"]
    )

    graph = build_feedback_graph(settings, db_conn)
    await graph.ainvoke(
        {
            "message_id": 600,
            "reaction_type": "more",
            "post_metadata": {},
            "preference_update": {},
        }
    )

    assert await get_preference_score(db_conn, "python", "web") == 1
    assert await get_preference_score(db_conn, "python", "api") == 1


async def test_feedback_graph_irrelevant(mock_llm, db_conn, settings):
    await save_sent_post(
        db_conn, _post(), telegram_message_id=601, category="tech", keywords=["python"]
    )

    graph = build_feedback_graph(settings, db_conn)
    await graph.ainvoke(
        {
            "message_id": 601,
            "reaction_type": "irrelevant",
            "post_metadata": {},
            "preference_update": {},
        }
    )

    assert await get_preference_score(db_conn, "python", "web") == -2
    assert await get_preference_score(db_conn, "python", "api") == -2


async def test_feedback_graph_less(mock_llm, db_conn, settings):
    await save_sent_post(
        db_conn, _post(), telegram_message_id=602, category="tech", keywords=["python"]
    )

    graph = build_feedback_graph(settings, db_conn)
    await graph.ainvoke(
        {
            "message_id": 602,
            "reaction_type": "less",
            "post_metadata": {},
            "preference_update": {},
        }
    )

    assert await get_preference_score(db_conn, "python", "web") == -1
