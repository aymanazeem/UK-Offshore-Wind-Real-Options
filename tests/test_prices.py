"""Checks on the two-factor price model: the fan widens with the horizon because of the long-term
random-walk factor, and with that factor switched off it collapses to a flat, mean-reverting fan."""

from __future__ import annotations

from src import price_simulator as ps


def test_fan_widens_with_horizon():
    paths = ps.simulate_price_paths(n_paths=20_000, horizon=35, seed=1)
    ratio = paths.percentiles()[90] / paths.percentiles()[10]
    assert ratio[-1] > ratio[0] * 1.3    # year 35 is meaningfully wider than year 1


def test_flat_fan_without_long_term_factor():
    # long-term vol = 0 leaves only the fast-reverting short-term factor, so the band should stay
    # roughly constant across the horizon (this is the one-factor limit the fix improves on).
    paths = ps.simulate_price_paths(n_paths=20_000, horizon=35, seed=1, lt_vol=0.0)
    ratio = paths.percentiles()[90] / paths.percentiles()[10]
    assert abs(ratio[-1] - ratio[0]) < 0.2
