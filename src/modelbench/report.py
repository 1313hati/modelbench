"""Aggregation and reporting.

A report is intentionally more than a score table: it records where the numbers
came from (served model, endpoint, suite digest, sampling), how complete the run
was, and where the model's answer had to be salvaged by the extractor.  Those
details are what make a comparison believable — and what let someone else
reproduce it months later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Iterable, Sequence

from . import __version__
from .stats import bootstrap_mean_ci, fmt_p, paired_delta
from .util import (
    column_table,
    int_fmt,
    mean,
    median,
    now_iso,
    p90,
    pct,
    read_json,
    read_jsonl,
    stdev,
    write_json,
)

MISSING = "—"


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
@dataclass
class Run:
    label: str
    path: Path
    header: dict
    records: list[dict]

    @property
    def tasks(self) -> list[str]:
        listed = (self.header.get("suite") or {}).get("tasks")
        if listed:
            return list(listed)
        return sorted({r["task"] for r in self.records})

    @property
    def generation(self) -> dict:
        """Sampler settings recorded in run.json (empty for hand-made runs)."""
        return dict(self.header.get("generation") or {})

    @property
    def samples(self) -> int:
        if self.header.get("samples"):
            return int(self.header["samples"])
        seen = {int(r.get("sample") or 1) for r in self.records}
        return max(seen) if seen else 1

    @property
    def suite_id(self) -> str:
        return str((self.header.get("suite") or {}).get("id") or (self.records[0].get("suite") if self.records else "") or "")


def load_run(path: str | Path) -> Run:
    path = Path(path).expanduser()
    if path.is_file():
        results = path
        root = path.parent
    else:
        results = path / "results.jsonl"
        root = path
    if not results.is_file():
        raise FileNotFoundError(f"no results.jsonl in {root}")
    records = read_jsonl(results)
    if not records:
        raise ValueError(f"{results} is empty")
    header = read_json(root / "run.json", default={}) or {}
    label = str(
        (header.get("target") or {}).get("name")
        or records[0].get("target")
        or records[0].get("model")
        or root.name
    )
    # A resumed run may contain records from different labels; keep them visible.
    labels = {str(r.get("target") or r.get("model")) for r in records}
    if len(labels) > 1:
        label = f"{label} (+{len(labels) - 1})"
    return Run(label=label, path=root, header=header, records=records)


def load_runs(paths: Iterable[str | Path]) -> list[Run]:
    runs = [load_run(path) for path in paths]
    if not runs:
        raise ValueError("no runs given")
    labels: dict[str, int] = {}
    for run in runs:
        labels[run.label] = labels.get(run.label, 0) + 1
        if labels[run.label] > 1:
            run.label = f"{run.label}#{labels[run.label]}"
    return runs



SAMPLING_KEYS = ("temperature", "top_p", "top_k", "min_p", "seed")


def sampling(run: "Run") -> dict:
    """Sampler settings for a run, falling back to what the records carry.

    ``None`` means the field was never sent, which is a real difference from
    "sent with the default value" and is shown as such.
    """
    gen = run.generation
    out = {key: gen.get(key) for key in SAMPLING_KEYS}
    if out["seed"] is None:
        seeds = sorted({r.get("seed") for r in run.records if r.get("seed") is not None})
        if seeds:
            out["seed"] = seeds[0]
    out["max_tokens"] = gen.get("max_tokens")
    return out


def sampling_note(run: "Run") -> str:
    """One line of prose: how this run was sampled."""
    s = sampling(run)
    bits = []
    if s["temperature"] is not None:
        bits.append(f"temperature {_num(s['temperature'])}")
    if s["top_p"] is not None:
        bits.append(f"top_p {_num(s['top_p'])}")
    if s["top_k"] is not None:
        bits.append(f"top_k {_num(s['top_k'])}")
    if s["min_p"] is not None:
        bits.append(f"min_p {_num(s['min_p'])}")
    if s["seed"] is None:
        bits.append("seed not pinned")
    elif run.samples > 1:
        bits.append(f"seed {s['seed']} (+1 per sample)")
    else:
        bits.append(f"seed {s['seed']}")
    if s["max_tokens"]:
        bits.append(f"fallback cap {int(s['max_tokens']):,} tokens")
    return ", ".join(bits)


def _num(value) -> str:
    """0.2 stays 0.2, 1.0 stays 1.0 — a sampler temperature is not a count."""
    if isinstance(value, float):
        return f"{value:g}" if value != int(value) else f"{value:.1f}"
    return str(value)


def sampling_conflicts(runs: Sequence["Run"]) -> list[str]:
    """Fields that differ between runs — the usual cause of a fake delta.

    A model re-run at temperature 0.2 and 1.0 is two experiments, not one.
    """
    if len(runs) < 2:
        return []
    conflicts = []
    settings = [sampling(run) for run in runs]
    for key in ("temperature", "top_p", "top_k", "min_p", "seed"):
        values = [s[key] for s in settings]
        if any(v is None for v in values):
            if any(v is not None for v in values):
                conflicts.append(key)
            continue
        if len({str(v) for v in values}) > 1:
            conflicts.append(key)
    return conflicts


# --------------------------------------------------------------------------- #
# metrics
# --------------------------------------------------------------------------- #
def task_map(records: Sequence[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for record in records:
        out.setdefault(str(record["task"]), []).append(record)
    return out


def token_usage(record: dict) -> tuple[int, int]:
    """(prompt, completion) tokens this record cost, retries and repairs included.

    Counting only the winning attempt understates the bill: a cap retry and a
    feedback turn are paid for whether or not they scored.
    """
    prompt = completion = 0
    for key in ("first", "repair"):
        attempt = record.get(key) or {}
        prompt += int(attempt.get("prompt_tokens") or 0)
        completion += int(attempt.get("completion_tokens") or 0)
        for extra in attempt.get("discarded_calls") or []:
            prompt += int(extra.get("prompt_tokens") or 0)
            completion += int(extra.get("completion_tokens") or 0)
    return prompt, completion


def total_tokens(record: dict) -> int:
    return token_usage(record)[1]


def pricing(run: "Run") -> dict | None:
    """Per-Mtok prices recorded with the run, if the target declared any."""
    header = (run.header.get("target") or {}).get("pricing") or {}
    record = run.records[0].get("pricing") or {} if run.records else {}
    merged = {**record, **header}
    if merged.get("input_per_mtok") is None and merged.get("output_per_mtok") is None:
        return None
    return {
        "input_per_mtok": float(merged.get("input_per_mtok") or 0.0),
        "output_per_mtok": float(merged.get("output_per_mtok") or 0.0),
    }


def run_metrics(run: Run) -> dict:
    records = run.records
    per_task = task_map(records)
    first_task_means = [mean([r["first"]["score"] for r in recs]) for recs in per_task.values()]
    final_task_means = [mean([r["final_score"] for r in recs]) for recs in per_task.values()]
    solved_first = [1.0 if r["first"]["solved"] else 0.0 for r in records]
    solved_final = [1.0 if r.get("final_solved") else 0.0 for r in records]
    repairs = [r for r in records if r.get("repair")]
    improved = [r for r in repairs if r["repair"]["score"] > r["first"]["score"]]
    repaired_solved = [r for r in repairs if r["repair"]["solved"]]
    walls = [r["first"].get("total_s") or 0.0 for r in records]
    tps = [r["first"]["tok_per_s"] for r in records if r["first"].get("tok_per_s")]
    ttfts = [r["first"].get("ttft_s") for r in records if r["first"].get("ttft_s")]
    tokens = [r["first"].get("completion_tokens") for r in records if r["first"].get("completion_tokens")]
    passed = sum(r["first"]["passed"] for r in records)
    assertions = sum(r["first"]["total"] for r in records)
    sources: dict[str, int] = {}
    for record in records:
        source = str(record["first"].get("source") or "?")
        sources[source] = sources.get(source, 0) + 1
    errors = sum(1 for r in records if r.get("error"))
    per_task_scores = {task: [r["first"]["score"] for r in recs] for task, recs in per_task.items()}
    spreads = [max(v) - min(v) for v in per_task_scores.values() if len(v) > 1]
    unstable = sorted(t for t, v in per_task_scores.items() if len(v) > 1 and (max(v) - min(v)) > 1e-9)
    first_ci = bootstrap_mean_ci(first_task_means)
    final_ci = bootstrap_mean_ci(final_task_means)
    usage = [token_usage(r) for r in records]
    input_tokens = sum(u[0] for u in usage)
    output_tokens = sum(u[1] for u in usage)
    price = pricing(run)
    cost = None
    cost_per_solved = None
    if price is not None:
        cost = (
            input_tokens / 1_000_000 * price["input_per_mtok"]
            + output_tokens / 1_000_000 * price["output_per_mtok"]
        )
        solved_count = sum(1 for r in records if r.get("final_solved"))
        cost_per_solved = cost / solved_count if solved_count else None
    return {
        "records": len(records),
        "tasks": len(per_task),
        "samples": run.samples,
        "expected": len(run.tasks) * run.samples,
        "missing": missing_pairs(run, per_task),
        "duplicates": duplicate_pairs(records),
        "first_score": mean(first_task_means),
        "first_sd": stdev(first_task_means),
        "first_ci": first_ci,
        "final_score": mean(final_task_means),
        "final_sd": stdev(final_task_means),
        "final_ci": final_ci,
        "assertions_passed": passed,
        "assertions_total": assertions,
        "assertion_rate": (passed / assertions) if assertions else 0.0,
        "solved_first": mean(solved_first),
        "solved_final": mean(solved_final),
        "repairs": len(repairs),
        "improved": len(improved),
        "repaired_solved": len(repaired_solved),
        "median_call_s": median(walls),
        "p90_call_s": p90(walls),
        "median_tps": median(tps),
        "median_ttft": median(ttfts) if ttfts else None,
        "median_tokens": median(tokens) if tokens else None,
        "total_tokens": output_tokens,
        "input_tokens": input_tokens,
        "pricing": price,
        "cost_usd": cost,
        "cost_per_solved_usd": cost_per_solved,
        "wall_s": sum(r.get("wall_s") or 0.0 for r in records),
        "truncated": sum(1 for r in records if r["first"].get("finish_reason") == "length"),
        "no_result": sum(1 for r in records if r["first"].get("no_result_line")),
        "sources": sources,
        "errors": errors,
        # How much the answer moves between independent samples of the same task.
        # A task that is solved once and missed once is the clearest sign that a
        # mean over two samples cannot separate two close models.
        "unstable": len(unstable),
        "unstable_ids": unstable,
        "sample_spread": mean(spreads) if spreads else 0.0,
    }


def missing_pairs(run: Run, per_task: dict[str, list[dict]] | None = None) -> list[dict]:
    per_task = per_task or task_map(run.records)
    missing = []
    for task in run.tasks:
        present = {int(r.get("sample") or 1) for r in per_task.get(task, [])}
        for sample in range(1, run.samples + 1):
            if sample not in present:
                missing.append({"task": task, "sample": sample})
    return missing


def duplicate_pairs(records: Sequence[dict]) -> list[dict]:
    seen: dict[tuple[str, int], int] = {}
    for record in records:
        key = (str(record["task"]), int(record.get("sample") or 1))
        seen[key] = seen.get(key, 0) + 1
    return [{"task": task, "sample": sample, "count": count} for (task, sample), count in seen.items() if count > 1]


def per_task_metrics(run: Run) -> dict[str, dict]:
    out = {}
    for task, records in sorted(task_map(run.records).items()):
        out[task] = {
            "category": records[0].get("category") or "",
            "n": len(records),
            "first": mean([r["first"]["score"] for r in records]),
            "final": mean([r["final_score"] for r in records]),
            "solved_first": mean([1.0 if r["first"]["solved"] else 0.0 for r in records]),
            "solved_final": mean([1.0 if r.get("final_solved") else 0.0 for r in records]),
            "assertions": [sum(r["first"]["passed"] for r in records), sum(r["first"]["total"] for r in records)],
            "median_s": median([r["first"].get("total_s") or 0.0 for r in records]),
            "tokens": int(mean([r["first"].get("completion_tokens") or 0 for r in records])),
        }
    return out


def per_category_metrics(run: Run) -> dict[str, dict]:
    buckets: dict[str, list[dict]] = {}
    for record in run.records:
        buckets.setdefault(str(record.get("category") or "misc"), []).append(record)
    out = {}
    for category, records in sorted(buckets.items()):
        by_task = task_map(records)
        out[category] = {
            "n": len(records),
            "tasks": len(by_task),
            "first": mean([mean([r["first"]["score"] for r in recs]) for recs in by_task.values()]),
            "final": mean([mean([r["final_score"] for r in recs]) for recs in by_task.values()]),
        }
    return out


def failure_signatures(run: Run, limit: int = 12) -> list[dict]:
    """Failing assertions of the first attempt, grouped by assertion name.

    Graders print ``FAIL <name>: ...``, so the name is the stable part and the
    message carries the values.  Counting names across independent samples shows
    systematic weaknesses instead of one-off wrong answers; a name counts once
    per record, so a chatty grader cannot dominate the list.
    """
    stats: dict[str, dict] = {}
    for record in run.records:
        attempt = record.get("first") or {}
        if attempt.get("no_result_line"):
            # The grader never reached RESULT, so "failures" holds raw output
            # (tracebacks, SyntaxError lines). Those belong to the integrity
            # section, not to a list of assertions.
            continue
        seen: dict[str, str] = {}
        for raw in attempt.get("failures") or []:
            text = str(raw).strip()
            if not text:
                continue
            name = text.split(":", 1)[0].strip()
            # Records store the message without its ``FAIL `` prefix; tolerate
            # both forms so hand-written or older records group the same way.
            if name.upper().startswith("FAIL "):
                name = name[5:].strip()
            if not name or not any(ch.isalnum() for ch in name):
                continue
            if len(name) > 90:
                name = name[:87] + "…"
            if name and name not in seen:
                seen[name] = text
        for name, example in seen.items():
            entry = stats.setdefault(name, {"name": name, "records": 0, "tasks": set(), "example": example})
            entry["records"] += 1
            entry["tasks"].add(str(record.get("task")))
    rows = sorted(stats.values(), key=lambda e: (-e["records"], e["name"]))[:limit]
    for row in rows:
        row["tasks"] = sorted(row["tasks"])  # type: ignore[assignment]
        row["task_count"] = len(row["tasks"])  # type: ignore[arg-type]
    return rows


@dataclass
class Pairwise:
    a: str
    b: str
    common: list[str]
    wins_a: int
    wins_b: int
    ties: int
    mean_delta_pp: float
    rows: list[dict]
    # Run-to-run noise: how much a task's own score moves between independent
    # samples. A gap smaller than this is not evidence of anything.
    noise_pp: float = 0.0
    decisive: bool = True
    # Fewest samples any one task carries in either run. The noise estimate is
    # only as good as this number: two samples give a two-point range.
    samples_min: int = 0
    # Bootstrap interval for the mean per-task delta, and the exact sign-test
    # p-value over the tasks that were not tied. A gap can clear the noise
    # threshold and still fail the sign test; both have to hold.
    delta_ci: tuple[float, float] | None = None
    p_value: float = 1.0
    significant: bool = False

    def provisional(self, require: int = 3) -> bool:
        """True when the evidence is too thin to separate close models."""
        return 0 < self.samples_min < require

    @property
    def identical(self) -> bool:
        """Same score on every common task — there is no gap to test."""
        return bool(self.common) and self.wins_a == 0 and self.wins_b == 0

    @property
    def gap_pp(self) -> float:
        """Per-task gap oriented towards the leader, always non-negative.

        ``mean_delta_pp`` is signed ``a - b`` because that is what the maths
        produces. Prose is written about the leader, so it uses this instead —
        otherwise a report on a run ordered b, a prints "+7.2 pp" next to a
        delta of -7.2.
        """
        return abs(self.mean_delta_pp)

    @property
    def gap_ci(self) -> tuple[float, float] | None:
        """``delta_ci`` flipped into the leader's orientation, low bound first."""
        if not self.delta_ci:
            return None
        low, high = self.delta_ci
        if self.mean_delta_pp < 0:
            low, high = -high, -low
        return (min(low, high), max(low, high))


