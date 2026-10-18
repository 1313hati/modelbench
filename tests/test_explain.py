from __future__ import annotations

import email.message
import json
import urllib.error

from modelbench.client import _retry_after
from modelbench.explain import failing_records, load, render_index, render_record


def test_index_lists_records_that_lost_points(run_dir, record):
    path = run_dir(
        "r",
        [
            record(task="good", sample=1, score=1.0, solved=True),
            record(task="bad", sample=1, score=0.5, failures=["FAIL adds: expected 3, got 4"]),
        ],
    )
    run = load(path)
    assert [r["task"] for r in failing_records(run)] == ["bad"]
    index = render_index(run)
    assert "1 to look at" in index
    assert "expected 3, got 4" in index


def test_record_view_diffs_against_the_reference(run_dir, record, tmp_path):
    path = run_dir(
        "r",
        [record(task="t01", sample=1, score=0.5, failures=["FAIL f: wrong"])],
    )
    sol = path / "s1" / "sol" / "t01.solution.py"
    sol.parent.mkdir(parents=True)
    sol.write_text("def f():\n    return 1\n")
    run = load(path)
    text = render_record(run, run.records[0])
    assert "what the model wrote" in text
    assert "failing assertions" in text
    assert "FAIL f: wrong" in text
    # core-v2 in conftest is not a real suite, so the reference is unavailable;
    # the view must say so rather than invent a diff.
    assert "reference unavailable" in text


def test_no_result_line_is_not_called_an_assertion(run_dir, record):
    path = run_dir(
        "r",
        [record(task="t01", sample=1, score=0.0, failures=["Traceback (most recent call last):"])],
    )
    run = load(path)
    run.records[0]["first"]["no_result_line"] = True
    text = render_record(run, run.records[0])
    assert "never reached a RESULT line" in text
    assert "failing assertions" not in text


def test_identical_answer_says_so(run_dir, record):
    path = run_dir("r", [record(task="t01", sample=1, score=0.5)])
    run = load(path)
    record_row = run.records[0]
    sol = path / "s1" / "sol" / "t01.solution.py"
    sol.parent.mkdir(parents=True)
    sol.write_text("x = 1\n")
    from modelbench import explain

    expected, _ = explain.ref_text(run, "t01", None)
    assert expected is None  # unknown suite in the fixture
    assert "reference unavailable" in render_record(run, record_row)


def _http_error(code: int, retry_after: str | None) -> urllib.error.HTTPError:
    headers = email.message.Message()
    if retry_after is not None:
        headers["retry-after"] = retry_after
    return urllib.error.HTTPError("http://x/v1/chat/completions", code, "err", headers, None)


def test_retry_after_is_honoured():
    assert _retry_after(_http_error(429, "7")) == 7
    assert _retry_after(_http_error(503, "0.5")) == 0.5


def test_retry_after_ignores_junk_and_silly_values():
    assert _retry_after(_http_error(429, None)) is None
    assert _retry_after(_http_error(429, "Wed, 21 Oct 2026 07:28:00 GMT")) is None
    assert _retry_after(_http_error(429, "9999")) is None
    assert _retry_after(_http_error(429, "-3")) is None
