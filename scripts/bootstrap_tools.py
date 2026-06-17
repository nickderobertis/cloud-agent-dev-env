#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

TOKEN_ENV_NAMES = (
    "GH_TOKEN",
    "GITHUB_TOKEN",
    "GITHUB_PAT",
    "GITHUB_PERSONAL_ACCESS_TOKEN",
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    repo: str
    asset_tokens: tuple[str, ...] = ()
    installer_url: str | None = None


def host_tokens() -> dict[str, str]:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        arch = "x86_64"
        gh_arch = "amd64"
    elif machine in {"aarch64", "arm64"}:
        arch = "aarch64"
        gh_arch = "arm64"
    else:
        msg = f"unsupported architecture: {machine}"
        raise RuntimeError(msg)

    if system == "linux":
        return {
            "gh": f"linux_{gh_arch}",
            "just": f"{arch}-unknown-linux-musl",
        }
    if system == "darwin":
        return {
            "gh": f"macOS_{gh_arch}",
            "just": f"{arch}-apple-darwin",
        }
    msg = f"unsupported operating system: {system}"
    raise RuntimeError(msg)


def tool_specs() -> dict[str, ToolSpec]:
    tokens = host_tokens()
    return {
        "just": ToolSpec("just", "casey/just", (tokens["just"],)),
        "gh": ToolSpec("gh", "cli/cli", (tokens["gh"],)),
        "allowlister": ToolSpec(
            "allowlister",
            "nickderobertis/allowlister",
            installer_url=(
                "https://raw.githubusercontent.com/"
                "nickderobertis/allowlister/main/scripts/install.sh"
            ),
        ),
        "oneharness": ToolSpec(
            "oneharness",
            "nickderobertis/oneharness",
            installer_url=(
                "https://raw.githubusercontent.com/"
                "nickderobertis/oneharness/main/scripts/install.sh"
            ),
        ),
    }


def github_token(env: Mapping[str, str]) -> str | None:
    for name in TOKEN_ENV_NAMES:
        value = env.get(name)
        if value:
            return value
    return None


def env_for_installer(env: Mapping[str, str]) -> dict[str, str]:
    out = dict(env)
    token = github_token(out)
    if token and not out.get("GITHUB_TOKEN"):
        out["GITHUB_TOKEN"] = token
    return out


def request(url: str, env: Mapping[str, str]) -> urllib.request.Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "cloud-agent-dev-env-bootstrap",
    }
    token = github_token(env)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def fetch_json(url: str, env: Mapping[str, str]) -> object:
    with urllib.request.urlopen(request(url, env), timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def download(url: str, dest: Path, env: Mapping[str, str]) -> None:
    with (
        urllib.request.urlopen(request(url, env), timeout=120) as response,
        dest.open("wb") as file,
    ):
        shutil.copyfileobj(response, file)


def release_assets(spec: ToolSpec, env: Mapping[str, str]) -> list[dict[str, object]]:
    data = fetch_json(
        f"https://api.github.com/repos/{spec.repo}/releases?per_page=10", env
    )
    if not isinstance(data, list):
        msg = f"{spec.repo}: releases response was not a list"
        raise RuntimeError(msg)
    releases = [
        release
        for release in data
        if isinstance(release, dict)
        and not release.get("draft")
        and not release.get("prerelease")
    ]
    if not releases:
        msg = f"{spec.repo}: no stable releases found"
        raise RuntimeError(msg)
    assets = releases[0].get("assets")
    if not isinstance(assets, list):
        msg = f"{spec.repo}: latest stable release has no assets"
        raise RuntimeError(msg)
    return [asset for asset in assets if isinstance(asset, dict)]


def asset_name(asset: Mapping[str, object]) -> str:
    value = asset.get("name")
    return value if isinstance(value, str) else ""


def asset_url(asset: Mapping[str, object]) -> str:
    value = asset.get("browser_download_url")
    if not isinstance(value, str):
        msg = f"asset {asset_name(asset)} has no browser_download_url"
        raise RuntimeError(msg)
    return value


def is_archive(name: str) -> bool:
    return name.endswith((".tar.gz", ".zip"))


def select_asset(
    spec: ToolSpec, assets: Sequence[Mapping[str, object]]
) -> Mapping[str, object]:
    matches = [
        asset
        for asset in assets
        if is_archive(asset_name(asset))
        and all(token in asset_name(asset) for token in spec.asset_tokens)
    ]
    if not matches:
        names = ", ".join(sorted(asset_name(asset) for asset in assets))
        msg = (
            f"{spec.name}: no matching release asset for {spec.asset_tokens}; "
            f"saw {names}"
        )
        raise RuntimeError(msg)
    return matches[0]


def safe_tar_members(archive: tarfile.TarFile, dest: Path) -> Iterable[tarfile.TarInfo]:
    root = dest.resolve()
    for member in archive.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(root) + os.sep) and target != root:
            msg = f"unsafe archive path: {member.name}"
            raise RuntimeError(msg)
        yield member


