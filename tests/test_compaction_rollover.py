from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hasystem.compaction_rollover import (
    DEFAULT_COMPACTION_ROLLOVER_THRESHOLD,
    DiscordCreatedThread,
    RolloverConfig,
    record_context_compaction,
)
from hasystem.gateway import DiscordGatewayEvent
from hasystem.state_store import StateStore


def test_state_store_increments_compaction_count_deterministically(tmp_path: Path) -> None:
    # Given: a Discord gateway conversation below the rollover threshold.
    store = StateStore(tmp_path / "state.db")
    event = DiscordGatewayEvent(
        raw_message="continue issue #19",
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        repo_hint="owner/repo",
    )

    # When: six context compactions are recorded for the same conversation.
    results = [record_context_compaction(store=store, event=event) for _ in range(6)]

    # Then: counts are deterministic and no rollover happens before the default threshold of seven.
    assert DEFAULT_COMPACTION_ROLLOVER_THRESHOLD == 7
    assert [result.compaction_count for result in results] == [1, 2, 3, 4, 5, 6]
    assert all(not result.should_rollover for result in results)
    state = store.get_gateway_conversation("discord:thread-1")
    assert state is not None
    assert state.compaction_count == 6


def test_discord_rollover_creates_thread_posts_handoff_and_resets_count(tmp_path: Path) -> None:
    # Given: a Discord conversation one compaction away from rollover and a fake Discord client.
    store = StateStore(tmp_path / "state.db")
    event = DiscordGatewayEvent(
        raw_message="continue implementing issue #19",
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        sender_id="user-1",
        repo_hint="owner/repo",
        latest_user_goal="Implement issue #19 rollover",
        active_issue_number=19,
        active_issue_title="Auto-rollover Discord conversations after 7 context compactions",
        session_summary="Implemented state counting; needs Discord handoff.",
    )
    fake_discord = FakeDiscordContinuationClient()
    for _ in range(6):
        record_context_compaction(store=store, event=event, discord_client=fake_discord)

    # When: the seventh compaction is recorded.
    result = record_context_compaction(store=store, event=event, discord_client=fake_discord)

    # Then: Hermes creates a public continuation thread, posts both notices, and routes future state there.
    assert result.should_rollover is True
    assert result.compaction_count == 7
    assert result.new_conversation_id == "discord:thread-new"
    assert result.new_thread_id == "thread-new"
    assert result.handoff_message is not None
    assert "7 context compactions" in result.handoff_message
    assert fake_discord.created_threads == [
        {
            "parent_channel_id": "channel-1",
            "source_thread_id": "thread-1",
            "name": "Hermes continuation after 7 compactions",
        }
    ]
    assert fake_discord.messages[0][0] == "thread-1"
    assert "thread-new" in fake_discord.messages[0][1]
    assert fake_discord.messages[1][0] == "thread-new"
    assert "Implement issue #19 rollover" in fake_discord.messages[1][1]
    old_state = store.get_gateway_conversation("discord:thread-1")
    new_state = store.get_gateway_conversation("discord:thread-new")
    assert old_state is not None
    assert old_state.continuation_conversation_id == "discord:thread-new"
    assert new_state is not None
    assert new_state.compaction_count == 0
    assert new_state.continuation_of == "discord:thread-1"
    assert new_state.active_issue_number == 19


def test_unsupported_platform_rollover_noops_safely_without_discord_thread(tmp_path: Path) -> None:
    # Given: a non-Discord platform at the rollover threshold.
    store = StateStore(tmp_path / "state.db")
    event = DiscordGatewayEvent(
        raw_message="continue issue #19",
        platform="slack",
        channel_id="channel-1",
        repo_hint="owner/repo",
        latest_user_goal="Keep working",
        session_summary="Prior session summary.",
    )

    # When: the threshold compaction is recorded.
    result = None
    for _ in range(7):
        result = record_context_compaction(store=store, event=event)

    # Then: the platform-neutral continuation message is returned without creating a routed Discord thread.
    assert result is not None
    assert result.should_rollover is True
    assert result.new_thread_id is None
    assert result.new_conversation_id is None
    assert result.handoff_message is not None
    assert "Start a fresh continuation session" in result.handoff_message
    state = store.get_gateway_conversation("slack:channel-1")
    assert state is not None
    assert state.compaction_count == 7
    assert state.continuation_conversation_id is None


def test_rollover_threshold_is_configurable(tmp_path: Path) -> None:
    # Given: a gateway conversation configured to roll over after two compactions.
    store = StateStore(tmp_path / "state.db")
    event = DiscordGatewayEvent(raw_message="continue", platform="discord", channel_id="channel-1", thread_id="thread-1")
    config = RolloverConfig(threshold=2)
    fake_discord = FakeDiscordContinuationClient()

    # When: two compactions are recorded.
    first = record_context_compaction(store=store, event=event, config=config, discord_client=fake_discord)
    second = record_context_compaction(store=store, event=event, config=config, discord_client=fake_discord)

    # Then: rollover uses the configured threshold instead of the default.
    assert first.should_rollover is False
    assert second.should_rollover is True
    assert second.compaction_count == 2


@dataclass
class FakeDiscordContinuationClient:
    created_threads: list[dict[str, str | None]] = field(default_factory=list)
    messages: list[tuple[str, str]] = field(default_factory=list)

    def create_public_thread(
        self,
        *,
        parent_channel_id: str,
        source_thread_id: str | None,
        name: str,
    ) -> DiscordCreatedThread:
        self.created_threads.append(
            {"parent_channel_id": parent_channel_id, "source_thread_id": source_thread_id, "name": name}
        )
        return DiscordCreatedThread(thread_id="thread-new", name=name, url="https://discord.test/thread-new")

    def post_message(self, *, channel_id: str, content: str) -> None:
        self.messages.append((channel_id, content))
