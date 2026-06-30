"""Look-ahead-free LSM, the structural identities that pin each option engine to the static spine."""

from __future__ import annotations

import pytest

from config import parameters as P
from src import financial_model as fm
from src import lsm_engine as lsm

LIFE = P.OPERATING_LIFE_YEARS


def test_defer_zero_deferral_matches_static(defer_sim):
    price, gen = defer_sim
    r = lsm.lsm_defer(price, gen, d_max=0, allow_walkaway=False)
    # with no deferral and no walk-away the LSM just commits on every path at t=0
    assert r.option_value == r.static_npv


def test_defer_static_matches_value_paths(defer_sim):
    price, gen = defer_sim
    r = lsm.lsm_defer(price, gen, d_max=0, allow_walkaway=False)
    static = fm.value_paths(price[:, :LIFE], gen).npv.mean()
    assert r.static_npv == pytest.approx(static, abs=1.0)


def test_abandon_spine_reconstruction(abandon_sim):
    price, gen = abandon_sim
    res = fm.value_paths(price, gen)
    vrem0 = fm.value_of_remaining_operations(price, gen, 0, wacc=P.WACC)
    c = P.CONSTRUCTION_PERIOD_YEARS
    # -CAPEX(PV) + disc(construction) * PV(remaining ops from COD) reconstructs the static NPV
    recon = -res.pv_capex + (1.0 + P.WACC) ** (-c) * vrem0.mean()
    assert recon == pytest.approx(res.npv.mean(), abs=1.0)


def test_abandon_no_arbitrage(abandon_sim):
    price, gen = abandon_sim
    r = lsm.lsm_abandon(price, gen, buyer_wacc=P.WACC, transaction_cost=0.0)
    # no WACC gap and no transaction cost => zero sell-advantage on every path
    assert abs(r.add_on) < 1.0


def test_expand_has_decline_floor():
    price, gen2 = lsm.simulate_expand(n_paths=4000, seed=42)
    r = lsm.lsm_expand(price, gen2, decision_years=lsm.expand_decision_years(), cfd_term_years=0)
    assert r.option_value >= -1.0  # never forced to expand => value >= 0
