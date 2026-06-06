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

## Korean beginner installation documentation

When changing installation, onboarding, gateway setup, or user-facing CLI behavior, keep the Korean beginner path current:

1. `README.md` must show where a non-coder starts and include the LLM copy/paste installation prompt or a direct link to it.
2. `docs/INSTALL_KO.md` must explain the selectable installation paths in Korean: general user install, developer install, Hermes/Discord dry-run validation, and LLM-guided terminal flow.
3. The `hasystem-install-ko` / `python3 -m hasystem.commands.install_ko` helper must default to safe dry-run output and must not run live gateway or GitHub mutations unless the user explicitly chooses execution.
4. Any new Markdown file should have a clear role: user guide, operator guide, developer rule, or verification note. Do not let stale `.md` files contradict the cmux-first and issue-first workflow.

## cmux worker workspace/surface workflow

When launching or instructing coding workers for repository tasks, use cmux as the session manager:

1. Prefer the caller/current cmux workspace (`CMUX_WORKSPACE_ID`) when present.
2. For Discord-originated work, treat the Discord thread as the cmux workspace boundary. Derive one deterministic workspace name from the Discord thread/channel context and keep all work for that thread in that workspace.
3. Provision the Discord-thread workspace with **20 additive terminal surfaces by default** for parallel workers. Do not collapse them into one terminal, and do not create unrelated cmux workspaces for the same Discord thread.
4. Run Codex CLI in those surfaces and instruct it to use OmX/OmO skills/workflows, especially ULW for implementation work. OmX/OmO can also be selected as worker engines by labels, but cmux remains the workspace/surface layer.
5. Make Codex CLI usage visibly verifiable inside cmux. A user who opens the relevant cmux workspace/surface must be able to see the Codex CLI session, command invocation, or live/logged Codex output for the work being claimed.
6. Do not claim cmux/Codex execution for hidden background-only Codex processes unless their invocation and output are surfaced in the relevant cmux surface for user inspection.
7. Split parallel work by git worktree/branch, using per-surface branches such as `ai/issue-51-topic/surface-01` through `surface-20`, so workers do not fight over the same index or working tree.
8. After worker branches finish, verify each branch, merge/combine the accepted branch changes into an integration branch, push, create/update the PR, and include the issue number in the PR body.
9. Keep layout changes additive and focus-neutral (`--focus false` where supported).
10. If no Discord/caller workspace exists, create one cmux workspace rooted at the target repository.
11. LazyCodex/OmX/OmO/ULW may remain worker-engine or execution-discipline standards, but they must not replace cmux as the workspace/surface orchestration layer.
