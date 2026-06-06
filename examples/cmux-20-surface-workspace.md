# cmux 20-Surface Workspace Example

For a Discord thread-backed repository task:

- Workspace: `discord-<thread-id>-<slug>`
- Surface 01: control, issue selection, and git state
- Surface 02: product thesis / operator intent tracker
- Surface 03: GitHub issue contract reader
- Surface 04: Codex implementation worker A
- Surface 05: Codex implementation worker B
- Surface 06: OmX/OmO planning or ULW prompt worker
- Surface 07: documentation/report worker
- Surface 08: README/onboarding worker
- Surface 09: policy/harness consistency worker
- Surface 10: test authoring worker
- Surface 11: test rerun / failure diagnosis
- Surface 12: GitHub issue/PR mutation checker
- Surface 13: integration branch and conflict resolver
- Surface 14: evidence collector
- Surface 15: security/no-fabrication reviewer
- Surface 16: platform setup reviewer
- Surface 17: macOS cmux command verifier
- Surface 18: Windows fallback consistency reviewer
- Surface 19: PR body/checks watcher
- Surface 20: follow-up issue creator

Each editing surface should use an isolated branch or worktree. The final integration branch is the only branch pushed for PR handoff unless the operator asks otherwise.
