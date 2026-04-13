import json
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage

from reddit_digest.db import is_post_seen
from reddit_digest.graphs.digest import build_digest_graph


def _mcp_top_posts_text(posts):
    """Build MCP get_top_posts text for test posts."""
    lines = ["# Top Posts from r/python (hot)\n"]
    for i, p in enumerate(posts, 1):
        lines.append(f"### {i}. {p.get('title', 'Test')}")
        lines.append("- Author: u/testuser")
        lines.append(f"- Score: {p.get('score', 100)} (95.0% upvoted)")
        lines.append(f"- Comments: {p.get('num_comments', 20)}")
        lines.append("- Posted: 4/12/2026, 10:00:00 AM")
        lines.append(
            f"- Link: https://reddit.com/r/{p['sub']}/comments/{p['id']}/test/"
        )
        lines.append("")
    return "\n".join(lines)


def _mcp_comments_text():
    """Build MCP get_post_comments text with one comment."""
    return (
        "# Comments for: Test\n\n"
        "## Post Details\n"
        "- Author: u/test\n"
        "- Subreddit: r/python\n"
        "- Score: 100 (95.0% upvoted)\n"
        "- Posted: 4/12/2026, 10:00:00 AM\n"
        "- Link: https://reddit.com/r/python/comments/x1/test/\n\n"
        "## Post Content\ncontent\n\n"
        "## Comments (1 loaded, sorted by best)\n\n"
        "**u/commenter** \u2022 5 points \u2022 4/12/2026, 11:00:00 AM\n"
        "Nice\n"
    )


def _mcp_tool_result(text):
    content_item = MagicMock()
    content_item.text = text
    result = MagicMock()
    result.content = [content_item]
    return result


def _mock_mcp_conn(call_tool_side_effect):
    """Create a patched _MCPConnection context manager."""
    session = AsyncMock()
    session.call_tool.side_effect = call_tool_side_effect
    mock_conn = MagicMock()
    mock_conn.connect = AsyncMock(return_value=session)
    mock_conn.close = AsyncMock()
    return patch(
        "reddit_digest.nodes.collector._MCPConnection",
        return_value=mock_conn,
    )


async def test_digest_graph_full_flow(db_conn, settings):
    posts = [{"id": "x1", "sub": "python", "score": 100, "num_comments": 20}]

    scores_resp = AIMessage(content=json.dumps({"scores": {"x1": 9}}))
    summaries_resp = AIMessage(
        content=json.dumps({"summaries": {"x1": "Great Python post"}})
    )

    fake_msg = MagicMock()
    fake_msg.message_id = 42

    with (
        _mock_mcp_conn(
            [
                _mcp_tool_result(_mcp_top_posts_text(posts)),
                _mcp_tool_result(_mcp_comments_text()),
            ]
        ),
        patch("reddit_digest.nodes.scorer.ChatOpenAI") as mock_scorer_llm_cls,
        patch("reddit_digest.nodes.summarizer.ChatOpenAI") as mock_sum_llm_cls,
        patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls,
    ):
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

    scores_resp = AIMessage(content=json.dumps({"scores": {"x1": 2}}))

    with (
        _mock_mcp_conn(
            [
                _mcp_tool_result(_mcp_top_posts_text(posts)),
                _mcp_tool_result(_mcp_comments_text()),
            ]
        ),
        patch("reddit_digest.nodes.scorer.ChatOpenAI") as mock_scorer_llm_cls,
        patch("reddit_digest.nodes.summarizer.ChatOpenAI") as mock_sum_llm_cls,
        patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls,
    ):
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
