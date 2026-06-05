from __future__ import annotations

import json
from pathlib import Path

import pytest

from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.discord_request import (
    DiscordAutomationService,
    DiscordRequestParseError,
    DiscordRequestRouterConfig,
    parse_discord_request,
)
from hasystem.gateway import DiscordGatewayEvent, build_gateway_response, load_router_config
from hasystem.github_client import DEFAULT_AI_LABELS, GitHubClient
from hasystem.intake import IntakeService
from hasystem.loop_runner import RunLoopService
from hasystem.state_store import StateStore
from hasystem.worker import CodexWorkerLauncher
from hasystem.workspace import Workspace


def test_parse_discord_request_from_json_payload() -> None:
    payload = json.dumps({"repo": "owner/repo", "request": "Fix auth and run tests"})

    request = parse_discord_request(payload)

    assert request.repo_raw == "owner/repo"
    assert request.request_text == "Fix auth and run tests"


def test_parse_gateway_event_envelope_from_json_payload() -> None:
    payload = json.dumps(
        {
            "platform": "discord",
            "guild_id": "guild-1",
            "channel_id": "channel-1",
            "channel_name": "planning",
            "thread_id": "thread-1",
            "thread_name": "Issue 36 planning thread",
            "sender": {"id": "user-1", "display_name": "Chai"},
            "message": {"content": "Hermes, ship gateway routing"},
            "repo": "hasystem",
            "dry_run": True,
            "no_run_loop": True,
        }
    )

    event = DiscordGatewayEvent.from_json(payload)

    assert event.platform == "discord"
    assert event.guild_id == "guild-1"
    assert event.channel_id == "channel-1"
    assert event.channel_name == "planning"
    assert event.thread_id == "thread-1"
    assert event.thread_name == "Issue 36 planning thread"
    assert event.sender_id == "user-1"
    assert event.sender_display_name == "Chai"
    assert event.raw_message == "Hermes, ship gateway routing"
    assert event.repo_hint == "hasystem"
    assert event.dry_run is True
    assert event.no_run_loop is True


def test_gateway_event_repo_hint_strips_hermes_prefix_in_structured_response(tmp_path: Path) -> None:
    runner = RecordingCommandRunner([])
    workspace = Workspace(tmp_path / "workspace", runner)
    service = DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=StateStore(tmp_path / "state.db"),
            worker=CodexWorkerLauncher(runner=runner),
            github_factory=lambda repo: GitHubClient(repo=repo, runner=runner),
        ),
        router_config=DiscordRequestRouterConfig(repo_aliases={"hasystem": "owner/repo"}),
    )
    event = DiscordGatewayEvent.from_json(
        json.dumps({"content": "Hermes, ship gateway routing", "repo": "hasystem", "dry_run": True})
    )

    payload = build_gateway_response(service=service, event=event, dry_run_override=None, no_run_loop_override=None)

    assert payload["parsed_request"]["request_text"] == "ship gateway routing"


def test_parse_discord_request_from_freeform_command() -> None:
    request = parse_discord_request("/agent https://github.com/owner/repo.git add Discord automation")

    assert request.repo_raw == "https://github.com/owner/repo.git"
    assert request.request_text == "add Discord automation"


def test_parse_discord_request_resolves_alias_in_natural_language() -> None:
    config = DiscordRequestRouterConfig(
        repo_aliases={"hermes-autonomous-agent-system": "jhun-kim/hermes-autonomous-agent-system"}
    )

    request = parse_discord_request(
        "Hermes, hermes-autonomous-agent-system 다음 단계 개발해줘", config=config
    )

    assert request.repo_raw == "jhun-kim/hermes-autonomous-agent-system"
    assert request.request_text == "다음 단계 개발해줘"


def test_parse_discord_request_uses_channel_default_for_friend_like_message() -> None:
    config = DiscordRequestRouterConfig(
        channel_default_repos={"1512060115757432833": "jhun-kim/hermes-autonomous-agent-system"}
    )

    request = parse_discord_request(
        "Hermes, 이 레포에 자동 finalize 붙여줘",
        config=config,
        thread_id="1512060115757432833",
    )

    assert request.repo_raw == "jhun-kim/hermes-autonomous-agent-system"
    assert request.request_text == "이 레포에 자동 finalize 붙여줘"


