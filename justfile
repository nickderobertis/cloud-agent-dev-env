set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

export UV_CACHE_DIR := env_var_or_default("UV_CACHE_DIR", justfile_directory() / ".cache/uv")

default:
    @just --list

bootstrap:
    uv sync --group dev

check: fmt-check lint typecheck test test-e2e lint-sh
    @echo "check: ok"

fmt-check:
    uv run ruff format --check .

format:
    uv run ruff format .
    shfmt -w scripts/*.sh .claude/hooks/*.sh .codex/hooks/*.sh

lint: lint-py lint-sh

lint-py:
    uv run ruff check .

lint-sh:
    if ! command -v shellcheck >/dev/null 2>&1; then echo "shellcheck not installed: brew install shellcheck / apt-get install shellcheck" >&2; exit 1; fi
    if ! command -v shfmt >/dev/null 2>&1; then echo "shfmt not installed: brew install shfmt / go install mvdan.cc/sh/v3/cmd/shfmt@latest" >&2; exit 1; fi
    shellcheck scripts/*.sh .claude/hooks/*.sh .codex/hooks/*.sh
    shfmt -d scripts/*.sh .claude/hooks/*.sh .codex/hooks/*.sh

typecheck:
    uv run ty check cloud_agent_dev_env

test:
    uv run pytest tests/unit

test-e2e:
    uv run pytest --no-cov tests/e2e

setup-session *ARGS:
    scripts/session-setup.sh {{ARGS}}

live-e2e:
    scripts/live-e2e.sh

secrets-sync:
    if ! command -v gh-secrets >/dev/null 2>&1; then echo "gh-secrets not installed." >&2; exit 1; fi
    gh-secrets sync

upgrade:
    uv lock --upgrade
    uv sync --group dev
    @just check

doctor:
    uv run cloud-agent-dev-env doctor

bootstrap-tools:
    python3 scripts/bootstrap_tools.py

setup-llmlint:
    scripts/setup-llmlint.sh

# Optional LLM-as-judge lint; non-deterministic and out of `check`.
lint-llm *paths:
    llmlint {{paths}}

# Deterministic llmlint config/ignore/version-bump validation.
lint-llm-validate *args:
    PATH="$HOME/.local/bin:$PATH" llmlint validate {{args}}

# llmlint scoped to changed files since the merge-base with main.
lint-llm-diff base="origin/main" *args:
    llmlint --diff --diff-base "{{base}}" {{args}}
