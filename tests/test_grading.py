from __future__ import annotations

from pathlib import Path

from modelbench.grader import grade
from modelbench.tasks import Suite


def _task(tmp_path: Path, factory, **kwargs):
    root = factory(**kwargs)
    suite = Suite.load(tmp_path)
    return next(t for t in suite.tasks if t.root == root)


def test_reference_solution_passes_every_check(tmp_path, task_factory):
    task = _task(tmp_path, task_factory)
    graded = grade(task, task.prepare_ref(tmp_path / "out"))
    assert (graded.passed, graded.total) == (2, 2)
    assert graded.solved
    assert graded.score == 1.0
    assert graded.no_result_line is False


def test_wrong_solution_records_failures(tmp_path, task_factory):
    task = _task(tmp_path, task_factory)
    solution = tmp_path / "bad.py"
    solution.write_text("def double(n):\n    return n\n", encoding="utf-8")
    graded = grade(task, solution)
    assert graded.passed == 0
    assert graded.total == 2
    assert not graded.solved
    assert graded.failures and graded.failures[0].startswith("double(2)")


def test_grader_without_result_line_is_flagged(tmp_path, task_factory):
    task = _task(tmp_path, task_factory, test="print('I forgot the result line')\n")
    solution = tmp_path / "anything.py"
    solution.write_text("x = 1\n", encoding="utf-8")
    graded = grade(task, solution)
    assert graded.no_result_line is True
    assert graded.passed == 0
    assert graded.total == 2  # falls back to meta.checks


def test_grader_crash_does_not_lose_the_run(tmp_path, task_factory):
    task = _task(tmp_path, task_factory, test="raise SystemExit(3)\n")
    solution = tmp_path / "anything.py"
    solution.write_text("x = 1\n", encoding="utf-8")
    graded = grade(task, solution)
    assert graded.no_result_line is True
    assert graded.exit_code == 3


def test_file_solution_is_written_with_the_task_extension(tmp_path, task_factory):
    task = _task(tmp_path, task_factory)
    path, source, written = task.write_solution("```python\ndef double(n):\n    return n * 2\n```\n", tmp_path / "sol")
    assert path.suffix == ".py"
    assert source == "fence"
    assert written == 1
    assert "return n * 2" in path.read_text()


def test_bytecode_caches_and_dotfiles_are_not_task_payload(tmp_path, task_factory):
    """pip byte-compiles installed packages; those .pyc files must be ignored."""
    root = task_factory()
    cache = root / "ref" / "__pycache__"
    cache.mkdir()
    (cache / "solution.cpython-312.pyc").write_bytes(b"\x00\x01")
    (root / ".DS_Store").write_bytes(b"junk")

    task = next(t for t in Suite.load(tmp_path).tasks if t.root == root)
    assert task.problems() == []
    assert task.prepare_ref(tmp_path / "out").name == "solution.py"


def test_repo_solution_materialises_files_and_blocks_escapes(tmp_path, task_factory):
    root = task_factory("t_repo", meta={"id": "t_repo", "kind": "repo", "lang": "py", "checks": 1})
    (root / "files" / "pkg").mkdir(parents=True)
    (root / "files" / "pkg" / "core.py").write_text("VALUE = 0\n", encoding="utf-8")
    suite = Suite.load(tmp_path)
    task = next(t for t in suite.tasks if t.root == root)

    answer = """### FILE: pkg/core.py
```python
VALUE = 1
```
### FILE: ../escaped.py
```python
oops = True
```
"""
    workspace, source, written = task.write_solution(answer, tmp_path / "sol")
    assert source == "markers"
    assert written == 1
    assert (workspace / "pkg" / "core.py").read_text().strip() == "VALUE = 1"
    assert not (tmp_path / "escaped.py").exists()
