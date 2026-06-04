from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def github_api_json(repo: str, path: str) -> list[dict[str, Any]]:
    payload = github_api_request(repo, "GET", path)
    if not isinstance(payload, list):
        raise GitHubApiError(f"GitHub API returned non-list payload for {path}")
    return payload


def github_api_request(
    repo: str,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    token = github_token_from_git_credentials(repo)
    url = f"https://api.github.com/repos/{repo}{path}"
    request_body = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=request_body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "hermes-autonomous-agent-system",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status == 204:
                return {}
            response_payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 422:
            raise GitHubApiAlreadyExistsError("GitHub API resource already exists") from exc
        raise GitHubApiError(f"GitHub API request failed ({exc.code}) for {method} {path}") from exc
    if isinstance(response_payload, dict):
        return response_payload
    if isinstance(response_payload, list):
        return response_payload
    raise GitHubApiError(f"GitHub API returned unsupported payload for {method} {path}")


def quote_path_segment(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def github_token_from_git_credentials(repo: str) -> str:
    credential_input = f"protocol=https\nhost=github.com\npath={repo}.git\n\n"
    try:
        result = subprocess.run(
            ["git", "credential", "fill"],
            input=credential_input,
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise GitHubApiError("Cannot use GitHub API fallback because git is not installed") from exc
    if result.returncode != 0:
        raise GitHubApiError("Cannot use GitHub API fallback because git credential lookup failed")
    for line in result.stdout.splitlines():
        if line.startswith("password="):
            token = line.split("=", 1)[1].strip()
            if token:
                return token
    raise GitHubApiError("Cannot use GitHub API fallback because no GitHub token was found in git credentials")


class GitHubApiError(RuntimeError):
    pass


class GitHubApiAlreadyExistsError(GitHubApiError):
    pass
