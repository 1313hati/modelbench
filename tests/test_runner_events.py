"""One real run, end to end, against the mock server, checked through its events.

This is the test that says the dashboard is showing the truth: the event file is
produced by the same code path that writes ``results.jsonl``, so the two cannot
drift into disagreeing about how many attempts happened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modelbench import RECORD_VERSION
from modelbench.config import Target
from modelbench.events import read_events
from modelbench.mockserver import start_mock
from modelbench.runner import RunPlan, Runner
from modelbench.tasks import Suite


def plan_for(tmp_path: Path, suite_dir: Path, base_url: str, **kwargs) -> RunPlan:
    suite = Suite.load(suite_dir)
    target = Target(name="mock", base_url=base_url, model="mock-model", context=8192)
    return RunPlan(
        suite=suite,
        target=target,
        out_dir=tmp_path / "run",
        samples=kwargs.pop("samples", 1),
        repair=kwargs.pop("repair", False),
        warmup=kwargs.pop("warmup", False),
        quiet=True,
        **kwargs,
    )


@pytest.fixture()
def one_task(tmp_path):
    def build(name: str = "t_double") -> Path:
        root = tmp_path / "suite"
        task = root / name
        (task / "tests").mkdir(parents=True)
        (task / "ref").mkdir()
        (task / "task.md").write_text("Write `double(n)`.", encoding="utf-8")
        (task / "meta.json").write_text(
            json.dumps(
                {
                    "id": name,
                    "category": "test",
                    "kind": "file",
                    "lang": "py",
                    "max_tokens": 512,
                    "timeout": 30,
                    "checks": 2,
                }
            ),
            encoding="utf-8",
        )
        (task / "ref" / "solution.py").write_text("def double(n):\n    return n * 2\n", encoding="utf-8")
        (task / "tests" / "test_double.py").write_text(
            "from harness import Checks, solution_arg\n"
            "C = Checks()\n"
            "ns = {}\n"
            "exec(open(solution_arg()).read(), ns)\n"
            "C.eq('double(2)', ns['double'](2), 4)\n"
            "C.eq('double(-3)', ns['double'](-3), -6)\n"
            "C.report()\n",
            encoding="utf-8",
        )
        return root

    return build


def events_of(path: Path) -> list[dict]:
    return read_events(path / "events.jsonl")


def kinds(events: list[dict]) -> list[str]:
    return [event["kind"] for event in events]


# --------------------------------------------------------------------------- #
# the happy path
# --------------------------------------------------------------------------- #
def test_a_run_writes_events_between_started_and_finished(tmp_path, one_task):
    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), delay=0.0) as mock:
        outcome = Runner(plan_for(tmp_path, suite_dir, mock.base_url)).execute()

    events = events_of(outcome.out_dir)
    assert kinds(events)[0] == "run_started"
    assert kinds(events)[-1] == "run_finished"
    assert len(outcome.records) == 1


def test_event_sequence_numbers_are_dense(tmp_path, one_task):
    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), delay=0.0) as mock:
        outcome = Runner(plan_for(tmp_path, suite_dir, mock.base_url)).execute()

    sequence = [event["seq"] for event in events_of(outcome.out_dir)]
    assert sequence == list(range(1, len(sequence) + 1))


def test_every_recorded_attempt_has_a_start_and_an_end(tmp_path, one_task):
    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), delay=0.0) as mock:
        outcome = Runner(plan_for(tmp_path, suite_dir, mock.base_url)).execute()

    events = events_of(outcome.out_dir)
    starts = [event for event in events if event["kind"] == "attempt_started"]
    ends = [event for event in events if event["kind"] == "attempt_finished"]
    assert len(starts) == len(ends) == len(outcome.records) == 1
    assert starts[0]["task"] == ends[0]["task"] == outcome.records[0]["task"]
    assert starts[0]["phase"] == "first"


def test_run_started_carries_what_a_monitor_needs_to_label_itself(tmp_path, one_task):
    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), delay=0.0) as mock:
        outcome = Runner(plan_for(tmp_path, suite_dir, mock.base_url)).execute()

    started = events_of(outcome.out_dir)[0]
    assert started["suite"] == "suite"
    assert started["target"] == "mock"
    assert started["samples"] == 1
    assert started["repair"] is False
    assert started["tasks"] == ["t_double"]
    assert started["modelbench"]


def test_run_finished_reports_the_outcome(tmp_path, one_task):
    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), delay=0.0) as mock:
        outcome = Runner(plan_for(tmp_path, suite_dir, mock.base_url)).execute()

    finished = events_of(outcome.out_dir)[-1]
    assert finished["status"] == "finished"
    assert finished["records"] == 1
    assert finished["errors"] == 0


def test_attempt_finished_carries_the_numbers_the_dashboard_shows(tmp_path, one_task):
    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), delay=0.0) as mock:
        outcome = Runner(plan_for(tmp_path, suite_dir, mock.base_url)).execute()

    done = next(event for event in events_of(outcome.out_dir) if event["kind"] == "attempt_finished")
    for field in ("score", "passed", "total", "total_s", "ttft_s", "tok_per_s", "completion_tokens", "protocol"):
        assert field in done
    assert done["score"] == 1.0


def test_records_carry_the_3_0_stream_fields(tmp_path, one_task):
    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), delay=0.0) as mock:
        outcome = Runner(plan_for(tmp_path, suite_dir, mock.base_url)).execute()

    first = outcome.records[0]["first"]
    assert outcome.records[0]["record_version"] == RECORD_VERSION
    assert first["itl_p50_s"] is not None
    assert first["itl_p95_s"] is not None
    assert first["tok_per_s_wall"] is not None
    assert first["cache_ratio"] == 0.0


def test_the_dashboard_can_read_the_run_while_it_is_still_warm(tmp_path, one_task):
    """The TUI reads the same two files the runner writes; nothing else."""
    from modelbench.tui import TuiState

    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), delay=0.0) as mock:
        outcome = Runner(plan_for(tmp_path, suite_dir, mock.base_url)).execute()

    state = TuiState(outcome.out_dir).refresh()
    assert state.status == "finished"
    assert state.completed == 1
    assert state.total_pairs == 1
    assert state.tasks == ["t_double"]
    assert state.in_flight() == []


# --------------------------------------------------------------------------- #
# repairs and failures
# --------------------------------------------------------------------------- #
def test_a_repair_attempt_is_its_own_event(tmp_path, one_task):
    """A failing first answer plus a repair turn: two attempts, one record."""
    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), mode="garbage", delay=0.0) as mock:
        outcome = Runner(plan_for(tmp_path, suite_dir, mock.base_url, repair=True)).execute()

    events = events_of(outcome.out_dir)
    phases = [event["phase"] for event in events if event["kind"] == "attempt_started"]
    assert phases == ["first", "repair"]
    assert len(outcome.records) == 1
    assert outcome.records[0]["final_score"] == 0.0
    assert outcome.records[0]["repair"] is not None


def test_a_dead_event_log_does_not_stop_the_run(tmp_path, one_task, monkeypatch):
    """A full disk may cost the dashboard; it must not cost the measurement."""
    from modelbench.events import EventLog

    def boom(self, kind, **fields):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(EventLog, "emit", boom)
    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), delay=0.0) as mock:
        outcome = Runner(plan_for(tmp_path, suite_dir, mock.base_url)).execute()

    assert len(outcome.records) == 1
    header = json.loads((outcome.out_dir / "run.json").read_text(encoding="utf-8"))
    assert header["status"] == "finished"


def test_resuming_a_run_emits_a_skip_instead_of_a_second_attempt(tmp_path, one_task):
    suite_dir = one_task()
    with start_mock(Suite.load(suite_dir), delay=0.0) as mock:
        first = Runner(plan_for(tmp_path, suite_dir, mock.base_url)).execute()
        first_kinds = kinds(events_of(first.out_dir))
        again = Runner(plan_for(tmp_path, suite_dir, mock.base_url, resume=True)).execute()

    assert again.out_dir == first.out_dir
    # The log is append-only, so the second run's events come after the first's.
    second_kinds = kinds(events_of(again.out_dir))[len(first_kinds) :]
    assert second_kinds[:2] == ["run_started", "sample_skipped"]
    assert "attempt_started" not in second_kinds
    assert len(again.records) == 1
