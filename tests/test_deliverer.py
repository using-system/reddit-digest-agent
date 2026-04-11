from unittest.mock import AsyncMock, MagicMock, patch

from reddit_digest.models import RedditPost, Summary
from reddit_digest.nodes.deliverer import (
    _build_keyboard,
    _format_message,
    deliver_summaries,
)


def _summary(reddit_id: str = "p1") -> Summary:
    return Summary(
        reddit_id=reddit_id,
        subreddit="python",
        title="Test Post",
        summary_text="This is a summary",
        category="tech",
        keywords=["python", "test"],
    )


def _post(reddit_id: str = "p1") -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit="python",
        title="Test Post",
        url="https://reddit.com/p1",
    )


def test_format_message():
    msg = _format_message(_summary())
    assert "r/python" in msg
    assert "Test Post" in msg
    assert "This is a summary" in msg
    assert "tech" in msg


def test_build_keyboard():
    kb = _build_keyboard("abc123")
    buttons = kb.inline_keyboard[0]
    assert len(buttons) == 3
    assert buttons[0].callback_data == "more:abc123"
    assert buttons[1].callback_data == "less:abc123"
    assert buttons[2].callback_data == "irrelevant:abc123"


async def test_deliver_summaries(db_conn, settings):
    fake_msg = MagicMock()
    fake_msg.message_id = 100

    with patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls:
        bot_instance = AsyncMock()
        bot_instance.send_message = AsyncMock(return_value=fake_msg)
        mock_bot_cls.return_value = bot_instance

        state = {
            "summaries": [_summary("p1")],
            "filtered_posts": [_post("p1")],
        }
        result = await deliver_summaries(state, settings, db_conn)

    assert result["delivered_ids"] == ["100"]
    bot_instance.send_message.assert_called_once()
    call_kwargs = bot_instance.send_message.call_args.kwargs
    assert call_kwargs["chat_id"] == "123"
    assert call_kwargs["parse_mode"] == "HTML"


async def test_deliver_summaries_empty(db_conn, settings):
    state = {"summaries": [], "filtered_posts": []}
    result = await deliver_summaries(state, settings, db_conn)
    assert result["delivered_ids"] == []
