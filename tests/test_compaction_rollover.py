from __future__ import annotations

from pathlib import Path

from hasystem.compaction_rollover import (
    DEFAULT_COMPACTION_ROLLOVER_THRESHOLD,
    RolloverConfig,
    record_context_compaction,
)
from hasystem.gateway import DiscordGatewayEvent
from hasystem.state_store import StateStore


def test_context_compaction_rollover_is_removed_and_does_not_persist_state(tmp_path: Path) -> None:
    # Given: a Discord gateway conversation that previously would have rolled over after seven compactions.
    store = StateStore(tmp_path / "state.db")
    event = DiscordGatewayEvent(
        raw_message="continue issue #64",
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="thread-1",
        repo_hint="owner/repo",
    )
    fake_discord = FakeDiscordClient()

    # When: more than the former default threshold is recorded.
    results = [record_context_compaction(store=store, event=event, discord_client=fake_discord) for _ in range(8)]

    # Then: no continuation thread is created and no compaction rollover state is persisted.
    assert DEFAULT_COMPACTION_ROLLOVER_THRESHOLD == 7
    assert all(result.should_rollover is False for result in results)
    assert [result.compaction_count for result in results] == [0] * 8
    assert results[-1].reason == "context compaction thread rollover has been removed"
    assert results[-1].new_thread_id is None
    assert store.get_gateway_conversation("discord:thread-1") is None
    assert fake_discord.created_threads == []
    assert fake_discord.messages == []


def test_configured_low_threshold_still_noops_without_discord_side_effects(tmp_path: Path) -> None:
    # Given: stale config still passes a low rollover threshold.
    store = StateStore(tmp_path / "state.db")
    event = DiscordGatewayEvent(raw_message="continue", platform="discord", channel_id="channel-1", thread_id="thread-1")
    fake_discord = FakeDiscordClient()

    # When: the compatibility shim is invoked at the old threshold.
    result = record_context_compaction(
        store=store,
        event=event,
        config=RolloverConfig(threshold=1),
        discord_client=fake_discord,
    )

    # Then: the threshold is accepted for compatibility but never triggers rollover.
    assert result.threshold == 1
    assert result.should_rollover is False
    assert result.compaction_count == 0
    assert store.get_gateway_conversation("discord:thread-1") is None
    assert fake_discord.created_threads == []
    assert fake_discord.messages == []


class FakeDiscordClient:
    def __init__(self) -> None:
        self.created_threads: list[dict[str, str | None]] = []
        self.messages: list[tuple[str, str]] = []

    def create_public_thread(self, *, parent_channel_id: str, source_thread_id: str | None, name: str):
        self.created_threads.append(
            {"parent_channel_id": parent_channel_id, "source_thread_id": source_thread_id, "name": name}
        )
        raise AssertionError("context compaction rollover must not create Discord threads")

    def post_message(self, *, channel_id: str, content: str) -> None:
        self.messages.append((channel_id, content))
        raise AssertionError("context compaction rollover must not post Discord handoff messages")
