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


def test_session_setup_skips_plain_ci(tmp_path: Path) -> None:
    marker = tmp_path / "uv-ran"
    bin_dir = minimal_path(tmp_path)
    uv = bin_dir / "uv"
    uv.write_text(
        '#!/usr/bin/env bash\nprintf ran > "$SESSION_SETUP_MARKER"\n',
        encoding="utf-8",
    )
    uv.chmod(0o755)
    env = {
        "PATH": str(bin_dir),
        "CI": "1",
        "SESSION_SETUP_MARKER": str(marker),
        "CLOUD_AGENT_DEV_ENV_SKIP_TOOL_BOOTSTRAP": "1",
    }

    result = subprocess.run(
        [str(ROOT / "scripts" / "session-setup.sh"), "--dry-run"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not marker.exists()


def test_session_setup_runs_in_codex_cloud_ci(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(ROOT / "scripts" / "session-setup.sh", scripts / "session-setup.sh")
    shutil.copy2(
        ROOT / "scripts" / "persist_setup_env.py", scripts / "persist_setup_env.py"
    )

    marker = tmp_path / "uv-ran"
    bin_dir = minimal_path(tmp_path)
    python3 = shutil.which("python3")
    assert python3 is not None
    (bin_dir / "python3").symlink_to(python3)
    uv = bin_dir / "uv"
    uv.write_text(
        "#!/usr/bin/env bash\n"
        'printf \'%s\' "$GH_CONFIG_DIR" > "$SESSION_SETUP_MARKER"\n',
        encoding="utf-8",
    )
    uv.chmod(0o755)
    env = {
        "PATH": str(bin_dir),
        "CI": "1",
        "CODEX_CI": "1",
        "GH_TOKEN": "ghp_test_secret",
        "SESSION_SETUP_MARKER": str(marker),
        "CLOUD_AGENT_DEV_ENV_SKIP_TOOL_BOOTSTRAP": "1",
    }

    result = subprocess.run(
        [str(scripts / "session-setup.sh"), "--dry-run"],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert marker.read_text(encoding="utf-8") == str(repo / ".local" / "gh")
    assert (repo / ".env").read_text(encoding="utf-8") == "GH_TOKEN='ghp_test_secret'\n"


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


def test_live_e2e_delegates_auth_without_token_env(tmp_path: Path) -> None:
    result = run_live_e2e_with_path(
        minimal_path(tmp_path, tools=("just", "gh", "allowlister", "oneharness", "uv"))
    )

    assert result.returncode == 0, result.stderr


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
