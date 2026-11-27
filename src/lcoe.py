"""
Reconciles the model with the published LCOE benchmark.

The Levelised Cost of Energy (LCOE) is the constant price a project would need, over its whole
life, to exactly break even. Arup for DESNZ publishes a central offshore-wind LCOE of £88.5/MWh
in 2023 prices (cost_benchmarks.csv) from the same cost inputs this model uses; like those costs,
it is restated in 2024 pounds. This module recomputes LCOE from the model's own DCF and explains
the gap to that benchmark, so the economics are transparent:

  1. pre-tax LCOE  = PV(all costs) / PV(all generation)  -- the standard, tax-free definition.
  2. break-even price = the flat price that makes the model's *after-tax* NPV zero.

The difference between the two is the tax effect. The gap between (1) and the benchmark comes
from differences in what is counted and when; docs/decisions.md sets them out. Seeing both makes
it clear why the headline NPV is negative at a CfD of £90.91.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq

from config import parameters as P
from src.financial_model import discount_factors, operating_prices, total_capex, value_paths
from src.price_simulator import simulate_price_paths

LIFE = P.OPERATING_LIFE_YEARS
# £/MWh, Arup for DESNZ 2024 central (cost_benchmarks.csv), published in 2023 prices
BENCHMARK_LCOE = 88.5 * P.ARUP_TO_BASE_YEAR


def _lifetime_generation_mwh(capacity_mw=P.CAPACITY_MW, cf=P.CF_MEAN) -> np.ndarray:
    """Deterministic annual generation at the mean capacity factor, with age de-rating."""
    age = np.arange(LIFE)
    return capacity_mw * cf * P.HOURS_PER_YEAR * (1.0 - P.DEGRADATION_RATE) ** age


def pretax_lcoe(capacity_mw=P.CAPACITY_MW, cf=P.CF_MEAN, per_kw=P.CAPEX_PER_KW["central"],
                opex_per_mw_year_k=P.OPEX_PER_MW_YEAR_K["central"], wacc=P.WACC) -> float:
    """Standard pre-tax LCOE = PV(costs) / PV(generation), £/MWh, using the model's own timing
    (CAPEX over a 5-year build, generation and OPEX mid-year across the operating life)."""
    c = P.CONSTRUCTION_YEARS
    gen = _lifetime_generation_mwh(capacity_mw, cf)
    df_op = discount_factors(c + np.arange(LIFE) + 0.5, wacc)

    pv_gen = gen @ df_op
    pv_capex = (total_capex(capacity_mw, per_kw) / c) * float(discount_factors(np.arange(c) + 0.5, wacc).sum())
    pv_opex = opex_per_mw_year_k * 1e3 * capacity_mw * float(df_op.sum())
    pv_decom = P.DECOMMISSIONING_PER_MW * capacity_mw * float(discount_factors(c + LIFE, wacc))
    return (pv_capex + pv_opex + pv_decom) / pv_gen


def breakeven_price(capacity_mw=P.CAPACITY_MW, cf=P.CF_MEAN, wacc=P.WACC) -> float:
    """The flat, all-merchant real price (with capture=1) that makes the after-tax NPV zero."""
    gen = _lifetime_generation_mwh(capacity_mw, cf)[None, :]  # one deterministic path

    def npv(price):
        prices = np.full((1, P.CONSTRUCTION_YEARS + LIFE), price)
        return value_paths(prices, gen, capacity_mw, wacc=wacc, cfd_term_years=0,
                           capture_factor=1.0).npv[0]

    return float(brentq(npv, 40.0, 400.0))


def main() -> None:
    lcoe = pretax_lcoe()
    be = breakeven_price()
    print("LCOE reconciliation (central inputs)")
    print(f"  published benchmark (Arup/DESNZ)   £{BENCHMARK_LCOE:.1f}/MWh   "
          f"(£88.5 in {P.ARUP_PRICE_YEAR} prices)")
    gap = lcoe - BENCHMARK_LCOE
    print(f"  model pre-tax LCOE                  £{lcoe:.1f}/MWh   "
          f"({'+' if gap >= 0 else '-'}£{abs(gap):.1f} vs benchmark; docs/decisions.md explains the gap)")
    print(f"  model after-tax break-even price    £{be:.1f}/MWh   "
          f"(+£{be - lcoe:.1f} vs pre-tax LCOE: tax effect)")
    merchant = operating_prices(simulate_price_paths().annual_prices, LIFE)[:, P.CFD_TERM_YEARS:]
    print(f"  CfD strike is £{P.CFD_STRIKE:.2f}/MWh; after the CfD the market price averages "
          f"£{merchant.mean():.0f}, of which wind captures £{P.MERCHANT_CAPTURE_FACTOR * merchant.mean():.0f}. "
          f"Both are below £{be:.0f}, so the project is NPV-negative.")


if __name__ == "__main__":
    main()
