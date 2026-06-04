from __future__ import annotations

from configparser import ConfigParser
from pathlib import Path


def test_hermes_run_once_console_script_entrypoint_exists() -> None:
    # Given: the project package metadata.
    pyproject = ConfigParser()
    pyproject.read(Path("pyproject.toml"))

    # When: console scripts are inspected.
    scripts = pyproject["project.scripts"]

    # Then: hermes-run-once points at the existing run_once command main function.
    assert scripts["hermes-run-once"].strip('"') == "hasystem.commands.run_once:main"
