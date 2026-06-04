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
