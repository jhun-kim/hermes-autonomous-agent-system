# Discord Thread cmux Multi-Agent Workspace

This is the central macOS operator report for the repository. The product shape is one Discord thread mapped to one cmux workspace, with multiple visible Codex/OmX/OmO worker surfaces inside that workspace.

## Thread Identity

- Guild ID: `1478650515888934932`
- Parent Channel ID: `1478650642854580434`
- Thread ID: `1512679333611700224`
- Workspace platform: macOS
- Workspace layer: cmux
- Default worker engine: Codex CLI in visible cmux terminal surfaces

## Product Center

The repository is organized around this operating model:

1. A Discord thread is the durable work room.
2. The thread maps to exactly one cmux workspace.
3. The cmux workspace owns multi-agent execution surfaces.
4. Codex, LazyCodex, OmX, and OmO are worker engines inside cmux surfaces; they do not replace cmux.
5. GitHub issues define the work contract.
6. Every worker claim must be visible through a cmux surface command, session, or log.

## macOS Prerequisites

Check the local machine before launching workers:

```bash
sw_vers
command -v cmux
cmux version
command -v codex
codex --version
git --version
gh auth status
```

If `cmux` is missing on macOS, install cmux first and verify `cmux version` before starting issue work. Do not fall back to hidden background workers for this thread workspace.

## Workspace Naming

Use a deterministic workspace name derived from the Discord thread:

```text
hasystem-thread-1512679333611700224
```

Human-readable title:

```text
HASystem cmux multi-agent — thread 1512679333611700224
```

## Create or Reuse the Workspace

From the repository root on macOS:

```bash
cd ~/Documents/GitHub/hermes-autonomous-agent-system
cmux list-workspaces
cmux new-workspace \
  --name "HASystem cmux multi-agent — thread 1512679333611700224" \
  --cwd "$PWD" \
  --command 'printf "HASystem thread 1512679333611700224 cmux control surface\n"; git status --short --branch; exec zsh -l' \
  --focus false
```

If the workspace already exists, reuse it instead of creating a second workspace for the same thread.

## Provision Multi-Agent Surfaces

Provision twenty additive terminal surfaces in the same workspace. Surface roles:

| Surface | Role |
| --- | --- |
| 01 | Control / issue selection / git state |
| 02 | Product thesis / operator intent tracker |
| 03 | GitHub issue contract reader |
| 04 | Codex implementation worker A |
| 05 | Codex implementation worker B |
| 06 | OmX/OmO planning or ULW prompt worker |
| 07 | Documentation/report worker |
| 08 | README/onboarding worker |
| 09 | Policy/harness consistency worker |
| 10 | Test authoring worker |
| 11 | Test rerun / failure diagnosis |
| 12 | GitHub issue/PR mutation checker |
| 13 | Integration branch and conflict resolver |
| 14 | Evidence collector |
| 15 | Security/no-fabrication reviewer |
| 16 | Platform setup reviewer |
| 17 | macOS cmux command verifier |
| 18 | Windows fallback consistency reviewer |
| 19 | PR body/checks watcher |
| 20 | Follow-up issue creator |

Example additive surface creation:

```bash
cmux new-surface --workspace <workspace-ref> --type terminal --focus false
cmux tab-action --workspace <workspace-ref> --surface <surface-ref> --action rename --title "Codex implementation #83"
```

Do not create unrelated cmux workspaces for parallel workers in this Discord thread.

## Launch Visible Codex Workers

A visible Codex launch must leave an inspectable command/session/log in the cmux surface:

```bash
cd ~/Documents/GitHub/hermes-autonomous-agent-system
codex exec --sandbox workspace-write \
  "Work on the confirmed GitHub issue for Discord thread 1512679333611700224. Follow harnesses/issue-loop.md and policies/cmux-first.md. Keep output evidence visible in this cmux surface."
```

When using OmX/OmO skill prompts through Codex, encode that in the Codex prompt. Do not claim OmX/OmO/Codex was used unless this surface shows the invocation or log.

## Branch Isolation

For parallel editing, use worktrees or branches per surface:

```text
ai/thread-1512679333611700224/issue-83/surface-02
ai/thread-1512679333611700224/issue-83/surface-03
```

Merge accepted work into one integration branch before pushing a PR.

## Verification Checklist

A completed thread workspace run must report:

- `cmux tree --all` showing the thread workspace and surfaces.
- The GitHub issue URL and title.
- The branch and commit SHA.
- The visible Codex/cmux surface used.
- Test commands and exact output.
- PR URL or explicit no-PR reason.
- Follow-up issue URL.

## Current Reference Thread

Use this thread identity as the canonical example in repo docs and harnesses:

```text
Guild ID: 1478650515888934932
Parent Channel ID: 1478650642854580434
Thread ID: 1512679333611700224
```
