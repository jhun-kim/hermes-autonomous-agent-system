from __future__ import annotations

from pathlib import Path

from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.loop_runner import RunLoopService
from hasystem.models import GitHubIssue, LoopState
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
    assert "Labels: ai:ready" in command.stdin_text
    assert "OmO/OmX workflow" in command.stdin_text
    assert "ulw skill/workflow" in command.stdin_text
    assert "issue first, code second" in command.stdin_text
    assert "confirm the selected GitHub issue" in command.stdin_text


def test_omx_worker_launcher_builds_non_interactive_exec_command(tmp_path: Path) -> None:
    # Given: an OmX launcher and a target GitHub issue.
    launcher = CodexWorkerLauncher(executor="omx")
    issue = GitHubIssue(number=6, title="Add OmX exec mode", body="Use exec", labels=["ai:ready", "executor:omx"])

    # When: the worker command is built.
    command = launcher.build(repo_path=tmp_path, repo="owner/repo", issue=issue, branch="ai/issue-6-add-omx-exec-mode")

    # Then: OmX runs non-interactively with the full worker prompt as an argument.
    assert command.cwd == tmp_path
    assert command.stdin_text == ""
    assert command.args[0:3] == ("omx", "exec", "--full-auto")
    assert command.args[3] == command.args[-1]
    assert "Issue #6: Add OmX exec mode" in command.args[-1]
    assert "Labels: ai:ready, executor:omx" in command.args[-1]
    assert "issue first, code second" in command.args[-1]
    assert "ulw skill/workflow" in command.args[-1]


def test_run_loop_dry_run_uses_selected_omx_executor(tmp_path: Path) -> None:
    # Given: one ready issue and an OmX-configured run loop service.
    command_runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    github = ReadyIssueClient()
    store = StateStore(tmp_path / "state.db")
    worker = CodexWorkerLauncher(executor="omx")
    service = RunLoopService(
        workspace=Workspace(tmp_path / "workspace", command_runner),
        store=store,
        worker=worker,
        github_factory=lambda repo: github,
    )

    # When: the loop runs in dry-run mode with OmX selected.
    result = service.run_once(repo_raw="owner/repo", dry_run=True, executor="omx")

    # Then: loop state and worker command both carry OmX executor selection.
    assert result.loop.executor == "omx"
    assert result.worker_command.args[0:3] == ("omx", "exec", "--full-auto")
    assert store.get_active_loop("owner/repo") is None
    assert command_runner.commands == []


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


def test_run_loop_existing_active_loop_uses_stored_executor(tmp_path: Path) -> None:
    # Given: an active loop previously saved with the OmX executor.
    command_runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    store = StateStore(tmp_path / "state.db")
    issue = GitHubIssue(number=6, title="Add OmX exec mode", body="Use exec", labels=["executor:omx"])
    active_loop = LoopState.start(repo="owner/repo", issue=issue, executor="omx")
    store.save_loop(active_loop)
    service = RunLoopService(
        workspace=Workspace(tmp_path / "workspace", command_runner),
        store=store,
        worker=CodexWorkerLauncher(),
        github_factory=lambda repo: ReadyIssueClient(),
    )

    # When: the run loop resumes with default arguments.
    result = service.run_once(repo_raw="owner/repo", dry_run=True)

    # Then: the resumed worker command uses the stored OmX executor.
    assert result.existing_active is True
    assert result.loop.executor == "omx"
    assert result.worker_command.args[0:3] == ("omx", "exec", "--full-auto")


class ReadyIssueClient:
    def list_ready_issues(self) -> list[GitHubIssue]:
        return [GitHubIssue(number=5, title="Add CLI", body="Build it", labels=["ai:ready", "priority:p2"])]

    @staticmethod
    def select_next_issue(issues: list[GitHubIssue]) -> GitHubIssue | None:
        return issues[0] if issues else None

    def mark_in_progress(self, issue_number: int) -> None:
        raise AssertionError(f"dry-run must not mark issue {issue_number} in progress")
