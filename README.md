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
with real credentials. To prove the same real external setup locally, run:

```console
just live-e2e
```

That uses the real `gh` CLI, `gh skill install`, and `oneharness`. It bootstraps
missing required CLIs first; missing credentials, authentication failures, or
API failures fail.

## Secrets

`gh-secrets.json` declares the repo secrets. Values are sourced from Bitwarden
and written to `.env` plus GitHub Actions:

```console
just secrets-sync
```

The values are never committed.
