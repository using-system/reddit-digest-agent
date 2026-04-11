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
    top_comments: list[str] = []
    relevance_score: int | None = None


class Summary(BaseModel):
    reddit_id: str
    subreddit: str
    summary_text: str


class PostMetadata(BaseModel):
    reddit_id: str
    subreddit: str
    title: str
    url: str
    category: str = ""
    keywords: list[str] = []
