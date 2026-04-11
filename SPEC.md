# Reddit Digest Agent — Specification

Full design spec: [docs/superpowers/specs/2026-04-09-reddit-digest-agent-design.md](docs/superpowers/specs/2026-04-09-reddit-digest-agent-design.md)

## Summary

A Python agent that daily collects top posts from configurable subreddits, summarizes them via an LLM, and delivers them to a Telegram channel. Users react via inline buttons; the system learns and adapts over time.

## Architecture

Two LangGraph graphs sharing SQLite state:

- **Digest Graph** (scheduled): Collector → Filterer → Summarizer → Deliverer
- **Feedback Graph** (event-driven): Receive Reaction → Analyze → Update Preferences

## Stack

| Component | Choice |
|-----------|--------|
| Orchestration | LangChain + LangGraph |
| Package manager | uv |
| Reddit | asyncpraw |
| LLM | OpenAI-compatible API (generic) |
| Scheduler | APScheduler |
| Storage | SQLite |
| Telegram | python-telegram-bot |
| Config | Environment variables (.env) |
| Tests | pytest + pytest-asyncio |
