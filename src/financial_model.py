"""
Turns simulated prices and generation into the project's value, the NPV.

For every simulated future we build a yearly cash flow and discount it back to today (the point of
committing capital, "FID"). Revenue is hybrid: a fixed CfD strike price for the first 20 years,
then the wholesale market price (haircut by the capture factor) for the rest. Thousands of price
and generation futures give a distribution of NPVs, not a single number.

Conventions, kept deliberately simple:
  - Real 2024 money throughout, so the discount rate is a real rate and there is no inflation.
  - t = 0 is the start of construction. CAPEX is spread evenly over the build. Cash flows are
    discounted mid-year. Decommissioning is a single outflow in the final year.
  - Price paths count years from today, so the first operating year earns the price of the year
    after the build finishes, not today's.
  - Cash flows are before tax, matching the pre-tax discount rate (see config.WACC). The after-tax
    view passes tax_rate: tax is then that share of (EBITDA - capital allowance), the allowance
    being the CAPEX written down at 18%/yr (UK reducing balance) on its nominal cost, so it loses
    value to inflation. Tax can go negative in early years; we assume the loss is used
    immediately against group profit, as a large developer can.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np

from config import parameters as P
from src.price_simulator import simulate_price_paths
from src.generation_model import simulate_generation


def discount_factors(times, wacc: float = P.WACC) -> np.ndarray:
    """(1 + wacc)^-t for each time t in years."""
    return (1.0 + wacc) ** (-np.asarray(times, dtype=float))


def total_capex(capacity_mw: float = P.CAPACITY_MW, per_kw: float = P.CAPEX_PER_KW["central"]) -> float:
    """Total CAPEX in £ (£/kW x MW x 1000 kW/MW)."""
    return per_kw * capacity_mw * 1_000.0


def capital_allowance(capex: float, life: int, rate: float = P.WDA_RATE) -> np.ndarray:
    """Yearly UK writing-down allowance: `rate` of the remaining pool each year, with the final
    year taking whatever is left (the balancing allowance). Sums to CAPEX, so it only changes the
    timing of the tax shield, never the total."""
    dep = np.empty(life)
    pool = capex
    for j in range(life - 1):
        dep[j] = rate * pool
        pool -= dep[j]
    dep[life - 1] = pool
    return dep


def real_capital_allowance(capex: float, life: int, inflation: float = P.INFLATION) -> np.ndarray:
    """The writing-down allowance in real pounds. The pool is the CAPEX in the pounds of the year
    it is spent, and each year's allowance is worth less by the time it is claimed."""
    c = P.CONSTRUCTION_YEARS
    nominal_pool = capex / c * ((1.0 + inflation) ** (np.arange(c) + 0.5)).sum()
    return capital_allowance(nominal_pool, life) / (1.0 + inflation) ** (c + np.arange(life) + 0.5)


@dataclass
class ValuationResult:
    """Per-path NPV (£) and the present-value pieces that build it."""
    npv: np.ndarray                 # (n_paths,)
    pv_operating: np.ndarray        # operating cash flow, all years
    pv_cfd: np.ndarray              # operating CF, CfD years only
    pv_merchant: np.ndarray         # operating CF, merchant years only
    pv_capex: float
    pv_decom: float
    op_cf: np.ndarray               # (n_paths, life) operating CF per year, for the LSM

    def summary(self) -> dict:
        p10, p50, p90 = np.percentile(self.npv, [10, 50, 90])
        return {"mean": float(self.npv.mean()), "p10": float(p10), "p50": float(p50),
                "p90": float(p90), "prob_negative": float((self.npv < 0).mean())}


def operating_prices(price: np.ndarray, life: int, decision_year: int = 0) -> np.ndarray:
    """The price columns a farm committed at `decision_year` earns over its operating life: it
    builds for CONSTRUCTION_YEARS, so operating year j sells in year decision_year + build + j."""
    first = decision_year + P.CONSTRUCTION_YEARS
    if decision_year < 0 or first + life > price.shape[1]:
        raise ValueError(f"need {first + life} price columns for decision_year={decision_year}, "
                         f"got {price.shape[1]}")
    return price[:, first:first + life]


