from __future__ import annotations

import json

import pytest

from modelbench.compare import compare_paths, exit_code, render_console, render_markdown
from modelbench.report import load_run


def _scores(value: float, tasks: int = 12) -> dict[str, float]:
    return {f"t{index:02d}": value for index in range(1, tasks + 1)}


def _run(run_dir, record, label: str, scores: dict[str, float]):
    return run_dir(label, [record(task, 1, score) for task, score in scores.items()])


def test_a_clean_sweep_is_established_and_fails_a_regression_gate(run_dir, record):
    baseline = _run(run_dir, record, "base", _scores(1.0))
    weak = _run(run_dir, record, "weak", _scores(0.2))

    result = compare_paths(baseline, [weak])

    comparison = result["_comparisons"][0]
    assert comparison.verdict == "worse"
    assert comparison.established is True
    assert comparison.gap_pp == pytest.approx(-80.0)
    assert result["baseline"]["score"] == pytest.approx(1.0)
    # The gate reads the direction, not the size.
    assert exit_code(result, "regression") == 1
    assert exit_code(result, "never") == 0


def test_holm_erases_a_borderline_win_once_it_joins_a_family(run_dir, record):
    # 10 wins, 2 losses: p = 0.039 on its own, which clears alpha.
    borderline = _scores(0.5)
    for task in list(borderline)[:10]:
        borderline[task] = 0.6
    for task in list(borderline)[10:]:
        borderline[task] = 0.4

    baseline = _run(run_dir, record, "base", _scores(0.5))
    challenger = _run(run_dir, record, "challenger", borderline)

    alone = compare_paths(baseline, [challenger])
    assert alone["_comparisons"][0].established is True

    # Four runs that are indistinguishable from the baseline make five tests.
    family = [challenger] + [
        _run(run_dir, record, f"copy{index}", _scores(0.5)) for index in range(1, 5)
    ]
    corrected = compare_paths(baseline, family)
    adjusted = corrected["_comparisons"][0]
    assert adjusted.established is False
    assert adjusted.p_adjusted > 0.05
    assert adjusted.verdict == "not established"


def test_identical_runs_say_identical_rather_than_zero_zero(run_dir, record):
    baseline = _run(run_dir, record, "base", _scores(0.8))
    copy = _run(run_dir, record, "copy", _scores(0.8))

    result = compare_paths(baseline, [copy])
    comparison = result["_comparisons"][0]

    assert comparison.identical is True
    assert comparison.verdict == "identical"
    # "identical" is a settled answer, not an unresolved comparison.
    assert exit_code(result, "unresolved") == 0


def test_runs_from_another_suite_are_refused(run_dir, record):
    baseline = _run(run_dir, record, "base", _scores(1.0))
    other = _run(run_dir, record, "other", _scores(1.0))
    header = json.loads((other / "run.json").read_text())
    header["suite"]["digest"] = "different"
    (other / "run.json").write_text(json.dumps(header))

    with pytest.raises(ValueError, match="not on one scale"):
        compare_paths(baseline, [other])

    result = compare_paths(baseline, [other], allow_mixed=True)
    assert result["_comparisons"][0].verdict == "identical"


def test_renderers_name_the_resolution_and_the_correction(run_dir, record):
    baseline = _run(run_dir, record, "base", _scores(1.0))
    weak = _run(run_dir, record, "weak", _scores(0.5))
    result = compare_paths(baseline, [weak])

    console = render_console(result)
    markdown = render_markdown(result)

    assert "resolution:" in console
    assert "10/12" in console  # the sign test's bar on a 12-task suite
    assert "Holm-adjusted" in console
    assert "| run | score | gap vs baseline | p (Holm) | verdict |" in markdown
    assert "Holm-adjusted over 1 comparison(s)." in markdown
