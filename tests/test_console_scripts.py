from __future__ import annotations

from configparser import ConfigParser
import os
from pathlib import Path
import subprocess
import sys
from typing import NoReturn

import pytest


def test_hermes_run_once_console_script_entrypoint_exists() -> None:
    # Given: the project package metadata.
    pyproject = ConfigParser()
    pyproject.read(Path("pyproject.toml"))

    # When: console scripts are inspected.
    scripts = pyproject["project.scripts"]

    # Then: hermes-run-once points at the existing run_once command main function.
    assert scripts["hermes-run-once"].strip('"') == "hasystem.commands.run_once:main"


def test_hermes_finalize_console_script_entrypoint_exists() -> None:
    # Given: the project package metadata.
    pyproject = ConfigParser()
    pyproject.read(Path("pyproject.toml"))

    # When: console scripts are inspected.
    scripts = pyproject["project.scripts"]

    # Then: hermes-finalize points at the finalize command main function.
    assert scripts["hermes-finalize"].strip('"') == "hasystem.commands.finalize:main"


def test_finalize_module_reports_missing_active_loop_with_documented_exit_code(tmp_path: Path) -> None:
    # Given: an empty Hermes state database and the module CLI entrypoint.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").resolve())
    state_db = tmp_path / "state.db"

    # When: finalization is requested without an active loop.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasystem.commands.finalize",
            "--repo",
            "owner/repo",
            "--local-path",
            str(tmp_path / "repo"),
            "--state-db",
            str(state_db),
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: the CLI prints an actionable message and exits with the documented missing-loop code.
    assert result.returncode == 3
    assert "No active loop found for owner/repo" in result.stderr
    assert "hermes-run-loop" in result.stderr


def test_finalize_module_help_documents_missing_active_loop_exit_code() -> None:
    # Given: the finalize module CLI help surface.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").resolve())

    # When: help is requested.
    result = subprocess.run(
        [sys.executable, "-m", "hasystem.commands.finalize", "--help"],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: the documented exit codes include the missing-active-loop code.
    assert result.returncode == 0
    assert "3 no active loop found" in result.stdout


def test_finalize_main_surfaces_unexpected_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    # Given: the finalize command encounters an unexpected service failure.
    from hasystem.commands import finalize as finalize_command

    def fail_finalize(self, repo_raw: str, local_path: Path, dry_run: bool) -> NoReturn:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(finalize_command.FinalizeService, "finalize", fail_finalize)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "hermes-finalize",
            "--repo",
            "owner/repo",
            "--local-path",
            "/tmp/repo",
            "--state-db",
            "/tmp/hermes-unexpected-error-state.db",
        ],
    )

    # When / Then: the unexpected failure is not converted into the missing-loop exit code.
    try:
        with pytest.raises(RuntimeError, match="database unavailable"):
            finalize_command.main()
    finally:
        Path("/tmp/hermes-unexpected-error-state.db").unlink(missing_ok=True)


def test_finalize_module_dry_run_prints_planned_label_transitions(tmp_path: Path) -> None:
    # Given: an unapproved active loop exists in the configured state database.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").resolve())
    state_db = tmp_path / "state.db"
    setup = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path;"
                "from hasystem.models import GitHubIssue, LoopState;"
                "from hasystem.state_store import StateStore;"
                f"store=StateStore(Path({str(state_db)!r}));"
                "store.save_loop(LoopState.start(repo='owner/repo', issue=GitHubIssue(number=11, title='Gate'), executor='omx'))"
            ),
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert setup.returncode == 0, setup.stderr

    # When: dry-run finalization is requested without approval.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasystem.commands.finalize",
            "--repo",
            "owner/repo",
            "--local-path",
            str(tmp_path / "repo"),
            "--state-db",
            str(state_db),
            "--dry-run",
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: dry-run prints git, PR, and issue label transitions without requiring approval.
    assert result.returncode == 0, result.stderr
    assert "Command: git push" in result.stdout
    assert "Command: gh pr create" in result.stdout
    assert "Labels add: ai:done" in result.stdout
    assert "Labels remove: ai:in-progress" in result.stdout


def test_finalize_module_refuses_unapproved_non_dry_run_with_documented_exit_code(tmp_path: Path) -> None:
    # Given: an active loop exists but approval has not been granted.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").resolve())
    state_db = tmp_path / "state.db"
    setup = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path;"
                "from hasystem.models import GitHubIssue, LoopState;"
                "from hasystem.state_store import StateStore;"
                f"store=StateStore(Path({str(state_db)!r}));"
                "store.save_loop(LoopState.start(repo='owner/repo', issue=GitHubIssue(number=11, title='Gate'), executor='omx'))"
            ),
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert setup.returncode == 0, setup.stderr

    # When: non-dry-run finalization is requested.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasystem.commands.finalize",
            "--repo",
            "owner/repo",
            "--local-path",
            str(tmp_path / "repo"),
            "--state-db",
            str(state_db),
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: the CLI refuses before attempting git/GitHub mutation.
    assert result.returncode == 4
    assert "requires approved approval state" in result.stderr


def test_finalize_module_records_and_verifies_approval_status(tmp_path: Path) -> None:
    # Given: an active loop exists in the configured state database.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").resolve())
    state_db = tmp_path / "state.db"
    setup = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path;"
                "from hasystem.models import GitHubIssue, LoopState;"
                "from hasystem.state_store import StateStore;"
                f"store=StateStore(Path({str(state_db)!r}));"
                "store.save_loop(LoopState.start(repo='owner/repo', issue=GitHubIssue(number=11, title='Gate'), executor='omx'))"
            ),
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert setup.returncode == 0, setup.stderr

    # When: approval intent/status is recorded through the finalize CLI approval path.
    record = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasystem.commands.finalize",
            "approval",
            "--repo",
            "owner/repo",
            "--state-db",
            str(state_db),
            "--intent",
            "finalize",
            "--status",
            "approved",
            "--approval-id",
            "approval-789",
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    verify = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasystem.commands.finalize",
            "approval",
            "--repo",
            "owner/repo",
            "--state-db",
            str(state_db),
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: both calls expose the active loop's approval intent/status.
    assert record.returncode == 0, record.stderr
    assert verify.returncode == 0, verify.stderr
    assert "Approval intent: finalize" in record.stdout
    assert "Approval status: approved" in verify.stdout
    assert "Approval id: approval-789" in verify.stdout