def operating_cashflows(
    price: np.ndarray, gen: np.ndarray, capacity_mw: float = P.CAPACITY_MW, *,
    capex_per_kw: float = P.CAPEX_PER_KW["central"],
    opex_per_mw_year_k: float = P.OPEX_PER_MW_YEAR_K["central"],
    cfd_strike: float = P.CFD_STRIKE, cfd_term_years: int = P.CFD_TERM_YEARS,
    capture_factor: float = P.MERCHANT_CAPTURE_FACTOR, tax_rate: float = 0.0,
    inflation: float = P.INFLATION,
) -> tuple[np.ndarray, np.ndarray]:
    """Operating cash flow for each path and year, before tax unless tax_rate is given. Returns
    (op_cf, cfd_mask).

    Revenue is the fixed CfD strike in contract years, and the market price haircut by the capture
    factor in merchant years. Setting cfd_term_years=0 makes the asset fully merchant (used for the
    Phase-2 expansion)."""
    life = gen.shape[1]
    cfd_mask = np.arange(life) < cfd_term_years
    revenue = np.where(cfd_mask, cfd_strike * gen, capture_factor * price * gen)
    opex = opex_per_mw_year_k * 1e3 * capacity_mw
    ebitda = revenue - opex
    allowance = real_capital_allowance(total_capex(capacity_mw, capex_per_kw), life, inflation)
    op_cf = ebitda - tax_rate * (ebitda - allowance)  # allowance broadcasts across paths
    return op_cf, cfd_mask


def value_from_decision_year(
    price: np.ndarray, gen: np.ndarray, decision_year: int = 0, capacity_mw: float = P.CAPACITY_MW,
    *, wacc: float = P.WACC, capex_per_kw: float = P.CAPEX_PER_KW["central"],
    opex_per_mw_year_k: float = P.OPEX_PER_MW_YEAR_K["central"],
    cfd_strike: float = P.CFD_STRIKE, cfd_term_years: int = P.CFD_TERM_YEARS,
    capture_factor: float = P.MERCHANT_CAPTURE_FACTOR, tax_rate: float = 0.0,
) -> ValuationResult:
    """NPV of committing at `decision_year`: start building then, discounted back to that date.
    This is the value the real-options engine sees at each "wait or commit" node. decision_year = 0
    is committing today."""
    life = gen.shape[1]
    op_cf, cfd_mask = operating_cashflows(
        operating_prices(price, life, decision_year), gen, capacity_mw, capex_per_kw=capex_per_kw,
        opex_per_mw_year_k=opex_per_mw_year_k, cfd_strike=cfd_strike,
        cfd_term_years=cfd_term_years, capture_factor=capture_factor, tax_rate=tax_rate)

    c = P.CONSTRUCTION_YEARS
    capex = total_capex(capacity_mw, capex_per_kw)
    df_op = discount_factors(c + np.arange(life) + 0.5, wacc)     # operating years, mid-year
    pv_capex = (capex / c) * float(discount_factors(np.arange(c) + 0.5, wacc).sum())
    pv_decom = float(P.DECOMMISSIONING_PER_MW * capacity_mw * discount_factors(c + life, wacc))

    pv_operating = op_cf @ df_op
    return ValuationResult(
        npv=-pv_capex + pv_operating - pv_decom,
        pv_operating=pv_operating,
        pv_cfd=op_cf[:, cfd_mask] @ df_op[cfd_mask],
        pv_merchant=op_cf[:, ~cfd_mask] @ df_op[~cfd_mask],
        pv_capex=pv_capex, pv_decom=pv_decom, op_cf=op_cf)


def value_paths(price: np.ndarray, gen: np.ndarray, capacity_mw: float = P.CAPACITY_MW,
                **kwargs) -> ValuationResult:
    """NPV of committing today (decision_year = 0). price covers the build and operating years,
    CONSTRUCTION_YEARS more columns than gen, which covers the operating years only."""
    if price.shape != (gen.shape[0], P.CONSTRUCTION_YEARS + gen.shape[1]):
        raise ValueError(f"price {price.shape} must have {P.CONSTRUCTION_YEARS} more columns "
                         f"than gen {gen.shape}")
    return value_from_decision_year(price, gen, 0, capacity_mw, **kwargs)


def _pv_remaining(op_cf: np.ndarray, from_year: int, capacity_mw: float, wacc: float) -> np.ndarray:
    """PV of op_cf[:, from_year:] plus the terminal decommissioning cost, discounted to the start
    of operating year `from_year`. No CAPEX (the asset is already built)."""
    life = op_cf.shape[1]
    df = discount_factors(np.arange(life - from_year) + 0.5, wacc)
    pv_decom = P.DECOMMISSIONING_PER_MW * capacity_mw * discount_factors(life - from_year, wacc)
    return op_cf[:, from_year:] @ df - pv_decom


