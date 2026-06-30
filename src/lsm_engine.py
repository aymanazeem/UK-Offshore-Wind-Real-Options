"""
Longstaff-Schwartz valuation of the project's real options. Step backwards through the price
paths and, at each annual decision node, weigh acting now against the regression-estimated value
of waiting.

  - defer, the right to delay committing Phase-1 capital, watching the price before locking in.
  - expand, an American option to add a 500 MW Phase 2 during a window after Phase-1 COD. Phase 1
    is treated as sunk, so this is the standalone incremental value of the expansion right.
  - abandon, the right to divest the operating Phase-1 asset mid-life to a lower-WACC buyer. The
    same cash flows discounted at the buyer's lower rate are worth more, so this is a largely
    deterministic WACC-gap transfer, net of a transaction cost, not a price-tail play.

Two readings of the defer option.
  - walk-away, you may also decide never to build, so the terminal floor is max(NPV, 0).
  - timing-only, you will build by the last allowed year. The only choice is when.
The gap between them separates the value of being able to abandon from the value of pure timing.
Expand is always walk-away, since you are never forced to build Phase 2, so its value is >= 0.

Conventions.
  - A project committed at decision year d reads merchant price column d+j in its operating
    year j, the stationary-OU convention that price column j is operating year j. See
    value_from_decision_year. So price needs d_max + life columns.
  - Each node's payoff EX[:, t] is the commit-at-t NPV in year-t money. Adjacent years are
    bridged by a single WACC discount factor.
  - decision year 0 with no walk-away is just the static valuation, so the engine reproduces
    the -£1.27bn headline bit-identically, asserted in main().

Method follows Longstaff & Schwartz (2001), Review of Financial Studies.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from config import parameters as P  # noqa: E402
from src.price_simulator import simulate_price_paths  # noqa: E402
from src.generation_model import simulate_generation  # noqa: E402
from src.financial_model import (  # noqa: E402
    value_from_decision_year, value_paths, value_of_remaining_operations,
)


@dataclass
class DeferResult:
    """Defer-option value at FID and the per-path decisions behind it, all in £."""

    option_value: float          # mean LSM value at t=0
    static_npv: float            # mean commit-now NPV, the no-option benchmark
    value0: np.ndarray           # (n_paths,) per-path option value at t=0
    commit_year: np.ndarray      # (n_paths,) chosen commit year, -1 = never build
    d_max: int
    allow_walkaway: bool

    @property
    def option_premium(self) -> float:
        """Value the option adds over committing today."""
        return self.option_value - self.static_npv

    def commit_mix(self) -> dict:
        """Share of paths committing in each year, and the share that never build."""
        out = {t: float((self.commit_year == t).mean()) for t in range(self.d_max + 1)}
        out["never"] = float((self.commit_year == -1).mean())
        return out


def commit_values(price, gen, d_max, *, wacc=P.WACC) -> np.ndarray:
    """EX[:, t] = NPV of committing at decision year t, in year-t money, for t = 0..d_max.
    Computed once at the largest d_max and sliced for smaller horizons. price must carry
    d_max + life columns."""
    n = price.shape[0]
    ex = np.empty((n, d_max + 1))
    for t in range(d_max + 1):
        ex[:, t] = value_from_decision_year(price, gen, t, wacc=wacc).npv
    return ex


def _fit(x: np.ndarray, y: np.ndarray, degree: int) -> np.ndarray:
    """Conditional expectation E[y | x], fitted by least squares on a monomial basis
    [1, z, z^2, ...] in the standardised state z. Returns the fitted values."""
    z = (x - x.mean()) / (x.std() + 1e-12)
    basis = np.vstack([z ** k for k in range(degree + 1)]).T
    coef, *_ = np.linalg.lstsq(basis, y, rcond=None)
    return basis @ coef


def _lsm(ex: np.ndarray, state: np.ndarray, *, allow_walkaway: bool, wacc=P.WACC,
         degree=P.LSM_BASIS_DEGREE):
    """Backward induction on precomputed payoffs.

    ex is (n, d_max+1), the commit-at-t NPV in year-t money. state is (n, d_max+1), the observable
    price at each decision year, which is the regression variable. Returns (value0 per path,
    commit_year per path).

    The commit payoff is the project NPV from the decision date, itself a forward expectation, not
    a spot function of the state, so committing on a path's realised NPV would peek at prices
    decades ahead. We instead regress the commit value on the observable state, alongside the
    continuation, and decide on those F_t expectations, while banking the realised outcome. This is
    the look-ahead-free LSM (cf. Gamba 2003) and is what we carry into the expand and abandon
    options."""
    n, cols = ex.shape
    d_max = cols - 1
    disc = 1.0 / (1.0 + wacc)

    # Terminal node. With walk-away, commit only where the expected commit value is positive.
    # Otherwise we must build, so commit regardless. Bank the realised NPV where we commit.
    if allow_walkaway:
        commit = _fit(state[:, d_max], ex[:, d_max], degree) > 0.0
        v = np.where(commit, ex[:, d_max], 0.0)
        commit_year = np.where(commit, d_max, -1)
    else:
        v = ex[:, d_max].copy()
        commit_year = np.full(n, d_max)

    for t in range(d_max - 1, -1, -1):
        h_hat = _fit(state[:, t], ex[:, t], degree)       # E[commit at t | F_t]
        c_hat = _fit(state[:, t], v * disc, degree)       # E[continue | F_t]
        commit = h_hat > c_hat
        if allow_walkaway:
            commit &= h_hat > 0.0                          # never commit to a negative expectation
        v = np.where(commit, ex[:, t], v * disc)          # bank the realised outcome
        commit_year = np.where(commit, t, commit_year)

    return v, commit_year


def lsm_defer(price, gen, d_max=P.DEFERRAL_MAX_YEARS, *, allow_walkaway=True, wacc=P.WACC,
              degree=P.LSM_BASIS_DEGREE, ex: np.ndarray | None = None) -> DeferResult:
    """Value the defer option over 0..d_max years. Pass precomputed `ex`, from commit_values at the
    largest d_max, to sweep d_max without re-valuing every node."""
    if ex is None:
        ex = commit_values(price, gen, d_max, wacc=wacc)
    else:
        ex = ex[:, :d_max + 1]
    state = price[:, :d_max + 1]
    v0, commit_year = _lsm(ex, state, allow_walkaway=allow_walkaway, wacc=wacc, degree=degree)
    return DeferResult(
        option_value=float(v0.mean()),
        static_npv=float(ex[:, 0].mean()),
        value0=v0,
        commit_year=commit_year,
        d_max=d_max,
        allow_walkaway=allow_walkaway,
    )


def simulate(n_paths=P.N_PATHS, d_max=P.DEFERRAL_MAX_YEARS, seed=P.RANDOM_SEED):
    """Price paths long enough to defer, life + d_max columns. Age-indexed generation."""
    life = P.OPERATING_LIFE_YEARS
    pp = simulate_price_paths(n_paths=n_paths, horizon=life + d_max, seed=seed)
    gp = simulate_generation(n_paths=n_paths, horizon=life, seed=seed + 1)
    n = min(pp.annual_prices.shape[0], gp.generation_mwh.shape[0])
    return pp.annual_prices[:n], gp.generation_mwh[:n]


# Chart 4, defer-option value decomposition and how it grows with the deferral window
def plot_defer(price, gen, d_max=P.DEFERRAL_MAX_YEARS, *, wacc=P.WACC, save_path=None):
    if save_path is None:
        save_path = P.CHARTS_DIR / "chart4_defer.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    bn = 1e9

    ex = commit_values(price, gen, d_max, wacc=wacc)
    static = float(ex[:, 0].mean())
    full = lsm_defer(price, gen, d_max, allow_walkaway=True, ex=ex)
    timing = lsm_defer(price, gen, d_max, allow_walkaway=False, ex=ex)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    # Left panel, the three valuations side by side. The full option's premium over commit-now is
    # almost entirely the right not to build. Genuine price-timing value is near zero, see box.
    bars = [
        ("Commit now\n(static NPV)", static, "#1f77b4"),
        (f"Defer ≤{d_max}y,\nmust build", timing.option_value, "#08519c"),
        (f"Defer ≤{d_max}y\n+ walk-away", full.option_value, "#2ca02c"),
    ]
    for i, (lab, v, c) in enumerate(bars):
        axL.bar(i, v / bn, color=c, width=0.6, alpha=0.9)
        axL.text(i, v / bn + (0.03 if v >= 0 else -0.03), f"£{v / bn:+.2f}bn", ha="center",
                 va="bottom" if v >= 0 else "top", fontsize=9.5, fontweight="bold")
    axL.axhline(0, color="#d62728", lw=2)
    axL.set_xticks(range(len(bars)))
    axL.set_xticklabels([lab for lab, _, _ in bars], fontsize=8.5)
    axL.set_ylabel("Value (£bn, real 2024)")
    axL.set_ylim(min(static / bn * 1.12, -0.1), 0.2)
    axL.set_title("Defer option vs commit-now")
    axL.grid(True, axis="y", alpha=0.25)
    box = ("Premium is the right not to build.\n"
           "Price-timing value ≈ £0,\n"
           "fixed CfD and flat single-factor fan.\n"
           "Must-build gain is just discounting\n"
           "a deferred loss, not information.")
    axL.text(0.97, 0.34, box, transform=axL.transAxes, fontsize=8, va="center", ha="right",
             bbox=dict(boxstyle="round,pad=0.4", fc="#fff7e6", ec="0.7", alpha=0.95))

    # Right panel, option value vs how long we may defer, with and without the walk-away right.
    ds = np.arange(d_max + 1)
    v_wa = np.array([lsm_defer(price, gen, d, allow_walkaway=True, ex=ex).option_value
                     for d in ds]) / bn
    v_to = np.array([lsm_defer(price, gen, d, allow_walkaway=False, ex=ex).option_value
                     for d in ds]) / bn
    axR.plot(ds, v_wa, marker="o", color="#2ca02c", lw=2, label="with walk-away")
    axR.plot(ds, v_to, marker="s", color="#08519c", lw=2, label="must build (timing only)")
    axR.axhline(static / bn, color="0.35", lw=1.4, ls="--", label=f"static £{static / bn:.2f}bn")
    axR.axhline(0, color="#d62728", lw=2, label="break-even")
    axR.set_xticks(ds)
    axR.set_xlabel("Maximum deferral (years)")
    axR.set_ylabel("Value (£bn, real 2024)")
    axR.set_title("Option value vs deferral window")
    axR.legend(loc="center right", fontsize=8)
    axR.grid(True, alpha=0.25)

    fig.suptitle(f"Chart 4: Defer option, Longstaff-Schwartz ({price.shape[0]:,} paths, "
                 f"WACC {wacc:.1%})", fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig, (axL, axR)


def report(price, gen, d_max=P.DEFERRAL_MAX_YEARS, *, wacc=P.WACC) -> str:
    bn = 1e9
    ex = commit_values(price, gen, d_max, wacc=wacc)
    static = float(ex[:, 0].mean())
    floor = lsm_defer(price, gen, 0, allow_walkaway=True, ex=ex).option_value
    full = lsm_defer(price, gen, d_max, allow_walkaway=True, ex=ex)
    timing = lsm_defer(price, gen, d_max, allow_walkaway=False, ex=ex)
    mix = full.commit_mix()

    lines = [
        f"Defer option ({price.shape[0]:,} paths, d_max={d_max}, WACC {wacc:.1%})",
        f"  static NPV (commit now)          £{static / bn:+.3f}bn",
        f"  walk-away floor (no deferral)    £{floor / bn:+.3f}bn   "
        f"(commit today only if E[NPV|today] > 0)",
        f"  full defer option (walk-away)    £{full.option_value / bn:+.3f}bn   "
        f"premium £{full.option_premium / bn:+.3f}bn",
        f"  timing-only (must build)         £{timing.option_value / bn:+.3f}bn   "
        f"premium £{timing.option_premium / bn:+.3f}bn",
        "  decomposition of the option premium over static:",
        f"    walk-away (right not to build) £{(floor - static) / bn:+.3f}bn",
        f"    timing (when to build)         £{(full.option_value - floor) / bn:+.3f}bn",
        "  commit-year mix (full option): "
        + ", ".join(f"yr{t} {mix[t]:.0%}" for t in range(d_max + 1))
        + f", never {mix['never']:.0%}",
    ]
    return "\n".join(lines)


# Expand option, an American option to add a 500 MW Phase 2 after Phase-1 COD

@dataclass
class ExpandResult:
    """Standalone value of the Phase-2 expand option at FID, with Phase 1 assumed built and sunk."""

    option_value: float          # mean option value, discounted to FID
    expand_now: float            # commit Phase 2 at the first window year regardless, at FID
    value0: np.ndarray           # (n_paths,) per-path option value at FID
    exercise_year: np.ndarray    # (n_paths,) FID-relative year expanded, -1 = never
    decision_years: np.ndarray   # window decision years from FID, COD = FID + construction
    merchant: bool

    @property
    def option_premium(self) -> float:
        """Value the timing and decline flexibility adds over expanding at the first opportunity."""
        return self.option_value - self.expand_now

    def exercise_mix(self) -> dict:
        out = {int(d): float((self.exercise_year == d).mean()) for d in self.decision_years}
        out["never"] = float((self.exercise_year == -1).mean())
        return out


def phase2_capex_per_kw(learning_rate: float = P.EXPAND_CAPEX_LEARNING_RATE) -> float:
    """Phase-2 £/kW after the build-out learning discount."""
    return P.CAPEX_PER_KW_CENTRAL * (1.0 - learning_rate)


def expand_decision_years(construction: int = P.CONSTRUCTION_PERIOD_YEARS,
                          window=P.EXPAND_DECISION_WINDOW_YEARS) -> np.ndarray:
    """FID-relative years at which Phase 2 may be committed. COD = FID + construction, and the
    window runs `window` years after COD, so decision years are construction+lo .. construction+hi."""
    lo, hi = window
    return np.arange(construction + lo, construction + hi + 1)


def expand_commit_values(price, gen2, decision_years, *, wacc=P.WACC,
                         capacity_mw=P.PHASE2_CAPACITY_MW, capex_per_kw=None,
                         cfd_strike=P.CFD_STRIKE, cfd_term_years=0) -> np.ndarray:
    """ex[:, k] = NPV of committing Phase 2 at decision_years[k], in that year's money. Fully
    merchant by default, cfd_term_years=0. Pass the CfD args for the contracted variant."""
    if capex_per_kw is None:
        capex_per_kw = phase2_capex_per_kw()
    ex = np.empty((price.shape[0], len(decision_years)))
    for k, d in enumerate(decision_years):
        ex[:, k] = value_from_decision_year(
            price, gen2, int(d), capacity_mw, wacc=wacc, capex_per_kw=capex_per_kw,
            cfd_strike=cfd_strike, cfd_term_years=cfd_term_years).npv
    return ex


def lsm_expand(price, gen2, *, wacc=P.WACC, degree=P.LSM_BASIS_DEGREE,
               capacity_mw=P.PHASE2_CAPACITY_MW, capex_per_kw=None,
               cfd_strike=P.CFD_STRIKE, cfd_term_years=0,
               decision_years=None, ex: np.ndarray | None = None) -> ExpandResult:
    """Value the American expand option over the Phase-2 window. Phase 1 is sunk, so this is the
    incremental option value alone. Declining to expand is always allowed, so it is >= 0.

    Reuses the look-ahead-free `_lsm`. Regress the Phase-2 commit value on the observed price
    state, decide, bank the realised NPV. The first window node sits at year decision_years[0], so
    its value is discounted back to FID."""
    if decision_years is None:
        decision_years = expand_decision_years()
    decision_years = np.asarray(decision_years)
    if ex is None:
        ex = expand_commit_values(price, gen2, decision_years, wacc=wacc,
                                  capacity_mw=capacity_mw, capex_per_kw=capex_per_kw,
                                  cfd_strike=cfd_strike, cfd_term_years=cfd_term_years)
    state = price[:, decision_years]
    disc = 1.0 / (1.0 + wacc)
    d0 = int(decision_years[0])

    v, idx = _lsm(ex, state, allow_walkaway=True, wacc=wacc, degree=degree)
    value0 = v * disc ** d0
    exercise_year = np.where(idx >= 0, decision_years[np.where(idx >= 0, idx, 0)], -1)
    return ExpandResult(
        option_value=float(value0.mean()),
        expand_now=float(ex[:, 0].mean()) * disc ** d0,
        value0=value0,
        exercise_year=exercise_year,
        decision_years=decision_years,
        merchant=(cfd_term_years == 0),
    )


def simulate_expand(n_paths=P.N_PATHS, seed=P.RANDOM_SEED):
    """Price paths spanning the whole Phase-2 window, life + last decision year columns, and
    co-located Phase-2 generation. The Phase-1 CF draws are scaled to Phase-2 capacity, so the two
    phases share wind and Phase 2 is age-indexed from its own COD."""
    life = P.OPERATING_LIFE_YEARS
    d_last = int(expand_decision_years()[-1])
    pp = simulate_price_paths(n_paths=n_paths, horizon=life + d_last, seed=seed)
    gp = simulate_generation(n_paths=n_paths, horizon=life, seed=seed + 1)
    n = min(pp.annual_prices.shape[0], gp.generation_mwh.shape[0])
    gen2 = gp.generation_mwh[:n] * (P.PHASE2_CAPACITY_MW / P.CAPACITY_MW)
    return pp.annual_prices[:n], gen2


# Chart 5, expand-option value and how it responds to the price Phase 2 actually achieves
def plot_expand(price, gen2, *, wacc=P.WACC, save_path=None):
    if save_path is None:
        save_path = P.CHARTS_DIR / "chart5_expand.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    bn = 1e9
    dys = expand_decision_years()

    merch = lsm_expand(price, gen2, wacc=wacc, decision_years=dys, cfd_term_years=0)
    cfd = lsm_expand(price, gen2, wacc=wacc, decision_years=dys,
                     cfd_strike=P.CFD_STRIKE, cfd_term_years=P.CFD_TERM_YEARS)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    # Left panel, expanding at the first opportunity, no option, vs the optimally-timed option, for
    # a merchant Phase 2 and the CfD-reuse sensitivity. Both options sit near £0. The value is the
    # right not to expand, since merchant revenue is far below break-even, see box.
    bars = [
        (f"Expand now\n@yr{dys[0]} (merchant)", merch.expand_now, "#1f77b4"),
        ("Expand option\n(merchant)", merch.option_value, "#2ca02c"),
        ("Expand option\n(CfD £90.91)", cfd.option_value, "#08519c"),
    ]
    vals_bn = [v / bn for _, v, _ in bars]
    for i, (lab, v, c) in enumerate(bars):
        axL.bar(i, v / bn, color=c, width=0.6, alpha=0.9)
        axL.text(i, v / bn + (0.008 if v >= 0 else -0.008), f"£{v / bn:+.2f}bn", ha="center",
                 va="bottom" if v >= 0 else "top", fontsize=9.5, fontweight="bold")
    axL.axhline(0, color="#d62728", lw=2)
    axL.set_ylim(min(vals_bn) - 0.05, max(vals_bn) + 0.06)
    axL.set_xticks(range(len(bars)))
    axL.set_xticklabels([lab for lab, _, _ in bars], fontsize=8.5)
    axL.set_ylabel("Value (£bn, real 2024)")
    axL.set_title("Phase-2 expand option (Phase 1 sunk)", pad=10)
    axL.grid(True, axis="y", alpha=0.25)
    box = ("Merchant ~£85 < break-even ~£120\n"
           "→ deeply out-of-the-money.\n"
           "Option value = the right not to\n"
           "expand. Timing ≈ £0, flat fan and\n"
           "√35 averaging starve uncertainty.")
    axL.text(0.97, 0.6, box, transform=axL.transAxes, fontsize=8, va="center", ha="right",
             bbox=dict(boxstyle="round,pad=0.4", fc="#fff7e6", ec="0.7", alpha=0.95))

    # Right panel, option value vs the price Phase 2 actually achieves, a fixed full-life contract.
    # The engine returns genuine ITM value once price clears break-even. At the calibrated
    # merchant level, ~£85, it correctly sits at ~£0, so the £0 base case is economics, not a bug.
    levels = np.arange(70, 156, 5, dtype=float)
    vals = np.array([
        lsm_expand(price, gen2, wacc=wacc, decision_years=dys,
                   cfd_strike=L, cfd_term_years=P.OPERATING_LIFE_YEARS).option_value
        for L in levels
    ]) / bn
    axR.plot(levels, vals, color="#2ca02c", lw=2, marker="o", ms=3, label="fixed-price Phase 2")
    axR.axhline(merch.option_value / bn, color="#2ca02c", ls=":", lw=1.3,
                label=f"merchant base £{merch.option_value / bn:.2f}bn")
    axR.axhline(0, color="#d62728", lw=1.5)
    trans = axR.get_xaxis_transform()
    merch_price = float(price.mean())
    axR.axvline(merch_price, color="0.35", ls="--", lw=1.2)
    axR.text(merch_price - 1.5, 0.6, f"sim mean £{merch_price:.0f}", transform=trans,
             fontsize=8, color="0.35", va="center", ha="right", rotation=90)
    axR.axvline(P.CFD_STRIKE, color="#08519c", ls="--", lw=1.2)
    axR.text(P.CFD_STRIKE + 1.6, 0.6, f"CfD £{P.CFD_STRIKE:.0f}", transform=trans,
             fontsize=8, color="#08519c", va="center", ha="left", rotation=90)
    axR.set_xlabel("Phase-2 achieved price (£/MWh, full-life contract)")
    axR.set_ylabel("Expand option value (£bn, real 2024)")
    axR.set_title("Engine check: value vs achieved price")
    axR.legend(loc="upper left", fontsize=8)
    axR.grid(True, alpha=0.25)

    fig.suptitle(f"Chart 5: Phase-2 expand option, Longstaff-Schwartz "
                 f"({price.shape[0]:,} paths, WACC {wacc:.1%})", fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig, (axL, axR)


def report_expand(price, gen2, *, wacc=P.WACC) -> str:
    bn = 1e9
    dys = expand_decision_years()
    merch = lsm_expand(price, gen2, wacc=wacc, decision_years=dys, cfd_term_years=0)
    cfd = lsm_expand(price, gen2, wacc=wacc, decision_years=dys,
                     cfd_strike=P.CFD_STRIKE, cfd_term_years=P.CFD_TERM_YEARS)
    mix = merch.exercise_mix()
    lines = [
        f"Expand option ({price.shape[0]:,} paths, +{P.PHASE2_CAPACITY_MW:.0f}MW, "
        f"window COD+{P.EXPAND_DECISION_WINDOW_YEARS}, FID yrs {dys[0]}-{dys[-1]}, "
        f"capex £{phase2_capex_per_kw():,.0f}/kW)",
        f"  sim mean annual price £{price.mean():.1f}/MWh   (CfD strike £{P.CFD_STRIKE:.2f})",
        "  merchant Phase 2:",
        f"    expand now @yr{dys[0]} (regardless)  £{merch.expand_now / bn:+.3f}bn",
        f"    expand option (optimal timing)    £{merch.option_value / bn:+.3f}bn   "
        f"premium £{merch.option_premium / bn:+.3f}bn",
        "    exercise mix: "
        + ", ".join(f"yr{int(d)} {mix[int(d)]:.0%}" for d in dys)
        + f", never {mix['never']:.0%}",
        "  CfD-reuse sensitivity (£90.91, 20yr):",
        f"    expand option                     £{cfd.option_value / bn:+.3f}bn",
    ]
    return "\n".join(lines)


# Abandon option, mid-life divestment of the operating Phase-1 asset to a lower-WACC buyer

@dataclass
class AbandonResult:
    """Value of the divestment right on the built Phase-1 asset, expressed at FID."""

    option_value: float          # static NPV plus optimally-timed divestment add-on
    static_npv: float            # NPV with no divestment right, build and hold to end
    add_on: float                # value the right to sell adds over holding to end
    sell_now: float              # NPV if we divest at the first eligible year regardless
    value0: np.ndarray           # (n_paths,) per-path total value at FID
    sell_year: np.ndarray        # (n_paths,) operating year sold, -1 = never sell, hold to end
    decision_years: np.ndarray   # operating years, 0 = COD, at which divestment is allowed
    buyer_wacc: float
    transaction_cost: float

    @property
    def option_premium(self) -> float:
        """Value the timing flexibility adds over divesting at the first opportunity."""
        return self.option_value - self.sell_now

    def sell_mix(self) -> dict:
        out = {int(t): float((self.sell_year == t).mean()) for t in self.decision_years}
        out["never"] = float((self.sell_year == -1).mean())
        return out


def divest_decision_years(life: int = P.OPERATING_LIFE_YEARS) -> np.ndarray:
    """Operating years, 0 = COD, at which the asset may be divested. Year 0 is the
    developer-to-yieldco flip at commissioning. The LSM reveals where selling is optimal."""
    return np.arange(life)


def abandon_advantage_values(price, gen, decision_years, *, wacc=P.WACC,
                             buyer_wacc=P.DIVESTMENT_BUYER_WACC,
                             transaction_cost=P.DIVESTMENT_TRANSACTION_COST,
                             capacity_mw=P.CAPACITY_MW, cfd_strike=P.CFD_STRIKE,
                             cfd_term_years=P.CFD_TERM_YEARS) -> np.ndarray:
    """A[:, k] = sell-advantage at decision_years[k], in that operating year's money.
        (1 - transaction_cost) * V_buyer - V_us
    where V_* is value_of_remaining_operations at the buyer's and our WACC. Positive where the
    WACC gap beats the transaction cost. Both legs are forward expectations, so committing on a
    path's realised advantage would peek ahead. `_lsm` regresses A on the observed price first."""
    A = np.empty((price.shape[0], len(decision_years)))
    for k, t in enumerate(decision_years):
        v_buyer = value_of_remaining_operations(
            price, gen, int(t), capacity_mw, wacc=buyer_wacc,
            cfd_strike=cfd_strike, cfd_term_years=cfd_term_years)
        v_us = value_of_remaining_operations(
            price, gen, int(t), capacity_mw, wacc=wacc,
            cfd_strike=cfd_strike, cfd_term_years=cfd_term_years)
        A[:, k] = (1.0 - transaction_cost) * v_buyer - v_us
    return A


