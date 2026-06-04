from __future__ import annotations

import json
from pathlib import Path

import pytest

from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.discord_request import DiscordAutomationService, DiscordRequestParseError, parse_discord_request
from hasystem.github_client import DEFAULT_AI_LABELS, GitHubClient
from hasystem.intake import IntakeService
from hasystem.loop_runner import RunLoopService
from hasystem.state_store import StateStore
from hasystem.worker import CodexWorkerLauncher
from hasystem.workspace import Workspace


def test_parse_discord_request_from_json_payload() -> None:
    payload = json.dumps({"repo": "owner/repo", "request": "Fix auth and run tests"})

    request = parse_discord_request(payload)

    assert request.repo_raw == "owner/repo"
    assert request.request_text == "Fix auth and run tests"


def test_parse_discord_request_from_freeform_command() -> None:
    request = parse_discord_request("/agent https://github.com/owner/repo.git add Discord automation")

    assert request.repo_raw == "https://github.com/owner/repo.git"
    assert request.request_text == "add Discord automation"


def test_parse_discord_request_requires_repo_and_task() -> None:
    with pytest.raises(DiscordRequestParseError):
        parse_discord_request("/agent please do a task without a repo")



def test_discord_automation_intakes_issue_and_launches_worker(tmp_path: Path) -> None:
    issue_json = json.dumps(
        [
            {
                "number": 42,
                "title": "Fix auth and run tests",
                "body": "Fix auth and run tests",
                "labels": [{"name": "ai:ready"}, {"name": "priority:p2"}],
            }
        ]
    )
    runner = RecordingCommandRunner(
        [
            CommandResult(stdout="", stderr="", returncode=0),
            *[CommandResult(stdout="", stderr="", returncode=0) for _ in DEFAULT_AI_LABELS],
            CommandResult(stdout="https://github.com/owner/repo/issues/42\n", stderr="", returncode=0),
            CommandResult(stdout=issue_json, stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
        ]
    )
    workspace = Workspace(tmp_path / "workspace", runner)
    service = DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=StateStore(tmp_path / "state.db"),
            worker=CodexWorkerLauncher(runner=runner),
            github_factory=lambda repo: GitHubClient(repo=repo, runner=runner),
        ),
    )

    result = service.handle('{"repo":"owner/repo","request":"Fix auth and run tests"}')

    assert result.intake is not None
    assert result.intake.issue_number == 42
    assert result.loop is not None
    assert result.loop.loop.issue.number == 42
    assert result.loop.worker_command.args == ("codex", ".")
    assert runner.commands[0][:2] == ("git", "clone")
    assert ("gh", "issue", "edit", "42", "--repo", "owner/repo", "--add-label", "ai:in-progress", "--remove-label", "ai:ready") in runner.commands
    assert runner.commands[-1][0:2] == ("osascript", "-e")
    assert "codex ." in runner.commands[-1][-1]
    assert result.loop.worker_command.stdin_text is not None
    assert "OmO/OmX workflow" in result.loop.worker_command.stdin_text


def test_discord_automation_dry_run_only_parses_message(tmp_path: Path) -> None:
    runner = RecordingCommandRunner([])
    workspace = Workspace(tmp_path / "workspace", runner)
    service = DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=StateStore(tmp_path / "state.db"),
            worker=CodexWorkerLauncher(runner=runner),
            github_factory=lambda repo: GitHubClient(repo=repo, runner=runner),
        ),
    )

    result = service.handle("repo: owner/repo\nrequest: Ship it", dry_run=True)

    assert result.dry_run is True
    assert result.request.repo_raw == "owner/repo"
    assert result.request.request_text == "Ship it"
    assert result.intake is None
    assert result.loop is None
    assert runner.commands == []
