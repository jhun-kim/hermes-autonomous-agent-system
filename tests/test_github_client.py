from hasystem.command_runner import CommandResult, RecordingCommandRunner
from hasystem.github_client import DEFAULT_AI_LABELS, GitHubApiAlreadyExistsError, GitHubClient
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


def test_ensure_ai_labels_falls_back_to_rest_create_and_update_when_gh_missing(monkeypatch) -> None:
    # Given: gh is unavailable and REST calls can create/update labels.
    calls = []

    class MissingGhRunner(RecordingCommandRunner):
        def run(self, *args, **kwargs):
            raise FileNotFoundError("gh")

    def fake_api_request(repo: str, method: str, path: str, payload=None):
        calls.append((repo, method, path, payload))
        return {"name": payload["name"]} if payload else {}

    monkeypatch.setattr("hasystem.github_client._github_api_request", fake_api_request)

    # When: required labels are ensured.
    GitHubClient(repo="owner/repo", runner=MissingGhRunner([])).ensure_ai_labels()

    # Then: each label is created through the authenticated REST fallback.
    assert calls[0] == (
        "owner/repo",
        "POST",
        "/labels",
        {
            "name": DEFAULT_AI_LABELS[0].name,
            "color": DEFAULT_AI_LABELS[0].color,
            "description": DEFAULT_AI_LABELS[0].description,
        },
    )
    assert len(calls) == len(DEFAULT_AI_LABELS)


def test_create_issue_falls_back_to_rest_when_gh_missing(monkeypatch) -> None:
    # Given: gh is unavailable and the REST API returns an issue number.
    calls = []

    class MissingGhRunner(RecordingCommandRunner):
        def run(self, *args, **kwargs):
            raise FileNotFoundError("gh")

    def fake_api_request(repo: str, method: str, path: str, payload=None):
        calls.append((repo, method, path, payload))
        return {"number": 42}

    monkeypatch.setattr("hasystem.github_client._github_api_request", fake_api_request)

    # When: an issue is created.
    issue_number = GitHubClient(repo="owner/repo", runner=MissingGhRunner([])).create_issue(
        title="Fix fallback",
        body="Use REST",
        labels=("ai:ready", "priority:p2"),
    )

    # Then: the REST fallback creates the issue with the requested labels.
    assert issue_number == 42
    assert calls == [
        (
            "owner/repo",
            "POST",
            "/issues",
            {"title": "Fix fallback", "body": "Use REST", "labels": ["ai:ready", "priority:p2"]},
        )
    ]


def test_issue_label_transitions_fall_back_to_rest_when_gh_missing(monkeypatch) -> None:
    # Given: gh is unavailable and REST label endpoints are recorded.
    calls = []

    class MissingGhRunner(RecordingCommandRunner):
        def run(self, *args, **kwargs):
            raise FileNotFoundError("gh")

    def fake_api_request(repo: str, method: str, path: str, payload=None):
        calls.append((repo, method, path, payload))
        return {}

    monkeypatch.setattr("hasystem.github_client._github_api_request", fake_api_request)
    client = GitHubClient(repo="owner/repo", runner=MissingGhRunner([]))

    # When: issue labels transition through in-progress and done.
    client.mark_in_progress(5)
    client.mark_done(5)

    # Then: labels are added and removed using REST, with URL-encoded label names.
    assert calls == [
        ("owner/repo", "POST", "/issues/5/labels", {"labels": ["ai:in-progress"]}),
        ("owner/repo", "DELETE", "/issues/5/labels/ai%3Aready", None),
        ("owner/repo", "POST", "/issues/5/labels", {"labels": ["ai:done"]}),
        ("owner/repo", "DELETE", "/issues/5/labels/ai%3Ain-progress", None),
    ]


def test_comment_issue_falls_back_to_rest_when_gh_missing(monkeypatch) -> None:
    # Given: gh is unavailable and comment requests are recorded.
    calls = []

    class MissingGhRunner(RecordingCommandRunner):
        def run(self, *args, **kwargs):
            raise FileNotFoundError("gh")

    def fake_api_request(repo: str, method: str, path: str, payload=None):
        calls.append((repo, method, path, payload))
        return {"id": 1}

    monkeypatch.setattr("hasystem.github_client._github_api_request", fake_api_request)

    # When: a comment is added.
    GitHubClient(repo="owner/repo", runner=MissingGhRunner([])).comment_issue(7, "Completed via REST")

    # Then: the REST fallback posts the issue comment body.
    assert calls == [("owner/repo", "POST", "/issues/7/comments", {"body": "Completed via REST"})]


def test_create_pr_falls_back_to_rest_when_gh_missing(monkeypatch) -> None:
    # Given: gh is unavailable and the REST API returns a PR URL.
    calls = []

    class MissingGhRunner(RecordingCommandRunner):
        def run(self, *args, **kwargs):
            raise FileNotFoundError("gh")

    def fake_api_request(repo: str, method: str, path: str, payload=None):
        calls.append((repo, method, path, payload))
        return {"html_url": "https://github.com/owner/repo/pull/9"}

    monkeypatch.setattr("hasystem.github_client._github_api_request", fake_api_request)
    issue = GitHubIssue(number=5, title="REST PR", body="", labels=[])

    # When: a PR is created.
    url = GitHubClient(repo="owner/repo", runner=MissingGhRunner([])).create_pr("ai/issue-5", issue)

    # Then: the REST fallback creates a PR linked to the issue.
    assert url == "https://github.com/owner/repo/pull/9"
    assert calls == [
        (
            "owner/repo",
            "POST",
            "/pulls",
            {
                "base": "main",
                "head": "ai/issue-5",
                "title": "AI: REST PR",
                "body": "Closes #5",
            },
        )
    ]


def test_ensure_ai_labels_updates_existing_label_when_rest_create_reports_duplicate(monkeypatch) -> None:
    # Given: gh is unavailable and creating the first label reports it already exists.
    calls = []

    class MissingGhRunner(RecordingCommandRunner):
        def run(self, *args, **kwargs):
            raise FileNotFoundError("gh")

    def fake_api_request(repo: str, method: str, path: str, payload=None):
        calls.append((repo, method, path, payload))
        if method == "POST" and path == "/labels" and payload["name"] == DEFAULT_AI_LABELS[0].name:
            raise GitHubApiAlreadyExistsError("exists")
        return {}

    monkeypatch.setattr("hasystem.github_client._github_api_request", fake_api_request)

    # When: required labels are ensured.
    GitHubClient(repo="owner/repo", runner=MissingGhRunner([])).ensure_ai_labels()

    # Then: an existing label is patched with the desired color and description.
    assert calls[1] == (
        "owner/repo",
        "PATCH",
        "/labels/ai%3Aready",
        {"color": DEFAULT_AI_LABELS[0].color, "description": DEFAULT_AI_LABELS[0].description},
    )
