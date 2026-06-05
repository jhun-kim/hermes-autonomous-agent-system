from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from .discord_request import DiscordRequestParseError

JsonValue = Any
JsonObject = dict[str, JsonValue]


class GatewayEventPayloadSource(Protocol):
    platform: str
    guild_id: str | None
    channel_id: str | None
    thread_id: str | None
    sender_id: str | None
    sender_display_name: str | None
    session_id: str | None
    repo_hint: str | None
    latest_user_goal: str | None
    active_issue_number: int | None
    active_issue_title: str | None
    active_issue_labels: list[str]
    session_summary: str | None
    context_compaction: bool
    event_type: str | None


def load_config_file(path: Path) -> JsonObject:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise DiscordRequestParseError("YAML config requires PyYAML; use JSON config in this environment") from exc
        loaded = yaml.safe_load(text)
    else:
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DiscordRequestParseError(f"Router config JSON is invalid: {exc.msg}") from exc
    if not isinstance(loaded, dict):
        raise DiscordRequestParseError("Router config must be a JSON/YAML object")
    return loaded


def event_message(data: dict[str, JsonValue]) -> str:
    nested = json_object(data.get("message"))
    message = (
        optional_str(data.get("raw_message"))
        or optional_str(data.get("content"))
        or optional_str(data.get("text"))
        or optional_str(data.get("request"))
        or (optional_str(nested.get("content")) if nested else None)
        or (optional_str(nested.get("text")) if nested else None)
    )
    if not message:
        raise DiscordRequestParseError("Gateway event needs message.content, content, text, request, or raw_message")
    return message


def json_object(value: JsonValue | None) -> JsonObject | None:
    if isinstance(value, dict):
        return value
    return None


def optional_str(value: JsonValue | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def optional_bool(value: JsonValue | None) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def optional_int(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def event_type_is_context_compaction(value: str | None) -> bool:
    return value in {"context_compaction", "compaction", "context.compaction"}


def string_mapping(values: dict[str, JsonValue] | dict[str, str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for key, value in values.items():
        if isinstance(value, str) and key.strip() and value.strip():
            parsed[key.strip()] = value.strip()
    return parsed


def normalized_mapping(values: dict[str, JsonValue] | dict[str, str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for key, value in string_mapping(values).items():
        parsed[key] = value
        parsed[key.lower()] = value
    return parsed


def string_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def event_payload(event: GatewayEventPayloadSource) -> JsonObject:
    return {
        "type": event.event_type or ("context.compaction" if event.context_compaction else None),
        "platform": event.platform,
        "guild_id": event.guild_id,
        "channel_id": event.channel_id,
        "thread_id": event.thread_id,
        "sender_id": event.sender_id,
        "sender_display_name": event.sender_display_name,
        "session_id": event.session_id,
        "repo": event.repo_hint,
        "latest_user_goal": event.latest_user_goal,
        "active_issue": {
            "number": event.active_issue_number,
            "title": event.active_issue_title,
            "labels": event.active_issue_labels,
        }
        if event.active_issue_number is not None
        else None,
        "session_summary": event.session_summary,
    }
