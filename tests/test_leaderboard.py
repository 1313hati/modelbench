from __future__ import annotations

import json

import pytest

from modelbench.errors import ModelBenchError
from modelbench.leaderboard import build, render_console, render_json, render_markdown
from modelbench.report import load_run, load_runs


def _run(run_dir, record, label: str, scores: list[float], digest: str | None = None, tokens: int = 100):
    records = []
    for i, score in enumerate(scores, start=1):
        item = record(f"t{i:02d}", 1, score)
        item["first"]["completion_tokens"] = tokens
        records.append(item)
    path = run_dir(label, records)
    if digest:
        header = json.loads((path / "run.json").read_text(encoding="utf-8"))
        header["suite"]["digest"] = digest
        (path / "run.json").write_text(json.dumps(header), encoding="utf-8")
    return path


def test_higher_score_ranks_first(run_dir, record):
    low = _run(run_dir, record, "low", [0.4, 0.5, 0.6])
    high = _run(run_dir, record, "high", [0.8, 0.9, 1.0])
    payload = build(load_runs([low, high]))
    assert [row["label"] for row in payload["rows"]] == ["high", "low"]
    assert payload["rows"][0]["rank"] == 1


def test_overlapping_intervals_share_a_rank(run_dir, record):
    one = _run(run_dir, record, "one", [0.8, 0.9, 1.0, 0.7])
    two = _run(run_dir, record, "two", [0.8, 0.9, 1.0, 0.7])
    payload = build(load_runs([one, two]))
    assert all(row["unresolved"] for row in payload["rows"])
    assert payload["rows"][0]["tied_with"] == [payload["rows"][1]["label"]]
    markdown = render_markdown(payload)
    assert "## Unresolved" in markdown
    assert "1=" in markdown or "2=" in markdown


def test_different_suites_are_refused(run_dir, record):
    a = _run(run_dir, record, "a", [0.9])
    b = _run(run_dir, record, "b", [0.8], digest="different")
    with pytest.raises(ModelBenchError, match="different suites"):
        build(load_runs([a, b]))
    payload = build(load_runs([a, b]), allow_mixed=True)
    assert payload["warnings"]


def test_frontier_prefers_score_without_more_tokens(run_dir, record):
    # Same score, fewer tokens: only the cheaper run is on the frontier.
    cheap = _run(run_dir, record, "cheap", [0.9, 0.8], tokens=100)
    pricey = _run(run_dir, record, "pricey", [0.9, 0.8], tokens=900)
    payload = build(load_runs([cheap, pricey]))
    frontier = {row["label"]: row["frontier"] for row in payload["rows"]}
    assert frontier == {"cheap": True, "pricey": False}


def test_json_is_serialisable(run_dir, record):
    payload = build(load_runs([_run(run_dir, record, "a", [1.0, 0.5])]))
    data = render_json(payload)
    assert json.loads(json.dumps(data))["rows"][0]["label"] == "a"
    assert isinstance(data["rows"][0]["ci_pp"], list)
