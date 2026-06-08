import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_markdown_harness_validator_passes() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/validate-harnesses"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Markdown harness validation passed" in result.stdout


def test_issue_loop_harness_is_user_editable_markdown_contract() -> None:
    text = (ROOT / "harnesses" / "issue-loop.md").read_text(encoding="utf-8")

    assert "Run one bounded GitHub issue" in text
    assert "123456789012345682" in text
    assert "twenty additive terminal surfaces" in text
    assert "Run Codex CLI visibly" in text
    assert "On macOS, cmux is the default" in text
    assert "On Windows, do not require cmux" in text
    assert "Do not fabricate" in text
    assert "Follow-up issue URL" in text


def test_platform_setup_documents_mac_cmux_and_windows_terminal_codex() -> None:
    text = (ROOT / "docs" / "PLATFORM_SETUP.md").read_text(encoding="utf-8")

    assert "## macOS: cmux by default" in text
    assert "cmux is missing" in text
    assert "cmux version" in text
    assert "## Windows: terminal Codex fallback" in text
    assert "codex --version" in text


def test_thread_cmux_workspace_is_the_central_mac_doc() -> None:
    text = (ROOT / "docs" / "THREAD_CMUX_WORKSPACE.md").read_text(encoding="utf-8")

    assert "Guild ID: `123456789012345678`" in text
    assert "Parent Channel ID: `123456789012345679`" in text
    assert "Thread ID: `123456789012345682`" in text
    assert "hasystem-thread-123456789012345682" in text
    assert "cmux new-workspace" in text
    assert "cmux new-surface" in text
    assert "codex exec" in text
    assert "twenty additive terminal surfaces" in text
    assert "| 20 | Follow-up issue creator |" in text


def test_cmux_example_uses_twenty_surfaces() -> None:
    text = (ROOT / "examples" / "cmux-20-surface-workspace.md").read_text(encoding="utf-8")

    assert "# cmux 20-Surface Workspace Example" in text
    assert "Surface 01" in text
    assert "Surface 20: follow-up issue creator" in text
