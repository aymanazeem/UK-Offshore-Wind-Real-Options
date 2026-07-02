"""
Turns simulated prices and output into the project's economics and an overall value, the NPV.

For every simulated future we build an annual cash flow of revenue, running costs and tax, then
discount it back to today. Revenue is hybrid. A fixed CfD strike for the first 20 years, then the
merchant market price for the remaining 15. Because thousands of price and output futures feed
in, the headline result is a distribution of NPVs, not a single number.

Conventions, kept deliberately simple for this DCF spine and refined later.
- Valued at FID, where t=0 is the start of construction. Mid-year discounting for annual flows.
- Total CAPEX is spread evenly over the construction period. Predevelopment, about 5% of CAPEX
  and really pre-FID, is folded into that spread, a small conservative timing simplification.
- Depreciation gives a tax shield, and tax can go negative since losses are assumed to offset
  group profit. The base case is straight-line. Front-loaded UK capital allowances are an opt-in
  refinement via depreciation_method. Decommissioning is a terminal post-tax outflow.
- The CfD strike is CPI-indexed, so it is constant in this real-terms model.
- Capacity factor is drawn independently of price by default, on separate seeds. The mild
  negative CF-price correlation is an opt-in refinement via run(cf_price_corr=) that moves NPV by
  less than £1m, since it bites only in the discounted merchant tail.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from config import parameters as P  # noqa: E402
from src.price_simulator import simulate_price_paths  # noqa: E402
from src.generation_model import simulate_generation  # noqa: E402


def discount_factors(times, wacc: float = P.WACC) -> np.ndarray:
    """Discount factor (1 + wacc)^-t for each time t in years."""
    return (1.0 + wacc) ** (-np.asarray(times, dtype=float))


def total_capex(capacity_mw: float = P.CAPACITY_MW, per_kw: float = P.CAPEX_PER_KW_CENTRAL) -> float:
    """Total real CAPEX in £ (per_kw * MW * 1000 kW/MW)."""
    return per_kw * capacity_mw * 1_000.0


def depreciation_schedule(
    capex: float,
    life: int,
    method: str = P.DEPRECIATION_METHOD,
    wda_rate: float = P.WDA_RATE,
) -> np.ndarray:
    """Per-operating-year depreciation or allowance, shape (life,), in £. Sums to `capex` for
    every method, so only the TIMING of the tax shield differs, not the total. The standalone SPV
    has no profit to shield during construction, so allowances are taken from operating year 0,
    since group relief lets a loss be monetised in-year, consistent with the rest of the model.

    - straight_line, capex/life each year, the base case matching the original scalar shield
      exactly.
    - wda_18, an 18%/yr reducing-balance writing-down allowance, with a balancing allowance
      clearing the residual pool in the final year, which front-loads the shield.
    - full_expensing, a 100% first-year allowance putting the entire shield in operating year 0,
      the UK regime.
    """
    if method == "straight_line":
        return np.full(life, capex / life)
    if method == "full_expensing":
        dep = np.zeros(life)
        dep[0] = capex
        return dep
    if method == "wda_18":
        dep = np.empty(life)
        pool = capex
        for j in range(life - 1):
            dep[j] = wda_rate * pool
            pool -= dep[j]
        dep[life - 1] = pool  # balancing allowance clears the residual pool
        return dep
    raise ValueError(f"unknown depreciation method {method!r}")


@dataclass
class ValuationResult:
    """Per-path NPV in £ and its present-value building blocks."""

    npv: np.ndarray              # (n_paths,)
    pv_operating: np.ndarray     # (n_paths,) post-tax operating CF, all 35 yrs
    pv_cfd: np.ndarray           # (n_paths,) operating CF, CfD years (1-20)
    pv_merchant_tail: np.ndarray  # (n_paths,) operating CF, merchant tail (21-35)
    pv_capex: float
    pv_decom: float
    op_cf: np.ndarray = None     # (n_paths, life) post-tax operating CF, per year, for the LSM
    inputs: dict = field(default_factory=dict)

    def merchant_tail_share(self) -> np.ndarray:
        """Fraction of operating PV that sits in the merchant tail, per path."""
        return self.pv_merchant_tail / self.pv_operating

    def summary(self) -> dict:
        n = self.npv
        p10, p50, p90 = np.percentile(n, [10, 50, 90])
        return {
            "mean": float(n.mean()),
            "p10": float(p10),
            "p50": float(p50),
            "p90": float(p90),
            "prob_negative": float((n < 0).mean()),
            "pv_capex": self.pv_capex,
            "pv_decom": self.pv_decom,
            "mean_pv_cfd": float(self.pv_cfd.mean()),
            "mean_pv_merchant_tail": float(self.pv_merchant_tail.mean()),
            "median_tail_share": float(np.median(self.merchant_tail_share())),
        }


def operating_cashflows(
    price: np.ndarray,
    gen: np.ndarray,
    capacity_mw: float = P.CAPACITY_MW,
    *,
    capex_per_kw: float = P.CAPEX_PER_KW_CENTRAL,
    opex_per_mw_year_k: float = P.OPEX_PER_MW_YEAR_K_CENTRAL,
    cfd_strike: float = P.CFD_STRIKE,
    cfd_term_years: int = P.CFD_TERM_YEARS,
    depreciation_method: str = P.DEPRECIATION_METHOD,
) -> tuple[np.ndarray, np.ndarray]:
    """Post-tax operating cash flow for each path and operating year. Shape matches gen.

    Revenue is hybrid, a fixed CfD strike for the contract term, then the merchant price.
    cfd_term_years=0 makes the asset fully merchant, as in a Phase-2 expansion.
    Depreciation is a non-cash shield that can turn tax negative, since losses are assumed to
    offset group profit. Its schedule, straight-line or capital allowances, front-loads but never
    changes the total allowance. Returns (op_cf, cfd_mask)."""
    life = gen.shape[1]
    cfd_mask = np.arange(life) < cfd_term_years  # contracted years, then the merchant tail
    revenue = np.where(cfd_mask, cfd_strike * gen, price * gen)
    opex = opex_per_mw_year_k * 1e3 * capacity_mw  # £/yr, constant real
    ebitda = revenue - opex
    dep = depreciation_schedule(total_capex(capacity_mw, capex_per_kw), life, depreciation_method)
    op_cf = ebitda - P.TAX_RATE * (ebitda - dep)  # tax on EBITDA less depreciation, dep broadcasts over paths
    return op_cf, cfd_mask


def value_from_decision_year(
    price: np.ndarray,
    gen: np.ndarray,
    decision_year: int = 0,
    capacity_mw: float = P.CAPACITY_MW,
    *,
    wacc: float = P.WACC,
    capex_per_kw: float = P.CAPEX_PER_KW_CENTRAL,
    opex_per_mw_year_k: float = P.OPEX_PER_MW_YEAR_K_CENTRAL,
    cfd_strike: float = P.CFD_STRIKE,
    cfd_term_years: int = P.CFD_TERM_YEARS,
    depreciation_method: str = P.DEPRECIATION_METHOD,
) -> ValuationResult:
    """NPV of committing at `decision_year`, that is starting construction then, discounted back
    to that date. This is the project value the LSM sees at each deferral node.

    Operating year j takes its merchant price from column decision_year+j of `price`. Generation
    is age-indexed, so the same gen profile applies whenever we commit. The OU price is
    stationary, so deferring shifts the price window without widening its band. The live
    uncertainty the defer option keys off sits only in the distant, decorrelated merchant tail.
    decision_year=0 with price.shape==gen.shape reproduces the FID-today valuation bit-identically.
    """
    life = gen.shape[1]
    d = decision_year
    if d < 0 or d + life > price.shape[1]:
        raise ValueError(f"price needs {d + life} columns for decision_year={d}, got {price.shape[1]}")
    price_win = price[:, d:d + life]

    op_cf, cfd_mask = operating_cashflows(
        price_win, gen, capacity_mw, capex_per_kw=capex_per_kw,
        opex_per_mw_year_k=opex_per_mw_year_k, cfd_strike=cfd_strike,
        cfd_term_years=cfd_term_years, depreciation_method=depreciation_method,
    )

    # Timeline from the decision date. Construction yrs 0..C-1, operations C..C+L-1, all
    # mid-year, decom terminal. Everything discounts to the decision date, not to t=0.
    c = P.CONSTRUCTION_PERIOD_YEARS
    capex = total_capex(capacity_mw, capex_per_kw)
    df_op = discount_factors(c + np.arange(life) + 0.5, wacc)  # mid-year factor per operating year
    pv_capex = (capex / c) * float(discount_factors(np.arange(c) + 0.5, wacc).sum())  # CAPEX spread over the build
    pv_decom = float(P.DECOMMISSIONING_PER_MW * capacity_mw * discount_factors(c + life, wacc))

    pv_operating = op_cf @ df_op
    pv_cfd = op_cf[:, cfd_mask] @ df_op[cfd_mask]
    pv_tail = op_cf[:, ~cfd_mask] @ df_op[~cfd_mask]
    npv = -pv_capex + pv_operating - pv_decom

    return ValuationResult(
        npv=npv,
        pv_operating=pv_operating,
        pv_cfd=pv_cfd,
        pv_merchant_tail=pv_tail,
        pv_capex=pv_capex,
        pv_decom=pv_decom,
        op_cf=op_cf,
        inputs={
            "capacity_mw": capacity_mw,
            "total_capex": capex,
            "opex_per_yr": opex_per_mw_year_k * 1e3 * capacity_mw,
            "wacc": wacc,
            "cfd_strike": cfd_strike,
            "cfd_term_years": cfd_term_years,
            "operating_life": life,
            "decision_year": d,
        },
    )


def value_paths(
    price: np.ndarray,
    gen: np.ndarray,
    capacity_mw: float = P.CAPACITY_MW,
    *,
    wacc: float = P.WACC,
    capex_per_kw: float = P.CAPEX_PER_KW_CENTRAL,
    opex_per_mw_year_k: float = P.OPEX_PER_MW_YEAR_K_CENTRAL,
    cfd_strike: float = P.CFD_STRIKE,
    depreciation_method: str = P.DEPRECIATION_METHOD,
) -> ValuationResult:
    """Discount each simulated (price, generation) future to an NPV at FID. The decision_year=0
    case of value_from_decision_year, commit today.

    price and gen are (n_paths, operating_life) arrays of annual-average £/MWh and annual MWh. The
    economics default to config but are overridable so the sensitivity sweep can flex one lever at
    a time."""
    if price.shape != gen.shape:
        raise ValueError(f"price {price.shape} and gen {gen.shape} must match")
    return value_from_decision_year(
        price, gen, 0, capacity_mw, wacc=wacc, capex_per_kw=capex_per_kw,
        opex_per_mw_year_k=opex_per_mw_year_k, cfd_strike=cfd_strike,
        depreciation_method=depreciation_method,
    )


def value_of_remaining_operations(
    price: np.ndarray,
    gen: np.ndarray,
    from_operating_year: int = 0,
    capacity_mw: float = P.CAPACITY_MW,
    *,
    wacc: float = P.WACC,
    capex_per_kw: float = P.CAPEX_PER_KW_CENTRAL,
    opex_per_mw_year_k: float = P.OPEX_PER_MW_YEAR_K_CENTRAL,
    cfd_strike: float = P.CFD_STRIKE,
    cfd_term_years: int = P.CFD_TERM_YEARS,
    depreciation_method: str = P.DEPRECIATION_METHOD,
) -> np.ndarray:
    """PV of the asset's REMAINING operating cash flows from `from_operating_year`, plus the
    terminal decommissioning liability. No CAPEX, no construction, because the asset is already
    built. Discounted to the start of that operating year.

    The CfD schedule is absolute. Operating year j stays contracted iff j < cfd_term_years, so a
    mid-CfD sale hands the buyer only the remaining contract years, then the merchant tail.
    Valuing at the buyer's lower WACC gives the price they would pay. At our WACC it is the
    hold-to-end value. The abandon option compares the two. Returns an (n_paths,) array in £.

    Discounting to FID instead reconstructs the static spine. With from_operating_year=0 and our
    WACC, -pv_capex + (1+wacc)^-construction * mean(this) == the static NPV, asserted in the LSM.
    """
    life = gen.shape[1]
    t = from_operating_year
    op_cf, _ = operating_cashflows(
        price[:, :life], gen, capacity_mw, capex_per_kw=capex_per_kw,
        opex_per_mw_year_k=opex_per_mw_year_k, cfd_strike=cfd_strike,
        cfd_term_years=cfd_term_years, depreciation_method=depreciation_method,
    )
    # Remaining operating years t..life-1, mid-year, discounted to the start of year t. Decom
    # falls at end of life, so (life - t) years out from the sale date.
    df = discount_factors(np.arange(life - t) + 0.5, wacc)
    pv_ops = op_cf[:, t:] @ df
    pv_decom = P.DECOMMISSIONING_PER_MW * capacity_mw * discount_factors(life - t, wacc)
    return pv_ops - pv_decom


def run(
    n_paths: int = P.N_PATHS,
    frequency: str = P.PRICE_FREQUENCY,
    window: str = P.PRICE_CALIBRATION_WINDOW,
    seed: int = P.RANDOM_SEED,
    *,
    cf_price_corr: float = 0.0,
    depreciation_method: str = P.DEPRECIATION_METHOD,
) -> tuple[ValuationResult, "object", "object"]:
    """Simulate prices and generation on independent seeds, then value every path. cf_price_corr!=0
    correlates CF with the simulated price for the cannibalisation effect. Both default to the base
    case."""
    life = P.OPERATING_LIFE_YEARS
    pp = simulate_price_paths(n_paths=n_paths, horizon=life, frequency=frequency,
                              window=window, seed=seed)
    gp = simulate_generation(n_paths=n_paths, horizon=life, seed=seed + 1,
                             price_annual=pp.annual_prices, cf_price_corr=cf_price_corr)
    n = min(pp.annual_prices.shape[0], gp.generation_mwh.shape[0])
    res = value_paths(pp.annual_prices[:n], gp.generation_mwh[:n],
                      depreciation_method=depreciation_method)
    return res, pp, gp


# Chart 2, NPV distribution and PV bridge
def plot_npv_chart(res: ValuationResult, save_path=None, title: str | None = None):
    """Left panel shows the NPV distribution with P10, P50 and P90 and break-even. Right panel
    shows the mean PV bridge from CAPEX through CfD and merchant-tail operating value to NPV."""
    if save_path is None:
        save_path = P.CHARTS_DIR / "chart2_npv.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    s = res.summary()
    bn = 1e9
    npv_bn = res.npv / bn

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    # Left panel, NPV distribution
    axL.hist(npv_bn, bins=70, color="#1f77b4", alpha=0.4)
    for q, lab, c in [(s["p10"], "P10", "#1f77b4"), (s["p50"], "P50", "#1f77b4"),
                      (s["p90"], "P90", "#1f77b4")]:
        axL.axvline(q / bn, color=c, lw=1.6, ls="--", alpha=0.85)
        axL.text(q / bn, axL.get_ylim()[1] * 0.97, lab, rotation=90, fontsize=8,
                 va="top", ha="right", color=c)
    axL.axvline(0, color="#d62728", lw=2)
    axL.set_xlabel("NPV (£bn, real 2024)")
    axL.set_ylabel("Paths")
    axL.set_title("NPV distribution")
    box = (f"mean  £{s['mean'] / bn:5.2f}bn\n"
           f"P50   £{s['p50'] / bn:5.2f}bn\n"
           f"P10   £{s['p10'] / bn:5.2f}bn\n"
           f"P90   £{s['p90'] / bn:5.2f}bn\n"
           f"P(NPV<0) {s['prob_negative']:.0%}")
    axL.text(0.015, 0.97, box, transform=axL.transAxes, fontsize=9, va="top", ha="left",
             family="monospace",
             bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="0.7", alpha=0.92))
    axL.grid(True, alpha=0.25)

    # Right panel, mean PV bridge waterfall
    steps = [
        ("CAPEX", -res.pv_capex / bn),
        ("CfD ops\n(yr 1-20)", s["mean_pv_cfd"] / bn),
        ("Merchant\n(yr 21-35)", s["mean_pv_merchant_tail"] / bn),
        ("Decom.", -res.pv_decom / bn),
    ]
    bottoms, running = [], 0.0
    for _, v in steps:
        bottoms.append(min(running, running + v))
        running += v
    colors = ["#d62728", "#2ca02c", "#98df8a", "#d62728"]
    xs = np.arange(len(steps) + 1)
    for i, (lab, v) in enumerate(steps):
        axR.bar(xs[i], abs(v), bottom=bottoms[i], color=colors[i], alpha=0.85, width=0.6)
    axR.bar(xs[-1], running, color="#1f77b4", alpha=0.9, width=0.6)
    axR.axhline(0, color="0.3", lw=0.8)
    axR.set_xticks(xs)
    axR.set_xticklabels([lab for lab, _ in steps] + ["NPV\n(mean)"], fontsize=8.5)
    axR.set_ylabel("Present value (£bn, real 2024)")
    axR.set_title("Mean PV bridge")
    axR.grid(True, axis="y", alpha=0.25)

    if title is None:
        title = (f"Chart 2: Project NPV ({res.npv.shape[0]:,} paths, WACC "
                 f"{P.WACC:.1%}, {res.inputs['operating_life']}-yr life)")
    fig.suptitle(title, fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig, (axL, axR)


def realism_report(res: ValuationResult, pp, gp) -> str:
    s = res.summary()
    bn = 1e9
    # deterministic "central path" check, P50 price, mean generation
    price_p50 = np.percentile(pp.annual_prices, 50, axis=0)[None, :]
    gen_mean = gp.generation_mwh.mean(axis=0)[None, :]
    det = value_paths(price_p50, gen_mean).npv[0]
    inp = res.inputs
    lines = [
        f"CAPEX total £{inp['total_capex'] / bn:.2f}bn  ->  PV £{res.pv_capex / bn:.2f}bn",
        f"OPEX £{inp['opex_per_yr'] / 1e6:.0f}m/yr   decom PV £{res.pv_decom / 1e6:.0f}m",
        f"NPV distribution (n={res.npv.shape[0]:,}):",
        f"  mean £{s['mean'] / bn:.2f}bn   P10 £{s['p10'] / bn:.2f}bn   "
        f"P50 £{s['p50'] / bn:.2f}bn   P90 £{s['p90'] / bn:.2f}bn",
        f"  P(NPV<0) = {s['prob_negative']:.1%}",
        f"  central-path NPV (P50 price, mean CF) = £{det / bn:.2f}bn",
        f"Operating PV split (mean): CfD £{s['mean_pv_cfd'] / bn:.2f}bn  "
        f"merchant tail £{s['mean_pv_merchant_tail'] / bn:.2f}bn  "
        f"(tail share median {s['median_tail_share']:.0%})",
    ]
    return "\n".join(lines)


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    n_paths = P.N_PATHS
    for arg in argv:
        if arg.startswith("--n="):
            n_paths = int(arg.split("=", 1)[1])

    print(f"Valuing {n_paths:,} paths ...")
    res, pp, gp = run(n_paths=n_paths)
    print(realism_report(res, pp, gp))

    out = P.CHARTS_DIR / "chart2_npv.png"
    plot_npv_chart(res, save_path=out)
    print(f"\nSaved NPV chart -> {out}")


if __name__ == "__main__":
    main()
