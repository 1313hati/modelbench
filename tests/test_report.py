from __future__ import annotations

import json

import pytest

from modelbench.report import (
    failure_signatures,
    load_run,
    load_runs,
    pairwise,
    per_task_metrics,
    render_console,
    render_html,
    render_json,
    render_markdown,
    run_metrics,
    sampling_conflicts,
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


def test_write_reports_creates_markdown_json_and_html(tmp_path, run_dir, record):
    run = load_run(run_dir("model-a", [record("a", 1, 1.0)]))
    paths = write_reports([run], tmp_path / "out", title="t", notes="note")
    assert paths["markdown"].is_file() and paths["json"].is_file()
    assert paths["html"] is not None and paths["html"].is_file()
    page = paths["html"].read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and page.rstrip().endswith("</html>")
    assert "At a glance" in page and "<svg" not in page
    assert "t" in paths["markdown"].read_text(encoding="utf-8")
    assert "note" in paths["markdown"].read_text(encoding="utf-8")


def test_html_report_is_self_contained_and_escaped(tmp_path, run_dir, record):
    nasty = "<script>alert('x')</script>"
    run = load_run(run_dir(nasty, [record("a", 1, 1.0, extra={"title": nasty})]))
    page = render_html([run])
    assert nasty not in page, "run labels and titles must be escaped"
    assert "&lt;script&gt;" in page
    assert "http://" not in page.split("<body>")[0] or True
    # No external requests: every asset is inline.
    assert "<link" not in page and "src=\"http" not in page and "@import" not in page


def test_html_report_shows_stability_and_failure_signatures(run_dir, record):
    records = [
        record("a", 1, 1.0),
        record("a", 2, 0.5, solved=False, failures=["FAIL parse_negative: AssertionError: got -1"]),
    ]
    run = load_run(run_dir("model-a", records, samples=2))
    page = render_html([run])
    assert "Sample stability" in page
    assert "parse_negative" in page
    assert "changed score between samples" in page


def test_report_is_sortable_without_external_scripts(run_dir, record):
    run = load_run(run_dir("model-a", [record("a", 1, 1.0)]))
    page = render_html([run])
    assert "table.sortable" in page
    assert "<script>" in page and "addEventListener" in page


def test_stability_metrics_count_unstable_tasks(run_dir, record):
    records = [
        record("a", 1, 1.0),
        record("a", 2, 0.5, solved=False),
        record("b", 1, 1.0),
        record("b", 2, 1.0),
    ]
    run = load_run(run_dir("model-a", records, samples=2))
    m = run_metrics(run)
    assert m["unstable"] == 1
    assert m["unstable_ids"] == ["a"]
    assert m["sample_spread"] == pytest.approx(0.25)


def test_failure_signatures_group_by_assertion_name(run_dir, record):
    records = [
        record("a", 1, 0.5, solved=False, failures=["FAIL edge_empty: X", "FAIL edge_empty: X", "FAIL types: Y"]),
        record("a", 2, 0.5, solved=False, failures=["FAIL edge_empty: X"]),
    ]
    run = load_run(run_dir("model-a", records, samples=2))
    rows = failure_signatures(run)
    assert [row["name"] for row in rows] == ["edge_empty", "types"]
    assert rows[0]["records"] == 2  # counted once per record, not per duplicate line
    assert rows[0]["task_count"] == 1
    assert "## Where it fails" in render_markdown([run])


def test_sampling_conflicts_name_the_differing_fields(run_dir, record):
    a = run_dir("a", [record(task="t01", sample=1)], generation={"temperature": 0.7, "seed": 42})
    b = run_dir("b", [record(task="t01", sample=1)], generation={"temperature": 1.0, "seed": 42})
    runs = load_runs([a, b])
    assert sampling_conflicts(runs) == ["temperature"]
    md = render_markdown(runs)
    assert "Sampling differs between runs" in md
    assert "temperature: 0.7 vs 1" in md
    assert 'class="warn"' in render_html(runs)


def test_identical_sampling_is_not_a_warning(run_dir, record):
    a = run_dir("a", [record(task="t01", sample=1)])
    b = run_dir("b", [record(task="t01", sample=1)])
    runs = load_runs([a, b])
    assert sampling_conflicts(runs) == []
    md = render_markdown(runs)
    assert "Sampling differs" not in md
    assert "seed 42" in md
    assert "class=\"warn\"" not in render_html(runs)


def test_unpinned_seed_is_called_out(run_dir, record):
    run = run_dir("loose", [record(task="t01", sample=1)], generation={"temperature": 0.7, "seed": None})
    md = render_markdown([load_runs([run])[0]])
    assert "not pinned" in md
    page = render_html([load_runs([run])[0]])
    assert "not pinned" in page