def task_spread_pp(run: "Run", task: str) -> float | None:
    """How far this task's score moved between samples, in pp (None if 1 sample)."""
    scores = [float(r["first"]["score"]) for r in run.records if r.get("task") == task]
    if len(scores) < 2:
        return None
    return (max(scores) - min(scores)) * 100


def samples_per_task(run: "Run", task: str) -> int:
    return sum(1 for r in run.records if r.get("task") == task)


def pairwise(a: Run, b: Run) -> Pairwise:
    ta, tb = per_task_metrics(a), per_task_metrics(b)
    common = sorted(set(ta) & set(tb))
    rows, wins_a, wins_b, ties = [], 0, 0, 0
    spreads: list[float] = []
    counts: list[int] = []
    for task in common:
        counts.append(min(samples_per_task(a, task), samples_per_task(b, task)))
        da, db = ta[task]["first"], tb[task]["first"]
        delta = (da - db) * 100
        noise = [x for x in (task_spread_pp(a, task), task_spread_pp(b, task)) if x is not None]
        task_noise = max(noise) if noise else None
        if task_noise is not None:
            spreads.append(task_noise)
        if abs(delta) < 0.05:
            winner = "tie"
            ties += 1
        elif delta > 0:
            winner = a.label
            wins_a += 1
        else:
            winner = b.label
            wins_b += 1
        rows.append(
            {
                "task": task,
                "category": ta[task]["category"],
                "a": da,
                "b": db,
                "delta_pp": delta,
                "winner": winner,
                "noise_pp": task_noise,
                "within_noise": task_noise is not None and task_noise > 0 and abs(delta) <= task_noise,
            }
        )
    deltas = [r["delta_pp"] for r in rows]
    test = paired_delta(deltas, wins_a, wins_b, ties)
    return Pairwise(
        a=a.label,
        b=b.label,
        common=common,
        wins_a=wins_a,
        wins_b=wins_b,
        ties=ties,
        mean_delta_pp=mean(deltas) if deltas else 0.0,
        rows=rows,
        noise_pp=mean(spreads) if spreads else 0.0,
        decisive=abs(mean(deltas) if deltas else 0.0) > (mean(spreads) if spreads else 0.0),
        samples_min=min(counts) if counts else 0,
        delta_ci=test["ci_pp"],
        p_value=test["p_value"],
        significant=test["significant"],
    )


