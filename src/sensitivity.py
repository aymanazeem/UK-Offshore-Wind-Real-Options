"""
Sensitivity of the static NPV: which input, moved across its sourced range, changes the answer
most, and how far each would have to move for the project to break even.

We simulate prices and generation once and hold them fixed, then flex one economic input at a
time (this is a "one-at-a-time tornado"). Each bar therefore isolates a single assumption. The
grid charge (TNUoS) is pulled out of OPEX into its own lever because it is both the biggest and
the most location-dependent cost.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq

from config import parameters as P
from src.price_simulator import simulate_price_paths
from src.generation_model import simulate_generation
from src.financial_model import value_paths

_OM = P.OPEX_OM_INSURANCE_K
_TN = P.OPEX_TNUOS_K

# Each lever: (label, {low, central, high}, build the value_paths overrides from a scalar value).
# The two OPEX levers each hold the other component at its central value.
LEVERS = [
    ("CAPEX (£/kW)",               P.CAPEX_PER_KW,          lambda v: {"capex_per_kw": v}),
    ("Grid charge TNUoS (k£/MW/yr)", _TN,                   lambda v: {"opex_per_mw_year_k": _OM["central"] + v}),
    ("O&M + insurance (k£/MW/yr)", _OM,                     lambda v: {"opex_per_mw_year_k": _TN["central"] + v}),
    ("WACC",                       P.WACC_RANGE,            lambda v: {"wacc": v}),
    ("Capacity factor",            P.CF_RANGE,              lambda v: {"cf": v}),
    ("CfD strike (£/MWh)",         P.CFD_STRIKE_RANGE,      lambda v: {"cfd_strike": v}),
    ("Merchant capture",           P.MERCHANT_CAPTURE_RANGE, lambda v: {"capture_factor": v}),
]

# Search brackets for the break-even root-find (the lever value that makes mean NPV = 0).
BREAKEVEN_BRACKETS = {
    "CAPEX (£/kW)": (100.0, 12_000.0),
    "Grid charge TNUoS (k£/MW/yr)": (-400.0, 400.0),
    "O&M + insurance (k£/MW/yr)": (-400.0, 400.0),
    "WACC": (0.001, 0.40),
    "Capacity factor": (0.10, 2.00),
    "CfD strike (£/MWh)": (0.0, 400.0),
    "Merchant capture": (0.0, 6.0),
}


@dataclass
class Lever:
    label: str
    low: float
    central: float
    high: float
    npv_low: float
    npv_high: float
    breakeven: float | None

    @property
    def swing(self) -> float:
        return abs(self.npv_high - self.npv_low)


def npv_mean(price, gen, **overrides) -> float:
    """Mean NPV (£) on the fixed paths. `cf` rescales generation linearly (generation is
    proportional to capacity factor); everything else passes straight to value_paths."""
    cf = overrides.pop("cf", P.CF_MEAN)
    g = gen if cf == P.CF_MEAN else gen * (cf / P.CF_MEAN)
    return float(value_paths(price, g, **overrides).npv.mean())


def _breakeven(price, gen, label, build) -> float | None:
    lo, hi = BREAKEVEN_BRACKETS[label]
    f = lambda v: npv_mean(price, gen, **build(v))
    try:
        if f(lo) * f(hi) > 0:      # same sign at both ends -> no zero crossing in the bracket
            return None
        return float(brentq(f, lo, hi, xtol=1e-4))
    except ValueError:
        return None


def compute(n_paths: int = P.N_PATHS, seed: int = P.RANDOM_SEED) -> tuple[float, list[Lever]]:
    """Return (base-case mean NPV, levers sorted by swing ascending for a tornado)."""
    life = P.OPERATING_LIFE_YEARS
    pp = simulate_price_paths(n_paths=n_paths, horizon=P.CONSTRUCTION_YEARS + life, seed=seed)
    gp = simulate_generation(n_paths=n_paths, horizon=life, seed=seed + 1)
    n = min(pp.annual_prices.shape[0], gp.generation_mwh.shape[0])
    price, gen = pp.annual_prices[:n], gp.generation_mwh[:n]

    base = npv_mean(price, gen)
    levers = []
    for label, rng, build in LEVERS:
        levers.append(Lever(
            label=label, low=rng["low"], central=rng["central"], high=rng["high"],
            npv_low=npv_mean(price, gen, **build(rng["low"])),
            npv_high=npv_mean(price, gen, **build(rng["high"])),
            breakeven=_breakeven(price, gen, label, build)))
    levers.sort(key=lambda x: x.swing)
    return base, levers


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    n_paths = next((int(a.split("=")[1]) for a in argv if a.startswith("--n=")), P.N_PATHS)
    bn = 1e9
    base, levers = compute(n_paths=n_paths)
    print(f"Static NPV sensitivity ({n_paths:,} paths). Base case £{base / bn:+.3f}bn\n")
    print(f"  {'lever':<32}{'low NPV':>10}{'high NPV':>10}{'swing':>9}   break-even")
    for lv in reversed(levers):  # widest swing first
        be = "none in range" if lv.breakeven is None else f"{lv.breakeven:,.2f}"
        print(f"  {lv.label:<32}{lv.npv_low / bn:>+9.2f} {lv.npv_high / bn:>+9.2f} "
              f"{lv.swing / bn:>8.2f}   {be}")


if __name__ == "__main__":
    main()
