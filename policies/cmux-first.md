# cmux-First Policy

## Rule

cmux is the workspace/surface layer for repository work. Worker engines such as Codex, LazyCodex, OmX, and OmO run inside cmux-managed surfaces rather than replacing cmux.

The repository's canonical operating room is Discord thread `123456789012345682` in guild `123456789012345678`, parent channel `123456789012345679`. Its cmux workspace should be named from that thread, for example `hasystem-thread-123456789012345682`.

## Platform Defaults

- macOS: cmux is the default. If `cmux` is missing on the user's computer, the LLM/operator should guide installation and verify `cmux version` before beginning repository-changing work.
- Windows: cmux is not required. Use a normal terminal environment with Codex CLI as the visible worker surface.
- Linux or unknown: prefer cmux when it is available; otherwise use a visible terminal Codex fallback and report that fallback in the final evidence.

## Discord Thread Mapping

- One Discord thread maps to one cmux workspace.
- The workspace name should be deterministic from thread/channel context.
- Add twenty terminal surfaces by default for parallel workers.

## Visible Execution

When Codex or another worker is claimed, a user opening the cmux workspace must be able to see one of:

- the live CLI session,
- the command invocation,
- or logged worker output in the relevant surface.

Hidden background-only execution is not enough to claim visible cmux/Codex work.

When Windows terminal fallback is used, the same visibility rule applies: the Codex command, live session, or saved log must be inspectable in the terminal environment.

## Parallel Work

Use isolated branches/worktrees per editing surface, then merge accepted changes into an integration branch before pushing and opening a PR.
