from __future__ import annotations

from pathlib import Path

from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.loop_runner import RunLoopService
from hasystem.models import GitHubIssue
from hasystem.state_store import StateStore
from hasystem.worker import CodexWorkerLauncher
from hasystem.workspace import Workspace


def test_codex_worker_launcher_builds_target_repo_command(tmp_path: Path) -> None:
    # Given: a target repo and GitHub issue.
    launcher = CodexWorkerLauncher()
    issue = GitHubIssue(number=7, title="Implement parser", body="Support owner/repo", labels=["ai:ready"])

    # When: the worker command is built.
    command = launcher.build(repo_path=tmp_path, repo="owner/repo", issue=issue, branch="ai/issue-7-implement-parser")

    # Then: codex runs from the target repository with issue context available.
    assert command.cwd == tmp_path
    assert command.args == ("codex", ".")
    assert "GitHub repo: owner/repo" in command.stdin_text
    assert "Issue #7: Implement parser" in command.stdin_text
    assert "OmO/OmX workflow" in command.stdin_text
    assert "issue first, code second" in command.stdin_text
    assert "confirm the selected GitHub issue" in command.stdin_text


def test_run_loop_dry_run_selects_issue_and_does_not_mutate_github(tmp_path: Path) -> None:
    # Given: one ready issue and a fake runner for workspace update.
    command_runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    github = ReadyIssueClient()
    store = StateStore(tmp_path / "state.db")
    worker = CodexWorkerLauncher()
    service = RunLoopService(
        workspace=Workspace(tmp_path / "workspace", command_runner),
        store=store,
        worker=worker,
        github_factory=lambda repo: github,
    )

    # When: the loop runs in dry-run mode.
    result = service.run_once(repo_raw="owner/repo", dry_run=True)

    # Then: loop state and worker command are prepared without local or GitHub mutations.
    assert result.loop.issue.number == 5
    assert result.worker_command.args == ("codex", ".")
    assert store.get_active_loop("owner/repo") is None
    assert command_runner.commands == []


class ReadyIssueClient:
    def list_ready_issues(self) -> list[GitHubIssue]:
        return [GitHubIssue(number=5, title="Add CLI", body="Build it", labels=["ai:ready", "priority:p2"])]

    @staticmethod
    def select_next_issue(issues: list[GitHubIssue]) -> GitHubIssue | None:
        return issues[0] if issues else None

    def mark_in_progress(self, issue_number: int) -> None:
        raise AssertionError(f"dry-run must not mark issue {issue_number} in progress")
