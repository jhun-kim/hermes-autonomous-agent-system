from __future__ import annotations

import argparse
from pathlib import Path

from hasystem.command_runner import SubprocessCommandRunner
from hasystem.intake import DEFAULT_WORKSPACE
from hasystem.loop_runner import RunLoopService
from hasystem.state_store import StateStore
from hasystem.worker import CodexWorkerLauncher
from hasystem.workspace import Workspace


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Hermes issue execution loop.")
    parser.add_argument("--repo", required=True, help="owner/repo or https://github.com/owner/repo(.git)")
    parser.add_argument("--state-db", default="state.db", help="Path to SQLite state DB")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="Clone/update workspace root")
    parser.add_argument("--executor", default="lazycodex", choices=["lazycodex", "omx"])
    parser.add_argument("--dry-run", action="store_true", help="Plan without local/GitHub mutations or worker launch")
    args = parser.parse_args()

    runner = SubprocessCommandRunner()
    service = RunLoopService(
        workspace=Workspace(Path(args.workspace), runner),
        store=StateStore(Path(args.state_db)),
        worker=CodexWorkerLauncher(runner=runner, executor=args.executor),
    )
    result = service.run_once(repo_raw=args.repo, dry_run=args.dry_run, executor=args.executor)
    if result is None:
        print("No eligible ai:ready issue found.")
        return 0
    print(f"Loop: {result.loop.loop_id}")
    print(f"Issue: #{result.loop.issue.number} {result.loop.issue.title}")
    print(f"Branch: {result.loop.branch}")
    print(f"Executor: {result.loop.executor}")
    print(f"Worker cwd: {result.worker_command.cwd}")
    print(f"Worker command: {' '.join(result.worker_command.args)}")
    if args.dry_run:
        print("Dry run complete. Local workspace, GitHub labels, and worker launch were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
