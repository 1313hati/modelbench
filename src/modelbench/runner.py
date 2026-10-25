"""The run loop: sample × task, repair turn, grading, crash-safe records."""

from __future__ import annotations

import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import RECORD_VERSION, __version__
from .client import ChatClient, ChatResult
from .config import Target
from .errors import GradeError, ModelBenchError, TargetUnavailable
from .events import EVENT_FILE, EventLog
from .grader import grade, runner_available
from .prompts import build_prompt, build_repair_prompt
from .tasks import Suite, Task
from .util import append_jsonl, human_duration, mean, now_iso, pct, read_jsonl, write_json


def resume_pairs(results_path: Path, suite_digest: str, target_name: str) -> set[tuple[str, int]]:
    """Task/sample pairs already recorded for *this* suite and target.

    A record from another model, or from a suite whose tasks changed, must never
    be counted as progress: the report would look complete while mixing two
    different benchmarks.
    """
    existing: set[tuple[str, int]] = set()
    foreign: list[str] = []
    for record in read_jsonl(results_path):
        if record.get("suite_digest") not in (None, suite_digest):
            foreign.append(f"{record.get('task')} s{record.get('sample')} (suite digest changed)")
            continue
        if record.get("target") not in (None, target_name):
            foreign.append(f"{record.get('task')} s{record.get('sample')} (target {record.get('target')!r})")
            continue
        existing.add((str(record.get("task")), int(record.get("sample") or 0)))
    if foreign:
        raise ModelBenchError(
            f"{results_path} already holds records that do not belong to this run "
            f"({foreign[0]}, {len(foreign)} total). Resuming would mix them into one report. "
            "Use a different --out, or move the old results.jsonl aside first."
        )
    return existing


def sample_seed(base: int | None, sample: int) -> int | None:
    """Seed for the n-th sample of a task.

    Two samples sent with the same seed are one sample counted twice: the
    stability rows would read 0.0 spread and hide real run-to-run variance.
    Offsetting by sample keeps the samples independent while the whole run stays
    reproducible from the base seed.
    """
    return None if base is None else int(base) + max(0, int(sample) - 1)


@dataclass
class RunPlan:
    suite: Suite
    target: Target
    out_dir: Path
    samples: int = 2
    repair: bool = True
    only: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    tiers: list[str] = field(default_factory=list)
    max_tokens: int | None = None
    retry_cap: int | None = None
    resume: bool = False
    warmup: bool = True
    order: str = "sample"  # "sample" (spread tasks over time) or "task"
    fail_fast: bool = False
    quiet: bool = False
    allow_missing_runners: bool = False
    manage_server: bool = False
    jobs: int = 1


@dataclass
class RunOutcome:
    out_dir: Path
    records: list[dict]
    errors: int
    elapsed_s: float
    skipped: list[str] = field(default_factory=list)

    @property
    def mean_first(self) -> float:
        return mean([r["first"]["score"] for r in self.records])


