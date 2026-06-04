from __future__ import annotations

import argparse
from pathlib import Path

from hasystem.github_client import GitHubClient
from hasystem.models import LoopState
from hasystem.state_store import StateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Hermes autonomous system loop in dry-run mode.")
    parser.add_argument("--repo", required=True, help="GitHub repository in owner/name format")
    parser.add_argument("--state-db", default="state.db", help="Path to SQLite state DB")
    parser.add_argument("--executor", default="lazycodex", choices=["lazycodex", "omx"])
    parser.add_argument("--dry-run", action="store_true", help="Do not modify GitHub or working tree")
    args = parser.parse_args()

    if not args.dry_run:
        parser.error("Only --dry-run is implemented in this MVP")

    store = StateStore(Path(args.state_db))
    active = store.get_active_loop(args.repo)
    if active is not None:
        print(f"Active loop already exists: {active.loop_id}")
        print(f"Phase: {active.phase}")
        print(f"Issue: #{active.issue.number} {active.issue.title}")
        print(f"Branch: {active.branch}")
        return 0

    client = GitHubClient(args.repo)
    issues = client.list_ready_issues()
    issue = client.select_next_issue(issues)
    if issue is None:
        print("No eligible ai:ready issue found.")
        return 0

    loop = LoopState.start(repo=args.repo, issue=issue, executor=args.executor)
    store.save_loop(loop)

    print(f"Selected issue #{issue.number}: {issue.title}")
    print(f"Created loop id: {loop.loop_id}")
    print(f"Would create branch: {loop.branch}")
    print(f"Executor: {loop.executor}")
    print(f"State DB: {Path(args.state_db).resolve()}")
    print("Dry run complete. No GitHub labels, branches, commits, or PRs were changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
