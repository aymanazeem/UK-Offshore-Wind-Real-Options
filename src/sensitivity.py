"""
One-at-a-time sensitivity of the static NPV. Which sourced input range moves value most, and
where each lever must sit for the project to break even.

Prices and generation are simulated once and held fixed. Only the economics flex, so each bar
isolates one assumption. Reported on the mean NPV. The flat-fan, CfD-dominated distribution is
tight enough that the mean approximates the central path, verified in financial_model.

OPEX is split into its location-specific TNUoS component and the rest, O&M and insurance. TNUoS
is both the largest single driver and the most uncertain input, so it earns its own lever rather
than hiding inside a combined OPEX bar.
"""

from __future__ import annotations

import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.optimize import brentq  # noqa: E402

from config import parameters as P  # noqa: E402
from src.price_simulator import simulate_price_paths  # noqa: E402
from src.generation_model import simulate_generation  # noqa: E402
from src.financial_model import value_paths  # noqa: E402

OC = P.OPEX_COMPONENTS_PER_MW_YEAR_K
OMINS = {k: OC["om"][k] + OC["insurance"][k] for k in ("low", "central", "high")}  # non-locational
TNUOS = OC["connection_uos"]

# label -> (low, central, high, build econ-kwargs from a scalar value)
LEVERS = [
    ("CAPEX (£/kW)",            P.CAPEX_PER_KW,            lambda v: {"capex_per_kw": v}),
    ("TNUoS (k£/MW/yr)",        TNUOS,                     lambda v: {"opex_per_mw_year_k": OMINS["central"] + v}),
    ("O&M + insurance (k£/MW/yr)", OMINS,                  lambda v: {"opex_per_mw_year_k": TNUOS["central"] + v}),
    ("WACC (%)",                P.WACC_SENSITIVITY,        lambda v: {"wacc": v}),
    ("Capacity factor",         P.CF_RANGE,                lambda v: {"cf": v}),
    ("CfD strike (£/MWh)",      P.CFD_STRIKE_SENSITIVITY,  lambda v: {"cfd_strike": v}),
]

# brackets for the break-even root-find, the lever value that sets NPV=0
BREAKEVEN_BRACKET = {
    "CAPEX (£/kW)": (200.0, 12_000.0),
    "TNUoS (k£/MW/yr)": (-300.0, 400.0),
    "O&M + insurance (k£/MW/yr)": (-300.0, 400.0),
    "WACC (%)": (0.001, 0.40),
    "Capacity factor": (0.10, 0.99),
    "CfD strike (£/MWh)": (0.0, 400.0),
}


def npv_mean(price, gen, *, cf=P.CF_MEAN, **econ) -> float:
    """Mean NPV in £ on fixed paths. `cf` rescales mean generation linearly. The rest,
    capex_per_kw, opex_per_mw_year_k, wacc and cfd_strike, pass straight to value_paths."""
    g = gen if cf == P.CF_MEAN else gen * (cf / P.CF_MEAN)
    return float(value_paths(price, g, **econ).npv.mean())


def breakeven(price, gen, label, build) -> float | None:
    lo, hi = BREAKEVEN_BRACKET[label]

    def f(v):
        kw = build(v)
        return npv_mean(price, gen, **kw)

    try:
        if f(lo) * f(hi) > 0:
            return None
        return float(brentq(f, lo, hi, xtol=1e-4))
    except ValueError:
        return None


def compute(n_paths: int = P.N_PATHS, seed: int = P.RANDOM_SEED):
    """Simulate once, then sweep each lever across low, central and high, and solve its break-even."""
    life = P.OPERATING_LIFE_YEARS
    pp = simulate_price_paths(n_paths=n_paths, horizon=life, seed=seed)
    gp = simulate_generation(n_paths=n_paths, horizon=life, seed=seed + 1)
    n = min(pp.annual_prices.shape[0], gp.generation_mwh.shape[0])
    price, gen = pp.annual_prices[:n], gp.generation_mwh[:n]

    base = npv_mean(price, gen)
    rows = []
    for label, rng, build in LEVERS:
        lo = npv_mean(price, gen, **build(rng["low"]))
        hi = npv_mean(price, gen, **build(rng["high"]))
        be = breakeven(price, gen, label, build)
        rows.append({
            "label": label, "rng": rng, "build": build,
            "npv_low": lo, "npv_high": hi, "breakeven": be,
            "swing": abs(hi - lo),
        })
    rows.sort(key=lambda r: r["swing"])
    return base, rows, price, gen


