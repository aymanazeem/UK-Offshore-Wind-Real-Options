"""Checks on the generation model: the fitted Beta reproduces the target capacity-factor mean and
spread, generation falls with age, and the lifetime average still matches the load factor, which
already allows for wear."""

from __future__ import annotations

import pytest

from config import parameters as P
from src import generation_model as gm


def test_beta_matches_target_moments():
    gp = gm.simulate_generation(n_paths=8000, seed=7)
    assert gp.capacity_factor.mean() == pytest.approx(gp.mean, abs=2e-3)
    assert gp.capacity_factor.std() == pytest.approx(gp.sd, abs=3e-3)


def test_generation_derates_with_age():
    gp = gm.simulate_generation(n_paths=4000, seed=7)
    mean_by_year = gp.generation_mwh.mean(axis=0)
    assert mean_by_year[-1] < mean_by_year[0]                       # output falls with age
    expected_last = mean_by_year[0] * (1.0 - P.DEGRADATION_RATE) ** (gp.generation_mwh.shape[1] - 1)
    assert mean_by_year[-1] == pytest.approx(expected_last, rel=1e-2)


def test_lifetime_average_output_matches_the_load_factor():
    gp = gm.simulate_generation(n_paths=8000, seed=7)
    expected = P.CAPACITY_MW * P.CF_MEAN * P.HOURS_PER_YEAR
    assert gp.generation_mwh.mean() == pytest.approx(expected, rel=2e-3)
