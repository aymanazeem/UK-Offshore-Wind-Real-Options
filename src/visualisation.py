"""
All of the project's charts live here, separated from the computation. Each function asks a model
module for numbers and draws them; nothing is calculated here that a module does not already own,
and every annotation is computed from the live results (no hard-coded figures that could drift).

    python -m src.visualisation             # all charts, base-case path count
    python -m src.visualisation --n=10000   # quick, fewer paths
    python -m src.visualisation --final     # production quality (N_PATHS_FINAL)
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy import stats  # noqa: E402

from config import parameters as P  # noqa: E402
from src import price_simulator as ps  # noqa: E402
from src import generation_model as gm  # noqa: E402
from src import financial_model as fm  # noqa: E402
from src import lsm_engine as lsm  # noqa: E402
from src import sensitivity as sens  # noqa: E402
from src import lcoe  # noqa: E402

BN = 1e9
BLUE, GREEN, RED, DARK = "#1f77b4", "#2ca02c", "#d62728", "#08519c"


def _save(fig, name):
    path = P.CHARTS_DIR / name
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def _box(ax, text, xy=(0.97, 0.03), ha="right", va="bottom"):
    ax.text(*xy, text, transform=ax.transAxes, fontsize=8, ha=ha, va=va,
            bbox=dict(boxstyle="round,pad=0.4", fc="#fff7e6", ec="0.7", alpha=0.95))


# --------------------------------------------------------------------------------------------
def chart_price_fan(n_paths):
    paths = ps.simulate_price_paths(n_paths=n_paths)
    pct = paths.percentiles()
    x = paths.calendar_year
    prm = paths.params

    hist = pd.read_csv(P.PRICE_DAILY_CSV, parse_dates=["date"])
    hist["yf"] = hist["date"].dt.year + ps.fractional_year(hist["date"])
    ym = (hist["date"].dt.year * 12 + hist["date"].dt.month).to_numpy()
    _, inv = np.unique(ym, return_inverse=True)
    monthly = pd.DataFrame({"yf": np.bincount(inv, weights=hist["yf"]) / np.bincount(inv),
                            "p": np.bincount(inv, weights=hist["price_gbp_per_mwh"]) / np.bincount(inv)})

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(monthly["yf"], monthly["p"], color="0.25", lw=1.4, label="Historical monthly avg")
    ax.fill_between(x, pct[10], pct[90], color=BLUE, alpha=0.22, label="Forecast P10-P90")
    ax.plot(x, pct[50], color=BLUE, lw=2.2, label="Forecast P50 (median)")
    ax.axvline(x[0] - 0.5, color="grey", ls=":", lw=1.2)
    r1, r35 = pct[90][0] / pct[10][0], pct[90][-1] / pct[10][-1]
    _box(ax, f"Two-factor OU\nκ={prm['kappa']:.1f} (half-life {prm['half_life_days']:.0f}d)\n"
             f"σ_short={prm['sigma_short']:.2f}  σ_long={prm['sigma_long']:.2f}/yr\n"
             f"P90/P10: {r1:.2f} (yr1) → {r35:.2f} (yr35)", xy=(0.015, 0.97), ha="left", va="top")
    ax.set_ylim(0, max(float(monthly["p"].max()), float(pct[90].max())) * 1.2)
    ax.set_title("Chart 1: Simulated GB wholesale price fan (two-factor, widens with horizon)")
    ax.set_xlabel("Year"); ax.set_ylabel("Wholesale price (£/MWh, real 2024)")
    ax.legend(loc="upper right", fontsize=9); ax.grid(True, alpha=0.25)
    return _save(fig, "chart1_price_fan.png")


def chart_generation(n_paths):
    gp = gm.simulate_generation(n_paths=n_paths)
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13, 5.2))

    cf0 = gp.capacity_factor[:, 0]
    axL.hist(cf0, bins=60, density=True, color=BLUE, alpha=0.35, label="Simulated CF (yr 1)")
    grid = np.linspace(cf0.min() - 0.02, cf0.max() + 0.02, 400)
    axL.plot(grid, stats.beta.pdf(grid, gp.alpha, gp.beta), color=BLUE, lw=2,
             label=f"Beta({gp.alpha:.0f}, {gp.beta:.0f})")
    axL.axvline(gp.mean, color=RED, lw=2, label=f"mean {gp.mean:.3f}")
    axL.set_xlabel("Annual capacity factor"); axL.set_ylabel("Density")
    axL.set_title("Capacity-factor distribution"); axL.legend(fontsize=8); axL.grid(True, alpha=0.25)

    twh = gp.generation_mwh / 1e6
    pct = gp.percentiles(twh)
    axR.fill_between(gp.calendar_year, pct[10], pct[90], color=GREEN, alpha=0.22, label="P10-P90")
    axR.plot(gp.calendar_year, pct[50], color=GREEN, lw=2, label="P50")
    axR.set_xlabel("Year"); axR.set_ylabel("Annual generation (TWh)"); axR.set_ylim(0, None)
    axR.set_title(f"Generation over {twh.shape[1]} yr ({P.CAPACITY_MW:.0f} MW, "
                  f"{P.DEGRADATION_RATE:.1%}/yr de-rating)")
    axR.legend(fontsize=8); axR.grid(True, alpha=0.25)
    fig.suptitle("Chart (verification): capacity factor and generation", fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return _save(fig, "chart_generation.png")


def chart_npv(n_paths):
    res, _, _ = fm.run(n_paths=n_paths)
    s = res.summary()
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    axL.hist(res.npv / BN, bins=70, color=BLUE, alpha=0.45)
    for q, lab in [(s["p10"], "P10"), (s["p50"], "P50"), (s["p90"], "P90")]:
        axL.axvline(q / BN, color=DARK, lw=1.4, ls="--")
        axL.text(q / BN, axL.get_ylim()[1] * 0.96, f" {lab} £{q / BN:.2f}bn", rotation=90,
                 fontsize=8, va="top")
    axL.axvline(0, color=RED, lw=2)
    axL.set_xlabel("NPV (£bn, real 2024)"); axL.set_ylabel("Paths")
    axL.set_title(f"NPV distribution (P(NPV<0) = {s['prob_negative']:.0%})")
    axL.grid(True, alpha=0.25)

    pieces = [("−CAPEX", -res.pv_capex), ("+CfD ops", res.pv_cfd.mean()),
              ("+Merchant ops", res.pv_merchant.mean()), ("−Decom", -res.pv_decom)]
    running = 0.0
    for i, (lab, v) in enumerate(pieces):
        axR.bar(i, v / BN, bottom=min(running, running + v) / BN, color=GREEN if v >= 0 else RED,
                width=0.6, alpha=0.85)
        running += v
    axR.bar(len(pieces), running / BN, color=DARK, width=0.6, alpha=0.9)
    axR.axhline(0, color="0.3", lw=1)
    axR.set_xticks(range(len(pieces) + 1))
    axR.set_xticklabels([p[0] for p in pieces] + ["= NPV"], fontsize=8)
    axR.set_ylabel("£bn"); axR.set_title(f"Mean PV bridge → NPV £{s['mean'] / BN:+.2f}bn")
    axR.grid(True, axis="y", alpha=0.25)
    fig.suptitle(f"Chart 2: Project NPV ({n_paths:,} paths, WACC {P.WACC:.1%})", fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return _save(fig, "chart2_npv.png")


def chart_sensitivity(n_paths):
    base, levers = sens.compute(n_paths=n_paths)
    fig, ax = plt.subplots(figsize=(11, 6))
    for i, lv in enumerate(levers):
        lo, hi = lv.npv_low / BN, lv.npv_high / BN
        ax.barh(i, hi - lo, left=lo, color=BLUE, alpha=0.7, height=0.6)
        be = "" if lv.breakeven is None else f"  break-even {lv.breakeven:,.2f}"
        ax.text(max(hi, lo) + 0.02, i, be, va="center", fontsize=8, color="0.3")
    ax.axvline(base / BN, color=RED, lw=2, label=f"base £{base / BN:+.2f}bn")
    ax.set_yticks(range(len(levers))); ax.set_yticklabels([lv.label for lv in levers], fontsize=9)
    ax.set_xlabel("Static NPV (£bn, real 2024)"); ax.legend(loc="lower right", fontsize=9)
    ax.set_title(f"Chart 3: Static-NPV sensitivity ({n_paths:,} paths)")
    ax.grid(True, axis="x", alpha=0.25)
    fig.tight_layout()
    return _save(fig, "chart3_sensitivity.png")


def chart_defer(n_paths):
    price, gen = lsm.simulate(n_paths, extra_price_years=P.DEFERRAL_MAX_YEARS)
    ex = lsm.commit_npvs(price, gen, P.DEFERRAL_MAX_YEARS)
    full = lsm.defer_option(price, gen, ex=ex)
    timing = lsm.defer_option(price, gen, can_walk_away=False, ex=ex)
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    bars = [("Commit now\n(static)", full.static_npv, BLUE),
            (f"Defer ≤{full.d_max}y\ntiming only", timing.option_value, DARK),
            (f"Defer ≤{full.d_max}y\n+ walk-away", full.option_value, GREEN)]
    for i, (lab, v, c) in enumerate(bars):
        axL.bar(i, v / BN, color=c, width=0.6, alpha=0.9)
        axL.text(i, v / BN, f"£{v / BN:+.2f}bn", ha="center",
                 va="bottom" if v >= 0 else "top", fontsize=9.5, fontweight="bold")
    axL.axhline(0, color=RED, lw=2)
    axL.set_xticks(range(3)); axL.set_xticklabels([b[0] for b in bars], fontsize=8.5)
    axL.set_ylabel("Value (£bn)"); axL.set_title("Defer option vs commit now")
    axL.grid(True, axis="y", alpha=0.25)
    never = (full.commit_year == -1).mean()
    _box(axL, f"Walk-away premium £{full.premium / BN:+.2f}bn\n= the right not to build\n"
              f"({never:.0%} of paths never build)")

    ds = np.arange(P.DEFERRAL_MAX_YEARS + 1)
    v_wa = [lsm.defer_option(price, gen, d, ex=ex).option_value / BN for d in ds]
    v_to = [lsm.defer_option(price, gen, d, can_walk_away=False, ex=ex).option_value / BN for d in ds]
    axR.plot(ds, v_wa, marker="o", color=GREEN, label="with walk-away")
    axR.plot(ds, v_to, marker="s", color=DARK, label="timing only")
    axR.axhline(full.static_npv / BN, color="0.4", ls="--", label="static")
    axR.axhline(0, color=RED, lw=1.5)
    axR.set_xticks(ds); axR.set_xlabel("Max deferral (years)"); axR.set_ylabel("Value (£bn)")
    axR.set_title("Value vs deferral window"); axR.legend(fontsize=8); axR.grid(True, alpha=0.25)
    fig.suptitle(f"Chart 4: Defer option ({price.shape[0]:,} paths)", fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return _save(fig, "chart4_defer.png")


def chart_expand(n_paths):
    price, gen2 = lsm.simulate(n_paths, extra_price_years=int(lsm.expand_decision_years()[-1]),
                               capacity_mw=P.PHASE2_CAPACITY_MW)
    dys = lsm.expand_decision_years()
    merch = lsm.expand_option(price, gen2, decision_years=dys)
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    bars = [(f"Expand now\n@yr{dys[0]}", merch.expand_now, BLUE),
            ("Expand option\n(optimal timing)", merch.option_value, GREEN)]
    for i, (lab, v, c) in enumerate(bars):
        axL.bar(i, v / BN, color=c, width=0.5, alpha=0.9)
        axL.text(i, v / BN, f"£{v / BN:+.2f}bn", ha="center",
                 va="bottom" if v >= 0 else "top", fontsize=9.5, fontweight="bold")
    axL.axhline(0, color=RED, lw=2)
    axL.set_xticks(range(len(bars))); axL.set_xticklabels([b[0] for b in bars], fontsize=8.5)
    axL.set_ylabel("Value (£bn)"); axL.set_title("Phase-2 expand option (merchant)")
    axL.grid(True, axis="y", alpha=0.25)
    be = lcoe.breakeven_price()
    _box(axL, f"Merchant Phase 2 is out of the money\n(sim price ~£{price.mean():.0f} < "
              f"break-even ~£{be:.0f}).\nOption value = the right not to expand.", va="top",
         xy=(0.97, 0.97))

    # engine check: as a guaranteed full-life contract price rises past break-even, value climbs
    levels = np.arange(70, 156, 5, dtype=float)
    vals = [lsm.expand_option(price, gen2, decision_years=dys, cfd_strike=L,
                              cfd_term_years=P.OPERATING_LIFE_YEARS).option_value / BN for L in levels]
    axR.plot(levels, vals, color=GREEN, marker="o", ms=3, label="fixed-price Phase 2")
    axR.axvline(price.mean(), color="0.4", ls="--", label=f"sim mean £{price.mean():.0f}")
    axR.axvline(be, color=DARK, ls=":", label=f"break-even £{be:.0f}")
    axR.axhline(0, color=RED, lw=1.5)
    axR.set_xlabel("Phase-2 achieved price (£/MWh)"); axR.set_ylabel("Option value (£bn)")
    axR.set_title("Engine check: value climbs once ITM"); axR.legend(fontsize=8)
    axR.grid(True, alpha=0.25)
    fig.suptitle(f"Chart 5: Expand option ({price.shape[0]:,} paths)", fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return _save(fig, "chart5_expand.png")


def chart_abandon(n_paths):
    price, gen = lsm.simulate(n_paths)
    base = lsm.abandon_option(price, gen)
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    st, add, tot = base.static_npv / BN, base.add_on / BN, base.option_value / BN
    axL.bar(0, st, color=BLUE, width=0.6, alpha=0.9)
    axL.bar(1, add, bottom=st, color=GREEN, width=0.6, alpha=0.9)
    axL.bar(2, tot, color=DARK, width=0.6, alpha=0.9)
    axL.text(0, st, f"£{st:+.2f}bn", ha="center", va="top", fontsize=9.5, fontweight="bold")
    axL.text(1, tot, f"+£{add:.2f}bn", ha="center", va="bottom", fontsize=9.5, fontweight="bold")
    axL.text(2, tot, f"£{tot:+.2f}bn", ha="center", va="top", fontsize=9.5, fontweight="bold")
    axL.axhline(0, color=RED, lw=2)
    axL.set_xticks(range(3)); axL.set_xticklabels(["Static\n(hold)", "Divest\nadd-on", "With\ndivest"],
                                                  fontsize=8.5)
    axL.set_ylabel("NPV (£bn)"); axL.set_title("Divestment lifts NPV (still < 0)")
    axL.grid(True, axis="y", alpha=0.25)
    _box(axL, f"WACC-gap sale: buyer {base.buyer_wacc:.1%} vs us {P.WACC:.1%},\n"
              f"net {base.transaction_cost:.0%} cost. Inputs are PLACEHOLDERS.", va="top",
         xy=(0.5, 0.97), ha="center")

    buyer_waccs = np.linspace(0.045, P.WACC, 7)
    for txn, c, ls in [(0.0, GREEN, "-"), (0.02, DARK, "--"), (0.05, RED, ":")]:
        adds = [lsm.abandon_option(price, gen, buyer_wacc=bw, transaction_cost=txn).add_on / BN
                for bw in buyer_waccs]
        axR.plot(buyer_waccs * 100, adds, marker="o", ms=3, color=c, ls=ls, label=f"txn {txn:.0%}")
    axR.axhline(0, color=RED, lw=1.5)
    axR.axvline(P.WACC * 100, color="0.4", ls="--", label=f"our WACC {P.WACC:.1%}")
    axR.set_xlabel("Buyer WACC (%)"); axR.set_ylabel("Divest add-on (£bn)")
    axR.set_title("Add-on vanishes as the WACC gap closes"); axR.legend(fontsize=8)
    axR.grid(True, alpha=0.25)
    fig.suptitle(f"Chart 6: Abandon (divestment) option ({price.shape[0]:,} paths)", fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    return _save(fig, "chart6_abandon.png")


CHARTS = [
    ("Price fan", chart_price_fan), ("Generation", chart_generation), ("NPV", chart_npv),
    ("Sensitivity", chart_sensitivity), ("Defer", chart_defer), ("Expand", chart_expand),
    ("Abandon", chart_abandon),
]


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    n_paths = P.N_PATHS
    for a in argv:
        if a == "--final":
            n_paths = P.N_PATHS_FINAL
        elif a.startswith("--n="):
            n_paths = int(a.split("=")[1])

    print(f"Regenerating {len(CHARTS)} charts at {n_paths:,} paths -> {P.CHARTS_DIR}\n")
    t0 = time.time()
    for i, (label, fn) in enumerate(CHARTS, 1):
        path = fn(n_paths)
        print(f"  [{i}/{len(CHARTS)}] {label:<12} -> {path.name}")
    print(f"\nDone in {time.time() - t0:.0f}s.")


if __name__ == "__main__":
    main()
