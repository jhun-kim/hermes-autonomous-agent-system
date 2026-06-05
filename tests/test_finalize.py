from pathlib import Path

import pytest

from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.finalize import ApprovalRequiredError, FinalizeService
from hasystem.github_client import GitHubClient
from hasystem.models import ApprovalState, GitHubIssue, LoopState
from hasystem.state_store import StateStore


def test_finalize_dry_run_builds_push_pr_and_issue_update_plan(tmp_path: Path) -> None:
    # Given: an active unapproved loop in state.
    runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    store = StateStore(tmp_path / "state.db")
    issue = GitHubIssue(number=9, title="Finish flow", body="Done?", labels=["ai:ready", "ai:in-progress"])
    loop = LoopState.start(repo="owner/repo", issue=issue, executor="lazycodex")
    store.save_loop(loop)
    client = GitHubClient(repo="owner/repo", runner=runner)
    service = FinalizeService(store=store, runner=runner, github_factory=lambda repo: client)

    # When: finalization is planned in dry-run mode.
    result = service.finalize(repo_raw="owner/repo", local_path=tmp_path / "repo", dry_run=True)

    # Then: the observable plan includes branch push, PR creation, and issue label transition.
    assert result.loop.loop_id == loop.loop_id
    assert result.commands[0].args == ("git", "push", "-u", "origin", loop.branch)
    assert result.commands[1].args[:6] == ("gh", "pr", "create", "--repo", "owner/repo", "--base")
    assert "ai:done" in result.issue_labels_to_add
    assert "ai:in-progress" in result.issue_labels_to_remove
    assert runner.commands == []


def test_finalize_refuses_unapproved_non_dry_run_before_mutating_state(tmp_path: Path) -> None:
    # Given: an active loop without an approved approval state.
    runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    store = StateStore(tmp_path / "state.db")
    issue = GitHubIssue(number=10, title="Needs approval", body="", labels=["ai:in-progress"])
    loop = LoopState.start(repo="owner/repo", issue=issue, executor="lazycodex")
    store.save_loop(loop)
    client = GitHubClient(repo="owner/repo", runner=runner)
    service = FinalizeService(store=store, runner=runner, github_factory=lambda repo: client)

    # When / Then: non-dry-run finalization is rejected before git or GitHub mutations run.
    with pytest.raises(ApprovalRequiredError, match="requires approved approval state"):
        service.finalize(repo_raw="owner/repo", local_path=tmp_path / "repo", dry_run=False)
    assert runner.commands == []
    saved = store.get_loop(loop.loop_id)
    assert saved is not None
    assert saved.phase == "plan"


def test_finalize_marks_loop_done_when_approved_changes_are_applied(tmp_path: Path) -> None:
    # Given: an active loop that has approved finalization.
    runner = RecordingCommandRunner(
        [
            CommandResult(stdout="", stderr="", returncode=0),
            CommandResult(stdout="https://github.com/owner/repo/pull/3\n", stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
        ]
    )
    store = StateStore(tmp_path / "state.db")
    issue = GitHubIssue(number=10, title="Next issue blocker", body="", labels=["ai:in-progress"])
    loop = LoopState.start(repo="owner/repo", issue=issue, executor="lazycodex")
    approved_loop = loop.with_approval(
        ApprovalState(intent="finalize", status="approved", approval_id="approval-123")
    )
    store.save_loop(approved_loop)
    client = GitHubClient(repo="owner/repo", runner=runner)
    service = FinalizeService(store=store, runner=runner, github_factory=lambda repo: client)

    # When: finalization applies real state transitions.
    service.finalize(repo_raw="owner/repo", local_path=tmp_path / "repo", dry_run=False)

    # Then: the completed loop no longer blocks the next ai:ready issue.
    saved = store.get_loop(loop.loop_id)
    assert saved is not None
    assert saved.phase == "done"
    assert store.get_active_loop("owner/repo") is None


def test_finalize_records_active_loop_approval_status(tmp_path: Path) -> None:
    # Given: an active loop in state.
    store = StateStore(tmp_path / "state.db")
    issue = GitHubIssue(number=11, title="Approval path", body="", labels=["ai:in-progress"])
    loop = LoopState.start(repo="owner/repo", issue=issue, executor="lazycodex")
    store.save_loop(loop)

    # When: finalization approval intent and status are recorded.
    updated = FinalizeService.record_approval(
        store=store,
        repo_raw="owner/repo",
        intent="finalize",
        status="approved",
        approval_id="approval-456",
    )

    # Then: the active loop exposes the approved approval state for later verification.
    assert updated.approval.intent == "finalize"
    assert updated.approval.status == "approved"
    assert updated.approval.approval_id == "approval-456"
    saved = store.get_loop(loop.loop_id)
    assert saved is not None
    assert saved.approval.status == "approved"
