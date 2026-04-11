import pytest

from reddit_digest.config import Settings


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot:token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    s = Settings(_env_file=None)
    assert s.telegram_bot_token == "bot:token"
    assert s.telegram_chat_id == "42"
    assert s.openai_api_key == "sk-test"


def test_settings_defaults(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot:t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    s = Settings(_env_file=None)
    assert s.reddit_sort == "hot"
    assert s.reddit_limit == 20
    assert s.llm_model == "google/gemini-2.5-flash"
    assert s.digest_cron == "0 8 * * *"
    assert s.digest_language == "fr"


def test_settings_subreddits_from_env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot:t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("REDDIT_SUBREDDITS", '["rust", "golang"]')
    s = Settings(_env_file=None)
    assert s.reddit_subreddits == ["rust", "golang"]


def test_settings_missing_required(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_settings_cron_expression(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot:t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk")
    monkeypatch.setenv("DIGEST_CRON", "30 9 * * 1-5")
    s = Settings(_env_file=None)
    assert s.digest_cron == "30 9 * * 1-5"
