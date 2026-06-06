"""Hermes plugin: route configured Discord thread requests to hasystem.

Install this directory as ``~/.hermes/plugins/hasystem-gateway-intake`` and add
``hasystem-gateway-intake`` to ``plugins.enabled``. Hermes calls this plugin via
its ``pre_gateway_dispatch`` hook before ordinary agent dispatch.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

_TRIGGER_PREFIX_RE = re.compile(r"^(?:/|!|@)?hasystem(?:\s+|$)", re.IGNORECASE)
_GODMODE_RE = re.compile(r"^/?godmode(?:\s+(?:status|pause|resume|stop))?$", re.IGNORECASE)
_HERMES_ESCAPE_RE = re.compile(r"^(?:/|@)hermes(?:\s+|$)", re.IGNORECASE)


@dataclass(frozen=True)
class PreparedDispatch:
    event: dict[str, Any]
    command: list[str]


def register(ctx: Any) -> None:
    ctx.register_hook("pre_gateway_dispatch", _on_pre_gateway_dispatch)


def _on_pre_gateway_dispatch(event: Any = None, gateway: Any = None, **_: Any) -> dict[str, str] | None:
    prepared = prepare_dispatch(event)
    if prepared is None:
        return None

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        _dispatch_and_send_sync(prepared, event, gateway)
    else:
        loop.create_task(_dispatch_and_send(prepared, event, gateway))

    return {"action": "skip", "reason": "hasystem gateway intake handled explicit routing command"}


def prepare_dispatch(event: Any) -> PreparedDispatch | None:
    if event is None:
        return None
    source = getattr(event, "source", None)
    if not _is_discord_source(source):
        return None
    if _source_is_bot(source):
        return None

    if not _channel_allowed(source):
        return None

    raw_text = str(getattr(event, "text", "") or "").strip()
    content = _routed_content(raw_text, source=source)
    if content is None:
        return None

    command = _adapter_command()
    if not command:
        return None

    return PreparedDispatch(event=_event_envelope(event=event, source=source, content=content), command=command)


def _is_discord_source(source: Any) -> bool:
    platform = getattr(source, "platform", "")
    platform_value = str(getattr(platform, "value", platform) or "").lower()
    return platform_value == "discord"


def _source_is_bot(source: Any) -> bool:
    return bool(getattr(source, "is_bot", False))


def _channel_allowed(source: Any) -> bool:
    configured = _csv_env("HASYSTEM_GATEWAY_PARENT_CHANNEL_IDS")
    if not configured:
        return True
    ids = _source_channel_ids(source)
    return bool(ids & configured)


def _source_channel_ids(source: Any) -> set[str]:
    values = {
        getattr(source, "parent_chat_id", None),
        getattr(source, "chat_id", None),
        getattr(source, "thread_id", None),
    }
    return {str(value).strip() for value in values if str(value or "").strip()}


def _routed_content(raw_text: str, *, source: Any) -> str | None:
    if not raw_text:
        return None
    if _HERMES_ESCAPE_RE.match(raw_text):
        return None
    if _GODMODE_RE.match(raw_text):
        return raw_text.lstrip("/").strip()
    match = _TRIGGER_PREFIX_RE.match(raw_text)
    if match:
        remainder = raw_text[match.end():].strip()
        return remainder or "godmode status"
    if _auto_route_enabled_for_source(source):
        # Preserve slash/bang commands for Hermes unless they are explicit
        # hasystem/GODMODE controls above.
        if raw_text.startswith(("/", "!")):
            return None
        return raw_text
    return None


def _auto_route_enabled_for_source(source: Any) -> bool:
    configured = _auto_route_channel_ids()
    if not configured:
        return False
    return bool(_source_channel_ids(source) & configured)


def _auto_route_channel_ids() -> set[str]:
    # Do not infer automatic routing from router defaults or GODMODE authorization.
    # Those settings are broad enough to cover parent channels and many child
    # threads; treating them as auto-route allow-lists makes ordinary Discord
    # messages create hasystem issues unexpectedly. Automatic routing is opt-in
    # through a dedicated env var. Explicit `hasystem ...` and `godmode ...`
    # commands still route through the adapter.
    return _csv_env("HASYSTEM_GATEWAY_AUTO_ROUTE_CHANNEL_IDS")


def _event_envelope(*, event: Any, source: Any, content: str) -> dict[str, Any]:
    parent_channel_id = _str_or_none(getattr(source, "parent_chat_id", None)) or _str_or_none(getattr(source, "chat_id", None))
    thread_id = _str_or_none(getattr(source, "thread_id", None))
    if thread_id is None and _str_or_none(getattr(source, "parent_chat_id", None)):
        thread_id = _str_or_none(getattr(source, "chat_id", None))

    return {
        "platform": "discord",
        "guild_id": _str_or_none(getattr(source, "guild_id", None)),
        "channel_id": parent_channel_id,
        "channel_name": _channel_name(source),
        "thread_id": thread_id,
        "thread_name": _thread_name(source),
        "sender": {
            "id": _str_or_none(getattr(source, "user_id", None)),
            "display_name": _str_or_none(getattr(source, "user_name", None)),
        },
        "message_id": _str_or_none(getattr(event, "message_id", None)) or _str_or_none(getattr(source, "message_id", None)),
        "content": content,
    }


def _channel_name(source: Any) -> str | None:
    if _str_or_none(getattr(source, "parent_chat_id", None)):
        return None
    return _str_or_none(getattr(source, "chat_name", None))


def _thread_name(source: Any) -> str | None:
    if _str_or_none(getattr(source, "thread_id", None)) or _str_or_none(getattr(source, "parent_chat_id", None)):
        return _str_or_none(getattr(source, "chat_name", None))
    return None


def _adapter_command() -> list[str]:
    configured = os.environ.get("HASYSTEM_GATEWAY_ADAPTER_COMMAND", "").strip()
    if configured:
        return shlex.split(configured)
    default_wrapper = os.path.expanduser("~/.hermes/hasystem-gateway-runtime/hasystem-gateway-wrapper")
    if os.path.exists(default_wrapper):
        return [default_wrapper, "--live"]
    return ["hermes-gateway-adapter"]


async def _dispatch_and_send(prepared: PreparedDispatch, event: Any, gateway: Any) -> None:
    result = await asyncio.to_thread(_run_adapter_command, prepared.command, prepared.event)
    await _send_gateway_response(event, gateway, _format_result(result))


def _dispatch_and_send_sync(prepared: PreparedDispatch, event: Any, gateway: Any) -> None:
    result = _run_adapter_command(prepared.command, prepared.event)
    # Synchronous fallback is used only in tests or unusual dispatch contexts.
    sender = getattr(gateway, "send_sync", None)
    if callable(sender):
        sender(event, _format_result(result))


def _run_adapter_command(command: list[str], envelope: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*command, "--event-json", json.dumps(envelope, ensure_ascii=False)],
        text=True,
        capture_output=True,
        timeout=float(os.environ.get("HASYSTEM_GATEWAY_ADAPTER_TIMEOUT", "60")),
        check=False,
    )


async def _send_gateway_response(event: Any, gateway: Any, content: str) -> None:
    source = getattr(event, "source", None)
    adapter = getattr(gateway, "adapters", {}).get(getattr(source, "platform", None)) if gateway is not None else None
    if adapter is None:
        return

    reply_to = _str_or_none(getattr(event, "message_id", None)) or _str_or_none(getattr(source, "message_id", None))
    metadata = None
    thread_meta = getattr(gateway, "_thread_metadata_for_source", None)
    if callable(thread_meta):
        try:
            metadata = thread_meta(source, reply_to)
        except Exception:
            metadata = None
    if metadata is None:
        metadata = {"thread_id": _str_or_none(getattr(source, "thread_id", None))} if _str_or_none(getattr(source, "thread_id", None)) else None

    send_with_retry = getattr(adapter, "_send_with_retry", None)
    if callable(send_with_retry):
        maybe = send_with_retry(
            chat_id=getattr(source, "chat_id", None),
            content=content,
            reply_to=reply_to,
            metadata=metadata,
        )
        if inspect.isawaitable(maybe):
            await maybe
        return

    send = getattr(adapter, "send", None)
    if callable(send):
        maybe = send(getattr(source, "chat_id", None), content)
        if asyncio.iscoroutine(maybe):
            await maybe


def _format_result(result: subprocess.CompletedProcess[str]) -> str:
    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode == 0:
        body = _pretty_json_or_text(stdout)
        return f"hasystem adapter result:\n```json\n{_truncate(body)}\n```"
    details = _pretty_json_or_text(stderr or stdout or f"adapter exited with {result.returncode}")
    return f"hasystem adapter failed with exit code {result.returncode}:\n```json\n{_truncate(details)}\n```"


def _pretty_json_or_text(text: str) -> str:
    try:
        return json.dumps(json.loads(text), ensure_ascii=False, indent=2, sort_keys=True)
    except Exception:
        return text


def _truncate(text: str, limit: int = 1800) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n... <truncated>"


def _csv_env(name: str) -> set[str]:
    return {item.strip() for item in os.environ.get(name, "").split(",") if item.strip()}


def _str_or_none(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
