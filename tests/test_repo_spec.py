from pathlib import Path

import pytest

from hasystem.repo_spec import InvalidRepoSpecError, RepoSpec


def test_repo_spec_parses_owner_repo_when_short_form() -> None:
    # Given: a GitHub owner/repo short spec.
    raw = "openai/codex"

    # When: the repo spec is parsed.
    spec = RepoSpec.parse(raw)

    # Then: the typed repo identity exposes stable derived values.
    assert spec.owner == "openai"
    assert spec.name == "codex"
    assert spec.full_name == "openai/codex"
    assert spec.clone_url == "https://github.com/openai/codex.git"


def test_repo_spec_parses_https_url_with_optional_git_suffix(tmp_path: Path) -> None:
    # Given: a GitHub HTTPS URL with a .git suffix.
    raw = "https://github.com/chai/hermes-autonomous-agent-system.git"

    # When: the repo spec is parsed.
    spec = RepoSpec.parse(raw)

    # Then: it maps to the default workspace directory shape.
    assert spec.full_name == "chai/hermes-autonomous-agent-system"
    assert spec.local_path(tmp_path) == tmp_path / "hermes-autonomous-agent-system"


def test_repo_spec_rejects_non_github_specs() -> None:
    # Given: a repo spec outside the supported GitHub forms.
    raw = "git@example.com:owner/repo.git"

    # When / Then: parsing raises a typed error.
    with pytest.raises(InvalidRepoSpecError):
        RepoSpec.parse(raw)


@pytest.mark.parametrize("raw", ["owner/.", "owner/..", "../repo", "owner/repo/extra"])
def test_repo_spec_rejects_path_traversal_names(raw: str) -> None:
    # Given: a repo spec that could escape or confuse the workspace path.
    # When / Then: parsing rejects it at the trust boundary.
    with pytest.raises(InvalidRepoSpecError):
        RepoSpec.parse(raw)
