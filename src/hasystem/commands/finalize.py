from __future__ import annotations

import argparse
import sys
from pathlib import Path

from hasystem.command_runner import SubprocessCommandRunner
from hasystem.finalize import ActiveLoopNotFoundError, ApprovalRequiredError, FinalizeService
from hasystem.repo_spec import RepoSpec
from hasystem.state_store import StateStore


NO_ACTIVE_LOOP_EXIT_CODE = 3
APPROVAL_REQUIRED_EXIT_CODE = 4


def _finalize_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Push branch, create PR, and mark the active issue done.",
        epilog=(
            "Exit codes: 0 success; 2 argument/config error; "
            f"{NO_ACTIVE_LOOP_EXIT_CODE} no active loop found; "
            f"{APPROVAL_REQUIRED_EXIT_CODE} approval required."
        ),
    )
    parser.add_argument("--repo", required=True, help="owner/repo or https://github.com/owner/repo(.git)")
    parser.add_argument("--local-path", required=True, help="Target repository checkout path")
    parser.add_argument("--state-db", default="state.db", help="Path to SQLite state DB")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without changing GitHub")
    return parser


def _approval_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hermes-finalize approval",
        description="Record or verify active-loop finalization approval intent/status.",
        epilog=f"Exit codes: 0 success; 2 argument/config error; {NO_ACTIVE_LOOP_EXIT_CODE} no active loop found.",
    )
    parser.add_argument("--repo", required=True, help="owner/repo or https://github.com/owner/repo(.git)")
    parser.add_argument("--state-db", default="state.db", help="Path to SQLite state DB")
    parser.add_argument("--intent", help="Approval intent to record, for example: finalize")
    parser.add_argument("--status", choices=("requested", "approved", "rejected"), help="Approval status to record")
    parser.add_argument("--approval-id", help="External approval request or decision identifier")
    return parser


def _print_approval(loop_id: str, intent: str | None, status: str | None, approval_id: str | None) -> None:
    print(f"Loop: {loop_id}")
    print(f"Approval intent: {intent or 'unset'}")
    print(f"Approval status: {status or 'unset'}")
    print(f"Approval id: {approval_id or 'unset'}")


def _approval_main(argv: list[str]) -> int:
    parser = _approval_parser()
    args = parser.parse_args(argv)
    if (args.intent is None) != (args.status is None):
        parser.error("--intent and --status must be provided together when recording approval")
    store = StateStore(Path(args.state_db))
    try:
        if args.intent is not None and args.status is not None:
            loop = FinalizeService.record_approval(
                store=store,
                repo_raw=args.repo,
                intent=args.intent,
                status=args.status,
                approval_id=args.approval_id,
            )
        else:
            repo = RepoSpec.parse(args.repo)
            loop = store.get_active_loop(repo.full_name)
            if loop is None:
                raise ActiveLoopNotFoundError(repo=repo.full_name)
    except ActiveLoopNotFoundError as exc:
        print(f"{exc}. Run hermes-run-loop first or check --state-db.", file=sys.stderr)
        return NO_ACTIVE_LOOP_EXIT_CODE
    _print_approval(loop.loop_id, loop.approval.intent, loop.approval.status, loop.approval.approval_id)
    return 0


def _finalize_main(argv: list[str]) -> int:
    parser = _finalize_parser()
    args = parser.parse_args(argv)
    runner = SubprocessCommandRunner()
    service = FinalizeService(store=StateStore(Path(args.state_db)), runner=runner)
    try:
        result = service.finalize(repo_raw=args.repo, local_path=Path(args.local_path), dry_run=args.dry_run)
    except ActiveLoopNotFoundError as exc:
        print(f"{exc}. Run hermes-run-loop first or check --state-db.", file=sys.stderr)
        return NO_ACTIVE_LOOP_EXIT_CODE
    except ApprovalRequiredError as exc:
        print(f"{exc}. Record approval with: hermes-finalize approval --intent finalize --status approved.", file=sys.stderr)
        return APPROVAL_REQUIRED_EXIT_CODE
    print(f"Loop: {result.loop.loop_id}")
    for command in result.commands:
        print(f"Command: {' '.join(command.args)}")
    print(f"Labels add: {', '.join(result.issue_labels_to_add)}")
    print(f"Labels remove: {', '.join(result.issue_labels_to_remove)}")
    if args.dry_run:
        print("Dry run complete. Push, PR, comments, and labels were not changed.")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "approval":
        return _approval_main(argv[1:])
    return _finalize_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
