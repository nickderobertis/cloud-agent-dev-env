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


def test_persist_github_token_writes_agent_phase_env_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {"CODEX_CI": "1", "GH_TOKEN": "ghp_secret", "HOME": str(home)}

    wrote = persist_setup_env.persist_github_token(tmp_path, env)

    env_file = tmp_path / ".env"
    local_state_env_file = tmp_path / ".local" / "state" / "cloud-agent-dev-env.env"
    status_file = tmp_path / ".local" / "state" / "setup-env-status.txt"
    parent_env_file = tmp_path.parent / ".cloud-agent-dev-env.env"
    home_env_file = home / ".cloud-agent-dev-env.env"
    assert wrote is True
    assert env_file.read_text(encoding="utf-8") == "GH_TOKEN='ghp_secret'\n"
    assert local_state_env_file.read_text(encoding="utf-8") == (
        "GH_TOKEN='ghp_secret'\n"
    )
    assert parent_env_file.read_text(encoding="utf-8") == "GH_TOKEN='ghp_secret'\n"
    assert home_env_file.read_text(encoding="utf-8") == "GH_TOKEN='ghp_secret'\n"
    assert "github_token_persisted=yes" in status_file.read_text(encoding="utf-8")
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(local_state_env_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(parent_env_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(home_env_file.stat().st_mode) == 0o600


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
    assert (tmp_path / ".local" / "state" / "cloud-agent-dev-env.env").read_text(
        encoding="utf-8"
    ) == "GH_TOKEN='new_pat'\n"
    assert (tmp_path.parent / ".cloud-agent-dev-env.env").read_text(
        encoding="utf-8"
    ) == "GH_TOKEN='new_pat'\n"


def test_persist_github_token_writes_status_when_token_missing(tmp_path: Path) -> None:
    assert persist_setup_env.persist_github_token(tmp_path, {"CODEX_CI": "1"}) is False

    status = (tmp_path / ".local" / "state" / "setup-env-status.txt").read_text(
        encoding="utf-8"
    )
    assert "github_token_present=no" in status
    assert "github_token_persisted=no" in status


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
