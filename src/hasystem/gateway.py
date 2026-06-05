from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .gateway_parsing import (
    event_message as _event_message,
    event_payload as _event_payload,
    event_type_is_context_compaction as _event_type_is_context_compaction,
    json_object as _json_object,
    load_config_file as _load_config_file,
    normalized_mapping as _normalized_mapping,
    optional_bool as _optional_bool,
    optional_int as _optional_int,
    optional_str as _optional_str,
    string_list as _string_list,
    string_mapping as _string_mapping,
)

from .discord_request import (
    DiscordAutomationResult,
    DiscordAutomationService,
    DiscordRequestParseError,
    DiscordRequestRouterConfig,
)
from .godmode import GodmodeAction, GodmodeAuthorizationError, GodmodeConfig, GodmodeContext, GodmodeResult, GodmodeService, parse_godmode_command
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
    new_session_id: str | None = None
    latest_user_goal: str | None = None
    session_summary: str | None = None
    compression_summary: str | None = None
    handoff_context: str | None = None
    active_issue_number: int | None = None
    active_issue_title: str | None = None
    active_issue_labels: list[str] = field(default_factory=list)
    context_compaction: bool = False
    event_type: str | None = None
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
        event_type = _optional_str(data.get("event_type")) or _optional_str(data.get("type"))
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
            new_session_id=_optional_str(data.get("new_session_id")),
            latest_user_goal=_optional_str(data.get("latest_user_goal")),
            session_summary=_optional_str(data.get("session_summary")) or _optional_str(data.get("summary")),
            compression_summary=_optional_str(data.get("compression_summary")),
            handoff_context=_optional_str(data.get("handoff_context")),
            active_issue_number=_optional_int(data.get("active_issue_number")),
            active_issue_title=_optional_str(data.get("active_issue_title")),
            active_issue_labels=_string_list(data.get("active_issue_labels")),
            context_compaction=(
                _optional_bool(data.get("context_compaction"))
                or _event_type_is_context_compaction(event_type)
            ),
            event_type=event_type,
            dry_run=_optional_bool(data.get("dry_run")) or False,
            no_run_loop=_optional_bool(data.get("no_run_loop")) or False,
        )

    def message_for_routing(self) -> str:
        if self.repo_hint is None:
            return self.raw_message
        return json.dumps({"repo": self.repo_hint, "request": self.raw_message})

    def conversation_id(self) -> str:
        stable_id = self.thread_id or self.channel_id or self.sender_id or self.session_id or "unknown"
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
    godmode_config = _godmode_config(raw_config)

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
        godmode=godmode_config,
    )



def _godmode_config(raw_config: JsonObject) -> GodmodeConfig:
    raw_godmode = _json_object(raw_config.get("godmode")) or {}
    return GodmodeConfig(
        authorized_channel_ids=frozenset(_string_list(raw_godmode.get("authorized_channel_ids"))),
        authorized_sender_ids=frozenset(_string_list(raw_godmode.get("authorized_sender_ids"))),
        max_iterations=_optional_int(raw_godmode.get("max_iterations")) or 3,
        max_runtime_seconds=_optional_int(raw_godmode.get("max_runtime_seconds")) or 300,
        max_failures=_optional_int(raw_godmode.get("max_failures")) or 1,
        create_issue_when_empty=_optional_bool(raw_godmode.get("create_issue_when_empty")) or False,
        seed_issue_title=_optional_str(raw_godmode.get("seed_issue_title")) or "GODMODE follow-up task",
        seed_issue_body=(
            _optional_str(raw_godmode.get("seed_issue_body")) or GodmodeConfig().seed_issue_body
        ),
        seed_issue_labels=tuple(_string_list(raw_godmode.get("seed_issue_labels"))) or GodmodeConfig().seed_issue_labels,
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
    godmode_action = parse_godmode_command(event.raw_message)
    if godmode_action is not None:
        return _godmode_payload(service=service, event=event, action=godmode_action)
    result = service.handle(
        event.message_for_routing(),
        dry_run=dry_run,
        run_loop=not no_run_loop,
        channel_id=event.channel_id,
        thread_id=event.thread_id,
        sender_id=event.sender_id,
    )
    return _automation_result_payload(result=result, event=event, no_run_loop=no_run_loop)



def _godmode_payload(*, service: DiscordAutomationService, event: DiscordGatewayEvent, action: GodmodeAction) -> JsonObject:
    repo_raw = event.repo_hint or service.router_config.default_for_context(
        channel_id=event.channel_id,
        thread_id=event.thread_id,
    )
    if repo_raw is None:
        raise DiscordRequestParseError("godmode requires a configured repo hint or channel/default repo")
    repo = service.router_config.ensure_allowed(repo_raw)
    try:
        result = GodmodeService(
            loop_runner=service.loop_runner,
            config=service.router_config.godmode,
        ).handle(
            action,
            GodmodeContext(
                conversation_id=event.conversation_id(),
                repo=repo,
                channel_id=event.channel_id,
                thread_id=event.thread_id,
                sender_id=event.sender_id,
            ),
        )
    except GodmodeAuthorizationError as exc:
        raise DiscordRequestParseError(str(exc)) from exc
    return {
        "status": _godmode_status(result),
        "platform": event.platform,
        "event": _event_payload(event),
        "godmode": _godmode_result_payload(result),
    }


def _godmode_status(result: GodmodeResult) -> str:
    if result.action == "status":
        return "godmode_status"
    return f"godmode_{result.session.status}"


def _godmode_result_payload(result: GodmodeResult) -> JsonObject:
    session = result.session
    return {
        "action": result.action,
        "conversation_id": session.conversation_id,
        "repo": session.repo,
        "status": session.status,
        "iterations": session.iterations,
        "failures": session.failures,
        "last_issue": {"number": session.last_issue_number, "title": session.last_issue_title}
        if session.last_issue_number is not None
        else None,
        "stop_reason": session.stop_reason,
        "evidence": session.evidence,
        "started_at": session.started_at,
        "updated_at": session.updated_at,
    }

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
