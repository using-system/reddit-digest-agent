# reddit-digest-agent Helm Chart

A Helm chart for deploying [reddit-digest-agent](https://github.com/using-system/reddit-digest-agent) on Kubernetes — an AI-powered agent that delivers daily Reddit digests to Telegram.

## Installation

```bash
helm install reddit-digest oci://ghcr.io/using-system/charts/reddit-digest-agent --version <version>
```

## Prerequisites

- Kubernetes 1.24+
- Helm 3.8+ (OCI registry support)
- A [Telegram Bot](https://core.telegram.org/bots#botfather) token + chat ID
- Access to an OpenAI-compatible LLM API

## Configuration

### Secrets

The chart supports two modes for managing sensitive values (`OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`):

**Option A — External Secret (recommended for production):**

Create the Secret manually (or via Sealed Secrets, External Secrets Operator, etc.), then reference it:

```bash
kubectl create secret generic reddit-digest-secrets \
  --from-literal=OPENAI_API_KEY=<your-key> \
  --from-literal=TELEGRAM_BOT_TOKEN=<your-token> \
  --from-literal=TELEGRAM_CHAT_ID=<your-chat-id>

helm install reddit-digest oci://ghcr.io/using-system/charts/reddit-digest-agent \
  --set secret.existingSecret=reddit-digest-secrets
```

**Option B — Chart-managed Secret (quick setup):**

```bash
helm install reddit-digest oci://ghcr.io/using-system/charts/reddit-digest-agent \
  --set secret.create=true \
  --set secret.values.OPENAI_API_KEY=<your-key> \
  --set secret.values.TELEGRAM_BOT_TOKEN=<your-token> \
  --set secret.values.TELEGRAM_CHAT_ID=<your-chat-id>
```

### Application settings

Non-sensitive configuration is stored in a ConfigMap. Override any value with `--set config.<KEY>=<value>`:

```bash
helm install reddit-digest oci://ghcr.io/using-system/charts/reddit-digest-agent \
  --set secret.existingSecret=reddit-digest-secrets \
  --set config.DIGEST_CRON="0 9 * * *" \
  --set config.DIGEST_LANGUAGE=en \
  --set 'config.REDDIT_SUBREDDITS=["python"\,"rust"\,"devops"]'
```

### Extra environment variables

Use `extraEnv` to inject any additional environment variable into the pod without modifying the chart. This is useful for OpenTelemetry, rate limiting, or any future setting:

```bash
helm install reddit-digest oci://ghcr.io/using-system/charts/reddit-digest-agent \
  --set secret.existingSecret=reddit-digest-secrets \
  --set extraEnv.OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318 \
  --set extraEnv.OTEL_SERVICE_NAME=reddit-digest-agent
```

All keys in `extraEnv` are merged into the same ConfigMap as `config` values.

### Persistence

The agent uses SQLite for state. A PersistentVolumeClaim is created automatically:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `persistence.size` | `1Gi` | Storage size |
| `persistence.storageClassName` | `""` (cluster default) | StorageClass to use |
| `persistence.accessModes` | `[ReadWriteOnce]` | PVC access modes |

### All values

| Parameter | Default | Description |
|-----------|---------|-------------|
| `image.repository` | `ghcr.io/using-system/reddit-digest-agent` | Container image |
| `image.tag` | `""` (uses `appVersion`) | Image tag override |
| `image.pullPolicy` | `IfNotPresent` | Pull policy |
| `nameOverride` | `""` | Override chart name |
| `fullnameOverride` | `""` | Override full release name |
| `serviceAccount.create` | `true` | Create a ServiceAccount |
| `serviceAccount.name` | `""` | ServiceAccount name override |
| `config.REDDIT_SUBREDDITS` | `'["python","machinelearning","selfhosted"]'` | Subreddits to monitor |
| `config.REDDIT_SORT` | `hot` | Sort method |
| `config.REDDIT_LIMIT` | `5` | Max posts per subreddit |
| `config.REDDIT_TIME_FILTER` | `day` | Time filter for top sort |
| `config.DIGEST_CRON` | `0 8 * * *` | Cron schedule |
| `config.DIGEST_LANGUAGE` | `fr` | Summary language |
| `config.OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | LLM API endpoint |
| `config.LLM_MODEL` | `google/gemini-2.5-flash` | LLM model name |
| `secret.create` | `false` | Create Secret from values |
| `secret.existingSecret` | `""` | Name of existing Secret |
| `secret.values.OPENAI_API_KEY` | `""` | LLM API key |
| `secret.values.TELEGRAM_BOT_TOKEN` | `""` | Telegram bot token |
| `secret.values.TELEGRAM_CHAT_ID` | `""` | Telegram chat ID |
| `extraEnv` | `{}` | Additional env vars merged into the ConfigMap |
| `resources` | `{}` | CPU/memory requests and limits |
| `nodeSelector` | `{}` | Node selector constraints |
| `tolerations` | `[]` | Pod tolerations |
| `affinity` | `{}` | Pod affinity rules |

## Architecture

The chart deploys a single-replica Deployment (no horizontal scaling — the agent uses an internal scheduler). There is no Service or Ingress since the agent pushes digests to Telegram and does not expose HTTP endpoints.

```
Deployment (1 replica)
├── ConfigMap (non-sensitive env vars)
├── Secret (API keys, tokens)
├── PVC (SQLite database)
└── ServiceAccount
```

## Uninstalling

```bash
helm uninstall reddit-digest
```

Note: the PVC is not deleted automatically. To remove it:

```bash
kubectl delete pvc reddit-digest-reddit-digest-agent
```
