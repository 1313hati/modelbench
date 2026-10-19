"""A leaderboard for the runs you actually have.

Public leaderboards compare submissions from strangers; this one compares
directories on your disk. The rule that makes it useful is the same one the
report enforces: runs from different suites, or sampled differently, are not a
ranking — they are several experiments printed next to each other. The builder
refuses that by default instead of quietly sorting it.

Two models whose confidence intervals overlap are printed as tied. That is not
a technicality: with a dozen tasks, "94.1% vs 94.6%" is a coin landing heads.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from .errors import ModelBenchError
from .report import (
    Run,
    _usd,
    ci_pct,
    load_runs,
    per_task_metrics,
    run_metrics,
    sampling,
    sampling_conflicts,
)
from .util import column_table


def _score(m: dict, by: str) -> float:
    return m["final_score"] if by == "final" else m["first_score"]


def _ci(m: dict, by: str):
    return m["final_ci"] if by == "final" else m["first_ci"]


def _overlap(a, b) -> bool:
    if not a or not b:
        return False
    return a[0] <= b[1] and b[0] <= a[1]


def build(runs: Sequence[Run], by: str = "first", allow_mixed: bool = False) -> dict:
    if not runs:
        raise ModelBenchError("no runs to rank")
    digests = {
        ((run.header.get("suite") or {}).get("digest") or (run.records[0].get("suite_digest") if run.records else ""))
        for run in runs
    }
    suites = {run.suite_id for run in runs}
    mixed = len(digests) > 1 or len(suites) > 1
    if mixed and not allow_mixed:
        raise ModelBenchError(
            "these runs come from different suites or suite versions "
            f"({', '.join(sorted(s or '?' for s in suites))}); their scores are not on one scale. "
            "Rank one suite at a time, or pass --allow-mixed to print the warning and continue."
        )

    warnings: list[str] = []
    if mixed:
        warnings.append("runs come from different suites or suite versions; the order is not a comparison")
    conflicts = sampling_conflicts(runs)
    if conflicts:
        warnings.append(
            "sampling differs between runs ("
            + ", ".join(conflicts)
            + "); part of any gap is the sampler, not the model"
        )
    if any(missing for missing in (run_metrics(r)["missing"] for r in runs)):
        warnings.append("at least one run is missing records; its score is not comparable at face value")

    rows = []
    for run in runs:
        m = run_metrics(run)
        price = m["pricing"]
        rows.append(
            {
                "label": run.label,
                "run": run,
                "path": str(run.path),
                "score": _score(m, by),
                "ci": _ci(m, by),
                "final": m["final_score"],
                "first": m["first_score"],
                "solved": m["solved_final"],
                "samples": m["samples"],
                "tasks": m["tasks"],
                "records": m["records"],
                "expected": m["expected"],
                "tps": m["median_tps"],
                "tokens": m["total_tokens"],
                "input_tokens": m["input_tokens"],
                "wall_s": m["wall_s"],
                "cost": m["cost_usd"],
                "cost_per_solved": m["cost_per_solved_usd"],
                "pricing": price,
                "suite": run.suite_id,
                "missing": len(m["missing"]),
            }
        )
    rows.sort(key=lambda r: (-r["score"], r["label"]))

    for index, row in enumerate(rows):
        tied = [
            other["label"]
            for other in rows
            if other is not row and _overlap(row["ci"], other["ci"])
        ]
        row["rank"] = index + 1
        row["tied_with"] = tied
        row["unresolved"] = bool(tied)

    # Pareto frontier: nobody beats you on both quality and token spend.
    axis = "cost" if all(r["cost"] is not None for r in rows) else "tokens"
    for row in rows:
        row["dominated_by"] = [
            other["label"]
            for other in rows
            if other is not row
            and other["score"] >= row["score"] - 1e-12
            and (other[axis] or 0) <= (row[axis] or 0)
            and (other["score"] > row["score"] or (other[axis] or 0) < (row[axis] or 0))
        ]
        row["frontier"] = not row["dominated_by"]

    return {
        "by": by,
        "axis": axis,
        "warnings": warnings,
        "rows": rows,
        "mixed": mixed,
    }


def render_markdown(payload: dict) -> str:
    by = payload["by"]
    axis = payload["axis"]
    lines = [
        f"# modelbench leaderboard — ranked by {by} score",
        "",
        f"{len(payload['rows'])} run{'s' if len(payload['rows']) != 1 else ''}. "
        "A rank is only printed when the confidence intervals separate; overlapping runs share "
        "a place and are marked `=`. The frontier column lists runs that no other run beats on "
        f"both score and {axis}.",
        "",
    ]
    for warning in payload["warnings"]:
        lines += [f"> **Warning.** {warning}", ""]
    lines += [
        "| # | model | score | 95% CI | final | solved | samples | tok/s | tokens | cost | $/solved | frontier |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in payload["rows"]:
        rank = f"{row['rank']}=" if row["unresolved"] else str(row["rank"])
        lines.append(
            "| {rank} | {label} | {score} | {ci} | {final} | {solved} | {samples} | {tps} | {tokens} | "
            "{cost} | {cps} | {frontier} |".format(
                rank=rank,
                label=row["label"],
                score=f"{row['score'] * 100:.1f}%",
                ci=ci_pct(row["ci"]),
                final=f"{row['final'] * 100:.1f}%",
                solved=f"{row['solved'] * 100:.0f}%",
                samples=row["samples"],
                tps=f"{row['tps']:.1f}" if row["tps"] else "—",
                tokens=f"{row['tokens']:,}",
                cost=_usd(row["cost"]),
                cps=_usd(row["cost_per_solved"]),
                frontier="◆" if row["frontier"] else "",
            )
        )
    ties = [r for r in payload["rows"] if r["tied_with"]]
    if ties:
        lines += ["", "## Unresolved", ""]
        for row in ties:
            lines.append(
                f"- **{row['label']}** ({row['score'] * 100:.1f}%) is not separable from "
                + ", ".join(f"**{name}**" for name in row["tied_with"])
                + " — the intervals overlap."
            )
    unresolved = [r for r in payload["rows"] if r["missing"]]
    if unresolved:
        lines += ["", "## Incomplete runs", ""]
        for row in unresolved:
            lines.append(
                f"- **{row['label']}**: {row['records']}/{row['expected']} records "
                f"({row['missing']} missing). Read its score as a partial result."
            )
    lines += [
        "",
        "Regenerate with `modelbench leaderboard <run-dirs>`. Every number here comes from "
        "`results.jsonl`; nothing is retyped.",
        "",
    ]
    return "\n".join(lines)


def render_console(payload: dict) -> str:
    rows = []
    for row in payload["rows"]:
        rank = f"{row['rank']}=" if row["unresolved"] else str(row["rank"])
        rows.append(
            [
                rank,
                row["label"],
                f"{row['score'] * 100:.1f}%",
                ci_pct(row["ci"]),
                f"{row['solved'] * 100:.0f}%",
                f"{row['tps']:.0f}" if row["tps"] else "—",
                f"{row['tokens'] / 1000:.1f}k",
                _usd(row["cost"]) if row["cost"] is not None else "—",
                "◆" if row["frontier"] else "",
            ]
        )
    table = column_table(
        ["#", "model", "score", "95% CI", "solved", "tok/s", "tokens", "cost", "frontier"],
        rows,
        align=["r", "l", "r", "r", "r", "r", "r", "r", "l"],
    )
    lines = [table]
    for warning in payload["warnings"]:
        lines.append(f"warning: {warning}")
    ties = [r for r in payload["rows"] if r["tied_with"]]
    if ties:
        lines.append(
            f"\n{len(ties)} run(s) share a rank — their intervals overlap, so the suite cannot "
            "separate them at this sample size."
        )
    return "\n".join(lines)


def render_json(payload: dict) -> dict:
    """Machine-readable form: no Run objects, no derived prose."""
    rows = []
    for row in payload["rows"]:
        clean = {key: value for key, value in row.items() if key not in {"run", "ci", "pricing"}}
        clean["ci_pp"] = [round(v * 100, 2) for v in row["ci"]] if row["ci"] else None
        clean["pricing"] = row["pricing"]
        rows.append(clean)
    return {
        "by": payload["by"],
        "axis": payload["axis"],
        "mixed": payload["mixed"],
        "warnings": payload["warnings"],
        "rows": rows,
    }


def load_and_build(
    paths: Iterable[str | Path], by: str = "first", allow_mixed: bool = False
) -> dict:
    runs = load_runs([Path(p).expanduser() for p in paths])
    return build(runs, by=by, allow_mixed=allow_mixed)
