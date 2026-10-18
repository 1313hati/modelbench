"""Explain one record: what the model wrote, what failed, how it differs.

A report answers "which task lost points". This answers "why", which is the
question you actually have at that moment:

    modelbench inspect runs/a --task t03_json_parser --sample 2

With no ``--task`` it lists the failing records of a run, so you can triage.
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Sequence

from .errors import ModelBenchError
from .report import Run, load_run
from .tasks import Suite, Task, payload_files, resolve_suite


def record_for(run: Run, task: str, sample: int | None = None) -> dict:
    matches = [r for r in run.records if r.get("task") == task]
    if sample is not None:
        matches = [r for r in matches if int(r.get("sample") or 1) == sample]
    if not matches:
        known = ", ".join(sorted({str(r.get("task")) for r in run.records}))[:400]
        raise ModelBenchError(f"{run.path}: no record for task {task!r}" + (f" sample {sample}" if sample else "") + f". Tasks present: {known}")
    matches.sort(key=lambda r: (int(r.get("sample") or 1),))
    return matches[0]


def failing_records(run: Run) -> list[dict]:
    """Records that lost at least one assertion, worst first."""
    bad = [
        r
        for r in run.records
        if float((r.get("first") or {}).get("score") or 0.0) < 1.0 or r.get("error")
    ]
    return sorted(
        bad,
        key=lambda r: (
            float((r.get("first") or {}).get("score") or 0.0),
            str(r.get("task")),
            int(r.get("sample") or 1),
        ),
    )


def _sol_dir(run: Run, record: dict) -> Path:
    return run.path / f"s{int(record.get('sample') or 1)}" / "sol"


def _files_under(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and not p.name.endswith((".pyc", ".pyo"))
    )


def _bundle(files: Sequence[Path], base: Path) -> str:
    """All written files as one comparable text, headed by their relative path."""
    if not files:
        return ""
    if len(files) == 1:
        return files[0].read_text(encoding="utf-8", errors="replace")
    parts = []
    for path in files:
        rel = path.relative_to(base).as_posix() if base in path.parents or path.parent == base else path.name
        parts.append(f"### FILE: {rel}\n{path.read_text(encoding='utf-8', errors='replace').rstrip()}\n")
    return "\n".join(parts)


def answer_text(run: Run, record: dict) -> tuple[str, str]:
    """(text, source) for what the model actually wrote, plus where it came from."""
    sol_dir = _sol_dir(run, record)
    files = [p for p in _files_under(sol_dir) if p.parent == sol_dir or "files" in p.parts]
    return _bundle(files, sol_dir), str(sol_dir)


def ref_text(run: Run, task_id: str, suite_spec: str | None) -> tuple[str | None, str]:
    """Reference solution for a task, if the suite can still be loaded."""
    spec = suite_spec or run.suite_id
    try:
        suite: Suite = resolve_suite(spec)
        task: Task = suite.task(task_id)
    except Exception as exc:  # suite moved, custom path, deleted task...
        return None, f"reference unavailable ({type(exc).__name__}: {exc})"
    files = payload_files(task.ref_dir)
    if not files:
        return None, "reference unavailable (no solution in the task)"
    return _bundle(files, task.ref_dir), str(task.ref_dir)


def unified(expected: str, got: str, expected_name: str = "reference", got_name: str = "model", context: int = 3) -> str:
    if expected.strip() == got.strip():
        return ""
    diff = difflib.unified_diff(
        expected.splitlines(),
        got.splitlines(),
        fromfile=expected_name,
        tofile=got_name,
        lineterm="",
        n=max(0, context),
    )
    return "\n".join(diff)


def _head(text: str, lines: int) -> tuple[str, int]:
    rows = text.splitlines()
    if len(rows) <= lines:
        return text, 0
    return "\n".join(rows[:lines]), len(rows) - lines


def _fmt_record_header(run: Run, record: dict) -> list[str]:
    first = record.get("first") or {}
    lines = [
        f"{record.get('task')}  sample {record.get('sample')}  [{(record.get('title') or '').strip()}]",
        f"run      {run.path}  ({run.label}, suite {run.suite_id})",
        f"kind     {record.get('kind') or '?'} / {record.get('lang') or '?'}   category {record.get('category') or '?'}",
        f"seed     {record.get('seed')}   served id {record.get('served_id') or '?'}",
        f"score    {first.get('passed', 0)}/{first.get('total', 0)} first"
        + (f"   final {record.get('final_score', 0) * 100:.1f}% ({'solved' if record.get('final_solved') else 'not solved'})"
           if record.get("repair") else ""),
        f"call     finish={first.get('finish_reason') or '?'}  tokens={first.get('completion_tokens') or 0}  "
        f"ttft={first.get('ttft_s') or 0:.2f}s  total={first.get('total_s') or 0:.2f}s  "
        f"source={first.get('source') or '?'}",
    ]
    if record.get("error"):
        lines.append(f"error    {record['error']}")
    return lines


def render_record(
    run: Run,
    record: dict,
    *,
    suite_spec: str | None = None,
    context: int = 3,
    full: bool = False,
    max_lines: int = 120,
) -> str:
    first = record.get("first") or {}
    lines = _fmt_record_header(run, record)

    for label, attempt in (("first", first), ("repair", record.get("repair"))):
        if not attempt:
            continue
        failures = attempt.get("failures") or []
        if attempt.get("no_result_line"):
            # The grader died before RESULT: a traceback is not an assertion,
            # and calling it one would send you looking for the wrong bug.
            lines += ["", f"{label} attempt — the grader never reached a RESULT line; output:"]
            lines += [f"  {row}" for row in (failures or ["<no output captured>"])[:12]]
        elif failures:
            lines += ["", f"{label} attempt — failing assertions:"]
            lines += [f"  {row}" for row in failures]
        elif not attempt.get("solved"):
            lines += ["", f"{label} attempt — scored below full marks but no assertion text was recorded"]

    written, where = answer_text(run, record)
    if written.strip():
        show, omitted = (written, 0) if full else _head(written, max_lines)
        lines += ["", f"what the model wrote ({where}):", "-" * 68, show.rstrip()]
        if omitted:
            lines.append(f"... {omitted} more line(s); pass --full to see everything")
        lines.append("-" * 68)
    else:
        lines += ["", f"no saved solution under {where} (the answer may have been empty)"]

    reference, ref_where = ref_text(run, str(record.get("task")), suite_spec)
    if reference is None:
        lines += ["", f"diff: {ref_where}"]
    else:
        diff = unified(reference, written, "reference", "model", context=context)
        lines += ["", f"diff against the reference ({ref_where}):", "-" * 68]
        lines.append(diff.rstrip() if diff else "identical to the reference")
        if not diff:
            lines[-1] = "identical to the reference — the loss is behavioural (timing, crashes), not textual"
        lines.append("-" * 68)
    return "\n".join(lines)


def render_index(run: Run) -> str:
    """Triage view: every record that lost points, worst first."""
    bad = failing_records(run)
    total = len(run.records)
    lines = [
        f"{run.label}  {run.path}",
        f"{total - len(bad)} of {_count(total, 'record')} lost nothing"
        + (f"; {len(bad)} to look at" if bad else "."),
        "",
    ]
    if not bad:
        return "\n".join(lines).rstrip()
    lines += ["task                     s  score    first failing assertion", "-" * 92]
    for record in bad[:40]:
        first = record.get("first") or {}
        failure = (first.get("failures") or [""])[0]
        if first.get("no_result_line"):
            tail = (first.get("failures") or [""])[-1].strip()
            failure = f"<no RESULT line>{': ' + tail[:44] if tail else ''}"
        if not failure and record.get("error"):
            failure = f"<run error: {record['error']}>"
        lines.append(
            f"{str(record.get('task'))[:24]:<24} {int(record.get('sample') or 1):>2}  "
            f"{first.get('passed', 0):>3}/{first.get('total', 0):<3} "
            f"{failure[:52]}"
        )
    if len(bad) > 40:
        lines.append(f"... and {len(bad) - 40} more")
    lines += [
        "",
        "modelbench inspect " + str(run.path) + f" --task {bad[0].get('task')} --sample {int(bad[0].get('sample') or 1)}",
    ]
    return "\n".join(lines)


def _count(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def load(path: str | Path) -> Run:
    return load_run(path)
