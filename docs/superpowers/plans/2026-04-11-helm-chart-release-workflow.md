# Helm Chart & Release Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Helm chart for Kubernetes deployment and restructure CI/release workflows into clean, separated concerns.

**Architecture:** Helm chart under `charts/reddit-digest-agent/` with ConfigMap, Secret (dual-mode), PVC, Deployment, and ServiceAccount. Workflows split: CI handles PR validation (lint, test, docker build), Release handles tag + docker push + helm push + GitHub release as four chained jobs.

**Tech Stack:** Helm 3, GitHub Actions, GHCR (OCI registry), `mathieudutour/github-tag-action`, `softprops/action-gh-release`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `charts/reddit-digest-agent/Chart.yaml` | Chart metadata and version |
| Create | `charts/reddit-digest-agent/values.yaml` | Default configuration values |
| Create | `charts/reddit-digest-agent/templates/_helpers.tpl` | Template helper functions |
| Create | `charts/reddit-digest-agent/templates/configmap.yaml` | Non-sensitive env vars |
| Create | `charts/reddit-digest-agent/templates/secret.yaml` | Sensitive env vars (optional) |
| Create | `charts/reddit-digest-agent/templates/pvc.yaml` | SQLite persistence |
| Create | `charts/reddit-digest-agent/templates/serviceaccount.yaml` | ServiceAccount (optional) |
| Create | `charts/reddit-digest-agent/templates/deployment.yaml` | Main workload |
| Modify | `.github/workflows/ci.yml` | Add `docker-build` job |
| Delete | `.github/workflows/docker.yml` | Replaced by `release.yml` |
| Create | `.github/workflows/release.yml` | version → docker → helm → release |

---

### Task 1: Chart.yaml and values.yaml

**Files:**
- Create: `charts/reddit-digest-agent/Chart.yaml`
- Create: `charts/reddit-digest-agent/values.yaml`

- [ ] **Step 1: Create Chart.yaml**

```yaml
apiVersion: v2
name: reddit-digest-agent
description: Agent-driven Reddit digest delivered to Telegram
type: application
version: 0.1.0
appVersion: "0.1.0"
```

- [ ] **Step 2: Create values.yaml**

```yaml
image:
  repository: ghcr.io/using-system/reddit-digest-agent
  tag: ""
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

- [ ] **Step 3: Commit**

```bash
git add charts/reddit-digest-agent/Chart.yaml charts/reddit-digest-agent/values.yaml
git commit -m "feat(helm): add Chart.yaml and values.yaml"
```

---

### Task 2: Template helpers

**Files:**
- Create: `charts/reddit-digest-agent/templates/_helpers.tpl`

- [ ] **Step 1: Create _helpers.tpl**

```gotemplate
{{/*
Expand the name of the chart.
*/}}
{{- define "reddit-digest-agent.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "reddit-digest-agent.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "reddit-digest-agent.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
app.kubernetes.io/name: {{ include "reddit-digest-agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "reddit-digest-agent.selectorLabels" -}}
app.kubernetes.io/name: {{ include "reddit-digest-agent.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Service account name
*/}}
{{- define "reddit-digest-agent.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "reddit-digest-agent.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
Secret name — either chart-created or user-provided
*/}}
{{- define "reddit-digest-agent.secretName" -}}
{{- if .Values.secret.create }}
{{- include "reddit-digest-agent.fullname" . }}
{{- else }}
{{- .Values.secret.existingSecret }}
{{- end }}
{{- end }}
```

- [ ] **Step 2: Commit**

```bash
git add charts/reddit-digest-agent/templates/_helpers.tpl
git commit -m "feat(helm): add template helpers"
```

---

### Task 3: ConfigMap and Secret templates

**Files:**
- Create: `charts/reddit-digest-agent/templates/configmap.yaml`
- Create: `charts/reddit-digest-agent/templates/secret.yaml`

- [ ] **Step 1: Create configmap.yaml**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "reddit-digest-agent.fullname" . }}
  labels:
    {{- include "reddit-digest-agent.labels" . | nindent 4 }}
data:
  {{- range $key, $value := .Values.config }}
  {{ $key }}: {{ $value | quote }}
  {{- end }}
```

- [ ] **Step 2: Create secret.yaml**

```yaml
{{- if .Values.secret.create }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "reddit-digest-agent.fullname" . }}
  labels:
    {{- include "reddit-digest-agent.labels" . | nindent 4 }}
type: Opaque
stringData:
  {{- range $key, $value := .Values.secret.values }}
  {{ $key }}: {{ $value | quote }}
  {{- end }}
{{- end }}
```

- [ ] **Step 3: Commit**

```bash
git add charts/reddit-digest-agent/templates/configmap.yaml charts/reddit-digest-agent/templates/secret.yaml
git commit -m "feat(helm): add ConfigMap and Secret templates"
```

---

### Task 4: PVC and ServiceAccount templates

**Files:**
- Create: `charts/reddit-digest-agent/templates/pvc.yaml`
- Create: `charts/reddit-digest-agent/templates/serviceaccount.yaml`

- [ ] **Step 1: Create pvc.yaml**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ include "reddit-digest-agent.fullname" . }}
  labels:
    {{- include "reddit-digest-agent.labels" . | nindent 4 }}
spec:
  accessModes:
    {{- toYaml .Values.persistence.accessModes | nindent 4 }}
  {{- if .Values.persistence.storageClassName }}
  storageClassName: {{ .Values.persistence.storageClassName | quote }}
  {{- end }}
  resources:
    requests:
      storage: {{ .Values.persistence.size }}
```

- [ ] **Step 2: Create serviceaccount.yaml**

```yaml
{{- if .Values.serviceAccount.create }}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "reddit-digest-agent.serviceAccountName" . }}
  labels:
    {{- include "reddit-digest-agent.labels" . | nindent 4 }}
{{- end }}
```

- [ ] **Step 3: Commit**

```bash
git add charts/reddit-digest-agent/templates/pvc.yaml charts/reddit-digest-agent/templates/serviceaccount.yaml
git commit -m "feat(helm): add PVC and ServiceAccount templates"
```

---

### Task 5: Deployment template

**Files:**
- Create: `charts/reddit-digest-agent/templates/deployment.yaml`

- [ ] **Step 1: Create deployment.yaml**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "reddit-digest-agent.fullname" . }}
  labels:
    {{- include "reddit-digest-agent.labels" . | nindent 4 }}
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      {{- include "reddit-digest-agent.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "reddit-digest-agent.selectorLabels" . | nindent 8 }}
    spec:
      serviceAccountName: {{ include "reddit-digest-agent.serviceAccountName" . }}
      containers:
        - name: {{ .Chart.Name }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          envFrom:
            - configMapRef:
                name: {{ include "reddit-digest-agent.fullname" . }}
            {{- if or .Values.secret.create .Values.secret.existingSecret }}
            - secretRef:
                name: {{ include "reddit-digest-agent.secretName" . }}
            {{- end }}
          env:
            - name: DB_PATH
              value: /data/digest.db
          volumeMounts:
            - name: data
              mountPath: /data
          {{- with .Values.resources }}
          resources:
            {{- toYaml . | nindent 12 }}
          {{- end }}
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: {{ include "reddit-digest-agent.fullname" . }}
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
```

