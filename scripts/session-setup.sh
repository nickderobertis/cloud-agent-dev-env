#!/usr/bin/env bash
set -euo pipefail

if [ -n "${CI:-}" ] && [ "${CLOUD_AGENT_DEV_ENV_RUN_IN_CI:-0}" != "1" ]; then
    exit 0
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.cache/uv}"

if ! command -v uv >/dev/null 2>&1; then
    echo "WARNING: uv is required for session setup; install uv and rerun scripts/session-setup.sh" >&2
    exit 0
fi

uv run cloud-agent-dev-env setup --repo-root "$ROOT" --quiet --non-blocking "$@"
