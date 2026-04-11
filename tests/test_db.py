import pytest

from reddit_digest.db import (
    get_post_by_message_id,
    get_preference_score,
    get_preferences,
    init_db,
    is_post_seen,
    save_reaction,
    save_seen_post,
    update_preference,
)
from reddit_digest.models import RedditPost


@pytest.fixture
async def db():
    conn = await init_db(":memory:")
    yield conn
    await conn.close()


def _make_post(**overrides) -> RedditPost:
    defaults = {
        "reddit_id": "abc123",
        "subreddit": "python",
        "title": "Test Post",
        "url": "https://reddit.com/r/python/abc123",
    }
    return RedditPost(**{**defaults, **overrides})


async def test_tables_created(db):
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    tables = [row[0] for row in await cursor.fetchall()]
    assert "preferences" in tables
    assert "reactions" in tables
    assert "sent_posts" in tables


async def test_save_seen_post_default_status(db):
    post = _make_post()
    assert not await is_post_seen(db, post.reddit_id)
    await save_seen_post(db, post, status="seen")
    assert await is_post_seen(db, post.reddit_id)


async def test_save_seen_post_sent_status(db):
    post = _make_post()
    await save_seen_post(db, post, telegram_message_id=100, status="sent")
    assert await is_post_seen(db, post.reddit_id)
    cursor = await db.execute(
        "SELECT status, telegram_message_id FROM sent_posts WHERE reddit_id = ?",
        (post.reddit_id,),
    )
    row = await cursor.fetchone()
    assert row[0] == "sent"
    assert row[1] == 100


async def test_get_post_by_message_id(db):
    post = _make_post()
    await save_seen_post(db, post, telegram_message_id=200, status="sent")
    meta = await get_post_by_message_id(db, 200)
    assert meta is not None
    assert meta.reddit_id == "abc123"


async def test_get_post_by_message_id_not_found(db):
    meta = await get_post_by_message_id(db, 999)
    assert meta is None


async def test_save_reaction(db):
    post = _make_post()
    await save_seen_post(db, post, telegram_message_id=300, status="sent")
    await save_reaction(db, 300, "up")
    cursor = await db.execute(
        "SELECT reaction_type FROM reactions WHERE telegram_message_id = 300"
    )
    row = await cursor.fetchone()
    assert row[0] == "up"


async def test_update_preference_insert(db):
    await update_preference(db, "python", "web", 1)
    score = await get_preference_score(db, "python", "web")
    assert score == 1


async def test_update_preference_upsert(db):
    await update_preference(db, "python", "web", 1)
    await update_preference(db, "python", "web", 1)
    await update_preference(db, "python", "web", -2)
    score = await get_preference_score(db, "python", "web")
    assert score == 0


async def test_get_preferences(db):
    await update_preference(db, "python", "web", 3)
    await update_preference(db, "ml", "nlp", -1)
    prefs = await get_preferences(db)
    assert len(prefs) == 2
    by_topic = {p["topic"]: p for p in prefs}
    assert by_topic["web"]["score"] == 3
    assert by_topic["nlp"]["score"] == -1
