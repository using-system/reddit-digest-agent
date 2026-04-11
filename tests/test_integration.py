"""End-to-end integration tests: full digest cycle + feedback loop."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from langchain_core.messages import AIMessage

from reddit_digest.db import get_preference_score, is_post_sent
from reddit_digest.graphs.digest import build_digest_graph
from reddit_digest.graphs.feedback import build_feedback_graph


def _make_post_data(id_: str, subreddit: str = "python"):
    return {
        "kind": "t3",
        "data": {
            "id": id_,
            "subreddit": subreddit,
            "title": f"Post {id_}",
            "url": f"https://reddit.com/{id_}",
            "score": 50,
            "num_comments": 10,
            "selftext": f"Content of post {id_}",
            "created_utc": 1700000000.0,
        },
    }


_FAKE_REQUEST = httpx.Request("GET", "https://www.reddit.com/r/test/hot.json")


def _reddit_response(posts):
    return httpx.Response(200, json={"data": {"children": posts}}, request=_FAKE_REQUEST)


def _summary_response():
    data = {"summary": "Résumé test", "category": "tech", "keywords": ["python", "web"]}
    return AIMessage(content=json.dumps(data))


def _feedback_response():
    data = {"topics": ["web", "api"]}
    return AIMessage(content=json.dumps(data))


@pytest.fixture
def mock_all():
    """Mock all external services: Reddit, LLM, Telegram."""
    with (
        patch("reddit_digest.nodes.collector.httpx.AsyncClient") as reddit_cls,
        patch("reddit_digest.nodes.summarizer.ChatOpenAI") as sum_llm_cls,
        patch("reddit_digest.nodes.deliverer.Bot") as bot_cls,
        patch("reddit_digest.nodes.feedback.ChatOpenAI") as fb_llm_cls,
    ):
        # Reddit mock
        client = AsyncMock()
        reddit_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        reddit_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        posts = [_make_post_data("int1"), _make_post_data("int2")]
        client.get = AsyncMock(return_value=_reddit_response(posts))

        # Summarizer LLM mock
        sum_llm = AsyncMock()
        sum_llm.ainvoke = AsyncMock(return_value=_summary_response())
        sum_llm_cls.return_value = sum_llm

        # Telegram bot mock
        bot = AsyncMock()
        msg_ids = iter([100, 101])

        async def fake_send(**kwargs):
            msg = MagicMock()
            msg.message_id = next(msg_ids)
            return msg

        bot.send_message = AsyncMock(side_effect=fake_send)
        bot_cls.return_value = bot

        # Feedback LLM mock
        fb_llm = AsyncMock()
        fb_llm.ainvoke = AsyncMock(return_value=_feedback_response())
        fb_llm_cls.return_value = fb_llm

        yield {
            "client": client,
            "sum_llm": sum_llm,
            "bot": bot,
            "fb_llm": fb_llm,
        }


async def test_full_digest_then_feedback(mock_all, db_conn, settings):
    """Full lifecycle: digest collects and delivers, then feedback updates preferences."""
    digest_graph = build_digest_graph(settings, db_conn)
    result = await digest_graph.ainvoke({"subreddits": ["python"]})

    assert len(result["delivered_ids"]) == 2
    assert await is_post_sent(db_conn, "int1")
    assert await is_post_sent(db_conn, "int2")

    # Simulate "more" reaction on first message
    feedback_graph = build_feedback_graph(settings, db_conn)
    await feedback_graph.ainvoke(
        {
            "message_id": 100,
            "reaction_type": "more",
            "post_metadata": {},
            "preference_update": {},
        }
    )

    assert await get_preference_score(db_conn, "python", "web") == 1
    assert await get_preference_score(db_conn, "python", "api") == 1


async def test_second_digest_skips_already_sent(mock_all, db_conn, settings):
    """Second digest run should skip posts already sent in the first run."""
    digest_graph = build_digest_graph(settings, db_conn)

    # First run
    result1 = await digest_graph.ainvoke({"subreddits": ["python"]})
    assert len(result1["delivered_ids"]) == 2

    # Second run — same posts, should be filtered out
    result2 = await digest_graph.ainvoke({"subreddits": ["python"]})
    assert len(result2["filtered_posts"]) == 0
    assert len(result2["delivered_ids"]) == 0


async def test_negative_preferences_filter_posts(mock_all, db_conn, settings):
    """Posts from subreddits with very negative scores should be filtered out."""
    from reddit_digest.db import update_preference

    await update_preference(db_conn, "python", "general", -5)

    digest_graph = build_digest_graph(settings, db_conn)
    result = await digest_graph.ainvoke({"subreddits": ["python"]})

    assert len(result["filtered_posts"]) == 0
    assert len(result["delivered_ids"]) == 0
