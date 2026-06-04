from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .command_runner import SubprocessCommandRunner
from .repo_spec import RepoSpec


@dataclass(frozen=True)
class WorkspacePathError(ValueError):
    workspace_root: Path
    local_path: Path

    def __str__(self) -> str:
        return f"Repository path escapes workspace: {self.local_path} is not under {self.workspace_root}"


@dataclass(frozen=True)
class Workspace:
    base_path: Path
    runner: SubprocessCommandRunner

    def ensure_repo(self, repo: RepoSpec) -> Path:
        self.base_path.mkdir(parents=True, exist_ok=True)
        local_path = repo.local_path(self.base_path)
        _ensure_under_workspace(workspace_root=self.base_path, local_path=local_path)
        if (local_path / ".git").exists():
            self.runner.run(["git", "-C", str(local_path), "pull", "--ff-only"])
            return local_path
        self.runner.run(["git", "clone", repo.clone_url, str(local_path)])
        return local_path


def _ensure_under_workspace(workspace_root: Path, local_path: Path) -> None:
    resolved_root = workspace_root.resolve()
    resolved_local = local_path.resolve()
    if resolved_root in resolved_local.parents:
        return
    raise WorkspacePathError(workspace_root=workspace_root, local_path=local_path)
