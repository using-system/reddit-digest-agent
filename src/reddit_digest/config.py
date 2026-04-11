from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Reddit
    reddit_subreddits: list[str] = ["python", "machinelearning", "selfhosted"]
    reddit_sort: str = "hot"
    reddit_limit: int = 5
    reddit_time_filter: str = "day"
    reddit_comments_limit: int = 5
    reddit_min_score: int = 10
    reddit_min_comments: int = 3

    @field_validator("reddit_limit", mode="before")
    @classmethod
    def _clamp_reddit_limit(cls, v: object) -> int:
        return max(1, min(int(v), 8))

    # LLM (OpenAI-compatible)
    openai_api_key: str
    openai_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "google/gemini-2.5-flash"

    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str

    # Storage
    db_path: str = str(
        Path.home() / ".local" / "share" / "reddit-digest" / "digest.db"
    )

    # Rate limiting
    reddit_fetch_delay: int = 200
    telegram_send_delay: int = 500

    # Digest
    digest_cron: str = "0 8 * * *"
    digest_language: str = "fr"


def load_settings(**kwargs: str) -> Settings:
    return Settings(**kwargs)
