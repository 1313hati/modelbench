"""Uncertainty for a benchmark that expects to be argued with.

A suite score is a mean over a dozen tasks. Printed to one decimal place it
looks like a measurement with a millimetre of precision; in reality one task
flipping moves it by eight points. These helpers add the two numbers a reader
needs before quoting a score:

* a bootstrap confidence interval for the suite score, resampling **tasks**
  (they are the unit the score gives equal weight to), and
* a paired comparison for "is A better than B": a bootstrap interval for the
  mean per-task delta plus an exact sign test, which assumes nothing about how
  scores are distributed.

Both are seeded. Two reports generated from the same runs print the same
numbers, so a CI quoted in a pull request still matches the CI on disk.
"""

from __future__ import annotations

import math
import random
from typing import Sequence

from .util import mean, percentile

DEFAULT_ITERATIONS = 2000


def bootstrap_mean_ci(
    values: Sequence[float],
    iterations: int = DEFAULT_ITERATIONS,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float] | None:
    """Percentile bootstrap interval for the mean of *values*.

    ``None`` when there is nothing to estimate from. A single observation has
    no interval: returning ``(v, v)`` would claim certainty we do not have.
    Identical observations do get ``(v, v)`` — the interval is genuinely zero
    width, which is different from pretending a sample of one is precise.
    """
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return None
    if len(clean) == 1 or iterations <= 0:
        return None
    first = clean[0]
    if all(v == first for v in clean):
        # A degenerate sample has a degenerate interval. Taking the resampling
        # path would work, but float summation adds an ulp on 3.11 (3.12's
        # compensated `sum` hides it), so an all-0.9 run would report
        # 0.9000000000000002 and fail an exact comparison.
        return (first, first)
    rng = random.Random(seed)
    n = len(clean)
    means = []
    for _ in range(iterations):
        means.append(sum(clean[rng.randrange(n)] for _ in range(n)) / n)
    lo = percentile(means, alpha / 2)
    hi = percentile(means, 1 - alpha / 2)
    return (min(lo, hi), max(lo, hi))


def sign_test_p(wins: int, losses: int) -> float:
    """Two-sided exact sign test over the tasks that were not tied.

    Under the null hypothesis each task is a fair coin, so the p-value is the
    chance of seeing a split at least this lopsided. No normality assumption,
    no t-distribution approximation over 12 points.
    """
    n = wins + losses
    if n == 0:
        return 1.0
    k = max(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k, n + 1)) / (2**n)
    return min(1.0, 2 * tail)


def paired_delta(
    deltas: Sequence[float],
    wins: int,
    losses: int,
    ties: int,
    iterations: int = DEFAULT_ITERATIONS,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict:
    """Summarise a per-task comparison in a form a report can quote.

    ``significant`` is deliberately conservative: the interval must exclude
    zero **and** the sign test must be below ``alpha``. With a dozen tasks and
    a small effect, those two can disagree; when they do the honest answer is
    "not established", not the more flattering of the two.
    """
    values = [float(d) for d in deltas]
    ci = bootstrap_mean_ci(values, iterations=iterations, alpha=alpha, seed=seed)
    p = sign_test_p(wins, losses)
    excludes_zero = bool(ci and (ci[0] > 0 or ci[1] < 0))
    return {
        "mean_pp": mean(values) if values else 0.0,
        "ci_pp": ci,
        "p_value": p,
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "tasks": len(values),
        "significant": bool(excludes_zero and p < alpha),
    }


def sign_test_min_wins(tasks: int, alpha: float = 0.05) -> int | None:
    """Fewest one-directional wins that the sign test can call significant.

    This is the resolution of the design, not of the data: with 12 tasks the
    test needs 10 of them to move the same way (p = 0.039); 9 gives p = 0.146
    and establishes nothing. Quoting that next to a score stops readers from
    treating a 4-point gap as settled when one task can erase it.
    """
    for wins in range((tasks + 1) // 2, tasks + 1):
        if sign_test_p(wins, tasks - wins) < alpha:
            return wins
    return None


def holm(pvalues: Sequence[float]) -> list[float]:
    """Holm-Bonferroni adjusted p-values, in the order they were given.

    Comparing one model against five others is five chances to be fooled by
    noise. Holm controls the family-wise error rate without assuming the tests
    are independent, and it is uniformly more powerful than a flat Bonferroni
    multiplier. Adjusted values are monotone, so a comparison that looked
    stronger cannot end up with a weaker adjusted p than the one below it.
    """
    count = len(pvalues)
    if count == 0:
        return []
    order = sorted(range(count), key=lambda index: pvalues[index])
    adjusted = [1.0] * count
    running = 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (count - rank) * float(pvalues[index])))
        adjusted[index] = running
    return adjusted


def fmt_p(p: float) -> str:
    if p < 0.001:
        return "p < 0.001"
    return f"p = {p:.3f}"
