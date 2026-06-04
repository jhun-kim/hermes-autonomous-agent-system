from pathlib import Path

from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.github_client import DEFAULT_AI_LABELS, GitHubClient
from hasystem.intake import IntakeService
from hasystem.repo_spec import RepoSpec
from hasystem.workspace import Workspace


def test_github_client_ensures_required_labels() -> None:
    # Given: a GitHub client using a fake subprocess runner.
    runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)] * len(DEFAULT_AI_LABELS))
    client = GitHubClient(repo="owner/repo", runner=runner)

    # When: required labels are ensured.
    client.ensure_ai_labels()

    # Then: every required automation label is created idempotently.
    assert [command[0:4] for command in runner.commands] == [
        ("gh", "label", "create", label.name) for label in DEFAULT_AI_LABELS
    ]
    assert all("--force" in command for command in runner.commands)


def test_intake_clones_repo_and_creates_ready_issue(tmp_path: Path) -> None:
    # Given: a Discord-style repo request and fake command runner.
    runner = RecordingCommandRunner(
        [
            CommandResult(stdout="", stderr="", returncode=0),
            *[CommandResult(stdout="", stderr="", returncode=0) for _ in DEFAULT_AI_LABELS],
            CommandResult(stdout="https://github.com/owner/repo/issues/42\n", stderr="", returncode=0),
        ]
    )
    service = IntakeService(workspace=Workspace(tmp_path, runner), runner=runner)

    # When: the request is ingested.
    result = service.create_task(repo_raw="owner/repo", request_text="Fix the failing tests")

    # Then: the repository is local and an ai:ready issue is created with executor metadata.
    assert result.repo == RepoSpec.parse("owner/repo")
    assert result.issue_number == 42
    assert (tmp_path / "repo") == result.local_path
    issue_command = runner.commands[-1]
    assert issue_command[:5] == ("gh", "issue", "create", "--repo", "owner/repo")
    assert "--label" in issue_command
    assert "ai:ready" in issue_command
    assert "executor:lazycodex" in issue_command
    assert "priority:p2" in issue_command
