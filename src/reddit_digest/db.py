from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from reddit_digest.models import PostMetadata, RedditPost

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sent_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reddit_id TEXT UNIQUE NOT NULL,
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL,
    telegram_message_id INTEGER,
    category TEXT DEFAULT '',
    keywords TEXT DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'sent',
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_message_id INTEGER NOT NULL,
    reaction_type TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subreddit TEXT NOT NULL,
    topic TEXT NOT NULL,
    score INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(subreddit, topic)
);
"""


async def init_db(db_path: str = "digest.db") -> aiosqlite.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(db_path)
    await conn.executescript(_SCHEMA)
    # Migration: add status column if missing (existing DBs)
    try:
        await conn.execute("SELECT status FROM sent_posts LIMIT 1")
    except Exception:
        await conn.execute(
            "ALTER TABLE sent_posts ADD COLUMN status TEXT NOT NULL DEFAULT 'sent'"
        )
        await conn.commit()
    return conn


async def is_post_seen(conn: aiosqlite.Connection, reddit_id: str) -> bool:
    cursor = await conn.execute(
        "SELECT 1 FROM sent_posts WHERE reddit_id = ?", (reddit_id,)
    )
    return await cursor.fetchone() is not None


async def save_seen_post(
    conn: aiosqlite.Connection,
    post: RedditPost,
    *,
    telegram_message_id: int | None = None,
    status: str = "seen",
) -> None:
    await conn.execute(
        """INSERT OR IGNORE INTO sent_posts
           (reddit_id, subreddit, title, url, telegram_message_id, status, sent_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            post.reddit_id,
            post.subreddit,
            post.title,
            post.url,
            telegram_message_id,
            status,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await conn.commit()


async def get_post_by_message_id(
    conn: aiosqlite.Connection, telegram_message_id: int
) -> PostMetadata | None:
    cursor = await conn.execute(
        """SELECT reddit_id, subreddit, title, url, category, keywords
           FROM sent_posts WHERE telegram_message_id = ?""",
        (telegram_message_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return PostMetadata(
        reddit_id=row[0],
        subreddit=row[1],
        title=row[2],
        url=row[3],
        category=row[4],
        keywords=json.loads(row[5]),
    )


async def get_post_by_reddit_id(
    conn: aiosqlite.Connection, reddit_id: str
) -> PostMetadata | None:
    cursor = await conn.execute(
        """SELECT reddit_id, subreddit, title, url, category, keywords
           FROM sent_posts WHERE reddit_id = ?""",
        (reddit_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return PostMetadata(
        reddit_id=row[0],
        subreddit=row[1],
        title=row[2],
        url=row[3],
        category=row[4],
        keywords=json.loads(row[5]),
    )


async def save_reaction(
    conn: aiosqlite.Connection, telegram_message_id: int, reaction_type: str
) -> None:
    await conn.execute(
        "INSERT INTO reactions (telegram_message_id, reaction_type) VALUES (?, ?)",
        (telegram_message_id, reaction_type),
    )
    await conn.commit()


async def get_preferences(conn: aiosqlite.Connection) -> list[dict]:
    cursor = await conn.execute("SELECT subreddit, topic, score FROM preferences")
    rows = await cursor.fetchall()
    return [{"subreddit": r[0], "topic": r[1], "score": r[2]} for r in rows]


async def update_preference(
    conn: aiosqlite.Connection, subreddit: str, topic: str, score_delta: int
) -> None:
    await conn.execute(
        """INSERT INTO preferences (subreddit, topic, score, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(subreddit, topic)
           DO UPDATE SET score = score + ?, updated_at = ?""",
        (
            subreddit,
            topic,
            score_delta,
            datetime.now(timezone.utc).isoformat(),
            score_delta,
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    await conn.commit()


async def get_preference_score(
    conn: aiosqlite.Connection, subreddit: str, topic: str
) -> int:
    cursor = await conn.execute(
        "SELECT score FROM preferences WHERE subreddit = ? AND topic = ?",
        (subreddit, topic),
    )
    row = await cursor.fetchone()
    return row[0] if row else 0
