# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

reddit-digest-agent is a Python-based, agent-driven tool that collects top posts from selected Reddit communities and delivers a curated daily digest to Telegram. The architecture is a modular pipeline with decoupled stages: data sourcing, filtering, summarization, and delivery.

## Development Setup

- Package manager: uv
- Python >=3.11 (src layout: `src/reddit_digest/`)
- Configuration: all via environment variables (`.env` file). See `.env.example` for reference.

## Development Commands

- `uv sync --all-extras` — install all dependencies
- `uv run pytest` — run all tests
- `uv run pytest -v --tb=short` — verbose test output
- `uv run ruff check src/ tests/` — lint
- `uv run ruff format src/ tests/` — format
- `uv run python -m reddit_digest.main` — run the agent (scheduler + Telegram bot)
- `uv run python -m reddit_digest.main --once` — run a single digest and exit

## Architecture

Two LangGraph graphs (Digest + Feedback) sharing SQLite state.
Single `Settings` class (pydantic-settings) loads all config from env vars.
Reddit data is fetched via public JSON endpoints (no API credentials needed).
Default LLM provider is OpenRouter (configurable to OpenAI, Ollama, LocalAI).
Scheduling uses a crontab expression (`DIGEST_CRON`).
See SPEC.md and `docs/superpowers/specs/` for full design spec.

## Commit Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/) with semantic versioning in mind:
- `feat:` — new feature (bumps MINOR)
- `fix:` — bug fix (bumps PATCH)
- `docs:` — documentation only
- `chore:` — maintenance, dependencies, CI
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `test:` — adding or updating tests
- `perf:` — performance improvement
- Append `!` after the type (e.g. `feat!:`) for breaking changes (bumps MAJOR)

Format: `<type>(<scope>): <description>` — always try to include a scope (e.g. `feat(digest):`, `fix(telegram):`, `chore(ci):`)

## Post-Commit Workflow

After each commit:
1. Push the branch to the remote
2. Create a PR if one does not already exist for the current branch
3. Update the PR title and description to reflect all changes on the branch (always in English)
4. Monitor the CI workflow run triggered by the push (`gh run watch`) and report the result
