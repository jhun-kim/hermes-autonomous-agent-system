from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import replace
from pathlib import Path

from hasystem.command_runner import SubprocessCommandRunner
from hasystem.compaction_rollover import DiscordRestContinuationClient
from hasystem.discord_request import DiscordAutomationService
from hasystem.gateway import JsonObject, load_router_config
from hasystem.hermes_context import HermesContextCompressionDispatchConfig, dispatch_hermes_context_compression
from hasystem.intake import DEFAULT_WORKSPACE, IntakeService
from hasystem.loop_runner import RunLoopService
from hasystem.runtime_hook import HermesCompressionLifecycle, HermesRuntimeHookParseError, runtime_hook_enabled
from hasystem.state_store import StateStore
from hasystem.worker import CodexWorkerLauncher
from hasystem.workspace import Workspace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Handle a live Hermes context-compression runtime hook through the hasystem gateway seam."
    )
    parser.add_argument("--event-json", help="Hermes context-compression hook JSON. If omitted, JSON is read from stdin.")
    parser.add_argument("--config", type=Path, help="Router config JSON file; YAML works only when PyYAML is installed.")
    parser.add_argument("--state-db", default="state.db", help="Path to SQLite state DB")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="Clone/update workspace root")
    parser.add_argument(
        "--compaction-rollover-threshold",
        type=int,
        help="Context compaction count that triggers continuation rollover; defaults to config or 7.",
    )
    args = parser.parse_args()

    try:
        raw_event = args.event_json if args.event_json is not None else sys.stdin.read()
        raw_data = json.loads(raw_event)
        if not isinstance(raw_data, dict):
            raise HermesRuntimeHookParseError("top-level hook JSON must be an object")
        enabled = runtime_hook_enabled(os.environ.get("HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED"))
        if not enabled:
            return _print_payload(
                {
                    "status": "noop",
                    "dispatch": {
                        "dispatched": False,
                        "reason": "context compaction dispatch is disabled",
                    },
                }
            )
        lifecycle = HermesCompressionLifecycle.from_runtime_hook(raw_data)
        if lifecycle.compression.platform != "discord":
            return _print_payload(
                {
                    "status": "noop",
                    "dispatch": {
                        "dispatched": False,
                        "reason": "context compaction dispatch only supports Discord sessions",
                    },
                }
            )
        router_config = load_router_config(args.config)
        if args.compaction_rollover_threshold is not None:
            router_config = replace(
                router_config,
                compaction_rollover_threshold=args.compaction_rollover_threshold,
            )
        runner = SubprocessCommandRunner()
        workspace = Workspace(Path(args.workspace), runner)
        state_store = StateStore(Path(args.state_db))
        service = DiscordAutomationService(
            intake=IntakeService(workspace=workspace, runner=runner),
            loop_runner=RunLoopService(
                workspace=workspace,
                store=state_store,
                worker=CodexWorkerLauncher(runner=runner),
            ),
            router_config=router_config,
        )
        result = dispatch_hermes_context_compression(
            compression=lifecycle.compression,
            config=HermesContextCompressionDispatchConfig(enabled=True),
            service=service,
            state_store=state_store,
            discord_client=_discord_client_from_env(),
        )
    except (json.JSONDecodeError, HermesRuntimeHookParseError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    payload = result.payload or {"status": "noop"}
    payload["dispatch"] = {"dispatched": result.dispatched, "reason": result.reason}
    return _print_payload(payload)


def _print_payload(payload: JsonObject) -> int:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0


def _discord_client_from_env() -> DiscordRestContinuationClient | None:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        return None
    return DiscordRestContinuationClient(bot_token=token)


if __name__ == "__main__":
    raise SystemExit(main())
