"""Running a task's hidden tests and parsing the ``RESULT p/t`` contract."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from .errors import GradeError
from .tasks import Task
from .util import tail

RESULT_RE = re.compile(r"RESULT\s+(\d+)\s*/\s*(\d+)")
TASKLIB = Path(__file__).resolve().parent / "tasklib"

RUNNER_BINARIES = {"python": sys.executable, "node": "node", "bash": "bash"}


@dataclass
class GradeResult:
    passed: int
    total: int
    score: float
    solved: bool
    exit_code: int
    seconds: float
    output: str
    failures: list[str] = field(default_factory=list)
    no_result_line: bool = False
    runner: str = ""
    command: list[str] = field(default_factory=list)

    def to_record(self) -> dict:
        return {
            "passed": self.passed,
            "total": self.total,
            "score": round(self.score, 4),
            "solved": self.solved,
            "exit": self.exit_code,
            "test_seconds": round(self.seconds, 2),
            "failures": self.failures,
            "no_result_line": self.no_result_line,
            "output": self.output,
        }


def runner_available(runner: str) -> bool:
    binary = RUNNER_BINARIES.get(runner, runner)
    return shutil.which(binary) is not None


def grade(task: Task, solution: Path) -> GradeResult:
    """Execute the task's grader against *solution*."""
    test = task.test_path
    if test is None:
        raise GradeError(f"{task.id}: no grader script")
    runner = task.runner
    binary = RUNNER_BINARIES.get(runner, runner)
    if not runner_available(runner):
        raise GradeError(f"{task.id}: runner {runner!r} is not installed ({binary})")

    command = [binary, str(test), str(Path(solution).resolve())]
    env = dict(os.environ)
    paths = [str(TASKLIB), str(task.root.parent.parent if task.root.parent.name == "tasks" else task.root)]
    env["PYTHONPATH"] = os.pathsep.join(paths + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.pop("PYTHONSTARTUP", None)

    started = time.perf_counter()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=task.timeout,
            cwd=str(task.root),
            env=env,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        exit_code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        output = raw + f"\nTIMEOUT after {task.timeout:.0f}s"
        exit_code = 124
    except OSError as exc:
        raise GradeError(f"{task.id}: could not start grader: {exc}") from None
    seconds = time.perf_counter() - started

    matches = RESULT_RE.findall(output)
    no_result = not matches
    if matches:
        passed, total = int(matches[-1][0]), int(matches[-1][1])
    else:
        passed, total = 0, task.checks or 1

    failures = [
        line.strip()[5:].strip()
        for line in output.splitlines()
        if line.strip().startswith("FAIL ")
    ][:30]
    if not failures and not matches:
        failures = [line for line in output.strip().splitlines()[-12:] if line.strip()]

    return GradeResult(
        passed=passed,
        total=total,
        score=(passed / total) if total else 0.0,
        solved=bool(total and passed == total),
        exit_code=exit_code,
        seconds=seconds,
        output=tail(output, 6000),
        failures=failures,
        no_result_line=no_result,
        runner=runner,
        command=command,
    )