- [ ] **Step 2: Validate chart with helm lint**

Run: `helm lint charts/reddit-digest-agent`
Expected: `1 chart(s) linted, 0 chart(s) failed`

- [ ] **Step 3: Validate template rendering**

Run: `helm template test charts/reddit-digest-agent --set secret.create=true --set secret.values.OPENAI_API_KEY=test --set secret.values.TELEGRAM_BOT_TOKEN=test --set secret.values.TELEGRAM_CHAT_ID=test`
Expected: renders all resources (Deployment, ConfigMap, Secret, PVC, ServiceAccount) without errors.

- [ ] **Step 4: Commit**

```bash
git add charts/reddit-digest-agent/templates/deployment.yaml
git commit -m "feat(helm): add Deployment template"
```

---

### Task 6: Move Docker build job to CI workflow

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add docker-build job to ci.yml**

Append the following job after the existing `test` job in `.github/workflows/ci.yml`:

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

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: move Docker build validation job to CI workflow"
```

---

### Task 7: Create release.yml and delete docker.yml

**Files:**
- Delete: `.github/workflows/docker.yml`
- Create: `.github/workflows/release.yml`

- [ ] **Step 1: Create release.yml with four chained jobs**

```yaml
name: Release

on:
  push:
    branches: [main]

permissions:
  contents: write
  packages: write

jobs:
  version:
    runs-on: ubuntu-latest
    outputs:
      new_tag: ${{ steps.tag.outputs.new_tag }}
      new_version: ${{ steps.tag.outputs.new_version }}
    steps:
      - uses: actions/checkout@v6
        with:
          fetch-depth: 0

      - name: Bump version and create tag
        id: tag
        uses: mathieudutour/github-tag-action@v6.2
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          default_bump: patch

  docker:
    needs: version
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - name: Set up QEMU
        uses: docker/setup-qemu-action@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to ghcr.io
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=semver,pattern={{version}},value=${{ needs.version.outputs.new_tag }}
            type=semver,pattern={{major}}.{{minor}},value=${{ needs.version.outputs.new_tag }}
            type=semver,pattern={{major}},value=${{ needs.version.outputs.new_tag }}
            type=raw,value=latest

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          platforms: linux/amd64,linux/arm64
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}

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

  release:
    needs: [version, docker, helm]
    runs-on: ubuntu-latest
    steps:
      - name: Create GitHub release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ needs.version.outputs.new_tag }}
          name: ${{ needs.version.outputs.new_tag }}
          generate_release_notes: true
```

- [ ] **Step 2: Delete docker.yml**

```bash
git rm .github/workflows/docker.yml
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "feat(ci): restructure release workflow with version, docker, helm, and release jobs"
```

---

### Task 8: Final validation

- [ ] **Step 1: Verify helm lint passes**

Run: `helm lint charts/reddit-digest-agent`
Expected: `1 chart(s) linted, 0 chart(s) failed`

- [ ] **Step 2: Verify helm template renders with external secret mode**

Run: `helm template test charts/reddit-digest-agent --set secret.existingSecret=my-secret`
Expected: no Secret resource rendered, Deployment has `secretRef` pointing to `my-secret`.

- [ ] **Step 3: Verify helm template renders with chart-created secret mode**

Run: `helm template test charts/reddit-digest-agent --set secret.create=true --set secret.values.OPENAI_API_KEY=k --set secret.values.TELEGRAM_BOT_TOKEN=t --set secret.values.TELEGRAM_CHAT_ID=c`
Expected: Secret resource rendered with the three keys, Deployment references it.

- [ ] **Step 4: Verify no leftover docker.yml**

Run: `ls .github/workflows/`
Expected: `ci.yml  release.yml` (no `docker.yml`)

- [ ] **Step 5: Squash-ready commit history check**

Run: `git log --oneline features/helm-chart-release --not main`
Expected: clean series of commits matching the tasks above.
