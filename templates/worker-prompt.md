# Worker Prompt Template

You are working on GitHub issue {{issue_number}} in {{repo}}.

## Contract

Read the issue body and implement only its acceptance criteria.

## Workspace Rules

- Work inside the cmux workspace for Discord thread {{discord_thread_id}}.
- Keep Codex/worker execution visibly inspectable in the cmux surface.
- Do not create unrelated workspaces or hidden-only sessions.

## Verification Rules

Run the commands listed by the issue or harness. Report exact output and blockers.

## Completion Format

- Issue:
- Branch:
- Commit:
- Commands:
- Files changed:
- PR:
- Follow-up issue:
