"""The dashboard, tested as a function of state and size.

Every test here calls :func:`render_frame` directly, with no terminal and no
curses: the layout is the part that can be wrong, and it is pure. The one thing
these tests insist on is that the frame is exactly the size asked for — a
dashboard that overflows its window corrupts the screen it is drawn on.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modelbench.tui import (
    Frame,
    TuiState,
    render_frame,
    render_text,
    sparkline,
)

T0 = 1767261600.0  # 2026-01-01T10:00:00Z, fixed so the clock is assertable


def write_run(
    root: Path,
    *,
    tasks: tuple[str, ...] = ("t_alpha", "t_beta"),
    samples: int = 2,
    records: list[dict] | None = None,
    events: list[dict] | None = None,
    status: str = "running",
    started_at: str = "2026-01-01T10:00:00+00:00",
    finished_at: str | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    header = {
        "record_version": 3,
        "modelbench": "3.0.0",
        "target": {"name": "qwen38", "base_url": "http://127.0.0.1:8080/v1", "model": "qwen38"},
        "suite": {"id": "core-v2", "version": "2.2", "digest": "abc123", "tasks": list(tasks)},
        "samples": samples,
        "repair": True,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
    }
    (root / "run.json").write_text(json.dumps(header), encoding="utf-8")
    (root / "results.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records or []), encoding="utf-8"
    )
    if events is not None:
        (root / "events.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in events), encoding="utf-8"
        )
    return root


def rec(task: str, sample: int = 1, score: float = 1.0, rate: float = 40.0, tokens: int = 500) -> dict:
    return {
        "task": task,
        "sample": sample,
        "final_score": score,
        "final_solved": score == 1.0,
        "wall_s": 12.0,
        "first": {
            "score": score,
            "tok_per_s": rate,
            "completion_tokens": tokens,
            "protocol": "ok",
        },
    }


def started(task: str, sample: int = 1, phase: str = "first", at: float = T0 + 100) -> dict:
    return {"kind": "attempt_started", "task": task, "sample": sample, "phase": phase, "t": at}


def finished(task: str, sample: int = 1, phase: str = "first", at: float = T0 + 140) -> dict:
    return {"kind": "attempt_finished", "task": task, "sample": sample, "phase": phase, "t": at}


def state_of(root: Path) -> TuiState:
    return TuiState(root).refresh()


# --------------------------------------------------------------------------- #
# geometry
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("width,height", [(40, 12), (60, 20), (80, 24), (120, 40), (200, 60)])
def test_frame_is_exactly_the_requested_size(tmp_path, width, height):
    root = write_run(tmp_path, records=[rec("t_alpha")], events=[started("t_beta")])
    frame = render_frame(state_of(root), width, height, now=T0 + 300)
    assert len(frame.lines) == height
    assert len(frame.styles) == height
    assert all(len(line) == width for line in frame.lines)


def test_frame_never_exceeds_a_tiny_window(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    frame = render_frame(state_of(root), 30, 8, now=T0 + 60)
    assert len(frame.lines) == 8
    assert all(len(line) == 30 for line in frame.lines)


def test_frame_has_one_style_per_line(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    frame = render_frame(state_of(root), 80, 24, now=T0 + 60)
    assert set(frame.styles) <= {
        "title",
        "rule",
        "progress",
        "header",
        "row",
        "bad",
        "dim",
        "warn",
        "footer",
    }
    assert frame.styles[0] == "title"
    assert frame.styles[-1] == "footer"


def test_narrow_terminal_keeps_task_names_and_drops_columns(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    text = render_frame(state_of(root), 40, 14, now=T0 + 60).text()
    assert "t_alpha" in text
    assert "protocol" not in text


def test_wide_terminal_shows_the_protocol_column(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    text = render_frame(state_of(root), 100, 20, now=T0 + 60).text()
    assert "protocol" in text


def test_ascii_mode_emits_only_ascii(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")], events=[started("t_beta")])
    text = render_frame(state_of(root), 100, 20, unicode=False, now=T0 + 60).text()
    assert text.isascii()
    assert "#" in text or "|" in text or "-" in text


def test_unicode_mode_uses_block_glyphs(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    text = render_frame(state_of(root), 100, 20, unicode=True, now=T0 + 60).text()
    assert "█" in text
    assert not text.isascii()


# --------------------------------------------------------------------------- #
# content
# --------------------------------------------------------------------------- #
def test_title_line_carries_suite_target_status_and_clock(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    title = render_frame(state_of(root), 120, 20, now=T0 + 305).lines[0]
    assert "modelbench" in title
    assert "core-v2" in title
    assert "qwen38" in title
    assert "running" in title
    assert "5m 05.0s" in title


def test_progress_counts_pairs_not_tasks(tmp_path):
    root = write_run(
        tmp_path,
        tasks=("t_alpha", "t_beta"),
        samples=2,
        records=[rec("t_alpha", 1), rec("t_alpha", 2), rec("t_beta", 1)],
    )
    text = render_frame(state_of(root), 100, 20, now=T0 + 60).text()
    assert "3/4 pairs" in text
    assert "75%" in text


def test_completed_counts_a_pair_once(tmp_path):
    # A resumed run can hold a record twice; the progress bar must not double-count.
    root = write_run(tmp_path, records=[rec("t_alpha", 1), rec("t_alpha", 1)])
    assert state_of(root).completed == 1


def test_done_task_shows_done_and_partial_shows_partial(tmp_path):
    root = write_run(
        tmp_path,
        tasks=("t_alpha", "t_beta"),
        samples=2,
        records=[rec("t_alpha", 1), rec("t_alpha", 2), rec("t_beta", 1)],
    )
    text = render_frame(state_of(root), 100, 20, now=T0 + 60).text()
    alpha = next(line for line in text.splitlines() if "t_alpha" in line)
    beta = next(line for line in text.splitlines() if "t_beta" in line)
    assert "done" in alpha
    assert "partial" in beta


def test_sample_scores_are_shown_per_column(tmp_path):
    root = write_run(
        tmp_path,
        samples=2,
        records=[rec("t_alpha", 1, score=0.5), rec("t_alpha", 2, score=1.0)],
    )
    line = next(
        line for line in render_frame(state_of(root), 100, 20, now=T0 + 60).lines if "t_alpha" in line
    )
    assert "50%" in line and "100%" in line


def test_eta_appears_only_while_running_with_progress(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    running = render_frame(state_of(root), 120, 20, now=T0 + 300).lines[0]
    assert "ETA" in running

    done = write_run(tmp_path / "done", status="finished", finished_at="2026-01-01T10:10:00+00:00")
    finished_title = render_frame(state_of(done), 120, 20, now=T0 + 600).lines[0]
    assert "ETA" not in finished_title
    assert "finished" in finished_title


def test_empty_run_renders_rather_than_crashing(tmp_path):
    root = write_run(tmp_path, records=[])
    text = render_frame(state_of(root), 80, 20, now=T0 + 5).text()
    assert "0/4 pairs" in text
    assert "no completed call yet" in text


def test_missing_directory_renders_a_waiting_screen(tmp_path):
    state = TuiState(tmp_path / "not-yet").refresh()
    assert state.status == "waiting"
    assert state.loaded is False
    text = render_frame(state, 80, 12, now=T0).text()
    assert "waiting for the run directory" in text


def test_missing_directory_snapshot_is_still_valid(tmp_path):
    snapshot = TuiState(tmp_path / "not-yet").refresh().snapshot(now=T0)
    assert snapshot["status"] == "waiting"
    assert snapshot["records"] == 0
    assert snapshot["in_flight"] == []


# --------------------------------------------------------------------------- #
# in-flight attempts
# --------------------------------------------------------------------------- #
def test_in_flight_attempt_is_named_with_its_age(tmp_path):
    root = write_run(tmp_path, records=[], events=[started("t_beta", 2, at=T0 + 100)])
    text = render_frame(state_of(root), 100, 20, now=T0 + 112).text()
    assert "now  t_beta s2 · first · 12.0s" in text


def test_repair_supersedes_the_first_attempt(tmp_path):
    root = write_run(
        tmp_path,
        events=[
            started("t_alpha", 1),
            finished("t_alpha", 1, at=T0 + 130),
            started("t_alpha", 1, phase="repair", at=T0 + 140),
        ],
    )
    live = state_of(root).in_flight(now=T0 + 145)
    assert [event["phase"] for event in live] == ["repair"]


def test_finishing_the_repair_clears_it(tmp_path):
    root = write_run(
        tmp_path,
        events=[
            started("t_alpha", 1),
            finished("t_alpha", 1, at=T0 + 130),
            started("t_alpha", 1, phase="repair", at=T0 + 140),
            finished("t_alpha", 1, phase="repair", at=T0 + 160),
        ],
    )
    assert state_of(root).in_flight(now=T0 + 170) == []


def test_failed_attempt_clears_in_flight(tmp_path):
    root = write_run(
        tmp_path,
        events=[started("t_alpha", 1), {"kind": "attempt_failed", "task": "t_alpha", "sample": 1, "t": T0 + 120}],
    )
    assert state_of(root).in_flight(now=T0 + 130) == []


def test_a_task_with_a_live_attempt_reads_running(tmp_path):
    root = write_run(tmp_path, tasks=("t_alpha",), samples=1, records=[], events=[started("t_alpha", 1)])
    line = next(
        line for line in render_frame(state_of(root), 100, 20, now=T0 + 105).lines if "t_alpha" in line
    )
    assert "running" in line


def test_errors_and_warnings_are_summarised(tmp_path):
    root = write_run(
        tmp_path,
        events=[
            {"kind": "attempt_failed", "task": "t_alpha", "sample": 1, "t": T0 + 10},
            {"kind": "warning", "reason": "context_too_small", "tasks": ["t_alpha"], "t": T0 + 11},
        ],
    )
    text = render_frame(state_of(root), 100, 20, now=T0 + 60).text()
    assert "errors 1" in text
    assert "1 warning(s)" in text


def test_ended_run_says_so_in_the_footer(tmp_path):
    root = write_run(tmp_path, status="finished", finished_at="2026-01-01T10:05:00+00:00")
    footer = render_frame(state_of(root), 100, 20, now=T0 + 400).lines[-1]
    assert "finished" in footer
    assert "press q" in footer


def test_paused_state_is_visible_in_the_title(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    title = render_frame(state_of(root), 120, 20, now=T0 + 60, paused=True).lines[0]
    assert "PAUSED" in title


def test_notice_replaces_the_key_hint(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    footer = render_frame(state_of(root), 120, 20, now=T0 + 60, notice="q is disabled").lines[-1]
    assert "q is disabled" in footer


def test_footer_survives_a_screen_with_no_room_for_statistics(tmp_path):
    root = write_run(
        tmp_path,
        tasks=tuple(f"t{i}" for i in range(12)),
        records=[rec("t0")],
        events=[started("t1")],
    )
    frame = render_frame(state_of(root), 60, 8, now=T0 + 60)
    assert "q quit" in frame.lines[-1]


def test_long_task_lists_are_truncated_with_a_count(tmp_path):
    tasks = tuple(f"task_number_{index}" for index in range(20))
    root = write_run(tmp_path, tasks=tasks, records=[rec(tasks[0])])
    text = render_frame(state_of(root), 100, 20, now=T0 + 60).text()
    assert "more task(s)" in text


# --------------------------------------------------------------------------- #
# derived numbers
# --------------------------------------------------------------------------- #
def test_snapshot_matches_what_the_screen_shows(tmp_path):
    root = write_run(
        tmp_path,
        records=[rec("t_alpha", 1, rate=40.0), rec("t_alpha", 2, rate=60.0)],
        events=[started("t_beta", 1, at=T0 + 200)],
    )
    snapshot = state_of(root).snapshot(now=T0 + 260)
    assert snapshot["status"] == "running"
    assert snapshot["records"] == 2
    assert snapshot["expected"] == 4
    assert snapshot["tasks"] == 2
    assert snapshot["median_tok_per_s"] == 40.0
    assert snapshot["completion_tokens"] == 1000
    assert [item["task"] for item in snapshot["in_flight"]] == ["t_beta"]
    assert snapshot["elapsed_s"] == 260.0
    assert snapshot["eta_s"] == 260.0


def test_speeds_ignore_records_without_a_rate(tmp_path):
    broken = rec("t_alpha")
    broken["first"]["tok_per_s"] = 0.0
    root = write_run(tmp_path, records=[rec("t_alpha", 1, rate=35.0), broken])
    assert state_of(root).speeds() == [35.0]


def test_snapshot_eta_is_none_before_any_record(tmp_path):
    root = write_run(tmp_path)
    assert state_of(root).snapshot(now=T0 + 10)["eta_s"] is None


def test_total_tokens_survives_records_without_usage(tmp_path):
    bare = {"task": "t_alpha", "sample": 1, "final_score": 1.0, "first": {}}
    root = write_run(tmp_path, records=[rec("t_alpha", 1, tokens=700), bare])
    assert state_of(root).total_tokens() == 700


def test_refresh_picks_up_new_records_without_a_restart(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha", 1)])
    state = state_of(root)
    assert state.completed == 1

    with open(root / "results.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(rec("t_alpha", 2)) + "\n")
    assert state.refresh().completed == 2


def test_refresh_picks_up_new_events(tmp_path):
    root = write_run(tmp_path, events=[started("t_alpha")])
    state = state_of(root)
    assert len(state.in_flight(now=T0 + 100)) == 1

    with open(root / "events.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(finished("t_alpha")) + "\n")
    assert state.refresh().in_flight(now=T0 + 200) == []


def test_refresh_tolerates_a_record_written_mid_append(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha", 1)])
    with open(root / "results.jsonl", "a", encoding="utf-8") as handle:
        handle.write('{"task": "t_alpha", "sample": 2')
    assert state_of(root).completed == 1


def test_unknown_status_falls_back_to_running(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    header = json.loads((root / "run.json").read_text(encoding="utf-8"))
    header.pop("status")
    (root / "run.json").write_text(json.dumps(header), encoding="utf-8")
    assert state_of(root).status == "running"


def test_run_finished_event_is_enough_to_close_a_run(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")], events=[{"kind": "run_finished", "t": T0 + 50}])
    header = json.loads((root / "run.json").read_text(encoding="utf-8"))
    header.pop("status")
    (root / "run.json").write_text(json.dumps(header), encoding="utf-8")
    assert state_of(root).status == "finished"


# --------------------------------------------------------------------------- #
# small pieces
# --------------------------------------------------------------------------- #
def test_sparkline_scales_to_the_observed_range():
    line = sparkline([1.0, 2.0, 3.0], 3)
    assert len(line) == 3
    assert line[0] != line[-1]


def test_sparkline_of_a_flat_series_is_not_maximal():
    # Reading "all equal" as "all maximal" is the classic sparkline lie.
    flat = sparkline([5.0, 5.0, 5.0], 3)
    assert len(set(flat)) == 1
    assert "█" not in flat


def test_sparkline_trims_to_the_newest_values():
    line = sparkline([1.0, 2.0, 3.0, 4.0, 5.0], 2)
    assert len(line) == 2


def test_sparkline_of_nothing_is_empty():
    assert sparkline([], 10) == ""
    assert sparkline([1.0], 0) == ""


def test_render_text_can_emit_ansi_colour(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    plain = render_text(state_of(root), 80, 16, colour=False)
    coloured = render_text(state_of(root), 80, 16, colour=True)
    assert "\033[" not in plain
    assert "\033[" in coloured
    assert "modelbench" in coloured


def test_frame_text_joins_the_lines(tmp_path):
    root = write_run(tmp_path, records=[rec("t_alpha")])
    frame = render_frame(state_of(root), 60, 10, now=T0 + 30)
    assert isinstance(frame, Frame)
    assert frame.text().count("\n") == len(frame) - 1
