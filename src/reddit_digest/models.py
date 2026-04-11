from __future__ import annotations

from pydantic import BaseModel


class RedditPost(BaseModel):
    reddit_id: str
    subreddit: str
    title: str
    url: str
    score: int = 0
    num_comments: int = 0
    selftext: str = ""
    created_utc: float = 0.0


class Summary(BaseModel):
    reddit_id: str
    subreddit: str
    title: str
    summary_text: str
    category: str = ""
    keywords: list[str] = []


class PostMetadata(BaseModel):
    reddit_id: str
    subreddit: str
    title: str
    url: str
    category: str = ""
    keywords: list[str] = []
