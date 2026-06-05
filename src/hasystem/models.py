from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any
from datetime import datetime, timezone


ACTIVE_PHASES = {"observe", "plan", "execute", "verify", "pr_created", "approval_wait", "paused"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify_title(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:60] or "task"


@dataclass(frozen=True)
class GitHubIssue:
    number: int
    title: str
    labels: list[str] = field(default_factory=list)
    body: str = ""


@dataclass(frozen=True)
class ApprovalState:
    intent: str | None = None
    status: str | None = None
    approval_id: str | None = None


@dataclass(frozen=True)
class LoopState:
    loop_id: str
    repo: str
    issue: GitHubIssue
    branch: str
    executor: str
    phase: str
    approval: ApprovalState = field(default_factory=ApprovalState)
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def start(cls, repo: str, issue: GitHubIssue, executor: str) -> "LoopState":
        branch = f"ai/issue-{issue.number}-{slugify_title(issue.title)}"
        return cls(
            loop_id=str(uuid.uuid4()),
            repo=repo,
            issue=issue,
            branch=branch,
            executor=executor,
            phase="plan",
        )

    def is_active(self) -> bool:
        return self.phase in ACTIVE_PHASES

    def with_approval(self, approval: ApprovalState) -> "LoopState":
        return LoopState(
            loop_id=self.loop_id,
            repo=self.repo,
            issue=self.issue,
            branch=self.branch,
            executor=self.executor,
            phase=self.phase,
            approval=approval,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True)
class GodmodeSession:
    conversation_id: str
    repo: str
    status: str
    iterations: int = 0
    failures: int = 0
    last_issue_number: int | None = None
    last_issue_title: str | None = None
    stop_reason: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)


@dataclass(frozen=True)
class GatewayConversationState:
    conversation_id: str
    platform: str
    guild_id: str | None = None
    channel_id: str | None = None
    thread_id: str | None = None
    repo: str | None = None
    latest_user_goal: str | None = None
    latest_summary: str | None = None
    active_issue_number: int | None = None
    active_issue_title: str | None = None
    active_issue_labels: list[str] = field(default_factory=list)
    compaction_count: int = 0
    continuation_of: str | None = None
    continuation_conversation_id: str | None = None
    continuation_thread_id: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
