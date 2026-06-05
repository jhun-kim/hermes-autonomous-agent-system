from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hasystem.command_runner import RecordingCommandRunner
from hasystem.discord_request import DiscordAutomationService, DiscordRequestRouterConfig
from hasystem.github_client import GitHubClient
from hasystem.hermes_context import (
    ActiveIssueContext,
    HermesContextCompression,
    HermesContextCompressionDispatchConfig,
    dispatch_hermes_context_compression,
)
from hasystem.intake import IntakeService
from hasystem.loop_runner import RunLoopService
from hasystem.state_store import StateStore
from hasystem.worker import CodexWorkerLauncher
from hasystem.workspace import Workspace


def test_builds_context_compaction_event_with_required_handoff_metadata() -> None:
    # Given: a real Hermes Discord session compression record with repo, goal, issue, and handoff context.
    compression = HermesContextCompression(
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        session_id="session-1",
        repo_hint="owner/repo",
        latest_goal="finish issue #22",
        active_issue=ActiveIssueContext(number=22, title="Wire real Hermes compression", labels=("ai:in-progress",)),
        compression_summary="Compressed last 80 messages into a compact state.",
        handoff_context="Continue from the gateway adapter wiring tests.",
    )

    # When: Hermes converts the compression record to the gateway event contract.
    event = compression.to_gateway_event()

    # Then: it emits a type=context.compaction Discord gateway event with all rollover metadata preserved.
    assert event.context_compaction is True
    assert event.platform == "discord"
    assert event.guild_id == "guild-1"
    assert event.channel_id == "channel-1"
    assert event.thread_id == "thread-1"
    assert event.session_id == "session-1"
    assert event.repo_hint == "owner/repo"
    assert event.latest_user_goal == "finish issue #22"
    assert event.active_issue_number == 22
    assert event.active_issue_title == "Wire real Hermes compression"
    assert event.active_issue_labels == ["ai:in-progress"]
    assert "Compressed last 80 messages" in (event.session_summary or "")
    assert "Continue from the gateway adapter" in (event.session_summary or "")


def test_dispatch_noops_when_disabled_or_not_discord(tmp_path: Path) -> None:
    # Given: configured-safe defaults and a state store that would mutate if dispatch ran.
    runner = RecordingCommandRunner([])
    store = StateStore(tmp_path / "state.db")
    service = _service(tmp_path=tmp_path, store=store, runner=runner, threshold=1)
    disabled = HermesContextCompressionDispatchConfig(enabled=False)
    non_discord = HermesContextCompressionDispatchConfig(enabled=True)

    # When: dispatch is disabled or the compression is not from Discord.
    disabled_result = dispatch_hermes_context_compression(
        compression=_compression(platform="discord"),
        config=disabled,
        service=service,
        state_store=store,
    )
    non_discord_result = dispatch_hermes_context_compression(
        compression=_compression(platform="cli"),
        config=non_discord,
        service=service,
        state_store=store,
    )

    # Then: both paths are explicit no-ops and no gateway conversation state is created.
    assert disabled_result.dispatched is False
    assert disabled_result.reason == "context compaction dispatch is disabled"
    assert non_discord_result.dispatched is False
    assert non_discord_result.reason == "context compaction dispatch only supports Discord sessions"
    assert store.get_gateway_conversation("discord:session-1") is None
    assert store.get_gateway_conversation("cli:session-1") is None
    assert runner.commands == []


def test_low_threshold_automatic_compression_dispatch_triggers_rollover(tmp_path: Path) -> None:
    # Given: the Hermes compression hook is enabled with a threshold of one and a fake Discord client.
    runner = RecordingCommandRunner([])
    store = StateStore(tmp_path / "state.db")
    service = _service(tmp_path=tmp_path, store=store, runner=runner, threshold=1)
    discord = FakeDiscordContinuationClient()

    # When: a real compression record is dispatched through the Hermes hook, not by invoking wrapper --event-json.
    result = dispatch_hermes_context_compression(
        compression=_compression(platform="discord"),
        config=HermesContextCompressionDispatchConfig(enabled=True),
        service=service,
        state_store=store,
        discord_client=discord,
    )

    # Then: the existing hasystem rollover adapter receives the event and creates a continuation thread.
    assert result.dispatched is True
    assert result.payload is not None
    assert result.payload["status"] == "rollover_required"
    assert result.payload["event"]["repo"] == "owner/repo"
    assert result.payload["event"]["latest_user_goal"] == "finish issue #22"
    assert result.payload["event"]["active_issue"]["number"] == 22
    assert result.payload["continuation"]["new_thread_id"] == "thread-auto-new"
    assert discord.created_parent_channel_ids == ["channel-1"]
    assert discord.messages[0][0] == "thread-1"
    assert discord.messages[1][0] == "thread-auto-new"
    assert runner.commands == []


def _compression(*, platform: str) -> HermesContextCompression:
    return HermesContextCompression(
        platform=platform,
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        session_id="session-1",
        repo_hint="owner/repo",
        latest_goal="finish issue #22",
        active_issue=ActiveIssueContext(number=22, title="Wire real Hermes compression", labels=("ai:ready",)),
        compression_summary="Summary from automatic context compression.",
        handoff_context="Handoff for the next Hermes session.",
    )


def _service(*, tmp_path: Path, store: StateStore, runner: RecordingCommandRunner, threshold: int) -> DiscordAutomationService:
    workspace = Workspace(tmp_path / "workspace", runner)
    return DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=store,
            worker=CodexWorkerLauncher(runner=runner),
            github_factory=lambda repo: GitHubClient(repo=repo, runner=runner),
        ),
        router_config=DiscordRequestRouterConfig(default_repo="owner/repo", compaction_rollover_threshold=threshold),
    )


@dataclass
class FakeDiscordContinuationClient:
    created_parent_channel_ids: list[str] = field(default_factory=list)
    messages: list[tuple[str, str]] = field(default_factory=list)

    def create_public_thread(self, *, parent_channel_id: str, source_thread_id: str | None, name: str):
        from hasystem.compaction_rollover import DiscordCreatedThread

        self.created_parent_channel_ids.append(parent_channel_id)
        assert source_thread_id == "thread-1"
        assert name == "Hermes continuation after 1 compactions"
        return DiscordCreatedThread(thread_id="thread-auto-new", name=name)

    def post_message(self, *, channel_id: str, content: str) -> None:
        self.messages.append((channel_id, content))
