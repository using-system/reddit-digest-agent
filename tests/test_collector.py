from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reddit_digest.nodes.collector import collect_posts


def _make_top_posts_response(subreddit: str, posts: list[dict]) -> str:
    """Build a fake MCP get_top_posts text response."""
    lines = [f"# Top Posts from r/{subreddit} (hot)\n"]
    for i, p in enumerate(posts, 1):
        lines.append(f"### {i}. {p['title']}")
        lines.append(f"- Author: u/{p.get('author', 'testuser')}")
        lines.append(f"- Score: {p['score']} (95.0% upvoted)")
        lines.append(f"- Comments: {p['num_comments']}")
        lines.append("- Posted: 4/12/2026, 10:00:00 AM")
        lines.append(
            f"- Link: https://reddit.com/r/{subreddit}/comments/{p['id']}/{p['title'].lower().replace(' ', '_')}/"
        )
        lines.append("")
    return "\n".join(lines)


def _make_comments_response(comments: list[str]) -> str:
    """Build a fake MCP get_post_comments text response."""
    lines = [
        "# Comments for: Test Post",
        "",
        "## Post Details",
        "- Author: u/test",
        "- Subreddit: r/python",
        "- Score: 42 (95.0% upvoted)",
        "- Posted: 4/12/2026, 10:00:00 AM",
        "- Link: https://reddit.com/r/python/comments/abc123/test_post/",
        "",
        "## Post Content",
        "Test content",
        "",
        f"## Comments ({len(comments)} loaded, sorted by best)",
        "",
    ]
    for i, c in enumerate(comments):
        lines.append(
            f"**u/commenter{i}** \u2022 {10 - i} points \u2022 4/12/2026, 10:00:00 AM"
        )
        lines.append(c)
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _make_tool_result(text: str) -> MagicMock:
    """Simulate an MCP CallToolResult."""
    content_item = MagicMock()
    content_item.text = text
    result = MagicMock()
    result.content = [content_item]
    return result


@pytest.fixture
def mock_mcp_session():
    """Mock the MCP client session."""
    session = AsyncMock()
    return session


@pytest.fixture
def _patch_mcp(mock_mcp_session):
    """Patch _MCPConnection to return the mock session."""
    mock_conn = MagicMock()
    mock_conn.connect = AsyncMock(return_value=mock_mcp_session)
    mock_conn.close = AsyncMock()
    with patch(
        "reddit_digest.nodes.collector._MCPConnection",
        return_value=mock_conn,
    ):
        yield


@pytest.mark.usefixtures("_patch_mcp")
async def test_collect_posts_basic(mock_mcp_session, settings):
    settings.reddit_comments_limit = 0
    posts_data = [
        {"id": "abc123", "title": "Test Post", "score": 42, "num_comments": 5},
    ]
    mock_mcp_session.call_tool.return_value = _make_tool_result(
        _make_top_posts_response("python", posts_data)
    )

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 1
    assert result["raw_posts"][0].reddit_id == "abc123"
    assert result["raw_posts"][0].subreddit == "python"


@pytest.mark.usefixtures("_patch_mcp")
async def test_collect_posts_with_comments(mock_mcp_session, settings):
    settings.reddit_comments_limit = 3
    posts_data = [
        {"id": "abc123", "title": "Test Post", "score": 42, "num_comments": 5},
    ]
    top_posts_text = _make_top_posts_response("python", posts_data)
    comments_text = _make_comments_response(["Great post", "I agree", "Nice work"])

    mock_mcp_session.call_tool.side_effect = [
        _make_tool_result(top_posts_text),
        _make_tool_result(comments_text),
    ]

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 1
    assert len(result["raw_posts"][0].top_comments) == 3
    assert result["raw_posts"][0].top_comments[0] == "Great post"


@pytest.mark.usefixtures("_patch_mcp")
async def test_collect_posts_multiple_subreddits(mock_mcp_session, settings):
    settings.reddit_comments_limit = 0
    posts_py = [{"id": "py1", "title": "Py Post", "score": 10, "num_comments": 2}]
    posts_ml = [{"id": "ml1", "title": "ML Post", "score": 20, "num_comments": 4}]

    mock_mcp_session.call_tool.side_effect = [
        _make_tool_result(_make_top_posts_response("python", posts_py)),
        _make_tool_result(_make_top_posts_response("machinelearning", posts_ml)),
    ]

    state = {"subreddits": ["python", "machinelearning"]}
    result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 2
    subreddits = {p.subreddit for p in result["raw_posts"]}
    assert subreddits == {"python", "machinelearning"}


@pytest.mark.usefixtures("_patch_mcp")
async def test_collect_posts_error_one_subreddit(mock_mcp_session, settings):
    settings.reddit_comments_limit = 0
    good_text = _make_top_posts_response(
        "python", [{"id": "ok1", "title": "OK", "score": 5, "num_comments": 1}]
    )

    mock_mcp_session.call_tool.side_effect = [
        _make_tool_result(good_text),
        Exception("MCP error"),
    ]

    state = {"subreddits": ["python", "badsubreddit"]}
    result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 1


@pytest.mark.usefixtures("_patch_mcp")
async def test_collect_posts_passes_sort_params(mock_mcp_session, settings):
    settings.reddit_comments_limit = 0
    settings.reddit_sort = "top"
    settings.reddit_time_filter = "week"
    posts_data = [{"id": "t1", "title": "Top", "score": 100, "num_comments": 10}]
    mock_mcp_session.call_tool.return_value = _make_tool_result(
        _make_top_posts_response("python", posts_data)
    )

    state = {"subreddits": ["python"]}
    await collect_posts(state, settings)

    call_args = mock_mcp_session.call_tool.call_args_list[0]
    assert call_args.kwargs["arguments"]["time_filter"] == "week"
