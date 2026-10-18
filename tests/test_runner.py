from __future__ import annotations

import json
from pathlib import Path

import pytest

from modelbench.errors import ModelBenchError
from modelbench.runner import resume_pairs, sample_seed


def write(path: Path, records: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def record(task: str = "a", sample: int = 1, target: str = "local", digest: str = "abc") -> dict:
    return {"task": task, "sample": sample, "target": target, "suite_digest": digest}


def test_resume_returns_pairs_recorded_by_the_same_run(tmp_path):
    path = write(tmp_path / "results.jsonl", [record("a", 1), record("b", 2)])
    assert resume_pairs(path, "abc", "local") == {("a", 1), ("b", 2)}


def test_resume_missing_file_is_not_an_error(tmp_path):
    assert resume_pairs(tmp_path / "nope.jsonl", "abc", "local") == set()


def test_resume_refuses_records_from_another_target(tmp_path):
    path = write(tmp_path / "results.jsonl", [record("a", 1), record("b", 1, target="other")])
    with pytest.raises(ModelBenchError) as excinfo:
        resume_pairs(path, "abc", "local")
    assert "do not belong to this run" in str(excinfo.value)
    assert "target 'other'" in str(excinfo.value)


def test_resume_refuses_records_from_a_changed_suite(tmp_path):
    path = write(tmp_path / "results.jsonl", [record("a", 1, digest="old")])
    with pytest.raises(ModelBenchError) as excinfo:
        resume_pairs(path, "new", "local")
    assert "suite digest changed" in str(excinfo.value)


def test_resume_tolerates_legacy_records_without_provenance(tmp_path):
    legacy = {"task": "a", "sample": 1}
    path = write(tmp_path / "results.jsonl", [legacy])
    assert resume_pairs(path, "abc", "local") == {("a", 1)}


def test_sample_seed_offsets_each_sample():
    assert sample_seed(42, 1) == 42
    assert sample_seed(42, 2) == 43
    assert sample_seed(0, 3) == 2
    assert sample_seed(None, 2) is None
