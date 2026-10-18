from __future__ import annotations

from pathlib import Path

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
    assert "model-a" in capsys.readouterr().out


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