# --------------------------------------------------------------------------- #
# rendering
# --------------------------------------------------------------------------- #
def _signed_pp(value: float) -> str:
    if abs(value) < 0.05:
        return "0.0"
    return f"{value:+.1f}"


def _count(n: int, word: str) -> str:
    """'1 record' / '3 records' — reports are read by people."""
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def ci_pct(ci: tuple[float, float] | None) -> str:
    """A 0–1 interval as percentages: ``92.1–96.3%``.

    CIs live in score units so the maths stays in one place; a report prints
    them in the same unit as the score it sits next to.
    """
    if not ci:
        return MISSING
    return f"{ci[0] * 100:.1f}–{ci[1] * 100:.1f}%"


def _usd(value: float | None) -> str:
    if value is None:
        return MISSING
    if value == 0:
        return "$0"
    if value < 0.01:
        return f"${value:.4f}"
    if value < 10:
        return f"${value:.2f}"
    return f"${value:,.2f}"


def headline_rows(runs: Sequence[Run], metrics: Sequence[dict]) -> list[tuple[str, list[str]]]:
    """The headline table, shared by the markdown and HTML reports."""
    rows = [
        ("records / expected", [f"{m['records']} / {m['expected']}" for m in metrics]),
        ("samples / task", [str(run.samples) for run in runs]),
        ("mean task score, first", [pct(m["first_score"]) for m in metrics]),
        ("95% CI, first · final", [f"{ci_pct(m['first_ci'])} · {ci_pct(m['final_ci'])}" for m in metrics]),
        ("mean task score, final", [pct(m["final_score"]) for m in metrics]),
        (
            "first-attempt assertions",
            [f"{m['assertions_passed']}/{m['assertions_total']} ({pct(m['assertion_rate'])})" for m in metrics],
        ),
        ("fully solved, first", [pct(m["solved_first"]) for m in metrics]),
        ("fully solved, final", [pct(m["solved_final"]) for m in metrics]),
        (
            "repair turns / improved / solved",
            [f"{m['repairs']} / {m['improved']} / {m['repaired_solved']}" for m in metrics],
        ),
        (
            "tasks where samples differ",
            [f"{m['unstable']}/{m['tasks']}" if m["samples"] > 1 else MISSING for m in metrics],
        ),
        (
            "mean within-task spread",
            [f"{m['sample_spread'] * 100:.1f} pp" if m["samples"] > 1 else MISSING for m in metrics],
        ),
        ("median call wall", [f"{m['median_call_s']:.1f}s" for m in metrics]),
        ("p90 call wall", [f"{m['p90_call_s']:.1f}s" for m in metrics]),
        ("median output tokens / call", [int_fmt(m["median_tokens"]) for m in metrics]),
        ("prompt tokens, total", [f"{m['input_tokens']:,}" if m["input_tokens"] else MISSING for m in metrics]),
        ("completion tokens, total", [f"{m['total_tokens']:,}" for m in metrics]),
        ("estimated cost", [_usd(m["cost_usd"]) for m in metrics]),
        ("cost per solved attempt", [_usd(m["cost_per_solved_usd"]) for m in metrics]),
        ("tokens per solved task", [
            int_fmt(m["total_tokens"] / solved) if (solved := sum(1 for r in run.records if r.get("final_solved"))) else MISSING
            for m, run in zip(metrics, runs)
        ]),
        ("wall clock, total", [f"{m['wall_s'] / 60:.1f} min" for m in metrics]),
        ("median decode speed", [f"{m['median_tps']:.1f} tok/s" if m["median_tps"] else MISSING for m in metrics]),
        ("median TTFT", [f"{m['median_ttft']:.2f}s" if m["median_ttft"] else MISSING for m in metrics]),
        ("answers cut by token cap", [str(m["truncated"]) for m in metrics]),
    ]
    # A local target has no prices; printing four rows of em dashes buries the
    # numbers that do exist. Drop a row only when no run can fill it.
    return [row for row in rows if any(cell != MISSING for cell in row[1])]


