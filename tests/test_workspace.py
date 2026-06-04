from pathlib import Path

import pytest

from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.repo_spec import RepoSpec
from hasystem.workspace import Workspace, WorkspacePathError


def test_workspace_clones_repo_when_missing(tmp_path: Path) -> None:
    # Given: a workspace without the target repository.
    runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    workspace = Workspace(base_path=tmp_path, runner=runner)
    spec = RepoSpec.parse("owner/repo")

    # When: the repo is ensured locally.
    local_path = workspace.ensure_repo(spec)

    # Then: git clone is invoked under the configured workspace root.
    assert local_path == tmp_path / "repo"
    assert runner.commands == [
        ("git", "clone", "https://github.com/owner/repo.git", str(tmp_path / "repo")),
    ]


def test_workspace_updates_repo_when_git_checkout_exists(tmp_path: Path) -> None:
    # Given: a workspace containing an existing git checkout.
    checkout = tmp_path / "repo"
    (checkout / ".git").mkdir(parents=True)
    runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    workspace = Workspace(base_path=tmp_path, runner=runner)

    # When: the repo is ensured locally.
    local_path = workspace.ensure_repo(RepoSpec.parse("owner/repo"))

    # Then: git pull updates the existing checkout.
    assert local_path == checkout
    assert runner.commands == [("git", "-C", str(checkout), "pull", "--ff-only")]


@pytest.mark.parametrize("repo_name", [".", ".."])
def test_workspace_rejects_repo_paths_outside_base(tmp_path: Path, repo_name: str) -> None:
    # Given: a repo spec constructed outside the parser boundary.
    runner = RecordingCommandRunner([])
    workspace = Workspace(base_path=tmp_path / "workspace", runner=runner)
    spec = RepoSpec(owner="owner", name=repo_name)

    # When / Then: workspace resolution refuses to escape the configured root.
    with pytest.raises(WorkspacePathError):
        workspace.ensure_repo(spec)
    assert runner.commands == []
