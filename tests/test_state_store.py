from pathlib import Path

from hasystem.models import GitHubIssue, LoopState
from hasystem.state_store import StateStore


def test_state_store_creates_state_db_and_persists_loop(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    store = StateStore(db_path)

    issue = GitHubIssue(number=123, title="Fix login bug", labels=["ai:ready", "priority:p1"])
    loop = LoopState.start(repo="owner/repo", issue=issue, executor="lazycodex")

    store.save_loop(loop)
    loaded = store.get_loop(loop.loop_id)

    assert db_path.exists()
    assert loaded is not None
    assert loaded.loop_id == loop.loop_id
    assert loaded.repo == "owner/repo"
    assert loaded.issue.number == 123
    assert loaded.issue.title == "Fix login bug"
    assert loaded.issue.labels == ["ai:ready", "priority:p1"]
    assert loaded.branch == "ai/issue-123-fix-login-bug"
    assert loaded.executor == "lazycodex"
    assert loaded.phase == "plan"
    assert loaded.approval.status is None


def test_state_store_returns_active_loop_before_starting_another(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state.db")
    issue = GitHubIssue(number=1, title="First task", labels=["ai:ready"])
    loop = LoopState.start(repo="owner/repo", issue=issue, executor="lazycodex")
    store.save_loop(loop)

    active = store.get_active_loop("owner/repo")

    assert active is not None
    assert active.loop_id == loop.loop_id
    assert active.phase == "plan"
