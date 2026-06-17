from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_cmd(argv: list[str], *, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["UV_CACHE_DIR"] = str(ROOT / ".cache" / "uv")
    return subprocess.run(
        argv, cwd=cwd, env=env, text=True, capture_output=True, check=False
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
