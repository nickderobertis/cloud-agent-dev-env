from __future__ import annotations

import json
from pathlib import Path

import pytest

from cloud_agent_dev_env import cli


def test_env_files_do_not_override_existing_values(tmp_path: Path) -> None:
    env = {"GH_TOKEN": "from-env"}
    (tmp_path / ".env").write_text(
        "GH_TOKEN=from-file\nGITHUB_PAT='pat'\nexport OPENAI_API_KEY=\"api\"\n",
        encoding="utf-8",
    )

    loaded = cli.session_env(tmp_path, env)

    assert loaded["GH_TOKEN"] == "from-env"
    assert loaded["GITHUB_PAT"] == "pat"
    assert loaded["OPENAI_API_KEY"] == "api"
    assert str(tmp_path / ".local" / "bin") in loaded["PATH"]


def test_session_env_prefers_local_state_env_before_fallback_env_files(
    tmp_path: Path,
) -> None:
    external_env = tmp_path.parent / ".cloud-agent-dev-env.env"
    external_env.write_text("GH_TOKEN=from-external-env\n", encoding="utf-8")
    local_state_env = tmp_path / ".local" / "state" / "cloud-agent-dev-env.env"
    local_state_env.parent.mkdir(parents=True)
    local_state_env.write_text("GH_TOKEN=from-local-state-env\n", encoding="utf-8")
    (tmp_path / ".env").write_text("GH_TOKEN=from-env\n", encoding="utf-8")

    loaded = cli.session_env(tmp_path, {"PATH": "/usr/bin"})

    assert loaded["GH_TOKEN"] == "from-local-state-env"


@pytest.mark.parametrize("env_key", ["CODEX_CI", "CODEX_THREAD_ID"])
def test_codex_cloud_session_env_uses_default_gh_config(
    tmp_path: Path, env_key: str
) -> None:
    loaded = cli.session_env(tmp_path, {env_key: "1", "PATH": "/usr/bin"})

    assert loaded["GH_CONFIG_DIR"] == str(tmp_path / ".local" / "gh")


def test_session_env_preserves_existing_gh_config_dir(tmp_path: Path) -> None:
    loaded = cli.session_env(
        tmp_path,
        {"CODEX_CI": "1", "GH_CONFIG_DIR": "/tmp/custom-gh", "PATH": "/usr/bin"},
    )

    assert loaded["GH_CONFIG_DIR"] == "/tmp/custom-gh"


def test_github_token_priority() -> None:
    assert cli.github_token({"GITHUB_TOKEN": "a", "GH_TOKEN": "b"}) == "b"
    assert cli.github_token({"GITHUB_PAT": "c"}) == "c"
    assert cli.github_token({}) is None
    assert cli.env_with_gh_token({"GITHUB_PAT": "c"})["GH_TOKEN"] == "c"
    assert "GITHUB_PAT" not in cli.env_without_gh_token({"GITHUB_PAT": "c"})


def test_local_skill_specs_discovers_namespaced_skills(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skills" / "bootstrap" / "create-repo"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: create-repo\n---\n", encoding="utf-8"
    )
    one_part = tmp_path / "skills" / "solo"
    one_part.mkdir()
    (one_part / "SKILL.md").write_text("---\nname: solo\n---\n", encoding="utf-8")
    outside = tmp_path / "other"
    outside.mkdir()
    (outside / "SKILL.md").write_text("---\nname: nope\n---\n", encoding="utf-8")

    assert cli.local_skill_specs(tmp_path) == ["bootstrap/create-repo", "solo"]