def render_markdown(
    runs: Sequence[Run],
    title: str | None = None,
    notes: str | None = None,
    generated: str | None = None,
    require_samples: int = 3,
) -> str:
    metrics = [run_metrics(run) for run in runs]
    labels = [run.label for run in runs]
    pairs = [pairwise(runs[i], runs[j]) for i in range(len(runs)) for j in range(i + 1, len(runs))]
    suite_ids = {run.suite_id for run in runs}
    title = title or ("modelbench — " + " vs ".join(labels))
    lines: list[str] = [f"# {title}", ""]

    if len(runs) == 1:
        m = metrics[0]
        lines += [
            f"Single run on suite `{runs[0].suite_id}`: **{pct(m['first_score'])}** mean first-attempt "
            f"task score, {pct(m['solved_first'])} of attempts fully solved before feedback.",
            "",
        ]
    else:
        best = max(range(len(runs)), key=lambda i: metrics[i]["first_score"])
        lead = sorted(range(len(runs)), key=lambda i: metrics[i]["first_score"], reverse=True)
        line = (
            f"**{labels[lead[0]]}** leads on first-attempt quality "
            f"({pct(metrics[lead[0]]['first_score'])} vs {pct(metrics[lead[1]]['first_score'])}"
        )
        if len(runs) > 2:
            line = f"**{labels[best]}** leads on first-attempt quality ("
            line += ", ".join(f"{labels[i]} {pct(metrics[i]['first_score'])}" for i in lead) + ")"
        else:
            line += ")"
        pair = next((p for p in pairs if p.a == labels[lead[0]] or p.b == labels[lead[0]]), None)
        if pair and len(runs) == 2:
            first = pair.a == labels[lead[0]]
            wins = pair.wins_a if first else pair.wins_b
            other = pair.b if first else pair.a
            line += f", winning {wins} of {len(pair.common)} tasks against {other} ({pair.ties} tie(s)); "
            line += (
                f"after one feedback turn it is {pct(metrics[lead[0]]['final_score'])} vs "
                f"{pct(metrics[lead[1]]['final_score'])}."
            )
        else:
            line += "."
        lines += [line, ""]
        if pair and pair.identical:
            lines += [
                f"Both runs score identically on all {len(pair.common)} common tasks; there is no "
                "gap to test. That is a statement about this suite, not about the models.",
                "",
            ]
        elif pair and len(runs) == 2:
            gap = pair.gap_pp
            ci = pair.gap_ci
            ci_text = f"{_signed_pp(ci[0])} to {_signed_pp(ci[1])} pp" if ci else "no interval"
            evidence = (
                f"95% CI {ci_text}, two-sided sign test {fmt_p(pair.p_value)} over "
                f"{pair.wins_a + pair.wins_b} decided task{'s' if pair.wins_a + pair.wins_b != 1 else ''}"
            )
            noise_clause = (
                f", against ±{pair.noise_pp:.1f} pp of run-to-run noise"
                if pair.noise_pp > 0
                else ""
            )
            if pair.significant:
                swing = (
                    f" Individual tasks still swing ±{pair.noise_pp:.1f} pp between samples — more "
                    "than the gap itself — but the direction of the gap is what holds."
                    if pair.noise_pp > gap
                    else ""
                )
                lines += [
                    f"Gap: **{_signed_pp(gap)} pp** mean per-task ({evidence}). The interval "
                    "excludes zero and the sign test agrees, so the ordering holds across the "
                    f"suite rather than resting on one heavy task.{swing}",
                    "",
                ]
            elif pair.decisive and pair.noise_pp > 0:
                lines += [
                    f"**The mean gap clears the noise, but not the sign test.** Difference is "
                    f"{_signed_pp(gap)} pp mean per-task ({evidence}); the tasks move by "
                    f"±{pair.noise_pp:.1f} pp between samples. A few large wins are carrying the "
                    "mean while the suite as a whole is close — read the per-task table before "
                    "quoting a winner.",
                    "",
                ]
            elif pair.noise_pp > 0:
                lines += [
                    f"**The gap is inside the noise.** Mean per-task difference is "
                    f"{_signed_pp(gap)} pp ({evidence}), and the same tasks move by "
                    f"±{pair.noise_pp:.1f} pp between samples of one run. At this sample size "
                    "the suite cannot separate these two; raise `--samples` (and keep the seed "
                    "pinned) before quoting a winner.",
                    "",
                ]
            else:
                lines += [
                    f"**Not established.** Mean per-task difference is {_signed_pp(gap)} pp "
                    f"({evidence}). The suite cannot separate these two at this sample size; "
                    "raise `--samples` (and keep the seed pinned) before quoting a winner.",
                    "",
                ]

    lines += [
        f"_Generated {generated or now_iso()} by modelbench {__version__}. "
        f"Suite{'s' if len(suite_ids) > 1 else ''}: "
        + ", ".join(f"`{s}`" for s in sorted(suite_ids))
        + ". _",
        "",
    ]
    conflicts = sampling_conflicts(runs)
    if conflicts:
        detail = "; ".join(f"{key}: " + " vs ".join(_num(sampling(r)[key]) if sampling(r)[key] is not None else "not set" for r in runs) for key in conflicts)
        lines += [
            f"**Sampling differs between runs** ({detail}). The sampler, not just the "
            "model, differs from column to column: a few points of the gap can come from "
            "temperature or an unpinned seed. Re-run both with identical settings before "
            "reading a winner into this.",
            "",
        ]
    prov = [p for p in pairs if p.provisional(require_samples)]
    if prov and len(runs) == 2:
        pair_ = prov[0]
        lines += [
            f"**Provisional ranking — {pair_.samples_min} sample{'s' if pair_.samples_min != 1 else ''} "
            "per task.** The noise figure above is measured from how far each task moves between "
            f"its own samples; with only {pair_.samples_min} sample{'s' if pair_.samples_min != 1 else ''} "
            "that is a range across "
            f"{pair_.samples_min} point{'s' if pair_.samples_min != 1 else ''}, and it can read 0 pp or "
            "very large — neither is an estimate. Run "
            f"`--samples {require_samples}` (seed pinned) "
            "before quoting this ranking; until then read the per-task column as a leader, not a "
            "result.",
            "",
        ]
    elif prov:
        summary = ", ".join(f"{p.a} vs {p.b}: {p.samples_min}" for p in prov[:3])
        lines += [
            f"**Provisional ranking — some pairs carry fewer than {require_samples} samples per task** "
            f"({summary}). Treat close calls in those columns as unresolved.",
            "",
        ]

    lines += [
        "## Headline",
        "",
        "Scores are means over tasks (each task weighs the same), then over samples. "
        "`first` is the answer before any feedback; `final` allows one repair turn in which "
        "only failing assertion messages are returned.",
        "",
        "| metric | " + " | ".join(labels) + " |",
        "|---|" + "---|" * len(labels),
    ]

    rows: list[tuple[str, list[str]]] = headline_rows(runs, metrics)
    for label, cells in rows:
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    if any(m["cost_usd"] is not None for m in metrics):
        prices = "; ".join(
            f"**{run.label}** ${m['pricing']['input_per_mtok']:.2f} in / "
            f"${m['pricing']['output_per_mtok']:.2f} out per Mtok"
            for run, m in zip(runs, metrics)
            if m["pricing"]
        )
        lines += [
            "",
            f"Cost is estimated from the prices recorded with each run ({prices}) and counts "
            "every prompt, every completion, the feedback turn and any discarded cap retry. "
            "It is the bill, not the list price of one call.",
        ]

    # -- per task -------------------------------------------------------- #
    per_task = [per_task_metrics(run) for run in runs]
    all_tasks = sorted({task for metrics_by_task in per_task for task in metrics_by_task})
    lines += ["", "## Per task", ""]
    word = "leader" if any(p.provisional(require_samples) for p in pairs) else "winner"
    if len(runs) == 2:
        lines += [
            "| task | category | " + " | ".join(labels) + f" | Δ (pp) | {word} |",
            "|---|---|" + "---|" * len(labels) + "---|---|",
        ]
        for task in all_tasks:
            cells, values = [], []
            for m in per_task:
                entry = m.get(task)
                values.append(entry["first"] if entry else None)
                cells.append(pct(entry["first"]) if entry else MISSING)
            delta = ""
            winner = ""
            if values[0] is not None and values[1] is not None:
                d = (values[0] - values[1]) * 100
                delta = _signed_pp(d)
                winner = "tie" if abs(d) < 0.05 else (labels[0] if d > 0 else labels[1])
                row = next((r for r in pairs[0].rows if r["task"] == task), None) if pairs else None
                if row and row.get("within_noise"):
                    delta = "≈" + delta
                    winner += " (within noise)"
            category = next((m[task]["category"] for m in per_task if task in m), "")
            lines.append(f"| {task} | {category} | " + " | ".join(cells) + f" | {delta} | {winner} |")
        if pairs:
            pair = pairs[0]
            ci = pair.delta_ci
            ci_text = (
                f"95% CI {_signed_pp(ci[0])} to {_signed_pp(ci[1])} pp, "
                if ci
                else ""
            )
            lines += [
                "",
                f"Task wins: **{pair.a} {pair.wins_a}**, **{pair.b} {pair.wins_b}**, {pair.ties} ties. "
                f"Mean per-task delta: {_signed_pp(pair.mean_delta_pp)} pp "
                f"({ci_text}two-sided sign test {fmt_p(pair.p_value)}).",
            ]
            if any(row.get("within_noise") for row in pair.rows):
                lines += [
                    "",
                    "`≈` marks a delta smaller than how much that task moved between samples of "
                    "one run — a coin flip, not a result.",
                ]
    else:
        lines += ["| task | category | " + " | ".join(labels) + " | best |", "|---|---|" + "---|" * len(labels) + "---|"]
        for task in all_tasks:
            cells, values = [], []
            for m in per_task:
                entry = m.get(task)
                values.append(entry["first"] if entry else None)
                cells.append(pct(entry["first"]) if entry else MISSING)
            best_value = max((v for v in values if v is not None), default=None)
            best = MISSING
            if best_value is not None:
                best = ", ".join(labels[i] for i, v in enumerate(values) if v is not None and abs(v - best_value) < 1e-9)
            category = next((m[task]["category"] for m in per_task if task in m), "")
            lines.append(f"| {task} | {category} | " + " | ".join(cells) + f" | {best} |")

    # -- per category ---------------------------------------------------- #
    categories = sorted({c for run in runs for c in per_category_metrics(run)})
    lines += ["", "## Per category", ""]
    lines += ["| category | " + " | ".join(labels) + " |", "|---|" + "---|" * len(labels)]
    cat_metrics = [per_category_metrics(run) for run in runs]
    for category in categories:
        cells = [pct(m[category]["first"]) if category in m else MISSING for m in cat_metrics]
        lines.append(f"| {category} | " + " | ".join(cells) + " |")

    # -- failure signatures ---------------------------------------------- #
    signatures = {run.label: failure_signatures(run) for run in runs}
    merged: dict[str, dict[str, dict]] = {}
    for label, rows in signatures.items():
        for row in rows:
            merged.setdefault(row["name"], {})[label] = row
    if merged:
        ordered = sorted(
            merged.items(),
            key=lambda item: (-sum(row["records"] for row in item[1].values()), item[0]),
        )[:12]
        lines += [
            "",
            "## Where it fails",
            "",
            "Failing assertions from the first attempt, counted once per record and grouped by "
            "assertion name. A name that fails in both samples of a task is a systematic gap, "
            "not noise.",
            "",
            "| assertion | " + " | ".join(labels) + " |",
            "|---|" + "---|" * len(labels),
        ]
        for name, per_run in ordered:
            cells = []
            for label in labels:
                row = per_run.get(label)
                cells.append(
                    f"{_count(row['records'], 'record')}, {_count(row['task_count'], 'task')}"
                    if row
                    else MISSING
                )
            lines.append(f"| `{name}` | " + " | ".join(cells) + " |")

    # -- provenance ------------------------------------------------------ #
    lines += ["", "## Provenance", ""]
    lines += [
        "| run | endpoint | served id | samples | records | suite | digest |",
        "|---|---|---|---|---|---|---|",
    ]
    for run, m in zip(runs, metrics):
        target = run.header.get("target") or {}
        served = target.get("served_id") or run.records[0].get("served_id") or target.get("model") or ""
        base_url = target.get("base_url") or ""
        digest = (run.header.get("suite") or {}).get("digest") or run.records[0].get("suite_digest") or ""
        lines.append(
            f"| {run.label} | {base_url} | {served} | {m['samples']} | {m['records']}/{m['expected']} | "
            f"`{run.suite_id}` | `{digest[:12]}` |"
        )
    lines += [""]
    for run in runs:
        seed_state = sampling(run)["seed"]
        pinned = "pinned" if seed_state is not None else "**not pinned** — this run is not reproducible"
        lines.append(f"- **{run.label}** — {sampling_note(run)} ({pinned})")
    lines += [
        "",
        "Sample *n* of a task uses `seed + n - 1`, so independent samples are independent "
        "while the run stays repeatable. Backends differ in how honestly they honour a "
        "seed: llama.cpp with a fixed seed and a warm cache is close to deterministic, "
        "some hosted providers ignore it entirely. The sample-stability rows above are "
        "how you find out which kind you are talking to.",
    ]

    # -- integrity ------------------------------------------------------- #
    lines += ["", "## Integrity", ""]
    any_issue = False
    for run, m in zip(runs, metrics):
        if m["missing"]:
            any_issue = True
            preview = ", ".join(f"{x['task']} s{x['sample']}" for x in m["missing"][:6])
            more = f" (+{len(m['missing']) - 6} more)" if len(m["missing"]) > 6 else ""
            lines.append(f"- **{run.label}**: {_count(len(m['missing']), 'missing record')}: {preview}{more}")
        if m["duplicates"]:
            any_issue = True
            lines.append(f"- **{run.label}**: {_count(len(m['duplicates']), 'duplicated task/sample record')}")
        if m["truncated"]:
            any_issue = True
            lines.append(f"- **{run.label}**: {_count(m['truncated'], 'first answer')} hit the token cap")
        if m["no_result"]:
            any_issue = True
            lines.append(f"- **{run.label}**: {_count(m['no_result'], 'grader run')} produced no `RESULT` line")
        raw = m["sources"].get("raw", 0)
        unclosed = m["sources"].get("fence-unclosed", 0)
        if raw:
            any_issue = True
            lines.append(f"- **{run.label}**: {_count(raw, 'answer')} had no code fence and were graded verbatim")
        if unclosed:
            lines.append(f"- **{run.label}**: {_count(unclosed, 'answer')} ended inside an unclosed fence (salvaged)")
        if m["errors"]:
            lines.append(f"- **{run.label}**: {m['errors']} record(s) carry a run error")
        if not m["missing"] and not m["duplicates"]:
            lines.append(
                f"- **{run.label}**: complete — {m['records']} of {m['expected']} expected records, no duplicates"
            )
    if not any_issue and runs:
        lines.append("")
        lines.append("No integrity problems detected.")

    if notes:
        lines += ["", "## Notes", "", notes.strip()]

    lines += [
        "",
        "## Reproducing this report",
        "",
        "```bash",
        "# one target from your modelbench.toml",
    ]
    for run in runs:
        target = (run.header.get("target") or {}).get("name") or run.label
        lines.append(f"modelbench run --target {target} --suite {run.suite_id} --samples {run.samples} --out runs/{target}")
    lines += [
        "modelbench report runs/" + " runs/".join(
            ((run.header.get("target") or {}).get("name") or run.label) for run in runs
        ),
        "```",
        "",
        "Exact prompts, raw model output and extracted solutions for every record are stored "
        "next to `results.jsonl` in each run directory (`s<N>/raw/`, `s<N>/sol/`).",
        "",
    ]
    return "\n".join(lines)


