from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.discord_request import DiscordAutomationService, DiscordRequestParseError, DiscordRequestRouterConfig
from hasystem.gateway import DiscordGatewayEvent, build_gateway_response
from hasystem.github_client import GitHubClient
from hasystem.godmode import GodmodeConfig, parse_godmode_command
from hasystem.intake import IntakeService
from hasystem.loop_runner import RunLoopService
from hasystem.models import GitHubIssue
from hasystem.state_store import StateStore
from hasystem.worker import CodexWorkerLauncher
from hasystem.workspace import Workspace


def test_parse_godmode_exact_start_and_controls() -> None:
    # Given: exact lowercase godmode commands.
    commands = ["godmode", "godmode status", "godmode pause", "godmode resume", "godmode stop"]

    # When/Then: each command parses to its action.
    assert [parse_godmode_command(command) for command in commands] == [
        "start",
        "status",
        "pause",
        "resume",
        "stop",
    ]


@pytest.mark.parametrize("message", ["Godmode", "godmode now", " hermes godmode", "/godmode", ""])
def test_parse_godmode_rejects_non_exact_messages(message: str) -> None:
    # Given/When/Then: adjacent messages are not godmode commands.
    assert parse_godmode_command(message) is None


def test_godmode_requires_authorized_channel_or_sender(tmp_path: Path) -> None:
    # Given: godmode is enabled for a different Discord channel.
    runner = RecordingCommandRunner([])
    service = _service(
        tmp_path,
        runner,
        router_config=DiscordRequestRouterConfig(
            default_repo="owner/repo",
            allow_repos=frozenset({"owner/repo"}),
            godmode=GodmodeConfig(authorized_channel_ids=frozenset({"allowed-channel"})),
        ),
    )
    event = DiscordGatewayEvent(raw_message="godmode", channel_id="blocked-channel", sender_id="user-1")

    # When/Then: the gateway refuses to start autonomous work from an unauthorized channel.
    with pytest.raises(DiscordRequestParseError, match="not authorized"):
        build_gateway_response(service=service, event=event, dry_run_override=None, no_run_loop_override=None)


def test_godmode_starts_selects_issue_marks_in_progress_and_records_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hasystem.worker.shutil.which", lambda _binary: None)
    # Given: an authorized godmode channel and one ready issue.
    runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    github = ReadyIssueClient(GitHubIssue(number=12, title="Ship loop", body="Do it", labels=["ai:ready", "priority:p2"]))
    service = _service(
        tmp_path,
        runner,
        github=github,
        router_config=DiscordRequestRouterConfig(
            default_repo="owner/repo",
            allow_repos=frozenset({"owner/repo"}),
            godmode=GodmodeConfig(authorized_channel_ids=frozenset({"channel-1"}), max_iterations=1),
        ),
    )
    event = DiscordGatewayEvent(raw_message="godmode", channel_id="channel-1", sender_id="user-1")

    # When: the gateway starts godmode.
    payload = build_gateway_response(service=service, event=event, dry_run_override=None, no_run_loop_override=None)

    # Then: the first iteration selects and marks an issue before worker launch evidence is returned.
    assert payload["status"] == "godmode_completed"
    assert payload["godmode"]["repo"] == "owner/repo"
    assert payload["godmode"]["iterations"] == 1
    assert payload["godmode"]["stop_reason"] == "max_iterations"
    assert payload["godmode"]["evidence"][0]["issue"]["number"] == 12
    assert github.marked == [12]
    assert runner.commands[-1] == ("codex", ".")
    assert runner.stdin_values[-1] is not None
    assert "issue-first agent workflow" in runner.stdin_values[-1]
    stored = service.loop_runner.store.get_godmode_session("discord:channel-1")
    assert stored is not None
    assert stored.status == "completed"
    assert stored.iterations == 1
    assert stored.evidence[0]["worker"]["launched"] is True


