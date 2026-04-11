# Docker CI/CD Workflow Design

## Overview

A GitHub Actions workflow (`docker.yml`) that builds Docker images on PRs and, on merge to main, automatically determines the next semantic version from conventional commits, builds and pushes to ghcr.io, and creates a GitHub release.

## Triggers

| Event | Behavior |
|-------|----------|
| `pull_request` targeting `main` | Build only (no push) — validates the Dockerfile |
| `push` to `main` (merge) | Version bump + Build + Push to ghcr.io + GitHub Release |

## Jobs

### Job: `build` (PR only)

Runs on `pull_request` events. Validates that the Docker image builds successfully without pushing.

Steps:
1. `actions/checkout@v6`
2. `docker/setup-buildx-action` — set up Buildx
3. `docker/build-push-action` with `push: false` — build only

### Job: `release` (merge to main only)

Runs on `push` to `main`. Full release pipeline.

Steps:
1. `actions/checkout@v6` with `fetch-depth: 0` (full history for tag analysis)
2. **Version bump**: `mathieudutour/github-tag-action` — analyzes conventional commits since last tag, determines bump type (major/minor/patch), creates Git tag
3. `docker/setup-buildx-action` — set up Buildx
4. `docker/login-action` — login to ghcr.io using ephemeral `GITHUB_TOKEN`
5. `docker/metadata-action` — generates image tags from the new version: `X.Y.Z`, `X.Y`, `X`, `latest`
6. `docker/build-push-action` with `push: true` — build and push to `ghcr.io/using-system/reddit-digest-agent`
7. `softprops/action-gh-release` — creates GitHub release with auto-generated changelog from commits

## Authentication

- Uses the ephemeral `GITHUB_TOKEN` provided by the workflow run
- Workflow permissions: `contents: write` (for tags and releases), `packages: write` (for ghcr.io push)
- No additional secrets required

## Image Registry

- Registry: `ghcr.io`
- Image: `ghcr.io/using-system/reddit-digest-agent`
- Tag strategy: `X.Y.Z` + `X.Y` + `X` + `latest`

## Version Source of Truth

- Git tags are the single source of truth for versioning
- `pyproject.toml` version is not updated automatically
- First release will be `0.1.1` (or `0.2.0`/`1.0.0` depending on commit types after current `0.1.0` baseline)

## Actions Used

| Action | Version | Role |
|--------|---------|------|
| `actions/checkout` | v6 | Checkout code |
| `docker/setup-buildx-action` | v3 | Set up Docker Buildx |
| `docker/login-action` | v3 | Authenticate to ghcr.io |
| `docker/metadata-action` | v5 | Generate semver image tags |
| `docker/build-push-action` | v6 | Build and push Docker image |
| `mathieudutour/github-tag-action` | v6.2 | Conventional commit analysis + Git tag creation |
| `softprops/action-gh-release` | v2 | Create GitHub release |

## Decisions

- **No release-please**: user prefers automatic tag+release on every merge, no intermediate PR
- **No pyproject.toml bump**: Git tags are the sole version source
- **Ephemeral token only**: no PAT or custom secrets needed for ghcr.io on same-repo packages
