from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from modelbench import cli
from modelbench.cli import build_parser, main


def test_parser_exposes_the_documented_commands():
    parser = build_parser()
    actions = [a for a in parser._actions if getattr(a, "choices", None)]
    commands = set()
    for action in actions:
        commands.update(action.choices)
    assert {
        "list",
        "validate",
        "run",
        "report",
        "doctor",
        "mock",
        "self-test",
        "init-suite",
    } <= commands


def test_list_prints_both_bundled_suites(capsys):
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "core-v1" in out and "core-v2" in out


def test_list_suite_details(capsys):
    assert main(["list", "--suite", "core-v2"]) == 0
    out = capsys.readouterr().out
    assert "t03_json_parser" in out
    assert "296" in out


def test_validate_bundled_suites():
    assert main(["validate", "--suite", "core-v1"]) == 0


def test_init_suite_then_validate(tmp_path: Path, capsys):
    target = tmp_path / "my-suite"
    assert main(["init-suite", "my-suite", "--dir", str(target)]) == 0
    assert (target / "tasks" / "example_is_even" / "tests" / "test_is_even.py").is_file()
    assert main(["validate", "--suite", str(target)]) == 0
    out = capsys.readouterr().out
    assert "all reference solutions pass" in out


def test_report_command_writes_files(tmp_path: Path, run_dir, record, capsys):
    run = run_dir("model-a", [record("a", 1, 1.0)])
    out = tmp_path / "report"
    assert main(["report", str(run), "--out", str(out)]) == 0
    assert (out / "REPORT.md").is_file()
    assert (out / "summary.json").is_file()
    assert (out / "REPORT.html").is_file()
    assert "model-a" in capsys.readouterr().out


def test_report_no_html_skips_the_page(tmp_path: Path, run_dir, record):
    run = run_dir("model-a", [record("a", 1, 1.0)])
    out = tmp_path / "report"
    assert main(["report", str(run), "--out", str(out), "--no-html"]) == 0
    assert (out / "REPORT.md").is_file()
    assert not (out / "REPORT.html").exists()


def test_report_html_accepts_a_custom_path(tmp_path: Path, run_dir, record):
    run = run_dir("model-a", [record("a", 1, 1.0)])
    page = tmp_path / "site" / "bench.html"
    assert main(["report", str(run), "--out", str(tmp_path / "r"), "--html", str(page)]) == 0
    assert page.is_file() and "At a glance" in page.read_text(encoding="utf-8")


def test_report_strict_exits_nonzero_on_missing_records(tmp_path: Path, run_dir, record, capsys):
    run = run_dir("model-a", [record("a", 1, 1.0)], tasks=["a", "b"])
    assert main(["report", str(run), "--out", str(tmp_path / "r"), "--strict"]) == 1
    assert "strict:" in capsys.readouterr().err
    complete = run_dir("model-b", [record("a", 1, 1.0)], tasks=["a"])
    assert main(["report", str(complete), "--out", str(tmp_path / "r2"), "--strict"]) == 0


CONFIG = """
[targets.local]
base_url = "http://127.0.0.1:9/v1"
model = "some-model"
"""


def test_run_dry_run_prints_the_plan_without_touching_the_endpoint(tmp_path: Path, monkeypatch, capsys):
    config = tmp_path / "modelbench.toml"
    config.write_text(CONFIG, encoding="utf-8")
    out = tmp_path / "run"
    code = main(
        [
            "run",
            "--config",
            str(config),
            "--target",
            "local",
            "--dry-run",
            "--samples",
            "2",
            "--only",
            "t01_weighted_jobs",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "nothing was sent to the endpoint" in printed
    assert "t01_weighted_jobs" in printed
    assert "2 first call(s), up to 4 with repair turns" in printed
    assert not out.exists()


def test_run_dry_run_shows_sampling_overrides(tmp_path: Path, capsys):
    config = tmp_path / "modelbench.toml"
    config.write_text(CONFIG, encoding="utf-8")
    code = main(
        [
            "run",
            "--config",
            str(config),
            "--target",
            "local",
            "--dry-run",
            "--only",
            "t01_weighted_jobs",
            "--temperature",
            "0.2",
            "--top-p",
            "0.5",
            "--top-k",
            "5",
            "--seed",
            "7",
            "--out",
            str(tmp_path / "run"),
        ]
    )
    assert code == 0
    printed = capsys.readouterr().out
    for expected in ("temp=0.2", "top_p=0.5", "top_k=5", "seed=7"):
        assert expected in printed, expected


def test_run_without_config_fails_cleanly(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODELBENCH_CONFIG", raising=False)
    assert main(["run", "--target", "local"]) == 2
    assert "no modelbench.toml" in capsys.readouterr().err


def test_doctor_without_config_reports_failure(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODELBENCH_CONFIG", raising=False)
    assert main(["doctor", "--no-probe"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out


def _fake_runner(score: float, write):
    """A Runner stand-in that records a run instead of calling an endpoint."""

    class Fake:
        def __init__(self, plan):
            self.plan = plan

        def execute(self):
            write(Path(self.plan.out_dir), score)
            return SimpleNamespace(records=[{"task": "t01_weighted_jobs"}], errors=0)

    return Fake


def test_fail_under_gate_exits_nonzero_on_a_low_score(tmp_path: Path, monkeypatch, capsys, record):
    config = tmp_path / "modelbench.toml"
    config.write_text(CONFIG, encoding="utf-8")
    out = tmp_path / "run"

    def write(directory: Path, score: float) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        rows = [record("t01_weighted_jobs", 1, score, score >= 1.0)]
        (directory / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (directory / "run.json").write_text(
            json.dumps({"modelbench": "1.4.0", "target": {"name": "local"}, "suite": {"id": "core-v2"}})
        )

    monkeypatch.setattr(cli, "Runner", _fake_runner(0.5, write))
    code = main(
        ["run", "--config", str(config), "--target", "local", "--only", "t01_weighted_jobs",
         "--no-report", "--out", str(out), "--fail-under", "0.9"]
    )
    assert code == 1
    assert "FAIL" in capsys.readouterr().out


def test_fail_under_gate_passes_above_the_bar(tmp_path: Path, monkeypatch, capsys, record):
    config = tmp_path / "modelbench.toml"
    config.write_text(CONFIG, encoding="utf-8")

    def write(directory: Path, score: float) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        rows = [record("t01_weighted_jobs", 1, score, score >= 1.0)]
        (directory / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        (directory / "run.json").write_text(
            json.dumps({"modelbench": "1.4.0", "target": {"name": "local"}, "suite": {"id": "core-v2"}})
        )

    monkeypatch.setattr(cli, "Runner", _fake_runner(1.0, write))
    code = main(
        ["run", "--config", str(config), "--target", "local", "--only", "t01_weighted_jobs",
         "--no-report", "--out", str(tmp_path / "run2"), "--fail-under", "90"]
    )
    assert code == 0
    printed = capsys.readouterr().out
    assert "gate" in printed and "pass" in printed
