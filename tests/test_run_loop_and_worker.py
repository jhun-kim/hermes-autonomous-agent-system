from __future__ import annotations

from pathlib import Path

from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.loop_runner import RunLoopService
from hasystem.models import GitHubIssue, LoopState
from hasystem.state_store import StateStore
from hasystem.worker import CodexWorkerLauncher, WorkerLaunchContext, resolve_worker_terminal_mode
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
    assert "issue-first agent workflow" in command.stdin_text
    assert "Run inside the cmux workspace/surface assigned to this Discord thread" in command.stdin_text
    assert "ten additive terminal surfaces" in command.stdin_text
    assert "Use Codex CLI in each surface" in command.stdin_text
    assert "especially ULW" in command.stdin_text
    assert "Do not replace cmux as the workspace/surface orchestration mechanism" in command.stdin_text
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
    assert "especially ULW" in command.args[-1]
    assert "Do not replace cmux as the workspace/surface orchestration mechanism" in command.args[-1]


def test_cmux_launcher_uses_current_workspace_surface_without_focus_switch(tmp_path: Path) -> None:
    # Given: an active cmux caller workspace and a worker command.
    launcher = CodexWorkerLauncher(cmux_binary="cmux")
    issue = GitHubIssue(number=39, title="Use cmux", body="Launch through cmux", labels=["ai:ready"])
    worker_command = launcher.build(repo_path=tmp_path, repo="owner/repo", issue=issue, branch="ai/issue-39-use-cmux")

    # When: building the cmux launch command with a caller workspace.
    cmux_command = launcher.build_cmux_command(worker_command, env={"CMUX_WORKSPACE_ID": "workspace:1"})

    # Then: a new surface is added to the caller workspace without selecting/focusing another workspace.
    assert cmux_command.args[0:2] == ("/bin/sh", "-lc")
    script = cmux_command.args[-1]
    assert "cmux --json new-surface --workspace workspace:1 --type terminal --focus false" in script
    assert "cmux send --surface" in script
    assert "codex ." in script
    assert "select-workspace" not in script
    assert "focus-pane" not in script
    assert "focus-panel" not in script


def test_cmux_launcher_creates_workspace_when_no_caller_workspace(tmp_path: Path) -> None:
    # Given: a worker command outside an existing cmux caller workspace.
    launcher = CodexWorkerLauncher(cmux_binary="cmux")
    issue = GitHubIssue(number=39, title="Use cmux", body="Launch through cmux", labels=["ai:ready"])
    worker_command = launcher.build(repo_path=tmp_path, repo="owner/repo", issue=issue, branch="ai/issue-39-use-cmux")

    # When: building the cmux launch command without cmux environment anchors.
    cmux_command = launcher.build_cmux_command(worker_command, env={})

    # Then: cmux opens one new workspace rooted at the target repository instead of Terminal.app.
    assert cmux_command.args[0:2] == ("cmux", "new-workspace")
    assert "--cwd" in cmux_command.args
    assert str(tmp_path) in cmux_command.args
    assert "--command" in cmux_command.args
    assert "--focus" in cmux_command.args
    assert "false" in cmux_command.args


def test_cmux_launcher_targets_discord_thread_workspace_and_adds_surface(tmp_path: Path) -> None:
    # Given: a Discord thread context and a worker command outside a caller cmux workspace.
    launcher = CodexWorkerLauncher(cmux_binary="cmux")
    issue = GitHubIssue(number=42, title="Thread workspace", body="Use cmux", labels=["ai:ready"])
    worker_command = launcher.build(repo_path=tmp_path, repo="owner/repo", issue=issue, branch="ai/issue-42-thread-workspace")
    context = WorkerLaunchContext(
        platform="discord",
        guild_id="guild-1",
        channel_id="channel-1",
        channel_name="agent messages",
        thread_id="1512332564218773564",
        thread_name="Hermes continuation after 2 compactions",
    )

    # When: building the cmux launch command without an active cmux env.
    cmux_command = launcher.build_cmux_command(worker_command, env={}, launch_context=context, repo="owner/repo")

    # Then: the command reuses or creates one deterministic Discord-thread workspace and adds a terminal surface.
    assert cmux_command.args[0:2] == ("/bin/sh", "-lc")
    script = cmux_command.args[-1]
    assert "workspace list" in script
    assert "discord: Hermes continuation after 2 compactions" in script
    assert "1512332564218773564"[-24:] in script
    assert "owner/repo" in script
    assert "new-workspace --name" in script
    assert "new-surface --workspace \"$workspace_id\" --type terminal --focus false" in script
    assert "cmux send --surface" in script
    assert "codex ." in script