def render_json(runs: Sequence[Run], title: str | None = None, require_samples: int = 3) -> dict:
    payload = {
        "generated_at": now_iso(),
        "modelbench": __version__,
        "title": title or " vs ".join(run.label for run in runs),
        "runs": [],
        "pairwise": [],
        "evidence": {},
    }
    for run in runs:
        payload["runs"].append(
            {
                "label": run.label,
                "path": str(run.path),
                "target": run.header.get("target") or {},
                "served_id": run.records[0].get("served_id"),
                "suite": run.header.get("suite") or {"id": run.suite_id},
                "metrics": run_metrics(run),
                "tasks": per_task_metrics(run),
                "categories": per_category_metrics(run),
                "signatures": failure_signatures(run),
            }
        )
    for i in range(len(runs)):
        for j in range(i + 1, len(runs)):
            pair = pairwise(runs[i], runs[j])
            payload["pairwise"].append(
                {
                    "a": pair.a,
                    "b": pair.b,
                    "wins_a": pair.wins_a,
                    "wins_b": pair.wins_b,
                    "ties": pair.ties,
                    "mean_delta_pp": round(pair.mean_delta_pp, 2),
                    "gap_pp": round(pair.gap_pp, 2),
                    "gap_ci_pp": [round(v, 2) for v in pair.gap_ci] if pair.gap_ci else None,
                    "noise_pp": round(pair.noise_pp, 2),
                    "decisive": pair.decisive,
                    "delta_ci_pp": [round(v, 2) for v in pair.delta_ci] if pair.delta_ci else None,
                    "p_value": round(pair.p_value, 4),
                    "significant": pair.significant,
                    "samples_per_task": pair.samples_min,
                    "provisional": pair.provisional(require_samples),
                    "tasks": pair.rows,
                }
            )
    pairs = [pairwise(runs[i], runs[j]) for i in range(len(runs)) for j in range(i + 1, len(runs))]
    payload["evidence"] = {
        "samples_required": require_samples,
        "samples_per_task": (
            min(p.samples_min for p in pairs) if pairs else (runs[0].samples if runs else 0)
        ),
        "provisional": any(p.provisional(require_samples) for p in pairs),
    }
    return payload


