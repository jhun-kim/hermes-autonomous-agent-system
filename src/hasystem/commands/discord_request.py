from __future__ import annotations

import argparse
from pathlib import Path

from hasystem.command_runner import SubprocessCommandRunner
from hasystem.discord_request import (
    DiscordAutomationService,
    DiscordRequestParseError,
    DiscordRequestRouterConfig,
    parse_discord_request,
)
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
    parser.add_argument(
        "--repo-alias",
        action="append",
        default=[],
        metavar="ALIAS=OWNER/REPO",
        help="Natural-language repo alias. Repeatable. Example: hermes-autonomous-agent-system=jhun-kim/hermes-autonomous-agent-system",
    )
    parser.add_argument("--default-repo", help="Repo to assume when the message does not name one")
    parser.add_argument(
        "--channel-default-repo",
        action="append",
        default=[],
        metavar="CHANNEL_OR_THREAD_ID=OWNER/REPO",
        help="Repo default for one Discord channel/thread. Repeatable.",
    )
    parser.add_argument("--channel-id", help="Discord channel ID used to resolve --channel-default-repo")
    parser.add_argument("--thread-id", help="Discord thread ID used to resolve --channel-default-repo before channel ID")
    parser.add_argument("--sender-id", help="Discord sender ID used for godmode authorization")
    args = parser.parse_args()

    try:
        router_config = DiscordRequestRouterConfig(
            repo_aliases=_parse_key_value_options(args.repo_alias, "--repo-alias"),
            default_repo=args.default_repo,
            channel_default_repos=_parse_key_value_options(args.channel_default_repo, "--channel-default-repo"),
        )
    except ValueError as exc:
        print(f"Config error: {exc}")
        return 2

    runner = SubprocessCommandRunner()
    workspace = Workspace(Path(args.workspace), runner)
    service = DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=StateStore(Path(args.state_db)),
            worker=CodexWorkerLauncher(runner=runner),
        ),
        router_config=router_config,
    )

    try:
        if args.dry_run:
            request = parse_discord_request(
                args.message,
                config=router_config,
                channel_id=args.channel_id,
                thread_id=args.thread_id,
            )
            print(f"Repo: {request.repo_raw}")
            print(f"Request: {request.request_text}")
            print("Dry run complete. No issue, clone/update, label, state, or worker changes were made.")
            return 0
        result = service.handle(
            args.message,
            dry_run=False,
            run_loop=not args.no_run_loop,
            channel_id=args.channel_id,
            thread_id=args.thread_id,
            sender_id=args.sender_id,
        )
    except DiscordRequestParseError as exc:
        print(f"Parse error: {exc}")
        return 2

    print(f"Repo: {result.request.repo_raw}")
    print(f"Request: {result.request.request_text}")
    if result.godmode is not None:
        print(f"Godmode: {result.godmode.session.status}")
        print(f"Iterations: {result.godmode.session.iterations}")
        print(f"Stop reason: {result.godmode.session.stop_reason}")
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


def _parse_key_value_options(values: list[str], flag_name: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{flag_name} must be ALIAS=OWNER/REPO, got: {value}")
        key, repo = value.split("=", 1)
        key = key.strip()
        repo = repo.strip()
        if not key or not repo:
            raise ValueError(f"{flag_name} must not have an empty key or repo: {value}")
        parsed[key] = repo
        parsed[key.lower()] = repo
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
