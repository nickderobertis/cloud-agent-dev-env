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
- Hooks stay non-blocking: a missing token or network failure should warn and
  let the agent session continue. Strict real-environment failures belong in
  explicit checks such as `just live-e2e`.

## Quality and tests

- The deterministic gate must stay credential-free and offline-capable. It
  drives the installed CLI and shell wrappers as subprocesses and uses real temp
  files.
- Live tests use real boundaries: `gh` against GitHub, `gh skill install` against
  the real skills repo, and `oneharness` detection for Claude Code and Codex.
  CI must invoke `scripts/live-e2e.sh` directly without preinstalling `just`, so
  missing required CLIs bootstrap first; missing credentials or real service
  failures fail.
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
