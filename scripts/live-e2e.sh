#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.cache/uv}"
export PATH="$ROOT/.local/bin:$PATH"

if [ "${CLOUD_AGENT_DEV_ENV_SKIP_ENV_FILE:-0}" != "1" ] && [ -f "$ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$ROOT/.env"
    set +a
fi

if [ "${CLOUD_AGENT_DEV_ENV_SKIP_TOOL_BOOTSTRAP:-0}" != "1" ]; then
    if command -v python3 >/dev/null 2>&1; then
        python3 "$ROOT/scripts/bootstrap_tools.py" --repo-root "$ROOT" --quiet
    fi
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "ERROR: gh is not installed and bootstrap did not install it." >&2
    exit 1
fi

if [ -z "${GH_TOKEN:-${GITHUB_TOKEN:-${GITHUB_PAT:-${GITHUB_PERSONAL_ACCESS_TOKEN:-}}}}" ]; then
    echo "ERROR: no GitHub token env var is set." >&2
    exit 1
fi

uv run cloud-agent-dev-env live-check --repo-root "$ROOT"
