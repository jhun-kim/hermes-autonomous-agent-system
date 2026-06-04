from __future__ import annotations

import argparse
from pathlib import Path

from hasystem.command_runner import SubprocessCommandRunner
from hasystem.finalize import FinalizeService
from hasystem.state_store import StateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Push branch, create PR, and mark the active issue done.")
    parser.add_argument("--repo", required=True, help="owner/repo or https://github.com/owner/repo(.git)")
    parser.add_argument("--local-path", required=True, help="Target repository checkout path")
    parser.add_argument("--state-db", default="state.db", help="Path to SQLite state DB")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without changing GitHub")
    args = parser.parse_args()

    runner = SubprocessCommandRunner()
    service = FinalizeService(store=StateStore(Path(args.state_db)), runner=runner)
    result = service.finalize(repo_raw=args.repo, local_path=Path(args.local_path), dry_run=args.dry_run)
    print(f"Loop: {result.loop.loop_id}")
    for command in result.commands:
        print(f"Command: {' '.join(command.args)}")
    if args.dry_run:
        print("Dry run complete. Push, PR, comments, and labels were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
