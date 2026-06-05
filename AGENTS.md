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

## cmux worker workspace/surface workflow

When launching or instructing coding workers for repository tasks, use cmux as the session manager:

1. Prefer the caller/current cmux workspace (`CMUX_WORKSPACE_ID`) when present.
2. For Discord-originated work, treat the Discord thread as the cmux workspace boundary. Derive one deterministic workspace name from the Discord thread/channel context and keep all work for that thread in that workspace.
3. Add terminal surfaces/panes inside that workspace for parallel workers; do not open unbounded Terminal.app windows or unrelated cmux workspaces.
4. Run Codex, OmX, and OmO as worker engines inside those cmux surfaces. Choose engines by issue labels or decomposition needs, but keep cmux as the workspace/surface orchestration layer.
5. Keep layout changes additive and focus-neutral (`--focus false` where supported).
6. If no Discord/caller workspace exists, create one cmux workspace rooted at the target repository.
7. LazyCodex/OmX/OmO/ULW may remain worker-engine or execution-discipline standards, but they must not replace cmux as the workspace/surface orchestration layer.
