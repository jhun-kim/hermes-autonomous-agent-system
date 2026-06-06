# cmux 10-Surface Workspace Example

For a Discord thread-backed repository task:

- Workspace: `discord-<thread-id>-<slug>`
- Surface 01: issue selection and plan
- Surface 02: implementation worker
- Surface 03: tests and verification
- Surface 04: README/docs review
- Surface 05: GitHub issue/PR mutation check
- Surfaces 06-10: reserved for parallel follow-up workers

Each editing surface should use an isolated branch or worktree. The final integration branch is the only branch pushed for PR handoff unless the operator asks otherwise.
