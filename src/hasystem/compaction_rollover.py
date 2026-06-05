from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol, Final
from urllib import error, request

from .gateway import DiscordGatewayEvent
from .models import GatewayConversationState, utc_now_iso
from .state_store import StateStore

DEFAULT_COMPACTION_ROLLOVER_THRESHOLD: Final = 7


@dataclass(frozen=True)
class RolloverConfig:
    threshold: int = DEFAULT_COMPACTION_ROLLOVER_THRESHOLD


@dataclass(frozen=True)
class DiscordCreatedThread:
    thread_id: str
    name: str
    url: str | None = None


class DiscordContinuationClient(Protocol):
    def create_public_thread(
        self,
        *,
        parent_channel_id: str,
        source_thread_id: str | None,
        name: str,
    ) -> DiscordCreatedThread: ...

    def post_message(self, *, channel_id: str, content: str) -> None: ...


@dataclass(frozen=True)
class DiscordRestContinuationClient:
    bot_token: str
    api_base_url: str = "https://discord.com/api/v10"

    def create_public_thread(
        self,
        *,
        parent_channel_id: str,
        source_thread_id: str | None,
        name: str,
    ) -> DiscordCreatedThread:
        payload = {"name": name, "type": 11, "auto_archive_duration": 1440}
        response = self._post_json(path=f"/channels/{parent_channel_id}/threads", payload=payload)
        thread_id = _json_string(response, "id")
        thread_name = _json_optional_string(response, "name") or name
        return DiscordCreatedThread(thread_id=thread_id, name=thread_name)

    def post_message(self, *, channel_id: str, content: str) -> None:
        self._post_json(path=f"/channels/{channel_id}/messages", payload={"content": content})

    def _post_json(self, *, path: str, payload: dict[str, str | int]) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.api_base_url}{path}",
            data=body,
            headers={
                "Authorization": f"Bot {self.bot_token}",
                "Content-Type": "application/json",
                "User-Agent": "HermesAutonomousAgentSystem/0.1",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except error.URLError as exc:
            raise DiscordContinuationError(detail=str(exc)) from exc
        if not isinstance(decoded, dict):
            raise DiscordContinuationError(detail="Discord API returned a non-object JSON response")
        return decoded


@dataclass(frozen=True)
class CompactionRolloverResult:
    conversation_id: str
    compaction_count: int
    threshold: int
    should_rollover: bool
    handoff_message: str | None = None
    new_conversation_id: str | None = None
    new_thread_id: str | None = None
    continuation_summary: str | None = None


@dataclass(frozen=True)
class DiscordContinuationError(RuntimeError):
    detail: str

    def __str__(self) -> str:
        return f"Discord continuation failed: {self.detail}"


def record_context_compaction(
    *,
    store: StateStore,
    event: DiscordGatewayEvent,
    config: RolloverConfig | None = None,
    discord_client: DiscordContinuationClient | None = None,
) -> CompactionRolloverResult:
    rollover_config = config or RolloverConfig()
    if rollover_config.threshold < 1:
        raise InvalidRolloverThresholdError(threshold=rollover_config.threshold)

    conversation_id = event.conversation_id()
    state = store.increment_gateway_compaction(
        conversation_id=conversation_id,
        platform=event.platform,
        guild_id=event.guild_id,
        channel_id=event.channel_id,
        thread_id=event.thread_id,
        repo=event.repo_hint,
        latest_user_goal=event.latest_user_goal or event.raw_message,
        latest_summary=event.session_summary,
        active_issue_number=event.active_issue_number,
        active_issue_title=event.active_issue_title,
        active_issue_labels=event.active_issue_labels,
    )
    if state.compaction_count < rollover_config.threshold:
        return CompactionRolloverResult(
            conversation_id=conversation_id,
            compaction_count=state.compaction_count,
            threshold=rollover_config.threshold,
            should_rollover=False,
        )
    if state.continuation_conversation_id is not None:
        return CompactionRolloverResult(
            conversation_id=conversation_id,
            compaction_count=state.compaction_count,
            threshold=rollover_config.threshold,
            should_rollover=False,
            handoff_message="Rollover was already created for this conversation.",
            new_conversation_id=state.continuation_conversation_id,
            new_thread_id=state.continuation_thread_id,
        )

    if event.platform == "discord":
        return _rollover_discord(
            store=store,
            state=state,
            event=event,
            threshold=rollover_config.threshold,
            discord_client=discord_client,
        )
    return _rollover_neutral(state=state, threshold=rollover_config.threshold)


def _rollover_discord(
    *,
    store: StateStore,
    state: GatewayConversationState,
    event: DiscordGatewayEvent,
    threshold: int,
    discord_client: DiscordContinuationClient | None,
) -> CompactionRolloverResult:
    summary = _continuity_summary(state=state, event=event, threshold=threshold)
    if event.channel_id is None or discord_client is None:
        message = _neutral_handoff_message(threshold=threshold, summary=summary)
        return CompactionRolloverResult(
            conversation_id=state.conversation_id,
            compaction_count=state.compaction_count,
            threshold=threshold,
            should_rollover=True,
            handoff_message=message,
            continuation_summary=summary,
        )

    thread_name = f"Hermes continuation after {threshold} compactions"
    created = discord_client.create_public_thread(
        parent_channel_id=event.channel_id,
        source_thread_id=event.thread_id,
        name=thread_name,
    )
    new_conversation_id = f"discord:{created.thread_id}"
    handoff = _discord_handoff_message(threshold=threshold, created=created)
    old_target_id = event.thread_id or event.channel_id
    discord_client.post_message(channel_id=old_target_id, content=handoff)
    discord_client.post_message(channel_id=created.thread_id, content=summary)
    store.create_gateway_continuation(
        old_conversation_id=state.conversation_id,
        new_state=GatewayConversationState(
            conversation_id=new_conversation_id,
            platform="discord",
            guild_id=event.guild_id,
            channel_id=event.channel_id,
            thread_id=created.thread_id,
            repo=event.repo_hint,
            latest_user_goal=event.latest_user_goal or event.raw_message,
            latest_summary=event.session_summary,
            active_issue_number=event.active_issue_number,
            active_issue_title=event.active_issue_title,
            active_issue_labels=event.active_issue_labels,
            compaction_count=0,
            continuation_of=state.conversation_id,
            created_at=utc_now_iso(),
            updated_at=utc_now_iso(),
        ),
        continuation_thread_id=created.thread_id,
    )
    return CompactionRolloverResult(
        conversation_id=state.conversation_id,
        compaction_count=state.compaction_count,
        threshold=threshold,
        should_rollover=True,
        handoff_message=handoff,
        new_conversation_id=new_conversation_id,
        new_thread_id=created.thread_id,
        continuation_summary=summary,
    )


def _rollover_neutral(*, state: GatewayConversationState, threshold: int) -> CompactionRolloverResult:
    summary = _continuity_summary_from_state(state=state, threshold=threshold)
    return CompactionRolloverResult(
        conversation_id=state.conversation_id,
        compaction_count=state.compaction_count,
        threshold=threshold,
        should_rollover=True,
        handoff_message=_neutral_handoff_message(threshold=threshold, summary=summary),
        continuation_summary=summary,
    )


def _discord_handoff_message(*, threshold: int, created: DiscordCreatedThread) -> str:
    target = created.url or created.thread_id
    return f"Hermes is rolling over after {threshold} context compactions. Continue in {created.name}: {target}"


def _neutral_handoff_message(*, threshold: int, summary: str) -> str:
    return f"Hermes reached {threshold} context compactions. Start a fresh continuation session with this handoff:\n{summary}"


def _continuity_summary(*, state: GatewayConversationState, event: DiscordGatewayEvent, threshold: int) -> str:
    latest_goal = event.latest_user_goal or state.latest_user_goal or event.raw_message
    summary = event.session_summary or state.latest_summary or "No prior summary was provided."
    issue = _issue_line(state=state)
    return (
        f"Hermes continuation handoff after {threshold} context compactions.\n"
        f"Original platform: {state.platform}; channel: {state.channel_id}; thread: {state.thread_id}.\n"
        f"Repo: {state.repo or 'unknown'}.\n"
        f"Latest user goal: {latest_goal}.\n"
        f"{issue}\n"
        f"Prior session summary: {summary}\n"
        "Compaction count has been reset for this continuation."
    )


def _continuity_summary_from_state(*, state: GatewayConversationState, threshold: int) -> str:
    issue = _issue_line(state=state)
    return (
        f"Hermes continuation handoff after {threshold} context compactions.\n"
        f"Original platform: {state.platform}; channel: {state.channel_id}; thread: {state.thread_id}.\n"
        f"Repo: {state.repo or 'unknown'}.\n"
        f"Latest user goal: {state.latest_user_goal or 'unknown'}.\n"
        f"{issue}\n"
        f"Prior session summary: {state.latest_summary or 'No prior summary was provided.'}"
    )


def _issue_line(*, state: GatewayConversationState) -> str:
    if state.active_issue_number is None:
        return "Active issue: unknown."
    title = state.active_issue_title or "untitled"
    labels = ", ".join(state.active_issue_labels)
    labels_text = labels if labels else "none"
    return f"Active issue: #{state.active_issue_number} {title}; labels: {labels_text}."


def _json_string(values: dict[str, object], key: str) -> str:
    value = values.get(key)
    if isinstance(value, str) and value:
        return value
    raise DiscordContinuationError(detail=f"Discord API response missing string field {key}")


def _json_optional_string(values: dict[str, object], key: str) -> str | None:
    value = values.get(key)
    if isinstance(value, str) and value:
        return value
    return None


@dataclass(frozen=True)
class InvalidRolloverThresholdError(ValueError):
    threshold: int

    def __str__(self) -> str:
        return f"Compaction rollover threshold must be at least 1, got {self.threshold}"