def extract_archive(archive_path: Path, dest: Path) -> None:
    if archive_path.name.endswith(".tar.gz"):
        with tarfile.open(archive_path, "r:gz") as archive:
            archive.extractall(dest, members=safe_tar_members(archive, dest))
        return
    if archive_path.name.endswith(".zip"):
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.namelist():
                target = (dest / member).resolve()
                if not str(target).startswith(str(dest.resolve()) + os.sep):
                    msg = f"unsafe archive path: {member}"
                    raise RuntimeError(msg)
            archive.extractall(dest)
        return
    msg = f"unsupported archive: {archive_path.name}"
    raise RuntimeError(msg)


def find_binary(root: Path, name: str) -> Path:
    candidates = [path for path in root.rglob(name) if path.is_file()]
    if not candidates:
        msg = f"{name}: binary not found in release archive"
        raise RuntimeError(msg)
    return sorted(candidates, key=lambda path: len(path.parts))[0]


def already_available(name: str, bin_dir: Path) -> bool:
    return (bin_dir / name).is_file() or shutil.which(name) is not None


def install_from_script(
    spec: ToolSpec,
    *,
    bin_dir: Path,
    env: Mapping[str, str],
) -> None:
    if not spec.installer_url:
        msg = f"{spec.name}: no installer script configured"
        raise RuntimeError(msg)

    bin_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{spec.name}-install-") as tmp_raw:
        script = Path(tmp_raw) / "install.sh"
        download(spec.installer_url, script, env)
        completed = subprocess.run(
            ["/bin/sh", str(script), "--to", str(bin_dir)],
            cwd=bin_dir.parent,
            env=env_for_installer(env),
            text=True,
            capture_output=True,
            check=False,
        )
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        msg = f"{spec.name}: installer script failed"
        if details:
            msg = f"{msg}: {details}"
        raise RuntimeError(msg)
    if not (bin_dir / spec.name).is_file():
        msg = f"{spec.name}: installer completed but binary is missing"
        raise RuntimeError(msg)


def install_from_release(
    spec: ToolSpec,
    *,
    bin_dir: Path,
    env: Mapping[str, str],
) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    assets = release_assets(spec, env)
    asset = select_asset(spec, assets)
    with tempfile.TemporaryDirectory(prefix=f"{spec.name}-bootstrap-") as tmp_raw:
        tmp = Path(tmp_raw)
        archive_path = tmp / asset_name(asset)
        download(asset_url(asset), archive_path, env)
        extract_dir = tmp / "extract"
        extract_dir.mkdir()
        extract_archive(archive_path, extract_dir)
        src = find_binary(extract_dir, spec.name)
        dest = bin_dir / spec.name
        shutil.copy2(src, dest)
        mode = dest.stat().st_mode
        dest.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install_tool(
    spec: ToolSpec,
    *,
    bin_dir: Path,
    env: Mapping[str, str],
    dry_run: bool,
) -> bool:
    if already_available(spec.name, bin_dir):
        return False
    if dry_run:
        return True

    if spec.installer_url:
        install_from_script(spec, bin_dir=bin_dir, env=env)
    else:
        install_from_release(spec, bin_dir=bin_dir, env=env)
    return True


def install_tools(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).expanduser().resolve()
    bin_dir = (
        Path(args.bin_dir).expanduser().resolve()
        if args.bin_dir
        else root / ".local" / "bin"
    )
    specs = tool_specs()
    selected = args.tool or list(specs)
    installed: list[str] = []
    for name in selected:
        changed = install_tool(
            specs[name],
            bin_dir=bin_dir,
            env=os.environ,
            dry_run=args.dry_run,
        )
        if changed:
            installed.append(name)
    if installed and not args.quiet:
        verb = "would install" if args.dry_run else "installed"
        print(f"{verb}: {', '.join(installed)} -> {bin_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--bin-dir")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--tool",
        action="append",
        choices=sorted(tool_specs()),
        help="tool to install; repeat to install a subset",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return install_tools(args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
