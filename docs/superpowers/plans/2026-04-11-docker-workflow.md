# Docker CI/CD Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a GitHub Actions workflow that builds Docker on PRs and auto-releases (tag + ghcr.io push + GitHub release) on merge to main using conventional commits.

**Architecture:** Single workflow file with two jobs — `build` (PR-only, no push) and `release` (main-only, full pipeline). Version is computed from conventional commits via `mathieudutour/github-tag-action`. Docker image is pushed to ghcr.io with semver tags via the standard docker/* action suite.

**Tech Stack:** GitHub Actions, Docker Buildx, ghcr.io, mathieudutour/github-tag-action, softprops/action-gh-release

---

### Task 1: Create the Docker workflow file

**Files:**
- Create: `.github/workflows/docker.yml`

- [ ] **Step 1: Create the workflow file with both jobs**

```yaml
name: Docker

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: write
  packages: write

jobs:
  build:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Build (no push)
        uses: docker/build-push-action@v6
        with:
          context: .
          push: false

  release:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
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
            type=semver,pattern={{version}},value=${{ steps.tag.outputs.new_tag }}
            type=semver,pattern={{major}}.{{minor}},value=${{ steps.tag.outputs.new_tag }}
            type=semver,pattern={{major}},value=${{ steps.tag.outputs.new_tag }}
            type=raw,value=latest

      - name: Build and push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}

      - name: Create GitHub release
        uses: softprops/action-gh-release@v2
        with:
          tag_name: ${{ steps.tag.outputs.new_tag }}
          name: ${{ steps.tag.outputs.new_tag }}
          body: ${{ steps.tag.outputs.changelog }}
          generate_release_notes: false
```

- [ ] **Step 2: Validate YAML syntax**

Run: `python3 -c "import yaml, sys; yaml.safe_load(open(sys.argv[1]))" .github/workflows/docker.yml && echo "YAML OK"`
Expected: `YAML OK`

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/docker.yml
git commit -m "feat(ci): add Docker build/release workflow

Build-only on PR, auto-tag + ghcr.io push + GitHub release on merge to main."
```

### Task 2: Commit the spec and plan docs

**Files:**
- Stage: `docs/superpowers/specs/2026-04-11-docker-workflow-design.md`
- Stage: `docs/superpowers/plans/2026-04-11-docker-workflow.md`

- [ ] **Step 1: Commit docs**

```bash
git add docs/superpowers/specs/2026-04-11-docker-workflow-design.md docs/superpowers/plans/2026-04-11-docker-workflow.md
git commit -m "docs(ci): add Docker workflow design spec and implementation plan"
```
