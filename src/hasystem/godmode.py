from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any, Final, Literal

from .loop_runner import RunLoopService
from .models import GodmodeSession, utc_now_iso

GodmodeAction = Literal["start", "status", "pause", "resume", "stop"]
GodmodeStatus = Literal["running", "paused", "stopped", "completed", "failed"]
JsonObject = dict[str, Any]

_COMMANDS: Final[dict[str, GodmodeAction]] = {
    "godmode": "start",
    "godmode status": "status",
    "godmode pause": "pause",
    "godmode resume": "resume",
    "godmode stop": "stop",
}


@dataclass(frozen=True)
class GodmodeConfig:
    authorized_channel_ids: frozenset[str] = frozenset()
    authorized_sender_ids: frozenset[str] = frozenset()
    max_iterations: int = 3
    max_runtime_seconds: int = 300
    max_failures: int = 1
    create_issue_when_empty: bool = False
    seed_issue_title: str = "GODMODE follow-up task"
    seed_issue_body: str = (
        "GODMODE could not find an ai:ready issue. Inspect the repository, identify the next "
        "concrete improvement, implement it with the issue-first OmO/OmX ULW workflow, and "
        "create another follow-up issue if more work remains."
    )
    seed_issue_labels: tuple[str, ...] = ("ai:ready", "executor:lazycodex", "priority:p2")


@dataclass(frozen=True)
class GodmodeResult:
    session: GodmodeSession
    action: GodmodeAction


@dataclass(frozen=True)
class GodmodeContext:
    conversation_id: str
    repo: str
    channel_id: str | None = None
    thread_id: str | None = None
    sender_id: str | None = None


def parse_godmode_command(raw_message: str) -> GodmodeAction | None:
    return _COMMANDS.get(raw_message.strip())


def ensure_authorized_godmode(*, config: GodmodeConfig, channel_id: str | None, thread_id: str | None, sender_id: str | None) -> None:
    channel_authorized = _is_authorized_id(channel_id, config.authorized_channel_ids) or _is_authorized_id(
        thread_id,
        config.authorized_channel_ids,
    )
    sender_authorized = _is_authorized_id(sender_id, config.authorized_sender_ids)
    if channel_authorized or sender_authorized:
        return
    raise GodmodeAuthorizationError("godmode is not authorized for this Discord sender/channel")