def test_cmux_launcher_distributes_parallel_workers_as_surfaces_in_same_discord_workspace(tmp_path: Path) -> None:
    # Given: two different worker engines for the same Discord thread.
    context = WorkerLaunchContext(platform="discord", thread_id="thread-42", thread_name="Implementation Room")
    issue = GitHubIssue(number=42, title="Parallel workers", body="Split work", labels=["ai:ready"])
    codex = CodexWorkerLauncher(cmux_binary="cmux")
    omx = CodexWorkerLauncher(cmux_binary="cmux", executor="omx")
    codex_command = codex.build(repo_path=tmp_path, repo="owner/repo", issue=issue, branch="ai/issue-42-parallel")
    omx_command = omx.build(repo_path=tmp_path, repo="owner/repo", issue=issue, branch="ai/issue-42-parallel")

    # When: both launch commands are built for the same Discord thread.
    codex_script = codex.build_cmux_command(codex_command, env={}, launch_context=context, repo="owner/repo").args[-1]
    omx_script = omx.build_cmux_command(omx_command, env={}, launch_context=context, repo="owner/repo").args[-1]

    # Then: both target the same cmux workspace name and differ only by worker engine surface command.
    expected_workspace = "discord: Implementation Room [thread-42] · owner/repo"
    assert expected_workspace in codex_script
    assert expected_workspace in omx_script
    assert "codex ." in codex_script
    assert "omx exec --full-auto" in omx_script
    assert codex_script.count("new-surface") == 1
    assert omx_script.count("new-surface") == 1


def test_parallel_surface_plan_defaults_to_ten_codex_worktrees_and_branches(tmp_path: Path) -> None:
    # Given: a Discord issue that should fan out into the standard 10 cmux surfaces.
    repo_path = tmp_path / "repo"
    issue = GitHubIssue(number=51, title="Ten surfaces", body="Parallelize", labels=["ai:ready"])
    launcher = CodexWorkerLauncher(cmux_binary="cmux")

    # When: the launcher builds the standard parallel plan.
    plan = launcher.build_parallel_surface_plan(
        repo_path=repo_path,
        repo="owner/repo",
        issue=issue,
        base_branch="ai/issue-51-ten-surfaces",
    )

    # Then: exactly ten isolated worktrees/branches are prepared, each running Codex CLI.
    assert len(plan) == 10
    assert plan[0].index == 1
    assert plan[-1].index == 10
    assert plan[0].total == 10
    assert plan[0].branch == "ai/issue-51-ten-surfaces/surface-01"
    assert plan[-1].branch == "ai/issue-51-ten-surfaces/surface-10"
    assert plan[0].worktree_path == tmp_path / "repo-issue-51-surface-01"
    assert plan[-1].worktree_path == tmp_path / "repo-issue-51-surface-10"
    assert plan[0].setup_command.args == (
        "git",
        "worktree",
        "add",
        "-B",
        "ai/issue-51-ten-surfaces/surface-01",
        str(tmp_path / "repo-issue-51-surface-01"),
        "HEAD",
    )
    assert all(item.worker_command.args == ("codex", ".") for item in plan)
    assert "Parallel surface: 01/10" in plan[0].worker_command.stdin_text
    assert "branch ai/issue-51-ten-surfaces/surface-10" in plan[-1].worker_command.stdin_text
    assert "OmX/OmO skills/workflows" in plan[0].worker_command.stdin_text


def test_parallel_surface_plan_can_use_custom_count_and_base_ref(tmp_path: Path) -> None:
    # Given: a smaller plan requested by a caller or test harness.
    repo_path = tmp_path / "repo"
    issue = GitHubIssue(number=52, title="Custom plan", body="Parallelize", labels=["ai:ready"])
    launcher = CodexWorkerLauncher(cmux_binary="cmux")

    # When: the caller overrides the surface count and base ref.
    plan = launcher.build_parallel_surface_plan(
        repo_path=repo_path,
        repo="owner/repo",
        issue=issue,
        base_branch="ai/issue-52-custom-plan",
        surface_count=3,
        base_ref="origin/main",
    )

    # Then: each worktree branch is based from the requested ref.
    assert len(plan) == 3
    assert plan[2].setup_command.args[-1] == "origin/main"
    assert "Parallel surface: 03/03" in plan[2].worker_command.stdin_text


