import pytest

from reddit_digest.config import SecretsConfig, load_config


def test_load_config_from_yaml(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
reddit:
  subreddits: ["python", "rust"]
  sort: "top"
  limit: 10
  time_filter: "week"

llm:
  base_url: "http://localhost:1234/v1"
  model: "local-model"

telegram:
  chat_id: "42"

digest:
  schedule: "09:00"
  timezone: "UTC"
  language: "en"
"""
    )
    config = load_config(cfg_file)
    assert config.reddit.subreddits == ["python", "rust"]
    assert config.reddit.sort == "top"
    assert config.reddit.limit == 10
    assert config.llm.base_url == "http://localhost:1234/v1"
    assert config.telegram.chat_id == "42"
    assert config.digest.language == "en"


def test_load_config_defaults(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        """
reddit:
  subreddits: ["python"]
telegram:
  chat_id: "1"
"""
    )
    config = load_config(cfg_file)
    assert config.reddit.sort == "hot"
    assert config.reddit.limit == 20
    assert config.llm.model == "gpt-4o-mini"
    assert config.digest.schedule == "08:00"
    assert config.digest.language == "fr"


def test_load_config_missing_required(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("llm:\n  model: foo\n")
    with pytest.raises(Exception):
        load_config(cfg_file)


def test_secrets_from_env(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id123")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret456")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "bot:token")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    secrets = SecretsConfig()
    assert secrets.reddit_client_id == "id123"
    assert secrets.reddit_client_secret == "secret456"
    assert secrets.telegram_bot_token == "bot:token"
    assert secrets.llm_api_key == "sk-test"
    assert secrets.reddit_user_agent == "reddit-digest-agent"


def test_secrets_missing_required(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(Exception):
        SecretsConfig(_env_file=None)
