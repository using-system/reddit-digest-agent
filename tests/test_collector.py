from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from reddit_digest.nodes.collector import collect_posts


def _make_submission(id_: str, subreddit: str, title: str = "Test"):
    sub = MagicMock()
    sub.id = id_
    sub.title = title
    sub.url = f"https://reddit.com/{id_}"
    sub.score = 42
    sub.num_comments = 5
    sub.selftext = "content"
    sub.created_utc = 1700000000.0
    return sub


@pytest.fixture
def mock_reddit():
    with patch("reddit_digest.nodes.collector.asyncpraw.Reddit") as mock_cls:
        instance = AsyncMock()
        mock_cls.return_value = instance
        yield instance


async def test_collect_posts_basic(mock_reddit, sample_config, sample_secrets):
    submissions = [_make_submission(f"id{i}", "python") for i in range(3)]

    sub_obj = AsyncMock()

    async def fake_hot(**kwargs):
        for s in submissions[: kwargs.get("limit", 20)]:
            yield s

    sub_obj.hot = fake_hot
    mock_reddit.subreddit = AsyncMock(return_value=sub_obj)

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, sample_config, sample_secrets)

    assert len(result["raw_posts"]) == 3
    assert result["raw_posts"][0].reddit_id == "id0"
    assert result["raw_posts"][0].subreddit == "python"


async def test_collect_posts_respects_limit(mock_reddit, sample_config, sample_secrets):
    sample_config.reddit.limit = 2
    submissions = [_make_submission(f"id{i}", "python") for i in range(5)]

    sub_obj = AsyncMock()

    async def fake_hot(**kwargs):
        for s in submissions[: kwargs.get("limit", 20)]:
            yield s

    sub_obj.hot = fake_hot
    mock_reddit.subreddit = AsyncMock(return_value=sub_obj)

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, sample_config, sample_secrets)
    assert len(result["raw_posts"]) == 2


async def test_collect_posts_error_in_one_subreddit(
    mock_reddit, sample_config, sample_secrets
):
    good_submissions = [_make_submission("good1", "python")]

    sub_good = AsyncMock()

    async def fake_hot(**kwargs):
        for s in good_submissions:
            yield s

    sub_good.hot = fake_hot

    sub_bad = AsyncMock()
    sub_bad.hot = MagicMock(side_effect=Exception("API error"))

    async def fake_subreddit(name):
        if name == "badsubreddit":
            return sub_bad
        return sub_good

    mock_reddit.subreddit = AsyncMock(side_effect=fake_subreddit)

    state = {"subreddits": ["python", "badsubreddit"]}
    result = await collect_posts(state, sample_config, sample_secrets)
    assert len(result["raw_posts"]) == 1


async def test_collect_posts_top_sort(mock_reddit, sample_config, sample_secrets):
    sample_config.reddit.sort = "top"
    sample_config.reddit.time_filter = "week"
    submissions = [_make_submission("t1", "python")]

    sub_obj = AsyncMock()
    calls = []

    async def fake_top(**kwargs):
        calls.append(kwargs)
        for s in submissions:
            yield s

    sub_obj.top = fake_top
    mock_reddit.subreddit = AsyncMock(return_value=sub_obj)

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, sample_config, sample_secrets)
    assert len(result["raw_posts"]) == 1
    assert calls[0]["time_filter"] == "week"
