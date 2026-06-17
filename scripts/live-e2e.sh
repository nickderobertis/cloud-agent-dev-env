#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.cache/uv}"

if [ -f "$ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$ROOT/.env"
    set +a
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "SKIP: gh is not installed."
    exit 0
fi

if [ -z "${GH_TOKEN:-${GITHUB_TOKEN:-${GITHUB_PAT:-${GITHUB_PERSONAL_ACCESS_TOKEN:-}}}}" ]; then
    echo "SKIP: no GitHub token env var is set."
    exit 0
fi

uv run cloud-agent-dev-env live-check --repo-root "$ROOT"
