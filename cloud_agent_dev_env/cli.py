from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cloud_agent_dev_env import __version__

DEFAULT_SKILLS_REPO = "nickderobertis/dero-skills"
DEFAULT_AGENTS = ("claude-code", "codex")
TOKEN_ENV_NAMES = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_PAT",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
)
REQUIRED_TOOLS = ("just", "gh", "allowlister", "oneharness")


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass
class Runner:
    dry_run: bool = False
    verbose: bool = False

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        input_text: str | None = None,
        check: bool = True,
    ) -> CommandResult:
        args = tuple(argv)
        if self.verbose or self.dry_run:
            print("+ " + " ".join(args), file=sys.stderr)
        if self.dry_run:
            return CommandResult(args, 0, "", "")

        completed = subprocess.run(
            args,
            cwd=cwd,
            env=dict(env) if env is not None else None,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
        )
        result = CommandResult(
            args,
            completed.returncode,
            completed.stdout,
            completed.stderr,
        )
        if check and completed.returncode != 0:
            raise RuntimeError(command_error(result))
        return result


def command_error(result: CommandResult) -> str:
    stderr = result.stderr.strip()
    stdout = result.stdout.strip()
    details = stderr or stdout or f"exit code {result.returncode}"
    return f"{' '.join(result.argv)} failed: {details}"


def repo_root_from(path: str | None) -> Path:
    return Path(path).expanduser().resolve() if path else Path.cwd().resolve()


def load_env_file(path: Path, env: dict[str, str]) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        if key and key not in env:
            env[key] = strip_env_quotes(value.strip())


