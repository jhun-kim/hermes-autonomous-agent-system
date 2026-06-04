from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.github_client import GitHubClient
from hasystem.models import GitHubIssue


def test_select_next_issue_prefers_ready_unblocked_high_priority_issue() -> None:
    issues = [
        GitHubIssue(number=10, title="Blocked", labels=["ai:ready", "ai:blocked", "priority:p0"]),
        GitHubIssue(number=11, title="Already running", labels=["ai:ready", "ai:in-progress", "priority:p0"]),
        GitHubIssue(number=12, title="Low priority", labels=["ai:ready", "priority:p2"]),
        GitHubIssue(number=13, title="High priority", labels=["ai:ready", "priority:p0", "executor:lazycodex"]),
    ]

    selected = GitHubClient.select_next_issue(issues)

    assert selected == issues[3]


def test_parse_gh_issue_json_converts_labels_to_names() -> None:
    raw = """
    [
      {
        "number": 7,
        "title": "Add docs",
        "body": "Write the docs",
        "labels": [{"name": "ai:ready"}, {"name": "executor:omx"}]
      }
    ]
    """

    issues = GitHubClient.parse_issue_list(raw)

    assert issues == [
        GitHubIssue(number=7, title="Add docs", body="Write the docs", labels=["ai:ready", "executor:omx"])
    ]


def test_parse_rest_issue_json_ignores_pull_requests() -> None:
    data = [
        {
            "number": 7,
            "title": "Add docs",
            "body": "Write the docs",
            "labels": [{"name": "ai:ready"}, {"name": "executor:omx"}],
        },
        {
            "number": 8,
            "title": "A PR from issues API",
            "body": "Ignore me",
            "labels": [{"name": "ai:ready"}],
            "pull_request": {"url": "https://api.github.com/repos/owner/repo/pulls/8"},
        },
    ]

    issues = GitHubClient.parse_rest_issue_list(data)

    assert issues == [
        GitHubIssue(number=7, title="Add docs", body="Write the docs", labels=["ai:ready", "executor:omx"])
    ]


def test_list_ready_issues_falls_back_to_rest_api_when_gh_is_missing(monkeypatch) -> None:
    class MissingGhRunner(RecordingCommandRunner):
        def run(self, *args, **kwargs):
            raise FileNotFoundError("gh")

    def fake_api_json(repo: str, path: str):
        assert repo == "owner/repo"
        assert path == "/issues?state=open&labels=ai:ready&per_page=100"
        return [
            {
                "number": 9,
                "title": "Verify dry-run fallback",
                "body": "Use GitHub REST when gh is missing",
                "labels": [{"name": "ai:ready"}, {"name": "priority:p2"}],
            }
        ]

    monkeypatch.setattr("hasystem.github_client._github_api_json", fake_api_json)

    issues = GitHubClient(repo="owner/repo", runner=MissingGhRunner([])).list_ready_issues()

    assert issues == [
        GitHubIssue(
            number=9,
            title="Verify dry-run fallback",
            body="Use GitHub REST when gh is missing",
            labels=["ai:ready", "priority:p2"],
        )
    ]
