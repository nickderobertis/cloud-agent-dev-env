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

## Live checks

The deterministic gate is credential-free. To prove the real external setup,
run:

```console
just live-e2e
```

That uses the real `gh` CLI, `gh skill install`, and `oneharness`. Missing
credentials or missing agent CLIs skip cleanly; authentication or API failures
fail.

## Secrets

`gh-secrets.json` declares the repo secrets. Values are sourced from Bitwarden
and written to `.env` plus GitHub Actions:

```console
just secrets-sync
```

The values are never committed.

