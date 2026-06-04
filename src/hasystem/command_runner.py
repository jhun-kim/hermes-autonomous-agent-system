from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    stderr: str
    returncode: int


@dataclass(frozen=True)
class CommandSpec:
    args: tuple[str, ...]
    cwd: Path | None = None
    stdin_text: str = ""


class CommandRunnerError(RuntimeError):
    def __init__(self, args: Sequence[str], returncode: int, stderr: str) -> None:
        super().__init__(f"Command failed ({returncode}): {' '.join(args)}\n{stderr}")
        self.args_tuple = tuple(args)
        self.returncode = returncode
        self.stderr = stderr


class SubprocessCommandRunner:
    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        stdin_text: str | None = None,
    ) -> CommandResult:
        result = subprocess.run(
            list(args),
            cwd=cwd,
            input=stdin_text,
            check=False,
            text=True,
            capture_output=True,
        )
        command_result = CommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            returncode=result.returncode,
        )
        if command_result.returncode != 0:
            raise CommandRunnerError(args=args, returncode=command_result.returncode, stderr=command_result.stderr)
        return command_result


@dataclass
class RecordingCommandRunner:
    results: list[CommandResult]
    commands: list[tuple[str, ...]] = field(default_factory=list)
    cwd_values: list[Path | None] = field(default_factory=list)
    stdin_values: list[str | None] = field(default_factory=list)

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        stdin_text: str | None = None,
    ) -> CommandResult:
        self.commands.append(tuple(args))
        self.cwd_values.append(cwd)
        self.stdin_values.append(stdin_text)
        if not self.results:
            return CommandResult(stdout="", stderr="", returncode=0)
        return self.results.pop(0)
