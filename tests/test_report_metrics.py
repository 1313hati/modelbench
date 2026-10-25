"""The 3.0 metrics: where the time went, and what a point of score cost.

Two rules are load-bearing here and both are easy to get wrong in a way that
looks fine on screen:

* "not measured" is not zero. A server that sends no cache details must not be
  reported as 0% cached, and a record written by modelbench 2.x has no
  inter-token timing at all.
* the three speeds are three different claims. If they collapse into one
  number, the report is lying about what it measured.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from modelbench.report import (
    load_run,
    render_html,
    render_json,
    render_markdown,
    run_metrics,
    timing_rows,
)


def full_record(
    task: str = "t01",
    sample: int = 1,
    *,
    score: float = 1.0,
    tokens: int = 400,
    total_s: float = 8.0,
    ttft_s: float = 0.5,
    itl: tuple[float, float] | None = (0.02, 0.05),
    wall_rate: float | None = 40.0,
    cache: float | None = 0.25,
    wall_s: float = 9.0,
) -> dict:
    first = {
        "score": score,
        "solved": score == 1.0,
        "passed": int(score * 10),
        "total": 10,
        "completion_tokens": tokens,
        "prompt_tokens": 900,
        "cached_tokens": 300 if cache is not None else None,
        "total_s": total_s,
        "ttft_s": ttft_s,
        "tok_per_s": tokens / max(total_s - ttft_s, 1e-6),
        "finish_reason": "stop",
        "source": "fence",
        "protocol": "ok",
        "failures": [],
    }
    if itl is not None:
        first["itl_p50_s"], first["itl_p95_s"] = itl
    if wall_rate is not None:
        first["tok_per_s_wall"] = wall_rate
    if cache is not None:
        first["cache_ratio"] = cache
    return {
        "record_version": 3,
        "target": "model-a",
        "model": "model-a",
        "task": task,
        "sample": sample,
        "suite": "core-v2",
        "first": first,
        "repair": None,
        "final_score": score,
        "final_solved": score == 1.0,
        "wall_s": wall_s,
    }


def make_run(root: Path, records: list[dict], *, samples: int = 1) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    header = {
        "record_version": 3,
        "target": {"name": "model-a", "base_url": "http://127.0.0.1:8080/v1", "model": "model-a"},
        "suite": {
            "id": "core-v2",
            "version": "2.2",
            "digest": "abc123",
            "tasks": sorted({r["task"] for r in records}),
        },
        "samples": samples,
        "status": "finished",
        "started_at": "2026-01-01T10:00:00+00:00",
        "finished_at": "2026-01-01T10:05:00+00:00",
    }
    (root / "run.json").write_text(json.dumps(header), encoding="utf-8")
    (root / "results.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in records), encoding="utf-8"
    )
    return root


def metrics_of(root: Path) -> dict:
    return run_metrics(load_run(root))


# --------------------------------------------------------------------------- #
# the three speeds
# --------------------------------------------------------------------------- #
def test_three_speeds_are_reported_separately(tmp_path):
    metrics = metrics_of(make_run(tmp_path / "r", [full_record(total_s=8.0, ttft_s=0.5, wall_rate=42.0)]))
    assert metrics["tps_p50"] == pytest.approx(400 / 7.5)
    assert metrics["wall_tps_p50"] == pytest.approx(42.0)
    assert metrics["tps_p50"] != metrics["wall_tps_p50"]


def test_ttft_percentiles(tmp_path):
    records = [
        full_record("t01", ttft_s=0.2),
        full_record("t02", ttft_s=0.4),
        full_record("t03", ttft_s=3.0),
    ]
    metrics = metrics_of(make_run(tmp_path / "r", records))
    assert metrics["ttft_p50"] == pytest.approx(0.4)
    assert metrics["ttft_p95"] == pytest.approx(3.0)


def test_inter_token_times_are_medians_of_the_per_call_medians(tmp_path):
    records = [
        full_record("t01", itl=(0.010, 0.030)),
        full_record("t02", itl=(0.030, 0.090)),
        full_record("t03", itl=(0.020, 0.060)),
    ]
    metrics = metrics_of(make_run(tmp_path / "r", records))
    assert metrics["itl_p50"] == pytest.approx(0.020)
    assert metrics["itl_p95"] == pytest.approx(0.060)


# --------------------------------------------------------------------------- #
# not measured is not zero
# --------------------------------------------------------------------------- #
def test_legacy_records_report_no_inter_token_time(tmp_path):
    legacy = full_record()
    for key in ("itl_p50_s", "itl_p95_s", "tok_per_s_wall", "cache_ratio"):
        legacy["first"].pop(key, None)
    metrics = metrics_of(make_run(tmp_path / "r", [legacy]))
    assert metrics["itl_p50"] is None
    assert metrics["itl_p95"] is None
    assert metrics["wall_tps_p50"] is None
    assert metrics["cache_ratio"] is None
    assert metrics["cache_records"] == 0


def test_a_zero_cache_ratio_is_a_measurement(tmp_path):
    metrics = metrics_of(make_run(tmp_path / "r", [full_record(cache=0.0)]))
    assert metrics["cache_ratio"] == 0.0
    assert metrics["cache_records"] == 1


def test_cache_ratio_averages_only_calls_that_reported(tmp_path):
    reporting = full_record("t01", cache=0.5)
    silent = full_record("t02")
    silent["first"].pop("cache_ratio")
    metrics = metrics_of(make_run(tmp_path / "r", [reporting, silent]))
    assert metrics["cache_ratio"] == pytest.approx(0.5)
    assert metrics["cache_records"] == 1


# --------------------------------------------------------------------------- #
# budget
# --------------------------------------------------------------------------- #
def test_generation_share_of_wall_clock(tmp_path):
    metrics = metrics_of(make_run(tmp_path / "r", [full_record(total_s=8.0, wall_s=10.0)]))
    assert metrics["generation_s"] == pytest.approx(8.0)
    assert metrics["grading_s"] == pytest.approx(2.0)
    assert metrics["gen_share"] == pytest.approx(0.8)


def test_generation_share_is_unknown_without_wall_time(tmp_path):
    record = full_record()
    record["wall_s"] = 0.0
    metrics = metrics_of(make_run(tmp_path / "r", [record]))
    assert metrics["gen_share"] is None
    assert metrics["grading_s"] == 0.0


def test_tokens_per_solved_task(tmp_path):
    records = [
        full_record("t01", tokens=100),
        full_record("t02", tokens=300, score=0.0),
    ]
    metrics = metrics_of(make_run(tmp_path / "r", records))
    # Both tokens were spent; only one task was solved. That is the point.
    assert metrics["tokens_per_solved"] == pytest.approx(400)


def test_tokens_per_solved_is_unknown_when_nothing_was_solved(tmp_path):
    metrics = metrics_of(make_run(tmp_path / "r", [full_record(score=0.0)]))
    assert metrics["tokens_per_solved"] is None


def test_score_per_ktoken(tmp_path):
    records = [full_record("t01", tokens=500, score=1.0), full_record("t02", tokens=500, score=0.0)]
    metrics = metrics_of(make_run(tmp_path / "r", records))
    assert metrics["score_per_ktoken"] == pytest.approx(0.5)


# --------------------------------------------------------------------------- #
# rows and renderers
# --------------------------------------------------------------------------- #
def test_timing_rows_keep_the_three_speeds_apart(tmp_path):
    run = load_run(make_run(tmp_path / "r", [full_record()]))
    rows = dict(timing_rows([run], [run_metrics(run)]))
    assert "TTFT p50 / p95" in rows
    assert "inter-token p50 / p95" in rows
    assert "decode tok/s p50 / p90" in rows
    assert "end-to-end tok/s p50" in rows
    assert rows["inter-token p50 / p95"][0] == "20 ms / 50 ms"


def test_timing_rows_drop_what_was_never_measured(tmp_path):
    legacy = full_record()
    for key in ("itl_p50_s", "itl_p95_s", "tok_per_s_wall", "cache_ratio"):
        legacy["first"].pop(key, None)
    run = load_run(make_run(tmp_path / "r", [legacy]))
    labels = [label for label, _ in timing_rows([run], [run_metrics(run)])]
    assert "inter-token p50 / p95" not in labels
    assert "prompt cache hit" not in labels
    assert "end-to-end tok/s p50" not in labels
    # TTFT and the decode rate were measured and must survive.
    assert "TTFT p50 / p95" in labels
    assert "decode tok/s p50 / p90" in labels


def test_grading_overhead_is_shown_in_seconds_below_a_minute(tmp_path):
    run = load_run(make_run(tmp_path / "r", [full_record(total_s=8.0, wall_s=10.0)]))
    rows = dict(timing_rows([run], [run_metrics(run)]))
    assert rows["grading / extraction overhead"][0] == "2.0s"


def test_markdown_has_a_timing_section_with_the_numbers(tmp_path):
    run = load_run(make_run(tmp_path / "r", [full_record()]))
    text = render_markdown([run])
    assert "## Timing and budget" in text
    assert "| TTFT p50 / p95 |" in text
    assert "end-to-end tok/s p50" in text


def test_markdown_timing_section_omits_empty_rows(tmp_path):
    legacy = full_record()
    for key in ("itl_p50_s", "itl_p95_s", "tok_per_s_wall", "cache_ratio"):
        legacy["first"].pop(key, None)
    run = load_run(make_run(tmp_path / "r", [legacy]))
    text = render_markdown([run])
    assert "## Timing and budget" in text
    assert "inter-token p50 / p95" not in text


def test_html_has_the_timing_table(tmp_path):
    run = load_run(make_run(tmp_path / "r", [full_record()]))
    page = render_html([run])
    assert "Timing and budget" in page
    assert "TTFT p50 / p95" in page
    assert "end-to-end tok/s p50" in page


def test_json_carries_the_new_metrics(tmp_path):
    run = load_run(make_run(tmp_path / "r", [full_record()]))
    payload = render_json([run])
    metrics = payload["runs"][0]["metrics"]
    assert metrics["itl_p50"] == pytest.approx(0.02)
    assert metrics["wall_tps_p50"] == pytest.approx(40.0)
    assert metrics["cache_ratio"] == pytest.approx(0.25)
    assert metrics["tokens_per_solved"] == pytest.approx(400)


def test_sub_millisecond_pacing_is_not_reported_as_zero(tmp_path):
    run = load_run(make_run(tmp_path / "r", [full_record(itl=(0.0002, 0.0004))]))
    rows = dict(timing_rows([run], [run_metrics(run)]))
    assert rows["inter-token p50 / p95"][0] == "<1 ms / <1 ms"


def test_very_high_rates_are_rounded_for_readability(tmp_path):
    fast = full_record(tokens=400, total_s=0.001, ttft_s=0.0, wall_rate=250000.0)
    run = load_run(make_run(tmp_path / "r", [fast]))
    rows = dict(timing_rows([run], [run_metrics(run)]))
    assert "/" in rows["decode tok/s p50 / p90"][0]
    assert "e+" not in rows["decode tok/s p50 / p90"][0]
    assert rows["end-to-end tok/s p50"][0] == "250000"
