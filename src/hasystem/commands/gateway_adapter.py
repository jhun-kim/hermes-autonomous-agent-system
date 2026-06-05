from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import NoReturn

from hasystem.command_runner import SubprocessCommandRunner
from hasystem.compaction_rollover import DiscordRestContinuationClient
from hasystem.discord_request import (
    DiscordAutomationService,
    DiscordRequestParseError,
)
from hasystem.gateway import DiscordGatewayEvent, build_gateway_response, load_router_config
from hasystem.intake import DEFAULT_WORKSPACE, IntakeService
from hasystem.loop_runner import RunLoopService
from hasystem.state_store import StateStore
from hasystem.worker import CodexWorkerLauncher
from hasystem.workspace import Workspace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hermes Discord/Gateway adapter: read an event JSON envelope and print structured routing JSON."
    )
    parser.add_argument("--event-json", help="Gateway event JSON. If omitted, JSON is read from stdin.")
    parser.add_argument("--config", type=Path, help="Router config JSON file; YAML works only when PyYAML is installed.")
    parser.add_argument("--state-db", default="state.db", help="Path to SQLite state DB")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="Clone/update workspace root")
    parser.add_argument("--dry-run", action="store_true", help="Override event and prove routing without mutations")
    parser.add_argument("--no-run-loop", action="store_true", help="Override event and create only the issue")
    parser.add_argument(
        "--repo-alias",
        action="append",
        default=[],
        metavar="ALIAS=OWNER/REPO",
        help="CLI repo alias override. Repeatable.",
    )
    parser.add_argument("--default-repo", help="CLI default repo override")
    parser.add_argument(
        "--compaction-rollover-threshold",
        type=int,
        help="Context compaction count that triggers continuation rollover; defaults to config or 7.",
    )
    parser.add_argument(
        "--channel-default-repo",
        action="append",
        default=[],
        metavar="CHANNEL_OR_THREAD_ID=OWNER/REPO",
        help="CLI channel/thread default repo override. Repeatable.",
    )
    parser.add_argument(
        "--allow-repo",
        action="append",
        default=None,
        metavar="OWNER/REPO",
        help="CLI allow-list override. Repeatable; replaces config allow_repos when supplied.",
    )
    parser.add_argument(
        "--allow-any-repo",
        action="store_true",
        help="Permit non-dry-run routing without an allow-list. Intended only for trusted gateways.",
    )
    args = parser.parse_args()

    try:
        event_json = args.event_json if args.event_json is not None else sys.stdin.read()
        event = DiscordGatewayEvent.from_json(event_json)
        router_config = load_router_config(
            args.config,
            repo_alias_overrides=_parse_key_value_options(args.repo_alias, "--repo-alias"),
            channel_default_repo_overrides=_parse_key_value_options(
                args.channel_default_repo,
                "--channel-default-repo",
            ),
            default_repo_override=args.default_repo,
            allow_repo_overrides=_allow_repo_overrides(args.allow_repo),
        )
        if args.compaction_rollover_threshold is not None:
            router_config = replace(
                router_config,
                compaction_rollover_threshold=args.compaction_rollover_threshold,
            )
        runner = SubprocessCommandRunner()
        workspace = Workspace(Path(args.workspace), runner)
        effective_dry_run = args.dry_run or event.dry_run
        if not effective_dry_run and not args.allow_any_repo and not router_config.allow_repos:
            raise DiscordRequestParseError(
                "Non-dry-run gateway routing requires allow_repos, --allow-repo, or explicit --allow-any-repo"
            )
        service = DiscordAutomationService(
            intake=IntakeService(workspace=workspace, runner=runner),
            loop_runner=_build_loop_runner(
                dry_run=effective_dry_run,
                workspace=workspace,
                state_db=Path(args.state_db),
                runner=runner,
            ),
            router_config=router_config,
        )
        payload = build_gateway_response(
            service=service,
            event=event,
            dry_run_override=True if args.dry_run else None,
            no_run_loop_override=True if args.no_run_loop else None,
            state_store=None if effective_dry_run else StateStore(Path(args.state_db)),
            discord_client=_discord_client_from_env(),
        )
    except DiscordRequestParseError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except ValueError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _parse_key_value_options(values: list[str], flag_name: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"{flag_name} must be KEY=OWNER/REPO, got: {value}")
        key, repo = value.split("=", 1)
        key = key.strip()
        repo = repo.strip()
        if not key or not repo:
            raise ValueError(f"{flag_name} must not have an empty key or repo: {value}")
        parsed[key] = repo
        parsed[key.lower()] = repo
    return parsed


def _allow_repo_overrides(values: list[str] | None) -> frozenset[str] | None:
    if values is None:
        return None
    return frozenset(value.strip() for value in values if value.strip())


def _discord_client_from_env() -> DiscordRestContinuationClient | None:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        return None
    return DiscordRestContinuationClient(bot_token=token)


class _DryRunLoopRunner:
    def run_once(self, repo_raw: str, dry_run: bool, executor: str = "lazycodex") -> NoReturn:
        raise RuntimeError("dry-run gateway adapter must not invoke the run loop")


def _build_loop_runner(
    *,
    dry_run: bool,
    workspace: Workspace,
    state_db: Path,
    runner: SubprocessCommandRunner,
) -> RunLoopService | _DryRunLoopRunner:
    if dry_run:
        return _DryRunLoopRunner()
    return RunLoopService(
        workspace=workspace,
        store=StateStore(state_db),
        worker=CodexWorkerLauncher(runner=runner),
    )


if __name__ == "__main__":
    raise SystemExit(main())
