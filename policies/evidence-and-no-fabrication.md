# Evidence and No-Fabrication Policy

## Rule

Reports must be backed by real tool, command, GitHub, browser, or file output.

## Required Evidence

- Test commands with exact output or failure text.
- Git status before completion.
- URLs read back from GitHub after issue, comment, or PR mutations.
- Commit SHA after commit.
- Explicit blockers when verification cannot run.

## Prohibited

- Inventing test results.
- Saying a PR, issue, comment, or deployment exists without reading it back.
- Claiming worker-engine usage without an observable command/session/log trail.
- Treating mocked tests as sufficient for a live GitHub automation path unless the issue scope is unit-only.