def test_runner_dry_run_and_real_commands(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dry = cli.Runner(dry_run=True)
    result = dry.run(["example", "arg"], cwd=tmp_path)
    assert result == cli.CommandResult(("example", "arg"), 0, "", "")
    assert "+ example arg" in capsys.readouterr().err

    ok = cli.Runner().run(["python3", "-c", "print('ok')"], cwd=tmp_path)
    assert ok.stdout.strip() == "ok"

    fail = cli.Runner().run(
        ["python3", "-c", "import sys; print('bad'); sys.exit(7)"],
        cwd=tmp_path,
        check=False,
    )
    assert fail.returncode == 7
    with pytest.raises(RuntimeError, match="failed"):
        cli.Runner().run(["python3", "-c", "import sys; sys.exit(7)"], cwd=tmp_path)


def test_command_error_prefers_stderr_then_stdout() -> None:
    assert "err" in cli.command_error(cli.CommandResult(("x",), 2, "out", "err"))
    assert "out" in cli.command_error(cli.CommandResult(("x",), 2, "out", ""))
    assert "exit code 2" in cli.command_error(cli.CommandResult(("x",), 2, "", ""))


def test_repo_root_and_env_file_edges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli.repo_root_from(None) == tmp_path
    assert cli.repo_root_from(str(tmp_path)) == tmp_path

    env: dict[str, str] = {}
    cli.load_env_file(tmp_path / "missing.env", env)
    assert env == {}
    env_file = tmp_path / ".env.local"
    env_file.write_text("\n# comment\nBAD\nPLAIN=value\n", encoding="utf-8")
    cli.load_env_file(env_file, env)
    assert env == {"PLAIN": "value"}


def test_require_and_ensure_optional_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = cli.Runner()
    calls: list[tuple[str, ...]] = []

    def fake_run(argv: list[str], **_kwargs: object) -> cli.CommandResult:
        calls.append(tuple(argv))
        return cli.CommandResult(tuple(argv), 0, "", "")

    runner.run = fake_run  # type: ignore[method-assign]

    monkeypatch.setattr(cli.shutil, "which", lambda name, **_kwargs: f"/bin/{name}")
    assert cli.require_tool("gh") == "/bin/gh"
    cli.ensure_optional_tool(
        "oneharness",
        ["install-oneharness"],
        runner=runner,
        root=tmp_path,
        env={},
        install_missing=False,
    )
    assert calls == []

    which_calls = {"count": 0}

    def fake_which(name: str, **_kwargs: object) -> str | None:
        which_calls["count"] += 1
        return (
            None if which_calls["count"] <= len(cli.REQUIRED_TOOLS) else f"/bin/{name}"
        )

    monkeypatch.setattr(cli.shutil, "which", fake_which)
    with pytest.raises(RuntimeError, match="gh is required"):
        cli.require_tool("gh")
    with pytest.raises(RuntimeError, match="Rerun with --install-missing"):
        cli.ensure_optional_tool(
            "oneharness",
            ["install-oneharness"],
            runner=runner,
            root=tmp_path,
            env={},
            install_missing=False,
        )
    cli.ensure_optional_tool(
        "oneharness",
        ["install-oneharness"],
        runner=runner,
        root=tmp_path,
        env={},
        install_missing=True,
    )
    assert calls == [("install-oneharness",)]


def test_remote_skill_specs_uses_tree_paths(tmp_path: Path) -> None:
    runner = cli.Runner()

    def fake_run(*_args: object, **_kwargs: object) -> cli.CommandResult:
        payload = {
            "tree": [
                {"path": "skills/bootstrap/create-repo/SKILL.md"},
                {"path": "README.md"},
            ]
        }
        return cli.CommandResult(("gh",), 0, json.dumps(payload), "")

    runner.run = fake_run  # type: ignore[method-assign]

    assert cli.remote_skill_specs(
        "nickderobertis/dero-skills",
        runner=runner,
        root=tmp_path,
        env={},
    ) == ["skills/bootstrap/create-repo"]


def test_remote_skill_specs_dry_run_returns_default(tmp_path: Path) -> None:
    runner = cli.Runner(dry_run=True)
    assert cli.remote_skill_specs(
        "nickderobertis/dero-skills",
        runner=runner,
        root=tmp_path,
        env={},
    ) == ["skills/bootstrap/create-repo"]


def test_discover_skill_specs_routes_local_and_remote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill = tmp_path / "skills" / "bootstrap" / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    assert cli.discover_skill_specs(
        str(tmp_path), runner=cli.Runner(), root=tmp_path, env={}
    ) == ["bootstrap/demo"]

    monkeypatch.setattr(
        cli, "remote_skill_specs", lambda *_args, **_kwargs: ["remote/demo"]
    )
    assert cli.discover_skill_specs(
        "owner/repo", runner=cli.Runner(), root=tmp_path, env={}
    ) == ["remote/demo"]


def test_install_skills_calls_gh_for_each_agent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []
    runner = cli.Runner()

    def fake_run(argv: list[str], **_kwargs: object) -> cli.CommandResult:
        calls.append(tuple(argv))
        return cli.CommandResult(tuple(argv), 0, "", "")

    monkeypatch.setattr(cli, "require_tool", lambda name, _env=None: f"/bin/{name}")
    monkeypatch.setattr(
        cli,
        "discover_skill_specs",
        lambda *_args, **_kwargs: ["skills/bootstrap/create-repo"],
    )
    runner.run = fake_run  # type: ignore[method-assign]

    specs = cli.install_skills(
        repo="nickderobertis/dero-skills",
        agents=("claude-code", "codex"),
        runner=runner,
        root=tmp_path,
        env={"GITHUB_PAT": "token"},
    )

    assert specs == ["skills/bootstrap/create-repo"]
    assert calls == [
        (
            "gh",
            "skill",
            "install",
            "nickderobertis/dero-skills",
            "skills/bootstrap/create-repo",
            "--agent",
            "claude-code",
            "--scope",
            "project",
            "--force",
        ),
        (
            "gh",
            "skill",
            "install",
            "nickderobertis/dero-skills",
            "skills/bootstrap/create-repo",
            "--agent",
            "codex",
            "--scope",
            "project",
            "--force",
        ),
    ]


def test_install_skills_local_without_force_and_empty_specs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []
    runner = cli.Runner()

    def fake_run(argv: list[str], **_kwargs: object) -> cli.CommandResult:
        calls.append(tuple(argv))
        return cli.CommandResult(tuple(argv), 0, "", "")

    runner.run = fake_run  # type: ignore[method-assign]
    monkeypatch.setattr(cli, "require_tool", lambda name, _env=None: f"/bin/{name}")
    monkeypatch.setattr(
        cli, "discover_skill_specs", lambda *_args, **_kwargs: ["bootstrap/demo"]
    )

    cli.install_skills(
        repo=str(tmp_path),
        agents=("codex",),
        runner=runner,
        root=tmp_path,
        env={},
        force=False,
    )
    assert calls[0][-1] == "--from-local"

    monkeypatch.setattr(cli, "discover_skill_specs", lambda *_args, **_kwargs: [])
    with pytest.raises(RuntimeError, match="no skills found"):
        cli.install_skills(
            repo="owner/repo",
            agents=("codex",),
            runner=runner,
            root=tmp_path,
            env={},
        )


def test_setup_gh_auth_uses_token_without_printing_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[tuple[str, ...], str | None, dict[str, str]]] = []
    runner = cli.Runner()

    monkeypatch.setattr(cli, "require_tool", lambda name, _env=None: f"/bin/{name}")

    def fake_run(
        argv: list[str],
        *,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
        **_kwargs: object,
    ) -> cli.CommandResult:
        calls.append((tuple(argv), input_text, dict(env or {})))
        if argv == ["gh", "auth", "status"]:
            return cli.CommandResult(tuple(argv), 1, "", "bad token")
        return cli.CommandResult(tuple(argv), 0, "", "")

    runner.run = fake_run  # type: ignore[method-assign]

    gh_config_dir = tmp_path / ".local" / "gh"
    cli.setup_gh_auth(
        runner=runner,
        root=tmp_path,
        env={"GITHUB_PAT": "secret", "GH_CONFIG_DIR": str(gh_config_dir)},
    )

    assert calls[0][0] == ("gh", "auth", "status")
    assert "GITHUB_PAT" not in calls[0][2]
    assert calls[0][2]["GH_CONFIG_DIR"] == str(gh_config_dir)
    assert calls[1] == (
        ("gh", "auth", "login", "--with-token"),
        "secret",
        {"GH_CONFIG_DIR": str(gh_config_dir)},
    )
    assert calls[2] == (
        ("gh", "auth", "setup-git"),
        None,
        {"GH_CONFIG_DIR": str(gh_config_dir)},
    )
    assert gh_config_dir.is_dir()


