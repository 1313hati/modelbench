from __future__ import annotations

from modelbench.tasks import PACKAGED_SUITES, available_suites, payload_files, resolve_suite


def test_packaged_suites_are_structurally_valid():
    suites = available_suites()
    assert {s.id for s in suites} == {"core-v1", "core-v2", "work-v1"}
    for suite in suites:
        assert suite.problems() == [], suite.problems()
        assert suite.tasks
        assert suite.total_checks > 0


def test_every_task_keeps_its_grader_in_tests_dir():
    for task_dir in PACKAGED_SUITES.glob("*/tasks/*"):
        assert (task_dir / "tests").is_dir(), f"{task_dir.name} has no tests/ directory"
        assert payload_files(task_dir / "tests"), f"{task_dir.name} has an empty tests/ directory"


def test_task_metadata_matches_the_directories():
    for suite in available_suites():
        for task in suite.tasks:
            assert task.meta.get("title"), f"{task.id}: missing title"
            assert task.checks > 0, f"{task.id}: missing checks"
            assert task.max_tokens >= 512
            assert task.category


def test_resolution_by_id_and_by_path(tmp_path):
    assert resolve_suite("core-v1").id == "core-v1"
    assert resolve_suite(str(PACKAGED_SUITES / "core-v2")).id == "core-v2"
