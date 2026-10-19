"""``modelbench compare`` — is this run actually different from the baseline?

The report already knows how to test one pair. This module answers the
question people actually have when a new model lands: rank it against the run
you trust, and say plainly whether the difference survives the noise.

Two things make the answer honest rather than decorative:

* the gap is quoted with its own interval, not as a bare number, and
* the p-values are Holm-adjusted across the family of comparisons, because
  testing one baseline against five challengers is five chances to be fooled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .report import Run, ci_pct, load_run, pairwise, pct, run_metrics
from .stats import holm, sign_test_min_wins

FAIL_ON = ("never", "regression", "unresolved")


@dataclass
class Comparison:
    run: Run
    score: float
    ci: tuple[float, float] | None
    gap_pp: float
    gap_ci: tuple[float, float] | None
    wins: int
    losses: int
    ties: int
    tasks: int
    samples: int
    p_value: float
    p_adjusted: float
    identical: bool
    provisional: bool
    established: bool

    @property
    def direction(self) -> str:
        if abs(self.gap_pp) < 0.05:
            return "same"
        return "better" if self.gap_pp > 0 else "worse"

    @property
    def verdict(self) -> str:
        if self.identical:
            return "identical"
        if self.tasks < 2:
            return "not enough tasks"
        if self.established:
            return self.direction
        return "not established"

    def as_dict(self) -> dict:
        return {
            "run": self.run.label,
            "path": str(self.run.path),
            "suite": self.run.suite_id,
            "score": round(self.score, 4),
            "ci_pp": [round(v * 100, 2) for v in self.ci] if self.ci else None,
            "gap_pp": round(self.gap_pp, 2),
            "gap_ci_pp": [round(v, 2) for v in self.gap_ci] if self.gap_ci else None,
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
            "tasks": self.tasks,
            "samples": self.samples,
            "p_value": round(self.p_value, 6),
            "p_adjusted": round(self.p_adjusted, 6),
            "established": self.established,
            "provisional": self.provisional,
            "identical": self.identical,
            "verdict": self.verdict,
        }


def _suite_key(run: Run) -> tuple[str, str]:
    digest = (run.header.get("suite") or {}).get("digest") or (
        run.records[0].get("suite_digest") if run.records else ""
    )
    return (run.suite_id, str(digest or ""))


def compare_runs(
    baseline: Run,
    others: Sequence[Run],
    alpha: float = 0.05,
    allow_mixed: bool = False,
) -> dict:
    """Compare each of *others* against *baseline*, correcting for the family.

    Raises ``ValueError`` when a run comes from another suite or another suite
    version: those scores are not on one scale, and averaging the difference
    would be arithmetic about nothing.
    """
    base_key = _suite_key(baseline)
    for other in others:
        if not allow_mixed and _suite_key(other) != base_key:
            raise ValueError(
                f"{other.label!r} is from {other.suite_id} ({(other.header.get('suite') or {}).get('digest')}), "
                f"the baseline is {baseline.suite_id} ({(baseline.header.get('suite') or {}).get('digest')}); "
                "scores from different suites are not on one scale. Pass --allow-mixed to compare anyway."
            )

    baseline_metrics = run_metrics(baseline)
    pairs = [(other, pairwise(other, baseline)) for other in others]
    adjusted = holm([pair.p_value for _, pair in pairs])

    comparisons: list[Comparison] = []
    for (other, pair), p_adjusted in zip(pairs, adjusted):
        metrics = run_metrics(other)
        ci = pair.delta_ci
        excludes_zero = bool(ci and (ci[0] > 0 or ci[1] < 0))
        comparisons.append(
            Comparison(
                run=other,
                score=metrics["first_score"],
                ci=metrics["first_ci"],
                gap_pp=(metrics["first_score"] - baseline_metrics["first_score"]) * 100,
                gap_ci=ci,
                wins=pair.wins_a,
                losses=pair.wins_b,
                ties=pair.ties,
                tasks=len(pair.common),
                samples=metrics["samples"],
                p_value=pair.p_value,
                p_adjusted=p_adjusted,
                identical=pair.identical,
                provisional=bool(metrics["samples"] and metrics["samples"] < 3),
                established=bool(excludes_zero and p_adjusted < alpha),
            )
        )

    return {
        "baseline": {
            "run": baseline.label,
            "path": str(baseline.path),
            "suite": baseline.suite_id,
            "score": round(baseline_metrics["first_score"], 4),
            "ci_pp": [round(v * 100, 2) for v in baseline_metrics["first_ci"]]
            if baseline_metrics["first_ci"]
            else None,
            "tasks": baseline_metrics["tasks"],
            "samples": baseline_metrics["samples"],
        },
        "alpha": alpha,
        "comparisons": [c.as_dict() for c in comparisons],
        "_comparisons": comparisons,
        "resolution": {
            "tasks": baseline_metrics["tasks"],
            "min_wins": sign_test_min_wins(baseline_metrics["tasks"], alpha),
        },
    }


def _p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def render_console(result: dict) -> str:
    base = result["baseline"]
    comparisons: list[Comparison] = result["_comparisons"]
    head = (
        f"baseline  {base['run']}  {pct(base['score'])}"
        f"{' (' + ci_pct(tuple(v / 100 for v in base['ci_pp'])) + ')' if base['ci_pp'] else ''}"
        f"  {base['suite']} · {base['tasks']} tasks · {base['samples']} sample(s)"
    )
    widths = {
        "run": max([len("run")] + [len(c.run.label) for c in comparisons]),
        "score": 20,
        "gap": 34,
        "p": 10,
    }
    lines = [
        head,
        "",
        f"{'run':<{widths['run']}}  {'score':<{widths['score']}}  {'gap vs baseline':<{widths['gap']}}  "
        f"{'p (Holm)':>{widths['p']}}  verdict",
    ]
    for c in comparisons:
        score = pct(c.score) + (f" ({ci_pct(c.ci)})" if c.ci else "")
        gap = f"{c.gap_pp:+.1f} pp"
        if c.gap_ci:
            gap += f" ({c.gap_ci[0]:+.1f}, {c.gap_ci[1]:+.1f})"
        lines.append(
            f"{c.run.label:<{widths['run']}}  {score:<{widths['score']}}  {gap:<{widths['gap']}}  "
            f"{_p(c.p_adjusted):>{widths['p']}}  {c.verdict}"
        )

    resolution = result["resolution"]
    if resolution["min_wins"]:
        lines += [
            "",
            f"resolution: with {resolution['tasks']} tasks the exact sign test needs "
            f"{resolution['min_wins']}/{resolution['tasks']} in the same direction to reach "
            f"p < {result['alpha']}; anything smaller is not established, whatever the interval says.",
        ]
    lines.append(
        f"\np-values are Holm-adjusted across {len(comparisons)} comparison(s); "
        "a gap counts only when its interval excludes zero and the adjusted p clears alpha."
    )
    return "\n".join(lines)


def render_markdown(result: dict) -> str:
    base = result["baseline"]
    comparisons: list[Comparison] = result["_comparisons"]
    lines = [
        f"**Baseline:** {base['run']} — {pct(base['score'])}"
        f"{' (' + ci_pct(tuple(v / 100 for v in base['ci_pp'])) + ')' if base['ci_pp'] else ''}, "
        f"{base['suite']}, {base['tasks']} tasks, {base['samples']} sample(s)",
        "",
        "| run | score | gap vs baseline | p (Holm) | verdict |",
        "| --- | --- | --- | --- | --- |",
    ]
    for c in comparisons:
        score = pct(c.score) + (f" ({ci_pct(c.ci)})" if c.ci else "")
        gap = f"{c.gap_pp:+.1f} pp" + (f" ({c.gap_ci[0]:+.1f}, {c.gap_ci[1]:+.1f})" if c.gap_ci else "")
        lines.append(f"| {c.run.label} | {score} | {gap} | {_p(c.p_adjusted)} | {c.verdict} |")
    resolution = result["resolution"]
    if resolution["min_wins"]:
        lines += [
            "",
            f"With {resolution['tasks']} tasks, the sign test needs {resolution['min_wins']} in the same "
            f"direction to reach p < {result['alpha']}.",
        ]
    lines.append("")
    lines.append(f"Holm-adjusted over {len(comparisons)} comparison(s).")
    return "\n".join(lines)


def exit_code(result: dict, fail_on: str = "never") -> int:
    if fail_on not in FAIL_ON:
        raise ValueError(f"fail_on must be one of {FAIL_ON}")
    if fail_on == "never":
        return 0
    comparisons: list[Comparison] = result["_comparisons"]
    if fail_on == "regression":
        return 1 if any(c.established and c.gap_pp < 0 for c in comparisons) else 0
    return 1 if any(not c.established and not c.identical for c in comparisons) else 0


def compare_paths(
    baseline: str | Path,
    others: Sequence[str | Path],
    alpha: float = 0.05,
    allow_mixed: bool = False,
) -> dict:
    return compare_runs(load_run(baseline), [load_run(path) for path in others], alpha=alpha, allow_mixed=allow_mixed)
