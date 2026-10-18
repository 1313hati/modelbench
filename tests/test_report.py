from __future__ import annotations

import json

from modelbench.report import (
    load_run,
    load_runs,
    pairwise,
    per_task_metrics,
    render_console,
    render_json,
    render_markdown,
    run_metrics,
    write_reports,
)


def test_metrics_average_tasks_not_records(run_dir, record):
    # Task A has two perfect samples, task B one sample at 50%: the task mean
    # must be 75%, not 83% (which is what averaging records would give).
    records = [
        record("a", 1, 1.0, True),
        record("a", 2, 1.0, True),
        record("b", 1, 0.5, False),
    ]
    run = load_run(run_dir("model-a", records))
    metrics = run_metrics(run)
    assert metrics["records"] == 3
    assert metrics["first_score"] == 0.75
    assert round(metrics["solved_first"], 4) == round(2 / 3, 4)  # solved is measured per attempt
    assert metrics["assertions_passed"] == 25
    assert metrics["assertions_total"] == 30


def test_missing_and_duplicate_records_are_reported(run_dir, record):
    records = [record("a", 1, 1.0, True), record("a", 1, 1.0, True)]
    run = load_run(run_dir("model-a", records, tasks=["a", "b"], samples=2))
    metrics = run_metrics(run)
    assert metrics["expected"] == 4  # 2 tasks × 2 samples
    assert {(m["task"], m["sample"]) for m in metrics["missing"]} == {("a", 2), ("b", 1), ("b", 2)}
    assert metrics["duplicates"][0]["count"] == 2


def test_pairwise_delta_and_task_wins(run_dir, record):
    a = load_run(run_dir("model-a", [record("a", 1, 1.0), record("b", 1, 0.8)]))
    b = load_run(run_dir("model-b", [record("a", 1, 0.9), record("b", 1, 0.9)]))
    pair = pairwise(a, b)
    assert pair.wins_a == 1
    assert pair.wins_b == 1
    assert pair.ties == 0
    assert round(pair.mean_delta_pp, 1) == 0.0


def test_per_task_metrics_groups_samples(run_dir, record):
    run = load_run(run_dir("model-a", [record("a", 1, 1.0), record("a", 2, 0.5, False)]))
    tasks = per_task_metrics(run)
    assert tasks["a"]["first"] == 0.75
    assert tasks["a"]["solved_first"] == 0.5
    assert tasks["a"]["n"] == 2


def test_markdown_has_every_section(run_dir, record):
    a = load_run(run_dir("model-a", [record("a", 1, 1.0), record("b", 1, 0.9, False)]))
    b = load_run(run_dir("model-b", [record("a", 1, 0.8, False), record("b", 1, 0.7, False)]))
    md = render_markdown([a, b])
    for heading in ("## Headline", "## Per task", "## Per category", "## Provenance", "## Integrity", "## Reproducing this report"):
        assert heading in md
    assert "model-a" in md and "model-b" in md
    assert "leads on first-attempt quality" in md


def test_markdown_flags_incomplete_runs(run_dir, record):
    run = load_run(run_dir("model-a", [record("a", 1, 1.0)], tasks=["a", "b"]))
    md = render_markdown([run])
    assert "missing record" in md
    assert "b s1" in md


def test_json_summary_roundtrips(run_dir, record):
    a = load_run(run_dir("model-a", [record("a", 1, 1.0)]))
    payload = render_json([a])
    encoded = json.dumps(payload)
    assert "model-a" in encoded
    assert payload["runs"][0]["metrics"]["records"] == 1
    assert payload["runs"][0]["tasks"]["a"]["first"] == 1.0


def test_console_table_mentions_task_wins(run_dir, record):
    a = load_run(run_dir("model-a", [record("a", 1, 1.0)]))
    b = load_run(run_dir("model-b", [record("a", 1, 0.5, False)]))
    table = render_console(load_runs([a.path, b.path]))
    assert "task wins" in table
    assert "model-a 1" in table


def test_write_reports_creates_both_files(tmp_path, run_dir, record):
    run = load_run(run_dir("model-a", [record("a", 1, 1.0)]))
    md_path, json_path = write_reports([run], tmp_path / "out", title="t", notes="note")
    assert md_path.is_file() and json_path.is_file()
    assert "# t" in md_path.read_text()
    assert "note" in md_path.read_text()