def test_godmode_status_pause_resume_stop_persist_controls(tmp_path: Path) -> None:
    # Given: a paused persistent godmode session.
    runner = RecordingCommandRunner([])
    service = _service(
        tmp_path,
        runner,
        router_config=DiscordRequestRouterConfig(
            default_repo="owner/repo",
            allow_repos=frozenset({"owner/repo"}),
            godmode=GodmodeConfig(authorized_channel_ids=frozenset({"channel-1"}), max_iterations=0),
        ),
    )
    start_event = DiscordGatewayEvent(raw_message="godmode", channel_id="channel-1", sender_id="user-1")
    pause_event = DiscordGatewayEvent(raw_message="godmode pause", channel_id="channel-1", sender_id="user-1")
    resume_event = DiscordGatewayEvent(raw_message="godmode resume", channel_id="channel-1", sender_id="user-1")
    stop_event = DiscordGatewayEvent(raw_message="godmode stop", channel_id="channel-1", sender_id="user-1")

    # When/Then: controls mutate and report durable state without launching commands.
    assert build_gateway_response(service=service, event=start_event, dry_run_override=None, no_run_loop_override=None)["status"] == "godmode_completed"
    assert build_gateway_response(service=service, event=pause_event, dry_run_override=None, no_run_loop_override=None)["status"] == "godmode_paused"
    assert service.loop_runner.store.get_godmode_session("discord:channel-1").status == "paused"
    assert build_gateway_response(service=service, event=resume_event, dry_run_override=None, no_run_loop_override=None)["status"] == "godmode_completed"
    assert build_gateway_response(service=service, event=stop_event, dry_run_override=None, no_run_loop_override=None)["status"] == "godmode_stopped"
    assert service.loop_runner.store.get_godmode_session("discord:channel-1").status == "stopped"
    assert runner.commands == []


def test_godmode_guardrail_stops_when_no_issue(tmp_path: Path) -> None:
    # Given: an authorized godmode session with no eligible issue.
    runner = RecordingCommandRunner([])
    service = _service(
        tmp_path,
        runner,
        github=ReadyIssueClient(None),
        router_config=DiscordRequestRouterConfig(
            default_repo="owner/repo",
            allow_repos=frozenset({"owner/repo"}),
            godmode=GodmodeConfig(authorized_channel_ids=frozenset({"channel-1"}), max_iterations=3),
        ),
    )
    event = DiscordGatewayEvent(raw_message="godmode", channel_id="channel-1", sender_id="user-1")

    # When: godmode cannot select an issue.
    payload = build_gateway_response(service=service, event=event, dry_run_override=None, no_run_loop_override=None)

    # Then: it stops with structured no-issue evidence and launches no worker.
    assert payload["status"] == "godmode_stopped"
    assert payload["godmode"]["stop_reason"] == "no_issue"
    assert payload["godmode"]["evidence"][-1]["event"] == "guardrail_stop"
    assert payload["godmode"]["evidence"][-1]["reason"] == "no_issue"
    assert runner.commands == []


def test_godmode_creates_seed_issue_when_configured_and_no_ready_issue(tmp_path: Path) -> None:
    # Given: godmode is allowed to create a seed issue when no ready issue exists.
    runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    github = CreateOnEmptyClient()
    service = _service(
        tmp_path,
        runner,
        github=github,
        router_config=DiscordRequestRouterConfig(
            default_repo="owner/repo",
            allow_repos=frozenset({"owner/repo"}),
            godmode=GodmodeConfig(
                authorized_channel_ids=frozenset({"channel-1"}),
                max_iterations=1,
                create_issue_when_empty=True,
                seed_issue_title="GODMODE inspect next task",
                seed_issue_body="Find and implement the next concrete improvement.",
            ),
        ),
    )
    event = DiscordGatewayEvent(raw_message="godmode", channel_id="channel-1", sender_id="user-1")

    # When: the loop starts with an empty ready queue.
    payload = build_gateway_response(service=service, event=event, dry_run_override=None, no_run_loop_override=None)

    # Then: godmode creates a ready issue, selects it, marks it in progress, and records durable URLs/evidence.
    assert github.created == [("GODMODE inspect next task", "Find and implement the next concrete improvement.")]
    assert github.marked == [77]
    assert payload["godmode"]["evidence"][0]["issue"] == {
        "number": 77,
        "title": "GODMODE inspect next task",
        "labels": ["ai:ready", "executor:lazycodex", "priority:p2"],
        "url": "https://github.com/owner/repo/issues/77",
        "created_by_godmode": True,
    }
    assert payload["godmode"]["evidence"][0]["verification"] == {"status": "pending_worker", "result": None}


def _service(
    tmp_path: Path,
    runner: RecordingCommandRunner,
    *,
    router_config: DiscordRequestRouterConfig,
    github: Any | None = None,
) -> DiscordAutomationService:
    workspace = Workspace(tmp_path / "workspace", runner)
    return DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=StateStore(tmp_path / "state.db"),
            worker=CodexWorkerLauncher(runner=runner),
            github_factory=lambda repo: github or ReadyIssueClient(GitHubIssue(1, "Default", ["ai:ready"], "")),
        ),
        router_config=router_config,
    )


class ReadyIssueClient:
    def __init__(self, issue: GitHubIssue | None) -> None:
        self.issue = issue
        self.marked: list[int] = []

    def list_ready_issues(self) -> list[GitHubIssue]:
        if self.issue is None:
            return []
        return [self.issue]

    @staticmethod
    def select_next_issue(issues: list[GitHubIssue]) -> GitHubIssue | None:
        return GitHubClient.select_next_issue(issues)

    def mark_in_progress(self, issue_number: int) -> None:
        self.marked.append(issue_number)


