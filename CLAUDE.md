# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

reddit-digest-agent is a Python-based, agent-driven tool that collects top posts from selected Reddit communities and delivers a curated daily digest to Telegram. The architecture is a modular pipeline with decoupled stages: data sourcing, filtering, summarization, and delivery.

## Development Setup

- Package manager: uv
- Python >=3.11 (src layout: `src/reddit_digest/`)

## Development Commands

- `uv sync --all-extras` — install all dependencies
- `uv run pytest` — run all tests
- `uv run pytest -v --tb=short` — verbose test output
- `uv run ruff check src/ tests/` — lint
- `uv run python -m reddit_digest.main` — run the agent

## Architecture

Two LangGraph graphs (Digest + Feedback) sharing SQLite state.
See SPEC.md and `docs/superpowers/specs/` for full design spec.
