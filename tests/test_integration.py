"""End-to-end integration tests: full digest cycle + feedback loop."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.db import get_preference_score, is_post_seen
from reddit_digest.graphs.digest import build_digest_graph
from reddit_digest.graphs.feedback import build_feedback_graph


def _mcp_top_posts_text(ids: list[str], subreddit: str = "python"):
    """Build MCP get_top_posts text."""
    lines = [f"# Top Posts from r/{subreddit} (hot)\n"]
    for i, id_ in enumerate(ids, 1):
        lines.append(f"### {i}. Post {id_}")
        lines.append("- Author: u/testuser")
        lines.append("- Score: 50 (95.0% upvoted)")
        lines.append("- Comments: 10")
        lines.append("- Posted: 4/12/2026, 10:00:00 AM")
        lines.append(
            f"- Link: https://reddit.com/r/{subreddit}/comments/{id_}/post_{id_}/"
        )
        lines.append("")
    return "\n".join(lines)


def _mcp_comments_text(id_: str = "int1"):
    """Build MCP get_post_comments text with one comment."""
    return (
        f"# Comments for: Post {id_}\n\n"
        "## Post Details\n"
        "- Author: u/test\n"
        "- Subreddit: r/python\n"
        "- Score: 50 (95.0% upvoted)\n"
        "- Posted: 4/12/2026, 10:00:00 AM\n"
        f"- Link: https://reddit.com/r/python/comments/{id_}/post_{id_}/\n\n"
        f"## Post Content\nContent of post {id_}\n\n"
        "## Comments (1 loaded, sorted by best)\n\n"
        "**u/commenter** \u2022 5 points \u2022 4/12/2026, 11:00:00 AM\n"
        "Nice post\n"
    )


def _mcp_tool_result(text):
    content_item = MagicMock()
    content_item.text = text
    result = MagicMock()
    result.content = [content_item]
    return result


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
    """Mock all external services: Reddit MCP, LLM (scorer + summarizer + feedback), Telegram."""
    # MCP mock
    mcp_session = AsyncMock()
    mcp_session.call_tool.side_effect = [
        _mcp_tool_result(_mcp_top_posts_text(["int1", "int2"])),
        _mcp_tool_result(_mcp_comments_text("int1")),
        _mcp_tool_result(_mcp_comments_text("int2")),
    ]
    mock_conn = MagicMock()
    mock_conn.connect = AsyncMock(return_value=mcp_session)
    mock_conn.close = AsyncMock()

    with (
        patch(
            "reddit_digest.nodes.collector._MCPConnection",
            return_value=mock_conn,
        ),
        patch("reddit_digest.nodes.scorer.ChatOpenAI") as scorer_llm_cls,
        patch("reddit_digest.nodes.summarizer.ChatOpenAI") as sum_llm_cls,
        patch("reddit_digest.nodes.deliverer.Bot") as bot_cls,
        patch("reddit_digest.nodes.feedback.ChatOpenAI") as fb_llm_cls,
    ):
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
            "mcp_session": mcp_session,
            "mcp_conn": mock_conn,
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

    # Simulate "up" reaction — bot passes post_metadata pre-filled (looked up by reddit_id)
    from reddit_digest.db import get_post_by_reddit_id

    post_meta = await get_post_by_reddit_id(db_conn, "int1")
    feedback_graph = build_feedback_graph(settings, db_conn)
    await feedback_graph.ainvoke(
        {
            "message_id": 100,
            "reaction_type": "up",
            "post_metadata": post_meta.model_dump(),
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

    # Reset MCP mock for second run (same posts returned)
    mock_all["mcp_session"].call_tool.side_effect = [
        _mcp_tool_result(_mcp_top_posts_text(["int1", "int2"])),
        _mcp_tool_result(_mcp_comments_text("int1")),
        _mcp_tool_result(_mcp_comments_text("int2")),
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
