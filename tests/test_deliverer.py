from unittest.mock import AsyncMock, MagicMock, patch

from reddit_digest.models import RedditPost, Summary
from reddit_digest.nodes.deliverer import (
    _build_keyboard,
    _format_subreddit_message,
    deliver_summaries,
)


def _summary(reddit_id: str = "p1", subreddit: str = "python") -> Summary:
    return Summary(
        reddit_id=reddit_id,
        subreddit=subreddit,
        summary_text=f"Summary of {reddit_id}",
    )


def _post(reddit_id: str = "p1", subreddit: str = "python") -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit=subreddit,
        title="Test Post",
        url=f"https://reddit.com/r/{subreddit}/comments/{reddit_id}",
    )


def test_format_subreddit_message():
    summaries = [_summary("p1"), _summary("p2")]
    posts = [_post("p1"), _post("p2")]
    msg = _format_subreddit_message("python", summaries, posts)
    assert "📌" in msg
    assert "r/python" in msg
    assert "1." in msg
    assert "Summary of p1" in msg
    assert "2." in msg
    assert "Summary of p2" in msg
    assert "reddit.com/r/python/comments/p1" in msg


def test_build_keyboard():
    summaries = [_summary("p1"), _summary("p2")]
    kb = _build_keyboard(summaries)
    assert len(kb.inline_keyboard) == 2
    row1 = kb.inline_keyboard[0]
    assert len(row1) == 2
    assert row1[0].text == "1 👍"
    assert row1[0].callback_data == "up:1:p1"
    assert row1[1].text == "1 👎"
    assert row1[1].callback_data == "down:1:p1"
    row2 = kb.inline_keyboard[1]
    assert row2[0].text == "2 👍"
    assert row2[0].callback_data == "up:2:p2"


async def test_deliver_summaries_grouped(db_conn, settings):
    fake_msg = MagicMock()
    fake_msg.message_id = 100

    with patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls:
        bot_instance = AsyncMock()
        bot_instance.send_message = AsyncMock(return_value=fake_msg)
        mock_bot_cls.return_value = bot_instance

        state = {
            "summaries": [_summary("p1", "python"), _summary("p2", "python")],
            "scored_posts": [_post("p1", "python"), _post("p2", "python")],
        }
        result = await deliver_summaries(state, settings, db_conn)

    assert bot_instance.send_message.call_count == 1
    assert len(result["delivered_ids"]) == 1


async def test_deliver_summaries_multiple_subreddits(db_conn, settings):
    fake_msg = MagicMock()
    fake_msg.message_id = 100

    with patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls:
        bot_instance = AsyncMock()
        bot_instance.send_message = AsyncMock(return_value=fake_msg)
        mock_bot_cls.return_value = bot_instance

        state = {
            "summaries": [_summary("p1", "python"), _summary("p2", "rust")],
            "scored_posts": [_post("p1", "python"), _post("p2", "rust")],
        }
        result = await deliver_summaries(state, settings, db_conn)

    assert bot_instance.send_message.call_count == 2


async def test_deliver_summaries_empty_sends_no_threads(db_conn, settings):
    with patch("reddit_digest.nodes.deliverer.Bot") as mock_bot_cls:
        bot_instance = AsyncMock()
        bot_instance.send_message = AsyncMock()
        mock_bot_cls.return_value = bot_instance

        state = {"summaries": [], "scored_posts": []}
        result = await deliver_summaries(state, settings, db_conn)

    bot_instance.send_message.assert_called_once()
    call_kwargs = bot_instance.send_message.call_args.kwargs
    assert "Aucun thread pertinent" in call_kwargs["text"]
    assert result["delivered_ids"] == []
