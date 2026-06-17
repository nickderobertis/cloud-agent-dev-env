#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.cache/uv}"
export PATH="$ROOT/.local/bin:$PATH"
if [ -n "${CODEX_CI:-}${CODEX_THREAD_ID:-}" ]; then
    export GH_CONFIG_DIR="${GH_CONFIG_DIR:-$ROOT/.local/gh}"
fi

if [ "${CLOUD_AGENT_DEV_ENV_SKIP_ENV_FILE:-0}" != "1" ] && [ -f "$ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$ROOT/.env"
    set +a
fi

if [ "${CLOUD_AGENT_DEV_ENV_SKIP_TOOL_BOOTSTRAP:-0}" != "1" ]; then
    if command -v python3 >/dev/null 2>&1; then
        python3 "$ROOT/scripts/bootstrap_tools.py" --repo-root "$ROOT" --quiet
    else
        echo "ERROR: python3 is required to bootstrap missing tools." >&2
        exit 1
    fi
fi

missing_tools=()
for tool in just gh allowlister oneharness; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        missing_tools+=("$tool")
    fi
done

if [ "${#missing_tools[@]}" -gt 0 ]; then
    echo "ERROR: required tool(s) missing after bootstrap: ${missing_tools[*]}" >&2
    exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv is required for live e2e." >&2
    exit 1
fi

just --list >/dev/null
uv run cloud-agent-dev-env setup --repo-root "$ROOT" --quiet --install-missing
uv run cloud-agent-dev-env live-check --repo-root "$ROOT"
