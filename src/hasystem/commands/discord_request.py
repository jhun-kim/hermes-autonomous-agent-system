from __future__ import annotations

import argparse
from pathlib import Path

from hasystem.command_runner import SubprocessCommandRunner
from hasystem.discord_request import DiscordAutomationService, DiscordRequestParseError, parse_discord_request
from hasystem.intake import DEFAULT_WORKSPACE, IntakeService
from hasystem.loop_runner import RunLoopService
from hasystem.state_store import StateStore
from hasystem.worker import CodexWorkerLauncher
from hasystem.workspace import Workspace


def main() -> int:
    parser = argparse.ArgumentParser(description="Handle one Discord/Gateway GitHub automation request.")
    parser.add_argument("--message", required=True, help="Raw Discord message or JSON payload containing repo + request")
    parser.add_argument("--state-db", default="state.db", help="Path to SQLite state DB")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="Clone/update workspace root")
    parser.add_argument("--dry-run", action="store_true", help="Parse and print the plan without GitHub/local/worker mutations")
    parser.add_argument("--no-run-loop", action="store_true", help="Only create the GitHub issue; do not launch the worker loop")
    args = parser.parse_args()

    runner = SubprocessCommandRunner()
    workspace = Workspace(Path(args.workspace), runner)
    service = DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=StateStore(Path(args.state_db)),
            worker=CodexWorkerLauncher(runner=runner),
        ),
    )

    try:
        if args.dry_run:
            request = parse_discord_request(args.message)
            print(f"Repo: {request.repo_raw}")
            print(f"Request: {request.request_text}")
            print("Dry run complete. No issue, clone/update, label, state, or worker changes were made.")
            return 0
        result = service.handle(args.message, dry_run=False, run_loop=not args.no_run_loop)
    except DiscordRequestParseError as exc:
        print(f"Parse error: {exc}")
        return 2

    print(f"Repo: {result.request.repo_raw}")
    print(f"Request: {result.request.request_text}")
    if result.intake is not None:
        print(f"Local path: {result.intake.local_path}")
        print(f"Issue: #{result.intake.issue_number}")
    if result.loop is None:
        print("Run loop skipped.")
    else:
        print(f"Loop: {result.loop.loop.loop_id}")
        print(f"Selected issue: #{result.loop.loop.issue.number} {result.loop.loop.issue.title}")
        print(f"Branch: {result.loop.loop.branch}")
        print(f"Worker cwd: {result.loop.worker_command.cwd}")
        print(f"Worker command: {' '.join(result.loop.worker_command.args)}")
        if result.loop.existing_active:
            print("Existing active loop reused; no new worker was launched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
