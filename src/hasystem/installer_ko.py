from __future__ import annotations

from dataclasses import dataclass
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


@dataclass(frozen=True)
class InstallOption:
    """One beginner-facing Korean installation path."""

    key: str
    title: str
    description: str
    commands: tuple[str, ...]
    next_steps: tuple[str, ...]


INTRO_TEXT = """\
HASYSTEM 한국어 설치 도우미
===========================

이 도우미는 코딩을 모르는 사용자가 LLM/에이전트와 함께 설치를 진행할 때
터미널에서 무엇을 선택하고 어떤 명령이 실행되는지 한국어로 보여줍니다.

권장 사용법:
1. GitHub에서 이 저장소를 다운로드하거나 clone 합니다.
2. 터미널에서 저장소 폴더로 이동합니다.
3. 아래 명령을 실행합니다.

   python3 -m hasystem.commands.install_ko --dry-run

4. 화면에 나온 선택지 중 자신의 목적에 맞는 번호를 LLM에게 알려주거나,
   --choice 옵션으로 바로 실행 계획을 확인합니다.
"""


def default_repo_path() -> str:
    return "$HOME/Documents/GitHub/hermes-autonomous-agent-system"


def build_options(repo_path: str | None = None) -> tuple[InstallOption, ...]:
    repo = repo_path or default_repo_path()
    quoted_repo = shlex.quote(repo)
    python = _python_command()
    venv_python = _venv_executable("python")
    venv_pytest = _venv_executable("pytest")
    venv_run_loop = _venv_executable("hermes-run-loop")
    venv_gateway_adapter = _venv_executable("hermes-gateway-adapter")
    return (
        InstallOption(
            key="1",
            title="일반 사용자 설치: 내 컴퓨터에서 HASYSTEM 명령을 쓸 수 있게 설치",
            description="Python 3.10 이상만 있으면 시작할 수 있는 가장 기본 설치입니다.",
            commands=(
                f"{python} --version",
                f"{python} -m venv .venv",
                f"{venv_python} -m pip install --upgrade pip",
                f"{venv_python} -m pip install -e .",
                f"{venv_run_loop} --help",
                f"{venv_gateway_adapter} --help",
            ),
            next_steps=(
                "명령 도움말이 보이면 설치가 끝난 것입니다.",
                "실제 Discord/Hermes 연결 전에는 dry-run으로 라우팅만 확인하세요.",
            ),
        ),
        InstallOption(
            key="2",
            title="개발자 설치: 테스트까지 실행해서 수정 가능한 환경 만들기",
            description="문서를 고치거나 코드를 수정할 사람을 위한 설치입니다.",
            commands=(
                f"{python} --version",
                f"{python} -m venv .venv",
                f"{venv_python} -m pip install --upgrade pip",
                f"{venv_python} -m pip install -e '.[dev]'",
                f"{venv_pytest} -q",
            ),
            next_steps=(
                "pytest가 통과하면 개발 환경이 준비된 것입니다.",
                "수정 전에는 GitHub issue를 먼저 만들고 확인하세요.",
            ),
        ),
        InstallOption(
            key="3",
            title="Hermes Discord gateway dry-run: 실제 변경 없이 연결만 점검",
            description="GitHub issue 생성이나 worker 실행 없이 Discord 이벤트 라우팅만 확인합니다.",
            commands=(
                f"{python} -m venv .venv",
                f"{venv_python} -m pip install -e .",
                "scripts/hermes-gateway-wrapper --dry-run --event-json \"$(cat examples/hermes-gateway-event.dry-run.json)\"",
            ),
            next_steps=(
                "출력 JSON의 status가 dry_run이고 repo가 예상 저장소인지 확인하세요.",
                "dry-run이 통과하기 전에는 --live를 사용하지 마세요.",
            ),
        ),
        InstallOption(
            key="4",
            title="LLM에게 맡기는 설치: 터미널을 열고 단계별로 물어보며 진행",
            description="ChatGPT/Hermes/Codex 같은 LLM에게 붙여넣을 프롬프트와 작업 순서입니다.",
            commands=(
                f"cd {quoted_repo}",
                "python3 -m hasystem.commands.install_ko --choice 1 --dry-run",
                "python3 -m hasystem.commands.install_ko --choice 2 --dry-run",
                "python3 -m hasystem.commands.install_ko --choice 3 --dry-run",
            ),
            next_steps=(
                "LLM에게 README의 'LLM에게 붙여넣는 설치 시작 프롬프트'를 전달하세요.",
                "LLM이 터미널을 열고 OS/Python/Git 상태를 먼저 확인하게 하세요.",
            ),
        ),
    )


