# Issue Loop Harness

## Purpose

Run one bounded GitHub issue from selection to verified completion, then create the next concrete follow-up issue. The harness is written in Markdown so an operator can change the agent workflow without editing Python.

## Inputs

- `repo`: GitHub repository in `owner/name` form.
- `repo_path`: local checkout path, normally `~/Documents/GitHub/<name>`.
- `issue_number`: optional explicit issue number. If omitted, select an eligible `ai:ready` issue.
- `discord_thread_id` and `discord_thread_name`: used to derive the cmux workspace boundary.
- `executor`: `codex`, `lazycodex`, `omx`, or `omo`; cmux remains the workspace layer.

## Required Workspace

- Treat one Discord thread as one cmux workspace.
- On macOS, cmux is the default workspace layer; if cmux is missing, guide the user through cmux installation before starting repository-changing work.
- On Windows, do not require cmux; use a normal terminal environment with Codex CLI as the visible worker surface.
- On Linux or unknown platforms, prefer cmux when available and otherwise use a visible terminal Codex fallback while reporting the chosen mode.
- Provision ten additive terminal surfaces by default for parallel worker capacity.
- Keep work focus-neutral; do not steal focus or create unrelated workspaces.
- Run Codex CLI visibly inside the relevant cmux surface when claiming Codex execution.
- In Windows terminal fallback mode, run Codex visibly in the terminal and preserve command/log evidence just like a cmux surface.
- Use per-surface branches/worktrees when more than one worker edits files.

## Steps

1. Confirm repository identity and clean-enough git state.
2. Register or select one bounded GitHub issue.
3. Read the issue body and labels; make it the work contract.
4. Mark the issue in progress where the repository label workflow supports it.
5. Create a topic branch named for the issue.
6. Launch or prepare visible cmux surfaces for the selected worker engine on macOS/cmux systems, or a visible Codex terminal fallback on Windows.
7. Implement only the issue acceptance criteria.
8. Run required verification commands and capture real output.
9. Clean runtime artifacts before staging changes.
10. Commit, push, and open a PR, or document why no PR was needed.
11. Comment on the issue with PR URL, commit SHA, verification evidence, and remaining state.
12. Create one concrete follow-up issue for the next bounded task.

## Verification

A completed run must report real evidence for:

- GitHub issue URL and title.
- Branch name and commit SHA.
- Files changed.
- Commands run and exact pass/fail output.
- PR URL or explicit no-PR reason.
- Follow-up issue URL.

## Prohibited

- Do not edit repository files before registering and confirming the issue.
- Do not claim Codex, OmX, OmO, or cmux was used unless there is a visible command/session/log trail.
- Do not fabricate command output, PR URLs, issue URLs, or test results.
- Do not commit `.omx`, `.omo`, `.next`, `node_modules`, pycache, build output, or local state unless the issue explicitly requires it.
- Do not keep looping after the operator says stop.
