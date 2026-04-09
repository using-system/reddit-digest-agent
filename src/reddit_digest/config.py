from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedditConfig(BaseModel):
    subreddits: list[str]
    sort: str = "hot"
    limit: int = 20
    time_filter: str = "day"


class LLMConfig(BaseModel):
    base_url: str = "http://localhost:8080/v1"
    model: str = "gpt-4o-mini"


class TelegramConfig(BaseModel):
    chat_id: str


class DigestConfig(BaseModel):
    schedule: str = "08:00"
    timezone: str = "Europe/Paris"
    language: str = "fr"


class AppConfig(BaseModel):
    reddit: RedditConfig
    llm: LLMConfig = LLMConfig()
    telegram: TelegramConfig
    digest: DigestConfig = DigestConfig()


class SecretsConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    reddit_client_id: str
    reddit_client_secret: str
    reddit_user_agent: str = "reddit-digest-agent"
    telegram_bot_token: str
    llm_api_key: str


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
    return AppConfig(**data)


def load_secrets(**kwargs: str) -> SecretsConfig:
    return SecretsConfig(**kwargs)
