"""Checks on the generation model, that switching on the CF-price link hits the target correlation
without disturbing the capacity-factor marginal."""

from __future__ import annotations

import numpy as np
import pytest

from config import parameters as P
from src import generation_model as gm

LIFE = P.OPERATING_LIFE_YEARS


def test_cf_correlation_preserves_marginal(abandon_sim):
    price, _ = abandon_sim
    n = price.shape[0]
    indep = gm.simulate_generation(n_paths=n, horizon=LIFE, seed=43).capacity_factor
    corr = gm.simulate_generation(n_paths=n, horizon=LIFE, seed=43,
                                  price_annual=price, cf_price_corr=-0.15).capacity_factor
    # the Gaussian-copula tilt keeps each CF standard-normal driver standard normal, so the
    # Beta marginal is unchanged, only the dependence on price moves
    assert indep.mean() == pytest.approx(P.CF_MEAN, abs=2e-3)
    assert corr.mean() == pytest.approx(P.CF_MEAN, abs=2e-3)
    assert corr.std() == pytest.approx(indep.std(), abs=2e-3)


def test_cf_price_correlation_is_realized(abandon_sim):
    price, _ = abandon_sim
    n = price.shape[0]
    rho = -0.15
    cf = gm.simulate_generation(n_paths=n, horizon=LIFE, seed=43,
                                price_annual=price, cf_price_corr=rho).capacity_factor
    # per-year corr(price, CF) over the merchant tail should land near the target rho
    rs = [np.corrcoef(price[:, t], cf[:, t])[0, 1] for t in range(P.CFD_TERM_YEARS, LIFE)]
    assert np.mean(rs) == pytest.approx(rho, abs=0.03)