_CSS = """
:root{
  --bg:#0a0f15; --panel:#111922; --panel2:#0d151d; --line:#1e2a36;
  --text:#e6edf4; --muted:#8b9aab; --accent:#22d3ee; --accent2:#6366f1;
  --full:#34d399; --high:#a3e635; --mid:#fbbf24; --low:#fb923c; --zero:#f87171;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 20% -10%,#122334 0%,var(--bg) 60%);
  color:var(--text);font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto;padding:52px 24px 72px}
h1{font-size:clamp(28px,4.4vw,46px);line-height:1.1;margin:0 0 10px;letter-spacing:-.02em;
  background:linear-gradient(92deg,var(--accent),var(--accent2));-webkit-background-clip:text;
  background-clip:text;color:transparent}
.lede{color:var(--muted);margin:0 0 34px;max-width:70ch}
.warn{background:rgba(245,158,11,.09);border:1px solid rgba(245,158,11,.35);border-left:3px solid #f59e0b;border-radius:10px;padding:14px 18px;margin:0 0 30px;color:#fcd8a0;font-size:13.5px;line-height:1.6;max-width:92ch}
.warn b{color:#fbbf24}.bad{color:#f87171}
h2{font-size:13px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
  margin:0 0 12px;font-weight:600}
section{margin:38px 0}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:14px}
.card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);
  border-radius:14px;padding:18px 18px 14px}
.card header{display:flex;align-items:center;gap:8px;justify-content:space-between}
.card h3{margin:0;font-size:15px;font-weight:600;overflow-wrap:anywhere}
.big{font-size:34px;font-weight:700;margin:10px 0 2px;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
.sub{color:var(--muted);font-size:12.5px;margin:0 0 12px}
dl{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;margin:0;font-size:12.5px}
dl div{display:flex;justify-content:space-between;gap:8px;border-top:1px solid var(--line);padding-top:6px}
dt{color:var(--muted)}dd{margin:0;font-variant-numeric:tabular-nums}
dl.stack{grid-template-columns:1fr}
dl.stack div{justify-content:space-between}
.badge{font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:#04212a;
  background:var(--accent);border-radius:999px;padding:3px 8px;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;font-size:11px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);
  font-weight:600;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th.num,td.num{text-align:right;font-variant-numeric:tabular-nums}
table.sortable th[data-sort]{cursor:pointer;user-select:none}
table.sortable th[data-sort]:hover{color:var(--text)}
table.sortable th[data-dir="asc"]::after{content:" ↑";color:var(--accent)}
table.sortable th[data-dir="desc"]::after{content:" ↓";color:var(--accent)}
td{padding:9px 10px;border-bottom:1px solid #18212b;vertical-align:middle}
tbody tr:hover{background:#101923}
td.task{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
.tag{font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:2px 8px}
.pct{display:block}
.bar{display:block;height:4px;border-radius:3px;background:#1b2632;margin-top:5px;overflow:hidden}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2))}
.full .pct,.full.big{color:var(--full)} .high .pct,.high.big{color:var(--high)}
.mid .pct,.mid.big{color:var(--mid)} .low .pct,.low.big{color:var(--low)}
.zero .pct,.zero.big{color:var(--zero)}
.muted{color:var(--muted)}
td .sub{display:block;margin:2px 0 0;font-size:11px}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:28px}
ul.chips{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:6px}
ul.chips li{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;
  background:#132030;border:1px solid var(--line);border-radius:7px;padding:3px 8px}
ul.issues{list-style:none;padding:0;margin:0;font-size:13px}
ul.issues li{padding:7px 0;border-bottom:1px solid #18212b}
ul.issues li b{color:var(--text)}
.ok{color:var(--full)}
pre{background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:14px;
  overflow:auto;font-size:12.5px;line-height:1.6}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
footer{color:var(--muted);font-size:12px;margin-top:44px;border-top:1px solid var(--line);padding-top:14px}
@media (prefers-reduced-motion:no-preference){tbody tr{transition:background .12s ease}}
"""

_JS = """
document.querySelectorAll("table.sortable").forEach(function (table) {
  var body = table.tBodies[0];
  if (!body) return;
  table.querySelectorAll("th[data-sort]").forEach(function (th, index) {
    th.addEventListener("click", function () {
      var dir = th.dataset.dir === "asc" ? -1 : 1;
      table.querySelectorAll("th").forEach(function (other) { delete other.dataset.dir; });
      th.dataset.dir = dir === 1 ? "asc" : "desc";
      var rows = Array.prototype.slice.call(body.rows);
      rows.sort(function (a, b) {
        var av = a.cells[index] ? (a.cells[index].dataset.value || a.cells[index].textContent) : "";
        var bv = b.cells[index] ? (b.cells[index].dataset.value || b.cells[index].textContent) : "";
        var an = parseFloat(av), bn = parseFloat(bv);
        var cmp = (!isNaN(an) && !isNaN(bn)) ? an - bn : String(av).localeCompare(String(bv));
        return cmp * dir;
      });
      rows.forEach(function (row) { body.appendChild(row); });
    });
  });
});
"""


