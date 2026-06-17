#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

TOKEN_ENV_NAMES = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_PAT",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
)
PERSISTED_REPO_ENV_RELATIVE_PATHS = (Path(".env"),)
PERSISTED_LOCAL_STATE_ENV_RELATIVE_PATH = (
    Path(".local") / "state" / "cloud-agent-dev-env.env"
)
SETUP_STATUS_RELATIVE_PATH = Path(".local") / "state" / "setup-env-status.txt"
PERSISTED_EXTERNAL_ENV_FILE = ".cloud-agent-dev-env.env"


def is_codex_cloud(env: Mapping[str, str]) -> bool:
    return bool(env.get("CODEX_CI") or env.get("CODEX_THREAD_ID"))


def is_session_setup(env: Mapping[str, str]) -> bool:
    return bool(env.get("CLOUD_AGENT_DEV_ENV_SETUP_CONTRACT"))


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


def persisted_env_paths(root: Path, env: Mapping[str, str]) -> tuple[Path, ...]:
    paths = [root / rel for rel in PERSISTED_REPO_ENV_RELATIVE_PATHS]
    paths.append(root / PERSISTED_LOCAL_STATE_ENV_RELATIVE_PATH)
    paths.append(root.parent / PERSISTED_EXTERNAL_ENV_FILE)
    home = env.get("HOME")
    if home:
        paths.append(Path(home).expanduser() / PERSISTED_EXTERNAL_ENV_FILE)

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(path)
    return tuple(deduped)


def write_status_file(root: Path, *, token_present: bool, persisted: bool) -> None:
    path = root / SETUP_STATUS_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            (
                "codex_cloud_setup_token_persistence=1",
                f"github_token_present={'yes' if token_present else 'no'}",
                f"github_token_persisted={'yes' if persisted else 'no'}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    path.chmod(0o644)


def should_persist(env: Mapping[str, str]) -> bool:
    return persistence_enabled(env) and (is_codex_cloud(env) or is_session_setup(env))


def persist_github_token(root: Path, env: Mapping[str, str]) -> bool:
    if not should_persist(env):
        return False

    token = github_token(env)
    if not token:
        write_status_file(root, token_present=False, persisted=False)
        return False
    if "\n" in token or "\r" in token:
        raise RuntimeError("refusing to persist multiline GitHub token")

    for path in persisted_env_paths(root, env):
        write_env_file(path, token)
    write_status_file(root, token_present=True, persisted=True)
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    persisted = persist_github_token(Path(args.repo_root).resolve(), os.environ)
    if should_persist(os.environ) and not persisted:
        print(
            "WARNING: no supported GitHub token was present during setup; "
            "expected one of GH_TOKEN, GITHUB_TOKEN, GITHUB_PAT, or "
            "GITHUB_PERSONAL_ACCESS_TOKEN.",
            file=sys.stderr,
            flush=True,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
