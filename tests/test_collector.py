from unittest.mock import MagicMock, patch

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


def _make_response(posts, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = {"data": {"children": posts}}
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


@pytest.fixture
def mock_session():
    with patch("reddit_digest.nodes.collector.cffi_requests.Session") as mock_cls:
        session = MagicMock()
        mock_cls.return_value = session
        # Homepage call for cookies returns OK
        session.get.return_value = _make_response([])
        yield session


async def test_collect_posts_basic(mock_session, settings):
    posts = [_make_post(f"id{i}", "python") for i in range(3)]
    mock_session.get.side_effect = [_make_response([]), _make_response(posts)]

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 3
    assert result["raw_posts"][0].reddit_id == "id0"
    assert result["raw_posts"][0].subreddit == "python"


async def test_collect_posts_respects_limit(mock_session, settings):
    settings.reddit_limit = 2
    posts = [_make_post(f"id{i}", "python") for i in range(2)]
    mock_session.get.side_effect = [_make_response([]), _make_response(posts)]

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, settings)

    # Second call is the subreddit fetch (first is homepage)
    call_kwargs = mock_session.get.call_args_list[1]
    assert call_kwargs.kwargs["params"]["limit"] == 2
    assert len(result["raw_posts"]) == 2


async def test_collect_posts_error_in_one_subreddit(mock_session, settings):
    good_posts = [_make_post("good1", "python")]

    def fake_get(url, **kwargs):
        if "badsubreddit" in url:
            raise Exception("Not found")
        if "reddit.com/" == url.rstrip("/") + "/" or url == "https://www.reddit.com/":
            return _make_response([])
        return _make_response(good_posts)

    mock_session.get.side_effect = fake_get

    state = {"subreddits": ["python", "badsubreddit"]}
    result = await collect_posts(state, settings)
    assert len(result["raw_posts"]) == 1


async def test_collect_posts_top_sort(mock_session, settings):
    settings.reddit_sort = "top"
    settings.reddit_time_filter = "week"
    posts = [_make_post("t1", "python")]
    mock_session.get.side_effect = [_make_response([]), _make_response(posts)]

    state = {"subreddits": ["python"]}
    result = await collect_posts(state, settings)

    assert len(result["raw_posts"]) == 1
    call_kwargs = mock_session.get.call_args_list[1]
    assert "top.json" in call_kwargs.args[0]
    assert call_kwargs.kwargs["params"]["t"] == "week"