class Runner:
    def __init__(self, plan: RunPlan, on_progress: Callable[[str], None] | None = None):
        self.plan = plan
        self.print = on_progress or (lambda line: print(line, flush=True))
        self.results_path = plan.out_dir / "results.jsonl"
        self.errors_path = plan.out_dir / "errors.log"
        self.client = ChatClient(plan.target, on_event=self._event)
        self.served_id: str | None = None
        self.suite_digest = plan.suite.digest()
        self.errors = 0
        self._lock = threading.Lock()
        self.skipped: list[str] = []
        self.skipped_context: list[str] = []
        self.context: int | None = None
        self._server_log = None
        self._server_stopped = False
        self.events: EventLog | None = None

    # ------------------------------------------------------------------ #
    # events
    # ------------------------------------------------------------------ #
    def _emit(self, kind: str, **fields) -> None:
        """Record one line in ``events.jsonl``; a monitor is allowed to be watching."""
        if self.events is not None:
            try:
                self.events.emit(kind, **fields)
            except OSError:
                # A full disk must not turn a benchmark into a crash; the
                # results file is the record that matters.
                self.events = None

    def _close_events(self) -> None:
        if self.events is not None:
            self.events.close()
            self.events = None

    # ------------------------------------------------------------------ #
    # setup
    # ------------------------------------------------------------------ #
    def _event(self, message: str) -> None:
        if not self.plan.quiet:
            self.print(f"    · {message}")

    def _meta(self, tasks: list[Task]) -> dict:
        return {
            "record_version": RECORD_VERSION,
            "modelbench": __version__,
            "started_at": now_iso(),
            "target": self.plan.target.describe(),
            "suite": {
                "id": self.plan.suite.id,
                "version": self.plan.suite.version,
                "digest": self.suite_digest,
                "tasks": [t.id for t in tasks],
                "categories": sorted({t.category for t in tasks}),
                "checks": sum(t.checks for t in tasks),
            },
            "samples": self.plan.samples,
            "repair": self.plan.repair,
            "order": self.plan.order,
            "generation": {
                **self.plan.target.generation.to_dict(),
                "max_tokens": self.plan.max_tokens or self.plan.target.generation.max_tokens,
                "retry_cap": self.plan.retry_cap or self.plan.target.generation.retry_cap,
            },
            "environment": {
                "python": sys.version.split()[0],
                "platform": sys.platform,
            },
            "finished_at": None,
            "status": "running",
        }

    def _start_server(self) -> None:
        target = self.plan.target
        if not target.start_cmd:
            return
        import subprocess

        cmd = target.start_cmd
        if "{port}" in cmd and target.port:
            cmd = cmd.replace("{port}", str(target.port))
        self._server_log = open(self.plan.out_dir / "server.log", "a", encoding="utf-8")  # noqa: SIM115
        self._server_log.write(f"$ {cmd}\n")
        self._server_log.flush()
        subprocess.run(cmd, shell=True, stdout=self._server_log, stderr=subprocess.STDOUT, check=False)

    def _stop_server(self) -> None:
        if self._server_stopped:
            return
        self._server_stopped = True
        target = self.plan.target
        if target.stop_cmd:
            import subprocess

            cmd = target.stop_cmd
            if "{port}" in cmd and target.port:
                cmd = cmd.replace("{port}", str(target.port))
            if self._server_log:
                self._server_log.write(f"$ {cmd}\n")
                self._server_log.flush()
            subprocess.run(cmd, shell=True, stdout=self._server_log, stderr=subprocess.STDOUT, check=False)
        if self._server_log:
            self._server_log.close()
            self._server_log = None

    def _preflight(self, tasks: list[Task]) -> None:
        needed = {t.runner for t in tasks}
        missing = sorted(r for r in needed if not runner_available(r))
        if missing and not self.plan.allow_missing_runners:
            raise ModelBenchError(
                "missing grader runtime(s): "
                + ", ".join(missing)
                + ". Install them, use --only/--exclude to skip those tasks, "
                "or pass --allow-missing-runners to drop them automatically."
            )
        if missing:
            dropped = [t for t in tasks if t.runner in missing]
            self.skipped = [t.id for t in dropped]
            tasks[:] = [t for t in tasks if t.runner not in missing]
            self.print(
                f"warning: skipping {len(dropped)} task(s) without runtime {', '.join(missing)}: "
                + ", ".join(self.skipped)
            )
            self._emit("warning", reason="missing_runtime", tasks=self.skipped, runtimes=sorted(missing))

    # ------------------------------------------------------------------ #
    # one task × one sample
    # ------------------------------------------------------------------ #
    def _cap_for(self, prompt: str, cap: int) -> int:
        """Clamp an answer budget to what the model can actually hold.

        ``prompt_chars / 3`` is a deliberately pessimistic token estimate
        (code runs near 3.3 chars/token); overestimating costs a little
        headroom, underestimating returns an HTTP 400 or a silent truncation.
        """
        if not self.context:
            return cap
        estimate = max(1, len(prompt) // 3)
        room = self.context - estimate - 256
        if room <= 128:
            raise ModelBenchError(
                f"context window {self.context:,} tokens cannot hold this prompt "
                f"(~{estimate:,} tokens) plus an answer"
            )
        return max(128, min(cap, room))

    @staticmethod
    def _protocol(result: ChatResult, source: str, graded, retried: bool) -> str:
        """Why a graded attempt looks the way it does, in one word.

        Scores alone hide the difference between "wrote the wrong code" and
        "never produced an answer the harness could grade"; a benchmark that
        conflates them reports formatting as capability.
        """
        if not (result.content or "").strip():
            return "empty_answer"
        if source == "none":
            return "unparseable"
        if graded.no_result_line:
            return "grader_crash"
        if result.finish_reason == "length" and not retried:
            return "truncated"
        return "ok"

    def _extra_call(self, result: ChatResult, max_tokens: int) -> dict:
        return {
            "max_tokens": max_tokens,
            "finish_reason": result.finish_reason,
            "completion_tokens": result.completion_tokens,
            "prompt_tokens": result.prompt_tokens,
            "total_s": round(result.total_s, 2),
        }

    def run_one(self, task: Task, sample: int, prompt: str) -> dict:
        plan = self.plan
        sample_dir = plan.out_dir / f"s{sample}"
        raw_path = sample_dir / "raw" / f"{task.id}.txt"
        sol_dir = sample_dir / "sol"
        cap = self._cap_for(prompt, plan.max_tokens or task.max_tokens)
        retry_cap = (
            plan.retry_cap
            if plan.retry_cap is not None
            else (task.retry_cap or plan.target.generation.retry_cap)
        )
        if retry_cap:
            retry_cap = self._cap_for(prompt, retry_cap) if retry_cap > cap else None

        wall_start = time.time()
        extra: list[dict] = []
        seed = sample_seed(plan.target.generation.seed, sample)

        self._emit(
            "attempt_started",
            task=task.id,
            sample=sample,
            phase="first",
            max_tokens=cap,
            retry_cap=retry_cap,
        )
        result = self.client.chat(
            [{"role": "user", "content": prompt}], max_tokens=cap, raw_path=raw_path, seed=seed
        )
        retried = False
        if result.truncated and retry_cap and retry_cap > cap:
            extra.append(self._extra_call(result, cap))
            result = self.client.chat(
                [{"role": "user", "content": prompt}],
                max_tokens=retry_cap,
                raw_path=raw_path,
                seed=seed,
            )
            retried = True

        solution, source, written = task.write_solution(result.content, sol_dir)
        graded = grade(task, solution)
        first = {
            **result.metrics(),
            "max_tokens": retry_cap if retried else cap,
            "source": source,
            "files_written": written,
            "retried_after_length": retried,
            "discarded_calls": extra,
            "protocol": self._protocol(result, source, graded, retried),
            **graded.to_record(),
        }
        self._emit(
            "attempt_finished",
            task=task.id,
            sample=sample,
            phase="first",
            score=first["score"],
            passed=first["passed"],
            total=first["total"],
            total_s=first.get("total_s"),
            ttft_s=first.get("ttft_s"),
            tok_per_s=first.get("tok_per_s"),
            completion_tokens=first.get("completion_tokens"),
            finish_reason=first.get("finish_reason"),
            protocol=first.get("protocol"),
            retried=retried,
        )

        repair_record = None
        if plan.repair and not graded.solved:
            # A thinking model can put everything in the reasoning channel and
            # leave content empty; sending "(empty)" back throws away the only
            # draft it produced. Echo the reasoning instead, capped so the
            # repair call still fits the window.
            draft = (result.content or "").strip() or (result.reasoning or "").strip()
            feedback = build_repair_prompt("\n".join(graded.failures))
            messages = [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": draft[-12000:] or "(empty)"},
                {"role": "user", "content": feedback},
            ]
            # The repair prompt is longer than the first one (it carries the
            # failing assertions and the draft), so its answer budget must be
            # recomputed rather than inherited.
            repair_cap = self._cap_for(prompt + draft[-12000:] + feedback, cap)
            repair_retry = None
            if retry_cap and retry_cap > repair_cap:
                repair_retry = self._cap_for(prompt + draft[-12000:] + feedback, retry_cap)
            repair_raw = sample_dir / "raw" / f"{task.id}.repair.txt"
            self._emit(
                "attempt_started",
                task=task.id,
                sample=sample,
                phase="repair",
                max_tokens=repair_cap,
            )
            repair_result = self.client.chat(messages, max_tokens=repair_cap, raw_path=repair_raw, seed=seed)
            repair_extra: list[dict] = []
            if repair_result.truncated and repair_retry and repair_retry > repair_cap:
                repair_extra.append(self._extra_call(repair_result, repair_cap))
                repair_result = self.client.chat(
                    messages, max_tokens=repair_retry, raw_path=repair_raw, seed=seed
                )
            repair_solution, repair_source, repair_written = task.write_solution(
                repair_result.content, sol_dir / "repair"
            )
            repair_graded = grade(task, repair_solution)
            repair_record = {
                **repair_result.metrics(),
                "max_tokens": repair_retry if repair_extra else repair_cap,
                "source": repair_source,
                "files_written": repair_written,
                "discarded_calls": repair_extra,
                "protocol": self._protocol(repair_result, repair_source, repair_graded, bool(repair_extra)),
                **repair_graded.to_record(),
            }
            self._emit(
                "attempt_finished",
                task=task.id,
                sample=sample,
                phase="repair",
                score=repair_record["score"],
                passed=repair_record["passed"],
                total=repair_record["total"],
                total_s=repair_record.get("total_s"),
                ttft_s=repair_record.get("ttft_s"),
                tok_per_s=repair_record.get("tok_per_s"),
                completion_tokens=repair_record.get("completion_tokens"),
                finish_reason=repair_record.get("finish_reason"),
                protocol=repair_record.get("protocol"),
                retried=bool(repair_extra),
            )

        final = repair_record if repair_record and repair_record["score"] > first["score"] else first
        return {
            "record_version": RECORD_VERSION,
            "model": plan.target.name,
            "target": plan.target.name,
            "served_id": self.served_id or plan.target.model,
            "suite": plan.suite.id,
            "suite_digest": self.suite_digest,
            "task": task.id,
            "title": task.title,
            "category": task.category,
            "tier": task.tier,
            "kind": task.kind,
            "lang": task.lang,
            "sample": sample,
            "seed": seed,
            "when": now_iso(),
            "prompt_chars": len(prompt),
            "context": self.context,
            "first": first,
            "repair": repair_record,
            "final_score": final["score"],
            "final_solved": final["solved"],
            "wall_s": round(time.time() - wall_start, 2),
        }

    # ------------------------------------------------------------------ #
    # the whole run
    # ------------------------------------------------------------------ #
    def execute(self) -> RunOutcome:
        plan = self.plan
        plan.out_dir.mkdir(parents=True, exist_ok=True)
        tasks = plan.suite.select(plan.only, plan.exclude)
        if plan.tiers:
            wanted = {t.lower() for t in plan.tiers}
            tasks = [t for t in tasks if t.tier in wanted]
            if not tasks:
                raise ModelBenchError(f"no tasks in tier(s) {', '.join(sorted(wanted))}")
        self._preflight(tasks)
        meta = self._meta(tasks)
        write_json(plan.out_dir / "run.json", meta)
        self.events = EventLog(plan.out_dir / EVENT_FILE)
        self._emit(
            "run_started",
            suite=plan.suite.id,
            suite_version=plan.suite.version,
            digest=self.suite_digest,
            target=plan.target.name,
            base_url=plan.target.base_url,
            model=plan.target.model,
            samples=plan.samples,
            repair=plan.repair,
            tasks=[t.id for t in tasks],
            jobs=plan.jobs,
            modelbench=__version__,
        )

        existing: set[tuple[str, int]] = set()
        if plan.resume:
            existing = resume_pairs(self.results_path, self.suite_digest, plan.target.name)
            if existing:
                self.print(f"resume: {len(existing)} task/sample record(s) already present")

        started = time.time()
        completed = 0
        try:
            self._start_server()
            self.served_id = self.client.wait_ready()
            self.print(f"target {plan.target.name} @ {plan.target.base_url} → served as {self.served_id!r}")
            self.context = self.client.detect_context()
            if self.context:
                self.print(f"context window: {self.context:,} tokens (answers clamped to fit)")
                too_small = [t for t in tasks if t.min_ctx and t.min_ctx > self.context]
                if too_small:
                    self.skipped_context = [t.id for t in too_small]
                    drop = set(self.skipped_context)
                    tasks[:] = [t for t in tasks if t.id not in drop]
                    self.print(
                        f"warning: skipping {len(too_small)} task(s) that need more than "
                        f"{self.context:,} tokens: " + ", ".join(self.skipped_context)
                    )
                    self._emit(
                        "warning",
                        reason="context_too_small",
                        tasks=self.skipped_context,
                        context=self.context,
                    )
            if plan.warmup:
                self._emit("warmup_started")
                self.client.chat([{"role": "user", "content": "Reply with the single word: ready"}], max_tokens=16)

            pairs = self._pairs(tasks)
            total = len(pairs)
            if plan.jobs > 1:
                completed = self._run_parallel(pairs, existing)
            else:
                for index, (task, sample) in enumerate(pairs, start=1):
                    if (task.id, sample) in existing:
                        self.print(f"[{index:>3}/{total}] {task.id:<24s} s{sample}  skipped (recorded)")
                        self._emit("sample_skipped", task=task.id, sample=sample, reason="recorded")
                        continue
                    prompt = build_prompt(task, plan.suite.prompt_text)
                    try:
                        record = self.run_one(task, sample, prompt)
                    except (TargetUnavailable, GradeError, ModelBenchError) as exc:
                        self.errors += 1
                        self._log_error(task, sample, exc)
                        if plan.fail_fast:
                            raise
                        continue
                    except Exception as exc:  # noqa: BLE001 - one broken task must not end the run
                        self.errors += 1
                        self._log_error(task, sample, exc)
                        if plan.fail_fast:
                            raise
                        continue
                    append_jsonl(self.results_path, record)
                    completed += 1
                    self._progress(index, total, task, sample, record)
        except KeyboardInterrupt:
            self.print("\ninterrupted — partial results are on disk")
            self._finish_meta(meta, tasks, status="interrupted", elapsed=time.time() - started)
            raise
        except Exception:
            # A run that dies before the loop — endpoint never ready, config
            # error, crash — must not leave run.json claiming to be running.
            self._finish_meta(meta, tasks, status="failed", elapsed=time.time() - started)
            raise
        finally:
            self._stop_server()

        elapsed = time.time() - started
        self._finish_meta(meta, tasks, status="finished", elapsed=elapsed)
        records = [r for r in read_jsonl(self.results_path)]
        self.print(
            f"run complete: {completed} new record(s), {len(records)} total, "
            f"{self.errors} error(s), {human_duration(elapsed)} → {plan.out_dir}"
        )
        return RunOutcome(plan.out_dir, records, self.errors, elapsed, self.skipped)

    def _run_parallel(self, pairs: list[tuple[Task, int]], existing: set[tuple[str, int]]) -> int:
        """Run task/sample pairs on several threads.

        Meant for endpoints that serve concurrent requests: a hosted API, or a
        local server started with several slots. Every pair owns its own sample
        directory, so the only shared state is the results file, the error log
        and the progress line — those go through a lock. Progress is printed in
        completion order, not task order.
        """
        pending = [(task, sample) for task, sample in pairs if (task.id, sample) not in existing]
        jobs = max(1, int(self.plan.jobs))
        if not pending:
            return 0
        self.print(f"running {len(pending)} pair(s) {jobs} at a time")
        completed = 0

        def work(task: Task, sample: int):
            prompt = build_prompt(task, self.plan.suite.prompt_text)
            try:
                return task, sample, self.run_one(task, sample, prompt)
            except Exception as exc:  # noqa: BLE001 - same contract as the serial loop
                with self._lock:
                    self.errors += 1
                    self._log_error(task, sample, exc)
                if self.plan.fail_fast:
                    raise
                return task, sample, None

        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(work, task, sample) for task, sample in pending]
            for future in as_completed(futures):
                task, sample, record = future.result()
                if record is None:
                    continue
                with self._lock:
                    append_jsonl(self.results_path, record)
                    completed += 1
                    self._progress(completed, len(pending), task, sample, record)
        return completed

    def _finish_meta(self, meta: dict, tasks: list[Task], status: str, elapsed: float) -> None:
        meta.update(
            {
                "finished_at": now_iso(),
                "status": status,
                "elapsed_s": round(elapsed, 1),
                "records": len(read_jsonl(self.results_path)),
                "errors": self.errors,
                "skipped_tasks": self.skipped,
                "skipped_context": self.skipped_context,
                "context": self.context,
            }
        )
        write_json(self.plan.out_dir / "run.json", meta)
        self._emit(
            "run_finished",
            status=status,
            records=meta["records"],
            errors=meta["errors"],
            elapsed_s=meta["elapsed_s"],
            skipped=list(self.skipped) + list(self.skipped_context),
        )
        self._close_events()

    def _pairs(self, tasks: list[Task]) -> list[tuple[Task, int]]:
        if self.plan.order == "task":
            return [(task, sample) for task in tasks for sample in range(1, self.plan.samples + 1)]
        return [(task, sample) for sample in range(1, self.plan.samples + 1) for task in tasks]

    def _progress(self, index: int, total: int, task: Task, sample: int, record: dict) -> None:
        if self.plan.quiet:
            return
        first = record["first"]
        repair = record.get("repair")
        extra = f"  repair {repair['passed']}/{repair['total']}" if repair else ""
        flags = ""
        if first.get("retried_after_length"):
            flags += " [cap-retry]"
        protocol = first.get("protocol") or "ok"
        if protocol != "ok":
            flags += f" [{protocol.replace('_', '-')}]"
        if first.get("source") in {"raw", "fence-unclosed"}:
            flags += f" [{first['source']}]"
        tps = f"{first['tok_per_s']:.0f} t/s" if first.get("tok_per_s") else "— t/s"
        self.print(
            f"[{index:>3}/{total}] {task.id:<24s} s{sample}  "
            f"{first['passed']:>3}/{first['total']:<3} {pct(first['score']):>6}  "
            f"{first['total_s']:>6.1f}s {tps:>8}{extra}{flags}"
        )

    def _log_error(self, task: Task, sample: int, exc: BaseException) -> None:
        import traceback

        self.print(f"    ! {task.id} s{sample} failed: {type(exc).__name__}: {exc}")
        self._emit(
            "attempt_failed",
            task=task.id,
            sample=sample,
            error=type(exc).__name__,
            message=str(exc)[:400],
        )
        with open(self.errors_path, "a", encoding="utf-8") as fh:
            fh.write(f"{task.id} s{sample} {type(exc).__name__}: {exc}\n")
            traceback.print_exc(file=fh)
