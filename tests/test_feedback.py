import json
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from reddit_digest.db import get_preference_score, save_seen_post
from reddit_digest.models import RedditPost
from reddit_digest.nodes.feedback import (
    analyze_reaction,
    receive_reaction,
    update_preferences,
)


def _post() -> RedditPost:
    return RedditPost(
        reddit_id="fb1",
        subreddit="python",
        title="Feedback Test Post",
        url="https://reddit.com/fb1",
    )


@pytest.fixture
def mock_llm():
    with patch("reddit_digest.nodes.feedback.ChatOpenAI") as mock_cls:
        instance = AsyncMock()
        data = {"topics": ["web", "frameworks"]}
        instance.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(data)))
        mock_cls.return_value = instance
        yield instance


async def test_receive_reaction(db_conn):
    post = _post()
    await save_seen_post(
        db_conn,
        post,
        telegram_message_id=500,
        status="sent",
    )

    state = {
        "message_id": 500,
        "reaction_type": "up",
        "post_metadata": {},
        "preference_update": {},
    }
    result = await receive_reaction(state, db_conn)
    assert result["post_metadata"]["reddit_id"] == "fb1"
    assert result["post_metadata"]["subreddit"] == "python"


async def test_receive_reaction_prefilled(db_conn):
    """When bot passes post_metadata pre-filled, receive_reaction skips DB lookup."""
    state = {
        "message_id": 999,
        "reaction_type": "up",
        "post_metadata": {"reddit_id": "fb1", "subreddit": "python", "title": "Test"},
        "preference_update": {},
    }
    result = await receive_reaction(state, db_conn)
    assert result["post_metadata"]["reddit_id"] == "fb1"


async def test_receive_reaction_not_found(db_conn):
    state = {
        "message_id": 999,
        "reaction_type": "up",
        "post_metadata": {},
        "preference_update": {},
    }
    result = await receive_reaction(state, db_conn)
    assert result["post_metadata"] == {}


async def test_analyze_reaction_up(mock_llm, settings):
    state = {
        "message_id": 1,
        "reaction_type": "up",
        "post_metadata": {
            "subreddit": "python",
            "title": "Test",
            "category": "tech",
            "keywords": ["python"],
        },
        "preference_update": {},
    }
    result = await analyze_reaction(state, settings)
    assert result["preference_update"]["score_delta"] == 1
    assert result["preference_update"]["topics"] == ["web", "frameworks"]


async def test_analyze_reaction_down(mock_llm, settings):
    state = {
        "message_id": 1,
        "reaction_type": "down",
        "post_metadata": {
            "subreddit": "python",
            "title": "Test",
            "category": "tech",
            "keywords": [],
        },
        "preference_update": {},
    }
    result = await analyze_reaction(state, settings)
    assert result["preference_update"]["score_delta"] == -1


async def test_analyze_reaction_llm_error(mock_llm, settings):
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM down"))
    state = {
        "message_id": 1,
        "reaction_type": "down",
        "post_metadata": {
            "subreddit": "python",
            "title": "Test",
            "category": "tech",
            "keywords": [],
        },
        "preference_update": {},
    }
    result = await analyze_reaction(state, settings)
    assert result["preference_update"]["topics"] == ["tech"]
    assert result["preference_update"]["score_delta"] == -1


async def test_update_preferences(db_conn):
    state = {
        "message_id": 1,
        "reaction_type": "up",
        "post_metadata": {},
        "preference_update": {
            "subreddit": "python",
            "topics": ["web", "frameworks"],
            "score_delta": 1,
        },
    }
    await update_preferences(state, db_conn)
    assert await get_preference_score(db_conn, "python", "web") == 1
    assert await get_preference_score(db_conn, "python", "frameworks") == 1


async def test_update_preferences_empty(db_conn):
    state = {
        "message_id": 1,
        "reaction_type": "up",
        "post_metadata": {},
        "preference_update": {},
    }
    result = await update_preferences(state, db_conn)
    assert result == {}
