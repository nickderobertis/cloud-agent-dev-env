from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def load_bootstrap_tools() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "bootstrap_tools", ROOT / "scripts" / "bootstrap_tools.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["bootstrap_tools"] = module
    spec.loader.exec_module(module)
    return module


def test_script_installer_runs_with_target_bin_dir(tmp_path: Path, monkeypatch) -> None:
    bootstrap_tools = load_bootstrap_tools()
    seen: list[tuple[str, Path]] = []

    def fake_download(url: str, dest: Path, _env: object) -> None:
        seen.append((url, dest))
        dest.write_text(
            "#!/bin/sh\n"
            'test "$1" = "--to"\n'
            'mkdir -p "$2"\n'
            'printf \'%s\' "$GITHUB_TOKEN" > "$2/token.txt"\n'
            'touch "$2/allowlister"\n',
            encoding="utf-8",
        )

    monkeypatch.setattr(bootstrap_tools, "download", fake_download)
    monkeypatch.setattr(bootstrap_tools, "already_available", lambda *_args: False)
    spec = bootstrap_tools.ToolSpec(
        "allowlister",
        "nickderobertis/allowlister",
        installer_url="https://example.test/install.sh",
    )
    bin_dir = tmp_path / ".local" / "bin"

    changed = bootstrap_tools.install_tool(
        spec, bin_dir=bin_dir, env={"GITHUB_PAT": "secret"}, dry_run=False
    )

    assert changed is True
    assert seen[0][0] == "https://example.test/install.sh"
    assert (bin_dir / "allowlister").is_file()
    assert (bin_dir / "token.txt").read_text(encoding="utf-8") == "secret"


def test_tool_specs_use_upstream_installers_for_owned_tools() -> None:
    bootstrap_tools = load_bootstrap_tools()

    specs = bootstrap_tools.tool_specs()

    assert specs["allowlister"].installer_url.endswith(
        "/nickderobertis/allowlister/main/scripts/install.sh"
    )
    assert specs["oneharness"].installer_url.endswith(
        "/nickderobertis/oneharness/main/scripts/install.sh"
    )
    assert specs["just"].installer_url is None
    assert specs["gh"].installer_url is None
