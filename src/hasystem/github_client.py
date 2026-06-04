from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from .models import GitHubIssue


_PRIORITY_RANK = {
    "priority:p0": 0,
    "priority:p1": 1,
    "priority:p2": 2,
}


@dataclass(frozen=True)
class GitHubClient:
    repo: str

    def list_ready_issues(self) -> list[GitHubIssue]:
        result = subprocess.run(
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
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        return self.parse_issue_list(result.stdout)

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
