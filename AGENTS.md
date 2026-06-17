# AGENTS

`cloud-agent-dev-env` provisions an agent development environment for working
across other repositories. It is meant to be launched by Codex or Claude Code
with a GitHub PAT in the environment; this repo should set up that session, not
receive product-change PRs itself.

> `CLAUDE.md` is a symlink to this file. Edit `AGENTS.md` only.

## Stack and composition

- **Product shape:** CLI plus shell startup wrappers.
- **Language(s):** Python 3.12 for the CLI and tests; Bash for agent hook
  wrappers.
- **References composed:** `shapes/cli.md`, `languages/python.md`,
  `languages/bash.md`, `intersections/python-cli.md`, and `ci.md`.
- **Excluded, and why:** Windows support is intentionally omitted; this
  environment targets macOS and Linux agent hosts. Python 3.14 is not used
  because the current Codex/Claude Code host has Python 3.12 available before
  bootstrap, and startup must run before installing another interpreter. A
  release pipeline is omitted until the CLI is distributed outside this repo.

## Command surface

Use `just`; do not hand-roll equivalent commands.

- `just bootstrap` sets up the dev environment from a clean clone.
- `just check` is the full gate: format check, lint, type check, unit tests, and
  deterministic e2e.
- `just live-e2e` is a blocking PR check and uses real GitHub and agent-harness
  credentials.
- `just setup-session` runs the same startup path the agent hooks call.
- `just secrets-sync` syncs the repo secret manifest with `gh-secrets`.

## What this repo may change

- This repo may change its startup scripts, tests, docs, CI, and repo setup.
- Do not open product-feature PRs against this repo. Use it to work in other
  repositories, create new repositories, or publish PRs in those repositories.
- When a task targets another repo, clone or enter that repo and put the branch,
  commit, and PR there.

## Startup contract

- `scripts/session-setup.sh` is the single startup entry point. Claude Code and
  Codex hook wrappers both call it.
- Startup installs missing `just`, `gh`, `allowlister`, and `oneharness` into
  `.local/bin`; authenticates `gh` from `GH_TOKEN`, `GITHUB_TOKEN`,
  `GITHUB_PAT`, or `GITHUB_PERSONAL_ACCESS_TOKEN`; installs skills from
  `nickderobertis/dero-skills` for Claude Code and Codex; and registers local
  allowlister hooks for both.
- Codex Cloud secrets are setup-only and are removed before the agent phase. Do
  not expect `GH_TOKEN` to be present when an agent later runs terminal
  commands. Setup must persist `gh` authentication while the secret is available;
  this repo sets `GH_CONFIG_DIR` to `.local/gh` in Codex Cloud so setup and the
  later agent phase share the same GitHub CLI auth files and do not silently use
  Codex Cloud's checkout credential. Setup also writes the
  GitHub token to `.local/state/cloud-agent-dev-env.env` with `0600`
  permissions so direct agent commands can read it after setup-only cloud
  secrets are removed. It also writes fallback copies to ignored `.env`,
  `.cloud-agent-dev-env.env` in the workspace parent, and `$HOME` because Codex
  Cloud may replace parts of the checkout between setup and the agent phase.
  Setup writes non-secret handoff diagnostics to
  `.local/state/setup-env-status.txt`. Never stage `.local/` or
  `.cloud-agent-dev-env.env`; they may contain credentials. If credentials
  change, save the Codex Cloud environment and reset/invalidate the cache so
  setup runs again.
- Hooks stay non-blocking: a missing token or network failure should warn and
  let the agent session continue. Strict real-environment failures belong in
  explicit checks such as `just live-e2e`.
- The startup hook may skip ordinary CI, but it must not skip Codex Cloud. Codex
  Cloud is the production setup path that receives setup-only secrets.

## Quality and tests

- The deterministic gate must stay credential-free and offline-capable. It
  drives the installed CLI and shell wrappers as subprocesses and uses real temp
  files.
- Live tests use real boundaries: `gh` against GitHub, `gh skill install` against
  the real skills repo, and `oneharness` detection for Claude Code and Codex.
  CI must invoke `scripts/live-e2e.sh` directly without preinstalling `just`, and
  the live job must simulate Codex Cloud by running `scripts/session-setup.sh`
  with `GH_TOKEN` and then unsetting all GitHub token env vars before the direct
  live script. Missing required CLIs bootstrap first; missing credentials or
  real service failures fail. Keep GitHub auth validation in the Python CLI, not
  as a shell env-only precheck, so setup-persisted `gh` auth and non-cloud token
  env vars both work.
- Coverage is enforced at 95% line coverage for the Python package.

## Commits, releases, and merging

- Main is protected and only takes squash-merged PRs. Branch protection requires
  `check (ubuntu-latest)`, `check (macos-latest)`, `live-e2e`, and conversation
  resolution; admins may override for emergencies.
- PRs use `.github/pull_request_template.md`: terse **What** and **Why**. The PR
  title becomes the squash subject.
- This repo is public as `nickderobertis/cloud-agent-dev-env`.

## Keeping allowlists current

- `.claude/settings.json`, `.codex/hooks.json`, and `.allowlister.jsonc` carry
  the repo-local agent policy. When a normal build/test/startup command becomes
  routine, add it there or to the startup script instead of re-approving it each
  session.
- Dangerous operations such as destructive deletes, history rewrites, secret
  reads, repository deletion, and publishing stay out of direct allows.
