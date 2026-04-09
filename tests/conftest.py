import pytest

from reddit_digest.config import AppConfig, SecretsConfig
from reddit_digest.db import init_db


@pytest.fixture
async def db_conn():
    conn = await init_db(":memory:")
    yield conn
    await conn.close()


@pytest.fixture
def sample_config() -> AppConfig:
    return AppConfig(
        reddit={
            "subreddits": ["python", "machinelearning"],
            "sort": "hot",
            "limit": 10,
            "time_filter": "day",
        },
        llm={"base_url": "http://localhost:8080/v1", "model": "test-model"},
        telegram={"chat_id": "123"},
        digest={"schedule": "08:00", "timezone": "UTC", "language": "fr"},
    )


@pytest.fixture
def sample_secrets() -> SecretsConfig:
    return SecretsConfig(
        reddit_client_id="test-id",
        reddit_client_secret="test-secret",
        reddit_user_agent="test-agent",
        telegram_bot_token="bot:test-token",
        llm_api_key="sk-test",
        _env_file=None,
    )
