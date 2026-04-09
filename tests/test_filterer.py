from reddit_digest.db import save_sent_post, update_preference
from reddit_digest.models import RedditPost
from reddit_digest.nodes.filterer import filter_posts


def _post(reddit_id: str, subreddit: str = "python") -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit=subreddit,
        title=f"Post {reddit_id}",
        url=f"https://reddit.com/{reddit_id}",
    )


async def test_filter_removes_already_sent(db_conn):
    post = _post("sent1")
    await save_sent_post(db_conn, post, telegram_message_id=1)

    state = {"raw_posts": [post, _post("new1")]}
    result = await filter_posts(state, db_conn)
    assert len(result["filtered_posts"]) == 1
    assert result["filtered_posts"][0].reddit_id == "new1"


async def test_filter_removes_negative_subreddit(db_conn):
    # Score -4 is below threshold (-3)
    await update_preference(db_conn, "badsubr", "general", -4)

    state = {"raw_posts": [_post("p1", "badsubr"), _post("p2", "python")]}
    result = await filter_posts(state, db_conn)
    assert len(result["filtered_posts"]) == 1
    assert result["filtered_posts"][0].subreddit == "python"


async def test_filter_keeps_neutral_and_positive(db_conn):
    await update_preference(db_conn, "python", "web", 2)

    state = {"raw_posts": [_post("p1", "python"), _post("p2", "rust")]}
    result = await filter_posts(state, db_conn)
    assert len(result["filtered_posts"]) == 2


async def test_filter_empty_input(db_conn):
    state = {"raw_posts": []}
    result = await filter_posts(state, db_conn)
    assert result["filtered_posts"] == []
