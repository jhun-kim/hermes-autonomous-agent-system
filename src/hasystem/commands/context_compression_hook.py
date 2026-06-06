from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from hasystem.gateway import JsonObject
from hasystem.intake import DEFAULT_WORKSPACE
from hasystem.runtime_hook import HermesCompressionLifecycle, HermesRuntimeHookParseError, runtime_hook_enabled


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Handle a live Hermes context-compression runtime hook through the hasystem gateway seam."
    )
    parser.add_argument("--event-json", help="Hermes context-compression hook JSON. If omitted, JSON is read from stdin.")
    parser.add_argument("--config", type=Path, help="Router config JSON file; YAML works only when PyYAML is installed.")
    parser.add_argument("--state-db", default="state.db", help="Path to SQLite state DB")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="Clone/update workspace root")
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
        HermesCompressionLifecycle.from_runtime_hook(raw_data)
        return _print_payload(
            {
                "status": "noop",
                "dispatch": {
                    "dispatched": False,
                    "reason": "context compaction thread rollover has been removed",
                },
            }
        )
    except (json.JSONDecodeError, HermesRuntimeHookParseError, ValueError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


def _print_payload(payload: JsonObject) -> int:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