class CreateOnEmptyClient:
    def __init__(self) -> None:
        self.issue: GitHubIssue | None = None
        self.created: list[tuple[str, str]] = []
        self.marked: list[int] = []

    def list_ready_issues(self) -> list[GitHubIssue]:
        if self.issue is None:
            return []
        return [self.issue]

    @staticmethod
    def select_next_issue(issues: list[GitHubIssue]) -> GitHubIssue | None:
        return GitHubClient.select_next_issue(issues)

    def create_issue(self, title: str, body: str, labels: tuple[str, ...]) -> int:
        self.created.append((title, body))
        self.issue = GitHubIssue(number=77, title=title, body=body, labels=list(labels))
        return 77

    def mark_in_progress(self, issue_number: int) -> None:
        self.marked.append(issue_number)


def test_discord_automation_service_routes_godmode_control_through_discord_request_layer(tmp_path: Path) -> None:
    # Given: the discord request service has a persisted godmode session.
    runner = RecordingCommandRunner([])
    service = _service(
        tmp_path,
        runner,
        router_config=DiscordRequestRouterConfig(
            default_repo="owner/repo",
            allow_repos=frozenset({"owner/repo"}),
            godmode=GodmodeConfig(authorized_sender_ids=frozenset({"user-1"}), max_iterations=0),
        ),
    )

    # When: a control command is handled through DiscordAutomationService directly.
    result = service.handle("godmode status", channel_id="channel-1", sender_id="user-1")

    # Then: the discord_request layer returns structured godmode state without intake or worker launch.
    assert result.godmode is not None
    assert result.godmode.session.repo == "owner/repo"
    assert result.godmode.action == "status"
    assert result.intake is None
    assert result.loop is None
    assert runner.commands == []


def test_godmode_guardrail_stops_when_runtime_budget_is_exhausted(tmp_path: Path) -> None:
    # Given: an authorized godmode session with an exhausted runtime budget.
    runner = RecordingCommandRunner([])
    service = _service(
        tmp_path,
        runner,
        github=ReadyIssueClient(GitHubIssue(number=13, title="Should not launch", body="", labels=["ai:ready"])),
        router_config=DiscordRequestRouterConfig(
            default_repo="owner/repo",
            allow_repos=frozenset({"owner/repo"}),
            godmode=GodmodeConfig(authorized_channel_ids=frozenset({"channel-1"}), max_iterations=3, max_runtime_seconds=0),
        ),
    )
    event = DiscordGatewayEvent(raw_message="godmode", channel_id="channel-1", sender_id="user-1")

    # When: godmode starts after its runtime budget is already exhausted.
    payload = build_gateway_response(service=service, event=event, dry_run_override=None, no_run_loop_override=None)

    # Then: the runtime guardrail stops before issue mutation or worker launch.
    assert payload["status"] == "godmode_stopped"
    assert payload["godmode"]["stop_reason"] == "max_runtime"
    assert payload["godmode"]["iterations"] == 0
    assert runner.commands == []


def test_godmode_guardrail_stops_on_iteration_failure(tmp_path: Path) -> None:
    # Given: issue selection raises during the first autonomous iteration.
    runner = RecordingCommandRunner([])
    service = _service(
        tmp_path,
        runner,
        github=FailingIssueClient(),
        router_config=DiscordRequestRouterConfig(
            default_repo="owner/repo",
            allow_repos=frozenset({"owner/repo"}),
            godmode=GodmodeConfig(authorized_channel_ids=frozenset({"channel-1"}), max_iterations=3),
        ),
    )
    event = DiscordGatewayEvent(raw_message="godmode", channel_id="channel-1", sender_id="user-1")

    # When: godmode encounters the failure.
    payload = build_gateway_response(service=service, event=event, dry_run_override=None, no_run_loop_override=None)

    # Then: it records a failure guardrail and does not claim progress.
    assert payload["status"] == "godmode_failed"
    assert payload["godmode"]["stop_reason"] == "failure"
    assert payload["godmode"]["failures"] == 1
    assert payload["godmode"]["evidence"][-1]["event"] == "guardrail_stop"
    assert payload["godmode"]["evidence"][-1]["reason"] == "failure"
    assert runner.commands == []


class FailingIssueClient:
    def list_ready_issues(self) -> list[GitHubIssue]:
        raise RuntimeError("simulated GitHub failure")

    @staticmethod
    def select_next_issue(issues: list[GitHubIssue]) -> GitHubIssue | None:
        return None

    def mark_in_progress(self, issue_number: int) -> None:
        raise AssertionError(f"failure path must not mark issue {issue_number} in progress")
