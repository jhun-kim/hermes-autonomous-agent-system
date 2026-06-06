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
    assert "Run Codex CLI visibly" in text
    assert "Do not fabricate" in text
    assert "Follow-up issue URL" in text
