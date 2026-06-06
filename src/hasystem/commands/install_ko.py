from __future__ import annotations

import argparse
import sys

from hasystem.installer_ko import build_options, find_option, render_menu, render_plan, run_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="한국어 초보자용 HASYSTEM 설치 도우미",
    )
    parser.add_argument(
        "--choice",
        choices=[option.key for option in build_options()],
        help="실행하거나 표시할 설치 선택지 번호",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="명령을 실행하지 않고 한국어 설치 계획만 출력합니다. 기본값입니다.",
    )
    mode.add_argument(
        "--execute",
        action="store_true",
        help="선택한 설치 명령을 실제로 실행합니다. 먼저 --dry-run으로 확인하세요.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.choice is None:
        print(render_menu(), end="")
        return 0

    try:
        option = find_option(args.choice)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.execute:
        return run_commands(option)

    print(render_plan(option), end="")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
