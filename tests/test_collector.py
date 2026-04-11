from unittest.mock import AsyncMock, patch

import httpx
import pytest

from reddit_digest.nodes.collector import collect_posts


def _make_post(id_: str, subreddit: str, title: str = "Test"):
    return {
        "kind": "t3",
        "data": {
            "id": id_,
            "subreddit": subreddit,
            "title": title,
            "url": f"https://reddit.com/{id_}",
            "score": 42,
            "num_comments": 5,
            "selftext": "content",
            "created_utc": 1700000000.0,
        },
    }


_FAKE_REQUEST = httpx.Request("GET", "https://www.reddit.com/r/test/hot.json")


def _make_response(posts, status_code=200):
    body = {"data": {"children": posts}}
    return httpx.Response(status_code, json=body, request=_FAKE_REQUEST)


@pytest.fixture
def mock_httpx():
    with patch("reddit_digest.nodes.collector.httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        yield client


async def test_collect_posts_basic(mock_httpx, settings):
    posts = [_make_post(f"id{i}", "python") for i in range(3)]
    mock_httpx.get = AsyncMock(return_value=_make_response(posts))

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 3
    assert result["raw_posts"][0].reddit_id == "id0"
    assert result["raw_posts"][0].subreddit == "python"


async def test_collect_posts_respects_limit(mock_httpx, settings):
    settings.reddit_limit = 2
    posts = [_make_post(f"id{i}", "python") for i in range(2)]
    mock_httpx.get = AsyncMock(return_value=_make_response(posts))

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, settings)

    call_kwargs = mock_httpx.get.call_args
    assert call_kwargs.kwargs["params"]["limit"] == 2
    assert len(result["raw_posts"]) == 2


async def test_collect_posts_error_in_one_subreddit(mock_httpx, settings):
    good_posts = [_make_post("good1", "python")]

    async def fake_get(url, **kwargs):
        if "badsubreddit" in url:
            req = httpx.Request("GET", url)
            raise httpx.HTTPStatusError(
                "Not found",
                request=req,
                response=httpx.Response(404, request=req),
            )
        return _make_response(good_posts)

    mock_httpx.get = AsyncMock(side_effect=fake_get)

    state = {"subreddits": ["python", "badsubreddit"]}
    result = await collect_posts(state, settings)
    assert len(result["raw_posts"]) == 1


async def test_collect_posts_top_sort(mock_httpx, settings):
    settings.reddit_sort = "top"
    settings.reddit_time_filter = "week"
    posts = [_make_post("t1", "python")]
    mock_httpx.get = AsyncMock(return_value=_make_response(posts))

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 1
    call_kwargs = mock_httpx.get.call_args
    assert "top.json" in call_kwargs.args[0]
    assert call_kwargs.kwargs["params"]["t"] == "week"