def lsm_abandon(price, gen, decision_years=None, *, wacc=P.WACC, degree=P.LSM_BASIS_DEGREE,
                buyer_wacc=P.DIVESTMENT_BUYER_WACC,
                transaction_cost=P.DIVESTMENT_TRANSACTION_COST,
                capacity_mw=P.CAPACITY_MW, cfd_strike=P.CFD_STRIKE,
                cfd_term_years=P.CFD_TERM_YEARS, A: np.ndarray | None = None) -> AbandonResult:
    """Value the American divestment option. At each operating year, sell the asset to a
    lower-WACC buyer or keep operating. Reuses the look-ahead-free `_lsm` on the sell-advantage
    A(t). Declining to sell is always allowed, so the add-on is >= 0. The headline is the static
    NPV, build and hold to end, plus this optimally-timed add-on."""
    life = gen.shape[1]
    if decision_years is None:
        decision_years = divest_decision_years(life)
    decision_years = np.asarray(decision_years)
    if A is None:
        A = abandon_advantage_values(
            price, gen, decision_years, wacc=wacc, buyer_wacc=buyer_wacc,
            transaction_cost=transaction_cost, capacity_mw=capacity_mw,
            cfd_strike=cfd_strike, cfd_term_years=cfd_term_years)

    static = value_paths(price[:, :life], gen, capacity_mw, wacc=wacc, cfd_strike=cfd_strike).npv
    state = price[:, decision_years]
    v_addon, idx = _lsm(A, state, allow_walkaway=True, wacc=wacc, degree=degree)

    c = P.CONSTRUCTION_PERIOD_YEARS
    d0 = int(decision_years[0])
    fid = (1.0 / (1.0 + wacc)) ** (c + d0)          # operating year d0 -> FID
    value0 = static + v_addon * fid
    sell_year = np.where(idx >= 0, decision_years[np.where(idx >= 0, idx, 0)], -1)
    static_npv = float(static.mean())
    add_on = float(v_addon.mean()) * fid
    return AbandonResult(
        option_value=static_npv + add_on,
        static_npv=static_npv,
        add_on=add_on,
        sell_now=static_npv + float(A[:, 0].mean()) * fid,
        value0=value0,
        sell_year=sell_year,
        decision_years=decision_years,
        buyer_wacc=buyer_wacc,
        transaction_cost=transaction_cost,
    )


