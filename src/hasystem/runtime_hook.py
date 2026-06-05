from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .compaction_rollover import DiscordContinuationClient
from .discord_request import DiscordAutomationService
from .hermes_context import (
    ActiveIssueContext,
    HermesContextCompression,
    HermesContextCompressionDispatchConfig,
    HermesContextCompressionDispatchResult,
    dispatch_hermes_context_compression,
)
from .state_store import StateStore

JsonValue = Any
JsonObject = dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class HermesRuntimeHookParseError(ValueError):
    detail: str

    def __str__(self) -> str:
        return f"Hermes runtime hook payload is invalid: {self.detail}"


@dataclass(frozen=True, slots=True)
class HermesCompressionLifecycle:
    """Successful live Hermes compression boundary after session rotation."""

    old_session_id: str
    new_session_id: str
    compression: HermesContextCompression

    @classmethod
    def from_runtime_hook(cls, data: JsonObject) -> "HermesCompressionLifecycle":
        session = _object(data.get("session")) or {}
        old_session_id = (
            _string(data.get("old_session_id"))
            or _string(session.get("old_id"))
            or _string(session.get("parent_id"))
        )
        new_session_id = (
            _string(data.get("new_session_id"))
            or _string(data.get("session_id"))
            or _string(session.get("new_id"))
            or _string(session.get("id"))
        )
        if old_session_id is None or new_session_id is None:
            raise HermesRuntimeHookParseError("compression lifecycle needs old and new session ids")
        if old_session_id == new_session_id:
            raise HermesRuntimeHookParseError("compression lifecycle did not rotate sessions")
        return cls(
            old_session_id=old_session_id,
            new_session_id=new_session_id,
            compression=compression_from_runtime_hook(
                data,
                session_id=old_session_id,
                new_session_id=new_session_id,
            ),
        )


def dispatch_runtime_context_compression(
    *,
    data: JsonObject,
    config: HermesContextCompressionDispatchConfig,
    service: DiscordAutomationService,
    state_store: StateStore,
    discord_client: DiscordContinuationClient | None = None,
) -> HermesContextCompressionDispatchResult:
    """Dispatch a successful live Hermes old-session to new-session compression event."""
    lifecycle = HermesCompressionLifecycle.from_runtime_hook(data)
    return dispatch_hermes_context_compression(
        compression=lifecycle.compression,
        config=config,
        service=service,
        state_store=state_store,
        discord_client=discord_client,
    )


def compression_from_runtime_hook(
    data: JsonObject,
    *,
    session_id: str | None = None,
    new_session_id: str | None = None,
) -> HermesContextCompression:
    """Parse the live Hermes context-compression hook shape into the dispatch model."""
    discord = _object(data.get("discord")) or {}
    session = _object(data.get("session")) or {}
    compression = _object(data.get("compression")) or {}
    active_issue = _active_issue(data.get("active_issue"))
    return HermesContextCompression(
        platform=_string(data.get("platform")) or "unknown",
        guild_id=_string(data.get("guild_id")) or _string(discord.get("guild_id")),
        channel_id=_string(data.get("channel_id")) or _string(discord.get("channel_id")),
        thread_id=_string(data.get("thread_id")) or _string(discord.get("thread_id")),
        session_id=session_id or _string(data.get("session_id")) or _string(data.get("conversation_id")) or _string(session.get("id")),
        repo_hint=_string(data.get("repo")) or _string(data.get("repository")) or _string(data.get("repo_hint")),
        latest_goal=_string(data.get("latest_goal")) or _string(data.get("latest_user_goal")),
        active_issue=active_issue,
        compression_summary=_string(data.get("compression_summary")) or _string(compression.get("summary")),
        handoff_context=_string(data.get("handoff_context")) or _string(compression.get("handoff_context")),
        new_session_id=new_session_id,
    )


def runtime_hook_enabled(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _active_issue(value: JsonValue | None) -> ActiveIssueContext | None:
    issue = _object(value)
    if issue is None:
        return None
    number = issue.get("number")
    title = _string(issue.get("title"))
    if not isinstance(number, int) or isinstance(number, bool) or title is None:
        raise HermesRuntimeHookParseError("active_issue needs integer number and string title")
    return ActiveIssueContext(number=number, title=title, labels=tuple(_string_list(issue.get("labels"))))


def _object(value: JsonValue | None) -> JsonObject | None:
    if isinstance(value, dict):
        return value
    return None


def _string(value: JsonValue | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_list(value: JsonValue | None) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
