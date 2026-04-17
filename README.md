# reddit-digest-agent

An AI-powered agent that delivers a daily digest of Reddit's top posts to your Telegram channel. It summarizes content in your language, and learns your preferences over time through reaction buttons.

## What it does

- Collects top posts from configurable subreddits on a cron schedule
- Filters by Reddit metrics (score, comment count) and LLM-based relevance scoring
- Summarizes each post in one sentence using any OpenAI-compatible LLM, informed by post content and top comments
- Sends one compact message per subreddit to Telegram with numbered threads and per-thread 👍/👎 buttons
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

### Helm (Kubernetes)

A Helm chart is published to the GitHub Container Registry alongside each release:

```bash
helm install reddit-digest oci://ghcr.io/using-system/charts/reddit-digest-agent --version <version>
```

Create a Kubernetes Secret with your credentials, then reference it:

```bash
kubectl create secret generic reddit-digest-secrets \
  --from-literal=OPENAI_API_KEY=<your-key> \
  --from-literal=TELEGRAM_BOT_TOKEN=<your-token> \
  --from-literal=TELEGRAM_CHAT_ID=<your-chat-id>

helm install reddit-digest oci://ghcr.io/using-system/charts/reddit-digest-agent \
  --set secret.existingSecret=reddit-digest-secrets \
  --set config.DIGEST_CRON="0 8 * * *" \
  --set config.DIGEST_LANGUAGE=en
```

See [`charts/reddit-digest-agent/values.yaml`](charts/reddit-digest-agent/values.yaml) for all available options.

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
| `REDDIT_LIMIT` | no | `5` | Max posts per subreddit (max 8) |
| `REDDIT_TIME_FILTER` | no | `day` | Time filter for `top` sort |
| `REDDIT_COMMENTS_LIMIT` | no | `5` | Top comments fetched per post (for summarization) |
| `REDDIT_MIN_SCORE` | no | `10` | Minimum Reddit score to keep a post |
| `REDDIT_MIN_COMMENTS` | no | `3` | Minimum comment count to keep a post |
| `OPENAI_API_KEY` | yes | | API key for the LLM provider |
| `OPENAI_BASE_URL` | no | `https://openrouter.ai/api/v1` | OpenAI-compatible API endpoint |
| `LLM_MODEL` | no | `google/gemma-3-12b-it` | Model name (see [benchmark results](benchmarks/README.md)) |
| `TELEGRAM_BOT_TOKEN` | yes | | Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | yes | | Target chat/channel ID |
| `REDDIT_FETCH_DELAY` | no | `200` | Delay in ms between Reddit API calls |
| `TELEGRAM_SEND_DELAY` | no | `500` | Delay in ms between Telegram messages |
| `DB_PATH` | no | `~/.local/share/reddit-digest/digest.db` | SQLite database path |
| `DIGEST_CRON` | no | `0 8 * * *` | Cron expression for digest schedule |
| `DIGEST_LANGUAGE` | no | `fr` | Summary language |

## Recommended model

Based on our [benchmark of 25 models](benchmarks/README.md), we recommend **`google/gemma-3-12b-it`** as the default LLM for self-hosted deployments:

| Model | Cost/run | JSON OK | Summary quality | Composite |
|-------|----------|---------|-----------------|-----------|
| google/gemma-3-27b-it | $0.0012 | 100% | 7.9/10 | 0.9819 |
| **google/gemma-3-12b-it** | **$0.0005** | **100%** | **7.9/10** | **0.9781** |
| openai/gpt-4o-mini | $0.0015 | 100% | 7.6/10 | 0.9746 |
| google/gemma-4-31b-it | $0.0016 | 100% | 8.0/10 | 0.9693 |

While `gemma-3-27b-it` tops the composite ranking, `gemma-3-12b-it` is the best self-hostable option: same summary quality (7.9/10), less than half the cost ($0.0005 vs $0.0012/run), 100% JSON reliability, and it runs on a single consumer GPU (12B parameters). It is the default value for `LLM_MODEL`.

See [benchmarks/README.md](benchmarks/README.md) for the full ranking and methodology.

## Observability (OpenTelemetry)

The agent supports optional [OpenTelemetry](https://opentelemetry.io/) instrumentation. When `OTEL_EXPORTER_OTLP_ENDPOINT` is set, traces and metrics are exported via OTLP. When unset, telemetry is completely disabled with zero overhead.

### Configuration

All configuration uses standard OpenTelemetry environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | no | _(unset = disabled)_ | OTLP collector endpoint (e.g. `http://localhost:4318`) |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | no | `http/protobuf` | Export protocol (`http/protobuf` or `grpc`) |
| `OTEL_EXPORTER_OTLP_HEADERS` | no | | Auth headers (e.g. `Authorization=Bearer xxx`) |
| `OTEL_SERVICE_NAME` | no | `reddit-digest-agent` | Service name in traces and metrics |
| `OTEL_RESOURCE_ATTRIBUTES` | no | | Additional resource attributes |

### GenAI traces (auto-instrumented)

LLM calls (scoring, summarization, feedback analysis) are automatically traced following the [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/), including:

- `gen_ai.operation.name`, `gen_ai.request.model`, `gen_ai.response.model`
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- `gen_ai.client.operation.duration`

### Pipeline traces

Each digest run produces a trace with spans for every pipeline stage:

`digest.run` → `digest.collector` → `digest.filterer` → `digest.scorer` → `digest.summarizer` → `digest.deliverer` → `digest.mark_all_seen`

Feedback reactions produce: `feedback.receive_reaction` → `feedback.analyze` → `feedback.update_preferences`

### Custom metrics

| Metric | Type | Unit | Description |
|--------|------|------|-------------|
| `reddit_digest.digest.runs` | Counter | | Digest runs (`status`: `success`/`error`) |
| `reddit_digest.digest.duration` | Histogram | `s` | Total digest run duration |
| `reddit_digest.reddit.posts.collected` | Counter | | Posts collected (`subreddit`) |
| `reddit_digest.reddit.posts.filtered` | Counter | | Posts retained after filtering |
| `reddit_digest.reddit.posts.scored` | Counter | | Posts retained after LLM scoring |
| `reddit_digest.reddit.fetch.duration` | Histogram | `s` | Reddit fetch duration per subreddit |
| `reddit_digest.telegram.messages.sent` | Counter | | Telegram messages sent (`subreddit`) |
| `reddit_digest.telegram.messages.errors` | Counter | | Telegram send errors |
| `reddit_digest.feedback.reactions` | Counter | | Reactions received (`reaction_type`: `like`/`dislike`) |
| `reddit_digest.feedback.preference_updates` | Counter | | Preference updates from feedback |

## Deploy agent with Docker

```bash
docker build -t reddit-digest-agent .
docker run -d --env-file .env --name reddit-digest reddit-digest-agent
```

## Deploy agent with Docker Compose

### Local LocalAI stack

A Docker Compose stack that runs the agent against a self-hosted [LocalAI](https://localai.io/) server preloading `google/gemma-3-4b-it`, so the digest can be produced without any external LLM provider. See [`docker-compose/localai-stack/`](docker-compose/localai-stack/) for setup instructions.

### Local observability stack

A full Docker Compose stack (OTel Collector, Tempo, Prometheus, Grafana, Phoenix) is available for local development. See [`docker-compose/observability-stack/`](docker-compose/observability-stack/) for setup instructions.

## Development

```bash
uv sync --all-extras          # install with dev deps
uv run pytest                 # run tests (59 tests)
uv run ruff check src/ tests/ # lint
uv run ruff format src/ tests/ # format
```

## License

Apache 2.0
