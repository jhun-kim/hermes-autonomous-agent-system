from __future__ import annotations

from configparser import ConfigParser
import json
import os
from pathlib import Path
import shutil
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


def test_hermes_gateway_adapter_console_script_entrypoint_exists() -> None:
    # Given: the project package metadata.
    pyproject = ConfigParser()
    pyproject.read(Path("pyproject.toml"))

    # When: console scripts are inspected.
    scripts = pyproject["project.scripts"]

    # Then: hermes-gateway-adapter points at the stable gateway adapter command.
    assert scripts["hermes-gateway-adapter"].strip('"') == "hasystem.commands.gateway_adapter:main"


def test_gateway_adapter_module_accepts_event_json_and_prints_structured_dry_run(tmp_path: Path) -> None:
    # Given: a Discord/Gateway event JSON payload and isolated state/workspace paths.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").resolve())
    event = (
        '{"platform":"discord","channel_id":"channel-1",'
        '"content":"Hermes, hasystem implement gateway adapter","dry_run":true}'
    )

    # When: the adapter command handles the event in dry-run mode.
    state_db = tmp_path / "state.db"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasystem.commands.gateway_adapter",
            "--event-json",
            event,
            "--repo-alias",
            "hasystem=owner/repo",
            "--state-db",
            str(state_db),
            "--workspace",
            str(tmp_path / "workspace"),
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: stdout is structured JSON and no stderr failure is reported.
    assert result.returncode == 0, result.stderr
    payload = __import__("json").loads(result.stdout)
    assert payload["status"] == "dry_run"
    assert payload["repo"] == "owner/repo"
    assert payload["parsed_request"]["request_text"] == "implement gateway adapter"
    assert not state_db.exists()


def test_packaged_gateway_adapter_console_script_dry_run_does_not_mutate_paths(tmp_path: Path) -> None:
    # Given: the current project is installed into an isolated virtual environment.
    venv_source_python = _packaging_test_python()
    venv_path = tmp_path / "venv"
    package_source = tmp_path / "package-source"
    package_source.mkdir()
    shutil.copy2(Path("pyproject.toml"), package_source / "pyproject.toml")
    shutil.copytree(Path("src"), package_source / "src")
    create_venv = subprocess.run(
        [venv_source_python, "-m", "venv", str(venv_path)],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert create_venv.returncode == 0, create_venv.stderr

    python_bin = venv_path / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    script_bin = venv_path / ("Scripts/hermes-gateway-adapter.exe" if os.name == "nt" else "bin/hermes-gateway-adapter")
    install_env = os.environ.copy()
    install_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    install_env["PIP_NO_CACHE_DIR"] = "1"
    install = subprocess.run(
        [
            str(python_bin),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-build-isolation",
            ".",
        ],
        cwd=package_source,
        env=install_env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert install.returncode == 0, install.stderr

    state_db = tmp_path / "state.db"
    workspace = tmp_path / "workspace"
    event = json.dumps(
        {
            "platform": "discord",
            "channel_id": "channel-1",
            "content": "Hermes, hasystem implement packaged gateway adapter smoke test",
            "dry_run": True,
        }
    )

    # When: the installed console script handles the event in dry-run mode.
    result = subprocess.run(
        [
            str(script_bin),
            "--event-json",
            event,
            "--repo-alias",
            "hasystem=owner/repo",
            "--state-db",
            str(state_db),
            "--workspace",
            str(workspace),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: the packaged executable prints structured dry-run JSON without mutating state or workspace paths.
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "dry_run"
    assert payload["repo"] == "owner/repo"
    assert payload["parsed_request"]["request_text"] == "implement packaged gateway adapter smoke test"
    assert payload["intake"] is None
    assert payload["loop"] is None
    assert not state_db.exists()
    assert not workspace.exists()


def _packaging_test_python() -> str:
    if sys.version_info >= (3, 10):
        return sys.executable
    python_311 = shutil.which("python3.11")
    if python_311 is None:
        pytest.skip("packaged console-script smoke test requires Python >=3.10 or python3.11 on PATH")
    return python_311


def test_gateway_adapter_non_dry_run_requires_allow_repo_before_state_write(tmp_path: Path) -> None:
    # Given: a non-dry-run gateway event with no allow-list.
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path("src").resolve())
    state_db = tmp_path / "state.db"

    # When: the adapter is invoked without --allow-repo or --allow-any-repo.
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "hasystem.commands.gateway_adapter",
            "--event-json",
            '{"platform":"discord","content":"Hermes, owner/repo implement gateway adapter"}',
            "--state-db",
            str(state_db),
            "--workspace",
            str(tmp_path / "workspace"),
        ],
        cwd=Path.cwd(),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    # Then: the adapter fails closed before initializing state or workspace mutations.
    assert result.returncode == 2
    payload = __import__("json").loads(result.stderr)
    assert payload["status"] == "error"
    assert "requires allow_repos" in payload["error"]
    assert not state_db.exists()


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
