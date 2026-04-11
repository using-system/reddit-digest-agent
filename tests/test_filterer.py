from reddit_digest.db import save_seen_post, update_preference
from reddit_digest.models import RedditPost
from reddit_digest.nodes.filterer import filter_posts


def _post(
    reddit_id: str,
    subreddit: str = "python",
    score: int = 50,
    num_comments: int = 10,
) -> RedditPost:
    return RedditPost(
        reddit_id=reddit_id,
        subreddit=subreddit,
        title=f"Post {reddit_id}",
        url=f"https://reddit.com/{reddit_id}",
        score=score,
        num_comments=num_comments,
    )


async def test_filter_removes_already_seen(db_conn):
    post = _post("sent1")
    await save_seen_post(db_conn, post, status="seen")

    state = {"raw_posts": [post, _post("new1")]}
    result = await filter_posts(state, db_conn)
    assert len(result["filtered_posts"]) == 1
    assert result["filtered_posts"][0].reddit_id == "new1"


async def test_filter_removes_negative_subreddit(db_conn):
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


async def test_filter_removes_low_score(db_conn, settings):
    low = _post("low1", score=5, num_comments=10)
    high = _post("high1", score=50, num_comments=10)

    state = {"raw_posts": [low, high]}
    result = await filter_posts(state, db_conn, settings)
    assert len(result["filtered_posts"]) == 1
    assert result["filtered_posts"][0].reddit_id == "high1"


async def test_filter_removes_few_comments(db_conn, settings):
    few = _post("few1", score=50, num_comments=1)
    many = _post("many1", score=50, num_comments=10)

    state = {"raw_posts": [few, many]}
    result = await filter_posts(state, db_conn, settings)
    assert len(result["filtered_posts"]) == 1
    assert result["filtered_posts"][0].reddit_id == "many1"
