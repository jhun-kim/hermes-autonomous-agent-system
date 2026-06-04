from __future__ import annotations

import argparse
from pathlib import Path

from hasystem.command_runner import SubprocessCommandRunner
from hasystem.intake import DEFAULT_WORKSPACE, IntakeService
from hasystem.workspace import Workspace


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an ai:ready GitHub issue from a Discord/Hermes task.")
    parser.add_argument("--repo", required=True, help="owner/repo or https://github.com/owner/repo(.git)")
    parser.add_argument("--request", required=True, help="Task text from Discord")
    parser.add_argument("--workspace", default=str(DEFAULT_WORKSPACE), help="Clone/update workspace root")
    args = parser.parse_args()

    runner = SubprocessCommandRunner()
    service = IntakeService(workspace=Workspace(Path(args.workspace), runner), runner=runner)
    result = service.create_task(repo_raw=args.repo, request_text=args.request)
    print(f"Repo: {result.repo.full_name}")
    print(f"Local path: {result.local_path}")
    print(f"Issue: #{result.issue_number}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
