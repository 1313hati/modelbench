"""The event log: append-only, ordered, and forgiving.

The properties worth defending are not the JSON shape but the failure
behaviour: a monitor must never see a renumbered sequence, a half-written line
must cost one event rather than the file, and a full disk must not be able to
abort a run that is measuring something real.
"""

from __future__ import annotations

import json

import pytest

from modelbench.events import EVENT_VERSION, EventLog, iter_new, read_events


def test_emit_writes_one_json_line_per_event(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    log.emit("run_started", suite="core-v2")
    log.emit("attempt_started", task="t01", sample=1)
    log.close()

    lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["kind"] == "run_started"
    assert first["suite"] == "core-v2"
    assert first["v"] == EVENT_VERSION
    assert isinstance(first["t"], float)


def test_sequence_numbers_are_dense_and_start_at_one(tmp_path):
    log = EventLog(tmp_path / "e.jsonl")
    for index in range(5):
        log.emit("attempt_finished", task=f"t{index}")
    log.close()

    events = read_events(tmp_path / "e.jsonl")
    assert [event["seq"] for event in events] == [1, 2, 3, 4, 5]


def test_caller_fields_cannot_overwrite_the_envelope(tmp_path):
    # A field called "seq" or "t" must not corrupt the log for every reader;
    # the envelope wins, because a reader keys on it.
    log = EventLog(tmp_path / "e.jsonl")
    event = log.emit("attempt_started", seq=99, t=1.0, at="yesterday", v=42)
    log.close()

    assert event["seq"] == 1
    assert event["kind"] == "attempt_started"
    assert event["v"] == EVENT_VERSION
    assert event["at"] != "yesterday"
    assert event["t"] > 1.0


def test_append_mode_keeps_an_existing_log(tmp_path):
    path = tmp_path / "e.jsonl"
    first = EventLog(path)
    first.emit("run_started")
    first.close()

    second = EventLog(path)
    second.emit("run_finished")
    second.close()

    kinds = [event["kind"] for event in read_events(path)]
    assert kinds == ["run_started", "run_finished"]
    # A second writer in the same process restarts at 1, which is why readers
    # use the file order rather than trusting seq to be globally unique.
    assert [event["seq"] for event in read_events(path)] == [1, 1]


def test_close_is_idempotent(tmp_path):
    log = EventLog(tmp_path / "e.jsonl")
    log.close()
    log.close()


def test_context_manager_closes(tmp_path):
    with EventLog(tmp_path / "e.jsonl") as log:
        log.emit("run_started")
    assert log._fh.closed


def test_emit_creates_the_parent_directory(tmp_path):
    log = EventLog(tmp_path / "nested" / "run" / "events.jsonl")
    log.emit("run_started")
    log.close()
    assert (tmp_path / "nested" / "run" / "events.jsonl").is_file()


def test_read_events_tolerates_a_truncated_last_line(tmp_path):
    path = tmp_path / "e.jsonl"
    log = EventLog(path)
    log.emit("run_started")
    log.emit("attempt_started", task="t01")
    log.close()
    with open(path, "a", encoding="utf-8") as handle:
        handle.write('{"v": 1, "seq": 3, "kind": "attempt_fin')  # killed mid-write

    events = read_events(path)
    assert [event["kind"] for event in events] == ["run_started", "attempt_started"]


def test_read_events_of_a_missing_file_is_empty(tmp_path):
    assert read_events(tmp_path / "nope.jsonl") == []


def test_iter_new_does_not_consume_a_half_written_line(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text('{"kind": "a", "seq": 1}\n{"kind": "b"', encoding="utf-8")

    seen = list(iter_new(path))
    assert [event["kind"] for event, _ in seen] == ["a"]
    offset = seen[-1][1]

    with open(path, "a", encoding="utf-8") as handle:
        handle.write(', "seq": 2}\n')
    rest = list(iter_new(path, offset))
    assert [event["kind"] for event, _ in rest] == ["b"]
    assert rest[-1][1] > offset


def test_iter_new_restarts_when_the_file_shrinks(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text('{"kind": "a", "seq": 1}\n{"kind": "b", "seq": 2}\n', encoding="utf-8")
    offset = list(iter_new(path))[-1][1]
    path.write_text('{"kind": "c", "seq": 1}\n', encoding="utf-8")
    assert path.stat().st_size < offset

    assert [event["kind"] for event, _ in iter_new(path, offset)] == ["c"]


def test_iter_new_skips_blank_and_broken_lines(tmp_path):
    path = tmp_path / "e.jsonl"
    path.write_text('{"kind": "a"}\n\nnot json\n{"kind": "b"}\n', encoding="utf-8")
    assert [event["kind"] for event, _ in iter_new(path)] == ["a", "b"]


def test_iter_new_of_a_missing_file_yields_nothing(tmp_path):
    assert list(iter_new(tmp_path / "nope.jsonl")) == []


def test_the_raw_writer_raises_so_the_caller_can_decide(tmp_path, monkeypatch):
    """A dead log must not take the benchmark with it — see runner._emit.

    The EventLog itself stays dumb: it raises, and the runner wraps every emit
    so a full disk costs monitoring, never a measurement. Swallowing here would
    hide the disk filling up from the one caller that can do something about it.
    """
    log = EventLog(tmp_path / "e.jsonl")

    def boom(*_args, **_kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(log._fh, "write", boom)
    with pytest.raises(OSError):
        log.emit("run_started")
    log.close()
