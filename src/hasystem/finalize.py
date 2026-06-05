from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .command_runner import CommandSpec, SubprocessCommandRunner
from .github_client import GitHubClient
from .models import ApprovalState, LoopState
from .repo_spec import RepoSpec
from .state_store import StateStore


@dataclass(frozen=True)
class FinalizeResult:
    loop: LoopState
    commands: tuple[CommandSpec, ...]
    issue_labels_to_add: tuple[str, ...]
    issue_labels_to_remove: tuple[str, ...]


def is_approval_granted(approval: ApprovalState) -> bool:
    return approval.intent == "finalize" and approval.status == "approved"


@dataclass(frozen=True)
class FinalizeService:
    store: StateStore
    runner: SubprocessCommandRunner
    github_factory: Callable[[str], GitHubClient] = GitHubClient

    def finalize(self, repo_raw: str, local_path: Path, dry_run: bool) -> FinalizeResult:
        repo = RepoSpec.parse(repo_raw)
        loop = self.store.get_active_loop(repo.full_name)
        if loop is None:
            raise ActiveLoopNotFoundError(repo=repo.full_name)

        commands = (
            CommandSpec(args=("git", "push", "-u", "origin", loop.branch), cwd=local_path),
            CommandSpec(
                args=(
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    repo.full_name,
                    "--base",
                    "main",
                    "--head",
                    loop.branch,
                    "--title",
                    f"AI: {loop.issue.title}",
                    "--body",
                    f"Closes #{loop.issue.number}",
                ),
                cwd=local_path,
            ),
        )
        if not dry_run:
            if not is_approval_granted(loop.approval):
                raise ApprovalRequiredError(repo=repo.full_name, loop_id=loop.loop_id)
            for command in commands:
                self.runner.run(command.args, cwd=command.cwd)
            client = self.github_factory(repo.full_name)
            client.comment_issue(loop.issue.number, "AI worker completed implementation and opened a PR.")
            client.mark_done(loop.issue.number)
            self.store.save_loop(replace(loop, phase="done"))
        return FinalizeResult(
            loop=loop,
            commands=commands,
            issue_labels_to_add=("ai:done",),
            issue_labels_to_remove=("ai:in-progress",),
        )

    @staticmethod
    def record_approval(
        store: StateStore,
        repo_raw: str,
        intent: str,
        status: str,
        approval_id: str | None = None,
    ) -> LoopState:
        repo = RepoSpec.parse(repo_raw)
        loop = store.get_active_loop(repo.full_name)
        if loop is None:
            raise ActiveLoopNotFoundError(repo=repo.full_name)
        updated = loop.with_approval(ApprovalState(intent=intent, status=status, approval_id=approval_id))
        store.save_loop(updated)
        return updated


@dataclass(frozen=True)
class ApprovalRequiredError(RuntimeError):
    repo: str
    loop_id: str

    def __str__(self) -> str:
        return f"Finalization for {self.repo} loop {self.loop_id} requires approved approval state"


@dataclass(frozen=True)
class ActiveLoopNotFoundError(RuntimeError):
    repo: str

    def __str__(self) -> str:
        return f"No active loop found for {self.repo}"
