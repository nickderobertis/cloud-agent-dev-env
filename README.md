# cloud-agent-dev-env

Agent startup environment for general development across GitHub repositories.
Launch it with a GitHub PAT in `GH_TOKEN`, `GITHUB_TOKEN`, `GITHUB_PAT`, or
`GITHUB_PERSONAL_ACCESS_TOKEN`; the startup path authenticates `gh`, installs
skills from `nickderobertis/dero-skills` for Claude Code and Codex, and wires
allowlister hooks for both harnesses.

```console
just bootstrap
just check
just setup-session
```

`scripts/session-setup.sh` is the single startup script. Claude Code calls it
through `.claude/hooks/session-start.sh`; Codex calls it through
`.codex/hooks/session-start.sh`.

If `just` is not installed yet, run the scripts directly:

```console
scripts/session-setup.sh
scripts/live-e2e.sh
```

Startup installs missing `just`, `gh`, `allowlister`, and `oneharness` into
`.local/bin` and prepends that directory to `PATH`. It uses release archives for
`just`/`gh` and the upstream `scripts/install.sh` installers for
`allowlister`/`oneharness`.

## Live checks

The deterministic gate is credential-free. PRs also run a blocking live e2e job
with real credentials. CI invokes `scripts/live-e2e.sh` directly without
preinstalling `just`, so startup must bootstrap the command surface itself. To
prove the same real external setup locally, run:

```console
just live-e2e
```

That uses the real `gh` CLI, `gh skill install`, and `oneharness`. It bootstraps
missing required CLIs first. In Codex Cloud, secrets are setup-only: they are
available to `scripts/session-setup.sh` and removed before the agent phase. The
setup path therefore logs `gh` in from `GH_TOKEN`, `GITHUB_TOKEN`, `GITHUB_PAT`,
or `GITHUB_PERSONAL_ACCESS_TOKEN` and persists the auth state for later direct
agent commands such as `scripts/live-e2e.sh`. In Codex Cloud, `GH_CONFIG_DIR`
is set to `.local/gh` so setup and the later agent phase read the same persisted
GitHub CLI auth files and do not silently fall back to Codex Cloud's checkout
credential. Setup also writes the GitHub token with `0600` permissions to
`.local/state/cloud-agent-dev-env.env`, ignored `.env`, the workspace parent
`.cloud-agent-dev-env.env`, and `$HOME/.cloud-agent-dev-env.env`. The
`.local/state` copy is the primary setup-to-agent handoff because `.local/`
survives the cloud session transition in practice; the other copies are
fallbacks. Setup writes non-secret diagnostics to
`.local/state/setup-env-status.txt` so a failed cloud run can prove whether the
secret was visible during setup without printing it. If a cloud task cannot
authenticate after adding or changing a secret, save the environment and reset
the container cache so setup runs again. Missing credentials, authentication
failures, or API failures fail there.

## Secrets

`gh-secrets.json` declares the repo secrets. Values are sourced from Bitwarden
and written to `.env` plus GitHub Actions:

```console
just secrets-sync
```

The values are never committed.
