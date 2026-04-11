import json
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from reddit_digest.db import is_post_seen
from reddit_digest.graphs.digest import build_digest_graph


def _make_collector_response(posts):
    children = [
        {
            "data": {
                "id": p["id"],
                "subreddit": p["sub"],
                "title": p.get("title", "Test"),
                "url": f"https://reddit.com/{p['id']}",
                "score": p.get("score", 100),
                "num_comments": p.get("num_comments", 20),
                "selftext": "content",
                "created_utc": 1700000000.0,
            }
        }
        for p in posts
    ]
    resp = MagicMock()
    resp.json.return_value = {"data": {"children": children}}
    resp.raise_for_status = MagicMock()
    return resp


def _make_comments_response():
    resp = MagicMock()
    resp.json.return_value = [
        {"data": {"children": []}},
        {"data": {"children": [{"kind": "t1", "data": {"body": "Nice", "score": 5}}]}},
    ]
    resp.raise_for_status = MagicMock()
    return resp


async def test_digest_graph_full_flow(db_conn, settings):
    posts = [{"id": "x1", "sub": "python", "score": 100, "num_comments": 20}]
    homepage_resp = MagicMock()
    homepage_resp.json.return_value = {"data": {"children": []}}
    homepage_resp.raise_for_status = MagicMock()

    scores_resp = AIMessage(content=json.dumps({"scores": {"x1": 9}}))
    summaries_resp = AIMessage(
        content=json.dumps({"summaries": {"x1": "Great Python post"}})
    )

    fake_msg = MagicMock()
    fake_msg.message_id = 42

    with (
        patch(
            "reddit_digest.nodes.collector.cffi_requests.Session"
        ) as mock_session_cls,
        patch("reddit_digest.nodes.scorer.ChatOpenAI") as mock_scorer_llm_cls,
        patch("reddit_digest.nodes.summarizer.ChatOpenAI") as mock_sum_llm_cls,
        patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls,
    ):
        session = MagicMock()
        mock_session_cls.return_value = session
        session.get.side_effect = [
            homepage_resp,
            _make_collector_response(posts),
            _make_comments_response(),
        ]

        scorer_llm = AsyncMock()
        scorer_llm.ainvoke = AsyncMock(return_value=scores_resp)
        mock_scorer_llm_cls.return_value = scorer_llm

        sum_llm = AsyncMock()
        sum_llm.ainvoke = AsyncMock(return_value=summaries_resp)
        mock_sum_llm_cls.return_value = sum_llm

        bot = AsyncMock()
        bot.send_message = AsyncMock(return_value=fake_msg)
        mock_bot_cls.return_value = bot

        graph = build_digest_graph(settings, db_conn)
        result = await graph.ainvoke({"subreddits": ["python"]})

    assert len(result["delivered_ids"]) == 1
    assert await is_post_seen(db_conn, "x1")


async def test_digest_graph_no_relevant_posts(db_conn, settings):
    posts = [{"id": "x1", "sub": "python", "score": 100, "num_comments": 20}]
    homepage_resp = MagicMock()
    homepage_resp.json.return_value = {"data": {"children": []}}
    homepage_resp.raise_for_status = MagicMock()

    scores_resp = AIMessage(content=json.dumps({"scores": {"x1": 2}}))

    with (
        patch(
            "reddit_digest.nodes.collector.cffi_requests.Session"
        ) as mock_session_cls,
        patch("reddit_digest.nodes.scorer.ChatOpenAI") as mock_scorer_llm_cls,
        patch("reddit_digest.nodes.summarizer.ChatOpenAI") as mock_sum_llm_cls,
        patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls,
    ):
        session = MagicMock()
        mock_session_cls.return_value = session
        session.get.side_effect = [
            homepage_resp,
            _make_collector_response(posts),
            _make_comments_response(),
        ]

        scorer_llm = AsyncMock()
        scorer_llm.ainvoke = AsyncMock(return_value=scores_resp)
        mock_scorer_llm_cls.return_value = scorer_llm

        sum_llm = AsyncMock()
        mock_sum_llm_cls.return_value = sum_llm

        bot = AsyncMock()
        bot.send_message = AsyncMock()
        mock_bot_cls.return_value = bot

        graph = build_digest_graph(settings, db_conn)
        await graph.ainvoke({"subreddits": ["python"]})

    bot.send_message.assert_called_once()
    call_kwargs = bot.send_message.call_args.kwargs
    assert "Aucun thread pertinent" in call_kwargs["text"]
    assert await is_post_seen(db_conn, "x1")