def strip_env_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def session_env(root: Path, base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(base or os.environ)
    local_bin = str(root / ".local" / "bin")
    current_path = env.get("PATH", "")
    if local_bin not in current_path.split(os.pathsep):
        env["PATH"] = (
            local_bin + os.pathsep + current_path if current_path else local_bin
        )
    load_env_file(root / ".env", env)
    load_env_file(root / ".env.local", env)
    return env


def github_token(env: Mapping[str, str]) -> str | None:
    for name in TOKEN_ENV_NAMES:
        value = env.get(name)
        if value:
            return value
    return None


def env_without_gh_token(env: Mapping[str, str]) -> dict[str, str]:
    out = dict(env)
    for name in TOKEN_ENV_NAMES:
        out.pop(name, None)
    return out


def env_with_gh_token(env: Mapping[str, str]) -> dict[str, str]:
    out = dict(env)
    token = github_token(out)
    if token and not out.get("GH_TOKEN"):
        out["GH_TOKEN"] = token
    return out


def require_tool(name: str, env: Mapping[str, str] | None = None) -> str:
    path = shutil.which(name, path=env.get("PATH") if env else None)
    if path is None:
        raise RuntimeError(f"{name} is required. Install it, then rerun setup.")
    return path


def ensure_optional_tool(
    name: str,
    install_argv: Sequence[str],
    *,
    runner: Runner,
    root: Path,
    env: Mapping[str, str],
    install_missing: bool,
) -> None:
    if shutil.which(name, path=env.get("PATH")) is not None:
        return
    if not install_missing:
        raise RuntimeError(f"{name} is required. Rerun with --install-missing.")
    runner.run(install_argv, cwd=root, env=env)


def setup_gh_auth(*, runner: Runner, root: Path, env: Mapping[str, str]) -> None:
    require_tool("gh", env)
    persisted_auth_env = env_without_gh_token(env)
    status = runner.run(
        ["gh", "auth", "status"],
        cwd=root,
        env=persisted_auth_env,
        check=False,
    )
    if status.returncode == 0:
        return

    token = github_token(env)
    if not token:
        raise RuntimeError(
            "gh is not authenticated and no GitHub token is available. "
            "Set GH_TOKEN, GITHUB_TOKEN, GITHUB_PAT, or "
            "GITHUB_PERSONAL_ACCESS_TOKEN. In Codex Cloud, configure the token as "
            "a secret or environment variable and reset the cache so setup can "
            "persist gh authentication before the agent phase."
        )
    runner.run(
        ["gh", "auth", "login", "--with-token"],
        cwd=root,
        env=persisted_auth_env,
        input_text=token,
    )
    runner.run(["gh", "auth", "setup-git"], cwd=root, env=persisted_auth_env)


def is_local_repo(repo: str) -> bool:
    return Path(repo).expanduser().exists()


def local_skill_specs(repo: Path) -> list[str]:
    specs: list[str] = []
    for skill_file in sorted(repo.rglob("SKILL.md")):
        try:
            rel = skill_file.parent.relative_to(repo / "skills")
        except ValueError:
            continue
        parts = rel.parts
        if len(parts) >= 2:
            specs.append("/".join(parts[-2:]))
        elif parts:
            specs.append(parts[-1])
    return specs


def remote_skill_specs(
    repo: str,
    *,
    runner: Runner,
    root: Path,
    env: Mapping[str, str],
) -> list[str]:
    result = runner.run(
        ["gh", "api", f"repos/{repo}/git/trees/HEAD?recursive=1"],
        cwd=root,
        env=env_with_gh_token(env),
    )
    if runner.dry_run:
        return ["skills/bootstrap/create-repo"]
    data = json.loads(result.stdout)
    specs: list[str] = []
    for entry in data.get("tree", []):
        path = entry.get("path", "")
        if path.startswith("skills/") and path.endswith("/SKILL.md"):
            specs.append(path.removesuffix("/SKILL.md"))
    return sorted(specs)


def discover_skill_specs(
    repo: str,
    *,
    runner: Runner,
    root: Path,
    env: Mapping[str, str],
) -> list[str]:
    if is_local_repo(repo):
        return local_skill_specs(Path(repo).expanduser().resolve())
    return remote_skill_specs(repo, runner=runner, root=root, env=env)


def install_skills(
    *,
    repo: str,
    agents: Sequence[str],
    runner: Runner,
    root: Path,
    env: Mapping[str, str],
    force: bool = True,
) -> list[str]:
    require_tool("gh", env)
    specs = discover_skill_specs(repo, runner=runner, root=root, env=env)
    if not specs:
        raise RuntimeError(f"no skills found in {repo}")
    local = is_local_repo(repo)
    for agent in agents:
        for spec in specs:
            argv = [
                "gh",
                "skill",
                "install",
                repo,
                spec,
                "--agent",
                agent,
                "--scope",
                "project",
            ]
            if local:
                argv.append("--from-local")
            if force:
                argv.append("--force")
            runner.run(argv, cwd=root, env=env_with_gh_token(env))
    return specs


def setup_allowlists(
    *,
    agents: Sequence[str],
    runner: Runner,
    root: Path,
    env: Mapping[str, str],
) -> None:
    require_tool("allowlister", env)
    harnesses = {"claude-code", "codex"}
    for agent in agents:
        if agent not in harnesses:
            continue
        runner.run(
            [
                "allowlister",
                "init",
                "--local",
                "--profile",
                "repo-write",
                "--harness",
                agent,
                "--hooks",
                "--force",
                "--yes",
            ],
            cwd=root,
            env=env,
        )


def setup_tools(
    *,
    runner: Runner,
    root: Path,
    env: Mapping[str, str],
    install_missing: bool,
) -> None:
    missing = [
        tool
        for tool in REQUIRED_TOOLS
        if shutil.which(tool, path=env.get("PATH")) is None
    ]
    if missing and install_missing:
        installer = root / "scripts" / "bootstrap_tools.py"
        runner.run(
            ["python3", str(installer), "--repo-root", str(root), "--quiet"],
            cwd=root,
            env=env,
        )
        missing = [
            tool
            for tool in REQUIRED_TOOLS
            if shutil.which(tool, path=env.get("PATH")) is None
        ]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"missing required tool(s): {joined}. Rerun setup with network access."
        )


def run_oneharness_detect(
    *,
    runner: Runner,
    root: Path,
    env: Mapping[str, str],
) -> CommandResult:
    require_tool("oneharness", env)
    return runner.run(
        ["oneharness", "detect", "--harness", "claude-code,codex"],
        cwd=root,
        env=env,
    )


def setup_session(args: argparse.Namespace) -> int:
    root = repo_root_from(args.repo_root)
    env = session_env(root)
    runner = Runner(dry_run=args.dry_run, verbose=args.verbose)
    agents = tuple(args.agent)
    actions: list[tuple[str, Any]] = [
        (
            "tools",
            lambda: setup_tools(
                runner=runner, root=root, env=env, install_missing=args.install_missing
            ),
        ),
        ("gh", lambda: setup_gh_auth(runner=runner, root=root, env=env)),
        (
            "allowlists",
            lambda: setup_allowlists(agents=agents, runner=runner, root=root, env=env),
        ),
        (
            "skills",
            lambda: install_skills(
                repo=args.skills_repo, agents=agents, runner=runner, root=root, env=env
            ),
        ),
        ("harness", lambda: run_oneharness_detect(runner=runner, root=root, env=env)),
    ]
    failures: list[str] = []
    for name, action in actions:
        if name in args.skip:
            continue
        try:
            action()
        except Exception as exc:
            if not args.non_blocking:
                raise
            failures.append(f"{name}: {exc}")
    if failures:
        for failure in failures:
            print(f"WARNING: {failure}", file=sys.stderr)
    elif not args.quiet:
        print("session setup: ok")
    return 0


