#!/usr/bin/env bash
set -euo pipefail

if [ -n "${CI:-}" ] && [ "${CLOUD_AGENT_DEV_ENV_RUN_IN_CI:-0}" != "1" ]; then
    exit 0
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export CLOUD_AGENT_DEV_ENV_SETUP_CONTRACT="2026-06-17-gh-config-dir"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$ROOT/.cache/uv}"
export PATH="$ROOT/.local/bin:$PATH"
if [ -n "${CODEX_CI:-}" ]; then
    export GH_CONFIG_DIR="${GH_CONFIG_DIR:-$ROOT/.local/gh}"
fi

if [ "${CLOUD_AGENT_DEV_ENV_SKIP_TOOL_BOOTSTRAP:-0}" != "1" ]; then
    if command -v python3 >/dev/null 2>&1; then
        python3 "$ROOT/scripts/bootstrap_tools.py" --repo-root "$ROOT" --quiet || {
            echo "WARNING: tool bootstrap failed; continuing with available tools" >&2
        }
    else
        echo "WARNING: python3 is required to install missing tools automatically" >&2
    fi
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "WARNING: uv is required for session setup; install uv and rerun scripts/session-setup.sh" >&2
    exit 0
fi

uv run cloud-agent-dev-env setup --repo-root "$ROOT" --quiet --install-missing --non-blocking "$@"
