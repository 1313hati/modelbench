from __future__ import annotations

import math

import pytest

from modelbench.stats import bootstrap_mean_ci, fmt_p, paired_delta, sign_test_p


def test_interval_is_reproducible():
    values = [1.0, 0.8, 0.9, 0.6, 1.0, 0.7, 0.95, 0.5]
    assert bootstrap_mean_ci(values) == bootstrap_mean_ci(values)


def test_interval_brackets_the_mean():
    values = [1.0, 0.8, 0.9, 0.6, 1.0, 0.7, 0.95, 0.5, 0.85, 0.75]
    low, high = bootstrap_mean_ci(values)
    assert low <= sum(values) / len(values) <= high
    assert high - low > 0


def test_one_observation_has_no_interval():
    # Claiming (v, v) would state a certainty the suite cannot have.
    assert bootstrap_mean_ci([0.7]) is None
    assert bootstrap_mean_ci([]) is None


def test_identical_scores_produce_a_point_interval():
    assert bootstrap_mean_ci([0.9] * 12) == (0.9, 0.9)


def test_sign_test_matches_the_binomial_tail():
    # 9 wins, 3 losses out of 12: 2 * (C(12,9)+C(12,10)+C(12,11)+C(12,12)) / 2**12
    expected = 2 * (math.comb(12, 9) + math.comb(12, 10) + math.comb(12, 11) + math.comb(12, 12)) / 2**12
    assert sign_test_p(9, 3) == pytest.approx(expected)
    assert sign_test_p(0, 0) == 1.0


def test_paired_delta_needs_the_interval_and_the_sign_test():
    strong = paired_delta([4.0, 5.0, 6.0, 4.0, 5.0, 3.0] * 2, wins=12, losses=0, ties=0)
    assert strong["significant"] is True
    assert strong["ci_pp"][0] > 0

    # A big mean driven by one task, with the sign test split: not established.
    noisy = paired_delta([20.0, -1.0, -1.0, -1.0, -1.0, 0.0], wins=2, losses=3, ties=1)
    assert noisy["significant"] is False


def test_identical_runs_are_not_significant():
    pair = paired_delta([0.0, 0.0, 0.0], wins=0, losses=0, ties=3)
    assert pair["p_value"] == 1.0
    assert pair["significant"] is False
    assert pair["ci_pp"] == (0.0, 0.0)


def test_p_formatting():
    assert fmt_p(0.0004) == "p < 0.001"
    assert fmt_p(0.0316) == "p = 0.032"
