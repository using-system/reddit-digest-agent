import pytest

from reddit_digest.config import Settings
from reddit_digest.db import init_db


@pytest.fixture
async def db_conn():
    conn = await init_db(":memory:")
    yield conn
    await conn.close()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        reddit_client_id="test-id",
        reddit_client_secret="test-secret",
        reddit_user_agent="test-agent",
        reddit_subreddits=["python", "machinelearning"],
        reddit_sort="hot",
        reddit_limit=10,
        reddit_time_filter="day",
        llm_api_key="sk-test",
        llm_base_url="https://openrouter.ai/api/v1",
        llm_model="test-model",
        telegram_bot_token="bot:test-token",
        telegram_chat_id="123",
        digest_cron="0 8 * * *",
        digest_language="fr",
        _env_file=None,
    )
