"""Command-line interface.

    modelbench list                 # suites and tasks
    modelbench doctor               # is the target reachable, are runtimes installed
    modelbench run --target local   # benchmark one model
    modelbench report runs/a runs/b # compare runs
    modelbench validate             # reference solutions must score 100%
    modelbench self-test            # end-to-end check with a mock model
    modelbench card RUN             # a shareable SVG scorecard
    modelbench leaderboard runs/*   # rank runs, with ties and a frontier
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from . import __version__
from .card import write_card
from .client import ChatClient, probe
from .config import Config, Generation, Target, find_config, target_from_cli
from .explain import failing_records, load as load_explain, render_index, render_record
from .errors import ModelBenchError, SuiteError, TaskError
from .grader import grade, runner_available
from .leaderboard import (
    load_and_build,
    render_console as render_leaderboard,
    render_json as leaderboard_json,
    render_markdown as render_leaderboard_markdown,
)
from .mockserver import start_mock
from .prompts import SINGLE_WRAPPER, REPAIR_PROMPT, build_prompt
from .report import (
    discover_runs,
    dump_json,
    load_run,
    load_runs,
    render_console,
    render_html,
    render_json,
    run_metrics,
    write_reports,
)
from .runner import RunPlan, Runner
from .tasks import PACKAGED_SUITES, Suite, available_suites, resolve_suite
from .util import column_table, human_duration, now_iso, pct


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #
def _config(args: argparse.Namespace, required: bool = False) -> Config | None:
    """Load the config if one exists; only fail when the command needs it."""
    path = find_config(getattr(args, "config", None))
    if path is None:
        if required and not getattr(args, "base_url", None):
            raise ModelBenchError(
                "no modelbench.toml found: copy modelbench.example.toml to modelbench.toml "
                "(or pass --config PATH, or give --base-url and --model)"
            )
        return None
    return Config.load(path)


def _suite(args: argparse.Namespace, config: Config | None) -> Suite:
    return resolve_suite(
        getattr(args, "suite", None),
        config.suite_paths if config else (),
        config.suite if config else None,
    )


def _target(args: argparse.Namespace, config: Config | None) -> Target:
    overrides = {}
    for field in ("temperature", "top_p", "top_k", "seed"):
        value = getattr(args, field, None)
        if value is not None:
            overrides[field] = value
    if getattr(args, "base_url", None):
        name = getattr(args, "target", None) or "adhoc"
        generation = (config.defaults if config else Generation()).merged(**overrides)
        return target_from_cli(
            name,
            args.base_url,
            args.model or "local",
            getattr(args, "api_key_env", None),
            generation,
        )
    if config is None:
        raise ModelBenchError(
            "no configuration found: pass --config PATH, or give --base-url and --model"
        )
    target = config.target(getattr(args, "target", None))
    if overrides:
        target.generation = target.generation.merged(**overrides)
    return target


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


# --------------------------------------------------------------------------- #
# list
# --------------------------------------------------------------------------- #
def cmd_list(args: argparse.Namespace) -> int:
    config = None
    try:
        config = Config.load(getattr(args, "config", None))
    except ModelBenchError:
        pass
    suites = available_suites(config.suite_paths if config else ())
    if config and config.suite:
        suites.sort(key=lambda s: (s.id != config.suite, s.id))
    if args.json:
        print(dump_json({"suites": [s.describe() for s in suites]}))
        return 0
    rows = [
        [s.id, s.version, s.name, str(len(s.tasks)), str(s.total_checks), s.root.as_posix()]
        for s in suites
    ]
    print(
        column_table(
            ["suite", "ver", "name", "tasks", "checks", "path"],
            rows,
            align=["l", "r", "l", "r", "r", "l"],
        )
    )
    print(f"\nbuilt-in suites: {', '.join(s.id for s in suites)}")
    if args.suite:
        suite = _suite(args, config)
        print(f"\n{suite.id} — {suite.name} ({len(suite.tasks)} tasks, {suite.total_checks} checks)")
        if suite.description:
            print(suite.description)
        print()
        rows = [
            [t.id, t.category, t.kind, t.lang, str(t.max_tokens), str(t.checks), t.title]
            for t in suite.tasks
        ]
        print(
            column_table(
                ["task", "category", "kind", "lang", "cap", "checks", "title"],
                rows,
                align=["l", "l", "l", "l", "r", "r", "l"],
            )
        )
    else:
        print("\nadd --suite <id> to list the tasks of one suite")
    return 0


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #
def validate_suite(suite: Suite, tasks=None, quiet: bool = False) -> list[dict]:
    results = []
    problems = suite.problems()
    if problems and not quiet:
        for problem in problems:
            print(f"  ! {problem}")
    selected = tasks or suite.tasks
    with tempfile.TemporaryDirectory(prefix="modelbench-ref-") as tmp:
        for task in selected:
            destination = Path(tmp) / task.id
            try:
                solution = task.prepare_ref(destination)
                graded = grade(task, solution)
            except (TaskError, ModelBenchError) as exc:
                results.append({"task": task.id, "ok": False, "message": str(exc), "passed": 0, "total": task.checks})
                if not quiet:
                    print(f"BAD {task.id:<26s} {exc}")
                continue
            ok = graded.solved and graded.total > 0
            results.append(
                {
                    "task": task.id,
                    "ok": ok,
                    "passed": graded.passed,
                    "total": graded.total,
                    "seconds": round(graded.seconds, 2),
                }
            )
            if not quiet:
                status = "OK " if ok else "BAD"
                print(f"{status} {task.id:<26s} {graded.passed:>3}/{graded.total:<3} {graded.seconds:5.1f}s")
                if not ok:
                    for failure in graded.failures[:6]:
                        print(f"    {failure}")
    return results


def cmd_validate(args: argparse.Namespace) -> int:
    config = _config(args)
    suite = _suite(args, config)
    tasks = suite.select(args.only_list, args.exclude_list) if (args.only_list or args.exclude_list) else suite.tasks
    print(f"validating {len(tasks)} task(s) in {suite.id} against their reference solutions\n")
    results = validate_suite(suite, tasks)
    bad = [r for r in results if not r["ok"]]
    total = sum(r["total"] for r in results)
    passed = sum(r["passed"] for r in results)
    print(f"\n{len(results) - len(bad)}/{len(results)} tasks perfect, {passed}/{total} assertions")
    if bad:
        print("FAILED: " + ", ".join(r["task"] for r in bad))
        return 1
    print("all reference solutions pass")
    return 0


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def _print_plan(suite: Suite, plan: RunPlan, out: Path) -> None:
    """Describe a run without contacting the endpoint."""
    tasks = suite.select(plan.only, plan.exclude)
    rows, chars, ceiling = [], 0, 0
    for task in tasks:
        prompt = build_prompt(task, suite.prompt_text)
        chars += len(prompt)
        cap = plan.max_tokens or task.max_tokens
        ceiling += cap * plan.samples
        rows.append([task.id, task.category, f"{cap:,}", f"{len(prompt):,}", task.runner])
    print(column_table(["task", "category", "cap", "prompt chars", "grader"], rows, align=["l", "l", "r", "r", "l"]))
    calls = len(tasks) * plan.samples
    repair_note = f", up to {calls * 2} with repair turns" if plan.repair else ""
    print(f"\n{len(tasks)} task(s) × {plan.samples} sample(s) = {calls} first call(s){repair_note}")
    print(f"prompt text   {chars:,} chars total (~{chars / 4:,.0f} input tokens at 4 chars/token)")
    print(f"output ceiling {ceiling:,} completion tokens before repairs and cap retries")
    print(f"suite digest  {suite.digest()[:12]} · nothing was sent to the endpoint")
    print(f"would write   {out}")


def cmd_run(args: argparse.Namespace) -> int:
    config = _config(args, required=True)
    suite = _suite(args, config)
    target = _target(args, config)
    overrides = {
        "temperature": args.temperature,
        "top_p": args.top_p,
        "top_k": args.top_k,
        "seed": args.seed,
    }
    if any(value is not None for value in overrides.values()):
        target.generation = target.generation.merged(**overrides)
    if getattr(args, "no_seed", False):
        # Measuring an endpoint as it behaves unpinned; the report will say so.
        target.generation = replace(target.generation, seed=None)

    label = args.name or target.name
    out = Path(args.out).expanduser() if args.out else Path("runs") / f"{label}-{suite.id}-{_stamp()}"
    plan = RunPlan(
        suite=suite,
        target=target,
        out_dir=out,
        samples=args.samples or (config.samples if config else 2),
        repair=not args.no_repair and (config.repair if config else True),
        only=args.only_list,
        exclude=args.exclude_list,
        max_tokens=args.max_tokens,
        retry_cap=args.retry_cap,
        resume=args.resume,
        warmup=not args.no_warmup,
        order=args.order,
        fail_fast=args.fail_fast,
        quiet=args.quiet,
        allow_missing_runners=args.allow_missing_runners,
    )
    if target.start_cmd and not args.no_manage_server:
        plan.manage_server = True

    print(f"suite    {suite.id} ({len(suite.tasks)} tasks, {suite.total_checks} checks, digest {suite.digest()[:12]})")
    print(f"target   {target.name} @ {target.base_url} model={target.model}")
    gen = target.generation
    sampling = " ".join(
        f"{key}={value}"
        for key, value in (("temp", gen.temperature), ("top_p", gen.top_p), ("top_k", gen.top_k))
        if value is not None
    )
    if gen.seed is None:
        sampling += "  seed=not pinned (reproducibility depends on the backend)"
    elif plan.samples > 1:
        sampling += f"  seed={gen.seed} (+1 per sample)"
    else:
        sampling += f"  seed={gen.seed}"
    print(f"samples  {plan.samples}   repair={plan.repair}   order={plan.order}   {sampling}")
    print(f"output   {out}\n")

    if args.dry_run:
        _print_plan(suite, plan, out)
        return 0

    try:
        outcome = Runner(plan).execute()
    except KeyboardInterrupt:
        return 130

    if not outcome.records:
        print("error: no records were produced", file=sys.stderr)
        return 1

    run = load_run(out)
    print()
    print(render_console([run]))
    if not args.no_report:
        title = args.title or f"modelbench — {label} on {suite.id}"
        paths = write_reports(
            [run], out, title=title, notes=args.notes, html=not args.no_html
        )
        print(f"\nreport   {paths['markdown']}")
        print(f"summary  {paths['json']}")
        if paths["html"]:
            print(f"html     {paths['html']}")
    if args.html:
        custom = Path(args.html).expanduser()
        custom.parent.mkdir(parents=True, exist_ok=True)
        custom.write_text(
            render_html([run], title=args.title or f"modelbench — {label} on {suite.id}", notes=args.notes),
            encoding="utf-8",
        )
        print(f"html     {custom}")
    if outcome.errors:
        print(f"\nwarning: {outcome.errors} task(s) failed and were not recorded; see {out / 'errors.log'}")
        return 1
    if args.fail_under is not None:
        bar = args.fail_under / 100.0 if args.fail_under > 1 else args.fail_under
        score = run_metrics(run)["final_score"]
        passed = score >= bar
        print(
            f"gate     final mean task score {pct(score)} "
            f"{'>=' if passed else '<'} {pct(bar)}  {'pass' if passed else 'FAIL'}"
        )
        if not passed:
            return 1
    return 0


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _strict_exit(runs: list) -> int:
    """Exit 1 when a run is incomplete, duplicated or carries errors (CI mode)."""
    issues: list[str] = []
    for run in runs:
        m = run_metrics(run)
        if m["missing"]:
            issues.append(f"{run.label}: {len(m['missing'])} missing record(s)")
        if m["duplicates"]:
            issues.append(f"{run.label}: {len(m['duplicates'])} duplicated record(s)")
        if m["errors"]:
            issues.append(f"{run.label}: {m['errors']} record(s) with run errors")
    if not issues:
        return 0
    print("\nstrict: " + "; ".join(issues), file=sys.stderr)
    return 1


def cmd_report(args: argparse.Namespace) -> int:
    paths: list[Path] = []
    for entry in args.paths:
        candidate = Path(entry).expanduser()
        if candidate.is_dir() and not (candidate / "results.jsonl").is_file():
            found = discover_runs(candidate)
            if found:
                paths.extend(found)
                continue
        paths.append(candidate)
    if not paths:
        print("error: no run directories found", file=sys.stderr)
        return 2
    runs = load_runs(paths)
    print(render_console(runs, require_samples=args.require_samples))
    notes = args.notes
    if args.notes_file:
        notes = Path(args.notes_file).read_text(encoding="utf-8")
    out = Path(args.out) if args.out else (paths[0] if len(paths) == 1 else Path("reports"))
    if args.json:
        print(dump_json(render_json(runs, title=args.title, require_samples=args.require_samples)))
        return _strict_exit(runs) if args.strict else 0
    paths_written = write_reports(
        runs,
        out,
        title=args.title,
        notes=notes,
        html=not args.no_html,
        require_samples=args.require_samples,
    )
    print(f"\nreport   {paths_written['markdown']}")
    print(f"summary  {paths_written['json']}")
    if paths_written["html"]:
        print(f"html     {paths_written['html']}")
    if args.html:
        custom = Path(args.html).expanduser()
        custom.parent.mkdir(parents=True, exist_ok=True)
        custom.write_text(render_html(runs, title=args.title, notes=notes), encoding="utf-8")
        print(f"html     {custom}")
    return _strict_exit(runs) if args.strict else 0


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #
def cmd_doctor(args: argparse.Namespace) -> int:
    checks: list[tuple[bool, str, str]] = []

    def record(ok: bool, name: str, detail: str) -> None:
        checks.append((ok, name, detail))

    config_path = find_config(args.config)
    config = None
    if config_path:
        try:
            config = Config.load(config_path)
        except ModelBenchError as exc:
            record(False, "config", str(exc))
        else:
            record(True, "config", f"{config_path} ({len(config.targets)} target(s))")
            for warning in config.warnings:
                record(False, "config warning", warning)
    elif args.base_url:
        record(True, "config", "none (using --base-url)")
    else:
        record(False, "config", "no modelbench.toml found")

    suite = None
    try:
        suite = _suite(args, config)
    except ModelBenchError as exc:
        record(False, "suite", str(exc))
    else:
        problems = suite.problems()
        record(
            not problems,
            "suite",
            f"{suite.id} v{suite.version}: {len(suite.tasks)} tasks, {suite.total_checks} checks, "
            f"digest {suite.digest()[:12]}",
        )
        for problem in problems[:10]:
            record(False, "task", problem)
        needed = sorted({t.runner for t in suite.tasks})
        for runner in needed:
            record(runner_available(runner), "runtime", f"{runner}: {'found' if runner_available(runner) else 'MISSING'}")

    target = None
    try:
        target = _target(args, config)
    except ModelBenchError as exc:
        record(False, "target", str(exc))
    else:
        record(True, "target", f"{target.name} @ {target.base_url} model={target.model}")
        client = ChatClient(target)
        try:
            models = client.list_models()
        except Exception as exc:  # noqa: BLE001
            record(False, "endpoint", f"{target.base_url}: {type(exc).__name__}: {exc}")
        else:
            record(True, "endpoint", f"/v1/models → {', '.join(models[:4]) or '(empty)'}")
            health = client.health()
            record(True, "health", "ok" if health else "no /health route (fine for hosted APIs)")

    if args.probe and target is not None:
        try:
            info = probe(target)
        except Exception as exc:  # noqa: BLE001
            record(False, "probe", f"{type(exc).__name__}: {exc}")
        else:
            record(
                bool(info["reply"]),
                "probe",
                f"{info['total_s']:.2f}s total, {info['ttft_s']:.2f}s TTFT, "
                f"{info['tok_per_s'] or 0:.1f} tok/s, finish={info['finish_reason']}",
            )

    print()
    for ok, name, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<14s} {detail}")
    failed = sum(1 for ok, _, _ in checks if not ok)
    print(f"\n{'ready to benchmark' if not failed else f'{failed} check(s) failed'}")
    return 0 if not failed else 1


# --------------------------------------------------------------------------- #
# card
# --------------------------------------------------------------------------- #
def cmd_card(args: argparse.Namespace) -> int:
    run = load_run(args.run)
    out = Path(args.out).expanduser() if args.out else run.path / "CARD.svg"
    png: Path | None = None
    if args.png is not None:
        png = Path(args.png).expanduser() if args.png else out.with_suffix(".png")
    try:
        written = write_card(
            run,
            out,
            title=args.title,
            subtitle=args.subtitle,
            footer=args.footer,
            png=png,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"card     {written['svg']}")
    if written["png"]:
        print(f"png      {written['png']}")
    if not args.title:
        print(
            f"\nthe label on the card is the run's target name ({run.label!r}); "
            "use --title to put the model's real name on it"
        )
    return 0


# --------------------------------------------------------------------------- #
# leaderboard
# --------------------------------------------------------------------------- #
def cmd_leaderboard(args: argparse.Namespace) -> int:
    paths: list[Path] = []
    for entry in args.paths:
        candidate = Path(entry).expanduser()
        if candidate.is_dir() and not (candidate / "results.jsonl").is_file():
            found = discover_runs(candidate)
            if found:
                paths.extend(found)
                continue
        paths.append(candidate)
    if not paths:
        print("error: no run directories found", file=sys.stderr)
        return 2
    payload = load_and_build(paths, by=args.by, allow_mixed=args.allow_mixed)
    print(render_leaderboard(payload))
    if args.json:
        print(dump_json(leaderboard_json(payload)))
        return 0
    out = Path(args.out).expanduser() if args.out else Path("reports")
    out.mkdir(parents=True, exist_ok=True)
    path = out / "LEADERBOARD.md"
    path.write_text(render_leaderboard_markdown(payload), encoding="utf-8")
    print(f"\nleaderboard {path}")
    return 0


# --------------------------------------------------------------------------- #
# mock
# --------------------------------------------------------------------------- #
def cmd_inspect(args: argparse.Namespace) -> int:
    run = load_explain(args.run)
    if not args.task:
        print(render_index(run))
        return 0
    record = next(
        (r for r in run.records if r.get("task") == args.task
         and (args.sample is None or int(r.get("sample") or 1) == args.sample)),
        None,
    )
    if record is None:
        from .errors import ModelBenchError

        raise ModelBenchError(
            f"{run.path}: no record for task {args.task!r}"
            + (f" sample {args.sample}" if args.sample else "")
        )
    if args.json:
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0
    print(
        render_record(
            run,
            record,
            suite_spec=args.suite,
            context=args.context,
            full=args.full,
        )
    )
    return 0


def cmd_mock(args: argparse.Namespace) -> int:
    config = None
    try:
        config = Config.load(args.config)
    except ModelBenchError:
        pass
    suite = _suite(args, config)
    handle = start_mock(suite, mode=args.mode, delay=args.delay, reasoning=not args.no_reasoning, port=args.port)
    print(f"mock server ({args.mode}) on {handle.base_url}")
    print(f"suite {suite.id}: {len(suite.tasks)} tasks")
    print("try: modelbench run --base-url " + handle.base_url + " --model mock --suite " + suite.id)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nstopping")
    finally:
        handle.close()
    return 0


# --------------------------------------------------------------------------- #
# self-test
# --------------------------------------------------------------------------- #
def cmd_self_test(args: argparse.Namespace) -> int:
    suite = _suite(args, None)
    print(f"self-test: suite {suite.id} ({len(suite.tasks)} tasks)")
    failures: list[str] = []

    print("\n1. reference solutions")
    ref_results = validate_suite(suite, quiet=False)
    bad = [r for r in ref_results if not r["ok"]]
    if bad:
        failures.append(f"{len(bad)} reference solution(s) below 100%")
    else:
        print(f"   {len(ref_results)}/{len(ref_results)} references perfect")

    workdir = Path(tempfile.mkdtemp(prefix="modelbench-selftest-"))
    try:
        print("\n2. mock model, full suite")
        with start_mock(suite, mode="ref") as mock:
            target = Target(name="mock", base_url=mock.base_url, model="mock-model", generation=Generation(temperature=0.0))
            plan = RunPlan(
                suite=suite,
                target=target,
                out_dir=workdir / "run",
                samples=args.samples,
                repair=True,
                quiet=True,
            )
            outcome = Runner(plan, on_progress=lambda line: None).execute()
        run = load_run(workdir / "run")
        expected = len(suite.tasks) * args.samples
        checks = [
            (len(outcome.records) == expected, f"produced {len(outcome.records)}/{expected} records"),
            (outcome.errors == 0, f"{outcome.errors} task error(s)"),
            (
                all(r["first"]["score"] == 1.0 for r in outcome.records),
                "every reference answer scored 100% on the first attempt",
            ),
        ]
        for ok, message in checks:
            print(f"   {'ok  ' if ok else 'FAIL'} {message}")
            if not ok:
                failures.append(message)
        paths = write_reports([run], workdir / "run", title="self-test")
        md_path, json_path = paths["markdown"], paths["json"]
        if not md_path.is_file() or "## Headline" not in md_path.read_text(encoding="utf-8"):
            failures.append("report was not generated correctly")
        html_path = paths["html"]
        if html_path is None or "At a glance" not in html_path.read_text(encoding="utf-8"):
            failures.append("HTML report was not generated correctly")
        print(
            f"   ok   report + summary + html written "
            f"({md_path.name}, {json_path.name}, {html_path.name if html_path else '—'})"
        )

        print("\n3. failure paths")
        first = suite.tasks[0]
        with start_mock(suite, mode="truncate") as mock:
            target = Target(name="truncate", base_url=mock.base_url, model="mock-model")
            plan = RunPlan(
                suite=suite,
                target=target,
                out_dir=workdir / "truncate",
                samples=1,
                repair=False,
                only=[first.id],
                quiet=True,
            )
            Runner(plan, on_progress=lambda line: None).execute()
        record = load_run(workdir / "truncate").records[0]
        ok = bool(record["first"].get("retried_after_length"))
        print(f"   {'ok  ' if ok else 'FAIL'} token-cap retry was triggered and recorded")
        if not ok:
            failures.append("cap retry was not recorded")

        with start_mock(suite, mode="garbage") as mock:
            target = Target(name="garbage", base_url=mock.base_url, model="mock-model")
            plan = RunPlan(
                suite=suite,
                target=target,
                out_dir=workdir / "garbage",
                samples=1,
                repair=True,
                only=[first.id],
                quiet=True,
            )
            Runner(plan, on_progress=lambda line: None).execute()
        record = load_run(workdir / "garbage").records[0]
        ok = record.get("repair") is not None and record["final_score"] < 1.0
        print(f"   {'ok  ' if ok else 'FAIL'} failed answer triggered a repair turn, still scored below 100%")
        if not ok:
            failures.append("repair turn did not run on a failing answer")
    finally:
        if args.keep:
            print(f"\nartefacts kept in {workdir}")
        else:
            shutil.rmtree(workdir, ignore_errors=True)

    print()
    if failures:
        print(f"SELF-TEST FAILED ({len(failures)} problem(s))")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("SELF-TEST PASSED")
    return 0


# --------------------------------------------------------------------------- #
# init-suite
# --------------------------------------------------------------------------- #
SUITE_MANIFEST = """id = "{id}"
name = "{name}"
version = "0.1"
description = "A custom suite."
"""

EXAMPLE_TASK = """# {id}: is_even

