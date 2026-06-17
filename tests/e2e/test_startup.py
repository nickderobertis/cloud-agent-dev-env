from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_cmd(argv: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(ROOT / ".cache" / "uv")
    env["CLOUD_AGENT_DEV_ENV_SKIP_TOOL_BOOTSTRAP"] = "1"
    return subprocess.run(
        argv, cwd=cwd, env=env, text=True, capture_output=True, check=False
    )


def minimal_path(tmp_path: Path, *, tools: tuple[str, ...] = ()) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("bash", "dirname"):
        source = shutil.which(name)
        assert source is not None
        (bin_dir / name).symlink_to(source)
    for tool in tools:
        executable = bin_dir / tool
        executable.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        executable.chmod(0o755)
    return bin_dir


def run_live_e2e_with_path(path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": str(path),
        "UV_CACHE_DIR": str(ROOT / ".cache" / "uv"),
        "CLOUD_AGENT_DEV_ENV_SKIP_TOOL_BOOTSTRAP": "1",
        "CLOUD_AGENT_DEV_ENV_SKIP_ENV_FILE": "1",
    }
    return subprocess.run(
        [str(ROOT / "scripts" / "live-e2e.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_installed_cli_doctor_json() -> None:
    result = run_cmd(["uv", "run", "cloud-agent-dev-env", "doctor", "--json"])

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["repo_root"] == str(ROOT)
    assert payload["claude_settings"] is True
    assert payload["codex_hooks"] is True


def test_session_startup_dry_run_is_clean() -> None:
    result = run_cmd(["scripts/session-setup.sh", "--dry-run"])

    assert result.returncode == 0, result.stderr
    assert "ERROR" not in result.stderr


def test_live_e2e_fails_when_just_is_missing(tmp_path: Path) -> None:
    result = run_live_e2e_with_path(
        minimal_path(tmp_path, tools=("gh", "allowlister", "oneharness"))
    )

    assert result.returncode == 1
    assert "required tool(s) missing after bootstrap: just" in result.stderr


def test_live_e2e_fails_when_gh_is_missing(tmp_path: Path) -> None:
    result = run_live_e2e_with_path(
        minimal_path(tmp_path, tools=("just", "allowlister", "oneharness"))
    )

    assert result.returncode == 1
    assert "required tool(s) missing after bootstrap: gh" in result.stderr


def test_live_e2e_fails_when_token_is_missing(tmp_path: Path) -> None:
    result = run_live_e2e_with_path(
        minimal_path(tmp_path, tools=("just", "gh", "allowlister", "oneharness"))
    )

    assert result.returncode == 1
    assert "no GitHub token env var is set" in result.stderr


def test_local_skill_install_uses_real_gh_skill(tmp_path: Path) -> None:
    skills_repo = tmp_path / "skills-src"
    skill = skills_repo / "skills" / "bootstrap" / "demo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo skill for e2e.\n---\n# Demo\n",
        encoding="utf-8",
    )
    target = tmp_path / "target"
    target.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)

    result = run_cmd(
        [
            "uv",
            "run",
            "cloud-agent-dev-env",
            "install-skills",
            "--repo-root",
            str(target),
            "--skills-repo",
            str(skills_repo),
            "--agent",
            "codex",
            "--quiet",
        ],
        cwd=target,
    )

    assert result.returncode == 0, result.stderr
    assert (target / ".agents" / "skills" / "demo-skill" / "SKILL.md").is_file()
