"""A model over time: every run of the same target, oldest first.

A leaderboard answers "who is best today". The question that decides whether a
new quant, a new sampler default or a new build actually changed anything is a
different one: "what did this model score last time, and is today's number
inside the noise of yesterday's". That needs the runs in order, the delta
between them, and a note when the suite itself moved underneath the series.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .report import Run, load_run, run_metrics
from .tui import sparkline
from .util import pct


def _ci(pair: tuple[float, float] | None) -> str:
    return f"{pair[0] * 100:.1f}–{pair[1] * 100:.1f}%" if pair else "—"


def build(paths: Iterable[str | Path], by: str = "first") -> dict:
    runs: list[Run] = []
    for path in paths:
        try:
            runs.append(load_run(path))
        except (OSError, ValueError):
            continue
    if not runs:
        raise ValueError("no readable runs given")
    ordered = sorted(
        runs,
        key=lambda run: (
            str((run.header or {}).get("started_at") or ""),
            run.label,
        ),
    )
    rows: list[dict] = []
    previous: dict[str, float] = {}
    for run in ordered:
        metrics = run_metrics(run)
        score = metrics["first_score"] if by == "first" else metrics["final_score"]
        ci = metrics["first_ci"] if by == "first" else metrics["final_ci"]
        started = str((run.header or {}).get("started_at") or "")
        digest = str((run.header.get("suite") or {}).get("digest") or "")
        delta = None
        if run.label in previous:
            delta = (score - previous[run.label]) * 100
        previous[run.label] = score
        rows.append(
            {
                "label": run.label,
                "when": started,
                "suite": run.suite_id,
                "digest": digest[:12],
                "samples": run.samples,
                "records": metrics["records"],
                "expected": metrics["expected"],
                "score": score,
                "ci": list(ci) if ci else None,
                "delta_pp": delta,
                "status": str((run.header or {}).get("status") or "?"),
                "median_tps": metrics["median_tps"],
            }
        )
    series = sorted({row["label"] for row in rows})
    return {"by": by, "runs": rows, "series": series, "count": len(rows)}


def render_console(payload: dict) -> str:
    rows = payload["runs"]
    if not rows:
        return "no runs found"
    by = payload["by"]
    width = max((len(row["label"]) for row in rows), default=5) + 2
    lines = [
        f"{len(rows)} run(s), oldest first · ranked by the {by}-attempt score",
        "",
        f"{'when':<17} {'target':<{width}} {'suite':<12} {'smp':>3} {'records':>9} "
        f"{'score':>7} {'95% CI':>15} {'delta':>8} {'tok/s':>6}",
    ]
    for row in rows:
        when = row["when"][:16].replace("T", " ") or "—"
        delta = "—" if row["delta_pp"] is None else f"{row['delta_pp']:+.1f} pp"
        rate = f"{row['median_tps']:.1f}" if row["median_tps"] else "—"
        lines.append(
            f"{when:<17} {row['label']:<{width}} {row['suite']:<12} {row['samples']:>3} "
            f"{row['records']:>4}/{row['expected']:<4} {pct(row['score']):>7} "
            f"{_ci(tuple(row['ci']) if row['ci'] else None):>15} {delta:>8} {rate:>6}"
        )
    for label in payload["series"]:
        values = [row["score"] * 100 for row in rows if row["label"] == label]
        if len(values) >= 2:
            lines.append("")
            lines.append(f"{label:<{width}} {sparkline(values, min(48, len(values)))}  {values[0]:.0f} -> {values[-1]:.0f}")
    # A series that changes suite digest is not a time series; say so rather
    # than letting two different benchmarks share one arrow.
    changes = []
    for label in payload["series"]:
        digests = [row["digest"] for row in rows if row["label"] == label]
        if len(set(digests)) > 1:
            changes.append(f"{label} ({len(set(digests))} suite digests)")
    if changes:
        lines.append("")
        lines.append(
            "warning: the suite changed inside these series, so a delta may measure the "
            "suite and not the model: " + ", ".join(changes)
        )
    return "\n".join(lines)


def render_markdown(payload: dict) -> str:
    rows = payload["runs"]
    lines = [
        "| when | target | suite | samples | records | score | 95% CI | delta |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        delta = "—" if row["delta_pp"] is None else f"{row['delta_pp']:+.1f} pp"
        lines.append(
            f"| {row['when'][:19] or '—'} | {row['label']} | `{row['suite']}` | {row['samples']} | "
            f"{row['records']}/{row['expected']} | {pct(row['score'])} | "
            f"{_ci(tuple(row['ci']) if row['ci'] else None)} | {delta} |"
        )
    return "\n".join(lines)


def render_json(payload: dict) -> dict:
    return payload


def summary_line(payload: dict) -> str:
    """One sentence for a console epilogue or a report footer."""
    rows = payload["runs"]
    if not rows:
        return "no runs"
    first, last = rows[0], rows[-1]
    if len(rows) == 1:
        return f"one run: {last['label']} {pct(last['score'])} on {last['when'][:10] or 'an unknown date'}"
    delta = last["score"] - first["score"]
    return (
        f"{len(rows)} runs for {len(payload['series'])} target(s); "
        f"latest {last['label']} {pct(last['score'])} ({delta * 100:+.1f} pp vs first)"
    )
