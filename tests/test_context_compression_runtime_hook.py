from __future__ import annotations

from configparser import ConfigParser
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def test_hermes_context_compression_hook_console_script_is_not_installed() -> None:
    # Given: the project package metadata.
    pyproject = ConfigParser()
    pyproject.read(Path("pyproject.toml"))

    # When: console scripts are inspected.
    scripts = pyproject["project.scripts"]

    # Then: hasystem no longer installs a context-compression rollover hook entrypoint.
    assert "hermes-context-compression-hook" not in scripts


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


def test_context_compression_hook_enabled_low_threshold_noops_without_rollover(tmp_path: Path) -> None:
    # Given: stale live hook dispatch is explicitly enabled with rollover threshold one.
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
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: the stale hook command is inert and does not create rollover state.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "noop"
    assert payload["dispatch"]["dispatched"] is False
    assert payload["dispatch"]["reason"] == "context compaction thread rollover has been removed"
    assert not state_db.exists()


def test_context_compression_hook_enabled_non_discord_also_noops_after_rollover_removal(tmp_path: Path) -> None:
    # Given: stale live hook dispatch is enabled and the compression lifecycle came from a non-Discord Hermes session.
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
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: all enabled compaction dispatches are inert after rollover removal.
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    assert output["status"] == "noop"
    assert output["dispatch"]["dispatched"] is False
    assert output["dispatch"]["reason"] == "context compaction thread rollover has been removed"
    assert not state_db.exists()


def test_repeated_rotated_hermes_sessions_do_not_create_rollover_state(tmp_path: Path) -> None:
    # Given: two stale live compression lifecycles in the same Discord thread with different Hermes session ids.
    env = _hook_env()
    env["HERMES_CONTEXT_COMPACTION_DISPATCH_ENABLED"] = "true"
    state_db = tmp_path / "state.db"

    # When: the hook sees both old-session to new-session rotations with the old threshold flag.
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
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: neither event records compaction count state or requests rollover.
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    first_payload = json.loads(first.stdout)
    second_payload = json.loads(second.stdout)
    assert first_payload["status"] == "noop"
    assert first_payload["dispatch"]["reason"] == "context compaction thread rollover has been removed"
    assert second_payload["status"] == "noop"
    assert second_payload["dispatch"]["reason"] == "context compaction thread rollover has been removed"
    assert not state_db.exists()


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
