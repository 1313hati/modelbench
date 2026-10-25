"""History: the same target, many runs, in order.

The interesting cases are the ones a leaderboard never sees: a series that
changes suite digest (so a delta measures the benchmark, not the model), a
target seen only once, and a directory that is not a run at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modelbench.history import build, render_console, render_markdown, summary_line


def make_run(
    root: Path,
    *,
    label: str = "qwen38",
    started_at: str = "2026-01-01T10:00:00+00:00",
    digest: str = "abc123",
    scores: tuple[float, ...] = (1.0, 1.0),
    rate: float = 40.0,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    header = {
        "record_version": 3,
        "target": {"name": label, "base_url": "http://127.0.0.1:8080/v1", "model": label},
        "suite": {
            "id": "core-v2",
            "version": "2.2",
            "digest": digest,
            "tasks": [f"t{index}" for index in range(len(scores))],
        },
        "samples": 1,
        "status": "finished",
        "started_at": started_at,
        "finished_at": started_at,
    }
    (root / "run.json").write_text(json.dumps(header), encoding="utf-8")
    records = []
    for index, score in enumerate(scores):
        records.append(
            {
                "task": f"t{index}",
                "sample": 1,
                "target": label,
                "suite_digest": digest,
                "final_score": score,
                "final_solved": score == 1.0,
                "wall_s": 10.0,
                "first": {
                    "score": score,
                    "solved": score == 1.0,
                    "total": 10,
                    "passed": int(score * 10),
                    "completion_tokens": 400,
                    "total_s": 9.0,
                    "ttft_s": 0.4,
                    "tok_per_s": rate,
                    "tok_per_s_wall": rate * 0.8,
                    "protocol": "ok",
                },
            }
        )
    (root / "results.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )
    return root


def test_runs_are_ordered_oldest_first(tmp_path):
    late = make_run(tmp_path / "b", started_at="2026-02-01T10:00:00+00:00")
    early = make_run(tmp_path / "a", started_at="2026-01-01T10:00:00+00:00")
    payload = build([late, early])
    assert [row["when"] for row in payload["runs"]] == [
        "2026-01-01T10:00:00+00:00",
        "2026-02-01T10:00:00+00:00",
    ]


def test_delta_is_against_the_previous_run_of_the_same_target(tmp_path):
    low = make_run(tmp_path / "a", scores=(0.5, 0.5))
    high = make_run(tmp_path / "b", started_at="2026-01-02T10:00:00+00:00", scores=(1.0, 1.0))
    rows = build([high, low])["runs"]
    assert rows[0]["delta_pp"] is None
    assert rows[1]["delta_pp"] == pytest.approx(50.0)


def test_the_first_run_of_a_target_has_no_delta(tmp_path):
    rows = build([make_run(tmp_path / "a")])["runs"]
    assert rows[0]["delta_pp"] is None


def test_two_targets_keep_separate_series(tmp_path):
    one = make_run(tmp_path / "a", label="qwen38", scores=(0.5, 0.5))
    two = make_run(tmp_path / "b", label="minicpm", started_at="2026-01-02T10:00:00+00:00", scores=(1.0, 1.0))
    payload = build([one, two])
    assert payload["series"] == ["minicpm", "qwen38"]
    assert all(row["delta_pp"] is None for row in payload["runs"])


def test_by_final_ranks_on_the_repair_score(tmp_path):
    root = make_run(tmp_path / "a", scores=(0.5, 0.5))
    path = root / "results.jsonl"
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for record in records:
        record["final_score"] = 1.0  # the repair turn fixed it
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")

    assert build([root], by="first")["runs"][0]["score"] == pytest.approx(0.5)
    assert build([root], by="final")["runs"][0]["score"] == pytest.approx(1.0)


def test_a_suite_digest_change_is_called_out(tmp_path):
    first = make_run(tmp_path / "a", digest="aaaa")
    second = make_run(tmp_path / "b", started_at="2026-01-02T10:00:00+00:00", digest="bbbb")
    text = render_console(build([first, second]))
    assert "suite changed inside these series" in text
    assert "qwen38" in text.split("warning:")[1]


def test_an_unchanged_suite_digest_is_not_called_out(tmp_path):
    first = make_run(tmp_path / "a")
    second = make_run(tmp_path / "b", started_at="2026-01-02T10:00:00+00:00")
    assert "suite changed" not in render_console(build([first, second]))


def test_console_shows_a_sparkline_once_there_are_two_runs(tmp_path):
    first = make_run(tmp_path / "a", scores=(0.4, 0.4))
    second = make_run(tmp_path / "b", started_at="2026-01-02T10:00:00+00:00", scores=(0.9, 0.9))
    text = render_console(build([first, second]))
    assert "40 -> 90" in text


def test_a_single_run_has_no_sparkline(tmp_path):
    text = render_console(build([make_run(tmp_path / "a")]))
    assert "->" not in text


def test_unreadable_directories_are_skipped(tmp_path):
    good = make_run(tmp_path / "a")
    empty = tmp_path / "b"
    empty.mkdir()
    payload = build([good, empty, tmp_path / "missing"])
    assert payload["count"] == 1


def test_build_raises_when_nothing_can_be_read(tmp_path):
    with pytest.raises(ValueError):
        build([tmp_path / "missing"])


def test_markdown_knows_the_columns(tmp_path):
    text = render_markdown(build([make_run(tmp_path / "a")]))
    assert text.splitlines()[0].startswith("| when | target |")
    assert "qwen38" in text
    assert "100.0%" in text


def test_summary_of_one_run_is_a_sentence_not_a_table(tmp_path):
    text = summary_line(build([make_run(tmp_path / "a")]))
    assert text.startswith("one run: qwen38")
    assert "2026-01-01" in text


def test_summary_counts_runs_and_targets(tmp_path):
    first = make_run(tmp_path / "a", scores=(0.5, 0.5))
    second = make_run(tmp_path / "b", started_at="2026-01-02T10:00:00+00:00", scores=(1.0, 1.0))
    text = summary_line(build([first, second]))
    assert "2 runs" in text
    assert "+50.0 pp" in text


def test_console_of_an_empty_build_is_impossible_to_reach(tmp_path):
    # build() refuses an empty series; render_console is defensive anyway.
    assert render_console({"runs": [], "series": [], "by": "first"}) == "no runs found"


def test_median_rate_is_carried_for_each_run(tmp_path):
    rows = build([make_run(tmp_path / "a", rate=42.0)])["runs"]
    assert rows[0]["median_tps"] == pytest.approx(42.0)