Write `is_even(n)` in Python. It returns `True` when `n` is even and `False`
otherwise. `n` is an integer and may be negative.

Return the complete file. Standard library only.
"""

EXAMPLE_TEST = '''from __future__ import annotations

import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))
from harness import Checks, solution_arg  # noqa: E402

C = Checks()
path = solution_arg()

spec = importlib.util.spec_from_file_location("solution", path)
mod = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(mod)
    fn = mod.is_even
except Exception as exc:  # noqa: BLE001
    C.check("solution imports and defines is_even", lambda: (_ for _ in ()).throw(exc))
    C.report()

for value, expected in [(0, True), (2, True), (-4, True), (1, False), (-3, False), (10**18, True)]:
    C.eq(f"is_even({value})", fn(value), expected)

C.report()
'''

EXAMPLE_META = """{{
  "id": "{id}",
  "category": "example",
  "kind": "file",
  "lang": "py",
  "max_tokens": 1024,
  "timeout": 60,
  "checks": 7
}}
"""

EXAMPLE_REF = """def is_even(n):
    return n % 2 == 0
"""


def cmd_init_suite(args: argparse.Namespace) -> int:
    suite_id = args.name
    root = Path(args.dir or suite_id).expanduser()
    if root.exists() and any(root.iterdir()):
        print(f"error: {root} already exists and is not empty", file=sys.stderr)
        return 2
    task_dir = root / "tasks" / "example_is_even"
    (task_dir / "tests").mkdir(parents=True)
    (task_dir / "ref").mkdir()
    (root / "suite.toml").write_text(SUITE_MANIFEST.format(id=suite_id, name=suite_id.replace("-", " ").title()), encoding="utf-8")
    (task_dir / "task.md").write_text(EXAMPLE_TASK.format(id=suite_id), encoding="utf-8")
    (task_dir / "meta.json").write_text(EXAMPLE_META.format(id="example_is_even"), encoding="utf-8")
    (task_dir / "tests" / "test_is_even.py").write_text(EXAMPLE_TEST, encoding="utf-8")
    (task_dir / "ref" / "is_even.py").write_text(EXAMPLE_REF, encoding="utf-8")
    print(f"created suite {suite_id} in {root}")
    print(f"  tasks/example_is_even/  (task.md, meta.json, tests/, ref/)")
    print(f"\nvalidate it:  modelbench validate --suite {root}")
    print(f"run it:       modelbench run --suite {root} --samples 1 --target <name>")
    return 0


# --------------------------------------------------------------------------- #
# parser
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modelbench",
        description="A reproducible coding benchmark for any OpenAI-compatible model endpoint.",
        epilog="built-in suites: "
        + ", ".join(sorted(p.name for p in PACKAGED_SUITES.iterdir() if (p / "suite.toml").is_file())),
    )
    parser.add_argument("--version", action="version", version=f"modelbench {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--config", help="path to modelbench.toml")
        sp.add_argument("--suite", help="suite id or directory (default: core-v2)")
        sp.add_argument("--quiet", action="store_true", help="suppress progress output")

    p = sub.add_parser("list", help="list suites and tasks")
    add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("validate", help="check that every reference solution passes every assertion")
    add_common(p)
    p.add_argument("--only", default=None, help="comma separated task ids")
    p.add_argument("--exclude", default=None, help="comma separated task ids")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("run", help="benchmark a target")
    add_common(p)
    p.add_argument("--target", help="target name from modelbench.toml")
    p.add_argument("--base-url", help="ad-hoc endpoint, e.g. http://127.0.0.1:8080/v1")
    p.add_argument("--model", help="model id for --base-url / to override the target")
    p.add_argument("--api-key-env", help="environment variable holding the API key")
    p.add_argument("--name", help="label for this run (default: target name)")
    p.add_argument("--out", help="output directory (default: runs/<label>-<suite>-<timestamp>)")
    p.add_argument("--samples", type=int, help="independent samples per task")
    p.add_argument("--only", dest="only", default=None, help="comma separated task ids")
    p.add_argument("--exclude", dest="exclude", default=None, help="comma separated task ids")
    p.add_argument("--max-tokens", type=int, default=None, help="override every task's token cap")
    p.add_argument("--retry-cap", type=int, default=None, help="token cap for the retry after a length finish")
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--top-p", type=float, default=None)
    p.add_argument("--top-k", type=int, default=None)
    p.add_argument("--seed", type=int, default=None, help="base sampler seed; sample n uses seed+n-1")
    p.add_argument(
        "--no-seed",
        action="store_true",
        help="do not send a seed at all (measures an unpinned endpoint; not reproducible)",
    )
    p.add_argument("--no-repair", action="store_true", help="do not offer the feedback turn")
    p.add_argument("--resume", action="store_true", help="skip task/sample pairs already recorded")
    p.add_argument("--no-warmup", action="store_true", help="skip the warm-up request")
    p.add_argument("--order", choices=["sample", "task"], default="sample", help="loop nesting")
    p.add_argument("--fail-fast", action="store_true", help="stop on the first task error")
    p.add_argument("--allow-missing-runners", action="store_true", help="drop tasks whose runtime is missing")
    p.add_argument("--no-manage-server", action="store_true", help="ignore start_cmd/stop_cmd in the config")
    p.add_argument("--no-report", action="store_true", help="do not write REPORT.md after the run")
    p.add_argument("--no-html", action="store_true", help="do not write REPORT.html next to REPORT.md")
    p.add_argument("--html", default=None, help="also write the HTML report to this path")
    p.add_argument("--dry-run", action="store_true", help="print the plan and exit without calling the endpoint")
    p.add_argument(
        "--fail-under",
        type=float,
        default=None,
        metavar="SCORE",
        help="exit 1 if the mean final task score is below SCORE (0-1 or a percentage)",
    )
    p.add_argument("--title", help="report title")
    p.add_argument("--notes", help="free-text notes appended to the report")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("report", help="aggregate one or more runs into a report")
    p.add_argument("paths", nargs="+", help="run directories (or a directory containing runs)")
    p.add_argument("--out", help="where to write REPORT.md + summary.json + REPORT.html")
    p.add_argument("--title", default=None)
    p.add_argument("--notes", default=None)
    p.add_argument("--notes-file", default=None)
    p.add_argument("--no-html", action="store_true", help="skip the standalone HTML report")
    p.add_argument("--html", default=None, help="also write the HTML report to this path")
    p.add_argument("--strict", action="store_true", help="exit 1 if a run has missing, duplicated or failed records")
    p.add_argument(
        "--require-samples",
        type=int,
        default=3,
        metavar="N",
        help="samples per task needed before the report names a winner (default 3; 0 disables)",
    )
    p.add_argument("--json", action="store_true", help="print the summary JSON instead of writing files")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("doctor", help="check config, suite, runtimes and endpoint")
    add_common(p)
    p.add_argument("--target")
    p.add_argument("--base-url")
    p.add_argument("--model")
    p.add_argument("--api-key-env")
    p.add_argument("--no-probe", dest="probe", action="store_false", default=True)
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("card", help="render a run as a shareable SVG/PNG scorecard")
    p.add_argument("run", help="run directory (the one holding results.jsonl)")
    p.add_argument("--out", default=None, help="SVG path (default: <run>/CARD.svg)")
    p.add_argument(
        "--png",
        nargs="?",
        const="",
        default=None,
        help="also write a PNG (default: beside the SVG); needs rsvg-convert",
    )
    p.add_argument("--title", default=None, help="label on the card (default: the run's target name)")
    p.add_argument("--subtitle", default=None)
    p.add_argument("--footer", default=None, help="override the provenance footer")
    p.set_defaults(func=cmd_card)

    p = sub.add_parser("leaderboard", help="rank several runs; overlapping intervals share a place")
    p.add_argument("paths", nargs="+", help="run directories (or directories holding runs)")
    p.add_argument("--by", choices=["first", "final"], default="first", help="which score to rank")
    p.add_argument("--out", default=None, help="where LEADERBOARD.md goes (default: reports/)")
    p.add_argument(
        "--allow-mixed",
        action="store_true",
        help="rank runs from different suites or suite versions anyway (adds a warning)",
    )
    p.add_argument("--json", action="store_true", help="print the ranking as JSON")
    p.set_defaults(func=cmd_leaderboard)

    p = sub.add_parser("mock", help="serve reference answers from a fake OpenAI endpoint")
    add_common(p)
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--mode", choices=["ref", "truncate", "garbage"], default="ref")
    p.add_argument("--delay", type=float, default=0.0, help="seconds between stream chunks")
    p.add_argument("--no-reasoning", action="store_true")
    p.set_defaults(func=cmd_mock)

    p = sub.add_parser("self-test", help="end-to-end check with a mock model (no GPU needed)")
    p.add_argument("--config", default=None)
    p.add_argument("--suite", default=None)
    p.add_argument("--samples", type=int, default=1)
    p.add_argument("--keep", action="store_true", help="keep the temporary run directory")
    p.add_argument("--quiet", action="store_true")
    p.set_defaults(func=cmd_self_test)

    p = sub.add_parser("inspect", help="show what the model wrote for one record, and why it failed")
    p.add_argument("run", help="run directory (the one holding results.jsonl)")
    p.add_argument("--task", help="task id; omit to list every record that lost points")
    p.add_argument("--sample", type=int, default=None, help="sample number (default: the first)")
    p.add_argument("--suite", default=None, help="suite path or id to diff against (default: the run's own suite)")
    p.add_argument("--context", type=int, default=3, help="diff context lines")
    p.add_argument("--full", action="store_true", help="print the whole answer, not the first 120 lines")
    p.add_argument("--json", action="store_true", help="print the raw record as JSON")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("init-suite", help="scaffold a new suite with one example task")
    p.add_argument("name")
    p.add_argument("--dir", default=None)
    p.set_defaults(func=cmd_init_suite)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Normalise comma-separated task lists.
    for attr in ("only", "exclude"):
        value = getattr(args, attr, None)
        if isinstance(value, str):
            setattr(args, f"{attr}_list", [p.strip() for p in value.split(",") if p.strip()])
        else:
            setattr(args, f"{attr}_list", [])
    try:
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        return 130
    except ModelBenchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
