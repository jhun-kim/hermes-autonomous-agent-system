from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from hasystem.compaction_rollover import (
    CompactionRolloverResult,
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


def test_discord_rollover_names_repeated_continuations_from_original_thread_name(tmp_path: Path) -> None:
    # Given: an original Discord thread with a readable name and a low rollover threshold.
    store = StateStore(tmp_path / "state.db")
    config = RolloverConfig(threshold=2)
    fake_discord = FakeDiscordContinuationClient(thread_ids=["thread-2", "thread-3"])
    original_event = DiscordGatewayEvent(
        raw_message="continue issue #36",
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        thread_name="Original planning thread",
        repo_hint="owner/repo",
    )

    # When: the original thread rolls over, and then its continuation rolls over again.
    first_result = _record_until_rollover(
        store=store,
        event=original_event,
        config=config,
        fake_discord=fake_discord,
    )
    continuation_event = DiscordGatewayEvent(
        raw_message="continue issue #36 again",
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id=first_result.new_thread_id,
        thread_name="Original planning thread continuation 2",
        repo_hint="owner/repo",
    )
    second_result = _record_until_rollover(
        store=store,
        event=continuation_event,
        config=config,
        fake_discord=fake_discord,
    )

    # Then: each new thread name is based on the original thread name with a deterministic sequence suffix.
    assert first_result.new_thread_id == "thread-2"
    assert second_result.new_thread_id == "thread-3"
    assert [thread["name"] for thread in fake_discord.created_threads] == [
        "Original planning thread continuation 2",
        "Original planning thread continuation 3",
    ]


def test_rollover_name_uses_persisted_original_name_when_latest_thread_has_suffix(tmp_path: Path) -> None:
    # Given: a continuation conversation whose latest Discord thread name already has a continuation suffix.
    store = StateStore(tmp_path / "state.db")
    config = RolloverConfig(threshold=1)
    fake_discord = FakeDiscordContinuationClient(thread_ids=["thread-3"])
    original_event = DiscordGatewayEvent(
        raw_message="continue issue #36",
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        thread_name="Original planning thread",
        repo_hint="owner/repo",
    )
    first_result = record_context_compaction(
        store=store,
        event=original_event,
        config=config,
        discord_client=FakeDiscordContinuationClient(thread_ids=["thread-2"]),
    )
    continuation_event = DiscordGatewayEvent(
        raw_message="continue issue #36 again",
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id=first_result.new_thread_id,
        thread_name="Original planning thread continuation 2",
        repo_hint="owner/repo",
    )

    # When: the suffixed continuation thread reaches rollover.
    result = record_context_compaction(
        store=store,
        event=continuation_event,
        config=config,
        discord_client=fake_discord,
    )

    # Then: the next name increments from the original base instead of nesting the latest suffix.
    assert result.new_thread_id == "thread-3"
    assert fake_discord.created_threads[0]["name"] == "Original planning thread continuation 3"


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


def _record_until_rollover(
    *,
    store: StateStore,
    event: DiscordGatewayEvent,
    config: RolloverConfig,
    fake_discord: "FakeDiscordContinuationClient",
) -> CompactionRolloverResult:
    result = record_context_compaction(store=store, event=event, config=config, discord_client=fake_discord)
    while not result.should_rollover:
        result = record_context_compaction(store=store, event=event, config=config, discord_client=fake_discord)
    return result


@dataclass
class FakeDiscordContinuationClient:
    thread_ids: list[str] = field(default_factory=lambda: ["thread-new"])
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
        thread_id = self.thread_ids[len(self.created_threads) - 1]
        return DiscordCreatedThread(thread_id=thread_id, name=name, url=f"https://discord.test/{thread_id}")

    def post_message(self, *, channel_id: str, content: str) -> None:
        self.messages.append((channel_id, content))
