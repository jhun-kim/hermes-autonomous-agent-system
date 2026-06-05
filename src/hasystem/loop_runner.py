from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from .command_runner import CommandSpec
from .github_client import GitHubClient
from .models import LoopState
from .repo_spec import RepoSpec
from .state_store import StateStore
from .worker import CodexWorkerLauncher, WorkerExecutor
from .workspace import Workspace


@dataclass(frozen=True)
class RunLoopResult:
    loop: LoopState
    worker_command: CommandSpec
    existing_active: bool


@dataclass(frozen=True)
class RunLoopService:
    workspace: Workspace
    store: StateStore
    worker: CodexWorkerLauncher
    github_factory: Callable[[str], GitHubClient] = GitHubClient

    def run_once(self, repo_raw: str, dry_run: bool, executor: WorkerExecutor = "lazycodex") -> RunLoopResult | None:
        _ = executor
        repo = RepoSpec.parse(repo_raw)
        active = self.store.get_active_loop(repo.full_name)
        if active is not None:
            active_worker = replace(self.worker, executor=active.executor)
            command = active_worker.build(
                repo_path=repo.local_path(self.workspace.base_path),
                repo=repo.full_name,
                issue=active.issue,
                branch=active.branch,
            )
            return RunLoopResult(loop=active, worker_command=command, existing_active=True)

        client = self.github_factory(repo.full_name)
        issue = client.select_next_issue(client.list_ready_issues())
        if issue is None:
            return None

        resolved_executor = resolve_worker_executor(issue.labels)
        loop = LoopState.start(repo=repo.full_name, issue=issue, executor=resolved_executor)
        local_path = repo.local_path(self.workspace.base_path) if dry_run else self.workspace.ensure_repo(repo)
        selected_worker = replace(self.worker, executor=resolved_executor)
        command = selected_worker.build(repo_path=local_path, repo=repo.full_name, issue=issue, branch=loop.branch)
        if not dry_run:
            self.store.save_loop(loop)
            client.mark_in_progress(issue.number)
            self.worker.launch(command)
        return RunLoopResult(loop=loop, worker_command=command, existing_active=False)


def resolve_worker_executor(labels: list[str]) -> WorkerExecutor:
    """Resolve worker executor labels with deterministic conflict precedence.

    OmX is the explicit non-default executor, so `executor:omx` wins when both
    executor labels are present. `executor:lazycodex` and no executor label both
    resolve to the LazyCodex/Codex default.
    """
    label_set = set(labels)
    if "executor:omx" in label_set:
        return "omx"
    return "lazycodex"