def test_parse_discord_request_prefers_thread_then_channel_then_default_repo() -> None:
    config = DiscordRequestRouterConfig(
        default_repo="owner/default",
        channel_default_repos={
            "channel-1": "owner/channel",
            "thread-1": "owner/thread",
        },
    )

    request = parse_discord_request(
        "Hermes, implement routing",
        config=config,
        channel_id="channel-1",
        thread_id="thread-1",
    )

    assert request.repo_raw == "owner/thread"
    assert request.request_text == "implement routing"


def test_load_router_config_from_json_file_and_cli_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "gateway.json"
    config_path.write_text(
        json.dumps(
            {
                "repo_aliases": {"hasystem": "owner/from-config"},
                "channel_default_repos": {"channel-1": "owner/channel-config"},
                "allow_repos": ["owner/from-cli", "owner/thread-cli"],
                "default_repo": "owner/default-config",
                "compaction_rollover_threshold": 3,
                "godmode": {
                    "authorized_channel_ids": ["thread-1"],
                    "authorized_sender_ids": ["user-1"],
                    "max_iterations": 2,
                    "max_runtime_seconds": 60,
                    "max_failures": 2,
                    "create_issue_when_empty": True,
                    "seed_issue_title": "Seed next GODMODE task",
                    "seed_issue_body": "Find the next concrete task.",
                    "seed_issue_labels": ["ai:ready", "executor:omx", "priority:p2"],
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_router_config(
        config_path,
        repo_alias_overrides={"hasystem": "owner/from-cli"},
        channel_default_repo_overrides={"thread-1": "owner/thread-cli"},
        default_repo_override=None,
    )

    assert config.resolve_alias("hasystem") == "owner/from-cli"
    assert config.default_for_context(channel_id="channel-1") == "owner/channel-config"
    assert config.default_for_context(thread_id="thread-1") == "owner/thread-cli"
    assert config.default_repo == "owner/default-config"
    assert config.allow_repos == frozenset({"owner/from-cli", "owner/thread-cli"})
    assert config.compaction_rollover_threshold == 3
    assert config.godmode.authorized_channel_ids == frozenset({"thread-1"})
    assert config.godmode.authorized_sender_ids == frozenset({"user-1"})
    assert config.godmode.max_iterations == 2
    assert config.godmode.max_runtime_seconds == 60
    assert config.godmode.max_failures == 2
    assert config.godmode.create_issue_when_empty is True
    assert config.godmode.seed_issue_title == "Seed next GODMODE task"
    assert config.godmode.seed_issue_body == "Find the next concrete task."
    assert config.godmode.seed_issue_labels == ("ai:ready", "executor:omx", "priority:p2")


def test_parse_discord_request_rejects_repos_not_in_allowlist() -> None:
    config = DiscordRequestRouterConfig(default_repo="owner/default", allow_repos=frozenset({"owner/allowed"}))

    with pytest.raises(DiscordRequestParseError, match="not allowed"):
        parse_discord_request("Hermes, ship it", config=config)


def test_parse_discord_request_resolves_repo_field_alias() -> None:
    config = DiscordRequestRouterConfig(
        repo_aliases={"hasystem": "jhun-kim/hermes-autonomous-agent-system"}
    )

    request = parse_discord_request("repo: hasystem\nrequest: 자연어 라우터 추가", config=config)

    assert request.repo_raw == "jhun-kim/hermes-autonomous-agent-system"
    assert request.request_text == "자연어 라우터 추가"


def test_parse_discord_request_requires_repo_and_task() -> None:
    with pytest.raises(DiscordRequestParseError):
        parse_discord_request("/agent please do a task without a repo")



def test_discord_automation_intakes_issue_and_launches_worker(tmp_path: Path) -> None:
    issue_json = json.dumps(
        [
            {
                "number": 42,
                "title": "Fix auth and run tests",
                "body": "Fix auth and run tests",
                "labels": [{"name": "ai:ready"}, {"name": "priority:p2"}],
            }
        ]
    )
    runner = RecordingCommandRunner(
        [
            CommandResult(stdout="", stderr="", returncode=0),
            *[CommandResult(stdout="", stderr="", returncode=0) for _ in DEFAULT_AI_LABELS],
            CommandResult(stdout="https://github.com/owner/repo/issues/42\n", stderr="", returncode=0),
            CommandResult(stdout=issue_json, stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
        ]
    )
    workspace = Workspace(tmp_path / "workspace", runner)
    service = DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=StateStore(tmp_path / "state.db"),
            worker=CodexWorkerLauncher(runner=runner),
            github_factory=lambda repo: GitHubClient(repo=repo, runner=runner),
        ),
    )

    result = service.handle('{"repo":"owner/repo","request":"Fix auth and run tests"}')

    assert result.intake is not None
    assert result.intake.issue_number == 42
    assert result.loop is not None
    assert result.loop.loop.issue.number == 42
    assert result.loop.worker_command.args == ("codex", ".")
    assert runner.commands[0][:2] == ("git", "clone")
    assert ("gh", "issue", "edit", "42", "--repo", "owner/repo", "--add-label", "ai:in-progress", "--remove-label", "ai:ready") in runner.commands
    assert runner.commands[-1] == ("codex", ".")
    assert result.loop.worker_command.stdin_text is not None
    assert runner.stdin_values[-1] == result.loop.worker_command.stdin_text
    assert "issue-first agent workflow" in result.loop.worker_command.stdin_text
    assert "do not use OmO/OmX as the terminal/session orchestration mechanism" in result.loop.worker_command.stdin_text


def test_discord_automation_maps_thread_to_cmux_workspace_surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: cmux is installed and a Discord thread starts a run-loop worker.
    monkeypatch.setattr("hasystem.worker.shutil.which", lambda binary: f"/usr/bin/{binary}" if binary == "cmux" else None)
    issue_json = json.dumps(
        [
            {
                "number": 42,
                "title": "Fix auth and run tests",
                "body": "Fix auth and run tests",
                "labels": [{"name": "ai:ready"}, {"name": "priority:p2"}],
            }
        ]
    )
    runner = RecordingCommandRunner(
        [
            CommandResult(stdout="", stderr="", returncode=0),
            *[CommandResult(stdout="", stderr="", returncode=0) for _ in DEFAULT_AI_LABELS],
            CommandResult(stdout="https://github.com/owner/repo/issues/42\n", stderr="", returncode=0),
            CommandResult(stdout=issue_json, stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
            CommandResult(stdout="", stderr="", returncode=0),
        ]
    )
    workspace = Workspace(tmp_path / "workspace", runner)
    service = DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=StateStore(tmp_path / "state.db"),
            worker=CodexWorkerLauncher(runner=runner),
            github_factory=lambda repo: GitHubClient(repo=repo, runner=runner),
        ),
        router_config=DiscordRequestRouterConfig(default_repo="owner/repo"),
    )

    # When: the message is handled with Discord thread metadata.
    result = service.handle(
        "Hermes, Fix auth and run tests",
        channel_id="channel-1",
        channel_name="agent messages",
        thread_id="thread-42",
        thread_name="Implementation Room",
    )

    # Then: the worker engine is launched in a cmux surface within the Discord-thread workspace.
    assert result.loop is not None
    assert runner.commands[-1][0:2] == ("/bin/sh", "-lc")
    script = runner.commands[-1][-1]
    assert "workspace list" in script
    assert "discord: Implementation Room [thread-42] · owner/repo" in script
    assert "new-surface --workspace \"$workspace_id\" --type terminal --focus false" in script
    assert "codex ." in script


def test_discord_automation_dry_run_only_parses_message(tmp_path: Path) -> None:
    runner = RecordingCommandRunner([])
    workspace = Workspace(tmp_path / "workspace", runner)
    service = DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=StateStore(tmp_path / "state.db"),
            worker=CodexWorkerLauncher(runner=runner),
            github_factory=lambda repo: GitHubClient(repo=repo, runner=runner),
        ),
        router_config=DiscordRequestRouterConfig(default_repo="owner/repo"),
    )

    result = service.handle("Hermes, Ship it", dry_run=True)

    assert result.dry_run is True
    assert result.request.repo_raw == "owner/repo"
    assert result.request.request_text == "Ship it"
    assert result.intake is None
    assert result.loop is None
    assert runner.commands == []


