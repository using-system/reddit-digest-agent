from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Reddit
    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str = "reddit-digest-agent"
    reddit_subreddits: list[str] = ["python", "machinelearning", "selfhosted"]
    reddit_sort: str = "hot"
    reddit_limit: int = 20
    reddit_time_filter: str = "day"

    # LLM (OpenAI-compatible)
    llm_api_key: str
    llm_base_url: str = "http://localhost:8080/v1"
    llm_model: str = "gpt-4o-mini"

    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str

    # Digest
    digest_cron: str = "0 8 * * *"
    digest_language: str = "fr"


def load_settings(**kwargs: str) -> Settings:
    return Settings(**kwargs)
