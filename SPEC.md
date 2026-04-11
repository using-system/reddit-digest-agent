# Reddit Digest Agent — Specification

Full design specs:
- [Initial design](docs/superpowers/specs/2026-04-09-reddit-digest-agent-design.md)
- [Compact digest redesign](docs/superpowers/specs/2026-04-11-compact-digest-design.md)

## Summary

A Python agent that daily collects top posts from configurable subreddits, filters them by Reddit metrics and LLM relevance scoring, summarizes them via an LLM (using post content and top comments), and delivers one compact message per subreddit to a Telegram channel. Users react via per-thread inline buttons; the system learns and adapts over time.

## Architecture

Two LangGraph graphs sharing SQLite state:

- **Digest Graph** (scheduled): Collector → Filterer → Scorer → Summarizer → Deliverer → Mark All Seen
- **Feedback Graph** (event-driven): Receive Reaction → Analyze → Update Preferences

## Stack

| Component | Choice |
|-----------|--------|
| Orchestration | LangChain + LangGraph |
| Package manager | uv |
| Reddit | curl_cffi (public JSON endpoints) |
| LLM | OpenAI-compatible API (generic) |
| Scheduler | APScheduler |
| Storage | SQLite |
| Telegram | python-telegram-bot |
| Config | Environment variables (.env) |
| Tests | pytest + pytest-asyncio |
