"""
Values the project's real options with Longstaff-Schwartz Monte Carlo (2001).

A real option is the right, not the obligation, to make a decision later once you have seen how
prices move. We value three:

  - defer   : the right to delay committing Phase-1 capital (wait and watch the price).
  - expand  : the right to build a +500 MW Phase 2 during a window after Phase-1 start-up.
  - abandon : the right to sell the running asset mid-life to a lower-cost-of-capital buyer.

The method (`_american_option` below) steps backwards through the simulated price paths. At each
yearly decision node it compares "act now" against "wait and decide next year."

The subtle part: acting now (say, committing to build) locks in a 35-year cash flow whose value
depends on the *whole future price path*, which we cannot know at the decision node. Using each
path's realised value would be cheating (looking into the future). So we estimate BOTH the
act-now value and the wait value as functions of today's observable price, by regressing across
all paths, and decide on those estimates, while banking the actual realised value where we act.
This "look-ahead-free" comparison is the heart of Longstaff-Schwartz.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np

from config import parameters as P
from src.price_simulator import simulate_price_paths
from src.generation_model import simulate_generation
from src.financial_model import value_from_decision_year, value_paths, divestment_advantage

LIFE = P.OPERATING_LIFE_YEARS


# --------------------------------------------------------------------------------------------
# The Longstaff-Schwartz core
# --------------------------------------------------------------------------------------------
def _expected_given_price(price_now: np.ndarray, value: np.ndarray, degree: int) -> np.ndarray:
    """Estimate E[value | today's price] by fitting a low-degree polynomial in price across all
    paths (least squares). Returns the fitted value per path. Price is standardised first so the
    polynomial stays well-conditioned."""
    z = (price_now - price_now.mean()) / (price_now.std() + 1e-12)
    basis = np.vander(z, degree + 1)          # columns [z^degree, ..., z, 1]
    coef, *_ = np.linalg.lstsq(basis, value, rcond=None)
    return basis @ coef


def _american_option(payoff: np.ndarray, price_state: np.ndarray, *, wacc: float, degree: int,
                     must_act_by_end: bool) -> tuple[np.ndarray, np.ndarray]:
    """Backward induction over decision nodes 0..T.

      payoff[:, t]      value of acting at node t, expressed in node-t money.
      price_state[:, t] the observable price at node t (the regression variable).

    Returns (value_at_node_0 per path, action_node per path; -1 = never acted). If
    must_act_by_end is True the last node forces an action (e.g. "you will build by the deadline");
    otherwise acting is always optional and the option value is floored at zero (walk away)."""
    n, n_nodes = payoff.shape
    last = n_nodes - 1
    disc = 1.0 / (1.0 + wacc)

    if must_act_by_end:
        value = payoff[:, last].copy()
        action = np.full(n, last)
    else:
        act = _expected_given_price(price_state[:, last], payoff[:, last], degree) > 0.0
        value = np.where(act, payoff[:, last], 0.0)
        action = np.where(act, last, -1)

    for t in range(last - 1, -1, -1):
        act_value = _expected_given_price(price_state[:, t], payoff[:, t], degree)
        wait_value = _expected_given_price(price_state[:, t], value * disc, degree)
        act = act_value > wait_value
        if not must_act_by_end:
            act &= act_value > 0.0                 # never act into an expected loss
        value = np.where(act, payoff[:, t], value * disc)   # bank the real payoff where we act
        action = np.where(act, t, action)
    return value, action


def _mix(action: np.ndarray, nodes) -> dict:
    """Share of paths acting at each node, plus the share that never act. `action` and `nodes`
    both hold actual decision years (not indices), so they compare directly."""
    out = {int(t): float((action == t).mean()) for t in nodes}
    out["never"] = float((action == -1).mean())
    return out


# --------------------------------------------------------------------------------------------
# Defer: the right to delay committing Phase-1 capital
# --------------------------------------------------------------------------------------------
@dataclass
class DeferResult:
    option_value: float          # mean value with the defer right
    static_npv: float            # mean NPV of committing today (no option), the benchmark
    commit_year: np.ndarray      # per path: year committed, -1 = never built
    d_max: int

    @property
    def premium(self) -> float:
        return self.option_value - self.static_npv


def commit_npvs(price, gen, d_max: int, *, wacc=P.WACC) -> np.ndarray:
    """ex[:, t] = NPV of committing at year t (t = 0..d_max), in year-t money. price must carry
    d_max + life columns."""
    ex = np.empty((price.shape[0], d_max + 1))
    for t in range(d_max + 1):
        ex[:, t] = value_from_decision_year(price, gen, t, wacc=wacc).npv
    return ex


def defer_option(price, gen, d_max=P.DEFERRAL_MAX_YEARS, *, can_walk_away=True, wacc=P.WACC,
                 degree=P.LSM_BASIS_DEGREE, ex: np.ndarray | None = None) -> DeferResult:
    """Value the right to wait up to `d_max` years before committing. can_walk_away=True also
    allows never building; can_walk_away=False is pure timing (you will build by year d_max)."""
    if ex is None:
        ex = commit_npvs(price, gen, d_max, wacc=wacc)
    ex = ex[:, :d_max + 1]
    value0, commit_year = _american_option(ex, price[:, :d_max + 1], wacc=wacc, degree=degree,
                                            must_act_by_end=not can_walk_away)
    years = np.arange(d_max + 1)
    commit_year = np.where(commit_year >= 0, years[np.where(commit_year >= 0, commit_year, 0)], -1)
    return DeferResult(option_value=float(value0.mean()), static_npv=float(ex[:, 0].mean()),
                       commit_year=commit_year, d_max=d_max)


# --------------------------------------------------------------------------------------------
# Expand: an American option to add a +500 MW Phase 2 after Phase-1 start-up
# --------------------------------------------------------------------------------------------
@dataclass
class ExpandResult:
    option_value: float          # value of the optimally-timed expansion right, at FID
    expand_now: float            # value of committing Phase 2 at the first chance, at FID
    exercise_year: np.ndarray    # per path: year expanded, -1 = never
    decision_years: np.ndarray

    @property
    def premium(self) -> float:
        return self.option_value - self.expand_now


def expand_decision_years() -> np.ndarray:
    """FID-relative years Phase 2 may be committed: the window runs after Phase-1 start-up
    (start-up = FID + construction)."""
    lo, hi = P.EXPAND_WINDOW_YEARS
    return np.arange(P.CONSTRUCTION_YEARS + lo, P.CONSTRUCTION_YEARS + hi + 1)


def expand_option(price, gen2, *, wacc=P.WACC, degree=P.LSM_BASIS_DEGREE, decision_years=None,
                  cfd_strike=P.CFD_STRIKE, cfd_term_years=0) -> ExpandResult:
    """Value the Phase-2 expansion right (Phase 1 is sunk, so this is its standalone value). Phase
    2 is fully merchant by default (cfd_term_years=0); pass CfD args for the contracted variant.
    Expanding is always optional, so the value is >= 0."""
    if decision_years is None:
        decision_years = expand_decision_years()
    decision_years = np.asarray(decision_years)
    capex_per_kw = P.CAPEX_PER_KW["central"] * (1.0 - P.EXPAND_CAPEX_LEARNING)

    ex = np.empty((price.shape[0], len(decision_years)))
    for k, d in enumerate(decision_years):
        ex[:, k] = value_from_decision_year(price, gen2, int(d), P.PHASE2_CAPACITY_MW, wacc=wacc,
                                             capex_per_kw=capex_per_kw, cfd_strike=cfd_strike,
                                             cfd_term_years=cfd_term_years).npv
    value, idx = _american_option(ex, price[:, decision_years], wacc=wacc, degree=degree,
                                  must_act_by_end=False)
    to_fid = (1.0 / (1.0 + wacc)) ** int(decision_years[0])   # first window year -> FID
    exercise_year = np.where(idx >= 0, decision_years[np.where(idx >= 0, idx, 0)], -1)
    return ExpandResult(option_value=float(value.mean()) * to_fid,
                        expand_now=float(ex[:, 0].mean()) * to_fid,
                        exercise_year=exercise_year, decision_years=decision_years)


# --------------------------------------------------------------------------------------------
# Abandon: the right to sell the running asset mid-life to a lower-WACC buyer
# --------------------------------------------------------------------------------------------
@dataclass
class AbandonResult:
    option_value: float          # static NPV + optimally-timed sale value, at FID
    static_npv: float            # NPV of building and holding to the end (no sale)
    add_on: float                # value the right to sell adds
    sell_year: np.ndarray        # per path: operating year sold, -1 = held to end
    buyer_wacc: float
    transaction_cost: float


def abandon_option(price, gen, *, wacc=P.WACC, degree=P.LSM_BASIS_DEGREE, buyer_wacc=P.BUYER_WACC,
                   transaction_cost=P.TRANSACTION_COST) -> AbandonResult:
    """Value the right to divest mid-life. The sell "payoff" at each operating year is the
    advantage of selling over holding (see financial_model.divestment_advantage). Selling is
    optional, so the add-on is >= 0. The static NPV of building and holding is the benchmark."""
    advantage = divestment_advantage(price, gen, our_wacc=wacc, buyer_wacc=buyer_wacc,
                                     transaction_cost=transaction_cost)
    static = value_paths(price[:, :LIFE], gen, wacc=wacc).npv
    add_on, idx = _american_option(advantage, price[:, :LIFE], wacc=wacc, degree=degree,
                                   must_act_by_end=False)
    to_fid = (1.0 / (1.0 + wacc)) ** P.CONSTRUCTION_YEARS   # operating year 0 -> FID
    sell_year = np.where(idx >= 0, idx, -1)                 # node index == operating year here
    return AbandonResult(option_value=float(static.mean()) + float(add_on.mean()) * to_fid,
                         static_npv=float(static.mean()), add_on=float(add_on.mean()) * to_fid,
                         sell_year=sell_year, buyer_wacc=buyer_wacc,
                         transaction_cost=transaction_cost)


# --------------------------------------------------------------------------------------------
# Simulation helpers and CLI
# --------------------------------------------------------------------------------------------
def simulate(n_paths=P.N_PATHS, extra_price_years=0, seed=P.RANDOM_SEED, capacity_mw=P.CAPACITY_MW):
    """Return (price, gen). `extra_price_years` adds price columns beyond the operating life so a
    decision can be deferred; capacity_mw sizes the generation (Phase 2 uses PHASE2_CAPACITY_MW)."""
    pp = simulate_price_paths(n_paths=n_paths, horizon=LIFE + extra_price_years, seed=seed)
    gp = simulate_generation(n_paths=n_paths, horizon=LIFE, seed=seed + 1, capacity_mw=capacity_mw)
    n = min(pp.annual_prices.shape[0], gp.generation_mwh.shape[0])
    return pp.annual_prices[:n], gp.generation_mwh[:n]


def report(n_paths=P.N_PATHS, option="defer") -> str:
    bn = 1e9
    if option == "defer":
        price, gen = simulate(n_paths, extra_price_years=P.DEFERRAL_MAX_YEARS)
        full = defer_option(price, gen, can_walk_away=True)
        timing = defer_option(price, gen, can_walk_away=False)
        mix = _mix(full.commit_year, np.arange(full.d_max + 1))
        return "\n".join([
            f"Defer option ({price.shape[0]:,} paths, up to {full.d_max} yr):",
            f"  commit today (static NPV)     £{full.static_npv / bn:+.3f}bn",
            f"  defer + timing only           £{timing.option_value / bn:+.3f}bn",
            f"  defer + walk-away             £{full.option_value / bn:+.3f}bn  "
            f"(premium £{full.premium / bn:+.3f}bn)",
            "  commit-year mix: " + ", ".join(f"yr{t} {mix[t]:.0%}" for t in range(full.d_max + 1))
            + f", never {mix['never']:.0%}",
        ])
    if option == "expand":
        # a Phase 2 committed at the last window year operates for `life` years beyond it, so the
        # price paths must extend that far past the operating life.
        price, gen2 = simulate(n_paths, extra_price_years=int(expand_decision_years()[-1]),
                               capacity_mw=P.PHASE2_CAPACITY_MW)
        res = expand_option(price, gen2)
        mix = _mix(res.exercise_year, res.decision_years)
        return "\n".join([
            f"Expand option ({price.shape[0]:,} paths, +{P.PHASE2_CAPACITY_MW:.0f}MW merchant):",
            f"  expand at first chance        £{res.expand_now / bn:+.3f}bn",
            f"  expand option (optimal time)  £{res.option_value / bn:+.3f}bn  "
            f"(premium £{res.premium / bn:+.3f}bn)",
            "  exercise mix: " + ", ".join(f"yr{int(d)} {mix[int(d)]:.0%}" for d in res.decision_years)
            + f", never {mix['never']:.0%}",
        ])
    if option == "abandon":
        price, gen = simulate(n_paths)
        res = abandon_option(price, gen)
        sellers = res.sell_year[res.sell_year >= 0]
        return "\n".join([
            f"Abandon option ({price.shape[0]:,} paths, buyer WACC {res.buyer_wacc:.1%} vs ours "
            f"{P.WACC:.1%}, txn {res.transaction_cost:.0%}):",
            f"  build and hold (static NPV)   £{res.static_npv / bn:+.3f}bn",
            f"  with divestment right         £{res.option_value / bn:+.3f}bn  "
            f"(add-on £{res.add_on / bn:+.3f}bn)",
            f"  sold: {(res.sell_year >= 0).mean():.0%} of paths, "
            f"median sale year {int(np.median(sellers)) if sellers.size else -1}",
        ])
    raise ValueError(f"unknown option {option!r}")


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    option = next((a.split("=")[1] for a in argv if a.startswith("--option=")), "defer")
    n_paths = next((int(a.split("=")[1]) for a in argv if a.startswith("--n=")), P.N_PATHS)
    print(report(n_paths, option))


if __name__ == "__main__":
    main()
