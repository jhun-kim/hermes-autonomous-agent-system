from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .discord_request import (
    DiscordAutomationResult,
    DiscordAutomationService,
    DiscordRequestParseError,
    DiscordRequestRouterConfig,
)
from .intake import IntakeResult
from .loop_runner import RunLoopResult
from .state_store import StateStore

JsonValue = Any
JsonObject = dict[str, JsonValue]

@dataclass(frozen=True)
class DiscordGatewayEvent:
    """First-class Discord/Gateway event envelope accepted by Hermes."""

    raw_message: str
    platform: str = "discord"
    guild_id: str | None = None
    channel_id: str | None = None
    thread_id: str | None = None
    sender_id: str | None = None
    sender_display_name: str | None = None
    repo_hint: str | None = None
    session_id: str | None = None
    latest_user_goal: str | None = None
    session_summary: str | None = None
    active_issue_number: int | None = None
    active_issue_title: str | None = None
    active_issue_labels: list[str] = field(default_factory=list)
    context_compaction: bool = False
    dry_run: bool = False
    no_run_loop: bool = False

    @classmethod
    def from_json(cls, event_json: str) -> "DiscordGatewayEvent":
        try:
            data = json.loads(event_json)
        except json.JSONDecodeError as exc:
            raise DiscordRequestParseError(f"Gateway event JSON is invalid: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise DiscordRequestParseError("Gateway event JSON must be an object")
        return cls.from_mapping(data)

    @classmethod
    def from_mapping(cls, data: dict[str, JsonValue]) -> "DiscordGatewayEvent":
        message = _event_message(data)
        sender = _json_object(data.get("sender")) or _json_object(data.get("author")) or {}
        return cls(
            raw_message=message,
            platform=_optional_str(data.get("platform")) or "discord",
            guild_id=_optional_str(data.get("guild_id")),
            channel_id=_optional_str(data.get("channel_id")),
            thread_id=_optional_str(data.get("thread_id")),
            sender_id=_optional_str(data.get("sender_id")) or _optional_str(sender.get("id")),
            sender_display_name=(
                _optional_str(data.get("sender_display_name"))
                or _optional_str(data.get("display_name"))
                or _optional_str(sender.get("display_name"))
                or _optional_str(sender.get("username"))
            ),
            repo_hint=_optional_str(data.get("repo")) or _optional_str(data.get("repository")) or _optional_str(data.get("repo_hint")),
            session_id=_optional_str(data.get("session_id")) or _optional_str(data.get("conversation_id")),
            latest_user_goal=_optional_str(data.get("latest_user_goal")),
            session_summary=_optional_str(data.get("session_summary")) or _optional_str(data.get("summary")),
            active_issue_number=_optional_int(data.get("active_issue_number")),
            active_issue_title=_optional_str(data.get("active_issue_title")),
            active_issue_labels=_string_list(data.get("active_issue_labels")),
            context_compaction=(
                _optional_bool(data.get("context_compaction"))
                or _event_type_is_context_compaction(_optional_str(data.get("event_type")) or _optional_str(data.get("type")))
            ),
            dry_run=_optional_bool(data.get("dry_run")) or False,
            no_run_loop=_optional_bool(data.get("no_run_loop")) or False,
        )

    def message_for_routing(self) -> str:
        if self.repo_hint is None:
            return self.raw_message
        return json.dumps({"repo": self.repo_hint, "request": self.raw_message})

    def conversation_id(self) -> str:
        stable_id = self.session_id or self.thread_id or self.channel_id or self.sender_id or "unknown"
        return f"{self.platform}:{stable_id}"


def load_router_config(
    path: Path | None,
    *,
    repo_alias_overrides: dict[str, str] | None = None,
    channel_default_repo_overrides: dict[str, str] | None = None,
    default_repo_override: str | None = None,
    allow_repo_overrides: frozenset[str] | None = None,
) -> DiscordRequestRouterConfig:
    raw_config = _load_config_file(path) if path is not None else {}
    repo_aliases = _normalized_mapping(_json_object(raw_config.get("repo_aliases")) or {})
    channel_defaults = _string_mapping(_json_object(raw_config.get("channel_default_repos")) or {})
    default_repo = _optional_str(raw_config.get("default_repo"))
    allow_repos = frozenset(_string_list(raw_config.get("allow_repos")))
    threshold = _optional_int(raw_config.get("compaction_rollover_threshold")) or 7

    if repo_alias_overrides:
        repo_aliases.update(_normalized_mapping(repo_alias_overrides))
    if channel_default_repo_overrides:
        channel_defaults.update(channel_default_repo_overrides)
    if default_repo_override:
        default_repo = default_repo_override
    if allow_repo_overrides is not None:
        allow_repos = allow_repo_overrides

    return DiscordRequestRouterConfig(
        repo_aliases=repo_aliases,
        default_repo=default_repo,
        channel_default_repos=channel_defaults,
        allow_repos=allow_repos,
        compaction_rollover_threshold=threshold,
    )


def build_gateway_response(
    *,
    service: DiscordAutomationService,
    event: DiscordGatewayEvent,
    dry_run_override: bool | None,
    no_run_loop_override: bool | None,
    state_store: StateStore | None = None,
    discord_client: Any | None = None,
) -> JsonObject:
    dry_run = event.dry_run if dry_run_override is None else dry_run_override
    no_run_loop = event.no_run_loop if no_run_loop_override is None else no_run_loop_override
    if event.context_compaction:
        return _compaction_rollover_payload(
            event=event,
            service=service,
            state_store=state_store,
            discord_client=discord_client,
        )
    result = service.handle(
        event.message_for_routing(),
        dry_run=dry_run,
        run_loop=not no_run_loop,
        channel_id=event.channel_id,
        thread_id=event.thread_id,
    )
    return _automation_result_payload(result=result, event=event, no_run_loop=no_run_loop)


def _compaction_rollover_payload(
    *,
    event: DiscordGatewayEvent,
    service: DiscordAutomationService,
    state_store: StateStore | None,
    discord_client: Any | None,
) -> JsonObject:
    if state_store is None:
        return {
            "status": "compaction_seen",
            "platform": event.platform,
            "event": _event_payload(event),
            "continuation": {
                "should_rollover": False,
                "reason": "No state store was provided, so compaction count was not persisted.",
            },
        }
    from .compaction_rollover import RolloverConfig, record_context_compaction

    result = record_context_compaction(
        store=state_store,
        event=event,
        config=RolloverConfig(threshold=service.router_config.compaction_rollover_threshold),
        discord_client=discord_client,
    )
    return {
        "status": "rollover_required" if result.should_rollover else "compaction_recorded",
        "platform": event.platform,
        "event": _event_payload(event),
        "continuation": {
            "conversation_id": result.conversation_id,
            "compaction_count": result.compaction_count,
            "threshold": result.threshold,
            "should_rollover": result.should_rollover,
            "new_conversation_id": result.new_conversation_id,
            "new_thread_id": result.new_thread_id,
            "handoff_message": result.handoff_message,
            "summary": result.continuation_summary,
        },
    }


def _automation_result_payload(
    *, result: DiscordAutomationResult, event: DiscordGatewayEvent, no_run_loop: bool
) -> JsonObject:
    status = "dry_run" if result.dry_run else "accepted"
    if not result.dry_run and result.loop is None:
        status = "intake_only" if no_run_loop else "no_ready_issue"
    payload: JsonObject = {
        "status": status,
        "platform": event.platform,
        "repo": result.request.repo_raw,
        "parsed_request": {"repo_raw": result.request.repo_raw, "request_text": result.request.request_text},
        "event": {
            **_event_payload(event),
        },
        "dry_run": result.dry_run,
        "intake": _intake_payload(result.intake),
        "loop": _loop_payload(result.loop),
        "hints": _hints_payload(result=result, no_run_loop=no_run_loop),
    }
    return payload


def _event_payload(event: DiscordGatewayEvent) -> JsonObject:
    return {
        "guild_id": event.guild_id,
        "channel_id": event.channel_id,
        "thread_id": event.thread_id,
        "sender_id": event.sender_id,
        "sender_display_name": event.sender_display_name,
        "session_id": event.session_id,
    }


def _intake_payload(result: IntakeResult | None) -> JsonObject | None:
    if result is None:
        return None
    return {"repo": result.repo.full_name, "local_path": str(result.local_path), "issue_number": result.issue_number}


def _loop_payload(result: RunLoopResult | None) -> JsonObject | None:
    if result is None:
        return None
    return {
        "loop_id": result.loop.loop_id,
        "issue": {
            "number": result.loop.issue.number,
            "title": result.loop.issue.title,
            "labels": result.loop.issue.labels,
        },
        "branch": result.loop.branch,
        "executor": result.loop.executor,
        "phase": result.loop.phase,
        "worker": {
            "executable": result.worker_command.args[0] if result.worker_command.args else None,
            "launched": not result.existing_active,
            "existing_active": result.existing_active,
        },
    }


def _hints_payload(*, result: DiscordAutomationResult, no_run_loop: bool) -> JsonObject:
    if result.dry_run:
        return {"next_action": "Remove dry-run to create an issue and optionally start the run loop."}
    if no_run_loop:
        return {"next_action": "Run hermes-run-loop or /restart a fresh agent session when ready to execute."}
    if result.loop is None:
        return {"next_action": "No ai:ready issue was selected; review labels or run intake-only mode."}
    return {"next_action": "Watch the worker session; finalize requires approval before PR/label changes."}


def _load_config_file(path: Path) -> JsonObject:
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


def _event_message(data: dict[str, JsonValue]) -> str:
    nested = _json_object(data.get("message"))
    message = (
        _optional_str(data.get("raw_message"))
        or _optional_str(data.get("content"))
        or _optional_str(data.get("text"))
        or _optional_str(data.get("request"))
        or (_optional_str(nested.get("content")) if nested else None)
        or (_optional_str(nested.get("text")) if nested else None)
    )
    if not message:
        raise DiscordRequestParseError("Gateway event needs message.content, content, text, request, or raw_message")
    return message


def _json_object(value: JsonValue | None) -> JsonObject | None:
    if isinstance(value, dict):
        return value
    return None


def _optional_str(value: JsonValue | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _optional_bool(value: JsonValue | None) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _optional_int(value: JsonValue | None) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _event_type_is_context_compaction(value: str | None) -> bool:
    return value in {"context_compaction", "compaction", "context.compaction"}


def _string_mapping(values: dict[str, JsonValue] | dict[str, str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for key, value in values.items():
        if isinstance(value, str) and key.strip() and value.strip():
            parsed[key.strip()] = value.strip()
    return parsed


def _normalized_mapping(values: dict[str, JsonValue] | dict[str, str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for key, value in _string_mapping(values).items():
        parsed[key] = value
        parsed[key.lower()] = value
    return parsed


def _string_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
