# Helm Chart & Release Workflow Restructuration

## Context

reddit-digest-agent is deployed as a Docker image on GHCR. The current `docker.yml` workflow handles both PR build validation and release (tag + Docker push + GitHub release) in a single workflow. We need to:

1. Create a Helm chart for Kubernetes deployment
2. Rename `docker.yml` to `release.yml` and restructure it into four chained jobs
3. Move the PR Docker build job into `ci.yml`

## Helm Chart

### Structure

```
charts/reddit-digest-agent/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── _helpers.tpl
    ├── deployment.yaml
    ├── pvc.yaml
    ├── secret.yaml
    ├── configmap.yaml
    └── serviceaccount.yaml
```

### Design Decisions

- **Single replica**: the agent is a singleton with an internal APScheduler-based scheduler. No horizontal scaling.
- **No Service/Ingress**: the app does not expose HTTP ports — it pushes digests to Telegram.
- **PVC for SQLite**: `storageClassName` configurable, default `1Gi`, mounted at `/data` with `DB_PATH=/data/digest.db`.
- **Secrets**: dual mode — either the chart creates a Secret from values (`secret.create=true`) or references an existing external Secret (`secret.existingSecret`). Sensitive keys: `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- **ConfigMap**: all non-sensitive env vars (`REDDIT_SUBREDDITS`, `DIGEST_CRON`, `LLM_MODEL`, etc.).
- **ServiceAccount**: optional, `create: true` by default.

### values.yaml

```yaml
image:
  repository: ghcr.io/using-system/reddit-digest-agent
  tag: ""          # defaults to appVersion from Chart.yaml
  pullPolicy: IfNotPresent

serviceAccount:
  create: true
  name: ""

config:
  REDDIT_SUBREDDITS: '["python","machinelearning","selfhosted"]'
  REDDIT_SORT: hot
  REDDIT_LIMIT: "5"
  REDDIT_TIME_FILTER: day
  DIGEST_CRON: "0 8 * * *"
  DIGEST_LANGUAGE: fr
  OPENAI_BASE_URL: https://openrouter.ai/api/v1
  LLM_MODEL: google/gemini-2.5-flash

secret:
  create: false
  existingSecret: ""
  values:
    OPENAI_API_KEY: ""
    TELEGRAM_BOT_TOKEN: ""
    TELEGRAM_CHAT_ID: ""

persistence:
  storageClassName: ""
  size: 1Gi
  accessModes:
    - ReadWriteOnce

resources: {}
nodeSelector: {}
tolerations: []
affinity: {}
```

## Workflow Restructuration

### CI Workflow (ci.yml)

Add the Docker build validation job (PR only):

```yaml
docker-build:
  if: github.event_name == 'pull_request'
  runs-on: ubuntu-latest
  permissions:
    contents: read
  steps:
    - uses: actions/checkout@v6
    - name: Set up QEMU
      uses: docker/setup-qemu-action@v3
    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3
    - name: Build (no push)
      uses: docker/build-push-action@v6
      with:
        context: .
        push: false
        platforms: linux/amd64,linux/arm64
```

### Release Workflow (docker.yml → release.yml)

Renamed from `Docker` to `Release`. Triggered only on `push` to `main`. Four chained jobs:

```
version → docker → helm → release
         ↘              ↗
          └──────────────┘
```

| Job | Depends on | Role |
|-----|-----------|------|
| **version** | — | `mathieudutour/github-tag-action` creates semver tag, exposes `new_tag` output |
| **docker** | version | Login to GHCR, multi-arch build & push with semver + `latest` tags |
| **helm** | version | `helm package` with `--version` and `--app-version` set to the tag, then `helm push` to `oci://ghcr.io/using-system/charts/reddit-digest-agent` |
| **release** | docker, helm | `softprops/action-gh-release` with `generate_release_notes: true` |

Permissions at workflow level: `contents: write` + `packages: write`.

### Helm Push Job Details

```yaml
helm:
  needs: version
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v6
    - name: Set up Helm
      uses: azure/setup-helm@v4
    - name: Login to GHCR
      run: echo "${{ secrets.GITHUB_TOKEN }}" | helm registry login ghcr.io -u ${{ github.actor }} --password-stdin
    - name: Package chart
      run: |
        helm package charts/reddit-digest-agent \
          --version "${{ needs.version.outputs.new_version }}" \
          --app-version "${{ needs.version.outputs.new_version }}"
    - name: Push chart
      run: helm push reddit-digest-agent-*.tgz oci://ghcr.io/using-system/charts
```
