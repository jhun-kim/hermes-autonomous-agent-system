from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


PLUGIN_PATH = Path(__file__).resolve().parents[1] / "integrations" / "hermes_plugins" / "hasystem_gateway_intake" / "__init__.py"


def load_plugin():
    spec = importlib.util.spec_from_file_location("hasystem_gateway_intake_test", PLUGIN_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PlatformValue:
    value = "discord"


def discord_thread_event(text: str = "godmode status"):
    source = SimpleNamespace(
        platform=PlatformValue(),
        guild_id="1478650515888934932",
        parent_chat_id="1478650642854580434",
        chat_id="1512332564218773564",
        chat_name="Hermes continuation after 2 compactions",
        chat_type="thread",
        thread_id="1512332564218773564",
        user_id="1032172433693749280",
        user_name="robbieboy",
        is_bot=False,
        message_id="1512476487289143306",
    )
    return SimpleNamespace(source=source, text=text, message_id="1512476487289143306")


def test_discord_thread_godmode_event_becomes_hasystem_adapter_json(monkeypatch):
    plugin = load_plugin()
    monkeypatch.setenv("HASYSTEM_GATEWAY_PARENT_CHANNEL_IDS", "1478650642854580434")
    monkeypatch.setenv("HASYSTEM_GATEWAY_ADAPTER_COMMAND", "/tmp/hasystem-wrapper --live")

    prepared = plugin.prepare_dispatch(discord_thread_event("godmode status"))

    assert prepared is not None
    assert prepared.command == ["/tmp/hasystem-wrapper", "--live"]
    assert prepared.event == {
        "platform": "discord",
        "guild_id": "1478650515888934932",
        "channel_id": "1478650642854580434",
        "channel_name": None,
        "thread_id": "1512332564218773564",
        "thread_name": "Hermes continuation after 2 compactions",
        "sender": {"id": "1032172433693749280", "display_name": "robbieboy"},
        "message_id": "1512476487289143306",
        "content": "godmode status",
    }


def test_hasystem_prefix_strips_routing_command(monkeypatch):
    plugin = load_plugin()
    monkeypatch.delenv("HASYSTEM_GATEWAY_PARENT_CHANNEL_IDS", raising=False)
    monkeypatch.setenv("HASYSTEM_GATEWAY_ADAPTER_COMMAND", "/tmp/hasystem-wrapper --live")

    prepared = plugin.prepare_dispatch(discord_thread_event("/hasystem repo status 확인"))

    assert prepared is not None
    assert prepared.event["content"] == "repo status 확인"


def test_ordinary_discord_message_is_not_intercepted(monkeypatch):
    plugin = load_plugin()
    monkeypatch.setenv("HASYSTEM_GATEWAY_ADAPTER_COMMAND", "/tmp/hasystem-wrapper --live")

    assert plugin.prepare_dispatch(discord_thread_event("그냥 일반 대화")) is None


def test_channel_allow_list_is_fail_closed(monkeypatch):
    plugin = load_plugin()
    monkeypatch.setenv("HASYSTEM_GATEWAY_PARENT_CHANNEL_IDS", "some-other-channel")
    monkeypatch.setenv("HASYSTEM_GATEWAY_ADAPTER_COMMAND", "/tmp/hasystem-wrapper --live")

    assert plugin.prepare_dispatch(discord_thread_event("godmode status")) is None


def test_adapter_command_receives_event_json(monkeypatch):
    plugin = load_plugin()
    monkeypatch.setenv("HASYSTEM_GATEWAY_ADAPTER_COMMAND", "/tmp/hasystem-wrapper --live")
    prepared = plugin.prepare_dispatch(discord_thread_event("godmode status"))
    assert prepared is not None

    calls = []

    def fake_run(command, *, text, capture_output, timeout, check):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='{"status":"godmode_status"}', stderr="")

    monkeypatch.setattr(plugin.subprocess, "run", fake_run)

    result = plugin._run_adapter_command(prepared.command, prepared.event)

    assert result.returncode == 0
    assert calls[0][:2] == ["/tmp/hasystem-wrapper", "--live"]
    assert calls[0][2] == "--event-json"
    assert '"channel_id": "1478650642854580434"' in calls[0][3]
    assert '"thread_id": "1512332564218773564"' in calls[0][3]
