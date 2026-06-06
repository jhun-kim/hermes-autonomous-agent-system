# cmux-First Policy

## Rule

cmux is the workspace/surface layer for repository work. Worker engines such as Codex, LazyCodex, OmX, and OmO run inside cmux-managed surfaces rather than replacing cmux.

## Discord Thread Mapping

- One Discord thread maps to one cmux workspace.
- The workspace name should be deterministic from thread/channel context.
- Add ten terminal surfaces by default for parallel workers.

## Visible Execution

When Codex or another worker is claimed, a user opening the cmux workspace must be able to see one of:

- the live CLI session,
- the command invocation,
- or logged worker output in the relevant surface.

Hidden background-only execution is not enough to claim visible cmux/Codex work.

## Parallel Work

Use isolated branches/worktrees per editing surface, then merge accepted changes into an integration branch before pushing and opening a PR.