def _esc(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def _score_class(score: float) -> str:
    if score >= 0.999:
        return "full"
    if score >= 0.85:
        return "high"
    if score >= 0.6:
        return "mid"
    if score > 0:
        return "low"
    return "zero"


def _score_cell(score: float | None) -> str:
    if score is None:
        return f'<td class="num muted">{MISSING}</td>'
    width = max(0.0, min(1.0, score)) * 100
    return (
        f'<td class="num {_score_class(score)}" data-value="{score:.4f}">'
        f'<span class="pct">{score * 100:.1f}%</span>'
        f'<span class="bar"><i style="width:{width:.1f}%"></i></span></td>'
    )


def render_html(
    runs: Sequence[Run],
    title: str | None = None,
    notes: str | None = None,
    generated: str | None = None,
    require_samples: int = 3,
) -> str:
    """A single self-contained page: no assets, no network, opens from disk."""
    metrics = [run_metrics(run) for run in runs]
    labels = [run.label for run in runs]
    per_task = [per_task_metrics(run) for run in runs]
    cat_metrics = [per_category_metrics(run) for run in runs]
    suite_ids = sorted({run.suite_id for run in runs})
    title = title or "modelbench — " + " vs ".join(labels)
    generated = generated or now_iso()
    best_index = max(range(len(runs)), key=lambda i: metrics[i]["first_score"]) if runs else 0
    pair = pairwise(runs[0], runs[1]) if len(runs) == 2 else None
    pairs = [pairwise(runs[i], runs[j]) for i in range(len(runs)) for j in range(i + 1, len(runs))]
    parts: list[str] = []

    parts.append(
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
        "<meta name=\"color-scheme\" content=\"dark\">\n"
        f"<title>{_esc(title)}</title>\n<style>{_CSS}</style>\n</head>\n<body>\n<div class=\"wrap\">"
    )
    parts.append(f"<h1>{_esc(title)}</h1>")
    lede = (
        f"{len(runs)} run{'s' if len(runs) != 1 else ''} · suite{'s' if len(suite_ids) > 1 else ''} "
        + ", ".join(f"<code>{_esc(s)}</code>" for s in suite_ids)
        + f" · generated {_esc(generated)} by modelbench {__version__}."
    )
    parts.append(f'<p class="lede">{lede}</p>')

    conflicts = sampling_conflicts(runs)
    if conflicts:
        detail = "; ".join(
            f"{key}: "
            + " vs ".join(
                _num(sampling(r)[key]) if sampling(r)[key] is not None else "not set" for r in runs
            )
            for key in conflicts
        )
        parts.append(
            '<div class="warn"><b>Sampling differs between runs.</b> '
            f"{_esc(detail)}. The sampler, not just the model, differs from column to column: "
            "a few points of the gap can come from temperature or an unpinned seed. Re-run both "
            "with identical settings before reading a winner into this.</div>"
        )

    if any(p.provisional(require_samples) for p in pairs):
        thin = min(p.samples_min for p in pairs if p.samples_min) if pairs else 0
        parts.append(
            '<div class="warn"><b>Provisional ranking.</b> '
            f"Only {thin} sample{'s' if thin != 1 else ''} per task: the noise figure is a "
            f"range across {thin} point{'s' if thin != 1 else ''}, not an estimate. Run "
            f"<code>--samples {require_samples}</code> (seed pinned) before quoting this ranking; "
            "until then the per-task column names a leader, not a winner.</div>"
        )

    # -- cards ------------------------------------------------------------ #
    cards = ['<section><h2>At a glance</h2><div class="cards">']
    for index, (run, m) in enumerate(zip(runs, metrics)):
        delta = ""
        if len(runs) > 1:
            gap = (m["first_score"] - metrics[best_index]["first_score"]) * 100
            delta = f"({_signed_pp(gap)} pp vs best)"
        badge = '<span class="badge">best</span>' if index == best_index and len(runs) > 1 else ""
        bits = ["first attempt"]
        if m["first_ci"]:
            bits.append("95% CI " + ci_pct(m["first_ci"]))
        if index == best_index and len(runs) > 1:
            bits.append("leader")
        elif delta:
            bits.append(delta.strip("()"))
        sub = " · ".join(bits)
        cards.append(
            '<article class="card">'
            f'<header><h3>{_esc(run.label)}</h3>{badge}</header>'
            f'<p class="big {_score_class(m["first_score"])}">{pct(m["first_score"])}</p>'
            f'<p class="sub">{sub}</p>'
            '<dl class="stack">'
            f'<div><dt>final (after repair)</dt><dd>{pct(m["final_score"])}</dd></div>'
            f'<div><dt>fully solved, first</dt><dd>{pct(m["solved_first"])}</dd></div>'
            f'<div><dt>records</dt><dd>{m["records"]}/{m["expected"]}</dd></div>'
            f'<div><dt>median decode</dt><dd>{m["median_tps"]:.1f} tok/s</dd></div>'
            f'<div><dt>output tokens</dt><dd>{m["total_tokens"]:,}</dd></div>'
            + (f'<div><dt>cost</dt><dd>{_usd(m["cost_usd"])}</dd></div>' if m["cost_usd"] is not None else "")
            + f'<div><dt>wall clock</dt><dd>{m["wall_s"] / 60:.1f} min</dd></div>'
            "</dl></article>"
        )
    cards.append("</div></section>")
    parts.append("\n".join(cards))

    # -- headline --------------------------------------------------------- #
    head = "".join(f'<th class="num" data-sort="num">{_esc(label)}</th>' for label in labels)
    body = []
    for label, cells in headline_rows(runs, metrics):
        tds = "".join(f'<td class="num">{_esc(cell)}</td>' for cell in cells)
        body.append(f"<tr><td>{_esc(label)}</td>{tds}</tr>")
    parts.append(
        '<section><h2>Headline</h2><p class="sub">Scores are means over tasks (equal weight), '
        "then over samples. <code>first</code> is the answer before any feedback; "
        "<code>final</code> allows one repair turn carrying only failing assertion names.</p>"
        f'<table class="sortable"><thead><tr><th>metric</th>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></section>"
    )

    # -- per task --------------------------------------------------------- #
    all_tasks = sorted({task for metrics_by_task in per_task for task in metrics_by_task})
    head_cells = "".join(f'<th class="num" data-sort="num">{_esc(label)}</th>' for label in labels)
    word = "leader" if any(p.provisional(require_samples) for p in pairs) else "winner"
    if len(runs) == 2:
        head_cells += f'<th class="num" data-sort="num">Δ pp</th><th>{word}</th>'
    else:
        head_cells += "<th>best</th>"
    body = []
    for task in all_tasks:
        values = [m.get(task, {}).get("first") for m in per_task]
        category = next((m[task]["category"] for m in per_task if task in m), "")
        cells = "".join(_score_cell(value) for value in values)
        if len(runs) == 2:
            left, right = values
            if left is None or right is None:
                tail = f'<td class="num muted">{MISSING}</td><td></td>'
            else:
                delta = (left - right) * 100
                winner = "tie" if abs(delta) < 0.05 else (labels[0] if delta > 0 else labels[1])
                row = next((r for r in pair.rows if r["task"] == task), None) if pair else None
                faint = row is not None and row.get("within_noise")
                shown = ("≈" + _signed_pp(delta)) if faint else _signed_pp(delta)
                tooltip = f' title="±{row["noise_pp"]:.1f} pp between samples"' if faint else ""
                winner_cell = _esc(winner) + ('<span class="sub">within noise</span>' if faint else "")
                tail = (
                    f'<td class="num{" muted" if faint else ""}" data-value="{delta:.2f}"{tooltip}>'
                    f"{shown}</td>"
                    f"<td>{winner_cell}</td>"
                )
        else:
            known = [v for v in values if v is not None]
            top = max(known) if known else None
            names = ", ".join(labels[i] for i, v in enumerate(values) if v is not None and top is not None and abs(v - top) < 1e-9)
            tail = f'<td>{_esc(names) or MISSING}</td>'
        body.append(
            f'<tr><td class="task">{_esc(task)}</td><td>{_esc(category)}</td>{cells}{tail}</tr>'
        )
    note = ""
    if pair and pair.identical:
        note = (
            f'<p class="sub">Both runs score identically on all {len(pair.common)} common tasks; '
            "there is no gap to test.</p>"
        )
    elif pair:
        ci = pair.gap_ci
        ci_text = (
            f" · 95% CI {_signed_pp(ci[0])} to {_signed_pp(ci[1])} pp" if ci else ""
        )
        note = (
            f'<p class="sub">Task wins: <b>{_esc(pair.a)} {pair.wins_a}</b>, '
            f"<b>{_esc(pair.b)} {pair.wins_b}</b>, {pair.ties} tie(s) · mean per-task delta "
            f"{_signed_pp(pair.gap_pp)} pp{ci_text} · sign test {fmt_p(pair.p_value)}</p>"
        )
        if pair.significant:
            note += (
                '<p class="sub">The interval excludes zero and the sign test agrees: the '
                "ordering holds across the suite, not just on one heavy task.</p>"
            )
        elif pair.decisive and pair.noise_pp > 0:
            note = (
                '<div class="warn"><b>The mean gap clears the noise, but not the sign test.</b> '
                "A few large wins are carrying the mean while the suite as a whole is close — "
                "read the per-task table before quoting a winner.</div>"
            ) + note
        elif pair.noise_pp > 0:
            note = (
                '<div class="warn"><b>The gap is inside the noise.</b> '
                f"Mean per-task difference is {_signed_pp(pair.mean_delta_pp)} pp while the "
                f"same tasks move by ±{pair.noise_pp:.1f} pp between samples of one run. "
                "At this sample size the suite cannot separate these two — raise "
                "<code>--samples</code> (seed pinned) before quoting a winner.</div>"
            ) + note
        else:
            note = (
                '<div class="warn"><b>Not established.</b> The interval for the mean per-task '
                "delta includes zero; at this sample size the suite cannot separate these two."
                "</div>"
            ) + note
    parts.append(
        '<section><h2>Per task</h2>'
        f"{note}<table class=\"sortable\"><thead><tr><th data-sort=\"text\">task</th>"
        f'<th data-sort="text">category</th>{head_cells}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></section>"
    )

    # -- per category ----------------------------------------------------- #
    categories = sorted({c for m in cat_metrics for c in m})
    head_cells = "".join(f'<th class="num" data-sort="num">{_esc(label)}</th>' for label in labels)
    body = []
    for category in categories:
        cells = "".join(
            _score_cell(m[category]["first"] if category in m else None) for m in cat_metrics
        )
        body.append(f'<tr><td>{_esc(category)}</td>{cells}</tr>')
    parts.append(
        '<section><h2>Per category</h2><table class="sortable"><thead><tr>'
        f'<th data-sort="text">category</th>{head_cells}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></section>"
    )

    # -- stability + failure signatures ----------------------------------- #
    stability = ['<section><h2>Sample stability</h2>']
    for run, m in zip(runs, metrics):
        if m["samples"] < 2:
            stability.append(
                f'<p class="sub"><b>{_esc(run.label)}</b>: one sample per task — stability '
                "cannot be measured. Use <code>--samples 2</code> or more.</p>"
            )
            continue
        if m["unstable_ids"]:
            chips = "".join(f"<li>{_esc(task)}</li>" for task in m["unstable_ids"])
            stability.append(
                f'<p class="sub"><b>{_esc(run.label)}</b>: {m["unstable"]} of {m["tasks"]} tasks '
                f'changed score between samples (mean spread {m["sample_spread"] * 100:.1f} pp).</p>'
                f'<ul class="chips">{chips}</ul>'
            )
        else:
            stability.append(
                f'<p class="sub"><b>{_esc(run.label)}</b>: no task changed score between samples '
                f'({m["samples"]} samples each).</p>'
            )
    stability.append("</section>")

    merged: dict[str, dict[str, dict]] = {}
    for run in runs:
        for row in failure_signatures(run):
            merged.setdefault(row["name"], {})[run.label] = row
    failures = ['<section><h2>Where it fails</h2>']
    if merged:
        ordered = sorted(
            merged.items(), key=lambda item: (-sum(r["records"] for r in item[1].values()), item[0])
        )[:12]
        head_cells = "".join(f'<th class="num">{_esc(label)}</th>' for label in labels)
        rows = []
        for name, per_run in ordered:
            cells = []
            for label in labels:
                row = per_run.get(label)
                cells.append(
                    f'<td class="num" data-value="{row["records"]}">{row["records"]}'
                    f'<span class="sub">{_count(row["task_count"], "task")}</span></td>'
                    if row
                    else f'<td class="num muted">{MISSING}</td>'
                )
            rows.append(f'<tr><td class="task">{_esc(name)}</td>{"".join(cells)}</tr>')
        failures.append(
            '<p class="sub">Failing assertions of the first attempt, counted once per record.</p>'
            f'<table><thead><tr><th>assertion</th>{head_cells}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table>"
        )
    else:
        failures.append('<p class="sub">No failing assertions were recorded.</p>')
    failures.append("</section>")
    parts.append('<div class="grid2">' + "".join(stability) + "".join(failures) + "</div>")

    # -- provenance ------------------------------------------------------- #
    rows = []
    for run, m in zip(runs, metrics):
        target = run.header.get("target") or {}
        served = target.get("served_id") or run.records[0].get("served_id") or target.get("model") or ""
        digest = (run.header.get("suite") or {}).get("digest") or run.records[0].get("suite_digest") or ""
        s = sampling(run)
        if s["seed"] is None:
            seed_cell = '<span class="bad">not pinned</span>'
        elif run.samples > 1:
            seed_cell = f'<code>{s["seed"]}</code> <span class="muted">+1/sample</span>'
        else:
            seed_cell = f'<code>{s["seed"]}</code>'
        temp_cell = _num(s["temperature"]) if s["temperature"] is not None else '<span class="muted">—</span>'
        rows.append(
            f"<tr><td>{_esc(run.label)}</td><td>{_esc(target.get('base_url') or '')}</td>"
            f"<td>{_esc(served)}</td><td class=\"num\">{m['samples']}</td>"
            f"<td class=\"num\">{m['records']}/{m['expected']}</td>"
            f"<td class=\"num\">{temp_cell}</td>"
            f"<td class=\"num\">{seed_cell}</td>"
            f"<td><code>{_esc(run.suite_id)}</code></td>"
            f"<td><code>{_esc(digest[:12])}</code></td></tr>"
        )
    parts.append(
        '<section><h2>Provenance</h2><table><thead><tr><th>run</th><th>endpoint</th>'
        "<th>served id</th><th class=\"num\">samples</th><th class=\"num\">records</th>"
        "<th class=\"num\">temp</th><th class=\"num\">seed</th>"
        f"<th>suite</th><th>digest</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>"
    )

    # -- integrity -------------------------------------------------------- #
    issues: list[str] = []
    for run, m in zip(runs, metrics):
        who = _esc(run.label)
        if m["missing"]:
            preview = ", ".join(f"{x['task']} s{x['sample']}" for x in m["missing"][:6])
            more = f" (+{len(m['missing']) - 6} more)" if len(m["missing"]) > 6 else ""
            issues.append(f"<li><b>{who}</b>: {_count(len(m['missing']), 'missing record')}: {_esc(preview)}{more}</li>")
        if m["duplicates"]:
            issues.append(f"<li><b>{who}</b>: {_count(len(m['duplicates']), 'duplicated task/sample record')}</li>")
        if m["truncated"]:
            issues.append(f"<li><b>{who}</b>: {_count(m['truncated'], 'first answer')} hit the token cap</li>")
        if m["no_result"]:
            issues.append(f"<li><b>{who}</b>: {_count(m['no_result'], 'grader run')} produced no <code>RESULT</code> line</li>")
        if m["sources"].get("raw"):
            issues.append(f"<li><b>{who}</b>: {_count(m['sources']['raw'], 'answer')} had no code fence and were graded verbatim</li>")
        if m["sources"].get("fence-unclosed"):
            issues.append(f"<li><b>{who}</b>: {_count(m['sources']['fence-unclosed'], 'answer')} ended inside an unclosed fence (salvaged)</li>")
        if m["errors"]:
            issues.append(f"<li><b>{who}</b>: {_count(m['errors'], 'record')} carry a run error</li>")
        if not m["missing"] and not m["duplicates"]:
            issues.append(
                f'<li><b>{who}</b>: complete — {m["records"]} of {m["expected"]} expected records, '
                'no duplicates <span class="ok">✓</span></li>'
            )
    parts.append(
        '<section><h2>Integrity</h2><ul class="issues">'
        + ("".join(issues) or "<li>No runs to check.</li>")
        + "</ul></section>"
    )

    # -- reproduce -------------------------------------------------------- #
    commands = []
    for run in runs:
        target = (run.header.get("target") or {}).get("name") or run.label
        commands.append(
            f"modelbench run --target {target} --suite {run.suite_id} --samples {run.samples} --out runs/{target}"
        )
    commands.append("modelbench report " + " ".join(f"runs/{((r.header.get('target') or {}).get('name') or r.label)}" for r in runs))
    parts.append(
        '<section><h2>Reproduce</h2><pre><code>'
        + _esc("\n".join(commands))
        + "</code></pre><p class=\"sub\">Raw model output and extracted solutions for every record "
        "live next to <code>results.jsonl</code> in <code>s&lt;N&gt;/raw/</code> and "
        "<code>s&lt;N&gt;/sol/</code>.</p></section>"
    )

    if notes:
        parts.append(f'<section><h2>Notes</h2><p>{_esc(notes.strip()).replace(chr(10), "<br>")}</p></section>')

    parts.append(
        f'<footer>Generated {_esc(generated)} by modelbench {__version__} · '
        f"{_esc(', '.join(suite_ids))} · click a column header to sort.</footer>"
    )
    parts.append(f"</div>\n<script>{_JS}</script>\n</body>\n</html>\n")
    return "\n".join(parts)


def render_console(runs: Sequence[Run], require_samples: int = 3) -> str:
    metrics = [run_metrics(run) for run in runs]
    priced = any(m["cost_usd"] is not None for m in metrics)
    rows = []
    for run, m in zip(runs, metrics):
        row = [
            run.label,
            pct(m["first_score"]),
            pct(m["final_score"]),
            pct(m["solved_first"]),
            f"{m['records']}/{m['expected']}",
            f"{m['median_call_s']:.1f}s",
            f"{m['median_tps']:.1f}" if m["median_tps"] else MISSING,
            f"{m['total_tokens']:,}",
        ]
        if priced:
            row.append(_usd(m["cost_usd"]))
        rows.append(row)
    headers = ["run", "first", "final", "solved", "records", "med call", "tok/s", "tokens"]
    if priced:
        headers.append("cost")
    table = column_table(
        headers,
        rows,
        align=["l"] + ["r"] * (len(headers) - 1),
    )
    lines = [table]
    if len(runs) == 2:
        pair = pairwise(runs[0], runs[1])
        flags: list[str] = []
        if pair.identical:
            flags.append("identical on every common task")
        else:
            if pair.significant:
                flags.append("difference established")
            elif not pair.decisive and pair.noise_pp > 0:
                flags.append("gap inside noise")
            else:
                flags.append("not established")
            if pair.provisional(require_samples):
                flags.append(f"provisional at {pair.samples_min} sample(s)/task")
        verdict = " · ".join(flags)
        gap_ci = pair.gap_ci
        ci = f" · 95% CI {_signed_pp(gap_ci[0])} to {_signed_pp(gap_ci[1])} pp" if gap_ci else ""
        noise = f" · task spread ±{pair.noise_pp:.1f} pp" if pair.noise_pp else ""
        ahead = pair.a if pair.mean_delta_pp > 0 else pair.b
        lines.append(
            f"\ntask wins: {pair.a} {pair.wins_a}, {pair.b} {pair.wins_b}, ties {pair.ties} "
            f"(mean gap {_signed_pp(pair.gap_pp)} pp in favour of {ahead}{ci}{noise} · "
            f"sign test {fmt_p(pair.p_value)} · {verdict})"
        )
    return "\n".join(lines)


def write_reports(
    runs: Sequence[Run],
    out_dir: str | Path,
    title: str | None = None,
    notes: str | None = None,
    html: bool = True,
    html_name: str = "REPORT.html",
    require_samples: int = 3,
) -> dict[str, Path | None]:
    """Write REPORT.md, summary.json and (by default) a standalone REPORT.html.

    Returns the paths that were written, keyed by format, so callers can print
    exactly what exists instead of guessing.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(runs, title=title, notes=notes, require_samples=require_samples)
    md_path = out / "REPORT.md"
    md_path.write_text(markdown, encoding="utf-8")
    json_path = out / "summary.json"
    write_json(json_path, render_json(runs, title=title, require_samples=require_samples))
    html_path: Path | None = None
    if html:
        html_path = out / html_name
        html_path.write_text(
            render_html(runs, title=title, notes=notes, require_samples=require_samples),
            encoding="utf-8",
        )
    return {"markdown": md_path, "json": json_path, "html": html_path}


def discover_runs(root: str | Path) -> list[Path]:
    """Every run directory below *root* (a directory holding run.json/results.jsonl)."""
    root = Path(root).expanduser()
    if (root / "results.jsonl").is_file():
        return [root]
    found = []
    for candidate in sorted(root.iterdir()) if root.is_dir() else []:
        if not candidate.is_dir():
            continue
        if (candidate / "results.jsonl").is_file():
            found.append(candidate)
    return found


def dump_json(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)
