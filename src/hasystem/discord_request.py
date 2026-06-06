from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Final

from .godmode import GodmodeAuthorizationError, GodmodeConfig, GodmodeContext, GodmodeResult, GodmodeService, parse_godmode_command
from .intake import IntakeResult, IntakeService
from .loop_runner import RunLoopResult, RunLoopService
from .worker import WorkerLaunchContext

JsonValue = Any

_REPO_PATTERN: Final = re.compile(
    r"(?P<repo>https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
)
_REPO_FIELD_PATTERN: Final = re.compile(r"^\s*(?:repo|repository)\s*[:=]\s*(?P<repo>\S+)\s*$", re.IGNORECASE)
_REQUEST_FIELD_PATTERN: Final = re.compile(r"^\s*(?:request|task|prompt)\s*[:=]\s*(?P<request>.*)$", re.IGNORECASE)
_COMMAND_PREFIX_PATTERN: Final = re.compile(r"^\s*(?:/agent|!agent|@hermes|hermes)\b\s*", re.IGNORECASE)


@dataclass(frozen=True)
class DiscordRequest:
    repo_raw: str
    request_text: str


@dataclass(frozen=True)
class DiscordRequestRouterConfig:
    """Options that let Discord messages feel like natural chat."""

    repo_aliases: dict[str, str] = field(default_factory=dict)
    default_repo: str | None = None
    channel_default_repos: dict[str, str] = field(default_factory=dict)
    allow_repos: frozenset[str] = frozenset()
    godmode: GodmodeConfig = field(default_factory=GodmodeConfig)

    def default_for_context(self, *, channel_id: str | None = None, thread_id: str | None = None) -> str | None:
        if thread_id and thread_id in self.channel_default_repos:
            return self.channel_default_repos[thread_id]
        if channel_id and channel_id in self.channel_default_repos:
            return self.channel_default_repos[channel_id]
        return self.default_repo

    def resolve_alias(self, repo_or_alias: str) -> str:
        key = repo_or_alias.strip()
        return self.repo_aliases.get(key) or self.repo_aliases.get(key.lower()) or key

    def ensure_allowed(self, repo_raw: str) -> str:
        repo = self.resolve_alias(repo_raw)
        if self.allow_repos and repo not in self.allow_repos:
            raise DiscordRequestParseError(f"Repo {repo} is not allowed by router config")
        return repo


@dataclass(frozen=True)
class DiscordAutomationResult:
    request: DiscordRequest
    intake: IntakeResult | None
    loop: RunLoopResult | None
    dry_run: bool
    godmode: GodmodeResult | None = None


@dataclass(frozen=True)
class DiscordAutomationService:
    intake: IntakeService
    loop_runner: RunLoopService
    router_config: DiscordRequestRouterConfig = field(default_factory=DiscordRequestRouterConfig)

    def handle(
        self,
        raw_message: str,
        *,
        dry_run: bool = False,
        run_loop: bool = True,
        channel_id: str | None = None,
        thread_id: str | None = None,
        sender_id: str | None = None,
        guild_id: str | None = None,
        channel_name: str | None = None,
        thread_name: str | None = None,
    ) -> DiscordAutomationResult:
        godmode_action = parse_godmode_command(raw_message)
        if godmode_action is not None:
            repo_raw = self.router_config.default_for_context(channel_id=channel_id, thread_id=thread_id)
            if repo_raw is None:
                raise DiscordRequestParseError("godmode requires a configured repo hint or channel/default repo")
            repo = self.router_config.ensure_allowed(repo_raw)
            conversation_id = f"discord:{thread_id or channel_id or sender_id or 'unknown'}"
            try:
                godmode = GodmodeService(loop_runner=self.loop_runner, config=self.router_config.godmode).handle(
                    godmode_action,
                    GodmodeContext(
                        conversation_id=conversation_id,
                        repo=repo,
                        channel_id=channel_id,
                        thread_id=thread_id,
                        sender_id=sender_id,
                        guild_id=guild_id,
                        channel_name=channel_name,
                        thread_name=thread_name,
                    ),
                )
            except GodmodeAuthorizationError as exc:
                raise DiscordRequestParseError(str(exc)) from exc
            return DiscordAutomationResult(
                request=DiscordRequest(repo_raw=repo, request_text=raw_message.strip()),
                intake=None,
                loop=None,
                dry_run=dry_run,
                godmode=godmode,
            )

        request = parse_discord_request(
            raw_message,
            config=self.router_config,
            channel_id=channel_id,
            thread_id=thread_id,
        )
        if dry_run:
            return DiscordAutomationResult(request=request, intake=None, loop=None, dry_run=True)

        intake_result = self.intake.create_task(repo_raw=request.repo_raw, request_text=request.request_text)
        loop_result = (
            self.loop_runner.run_once(
                repo_raw=request.repo_raw,
                dry_run=False,
                launch_context=WorkerLaunchContext(
                    platform="discord",
                    guild_id=guild_id,
                    channel_id=channel_id,
                    channel_name=channel_name,
                    thread_id=thread_id,
                    thread_name=thread_name,
                    conversation_id=f"discord:{thread_id or channel_id or sender_id or 'unknown'}",
                ),
            )
            if run_loop
            else None
        )
        return DiscordAutomationResult(request=request, intake=intake_result, loop=loop_result, dry_run=False)


