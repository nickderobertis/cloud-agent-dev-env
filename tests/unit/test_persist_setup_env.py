from __future__ import annotations

import importlib.util
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "persist_setup_env", ROOT / "scripts" / "persist_setup_env.py"
)
assert SPEC is not None
persist_setup_env = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(persist_setup_env)


def test_persist_github_token_writes_ignored_env_file(tmp_path: Path) -> None:
    env = {"CODEX_CI": "1", "GH_TOKEN": "ghp_secret"}

    wrote = persist_setup_env.persist_github_token(tmp_path, env)

    env_file = tmp_path / ".env"
    assert wrote is True
    assert env_file.read_text(encoding="utf-8") == "GH_TOKEN='ghp_secret'\n"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_persist_github_token_replaces_existing_token_lines(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PLAIN=value\nGH_TOKEN='old'\nexport GITHUB_PAT=old_pat\n",
        encoding="utf-8",
    )

    persist_setup_env.persist_github_token(
        tmp_path, {"CODEX_THREAD_ID": "thread", "GITHUB_PAT": "new_pat"}
    )

    assert env_file.read_text(encoding="utf-8") == ("PLAIN=value\nGH_TOKEN='new_pat'\n")


def test_persist_github_token_skips_non_cloud_and_disabled(tmp_path: Path) -> None:
    assert (
        persist_setup_env.persist_github_token(tmp_path, {"GH_TOKEN": "secret"})
        is False
    )
    assert (
        persist_setup_env.persist_github_token(
            tmp_path,
            {
                "CODEX_CI": "1",
                "GH_TOKEN": "secret",
                "CLOUD_AGENT_DEV_ENV_PERSIST_GITHUB_TOKEN": "0",
            },
        )
        is False
    )
    assert not (tmp_path / ".env").exists()
