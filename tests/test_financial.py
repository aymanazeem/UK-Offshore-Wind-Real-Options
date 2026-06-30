"""Static DCF spine, depreciation schedules, the decision-year-0 identity, and the headline NPV."""

from __future__ import annotations

import numpy as np
import pytest

from config import parameters as P
from src import financial_model as fm

LIFE = P.OPERATING_LIFE_YEARS


def test_default_depreciation_is_straight_line():
    # the validated -£1.2707bn spine assumes straight-line, capital allowances are opt-in
    assert P.DEPRECIATION_METHOD == "straight_line"


@pytest.mark.parametrize("method", ["straight_line", "wda_18", "full_expensing"])
def test_depreciation_schedule_conserves_capex(method):
    cap = fm.total_capex()
    sched = fm.depreciation_schedule(cap, LIFE, method)
    assert sched.shape == (LIFE,)
    assert sched.sum() == pytest.approx(cap, rel=1e-12)  # only timing differs, not the total
    assert (sched >= 0).all()


def test_value_paths_equals_decision_year_zero(abandon_sim):
    price, gen = abandon_sim
    a = fm.value_paths(price, gen).npv
    b = fm.value_from_decision_year(price, gen, 0).npv
    assert np.array_equal(a, b)  # value_paths is exactly the decision_year=0 wrapper


def test_capital_allowances_front_load_the_shield(abandon_sim):
    price, gen = abandon_sim
    sl = fm.value_paths(price, gen, depreciation_method="straight_line").npv.mean()
    wda = fm.value_paths(price, gen, depreciation_method="wda_18").npv.mean()
    fe = fm.value_paths(price, gen, depreciation_method="full_expensing").npv.mean()
    # the shield total is fixed, bringing it forward raises PV
    assert fe > wda > sl


def test_static_npv_headline():
    # documented base case, 50k paths, seed 42 -> -£1.2707bn
    res, _, _ = fm.run(n_paths=50_000, seed=42)
    assert res.npv.mean() / 1e9 == pytest.approx(-1.2707, abs=1e-3)