def test_gateway_response_dry_run_is_structured_and_non_mutating(tmp_path: Path) -> None:
    runner = RecordingCommandRunner([])
    workspace = Workspace(tmp_path / "workspace", runner)
    service = DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=StateStore(tmp_path / "state.db"),
            worker=CodexWorkerLauncher(runner=runner),
            github_factory=lambda repo: GitHubClient(repo=repo, runner=runner),
        ),
        router_config=DiscordRequestRouterConfig(
            repo_aliases={"hasystem": "jhun-kim/hermes-autonomous-agent-system"}
        ),
    )
    event = DiscordGatewayEvent.from_json(
        json.dumps(
            {
                "platform": "discord",
                "channel_id": "channel-1",
                "content": "Hermes, hasystem integrate gateway adapter",
                "dry_run": True,
            }
        )
    )

    payload = build_gateway_response(service=service, event=event, dry_run_override=None, no_run_loop_override=None)

    assert payload["status"] == "dry_run"
    assert payload["repo"] == "jhun-kim/hermes-autonomous-agent-system"
    assert payload["parsed_request"] == {
        "repo_raw": "jhun-kim/hermes-autonomous-agent-system",
        "request_text": "integrate gateway adapter",
    }
    assert payload["intake"] is None
    assert payload["loop"] is None
    assert payload["hints"]["next_action"] == "Remove dry-run to create an issue and optionally start the run loop."
    assert runner.commands == []


