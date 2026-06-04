from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Final

from .command_runner import SubprocessCommandRunner
from .models import GitHubIssue


@dataclass(frozen=True)
class GitHubLabel:
    name: str
    color: str
    description: str


DEFAULT_AI_LABELS: Final = (
    GitHubLabel("ai:ready", "0e8a16", "Ready for autonomous AI execution"),
    GitHubLabel("executor:lazycodex", "5319e7", "Use LazyCodex/Codex executor"),
    GitHubLabel("priority:p2", "fbca04", "Default automation priority"),
    GitHubLabel("ai:in-progress", "1d76db", "AI worker is processing this issue"),
    GitHubLabel("ai:blocked", "d93f0b", "AI worker is blocked"),
    GitHubLabel("ai:done", "0e8a16", "AI worker completed the task"),
)

_PRIORITY_RANK = {
    "priority:p0": 0,
    "priority:p1": 1,
    "priority:p2": 2,
}


@dataclass(frozen=True)
class GitHubClient:
    repo: str
    runner: SubprocessCommandRunner = SubprocessCommandRunner()

    def ensure_ai_labels(self) -> None:
        for label in DEFAULT_AI_LABELS:
            self.runner.run(
                [
                    "gh",
                    "label",
                    "create",
                    label.name,
                    "--repo",
                    self.repo,
                    "--color",
                    label.color,
                    "--description",
                    label.description,
                    "--force",
                ]
            )

    def create_issue(self, title: str, body: str, labels: tuple[str, ...]) -> int:
        args = ["gh", "issue", "create", "--repo", self.repo, "--title", title, "--body", body]
        for label in labels:
            args.extend(["--label", label])
        result = self.runner.run(args)
        return _parse_issue_number(result.stdout)

    def list_ready_issues(self) -> list[GitHubIssue]:
        result = self.runner.run(
            [
                "gh",
                "issue",
                "list",
                "--repo",
                self.repo,
                "--label",
                "ai:ready",
                "--state",
                "open",
                "--json",
                "number,title,body,labels",
            ]
        )
        return self.parse_issue_list(result.stdout)

    def mark_in_progress(self, issue_number: int) -> None:
        self.runner.run(
            [
                "gh",
                "issue",
                "edit",
                str(issue_number),
                "--repo",
                self.repo,
                "--add-label",
                "ai:in-progress",
                "--remove-label",
                "ai:ready",
            ]
        )

    def create_pr(self, branch: str, issue: GitHubIssue) -> str:
        result = self.runner.run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                self.repo,
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                f"AI: {issue.title}",
                "--body",
                f"Closes #{issue.number}",
            ]
        )
        return result.stdout.strip()

    def comment_issue(self, issue_number: int, body: str) -> None:
        self.runner.run(["gh", "issue", "comment", str(issue_number), "--repo", self.repo, "--body", body])

    def mark_done(self, issue_number: int) -> None:
        self.runner.run(
            [
                "gh",
                "issue",
                "edit",
                str(issue_number),
                "--repo",
                self.repo,
                "--add-label",
                "ai:done",
                "--remove-label",
                "ai:in-progress",
            ]
        )

    @staticmethod
    def parse_issue_list(raw_json: str) -> list[GitHubIssue]:
        data = json.loads(raw_json)
        issues: list[GitHubIssue] = []
        for item in data:
            labels = [label["name"] for label in item.get("labels", [])]
            issues.append(
                GitHubIssue(
                    number=int(item["number"]),
                    title=item["title"],
                    body=item.get("body") or "",
                    labels=labels,
                )
            )
        return issues

    @staticmethod
    def select_next_issue(issues: list[GitHubIssue]) -> GitHubIssue | None:
        eligible = [issue for issue in issues if _is_eligible(issue)]
        if not eligible:
            return None
        return sorted(eligible, key=_issue_sort_key)[0]


def _is_eligible(issue: GitHubIssue) -> bool:
    labels = set(issue.labels)
    return "ai:ready" in labels and "ai:blocked" not in labels and "ai:in-progress" not in labels


def _issue_sort_key(issue: GitHubIssue) -> tuple[int, int]:
    labels = set(issue.labels)
    priority = min((_PRIORITY_RANK[label] for label in labels if label in _PRIORITY_RANK), default=99)
    return priority, issue.number


def _parse_issue_number(raw: str) -> int:
    marker = "/issues/"
    for line in raw.splitlines():
        if marker in line:
            return int(line.rsplit(marker, maxsplit=1)[1].strip().strip("/"))
    return int(raw.strip().lstrip("#"))