def parse_discord_request(
    raw_message: str,
    *,
    config: DiscordRequestRouterConfig | None = None,
    channel_id: str | None = None,
    thread_id: str | None = None,
) -> DiscordRequest:
    """Parse a Discord/Gateway task message into repo + request text."""
    config = config or DiscordRequestRouterConfig()
    raw_message = raw_message.strip()
    if not raw_message:
        raise DiscordRequestParseError("Discord request is empty")

    parsed_json = _parse_json_request(raw_message, config=config)
    if parsed_json is not None:
        return parsed_json

    repo_from_field: str | None = None
    request_lines: list[str] = []
    for line in raw_message.splitlines():
        repo_field = _REPO_FIELD_PATTERN.match(line)
        if repo_field:
            repo_from_field = config.ensure_allowed(repo_field.group("repo"))
            continue
        request_field = _REQUEST_FIELD_PATTERN.match(line)
        if request_field:
            request_lines.append(request_field.group("request"))
            continue
        request_lines.append(line)

    text_without_repo_field = "\n".join(request_lines).strip()
    repo_match = _REPO_PATTERN.search(text_without_repo_field)
    alias_match = None if repo_match else _find_alias_match(text_without_repo_field, config.repo_aliases)

    if repo_from_field:
        repo_raw = repo_from_field
        request_text = text_without_repo_field
    elif repo_match:
        repo_raw = config.ensure_allowed(repo_match.group("repo"))
        request_text = (text_without_repo_field[: repo_match.start()] + text_without_repo_field[repo_match.end() :]).strip()
    elif alias_match:
        _alias, owner_repo, start, end = alias_match
        repo_raw = config.ensure_allowed(owner_repo)
        request_text = (text_without_repo_field[:start] + text_without_repo_field[end:]).strip()
    else:
        repo_raw = config.default_for_context(channel_id=channel_id, thread_id=thread_id)
        request_text = text_without_repo_field

    if repo_raw is None:
        raise DiscordRequestParseError(
            "Could not find a GitHub repo. Mention owner/repo, a GitHub URL, a configured alias, or set a default repo for this channel."
        )

    repo_raw = config.ensure_allowed(repo_raw)
    request_text = _strip_command_prefix(request_text).strip(" ,:：-—\n\t")
    if not request_text:
        raise DiscordRequestParseError("Could not find task text after the repo/alias/default context.")
    return DiscordRequest(repo_raw=repo_raw, request_text=request_text)


def _parse_json_request(raw_message: str, *, config: DiscordRequestRouterConfig) -> DiscordRequest | None:
    try:
        data = json.loads(raw_message)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        raise DiscordRequestParseError("JSON Discord request must be an object")
    repo = _optional_str(data.get("repo")) or _optional_str(data.get("repository")) or _optional_str(data.get("repo_hint"))
    request = (
        _optional_str(data.get("request"))
        or _optional_str(data.get("task"))
        or _optional_str(data.get("prompt"))
        or _optional_str(data.get("content"))
        or _optional_str(data.get("text"))
    )
    if not repo:
        raise DiscordRequestParseError("JSON Discord request needs a repo field")
    if not request:
        raise DiscordRequestParseError("JSON Discord request needs request/task/prompt/content text")
    request_text = _strip_command_prefix(request).strip(" ,:：-—\n\t")
    if not request_text:
        raise DiscordRequestParseError("Could not find task text after the repo/alias/default context.")
    return DiscordRequest(repo_raw=config.ensure_allowed(repo.strip()), request_text=request_text)


def _find_alias_match(text: str, aliases: dict[str, str]) -> tuple[str, str, int, int] | None:
    """Return the first configured alias mention, preferring longer aliases."""
    if not aliases:
        return None
    for alias, repo in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
        if not alias.strip():
            continue
        pattern = re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(alias)}(?![A-Za-z0-9_.-])", re.IGNORECASE)
        match = pattern.search(text)
        if match:
            return alias, repo, match.start(), match.end()
    return None


def _strip_command_prefix(text: str) -> str:
    return _COMMAND_PREFIX_PATTERN.sub("", text)


def _optional_str(value: JsonValue | None) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


class DiscordRequestParseError(ValueError):
    pass


def __getattr__(name: str) -> Any:
    """Keep gateway symbols available from this legacy module path."""
    if name == "DiscordGatewayEvent":
        from .gateway import DiscordGatewayEvent

        return DiscordGatewayEvent
    if name == "build_gateway_response":
        from .gateway import build_gateway_response

        return build_gateway_response
    if name == "load_router_config":
        from .gateway import load_router_config

        return load_router_config
    raise AttributeError(name)
