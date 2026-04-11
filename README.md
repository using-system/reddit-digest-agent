# reddit-digest-agent

An AI-powered agent that delivers a daily digest of Reddit's top posts to your Telegram channel. It summarizes content in your language, and learns your preferences over time through reaction buttons.

## What it does

- Collects top posts from configurable subreddits on a cron schedule
- Summarizes each post using any OpenAI-compatible LLM (OpenAI, LocalAI, OpenRouter, etc.)
- Sends summaries to Telegram with inline reaction buttons
- Learns from your feedback to filter future content

## Prerequisites

### Usage

- Docker (or any OCI-compatible runtime)
- A [Telegram Bot](https://core.telegram.org/bots#botfather) token + your chat ID
- Access to an OpenAI-compatible LLM API

### Development

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

## Quick start

### Docker (recommended)

Pre-built images are published to the GitHub Container Registry after each merge to `main`:

```
ghcr.io/using-system/reddit-digest-agent
```

Available tags follow semantic versioning:

| Tag | Description |
|-----|-------------|
| `latest` | Most recent release |
| `X.Y.Z` (e.g. `1.2.3`) | Exact version |
| `X.Y` (e.g. `1.2`) | Latest patch for a minor version |
| `X` (e.g. `1`) | Latest minor+patch for a major version |

```bash
docker pull ghcr.io/using-system/reddit-digest-agent:latest
cp .env.example .env
# Edit .env with your credentials
docker run -d --env-file .env --name reddit-digest ghcr.io/using-system/reddit-digest-agent:latest
```

### From source

```bash
git clone https://github.com/using-system/reddit-digest-agent.git
cd reddit-digest-agent
uv sync
cp .env.example .env
# Edit .env with your credentials
uv run python -m reddit_digest.main
```

To run a single digest immediately (no scheduler, no bot):

```bash
uv run python -m reddit_digest.main --once
```

## Telegram setup

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`, choose a name and a username ending with `bot`
3. Copy the token — this is your `TELEGRAM_BOT_TOKEN`
4. Create a **new private channel** (new message > New Channel)
5. Go to channel settings > **Administrators** > **Add Administrator**, search for your bot and confirm
6. Send any message in the channel, then run:
   ```bash
   curl https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
7. In the JSON response, find `"chat":{"id":-100...}` — this negative number is your `TELEGRAM_CHAT_ID`

> If `getUpdates` returns empty results, remove and re-add the bot as admin, send a new message, and retry.

## Configuration

All configuration is done via environment variables (`.env` file).

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDDIT_SUBREDDITS` | no | `["python","machinelearning","selfhosted"]` | JSON list of subreddits |
| `REDDIT_SORT` | no | `hot` | Sort method: `hot`, `top`, `rising`, `new` |
| `REDDIT_LIMIT` | no | `20` | Max posts per subreddit |
| `REDDIT_TIME_FILTER` | no | `day` | Time filter for `top` sort |
| `OPENAI_API_KEY` | yes | | API key for the LLM provider |
| `OPENAI_BASE_URL` | no | `https://openrouter.ai/api/v1` | OpenAI-compatible API endpoint |
| `LLM_MODEL` | no | `google/gemini-2.5-flash` | Model name |
| `TELEGRAM_BOT_TOKEN` | yes | | Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | yes | | Target chat/channel ID |
| `REDDIT_FETCH_DELAY` | no | `200` | Delay in ms between Reddit API calls |
| `TELEGRAM_SEND_DELAY` | no | `500` | Delay in ms between Telegram messages |
| `DB_PATH` | no | `~/.local/share/reddit-digest/digest.db` | SQLite database path |
| `DIGEST_CRON` | no | `0 8 * * *` | Cron expression for digest schedule |
| `DIGEST_LANGUAGE` | no | `fr` | Summary language |

## Deploy with Docker

```bash
docker build -t reddit-digest-agent .
docker run -d --env-file .env --name reddit-digest reddit-digest-agent
```

## Development

```bash
uv sync --all-extras          # install with dev deps
uv run pytest                 # run tests (44 tests)
uv run ruff check src/ tests/ # lint
uv run ruff format src/ tests/ # format
```

## License

Apache 2.0
