from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .intake import IntakeResult, IntakeService
from .loop_runner import RunLoopResult, RunLoopService

_REPO_PATTERN = re.compile(
    r"(?P<repo>https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
)
_REPO_FIELD_PATTERN = re.compile(r"^\s*(?:repo|repository)\s*[:=]\s*(?P<repo>\S+)\s*$", re.IGNORECASE)
_REQUEST_FIELD_PATTERN = re.compile(r"^\s*(?:request|task|prompt)\s*[:=]\s*(?P<request>.*)$", re.IGNORECASE)
_COMMAND_PREFIX_PATTERN = re.compile(r"^\s*(?:/agent|!agent|@hermes|hermes)\b\s*", re.IGNORECASE)


@dataclass(frozen=True)
class DiscordRequest:
    repo_raw: str
    request_text: str


@dataclass(frozen=True)
class DiscordRequestRouterConfig:
    """Options that let Discord messages feel like natural chat.

    `repo_aliases` maps human-friendly names to GitHub repos. Example:
    `{"hermes-autonomous-agent-system": "jhun-kim/hermes-autonomous-agent-system"}`.

    `channel_default_repos` maps Discord channel/thread IDs to the repo that
    should be assumed when the message does not mention a repo.
    """

    repo_aliases: dict[str, str] = field(default_factory=dict)
    default_repo: str | None = None
    channel_default_repos: dict[str, str] = field(default_factory=dict)

    def default_for_context(self, *, channel_id: str | None = None, thread_id: str | None = None) -> str | None:
        if thread_id and thread_id in self.channel_default_repos:
            return self.channel_default_repos[thread_id]
        if channel_id and channel_id in self.channel_default_repos:
            return self.channel_default_repos[channel_id]
        return self.default_repo

    def resolve_alias(self, repo_or_alias: str) -> str:
        key = repo_or_alias.strip()
        return self.repo_aliases.get(key) or self.repo_aliases.get(key.lower()) or key


@dataclass(frozen=True)
class DiscordAutomationResult:
    request: DiscordRequest
    intake: IntakeResult | None
    loop: RunLoopResult | None
    dry_run: bool


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
    ) -> DiscordAutomationResult:
        request = parse_discord_request(
            raw_message,
            config=self.router_config,
            channel_id=channel_id,
            thread_id=thread_id,
        )
        if dry_run:
            return DiscordAutomationResult(request=request, intake=None, loop=None, dry_run=True)

        intake_result = self.intake.create_task(repo_raw=request.repo_raw, request_text=request.request_text)
        loop_result = self.loop_runner.run_once(repo_raw=request.repo_raw, dry_run=False) if run_loop else None
        return DiscordAutomationResult(request=request, intake=intake_result, loop=loop_result, dry_run=False)


def parse_discord_request(
    raw_message: str,
    *,
    config: DiscordRequestRouterConfig | None = None,
    channel_id: str | None = None,
    thread_id: str | None = None,
) -> DiscordRequest:
    """Parse a Discord/Gateway task message into repo + request text.

    Supported shapes:
    - JSON: {"repo": "owner/repo", "request": "..."}
    - Multiline: repo: owner/repo\nrequest: ...
    - Free text: /agent owner/repo implement the feature
    - GitHub URL instead of owner/repo.
    - Natural chat using aliases/defaults:
      "Hermes, hermes-autonomous-agent-system 계속 개발해줘"
      "이 레포에 자동 finalize 붙여줘" with a channel default repo.
    """
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
            repo_from_field = config.resolve_alias(repo_field.group("repo"))
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
        repo_raw = config.resolve_alias(repo_match.group("repo"))
        request_text = (text_without_repo_field[: repo_match.start()] + text_without_repo_field[repo_match.end() :]).strip()
    elif alias_match:
        alias, owner_repo, start, end = alias_match
        repo_raw = owner_repo
        request_text = (text_without_repo_field[:start] + text_without_repo_field[end:]).strip()
    else:
        repo_raw = config.default_for_context(channel_id=channel_id, thread_id=thread_id)
        request_text = text_without_repo_field

    if repo_raw is None:
        raise DiscordRequestParseError(
            "Could not find a GitHub repo. Mention owner/repo, a GitHub URL, a configured alias, or set a default repo for this channel."
        )

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
    repo = data.get("repo") or data.get("repository")
    request = data.get("request") or data.get("task") or data.get("prompt") or data.get("content") or data.get("text")
    if not isinstance(repo, str) or not repo.strip():
        raise DiscordRequestParseError("JSON Discord request needs a repo field")
    if not isinstance(request, str) or not request.strip():
        raise DiscordRequestParseError("JSON Discord request needs request/task/prompt/content text")
    return DiscordRequest(repo_raw=config.resolve_alias(repo.strip()), request_text=request.strip())


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


class DiscordRequestParseError(ValueError):
    pass
