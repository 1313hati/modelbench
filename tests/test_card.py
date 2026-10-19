from __future__ import annotations

from modelbench.card import render_card, write_card
from modelbench.report import load_run


def test_card_carries_the_interval_and_the_digest(run_dir, record):
    records = [record(f"t{i:02d}", 1, 0.5 + i / 20) for i in range(1, 11)]
    run = load_run(run_dir("model-a", records))
    svg = render_card(run, title="Model A")
    assert svg.startswith("<svg")
    assert "Model A" in svg
    assert "95% CI" in svg
    assert "core-v2" in svg
    assert "abc123" in svg


def test_card_escapes_untrusted_labels(run_dir, record):
    run = load_run(run_dir("model-a", [record("t01", 1, 1.0)]))
    svg = render_card(run, title="<script>alert(1)</script>")
    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_single_sample_says_so(run_dir, record):
    run = load_run(run_dir("model-a", [record("t01", 1, 1.0)]))
    assert "single sample" in render_card(run)


def test_unpriced_run_does_not_show_a_price(run_dir, record):
    # A local model is not free, it is unpriced; printing $0 would read as a
    # measurement. The stat row is suppressed instead.
    run = load_run(run_dir("local", [record("t01", 1, 1.0), record("t02", 1, 1.0)]))
    assert "$" not in render_card(run)


def test_write_card_produces_a_file(tmp_path, run_dir, record):
    run = load_run(run_dir("model-a", [record("t01", 1, 1.0), record("t02", 1, 0.5)]))
    written = write_card(run, tmp_path / "card.svg")
    assert written["svg"].is_file()
    assert written["svg"].read_text(encoding="utf-8").startswith("<svg")
    assert written["png"] is None