def value_of_remaining_operations(
    price: np.ndarray, gen: np.ndarray, from_year: int = 0, capacity_mw: float = P.CAPACITY_MW,
    *, wacc: float = P.WACC, cfd_strike: float = P.CFD_STRIKE,
    cfd_term_years: int = P.CFD_TERM_YEARS, capture_factor: float = P.MERCHANT_CAPTURE_FACTOR,
) -> np.ndarray:
    """PV of the operating cash flows still to come from `from_year` (plus terminal decom),
    discounted to the start of that year. Valuing this at a buyer's lower WACC gives their price."""
    op_cf, _ = operating_cashflows(operating_prices(price, gen.shape[1]), gen, capacity_mw,
                                   cfd_strike=cfd_strike, cfd_term_years=cfd_term_years,
                                   capture_factor=capture_factor)
    return _pv_remaining(op_cf, from_year, capacity_mw, wacc)


def divestment_advantage(
    price: np.ndarray, gen: np.ndarray, capacity_mw: float = P.CAPACITY_MW, *,
    our_wacc: float = P.WACC, buyer_wacc: float = P.BUYER_WACC,
    transaction_cost: float = P.TRANSACTION_COST, cfd_strike: float = P.CFD_STRIKE,
    cfd_term_years: int = P.CFD_TERM_YEARS, capture_factor: float = P.MERCHANT_CAPTURE_FACTOR,
) -> np.ndarray:
    """(n_paths, life) advantage of selling the asset at each operating year over holding it:
        (1 - transaction_cost) * value-to-buyer  -  value-to-us,
    where each value is the PV of the remaining operations at that party's WACC. The buyer's lower
    WACC makes the same future cash flows worth more. The operating cash flow does not depend on
    the discount rate, so it is computed once and reused for every year and both WACCs."""
    life = gen.shape[1]
    op_cf, _ = operating_cashflows(operating_prices(price, life), gen, capacity_mw,
                                   cfd_strike=cfd_strike, cfd_term_years=cfd_term_years,
                                   capture_factor=capture_factor)
    advantage = np.empty((price.shape[0], life))
    for t in range(life):
        v_buyer = _pv_remaining(op_cf, t, capacity_mw, buyer_wacc)
        v_us = _pv_remaining(op_cf, t, capacity_mw, our_wacc)
        advantage[:, t] = (1.0 - transaction_cost) * v_buyer - v_us
    return advantage


def run(n_paths: int = P.N_PATHS, seed: int = P.RANDOM_SEED) -> tuple[ValuationResult, object, object]:
    """Simulate prices and generation (on independent seeds) and value every path."""
    life = P.OPERATING_LIFE_YEARS
    pp = simulate_price_paths(n_paths=n_paths, horizon=P.CONSTRUCTION_YEARS + life, seed=seed)
    gp = simulate_generation(n_paths=n_paths, horizon=life, seed=seed + 1)
    n = min(pp.annual_prices.shape[0], gp.generation_mwh.shape[0])
    res = value_paths(pp.annual_prices[:n], gp.generation_mwh[:n])
    return res, pp, gp


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    n_paths = next((int(a.split("=")[1]) for a in argv if a.startswith("--n=")), P.N_PATHS)
    res, pp, gp = run(n_paths=n_paths)
    s = res.summary()
    bn = 1e9
    print(f"Static NPV ({n_paths:,} paths): mean £{s['mean'] / bn:+.3f}bn  "
          f"[P10 £{s['p10'] / bn:+.2f} · P50 £{s['p50'] / bn:+.2f} · P90 £{s['p90'] / bn:+.2f}]  "
          f"P(NPV<0) {s['prob_negative']:.0%}")
    print(f"  PV pieces (mean £bn): capex -{res.pv_capex / bn:.2f}, "
          f"CfD ops +{res.pv_cfd.mean() / bn:.2f}, merchant ops +{res.pv_merchant.mean() / bn:.2f}, "
          f"decom -{res.pv_decom / bn:.2f}")
    n = res.npv.shape[0]
    after = value_paths(pp.annual_prices[:n], gp.generation_mwh[:n], tax_rate=P.TAX_RATE,
                        wacc=P.POST_TAX_WACC).summary()
    print(f"  After-tax view ({P.TAX_RATE:.0%} tax, discounted at {P.POST_TAX_WACC:.2%}): "
          f"mean £{after['mean'] / bn:+.3f}bn, P(NPV<0) {after['prob_negative']:.0%}")


if __name__ == "__main__":
    main()
