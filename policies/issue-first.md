# Issue-First Policy

## Rule

Every repository-changing task starts by creating or confirming a GitHub issue. The confirmed issue is the source of truth for scope, branch naming, commits, PR bodies, and completion notes.

## Required Order

1. Create or select the issue.
2. Read back number, title, body, labels, state, and URL.
3. Confirm the acceptance criteria.
4. Only then edit docs, code, tests, branches, or PRs.

## Exceptions

- Pure status checks may inspect files and GitHub state without creating an issue.
- Emergency cleanup of accidental local artifacts may happen before issue creation.
- If GitHub issue creation is unavailable, stop and report the blocker.

## Operator-Friendly Editing

To change this behavior, edit this Markdown policy and the harnesses that reference it. Python glue should validate and transport the policy; it should not hide the operating rule from the user.
