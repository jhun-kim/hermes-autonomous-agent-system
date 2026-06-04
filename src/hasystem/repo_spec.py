from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final


_OWNER_RE_FRAGMENT: Final = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
_REPO_RE_FRAGMENT: Final = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?"
_SHORT_RE: Final = re.compile(rf"^(?P<owner>{_OWNER_RE_FRAGMENT})/(?P<repo>{_REPO_RE_FRAGMENT})$")
_GITHUB_HTTPS_PREFIX: Final = "https://github.com/"


@dataclass(frozen=True)
class InvalidRepoSpecError(ValueError):
    raw: str

    def __str__(self) -> str:
        return f"Unsupported GitHub repo spec: {self.raw}"


@dataclass(frozen=True)
class RepoSpec:
    owner: str
    name: str

    @classmethod
    def parse(cls, raw: str) -> "RepoSpec":
        cleaned = raw.strip()
        short_match = _SHORT_RE.fullmatch(cleaned)
        if short_match is not None:
            return _build_spec(raw=raw, owner=short_match.group("owner"), name=short_match.group("repo"))
        if cleaned.startswith(_GITHUB_HTTPS_PREFIX):
            path = cleaned[len(_GITHUB_HTTPS_PREFIX) :].rstrip("/")
            repo_path = path[:-4] if path.endswith(".git") else path
            https_match = _SHORT_RE.fullmatch(repo_path)
            if https_match is not None:
                return _build_spec(raw=raw, owner=https_match.group("owner"), name=https_match.group("repo"))
        raise InvalidRepoSpecError(raw=raw)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.full_name}.git"

    def local_path(self, workspace_root: Path) -> Path:
        return workspace_root / self.name


def _build_spec(raw: str, owner: str, name: str) -> RepoSpec:
    if name in {".", ".."} or name.startswith("."):
        raise InvalidRepoSpecError(raw=raw)
    return RepoSpec(owner=owner, name=name)