def test_setup_gh_auth_persists_setup_only_cloud_secret(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []
    runner = cli.Runner()

    monkeypatch.setattr(cli, "require_tool", lambda name, _env=None: f"/bin/{name}")

    def fake_run(
        argv: list[str],
        *,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
        **_kwargs: object,
    ) -> cli.CommandResult:
        assert env is not None
        assert not any(name in env for name in cli.TOKEN_ENV_NAMES)
        calls.append(tuple(argv))
        if argv == ["gh", "auth", "status"]:
            return cli.CommandResult(tuple(argv), 1, "", "not logged in")
        if argv == ["gh", "auth", "login", "--with-token"]:
            assert input_text == "setup-only"
        return cli.CommandResult(tuple(argv), 0, "", "")

    runner.run = fake_run  # type: ignore[method-assign]

    cli.setup_gh_auth(runner=runner, root=tmp_path, env={"GH_TOKEN": "setup-only"})

    assert calls == [
        ("gh", "auth", "status"),
        ("gh", "auth", "login", "--with-token"),
        ("gh", "auth", "setup-git"),
    ]


def test_setup_gh_auth_errors_without_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = cli.Runner()
    monkeypatch.setattr(cli, "require_tool", lambda name, _env=None: f"/bin/{name}")

    def fake_run(*_args: object, **_kwargs: object) -> cli.CommandResult:
        return cli.CommandResult(("gh",), 1, "", "")

    runner.run = fake_run  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="no GitHub token"):
        cli.setup_gh_auth(runner=runner, root=tmp_path, env={})


