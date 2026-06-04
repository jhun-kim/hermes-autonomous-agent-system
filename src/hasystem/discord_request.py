from __future__ import annotations

import json
import re
from dataclasses import dataclass

from .intake import IntakeResult, IntakeService
from .loop_runner import RunLoopResult, RunLoopService

_REPO_PATTERN = re.compile(
    r"(?P<repo>https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?|[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)"
)
_REPO_FIELD_PATTERN = re.compile(r"^\s*(?:repo|repository)\s*[:=]\s*(?P<repo>\S+)\s*$", re.IGNORECASE)
_REQUEST_FIELD_PATTERN = re.compile(r"^\s*(?:request|task|prompt)\s*[:=]\s*(?P<request>.*)$", re.IGNORECASE)


@dataclass(frozen=True)
class DiscordRequest:
    repo_raw: str
    request_text: str


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

    def handle(self, raw_message: str, *, dry_run: bool = False, run_loop: bool = True) -> DiscordAutomationResult:
        request = parse_discord_request(raw_message)
        if dry_run:
            return DiscordAutomationResult(request=request, intake=None, loop=None, dry_run=True)

        intake_result = self.intake.create_task(repo_raw=request.repo_raw, request_text=request.request_text)
        loop_result = self.loop_runner.run_once(repo_raw=request.repo_raw, dry_run=False) if run_loop else None
        return DiscordAutomationResult(request=request, intake=intake_result, loop=loop_result, dry_run=False)


def parse_discord_request(raw_message: str) -> DiscordRequest:
    """Parse a Discord/Gateway task message into repo + request text.

    Supported shapes:
    - JSON: {"repo": "owner/repo", "request": "..."}
    - Multiline: repo: owner/repo\nrequest: ...
    - Free text: /agent owner/repo implement the feature
    - GitHub URL instead of owner/repo.
    """
    raw_message = raw_message.strip()
    if not raw_message:
        raise DiscordRequestParseError("Discord request is empty")

    parsed_json = _parse_json_request(raw_message)
    if parsed_json is not None:
        return parsed_json

    repo_from_field: str | None = None
    request_lines: list[str] = []
    for line in raw_message.splitlines():
        repo_field = _REPO_FIELD_PATTERN.match(line)
        if repo_field:
            repo_from_field = repo_field.group("repo")
            continue
        request_field = _REQUEST_FIELD_PATTERN.match(line)
        if request_field:
            request_lines.append(request_field.group("request"))
            continue
        request_lines.append(line)

    text_without_repo_field = "\n".join(request_lines).strip()
    repo_match = _REPO_PATTERN.search(text_without_repo_field)
    repo_raw = repo_from_field or (repo_match.group("repo") if repo_match else None)
    if repo_raw is None:
        raise DiscordRequestParseError("Could not find a GitHub repo. Use owner/repo or a GitHub URL.")

    if repo_match:
        request_text = (text_without_repo_field[: repo_match.start()] + text_without_repo_field[repo_match.end() :]).strip()
    else:
        request_text = text_without_repo_field
    request_text = _strip_command_prefix(request_text).strip()
    if not request_text:
        raise DiscordRequestParseError("Could not find task text after the repo.")
    return DiscordRequest(repo_raw=repo_raw, request_text=request_text)


def _parse_json_request(raw_message: str) -> DiscordRequest | None:
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
    return DiscordRequest(repo_raw=repo.strip(), request_text=request.strip())


def _strip_command_prefix(text: str) -> str:
    return re.sub(r"^\s*(?:/agent|!agent|@hermes|hermes)\b\s*", "", text, flags=re.IGNORECASE)


class DiscordRequestParseError(ValueError):
    pass
