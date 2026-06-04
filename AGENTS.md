# Agent Operating Rules

## Issue-first workflow for this repository

When continuing this repository to the next stage, do not start by editing code directly.

Required order:

1. Register the intended task as a GitHub issue in this repository.
2. Immediately read/confirm the created issue, including its number, title, body, and labels.
3. Use the confirmed issue as the source of truth for the work bundle.
4. Only after the issue is confirmed, create/change code, docs, tests, branches, or PRs.
5. Mention the issue number in commits, PR bodies, and completion notes when practical.

This rule applies to human Discord requests such as "next step", "continue this repo", "fix this", or natural-language requests that imply code or documentation changes.

Exceptions:

- Pure inspection/status checks may read files or GitHub state without creating an issue.
- Emergency cleanup of accidental local artifacts may be done before issue creation.
- If GitHub issue creation is unavailable, stop and report the blocker instead of silently editing code.
