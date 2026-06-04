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
    parser = argparse.ArgumentParser(description="Run one Hermes autonomous system loop in dry-run mode.")
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name or HTTPS format")
    parser.add_argument("--state-db", default="state.db", help="Path to SQLite state DB")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="Clone/update workspace root")
    parser.add_argument("--executor", default="lazycodex", choices=["lazycodex", "omx"])
    parser.add_argument("--dry-run", action="store_true", help="Do not change GitHub labels or launch a worker")
    args = parser.parse_args()

    if not args.dry_run:
        parser.error("Only --dry-run is implemented in this MVP")

    runner = SubprocessCommandRunner()
    service = RunLoopService(
        workspace=Workspace(Path(args.workspace), runner),
        store=StateStore(Path(args.state_db)),
        worker=CodexWorkerLauncher(runner=runner, executor=args.executor),
    )
    result = service.run_once(repo_raw=args.repo, dry_run=True, executor=args.executor)
    if result is None:
        print("No eligible ai:ready issue found.")
        return 0

    if result.existing_active:
        print(f"Active loop already exists: {result.loop.loop_id}")
    else:
        print(f"Selected issue #{result.loop.issue.number}: {result.loop.issue.title}")
        print(f"Created loop id: {result.loop.loop_id}")
    print(f"Would create branch: {result.loop.branch}")
    print(f"Executor: {result.loop.executor}")
    print(f"Worker cwd: {result.worker_command.cwd}")
    print(f"Worker command: {' '.join(result.worker_command.args)}")
    print(f"State DB: {Path(args.state_db).resolve()}")
    print("Dry run complete. GitHub labels and worker launch were not changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