# Chart 3, tornado and break-even on the hero lever TNUoS
def plot_sensitivity(base, rows, price, gen, save_path=None):
    if save_path is None:
        save_path = P.CHARTS_DIR / "chart3_sensitivity.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    bn = 1e9

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(14, 5.6))

    # Left panel, tornado, widest swing on top
    y = np.arange(len(rows))
    for i, r in enumerate(rows):
        lo, hi = r["npv_low"] / bn, r["npv_high"] / bn
        left, right = min(lo, hi), max(lo, hi)
        axL.barh(i, right - left, left=left, height=0.62, color="#9ecae1",
                 edgecolor="0.4", linewidth=0.6, zorder=3)
        # endpoint labels = the input values that produce each NPV end
        axL.text(lo, i + 0.30, f"{_fmt(r,'low')}", fontsize=7.5, ha="center", va="bottom", color="#08519c")
        axL.text(hi, i + 0.30, f"{_fmt(r,'high')}", fontsize=7.5, ha="center", va="bottom", color="#08519c")
    axL.axvline(base / bn, color="0.35", lw=1.4, zorder=4, label=f"base £{base/bn:.2f}bn")
    axL.axvline(0, color="#d62728", lw=2, zorder=4, label="break-even")
    axL.set_yticks(y)
    axL.set_yticklabels([r["label"] for r in rows], fontsize=9)
    axL.set_xlabel("NPV (£bn, real 2024)")
    axL.set_title("Tornado: NPV sensitivity to each sourced input range")
    axL.legend(loc="lower right", fontsize=8)
    axL.grid(True, axis="x", alpha=0.25)

    # Right panel, NPV vs TNUoS, the hero lever, with sourced points and break-even crossing
    tn = TNUOS
    xs = np.linspace(0, max(160, tn["high"] + 20), 60)
    ys = np.array([npv_mean(price, gen, opex_per_mw_year_k=OMINS["central"] + x) for x in xs]) / bn
    axR.plot(xs, ys, color="#08519c", lw=2)
    axR.axhline(0, color="#d62728", lw=2)
    for k, c in [("low", "#2ca02c"), ("central", "#ff7f0e"), ("high", "#d62728")]:
        xv = tn[k]
        yv = npv_mean(price, gen, opex_per_mw_year_k=OMINS["central"] + xv) / bn
        axR.scatter([xv], [yv], color=c, s=55, zorder=5, edgecolor="white", linewidth=0.8)
        axR.text(xv, yv + 0.06, f"{k}\n£{xv:.0f}k", fontsize=8, ha="center", va="bottom", color=c)
    be = next(r["breakeven"] for r in rows if r["label"].startswith("TNUoS"))
    if be is not None:
        axR.scatter([be], [0], color="black", s=45, zorder=6)
        axR.annotate(f"break-even\nTNUoS £{be:.0f}k/MW/yr", (be, 0), xytext=(be, 0.55),
                     fontsize=8.5, ha="center", arrowprops=dict(arrowstyle="->", color="0.3"))
    axR.set_xlabel("TNUoS connection charge (k£/MW/yr)")
    axR.set_ylabel("NPV (£bn, real 2024)")
    axR.set_title("Hero lever: NPV vs TNUoS")
    axR.grid(True, alpha=0.25)

    fig.suptitle(f"Chart 3: Static-NPV sensitivity ({price.shape[0]:,} paths, base £{base/bn:.2f}bn)",
                 fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig, (axL, axR)


def _fmt(r, end) -> str:
    """Format the input value at the low or high end of a lever for the tornado labels."""
    v = r["rng"][end]
    lab = r["label"]
    if lab.startswith("WACC"):
        return f"{v:.1%}"
    if lab.startswith("Capacity"):
        return f"{v:.2f}"
    return f"{v:.0f}"


def report(base, rows) -> str:
    bn = 1e9
    lines = [
        f"Static NPV base case: £{base / bn:.2f}bn   (break-even target: £0)",
        f"{'lever':<28}{'low input':>12}{'high input':>12}{'NPV swing £bn':>15}{'break-even':>16}",
    ]
    for r in reversed(rows):  # widest first
        rng = r["rng"]
        be = r["breakeven"]
        be_s = "n/a" if be is None else (f"{be:.1%}" if r["label"].startswith("WACC")
                                       else f"{be:.2f}" if r["label"].startswith("Capacity")
                                       else f"{be:.0f}")
        lo_s = f"{rng['low']:.3g}"
        hi_s = f"{rng['high']:.3g}"
        lines.append(
            f"{r['label']:<28}{lo_s:>12}{hi_s:>12}"
            f"{(r['npv_high'] - r['npv_low']) / bn:>+15.2f}{be_s:>16}"
        )
    lines.append("  break-even = lever value, holding all others central, that sets NPV=0. "
                 "Central CfD strike £90.91, central TNUoS £83.4k")
    return "\n".join(lines)


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    n_paths = P.N_PATHS
    for arg in argv:
        if arg.startswith("--n="):
            n_paths = int(arg.split("=", 1)[1])

    print(f"Sweeping static-NPV sensitivities on {n_paths:,} fixed paths ...")
    base, rows, price, gen = compute(n_paths=n_paths)
    print(report(base, rows))

    out = P.CHARTS_DIR / "chart3_sensitivity.png"
    plot_sensitivity(base, rows, price, gen, save_path=out)
    print(f"\nSaved sensitivity chart -> {out}")


if __name__ == "__main__":
    main()
