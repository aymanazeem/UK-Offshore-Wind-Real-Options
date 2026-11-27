"""Checks on the DCF: the capital allowance only shifts the tax shield's timing (never its
total), the capture factor touches merchant revenue only, each operating year earns the price of
its own year after the build, the remaining-operations helper rebuilds the static NPV, and the
headline NPV is stable."""

from __future__ import annotations

import numpy as np
import pytest

from config import parameters as P
from src import financial_model as fm

LIFE = P.OPERATING_LIFE_YEARS


def test_capital_allowance_conserves_capex():
    capex = fm.total_capex()
    sched = fm.capital_allowance(capex, LIFE)
    assert sched.shape == (LIFE,)
    assert sched.sum() == pytest.approx(capex, rel=1e-12)   # timing only, total unchanged
    assert (sched >= 0).all()


def test_value_paths_is_decision_year_zero(base_sim):
    price, gen = base_sim
    assert np.array_equal(fm.value_paths(price, gen).npv,
                          fm.value_from_decision_year(price, gen, 0).npv)


def test_capture_factor_only_affects_merchant(base_sim):
    price, gen = base_sim
    full = fm.value_paths(price, gen, capture_factor=1.0)
    haircut = fm.value_paths(price, gen, capture_factor=0.70)
    assert full.pv_cfd.mean() == pytest.approx(haircut.pv_cfd.mean(), rel=1e-12)  # CfD untouched
    assert haircut.pv_merchant.mean() < full.pv_merchant.mean()                   # merchant lower


@pytest.mark.parametrize("decision_year", [0, 2, 4])
def test_operating_year_earns_the_price_of_its_own_year(defer_sim, decision_year):
    price, gen = defer_sim
    first_merchant = P.CFD_TERM_YEARS                      # operating-year index
    year = decision_year + P.CONSTRUCTION_YEARS + first_merchant   # that year, counted from today
    bumped = price.copy()
    bumped[:, year] += 10.0
    gain = (fm.value_from_decision_year(bumped, gen, decision_year).npv
            - fm.value_from_decision_year(price, gen, decision_year).npv)
    t = P.CONSTRUCTION_YEARS + first_merchant + 0.5        # from the decision, mid-year
    expected = (10.0 * P.MERCHANT_CAPTURE_FACTOR * gen[:, first_merchant] * (1 - P.TAX_RATE)
                * (1 + P.WACC) ** -t)
    assert gain == pytest.approx(expected, rel=1e-9)


def test_remaining_ops_reconstructs_static(base_sim):
    price, gen = base_sim
    res = fm.value_paths(price, gen)
    vrem = fm.value_of_remaining_operations(price, gen, 0)
    recon = -res.pv_capex + (1.0 + P.WACC) ** (-P.CONSTRUCTION_YEARS) * vrem.mean()
    assert recon == pytest.approx(res.npv.mean(), abs=1.0)


def test_static_npv_headline():
    # base case, 50k paths, seed 42 (two-factor prices, WDA allowances, 0.85 capture factor)
    res, _, _ = fm.run(n_paths=50_000, seed=42)
    assert res.npv.mean() / 1e9 == pytest.approx(-1.1863, abs=2e-3)