def simulate_abandon(n_paths=P.N_PATHS, seed=P.RANDOM_SEED):
    """Price and generation over the operating life. No horizon extension, since divestment does
    not shift the operating window. Same seeds as the static and defer base case."""
    life = P.OPERATING_LIFE_YEARS
    pp = simulate_price_paths(n_paths=n_paths, horizon=life, seed=seed)
    gp = simulate_generation(n_paths=n_paths, horizon=life, seed=seed + 1)
    n = min(pp.annual_prices.shape[0], gp.generation_mwh.shape[0])
    return pp.annual_prices[:n], gp.generation_mwh[:n]


# Chart 6, how the divestment right lifts the headline NPV, and its dependence on the two unsourced inputs
def plot_abandon(price, gen, *, wacc=P.WACC, save_path=None):
    if save_path is None:
        save_path = P.CHARTS_DIR / "chart6_abandon.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    bn = 1e9

    base = lsm_abandon(price, gen, wacc=wacc)
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13.5, 5.4))

    # Left panel, waterfall. The WACC-gap add-on lifts the static NPV. Selling at COD captures all
    # of it, most life remaining, so optimal timing adds nothing and the headline still stays negative.
    static_bn, addon_bn, result_bn = base.static_npv / bn, base.add_on / bn, base.option_value / bn
    axL.bar(0, static_bn, color="#1f77b4", width=0.6, alpha=0.9)
    axL.bar(1, addon_bn, bottom=static_bn, color="#2ca02c", width=0.6, alpha=0.9)
    axL.bar(2, result_bn, color="#08519c", width=0.6, alpha=0.9)
    axL.plot([0.3, 0.7], [static_bn, static_bn], color="0.4", lw=0.9, ls="--")
    axL.plot([1.3, 1.7], [result_bn, result_bn], color="0.4", lw=0.9, ls="--")
    axL.text(0, static_bn - 0.03, f"£{static_bn:+.2f}bn", ha="center", va="top",
             fontsize=9.5, fontweight="bold")
    axL.text(1, result_bn + 0.025, f"+£{addon_bn:.2f}bn", ha="center", va="bottom",
             fontsize=9.5, fontweight="bold", color="#1a7a1a")
    axL.text(2, result_bn - 0.03, f"£{result_bn:+.2f}bn", ha="center", va="top",
             fontsize=9.5, fontweight="bold")
    axL.axhline(0, color="#d62728", lw=2)
    axL.set_ylim(static_bn - 0.20, 0.16)
    axL.set_xticks(range(3))
    axL.set_xticklabels(["Static NPV\n(build + hold)", "Divest\nadd-on", "NPV with\ndivest option"],
                        fontsize=8.5)
    axL.set_ylabel("NPV (£bn, real 2024)")
    axL.set_title("Divestment lifts the headline NPV", pad=10)
    axL.grid(True, axis="y", alpha=0.25)
    box = ("WACC-gap transfer, net 2% cost.\n"
           "Deterministic → sell at COD,\n"
           "no timing value. Inputs UNSOURCED.\n"
           "Still NPV < 0.")
    axL.text(0.5, 0.90, box, transform=axL.transAxes, fontsize=7.8, va="top", ha="center",
             bbox=dict(boxstyle="round,pad=0.4", fc="#fff7e6", ec="0.7", alpha=0.95))

    # Right panel, the add-on is purely a function of the unsourced buyer-WACC gap and transaction
    # cost. It must vanish as buyer WACC -> ours, no gap, a visual no-arbitrage check.
    buyer_waccs = np.linspace(0.045, wacc, 8)
    for tau, col, ls in [(0.0, "#2ca02c", "-"), (0.02, "#08519c", "--"), (0.05, "#d62728", ":")]:
        addons = np.array([
            lsm_abandon(price, gen, wacc=wacc, buyer_wacc=bw, transaction_cost=tau).add_on
            for bw in buyer_waccs
        ]) / bn
        axR.plot(buyer_waccs * 100, addons, marker="o", ms=3, color=col, ls=ls,
                 label=f"txn cost {tau:.0%}")
    axR.axhline(0, color="#d62728", lw=1.5)
    trans = axR.get_xaxis_transform()
    axR.axvline(wacc * 100, color="0.35", ls="--", lw=1.2)
    axR.text(wacc * 100 - 0.05, 0.55, f"our WACC {wacc:.1%}", transform=trans, fontsize=8,
             color="0.35", va="center", ha="right", rotation=90)
    axR.axvline(P.DIVESTMENT_BUYER_WACC * 100, color="#2ca02c", ls=":", lw=1.2)
    axR.text(P.DIVESTMENT_BUYER_WACC * 100 + 0.05, 0.55, f"placeholder {P.DIVESTMENT_BUYER_WACC:.0%}",
             transform=trans, fontsize=8, color="#2ca02c", va="center", ha="left", rotation=90)
    axR.set_xlabel("Buyer WACC (%)")
    axR.set_ylabel("Divestment add-on (£bn, real 2024)")
    axR.set_title("Add-on vs buyer WACC (both inputs unsourced)")
    axR.legend(loc="upper right", fontsize=8)
    axR.grid(True, alpha=0.25)

    fig.suptitle(f"Chart 6: Abandon (divestment) option, Longstaff-Schwartz "
                 f"({price.shape[0]:,} paths, WACC {wacc:.1%})", fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig, (axL, axR)


def report_abandon(price, gen, *, wacc=P.WACC) -> str:
    bn = 1e9
    res = lsm_abandon(price, gen, wacc=wacc)
    mix = res.sell_mix()
    sellers = res.sell_year[res.sell_year >= 0]
    med = int(np.median(sellers)) if sellers.size else -1
    lines = [
        f"Abandon / divestment option ({price.shape[0]:,} paths, buyer WACC {res.buyer_wacc:.1%} "
        f"vs ours {wacc:.1%}, txn cost {res.transaction_cost:.0%})",
        f"  static NPV (build + hold to end)   £{res.static_npv / bn:+.3f}bn",
        f"  divest now @COD (regardless)       £{res.sell_now / bn:+.3f}bn   "
        f"add-on £{(res.sell_now - res.static_npv) / bn:+.3f}bn",
        f"  divest option (optimal timing)     £{res.option_value / bn:+.3f}bn   "
        f"add-on £{res.add_on / bn:+.3f}bn   premium over sell-now £{res.option_premium / bn:+.3f}bn",
        f"  sell timing: yr0/COD {mix[0]:.0%}, never {mix['never']:.0%}, "
        f"median sell yr (sellers) {med}",
    ]
    return "\n".join(lines)


def main_defer(n_paths=P.N_PATHS) -> None:
    print(f"Valuing the defer option on {n_paths:,} paths ...")
    price, gen = simulate(n_paths=n_paths)

    # Validation, zero deferral with no walk-away must reproduce the static NPV bit-identically.
    static_lsm = lsm_defer(price, gen, d_max=0, allow_walkaway=False)
    static_ref = value_paths(price[:, :P.OPERATING_LIFE_YEARS], gen)
    d = abs(static_lsm.option_value - float(static_ref.npv.mean()))
    print(f"  [validation] LSM(d_max=0, no walk-away) mean NPV £{static_lsm.option_value / 1e9:.4f}bn "
          f"vs static £{static_ref.npv.mean() / 1e9:.4f}bn  |Δ|={d:.3e}")
    assert d < 1.0, "zero-deferral LSM must match the static NPV"

    print(report(price, gen))
    out = P.CHARTS_DIR / "chart4_defer.png"
    plot_defer(price, gen, save_path=out)
    print(f"\nSaved defer chart -> {out}")


def main_expand(n_paths=P.N_PATHS) -> None:
    print(f"Valuing the expand option on {n_paths:,} paths ...")
    price, gen2 = simulate_expand(n_paths=n_paths)
    assert price.shape[1] == P.OPERATING_LIFE_YEARS + int(expand_decision_years()[-1]), \
        "price horizon must span the last Phase-2 decision year + life"
    dys = expand_decision_years()
    d0 = int(dys[0])
    ex = expand_commit_values(price, gen2, dys)

    # Wiring check, a single-node forced expand reproduces the direct decision-year valuation.
    v_single, _ = _lsm(ex[:, :1], price[:, dys[:1]], allow_walkaway=False)
    ref = value_from_decision_year(price, gen2, d0, P.PHASE2_CAPACITY_MW,
                                   capex_per_kw=phase2_capex_per_kw(), cfd_term_years=0).npv.mean()
    d_check = abs(float(v_single.mean()) - ref)
    print(f"  [validation] single-node forced expand £{v_single.mean() / 1e9:.4f}bn "
          f"vs direct value £{ref / 1e9:.4f}bn  |Δ|={d_check:.3e}")
    assert d_check < 1.0, "single-node LSM must match the direct Phase-2 valuation"

    res = lsm_expand(price, gen2, ex=ex, decision_years=dys)
    assert res.option_value >= -1.0, "expand option value must be >= 0 (decline floor)"
    itm = lsm_expand(price, gen2, decision_years=dys, cfd_strike=140.0,
                     cfd_term_years=P.OPERATING_LIFE_YEARS)
    print(f"  [validation] expand option (merchant) £{res.option_value / 1e9:+.4f}bn >= 0, "
          f"ITM check (£140 contract) £{itm.option_value / 1e9:+.3f}bn > 0")
    assert itm.option_value > 0.0, "an above-break-even Phase 2 must give strictly positive value"

    print(report_expand(price, gen2))
    out = P.CHARTS_DIR / "chart5_expand.png"
    plot_expand(price, gen2, save_path=out)
    print(f"\nSaved expand chart -> {out}")


def main_abandon(n_paths=P.N_PATHS) -> None:
    print(f"Valuing the abandon (divestment) option on {n_paths:,} paths ...")
    price, gen = simulate_abandon(n_paths=n_paths)
    life = P.OPERATING_LIFE_YEARS

    # Spine check, the remaining-ops primitive, discounted back to FID, must rebuild the static NPV.
    from src.financial_model import total_capex, discount_factors
    c = P.CONSTRUCTION_PERIOD_YEARS
    v_us0 = float(value_of_remaining_operations(price, gen, 0, wacc=P.WACC).mean())
    pv_capex = (total_capex() / c) * float(discount_factors(np.arange(c) + 0.5).sum())
    recon = -pv_capex + (1.0 / (1.0 + P.WACC)) ** c * v_us0
    static_ref = float(value_paths(price[:, :life], gen).npv.mean())
    d_recon = abs(recon - static_ref)
    print(f"  [validation] hold-to-end via remaining-ops £{recon / 1e9:.4f}bn "
          f"vs static £{static_ref / 1e9:.4f}bn  |Δ|={d_recon:.3e}")
    assert d_recon < 1.0, "remaining-ops primitive must reconstruct the static NPV"

    # No-arbitrage check, buyer WACC = ours and zero txn cost => the divestment add-on must vanish.
    noarb = lsm_abandon(price, gen, buyer_wacc=P.WACC, transaction_cost=0.0)
    print(f"  [validation] no-arbitrage add-on (buyer=our WACC, 0 txn) "
          f"£{noarb.add_on / 1e9:+.4f}bn")
    assert abs(noarb.add_on) < 1.0, "no WACC gap and no cost => zero divestment value"

    print(report_abandon(price, gen))
    out = P.CHARTS_DIR / "chart6_abandon.png"
    plot_abandon(price, gen, save_path=out)
    print(f"\nSaved abandon chart -> {out}")


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    n_paths = P.N_PATHS
    option = "defer"
    for arg in argv:
        if arg.startswith("--n="):
            n_paths = int(arg.split("=", 1)[1])
        elif arg.startswith("--option="):
            option = arg.split("=", 1)[1]

    dispatch = {"expand": main_expand, "abandon": main_abandon}
    dispatch.get(option, main_defer)(n_paths)


if __name__ == "__main__":
    main()
