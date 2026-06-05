from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess


def test_gateway_wrapper_live_mode_uses_config_allow_list_without_allow_any(tmp_path: Path) -> None:
    # Given: a fake installed adapter that records live wrapper arguments.
    fake_adapter = _write_fake_gateway_adapter(tmp_path)
    env = _wrapper_env(tmp_path, fake_adapter)
    event = json.dumps(
        {
            "platform": "discord",
            "channel_id": "1512060115757432833",
            "content": "Hermes, hasystem add live wrapper fixture",
            "dry_run": False,
        }
    )

    # When: the reusable wrapper is exercised in live mode with the example router config.
    result = subprocess.run(
        ["scripts/hermes-gateway-wrapper", "--live", "--event-json", event],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: live mode succeeds through config allow_repos without relying on --allow-any-repo.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == {
        "allowed_by": "config",
        "repo": "jhun-kim/hermes-autonomous-agent-system",
        "status": "accepted",
    }
    invocation = json.loads((tmp_path / "adapter-invocation.json").read_text(encoding="utf-8"))
    assert invocation["has_dry_run"] is False
    assert invocation["has_allow_any_repo"] is False
    assert invocation["config"].endswith("examples/hermes-router.json")
    assert not (tmp_path / "real-mutation-marker").exists()


def test_gateway_wrapper_live_mode_accepts_explicit_allow_repo_override(tmp_path: Path) -> None:
    # Given: an isolated router config with no allow_repos and a fake adapter environment.
    fake_adapter = _write_fake_gateway_adapter(tmp_path)
    config_path = tmp_path / "router-without-allow-repos.json"
    config_path.write_text(
        json.dumps(
            {
                "repo_aliases": {"hasystem": "jhun-kim/hermes-autonomous-agent-system"},
                "allow_repos": [],
            }
        ),
        encoding="utf-8",
    )
    env = _wrapper_env(tmp_path, fake_adapter)
    env["HERMES_GATEWAY_ROUTER_CONFIG"] = str(config_path)
    event = json.dumps(
        {
            "platform": "discord",
            "content": "Hermes, hasystem add live wrapper fixture",
            "dry_run": False,
        }
    )

    # When: live mode is run once without and once with an explicit allow-repo override.
    denied = subprocess.run(
        ["scripts/hermes-gateway-wrapper", "--live", "--event-json", event],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    allowed = subprocess.run(
        [
            "scripts/hermes-gateway-wrapper",
            "--live",
            "--event-json",
            event,
            "--allow-repo",
            "jhun-kim/hermes-autonomous-agent-system",
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: repos must be allowed by config or explicit CLI allow-list.
    assert denied.returncode == 2
    denied_payload = json.loads(denied.stderr)
    assert denied_payload["status"] == "error"
    assert "requires allow_repos" in denied_payload["error"]
    assert allowed.returncode == 0, allowed.stderr
    allowed_payload = json.loads(allowed.stdout)
    assert allowed_payload["allowed_by"] == "cli"
    invocation = json.loads((tmp_path / "adapter-invocation.json").read_text(encoding="utf-8"))
    assert invocation["has_dry_run"] is False
    assert invocation["has_allow_any_repo"] is False
    assert not (tmp_path / "real-mutation-marker").exists()


def _wrapper_env(tmp_path: Path, fake_adapter: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = f"{fake_adapter.parent}{os.pathsep}{env['PATH']}"
    env["FAKE_HERMES_ADAPTER_INVOCATION"] = str(tmp_path / "adapter-invocation.json")
    env["FAKE_HERMES_ADAPTER_MUTATION_MARKER"] = str(tmp_path / "real-mutation-marker")
    return env


def _write_fake_gateway_adapter(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    adapter = bin_dir / "hermes-gateway-adapter"
    adapter.write_text(
        """#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
config_path = args[args.index("--config") + 1]
event_json = args[args.index("--event-json") + 1] if "--event-json" in args else sys.stdin.read()
config = json.loads(Path(config_path).read_text(encoding="utf-8"))
event = json.loads(event_json)
content = event["content"]
aliases = config.get("repo_aliases", {})
repo = next(
    (target for alias, target in aliases.items() if alias in content),
    config.get("default_repo"),
)
cli_allow_repos = [
    args[index + 1]
    for index, value in enumerate(args[:-1])
    if value == "--allow-repo"
]
has_allow_any_repo = "--allow-any-repo" in args
record = {
    "args": args,
    "config": config_path,
    "has_dry_run": "--dry-run" in args,
    "has_allow_any_repo": has_allow_any_repo,
}
Path(os.environ["FAKE_HERMES_ADAPTER_INVOCATION"]).write_text(
    json.dumps(record, sort_keys=True),
    encoding="utf-8",
)
if record["has_dry_run"] or has_allow_any_repo:
    print(
        json.dumps({"status": "error", "error": "live wrapper passed an unsafe flag"}),
        file=sys.stderr,
    )
    raise SystemExit(9)
if repo in cli_allow_repos:
    print(json.dumps({"status": "accepted", "repo": repo, "allowed_by": "cli"}, sort_keys=True))
    raise SystemExit(0)
if repo in config.get("allow_repos", []):
    print(json.dumps({"status": "accepted", "repo": repo, "allowed_by": "config"}, sort_keys=True))
    raise SystemExit(0)
print(
    json.dumps(
        {
            "status": "error",
            "error": "Non-dry-run gateway routing requires allow_repos or --allow-repo",
        }
    ),
    file=sys.stderr,
)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    adapter.chmod(0o755)
    return adapter
