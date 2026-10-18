from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def task_factory(tmp_path: Path):
    """Build a throwaway task directory: task.md, meta.json, tests/, ref/."""

    def build(
        name: str = "t_double",
        *,
        body: str = "Write `double(n)`.",
        test: str | None = None,
        ref: str = "def double(n):\n    return n * 2\n",
        meta: dict | None = None,
        lang: str = "py",
    ) -> Path:
        root = tmp_path / name
        (root / "tests").mkdir(parents=True)
        (root / "ref").mkdir()
        (root / "task.md").write_text(body, encoding="utf-8")
        (root / "meta.json").write_text(
            json.dumps(
                meta
                or {
                    "id": name,
                    "category": "test",
                    "kind": "file",
                    "lang": lang,
                    "max_tokens": 512,
                    "timeout": 30,
                    "checks": 2,
                }
            ),
            encoding="utf-8",
        )
        (root / "ref" / f"solution.{lang}").write_text(ref, encoding="utf-8")
        (root / "tests" / f"test_{name}.py").write_text(
            test
            or (
                "from harness import Checks, solution_arg\n"
                "C = Checks()\n"
                "ns = {}\n"
                "exec(open(solution_arg()).read(), ns)\n"
                "C.eq('double(2)', ns['double'](2), 4)\n"
                "C.eq('double(-3)', ns['double'](-3), -6)\n"
                "C.report()\n"
            ),
            encoding="utf-8",
        )
        return root

    return build


@pytest.fixture()
def record():
    """One results.jsonl record, shaped like the runner's output."""

    def build(task: str = "t01", sample: int = 1, score: float = 1.0, solved: bool = True, **extra):
        total = extra.pop("total", 10)
        passed = extra.pop("passed", int(score * total))
        failures = extra.pop("failures", [])
        data = {
            "record_version": 2,
            "model": "model-a",
            "target": "model-a",
            "served_id": "model-a",
            "suite": "core-v2",
            "suite_digest": "abc123",
            "task": task,
            "title": task,
            "category": "algorithms",
            "kind": "file",
            "lang": "py",
            "sample": sample,
            "when": "2026-01-01T00:00:00+00:00",
            "prompt_chars": 1000,
            "first": {
                "score": score,
                "solved": solved,
                "passed": passed,
                "total": total,
                "completion_tokens": 100,
                "prompt_tokens": 500,
                "total_s": 10.0,
                "ttft_s": 0.5,
                "tok_per_s": 50.0,
                "finish_reason": "stop",
                "source": "fence",
                "no_result_line": False,
                "discarded_calls": [],
                "failures": list(failures),
            },
            "repair": None,
            "final_score": score,
            "final_solved": solved,
            "wall_s": 10.5,
        }
        data.update(extra)
        return data

    return build


@pytest.fixture()
def run_dir(tmp_path: Path):
    """Write a minimal run directory that report.load_run can read."""

    def build(
        label: str = "model-a",
        records: list[dict] | None = None,
        tasks: list[str] | None = None,
        samples: int | None = None,
    ) -> Path:
        root = tmp_path / label
        root.mkdir(parents=True, exist_ok=True)
        records = records or []
        tasks = tasks or sorted({r["task"] for r in records})
        header = {
            "record_version": 2,
            "modelbench": "1.0.0",
            "target": {"name": label, "base_url": "http://127.0.0.1:8080/v1", "model": label},
            "suite": {"id": "core-v2", "version": "2.0", "digest": "abc123", "tasks": tasks},
            "samples": samples or max((r["sample"] for r in records), default=1),
            "repair": True,
            "status": "finished",
        }
        (root / "run.json").write_text(json.dumps(header), encoding="utf-8")
        (root / "results.jsonl").write_text(
            "\n".join(json.dumps(r) for r in records) + ("\n" if records else ""), encoding="utf-8"
        )
        return root

    return build