@dataclass(frozen=True)
class GodmodeService:
    loop_runner: RunLoopService
    config: GodmodeConfig = field(default_factory=GodmodeConfig)

    def handle(self, action: GodmodeAction, context: GodmodeContext) -> GodmodeResult:
        ensure_authorized_godmode(
            config=self.config,
            channel_id=context.channel_id,
            thread_id=context.thread_id,
            sender_id=context.sender_id,
        )
        current = self.loop_runner.store.get_godmode_session(context.conversation_id)
        match action:
            case "start":
                session = self._start_or_restart(current=current, context=context)
                return GodmodeResult(session=self._run_until_guardrail(session), action=action)
            case "status":
                return GodmodeResult(session=current or self._new_session(context=context, status="stopped"), action=action)
            case "pause":
                return GodmodeResult(session=self._persist_control(current=current, context=context, status="paused"), action=action)
            case "resume":
                resumed = self._persist_control(current=current, context=context, status="running")
                return GodmodeResult(session=self._run_until_guardrail(resumed), action=action)
            case "stop":
                return GodmodeResult(
                    session=self._persist_control(current=current, context=context, status="stopped", stop_reason="user_stop"),
                    action=action,
                )

    def _start_or_restart(self, *, current: GodmodeSession | None, context: GodmodeContext) -> GodmodeSession:
        if current is not None and current.status in {"running", "paused"}:
            session = replace(current, status="running", stop_reason=None, updated_at=utc_now_iso())
        else:
            session = self._new_session(context=context, status="running")
        self.loop_runner.store.save_godmode_session(session)
        return session

    def _persist_control(
        self,
        *,
        current: GodmodeSession | None,
        context: GodmodeContext,
        status: GodmodeStatus,
        stop_reason: str | None = None,
    ) -> GodmodeSession:
        base = current or self._new_session(context=context, status=status)
        session = replace(base, status=status, stop_reason=stop_reason or base.stop_reason, updated_at=utc_now_iso())
        self.loop_runner.store.save_godmode_session(session)
        return session

    def _run_until_guardrail(self, session: GodmodeSession) -> GodmodeSession:
        active = session
        while active.status == "running":
            guardrail = self._guardrail_reason(active)
            if guardrail is not None:
                return self._stop(active, status="completed" if guardrail == "max_iterations" else "stopped", reason=guardrail)
            created_issue = self._create_seed_issue_if_configured(active)
            try:
                result = self.loop_runner.run_once(repo_raw=active.repo, dry_run=False)
            except RuntimeError as exc:
                return self._record_failure(active, str(exc))
            if result is None:
                if created_issue is not None:
                    return self._record_failure(active, "created seed issue was not selectable")
                return self._stop(active, status="stopped", reason="no_issue")
            issue_url = _issue_url(active.repo, result.loop.issue.number)
            evidence: JsonObject = {
                "event": "iteration",
                "iteration": active.iterations + 1,
                "issue": {
                    "number": result.loop.issue.number,
                    "title": result.loop.issue.title,
                    "labels": result.loop.issue.labels,
                    "url": issue_url,
                    "created_by_godmode": created_issue == result.loop.issue.number,
                },
                "loop_id": result.loop.loop_id,
                "branch": result.loop.branch,
                "executor": result.loop.executor,
                "worker": {
                    "command": list(result.worker_command.args),
                    "launched": not result.existing_active,
                    "existing_active": result.existing_active,
                },
                "pr_url": None,
                "commit_url": None,
                "verification": {"status": "pending_worker", "result": None},
                "next_issue": None,
            }
            active = replace(
                active,
                iterations=active.iterations + 1,
                last_issue_number=result.loop.issue.number,
                last_issue_title=result.loop.issue.title,
                evidence=[*active.evidence, evidence],
                updated_at=utc_now_iso(),
            )
            self.loop_runner.store.save_godmode_session(active)
            if result.existing_active:
                return self._stop(active, status="stopped", reason="existing_active_loop")
        return active

    def _create_seed_issue_if_configured(self, session: GodmodeSession) -> int | None:
        if not self.config.create_issue_when_empty:
            return None
        client = self.loop_runner.github_factory(session.repo)
        if client.select_next_issue(client.list_ready_issues()) is not None:
            return None
        return client.create_issue(
            title=self.config.seed_issue_title,
            body=self.config.seed_issue_body,
            labels=self.config.seed_issue_labels,
        )

    def _guardrail_reason(self, session: GodmodeSession) -> str | None:
        if session.iterations >= max(0, self.config.max_iterations):
            return "max_iterations"
        if session.failures >= max(1, self.config.max_failures):
            return "failure"
        elapsed_seconds = (_parse_iso(utc_now_iso()) - _parse_iso(session.started_at)).total_seconds()
        if elapsed_seconds >= max(0, self.config.max_runtime_seconds):
            return "max_runtime"
        return None

    def _record_failure(self, session: GodmodeSession, message: str) -> GodmodeSession:
        evidence: JsonObject = {"event": "guardrail_stop", "reason": "failure", "error": message}
        failed = replace(
            session,
            status="failed",
            failures=session.failures + 1,
            stop_reason="failure",
            evidence=[*session.evidence, evidence],
            updated_at=utc_now_iso(),
        )
        self.loop_runner.store.save_godmode_session(failed)
        return failed

    def _stop(self, session: GodmodeSession, *, status: GodmodeStatus, reason: str) -> GodmodeSession:
        evidence: JsonObject = {"event": "guardrail_stop", "reason": reason, "iteration": session.iterations}
        stopped = replace(
            session,
            status=status,
            stop_reason=reason,
            evidence=[*session.evidence, evidence],
            updated_at=utc_now_iso(),
        )
        self.loop_runner.store.save_godmode_session(stopped)
        return stopped

    @staticmethod
    def _new_session(*, context: GodmodeContext, status: GodmodeStatus) -> GodmodeSession:
        now = utc_now_iso()
        return GodmodeSession(
            conversation_id=context.conversation_id,
            repo=context.repo,
            status=status,
            started_at=now,
            updated_at=now,
        )


def _issue_url(repo: str, issue_number: int) -> str:
    return f"https://github.com/{repo}/issues/{issue_number}"


def _is_authorized_id(value: str | None, allowed: frozenset[str]) -> bool:
    return value is not None and value in allowed


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class GodmodeAuthorizationError(ValueError):
    pass