def test_omo_worker_launcher_builds_surface_engine_command(tmp_path: Path) -> None:
    # Given: an OmO executor request.
    launcher = CodexWorkerLauncher(executor="omo")
    issue = GitHubIssue(number=42, title="Run with OmO", body="Use OmO", labels=["ai:ready", "executor:omo"])

    # When: the worker command is built.
    command = launcher.build(repo_path=tmp_path, repo="owner/repo", issue=issue, branch="ai/issue-42-run-with-omo")

    # Then: OmO is represented as a worker engine that can be run inside a cmux surface.
    assert command.cwd == tmp_path
    assert command.args[0:3] == ("omo", "exec", "--full-auto")
    assert "Issue #42: Run with OmO" in command.args[-1]


def test_launcher_falls_back_to_direct_runner_when_cmux_missing(tmp_path: Path, monkeypatch) -> None:
    # Given: cmux preference is enabled, but the host has no cmux binary.
    runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    launcher = CodexWorkerLauncher(runner=runner)
    issue = GitHubIssue(number=39, title="Use cmux", body="Launch through cmux", labels=["ai:ready"])
    worker_command = launcher.build(repo_path=tmp_path, repo="owner/repo", issue=issue, branch="ai/issue-39-use-cmux")
    monkeypatch.delenv("HASYSTEM_WORKER_TERMINAL", raising=False)
    monkeypatch.setattr("hasystem.worker.shutil.which", lambda _binary: None)

    # When: launching in automatic mode.
    launcher.launch(worker_command)

    # Then: headless fallback runs the worker directly instead of opening Terminal.app.
    assert runner.commands == [("codex", ".")]


def test_launcher_uses_terminal_app_when_terminal_mode_requested(tmp_path: Path, monkeypatch) -> None:
    # Given: cmux is installed, but the operator requested the legacy Terminal.app environment.
    runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    launcher = CodexWorkerLauncher(runner=runner)
    issue = GitHubIssue(number=69, title="Terminal mode", body="Use Terminal.app", labels=["ai:ready"])
    worker_command = launcher.build(repo_path=tmp_path, repo="owner/repo", issue=issue, branch="ai/issue-69-terminal-mode")
    monkeypatch.setenv("HASYSTEM_WORKER_TERMINAL", "terminal")
    monkeypatch.setattr("hasystem.worker.shutil.which", lambda binary: f"/usr/bin/{binary}" if binary == "cmux" else None)

    # When: launching with the terminal mode override.
    launcher.launch(worker_command)

    # Then: the launcher uses Terminal.app instead of cmux workspace/surface commands.
    expected = launcher.build_terminal_command(worker_command)
    assert runner.commands == [expected.args]
    assert runner.commands[0][0:2] == ("osascript", "-e")


def test_worker_terminal_mode_env_aliases() -> None:
    assert resolve_worker_terminal_mode(prefer_cmux=True, env={}) == "auto"
    assert resolve_worker_terminal_mode(prefer_cmux=False, env={}) == "terminal"
    assert resolve_worker_terminal_mode(prefer_cmux=True, env={"HASYSTEM_WORKER_TERMINAL": "Terminal.app"}) == "terminal"
    assert resolve_worker_terminal_mode(prefer_cmux=True, env={"HASYSTEM_WORKER_TERMINAL": "headless"}) == "direct"


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


def test_run_loop_dry_run_resolves_omo_executor_from_issue_label(tmp_path: Path) -> None:
    # Given: the selected issue explicitly requests the OmO executor.
    command_runner = RecordingCommandRunner([CommandResult(stdout="", stderr="", returncode=0)])
    issue = GitHubIssue(number=12, title="Run with OmO", body="Use OmO", labels=["ai:ready", "executor:omo"])
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

    # Then: OmO is resolved as a worker engine for a cmux surface.
    assert result is not None
    assert result.loop.executor == "omo"
    assert result.worker_command.args[0:3] == ("omo", "exec", "--full-auto")


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
