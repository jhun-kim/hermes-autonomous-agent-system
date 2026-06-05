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


def test_run_loop_dry_run_ignores_executor_argument_and_uses_issue_label(tmp_path: Path) -> None:
    # Given: one ready issue has no executor label, while the caller requests OmX.
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

    # When: the loop runs in dry-run mode with a stale explicit executor argument.
    result = service.run_once(repo_raw="owner/repo", dry_run=True, executor="omx")

    # Then: selected issue labels remain the source of truth and default to LazyCodex.
    assert result.loop.executor == "lazycodex"
    assert result.worker_command.args == ("codex", ".")
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


def test_run_loop_dry_run_resolves_omx_executor_from_issue_label(tmp_path: Path) -> None:
    # Given: the selected issue explicitly requests the OmX executor.
    command_runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    issue = GitHubIssue(number=8, title="Run with OmX", body="Use OmX", labels=["ai:ready", "executor:omx"])
    github = ReadyIssueClient(issue)
    store = StateStore(tmp_path / "state.db")
    service = RunLoopService(
        workspace=Workspace(tmp_path / "workspace", command_runner),
        store=store,
        worker=CodexWorkerLauncher(),
        github_factory=lambda repo: github,
    )

    # When: the loop selects that issue.
    result = service.run_once(repo_raw="owner/repo", dry_run=True)

    # Then: the resolved executor is stored in loop state and used for the worker.
    assert result.loop.executor == "omx"
    assert result.worker_command.args[0:3] == ("omx", "exec", "--full-auto")


def test_run_loop_dry_run_resolves_lazycodex_executor_from_issue_label(tmp_path: Path) -> None:
    # Given: the selected issue explicitly requests the LazyCodex executor.
    command_runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    issue = GitHubIssue(number=9, title="Run with LazyCodex", body="Use Codex", labels=["ai:ready", "executor:lazycodex"])
    github = ReadyIssueClient(issue)
    store = StateStore(tmp_path / "state.db")
    service = RunLoopService(
        workspace=Workspace(tmp_path / "workspace", command_runner),
        store=store,
        worker=CodexWorkerLauncher(executor="omx"),
        github_factory=lambda repo: github,
    )

    # When: the loop selects that issue.
    result = service.run_once(repo_raw="owner/repo", dry_run=True)

    # Then: the issue label wins over the launcher default.
    assert result.loop.executor == "lazycodex"
    assert result.worker_command.args == ("codex", ".")


def test_run_loop_dry_run_defaults_to_lazycodex_without_executor_label(tmp_path: Path) -> None:
    # Given: the selected issue has no executor label.
    command_runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    issue = GitHubIssue(number=10, title="Run default", body="Use default", labels=["ai:ready", "priority:p2"])
    github = ReadyIssueClient(issue)
    store = StateStore(tmp_path / "state.db")
    service = RunLoopService(
        workspace=Workspace(tmp_path / "workspace", command_runner),
        store=store,
        worker=CodexWorkerLauncher(executor="omx"),
        github_factory=lambda repo: github,
    )

    # When: the loop selects that issue.
    result = service.run_once(repo_raw="owner/repo", dry_run=True)

    # Then: LazyCodex is the documented default.
    assert result.loop.executor == "lazycodex"
    assert result.worker_command.args == ("codex", ".")


def test_run_loop_dry_run_resolves_conflicting_executor_labels_deterministically(tmp_path: Path) -> None:
    # Given: the selected issue has both executor labels.
    command_runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    issue = GitHubIssue(
        number=11,
        title="Run conflict",
        body="Conflicting labels",
        labels=["ai:ready", "executor:lazycodex", "executor:omx"],
    )
    github = ReadyIssueClient(issue)
    store = StateStore(tmp_path / "state.db")
    service = RunLoopService(
        workspace=Workspace(tmp_path / "workspace", command_runner),
        store=store,
        worker=CodexWorkerLauncher(),
        github_factory=lambda repo: github,
    )

    # When: the loop selects that issue.
    result = service.run_once(repo_raw="owner/repo", dry_run=True)

    # Then: documented conflict precedence selects OmX deterministically.
    assert result.loop.executor == "omx"
    assert result.worker_command.args[0:3] == ("omx", "exec", "--full-auto")


class ReadyIssueClient:
    def __init__(self, issue: GitHubIssue | None = None) -> None:
        self.issue = issue or GitHubIssue(number=5, title="Add CLI", body="Build it", labels=["ai:ready", "priority:p2"])

    def list_ready_issues(self) -> list[GitHubIssue]:
        return [self.issue]

    @staticmethod
    def select_next_issue(issues: list[GitHubIssue]) -> GitHubIssue | None:
        return issues[0] if issues else None

    def mark_in_progress(self, issue_number: int) -> None:
        raise AssertionError(f"dry-run must not mark issue {issue_number} in progress")
