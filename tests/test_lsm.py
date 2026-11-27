"""Checks on the Longstaff-Schwartz engine.

The headline test values a vanilla American put with the same engine and compares it to an
independent binomial-tree price: this exercises the backward induction, discounting and
regression on a problem with a known answer. The rest are structural identities: with no room to
defer the defer option is just the static NPV, and with no WACC gap the divestment right is
worthless."""

from __future__ import annotations

import numpy as np
import pytest

from config import parameters as P
from src import lsm_engine as lsm

LIFE = P.OPERATING_LIFE_YEARS


# ---- validation against a known option value -----------------------------------------------
def _gbm_paths(s0, r, sigma, T, n_steps, n_paths, seed):
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    z = rng.standard_normal((n_paths // 2, n_steps))
    z = np.concatenate([z, -z])                                  # antithetic
    log_return = (r - 0.5 * sigma ** 2) * dt + sigma * np.sqrt(dt) * z
    s = np.empty((z.shape[0], n_steps + 1))
    s[:, 0] = s0
    s[:, 1:] = s0 * np.exp(np.cumsum(log_return, axis=1))
    return s


def _binomial_american_put(s0, K, r, sigma, T, n=500):
    dt = T / n
    u = np.exp(sigma * np.sqrt(dt)); d = 1.0 / u
    p = (np.exp(r * dt) - d) / (u - d); disc = np.exp(-r * dt)
    j = np.arange(n + 1); value = np.maximum(K - s0 * u ** (n - j) * d ** j, 0.0)
    for i in range(n, 0, -1):
        j = np.arange(i)
        spot = s0 * u ** (i - 1 - j) * d ** j
        value = np.maximum(disc * (p * value[:-1] + (1 - p) * value[1:]), K - spot)
    return float(value[0])


def test_lsm_matches_binomial_american_put():
    s0, K, r, sigma, T, n_steps = 36.0, 40.0, 0.06, 0.20, 1.0, 50
    spot = _gbm_paths(s0, r, sigma, T, n_steps, 200_000, seed=0)
    payoff = np.maximum(K - spot, 0.0)
    wacc_per_step = np.exp(r * T / n_steps) - 1.0
    value, _ = lsm._american_option(payoff, spot, wacc=wacc_per_step, degree=4, must_act_by_end=False)
    reference = _binomial_american_put(s0, K, r, sigma, T, n=500)
    assert value.mean() == pytest.approx(reference, abs=0.15)   # ~3%: MC + regression


# ---- structural identities -----------------------------------------------------------------
def test_defer_zero_deferral_is_static(defer_sim):
    price, gen = defer_sim
    r = lsm.defer_option(price, gen, d_max=0, can_walk_away=False)
    assert r.option_value == pytest.approx(r.static_npv, abs=1.0)


def test_abandon_no_arbitrage(base_sim):
    price, gen = base_sim
    # no WACC gap and no transaction cost => selling can never beat holding
    r = lsm.abandon_option(price, gen, buyer_wacc=P.WACC, transaction_cost=0.0)
    assert abs(r.add_on) < 1.0


def test_decisions_use_only_prices_already_seen(defer_sim):
    # the decision at the start of year y may use prices up to year y - 1, so with the values of
    # committing held fixed, scrambling the prices from the last decision year on changes nothing
    price, gen = defer_sim
    ex = lsm.commit_npvs(price, gen, P.DEFERRAL_MAX_YEARS)
    scrambled = price.copy()
    later = slice(P.DEFERRAL_MAX_YEARS, None)
    scrambled[:, later] = np.random.default_rng(0).permutation(scrambled[:, later])
    seen = lsm.defer_option(price, gen, ex=ex)
    unseen = lsm.defer_option(scrambled, gen, ex=ex)
    assert unseen.option_value == seen.option_value
    assert np.array_equal(unseen.commit_year, seen.commit_year)
    # the first decision sees only history, the same on every path, so it is all or nothing
    first = seen.commit_year == 0
    assert first.all() or not first.any()


def test_options_never_negative(defer_sim):
    price, gen = defer_sim
    # the right to walk away / decline is worth at least zero
    assert lsm.defer_option(price, gen, can_walk_away=True).option_value >= -1.0
