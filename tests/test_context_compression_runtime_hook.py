from __future__ import annotations

from configparser import ConfigParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_hermes_context_compression_hook_console_script_entrypoint_exists() -> None:
    # Given: the project package metadata.
    pyproject = ConfigParser()
    pyproject.read(Path("pyproject.toml"))

    # When: console scripts are inspected.
    scripts = pyproject["project.scripts"]

    # Then: the live runtime hook points at the context compression hook command.
    assert scripts["hermes-context-compression-hook"].strip('"') == "hasystem.commands.context_compression_hook:main"


def test_context_compression_hook_noops_by_default_without_state_write(tmp_path: Path) -> None:
    # Given: a Discord context compression hook payload and default-disabled environment.
    env = _hook_env()
    state_db = tmp_path / "state.db"

    # When: the hook command receives the real runtime-shaped event without opt-in enablement.
    result = subprocess.run(
        [
            _runtime_python(),
            "-m",
            "hasystem.commands.context_compression_hook",
            "--event-json",
            json.dumps(_runtime_payload()),
            "--state-db",
            str(state_db),
            "--workspace",
            str(tmp_path / "workspace"),
            "--compaction-rollover-threshold",
            "1",
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: the default safe path is an explicit no-op and does not create state.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "noop"
    assert payload["dispatch"]["dispatched"] is False
    assert payload["dispatch"]["reason"] == "context compaction dispatch is disabled"
    assert not state_db.exists()


def test_context_compression_hook_enabled_low_threshold_dispatches_lifecycle_event(tmp_path: Path) -> None:
    # Given: live hook dispatch is explicitly enabled with rollover threshold one and no Discord token.
    env = _hook_env()
    env["HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED"] = "true"
    state_db = tmp_path / "state.db"

    # When: the runtime hook payload is handled; this is not a synthetic gateway --event-json dispatch.
    result = subprocess.run(
        [
            _runtime_python(),
            "-m",
            "hasystem.commands.context_compression_hook",
            "--event-json",
            json.dumps(_runtime_payload()),
            "--state-db",
            str(state_db),
            "--workspace",
            str(tmp_path / "workspace"),
            "--compaction-rollover-threshold",
            "1",
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: the hasystem dispatch seam receives type=context.compaction with complete handoff metadata.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "rollover_required"
    assert payload["dispatch"]["dispatched"] is True
    assert payload["event"]["type"] == "context.compaction"
    assert payload["event"]["guild_id"] == "guild-25"
    assert payload["event"]["channel_id"] == "channel-25"
    assert payload["event"]["thread_id"] == "thread-25"
    assert payload["event"]["session_id"] == "old-session-25"
    assert payload["event"]["new_session_id"] == "new-session-25"
    assert payload["event"]["repo"] == "jhun-kim/hermes-autonomous-agent-system"
    assert payload["event"]["latest_user_goal"] == "Finish GitHub issue #25"
    assert payload["event"]["active_issue"] == {
        "number": 25,
        "title": "Connect hasystem compaction dispatch seam to live Hermes runtime hooks",
        "labels": ["executor:lazycodex", "ai:in-progress", "priority:p3"],
    }
    assert payload["event"]["compression_summary"] == "compression summary from live runtime"
    assert payload["event"]["handoff_context"] == "handoff context from live runtime"
    assert "compression summary from live runtime" in payload["event"]["session_summary"]
    assert "handoff context from live runtime" in payload["event"]["session_summary"]
    assert payload["continuation"]["conversation_id"] == "discord:thread-25"
    assert payload["continuation"]["compaction_count"] == 1
    assert payload["continuation"]["should_rollover"] is True
    assert state_db.exists()


def test_context_compression_hook_enabled_non_discord_noops(tmp_path: Path) -> None:
    # Given: live hook dispatch is enabled but the compression lifecycle came from a non-Discord Hermes session.
    env = _hook_env()
    env["HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED"] = "1"
    state_db = tmp_path / "state.db"
    payload = _runtime_payload(platform="cli")

    # When: the runtime hook command handles the rotated non-Discord session.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasystem.commands.context_compression_hook",
            "--event-json",
            json.dumps(payload),
            "--state-db",
            str(state_db),
            "--workspace",
            str(tmp_path / "workspace"),
            "--compaction-rollover-threshold",
            "1",
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: enabled dispatch still fails closed for unsupported non-Discord runtime hooks.
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["status"] == "noop"
    assert output["dispatch"]["dispatched"] is False
    assert output["dispatch"]["reason"] == "context compaction dispatch only supports Discord sessions"
    assert not state_db.exists()


def test_gateway_conversation_key_survives_rotated_hermes_sessions(tmp_path: Path) -> None:
    # Given: two successful live compression lifecycles in the same Discord thread with different Hermes session ids.
    env = _hook_env()
    env["HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED"] = "true"
    state_db = tmp_path / "state.db"

    # When: the hook sees both old-session to new-session rotations below a threshold of two.
    first = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasystem.commands.context_compression_hook",
            "--event-json",
            json.dumps(_runtime_payload(old_session_id="session-25-a", new_session_id="session-25-b")),
            "--state-db",
            str(state_db),
            "--workspace",
            str(tmp_path / "workspace"),
            "--compaction-rollover-threshold",
            "2",
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    second = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasystem.commands.context_compression_hook",
            "--event-json",
            json.dumps(_runtime_payload(old_session_id="session-25-b", new_session_id="session-25-c")),
            "--state-db",
            str(state_db),
            "--workspace",
            str(tmp_path / "workspace"),
            "--compaction-rollover-threshold",
            "2",
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: rollover counts the stable Discord thread, not each volatile Hermes session id separately.
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload["status"] == "compaction_recorded"
    assert first_payload["continuation"]["compaction_count"] == 1
    assert second_payload["status"] == "rollover_required"
    assert second_payload["continuation"]["conversation_id"] == "discord:thread-25"
    assert second_payload["continuation"]["compaction_count"] == 2


def _hook_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").resolve())
    env.pop("HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED", None)
    env.pop("DISCORD_BOT_TOKEN", None)
    return env


def _runtime_python() -> str:
    if sys.version_info >= (3, 10):
        return sys.executable
    python_311 = shutil.which("python3.11")
    if python_311 is not None:
        return python_311
    python_310 = shutil.which("python3.10")
    if python_310 is not None:
        return python_310
    return sys.executable


def _runtime_payload(
    *,
    platform: str = "discord",
    old_session_id: str = "old-session-25",
    new_session_id: str = "new-session-25",
) -> dict[str, object]:
    return {
        "hook_event_name": "context.compaction",
        "platform": platform,
        "discord": {
            "guild_id": "guild-25",
            "channel_id": "channel-25",
            "thread_id": "thread-25",
        },
        "session": {"old_id": old_session_id, "new_id": new_session_id},
        "repository": "jhun-kim/hermes-autonomous-agent-system",
        "latest_goal": "Finish GitHub issue #25",
        "active_issue": {
            "number": 25,
            "title": "Connect hasystem compaction dispatch seam to live Hermes runtime hooks",
            "labels": ["executor:lazycodex", "ai:in-progress", "priority:p3"],
        },
        "compression": {
            "summary": "compression summary from live runtime",
            "handoff_context": "handoff context from live runtime",
        },
    }