def doctor(args: argparse.Namespace) -> int:
    root = repo_root_from(args.repo_root)
    env = session_env(root)
    tool_names = ["gh", "gh-secrets", "oneharness", "allowlister", "uv", "just"]
    tools = {name: shutil.which(name, path=env.get("PATH")) for name in tool_names}
    data = {
        "repo_root": str(root),
        "version": __version__,
        "tools": tools,
        "github_token_env": next(
            (name for name in TOKEN_ENV_NAMES if env.get(name)), None
        ),
        "claude_settings": (root / ".claude" / "settings.json").is_file(),
        "codex_hooks": (root / ".codex" / "hooks.json").is_file(),
        "allowlister_config": (
            (root / ".allowlister.json").is_file()
            or (root / ".allowlister.jsonc").is_file()
        ),
    }
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        missing = [name for name, path in tools.items() if path is None]
        if missing:
            print("missing tools: " + ", ".join(missing), file=sys.stderr)
            return 1
        print("doctor: ok")
    return 0


def install_skills_cmd(args: argparse.Namespace) -> int:
    root = repo_root_from(args.repo_root)
    env = session_env(root)
    runner = Runner(dry_run=args.dry_run, verbose=args.verbose)
    specs = install_skills(
        repo=args.skills_repo,
        agents=tuple(args.agent),
        runner=runner,
        root=root,
        env=env,
    )
    if not args.quiet:
        print(f"installed {len(specs)} skill(s)")
    return 0


def setup_allowlists_cmd(args: argparse.Namespace) -> int:
    root = repo_root_from(args.repo_root)
    env = session_env(root)
    runner = Runner(dry_run=args.dry_run, verbose=args.verbose)
    setup_allowlists(agents=tuple(args.agent), runner=runner, root=root, env=env)
    if not args.quiet:
        print("allowlists: ok")
    return 0


def live_check(args: argparse.Namespace) -> int:
    root = repo_root_from(args.repo_root)
    env = session_env(root)
    runner = Runner(dry_run=args.dry_run, verbose=args.verbose)
    setup_gh_auth(runner=runner, root=root, env=env)
    runner.run(
        ["gh", "repo", "view", args.skills_repo, "--json", "nameWithOwner"],
        cwd=root,
        env=env_with_gh_token(env),
    )
    specs = install_skills(
        repo=args.skills_repo,
        agents=tuple(args.agent),
        runner=runner,
        root=root,
        env=env,
    )
    detect = run_oneharness_detect(runner=runner, root=root, env=env)
    if not args.quiet:
        snippet = detect.stdout.strip()[:120]
        print(f"live-check: ok ({len(specs)} skill(s)); oneharness={snippet}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cloud-agent-dev-env")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--repo-root")
        p.add_argument("--skills-repo", default=DEFAULT_SKILLS_REPO)
        p.add_argument("--agent", action="append", choices=DEFAULT_AGENTS, default=[])
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--verbose", action="store_true")
        p.add_argument("--quiet", action="store_true")

    setup = sub.add_parser("setup")
    add_common(setup)
    setup.add_argument("--install-missing", action="store_true")
    setup.add_argument("--non-blocking", action="store_true")
    setup.add_argument(
        "--skip",
        action="append",
        choices=["tools", "gh", "allowlists", "skills", "harness"],
        default=[],
    )
    setup.set_defaults(func=setup_session)

    doc = sub.add_parser("doctor")
    doc.add_argument("--repo-root")
    doc.add_argument("--json", action="store_true")
    doc.set_defaults(func=doctor)

    skills = sub.add_parser("install-skills")
    add_common(skills)
    skills.set_defaults(func=install_skills_cmd)

    allow = sub.add_parser("setup-allowlists")
    add_common(allow)
    allow.set_defaults(func=setup_allowlists_cmd)

    live = sub.add_parser("live-check")
    add_common(live)
    live.set_defaults(func=live_check)
    return parser


def normalize_agents(args: argparse.Namespace) -> None:
    if hasattr(args, "agent") and not args.agent:
        args.agent = list(DEFAULT_AGENTS)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    normalize_agents(args)
    try:
        return int(args.func(args))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