def render_menu(options: tuple[InstallOption, ...] | None = None) -> str:
    selected = options or build_options()
    lines = [INTRO_TEXT.rstrip(), "", "설치 선택지:"]
    for option in selected:
        lines.append(f"  {option.key}. {option.title}")
        lines.append(f"     - {option.description}")
    lines.extend(
        [
            "",
            "실행 예시:",
            "  python3 -m hasystem.commands.install_ko --choice 1 --dry-run",
            "  python3 -m hasystem.commands.install_ko --choice 2 --execute",
            "",
            "안전 원칙: 처음에는 반드시 --dry-run으로 명령 목록만 확인하세요.",
        ]
    )
    return "\n".join(lines) + "\n"


def render_plan(option: InstallOption) -> str:
    lines = [f"선택 {option.key}: {option.title}", "", option.description, "", "실행할 명령:"]
    for index, command in enumerate(option.commands, start=1):
        lines.append(f"  {index}. {command}")
    lines.append("")
    lines.append("설치 후 확인:")
    for step in option.next_steps:
        lines.append(f"  - {step}")
    return "\n".join(lines) + "\n"


def find_option(choice: str, options: tuple[InstallOption, ...] | None = None) -> InstallOption:
    selected = options or build_options()
    for option in selected:
        if option.key == choice:
            return option
    valid = ", ".join(option.key for option in selected)
    raise ValueError(f"알 수 없는 선택지입니다: {choice!r}. 가능한 값: {valid}")


def run_commands(option: InstallOption, *, cwd: Path | None = None) -> int:
    """Run commands one by one for an interactive terminal session."""

    workdir = cwd or Path.cwd()
    print(render_plan(option))
    print("이제 위 명령을 순서대로 실행합니다. 실패하면 즉시 중단합니다.\n")
    env = os.environ.copy()
    shell = _shell_for_platform()
    for command in option.commands:
        print(f"$ {command}", flush=True)
        result = subprocess.run(command, cwd=workdir, env=env, shell=True, executable=shell, check=False)
        if result.returncode != 0:
            print(f"\n명령 실패: {command}\n종료 코드: {result.returncode}", file=sys.stderr)
            return result.returncode
    print("\n설치 도우미가 선택한 명령을 모두 실행했습니다.")
    return 0


def _python_command() -> str:
    """Return a beginner-safe Python command that satisfies the package requirement when possible."""

    if sys.version_info >= (3, 10):
        return shlex.quote(sys.executable)
    for candidate in ("python3.12", "python3.11", "python3.10", "python"):
        resolved = shutil.which(candidate)
        if resolved:
            return shlex.quote(resolved)
    return "python3"


def _venv_executable(name: str) -> str:
    if platform.system() == "Windows":
        suffix = ".exe" if name in {"python", "pytest", "hermes-run-loop", "hermes-gateway-adapter"} else ""
        return f".venv\\Scripts\\{name}{suffix}"
    return f".venv/bin/{name}"


def _shell_for_platform() -> str | None:
    if platform.system() == "Windows":
        return None
    return "/bin/bash" if Path("/bin/bash").exists() else None
