from __future__ import annotations

from dataclasses import dataclass

from .compaction_rollover import DiscordContinuationClient
from .discord_request import DiscordAutomationService
from .gateway import DiscordGatewayEvent, JsonObject, build_gateway_response
from .state_store import StateStore


@dataclass(frozen=True, slots=True)
class ActiveIssueContext:
    """GitHub issue metadata active when Hermes compressed the session."""

    number: int
    title: str
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class HermesContextCompression:
    """Hermes context-compression record at the session boundary."""

    platform: str
    guild_id: str | None = None
    channel_id: str | None = None
    thread_id: str | None = None
    session_id: str | None = None
    repo_hint: str | None = None
    latest_goal: str | None = None
    active_issue: ActiveIssueContext | None = None
    compression_summary: str | None = None
    handoff_context: str | None = None

    def to_gateway_event(self) -> DiscordGatewayEvent:
        return DiscordGatewayEvent(
            raw_message=self.latest_goal or "Hermes context compression",
            platform=self.platform,
            guild_id=self.guild_id,
            channel_id=self.channel_id,
            thread_id=self.thread_id,
            repo_hint=self.repo_hint,
            session_id=self.session_id,
            latest_user_goal=self.latest_goal,
            session_summary=_session_summary(
                compression_summary=self.compression_summary,
                handoff_context=self.handoff_context,
            ),
            active_issue_number=self.active_issue.number if self.active_issue is not None else None,
            active_issue_title=self.active_issue.title if self.active_issue is not None else None,
            active_issue_labels=list(self.active_issue.labels) if self.active_issue is not None else [],
            context_compaction=True,
            event_type="context.compaction",
        )


@dataclass(frozen=True, slots=True)
class HermesContextCompressionDispatchConfig:
    """Config gate for repo-specific Hermes compression rollover integration."""

    enabled: bool = False


@dataclass(frozen=True, slots=True)
class HermesContextCompressionDispatchResult:
    """Observable result of attempting to dispatch a Hermes compression event."""

    dispatched: bool
    reason: str
    payload: JsonObject | None = None


def dispatch_hermes_context_compression(
    *,
    compression: HermesContextCompression,
    config: HermesContextCompressionDispatchConfig,
    service: DiscordAutomationService,
    state_store: StateStore,
    discord_client: DiscordContinuationClient | None = None,
) -> HermesContextCompressionDispatchResult:
    """Dispatch enabled Discord compression records through the gateway adapter."""
    if not config.enabled:
        return HermesContextCompressionDispatchResult(
            dispatched=False,
            reason="context compaction dispatch is disabled",
        )
    if compression.platform != "discord":
        return HermesContextCompressionDispatchResult(
            dispatched=False,
            reason="context compaction dispatch only supports Discord sessions",
        )

    payload = build_gateway_response(
        service=service,
        event=compression.to_gateway_event(),
        dry_run_override=None,
        no_run_loop_override=None,
        state_store=state_store,
        discord_client=discord_client,
    )
    return HermesContextCompressionDispatchResult(
        dispatched=True,
        reason="context compaction dispatched to gateway adapter",
        payload=payload,
    )


def _session_summary(*, compression_summary: str | None, handoff_context: str | None) -> str | None:
    parts = []
    if compression_summary:
        parts.append(compression_summary)
    if handoff_context:
        parts.append(f"Handoff context: {handoff_context}")
    if not parts:
        return None
    return "\n".join(parts)