def test_gateway_response_records_compaction_and_routes_discord_rollover(tmp_path: Path) -> None:
    # Given: a Discord gateway compaction event and a configurable threshold of two.
    runner = RecordingCommandRunner([])
    store = StateStore(tmp_path / "state.db")
    workspace = Workspace(tmp_path / "workspace", runner)
    service = DiscordAutomationService(
        intake=IntakeService(workspace=workspace, runner=runner),
        loop_runner=RunLoopService(
            workspace=workspace,
            store=store,
            worker=CodexWorkerLauncher(runner=runner),
            github_factory=lambda repo: GitHubClient(repo=repo, runner=runner),
        ),
        router_config=DiscordRequestRouterConfig(default_repo="owner/repo", compaction_rollover_threshold=2),
    )
    event = DiscordGatewayEvent.from_json(
        json.dumps(
            {
                "platform": "discord",
                "channel_id": "channel-1",
                "thread_id": "thread-1",
                "content": "continue work",
                "context_compaction": True,
                "latest_user_goal": "finish rollover",
                "active_issue_number": 19,
            }
        )
    )
    discord = GatewayFakeDiscordClient()

    # When: two compactions arrive through the gateway response seam.
    first = build_gateway_response(
        service=service,
        event=event,
        dry_run_override=None,
        no_run_loop_override=None,
        state_store=store,
        discord_client=discord,
    )
    second = build_gateway_response(
        service=service,
        event=event,
        dry_run_override=None,
        no_run_loop_override=None,
        state_store=store,
        discord_client=discord,
    )

    # Then: the gateway exposes deterministic count state and routes the rollover into a new Discord thread.
    assert first["status"] == "compaction_recorded"
    assert first["continuation"]["compaction_count"] == 1
    assert second["status"] == "rollover_required"
    assert second["continuation"]["compaction_count"] == 2
    assert second["continuation"]["new_thread_id"] == "thread-gateway-new"
    assert discord.created_parent_channel_ids == ["channel-1"]
    assert discord.messages[0][0] == "thread-1"
    assert discord.messages[1][0] == "thread-gateway-new"
    assert runner.commands == []


class GatewayFakeDiscordClient:
    def __init__(self) -> None:
        self.created_parent_channel_ids: list[str] = []
        self.messages: list[tuple[str, str]] = []

    def create_public_thread(self, *, parent_channel_id: str, source_thread_id: str | None, name: str):
        from hasystem.compaction_rollover import DiscordCreatedThread

        self.created_parent_channel_ids.append(parent_channel_id)
        assert source_thread_id == "thread-1"
        assert name == "Hermes continuation after 2 compactions"
        return DiscordCreatedThread(thread_id="thread-gateway-new", name=name)

    def post_message(self, *, channel_id: str, content: str) -> None:
        self.messages.append((channel_id, content))
