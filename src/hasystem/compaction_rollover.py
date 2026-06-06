from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

from .gateway import DiscordGatewayEvent
from .state_store import StateStore

# Kept for backward-compatible config parsing only. Context compaction no
# longer triggers Discord continuation thread rollover.
DEFAULT_COMPACTION_ROLLOVER_THRESHOLD: Final = 7


@dataclass(frozen=True)
class RolloverConfig:
    threshold: int = DEFAULT_COMPACTION_ROLLOVER_THRESHOLD


@dataclass(frozen=True)
class CompactionRolloverResult:
    conversation_id: str
    compaction_count: int
    threshold: int
    should_rollover: bool = False
    handoff_message: str | None = None
    new_conversation_id: str | None = None
    new_thread_id: str | None = None
    continuation_summary: str | None = None
    reason: str = "context compaction thread rollover has been removed"


@dataclass(frozen=True)
class InvalidRolloverThresholdError(ValueError):
    threshold: int

    def __str__(self) -> str:
        return f"Compaction rollover threshold must be at least 1, got {self.threshold}"


def record_context_compaction(
    *,
    store: StateStore,
    event: DiscordGatewayEvent,
    config: RolloverConfig | None = None,
    discord_client: Any | None = None,
) -> CompactionRolloverResult:
    """A removed compatibility shim for the former Discord thread rollover.

    The old behavior incremented a per-conversation compaction counter and
    created a Discord continuation thread after a threshold, defaulting to 7.
    That workflow has been cancelled, so the hook is intentionally inert: it
    does not persist compaction state, call Discord, post handoff messages, or
    create continuation conversations.
    """
    del store, discord_client
    rollover_config = config or RolloverConfig()
    if rollover_config.threshold < 1:
        raise InvalidRolloverThresholdError(threshold=rollover_config.threshold)
    return CompactionRolloverResult(
        conversation_id=event.conversation_id(),
        compaction_count=0,
        threshold=rollover_config.threshold,
    )
