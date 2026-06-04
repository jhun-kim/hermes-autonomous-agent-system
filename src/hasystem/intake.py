from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from .command_runner import SubprocessCommandRunner
from .github_client import GitHubClient
from .repo_spec import RepoSpec
from .workspace import Workspace


DEFAULT_WORKSPACE: Final = Path("/Users/chai/Documents/GitHub")
DEFAULT_ISSUE_LABELS: Final = ("ai:ready", "executor:lazycodex", "priority:p2")


@dataclass(frozen=True)
class IntakeResult:
    repo: RepoSpec
    local_path: Path
    issue_number: int


@dataclass(frozen=True)
class IntakeService:
    workspace: Workspace
    runner: SubprocessCommandRunner

    def create_task(self, repo_raw: str, request_text: str) -> IntakeResult:
        repo = RepoSpec.parse(repo_raw)
        local_path = self.workspace.ensure_repo(repo)
        client = GitHubClient(repo=repo.full_name, runner=self.runner)
        client.ensure_ai_labels()
        issue_number = client.create_issue(
            title=_title_from_request(request_text),
            body=request_text,
            labels=DEFAULT_ISSUE_LABELS,
        )
        return IntakeResult(repo=repo, local_path=local_path, issue_number=issue_number)


def _title_from_request(request_text: str) -> str:
    first_line = request_text.strip().splitlines()[0] if request_text.strip() else "Hermes task"
    return first_line[:80]
