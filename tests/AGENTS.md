# Tests

Tests must drive real subprocess boundaries where the user-visible contract is a
CLI or shell wrapper. Use fakes only for external third parties that cannot run
in the deterministic gate, and keep live coverage in `scripts/live-e2e.sh`.