def test_setup_gh_auth_returns_when_already_authenticated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = cli.Runner()
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(cli, "require_tool", lambda name, _env=None: f"/bin/{name}")

    def fake_run(argv: list[str], **_kwargs: object) -> cli.CommandResult:
        calls.append(tuple(argv))
        return cli.CommandResult(tuple(argv), 0, "", "")

    runner.run = fake_run  # type: ignore[method-assign]
    cli.setup_gh_auth(runner=runner, root=tmp_path, env={})
    assert calls == [("gh", "auth", "status")]


def test_setup_allowlists_and_tools_and_detect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, ...]] = []
    runner = cli.Runner()

    def fake_run(argv: list[str], **_kwargs: object) -> cli.CommandResult:
        calls.append(tuple(argv))
        return cli.CommandResult(tuple(argv), 0, "{}", "")

    runner.run = fake_run  # type: ignore[method-assign]
    monkeypatch.setattr(cli, "require_tool", lambda name, _env=None: f"/bin/{name}")

    cli.setup_allowlists(
        agents=("claude-code", "codex"), runner=runner, root=tmp_path, env={}
    )
    cli.setup_allowlists(agents=("unknown",), runner=runner, root=tmp_path, env={})
    assert any(
        call[:6]
        == ("allowlister", "init", "--local", "--profile", "repo-write", "--harness")
        for call in calls
    )

    which_calls = {"count": 0}

    def fake_which(name: str, **_kwargs: object) -> str | None:
        which_calls["count"] += 1
        return (
            None if which_calls["count"] <= len(cli.REQUIRED_TOOLS) else f"/bin/{name}"
        )

    monkeypatch.setattr(cli.shutil, "which", fake_which)
    cli.setup_tools(
        runner=runner, root=tmp_path, env={"PATH": ""}, install_missing=True
    )
    assert any(
        call[:2] == ("python3", str(tmp_path / "scripts" / "bootstrap_tools.py"))
        for call in calls
    )
    assert (
        cli.run_oneharness_detect(runner=runner, root=tmp_path, env={}).stdout == "{}"
    )


def test_setup_session_success_and_non_blocking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "setup_tools", lambda **_kwargs: calls.append("tools"))
    monkeypatch.setattr(cli, "setup_gh_auth", lambda **_kwargs: calls.append("gh"))
    monkeypatch.setattr(
        cli, "setup_allowlists", lambda **_kwargs: calls.append("allowlists")
    )
    monkeypatch.setattr(cli, "install_skills", lambda **_kwargs: calls.append("skills"))
    monkeypatch.setattr(
        cli, "run_oneharness_detect", lambda **_kwargs: calls.append("harness")
    )
    args = cli.build_parser().parse_args(
        ["setup", "--repo-root", str(tmp_path), "--skip", "gh"]
    )
    cli.normalize_agents(args)

    assert cli.setup_session(args) == 0
    assert calls == ["tools", "allowlists", "skills", "harness"]
    assert "session setup: ok" in capsys.readouterr().out

    def fail_tools(**_kwargs: object) -> None:
        raise RuntimeError("missing")

    monkeypatch.setattr(cli, "setup_tools", fail_tools)
    args = cli.build_parser().parse_args(
        ["setup", "--repo-root", str(tmp_path), "--non-blocking", "--quiet"]
    )
    cli.normalize_agents(args)
    assert cli.setup_session(args) == 0
    assert "WARNING: tools: missing" in capsys.readouterr().err


def test_setup_session_strict_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_tools(**_kwargs: object) -> None:
        raise RuntimeError("missing")

    monkeypatch.setattr(cli, "setup_tools", fail_tools)
    args = cli.build_parser().parse_args(["setup", "--repo-root", str(tmp_path)])
    cli.normalize_agents(args)
    with pytest.raises(RuntimeError, match="missing"):
        cli.setup_session(args)


