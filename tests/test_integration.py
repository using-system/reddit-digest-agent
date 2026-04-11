"""End-to-end integration tests: full digest cycle + feedback loop."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.db import get_preference_score, is_post_seen
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


def _reddit_response(posts):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": {"children": posts}}
    resp.raise_for_status = MagicMock()
    return resp


def _comments_response():
    resp = MagicMock()
    resp.json.return_value = [
        {"data": {"children": []}},
        {
            "data": {
                "children": [{"kind": "t1", "data": {"body": "Nice post", "score": 5}}]
            }
        },
    ]
    resp.raise_for_status = MagicMock()
    return resp


def _scores_response(ids: list[str], score: int = 9):
    data = {"scores": {id_: score for id_ in ids}}
    return AIMessage(content=json.dumps(data))


def _summaries_response(ids: list[str]):
    data = {"summaries": {id_: f"Summary of {id_}" for id_ in ids}}
    return AIMessage(content=json.dumps(data))


def _feedback_response():
    data = {"topics": ["web", "api"]}
    return AIMessage(content=json.dumps(data))


@pytest.fixture
def mock_all():
    """Mock all external services: Reddit, LLM (scorer + summarizer + feedback), Telegram."""
    with (
        patch("reddit_digest.nodes.collector.cffi_requests.Session") as reddit_cls,
        patch("reddit_digest.nodes.scorer.ChatOpenAI") as scorer_llm_cls,
        patch("reddit_digest.nodes.summarizer.ChatOpenAI") as sum_llm_cls,
        patch("reddit_digest.nodes.deliverer.Bot") as bot_cls,
        patch("reddit_digest.nodes.feedback.ChatOpenAI") as fb_llm_cls,
    ):
        # Reddit mock
        session = MagicMock()
        reddit_cls.return_value = session
        posts = [_make_post_data("int1"), _make_post_data("int2")]
        homepage_resp = _reddit_response([])
        listing_resp = _reddit_response(posts)
        comments_resp = _comments_response()
        # Homepage + listing + comments for each post
        session.get.side_effect = [
            homepage_resp,
            listing_resp,
            comments_resp,
            comments_resp,
        ]

        # Scorer LLM mock
        scorer_llm = AsyncMock()
        scorer_llm.ainvoke = AsyncMock(return_value=_scores_response(["int1", "int2"]))
        scorer_llm_cls.return_value = scorer_llm

        # Summarizer LLM mock
        sum_llm = AsyncMock()
        sum_llm.ainvoke = AsyncMock(return_value=_summaries_response(["int1", "int2"]))
        sum_llm_cls.return_value = sum_llm

        # Telegram bot mock
        bot = AsyncMock()
        msg_counter = {"n": 100}

        async def fake_send(**kwargs):
            msg = MagicMock()
            msg.message_id = msg_counter["n"]
            msg_counter["n"] += 1
            return msg

        bot.send_message = AsyncMock(side_effect=fake_send)
        bot_cls.return_value = bot

        # Feedback LLM mock
        fb_llm = AsyncMock()
        fb_llm.ainvoke = AsyncMock(return_value=_feedback_response())
        fb_llm_cls.return_value = fb_llm

        yield {
            "session": session,
            "scorer_llm": scorer_llm,
            "sum_llm": sum_llm,
            "bot": bot,
            "fb_llm": fb_llm,
        }


async def test_full_digest_then_feedback(mock_all, db_conn, settings):
    """Full lifecycle: digest collects and delivers, then feedback updates preferences."""
    digest_graph = build_digest_graph(settings, db_conn)
    result = await digest_graph.ainvoke({"subreddits": ["python"]})

    # One message per subreddit (both posts grouped)
    assert len(result["delivered_ids"]) == 1
    assert await is_post_seen(db_conn, "int1")
    assert await is_post_seen(db_conn, "int2")

    # Link a post to the telegram message so the feedback graph can look it up
    await db_conn.execute(
        "UPDATE sent_posts SET telegram_message_id = ? WHERE reddit_id = ?",
        (100, "int1"),
    )
    await db_conn.commit()

    # Simulate "up" reaction on the message
    feedback_graph = build_feedback_graph(settings, db_conn)
    await feedback_graph.ainvoke(
        {
            "message_id": 100,
            "reaction_type": "up",
            "post_metadata": {},
            "preference_update": {},
        }
    )

    assert await get_preference_score(db_conn, "python", "web") == 1
    assert await get_preference_score(db_conn, "python", "api") == 1


async def test_second_digest_skips_already_seen(mock_all, db_conn, settings):
    """Second digest run should skip posts already seen in the first run."""
    digest_graph = build_digest_graph(settings, db_conn)

    # First run
    result1 = await digest_graph.ainvoke({"subreddits": ["python"]})
    assert len(result1["delivered_ids"]) == 1

    # Reset mocks for second run (same posts returned by Reddit)
    posts = [_make_post_data("int1"), _make_post_data("int2")]
    homepage_resp = _reddit_response([])
    listing_resp = _reddit_response(posts)
    comments_resp = _comments_response()
    mock_all["session"].get.side_effect = [
        homepage_resp,
        listing_resp,
        comments_resp,
        comments_resp,
    ]
    mock_all["bot"].send_message.reset_mock()

    # Second run — same posts, should be filtered out
    result2 = await digest_graph.ainvoke({"subreddits": ["python"]})
    assert len(result2["filtered_posts"]) == 0
    # "Aucun thread pertinent" message sent
    mock_all["bot"].send_message.assert_called_once()


async def test_negative_preferences_filter_posts(mock_all, db_conn, settings):
    """Posts from subreddits with very negative scores should be filtered out."""
    from reddit_digest.db import update_preference

    await update_preference(db_conn, "python", "general", -5)

    digest_graph = build_digest_graph(settings, db_conn)
    result = await digest_graph.ainvoke({"subreddits": ["python"]})

    assert len(result["filtered_posts"]) == 0
    # "Aucun thread pertinent" message sent
    mock_all["bot"].send_message.assert_called_once()
