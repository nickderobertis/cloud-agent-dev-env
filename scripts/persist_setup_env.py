#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

TOKEN_ENV_NAMES = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_PAT",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
)
PERSISTED_ENV_RELATIVE_PATHS = (
    Path(".env"),
    Path(".git") / "cloud-agent-dev-env.env",
)


def is_codex_cloud(env: Mapping[str, str]) -> bool:
    return bool(env.get("CODEX_CI") or env.get("CODEX_THREAD_ID"))


def persistence_enabled(env: Mapping[str, str]) -> bool:
    return env.get("CLOUD_AGENT_DEV_ENV_PERSIST_GITHUB_TOKEN", "1").lower() not in {
        "0",
        "false",
        "no",
    }


def github_token(env: Mapping[str, str]) -> str | None:
    for name in TOKEN_ENV_NAMES:
        value = env.get(name)
        if value:
            return value
    return None


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def is_token_line(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("export "):
        stripped = stripped.removeprefix("export ").lstrip()
    return any(stripped.startswith(f"{name}=") for name in TOKEN_ENV_NAMES)


def write_env_file(path: Path, token: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    kept = [line for line in lines if not is_token_line(line)]
    kept.append(f"GH_TOKEN={shell_quote(token)}")

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    old_umask = os.umask(0o177)
    try:
        tmp_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
        tmp_path.chmod(0o600)
        tmp_path.replace(path)
        path.chmod(0o600)
    finally:
        os.umask(old_umask)
        if tmp_path.exists():
            tmp_path.unlink()


def persisted_env_paths(root: Path) -> tuple[Path, ...]:
    return tuple(root / rel for rel in PERSISTED_ENV_RELATIVE_PATHS)


def persist_github_token(root: Path, env: Mapping[str, str]) -> bool:
    if not is_codex_cloud(env) or not persistence_enabled(env):
        return False

    token = github_token(env)
    if not token:
        return False
    if "\n" in token or "\r" in token:
        raise RuntimeError("refusing to persist multiline GitHub token")

    for path in persisted_env_paths(root):
        write_env_file(path, token)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    persist_github_token(Path(args.repo_root).resolve(), os.environ)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