def test_doctor_json_reports_tools(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = cli.build_parser().parse_args(
        ["doctor", "--repo-root", str(tmp_path), "--json"]
    )

    assert cli.doctor(args) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["repo_root"] == str(tmp_path)
    assert "gh" in data["tools"]


def test_doctor_human_missing_and_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    args = cli.build_parser().parse_args(["doctor", "--repo-root", str(tmp_path)])
    monkeypatch.setattr(cli.shutil, "which", lambda _name, **_kwargs: None)
    assert cli.doctor(args) == 1
    assert "missing tools" in capsys.readouterr().err

    monkeypatch.setattr(cli.shutil, "which", lambda name, **_kwargs: f"/bin/{name}")
    assert cli.doctor(args) == 0
    assert "doctor: ok" in capsys.readouterr().out


def test_command_wrappers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "install_skills", lambda **_kwargs: ["a", "b"])
    args = cli.build_parser().parse_args(
        ["install-skills", "--repo-root", str(tmp_path)]
    )
    cli.normalize_agents(args)
    assert cli.install_skills_cmd(args) == 0
    assert "installed 2 skill" in capsys.readouterr().out

    monkeypatch.setattr(cli, "setup_allowlists", lambda **_kwargs: None)
    args = cli.build_parser().parse_args(
        ["setup-allowlists", "--repo-root", str(tmp_path)]
    )
    cli.normalize_agents(args)
    assert cli.setup_allowlists_cmd(args) == 0
    assert "allowlists: ok" in capsys.readouterr().out


def test_live_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner_calls: list[tuple[str, ...]] = []

    def fake_run(
        _self: cli.Runner, argv: list[str], **_kwargs: object
    ) -> cli.CommandResult:
        runner_calls.append(tuple(argv))
        if argv[:4] == ["gh", "repo", "view", "nickderobertis/gh-secrets-e2e-sandbox"]:
            return cli.CommandResult(
                tuple(argv),
                0,
                json.dumps(
                    {
                        "nameWithOwner": "nickderobertis/gh-secrets-e2e-sandbox",
                        "visibility": "PRIVATE",
                    }
                ),
                "",
            )
        return cli.CommandResult(tuple(argv), 0, "detected", "")

    monkeypatch.setattr(cli.Runner, "run", fake_run)
    monkeypatch.setattr(cli, "setup_gh_auth", lambda **_kwargs: None)
    monkeypatch.setattr(cli, "install_skills", lambda **_kwargs: ["demo"])
    monkeypatch.setattr(
        cli,
        "run_oneharness_detect",
        lambda **_kwargs: cli.CommandResult(("oneharness",), 0, "detected", ""),
    )
    args = cli.build_parser().parse_args(["live-check", "--repo-root", str(tmp_path)])
    cli.normalize_agents(args)

    assert cli.live_check(args) == 0
    assert (
        "gh",
        "repo",
        "view",
        "nickderobertis/gh-secrets-e2e-sandbox",
        "--json",
        "nameWithOwner,visibility",
    ) in runner_calls
    assert (
        "gh",
        "repo",
        "view",
        "nickderobertis/dero-skills",
        "--json",
        "nameWithOwner",
    ) in runner_calls
    assert "live-check: ok" in capsys.readouterr().out


def test_check_required_private_github_repos_rejects_current_repo(
    tmp_path: Path,
) -> None:
    with pytest.raises(RuntimeError, match="cannot prove broad GitHub token scope"):
        cli.check_required_private_github_repos(
            [cli.CURRENT_REPO],
            runner=cli.Runner(),
            root=tmp_path,
            env={},
        )


def test_check_required_private_github_repos_rejects_public_repo(
    tmp_path: Path,
) -> None:
    runner = cli.Runner()

    def fake_run(argv: list[str], **_kwargs: object) -> cli.CommandResult:
        return cli.CommandResult(
            tuple(argv),
            0,
            json.dumps({"nameWithOwner": "owner/public", "visibility": "PUBLIC"}),
            "",
        )

    runner.run = fake_run  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="public and cannot prove"):
        cli.check_required_private_github_repos(
            ["owner/public"],
            runner=runner,
            root=tmp_path,
            env={},
        )


def test_parser_defaults_and_main_error(monkeypatch: pytest.MonkeyPatch) -> None:
    args = cli.build_parser().parse_args(["setup"])
    cli.normalize_agents(args)
    assert args.agent == ["claude-code", "codex"]

    def boom(_args: object) -> int:
        msg = "bad"
        raise RuntimeError(msg)

    monkeypatch.setattr(cli, "doctor", boom)
    assert cli.main(["doctor"]) == 1


def test_main_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "doctor", lambda _args: 0)
    assert cli.main(["doctor"]) == 0
