"""
Simulates many possible futures for the UK wholesale electricity price.

The wind farm's revenue depends on a price nobody can know in advance, so instead of betting on
one forecast we generate thousands of plausible price paths and value the project on all of them.

The price is modelled in three layers, all in log space so everything is a percentage move:

    log(price) = season(month)  +  short_term  +  long_term_level

  - season       a fixed repeating within-year pattern (winter peak, summer dip), fitted once.
  - short_term   fast, temporary swings that always pull back toward zero (an Ornstein-Uhlenbeck,
                 i.e. mean-reverting, process). Fitted to recent history.
  - long_term    the slowly-moving equilibrium price level. It follows a random walk, so it does
                 NOT pull back: small shocks accumulate and the range of possible prices keeps
                 widening the further out we look. This is what gives decades-out uncertainty.

This two-factor split (Schwartz-Smith, 2000) matters for the real options: deferring or expanding
is only worth anything if the future is genuinely uncertain. A one-factor mean-reverting model
would snap back to its average within weeks and leave the 40-year price fan almost flat, wrongly
making every timing option worthless. The long-term random-walk factor fixes that.

Calibration note: the short-term factor is fitted to ~2.5 years of recent monthly prices. The
long-term volatility cannot be estimated from so little data, so it is a forward-looking
assumption (config.PRICE_LT_VOL) and is always reported as a sensitivity.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from config import parameters as P

MONTHS_PER_YEAR = 12
DT = 1.0 / MONTHS_PER_YEAR  # one calibration/simulation step is one month


# --------------------------------------------------------------------------------------------
# Seasonal pattern
# --------------------------------------------------------------------------------------------
def fractional_year(dates: pd.Series) -> np.ndarray:
    """Where each date sits in the calendar year, as a fraction in [0, 1)."""
    doy = dates.dt.dayofyear.to_numpy()
    year_len = np.where(dates.dt.is_leap_year.to_numpy(), 366.0, 365.0)
    return doy / year_len


def seasonal_design(tau: np.ndarray) -> np.ndarray:
    """Predictor columns for the seasonal fit: a constant plus one and two cycles per year.

    These four waves let the fitted season bend to a winter peak, a summer dip and a smaller
    twice-a-year ripple. tau repeats every year, so the pattern repeats cleanly."""
    tau = np.asarray(tau, dtype=float)
    return np.column_stack([
        np.ones_like(tau),
        np.sin(2 * np.pi * tau), np.cos(2 * np.pi * tau),
        np.sin(4 * np.pi * tau), np.cos(4 * np.pi * tau),
    ])


def fit_seasonal(dates: pd.Series, log_price: np.ndarray) -> np.ndarray:
    """Least-squares fit of the seasonal waves to log price. Returns the 5 coefficients."""
    coef, *_ = np.linalg.lstsq(seasonal_design(fractional_year(dates)), log_price, rcond=None)
    return coef


# --------------------------------------------------------------------------------------------
# Calibration
# --------------------------------------------------------------------------------------------
def _load_history(csv_path=P.PRICE_DAILY_CSV, since: str = P.PRICE_HISTORY_START) -> pd.DataFrame:
    """Daily real prices from `since` onward, date-sorted. The model works in log prices, so the
    rare days whose average was zero or negative are left out."""
    df = (pd.read_csv(csv_path, parse_dates=["date"])
          .sort_values("date").reset_index(drop=True))
    keep = (df["price_real_gbp_per_mwh"] > 0) & (df["date"] >= pd.Timestamp(since))
    return df[keep].reset_index(drop=True)


def _monthly_deseasonalised(df: pd.DataFrame, seasonal_coef: np.ndarray) -> np.ndarray:
    """Strip the season out of daily log price, then average to one value per calendar month.

    We average the log residuals (not price levels) so there is no bias from taking a log of an
    average. The result is the short-term series the mean-reverting model is fitted to."""
    logp = np.log(df["price_real_gbp_per_mwh"].to_numpy())
    residual = logp - seasonal_design(fractional_year(df["date"])) @ seasonal_coef
    month_id = (df["date"].dt.year * 12 + df["date"].dt.month).to_numpy()
    _, inverse = np.unique(month_id, return_inverse=True)   # unique() sorts, so months stay ordered
    counts = np.bincount(inverse)
    return np.bincount(inverse, weights=residual) / counts


def fit_short_term(x: np.ndarray) -> dict:
    """Fit the monthly deseasonalised series as a mean-reverting (Ornstein-Uhlenbeck) process.

    We regress each month on the one before, x[t] = a + b*x[t-1] + noise (an AR(1) fit, which is
    the exact best fit for this process). From (a, b) we recover the three plain-English numbers:
      kappa  how fast a swing pulls back (bigger = faster),
      level  the value it pulls back toward,
      sigma  how big the monthly random shocks are (annualised).
    """
    x0, x1 = x[:-1], x[1:]
    (a, b), *_ = np.linalg.lstsq(np.column_stack([np.ones_like(x0), x0]), x1, rcond=None)
    residual_sd = float((x1 - (a + b * x0)).std(ddof=2))

    kappa = float(-np.log(b) / DT)
    level = float(a / (1.0 - b))
    sigma = float(residual_sd * np.sqrt(-2.0 * np.log(b) / (DT * (1.0 - b ** 2))))
    return {
        "kappa": kappa,
        "sigma": sigma,
        "level": level,
        "x_last": float(x[-1]),              # today's short-term value, the simulation start
        "half_life_days": float(np.log(2.0) / kappa * 365.0),
        "n_months": int(len(x)),
    }


def calibrate(csv_path=P.PRICE_DAILY_CSV) -> dict:
    """Fit the seasonal pattern and the short-term factor, and record the long-term assumption.
    Returns the dict written to config/price_calibrated.json."""
    df = _load_history(csv_path)
    seasonal_coef = fit_seasonal(df["date"], np.log(df["price_real_gbp_per_mwh"].to_numpy()))
    short = fit_short_term(_monthly_deseasonalised(df, seasonal_coef))

    years = df["date"].dt.year.to_numpy()
    price = df["price_real_gbp_per_mwh"].to_numpy()
    annual_means = {int(y): float(price[years == y].mean()) for y in np.unique(years)}
    return {
        "metadata": {
            "model": "two-factor: seasonal + mean-reverting short term + random-walk long term",
            "history_window": [str(df["date"].min().date()), str(df["date"].max().date())],
            "n_daily_obs": int(len(df)),
            "note": ("Short-term factor fitted to this window. Long-term volatility is a "
                     "forward-looking assumption (config.PRICE_LT_VOL), reported as a sensitivity."),
        },
        "seasonal_coefficients": [float(c) for c in seasonal_coef],
        "short_term": short,
        "long_term": {"sigma_per_year": P.PRICE_LT_VOL, "drift_per_year": P.PRICE_LT_DRIFT},
        "sim_start_date": P.SIM_START_DATE,
        "history": {"mean_price": float(price.mean()), "annual_means": annual_means},
    }


def load_calibration(path=P.PRICE_CALIBRATION_JSON) -> dict:
    """Load the calibration, regenerating it from the price CSV if the file is missing."""
    if not path.exists():
        cal = calibrate()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cal, indent=2))
        return cal
    return json.loads(path.read_text())


# --------------------------------------------------------------------------------------------
# Simulation
# --------------------------------------------------------------------------------------------
@dataclass
class PricePaths:
    """Simulated annual-average wholesale prices, £/MWh, shape (n_paths, horizon)."""
    annual_prices: np.ndarray
    calendar_year: np.ndarray
    params: dict

    def percentiles(self, qs=(10, 50, 90)) -> dict:
        return {q: np.percentile(self.annual_prices, q, axis=0) for q in qs}


def simulate_price_paths(
    n_paths: int = P.N_PATHS,
    horizon: int = P.CONSTRUCTION_YEARS + P.OPERATING_LIFE_YEARS,
    seed: int = P.RANDOM_SEED,
    antithetic: bool = P.ANTITHETIC,
    lt_vol: float = P.PRICE_LT_VOL,
    lt_drift: float = P.PRICE_LT_DRIFT,
) -> PricePaths:
    """Simulate `n_paths` price futures, each `horizon` years of annual-average £/MWh.

    We step month by month. The short-term factor takes an exact mean-reverting step; the
    long-term level takes a random-walk step. We add the season back, undo the log to get a £
    price, and average the 12 months into one annual price. `lt_vol`/`lt_drift` are exposed so the
    sensitivity analysis can flex the long-term assumption without re-calibrating."""
    cal = load_calibration()
    st = cal["short_term"]
    kappa, sigma_st, level, x_last = st["kappa"], st["sigma"], st["level"], st["x_last"]
    seasonal_coef = np.asarray(cal["seasonal_coefficients"], dtype=float)

    if antithetic and n_paths % 2:
        n_paths += 1  # need an even count to pair each draw with its mirror

    # Exact one-month steps (no discretisation error). The short-term step keeps a fraction `decay`
    # of the current swing and adds noise; the long-term step just adds drift and noise.
    decay = np.exp(-kappa * DT)
    sd_short = sigma_st * np.sqrt((1.0 - np.exp(-2.0 * kappa * DT)) / (2.0 * kappa))
    sd_long = lt_vol * np.sqrt(DT)

    # Split today's deviation: the reverting part is the short-term factor, the level is long-term.
    short = np.full(n_paths, x_last - level, dtype=float)
    long = np.full(n_paths, level, dtype=float)

    # Precompute the seasonal value at each simulated month.
    start = pd.Timestamp(cal["sim_start_date"])
    start_frac = float(fractional_year(pd.Series([start]))[0])
    step_tau = (start_frac + (np.arange(horizon * MONTHS_PER_YEAR) + 1) * DT) % 1.0
    season = seasonal_design(step_tau) @ seasonal_coef

    rng = np.random.default_rng(seed)
    half = n_paths // 2
    annual = np.empty((n_paths, horizon), dtype=float)

    step = 0
    for yr in range(horizon):
        monthly_price_sum = np.zeros(n_paths)
        for _ in range(MONTHS_PER_YEAR):
            z_short, z_long = _draws(rng, n_paths, half, antithetic)
            short = short * decay + sd_short * z_short
            long = long + lt_drift * DT + sd_long * z_long
            monthly_price_sum += np.exp(season[step] + short + long)
            step += 1
        annual[:, yr] = monthly_price_sum / MONTHS_PER_YEAR

    calendar_year = start.year + start_frac + 0.5 + np.arange(horizon)
    return PricePaths(annual_prices=annual, calendar_year=calendar_year,
                      params={"kappa": kappa, "sigma_short": sigma_st, "level": level,
                              "sigma_long": lt_vol, "half_life_days": st["half_life_days"],
                              "n_months": st["n_months"]})


def _draws(rng, n_paths, half, antithetic):
    """Two independent standard-normal shocks per step, antithetic-mirrored if requested."""
    if antithetic:
        zs = rng.standard_normal((2, half))
        z = np.concatenate([zs, -zs], axis=1)  # pair each draw with its negative
        return z[0], z[1]
    z = rng.standard_normal((2, n_paths))
    return z[0], z[1]


def main(argv=None) -> None:
    """Recalibrate from the price CSV and print the price fan's widening over the horizon."""
    argv = sys.argv[1:] if argv is None else argv
    n_paths = next((int(a.split("=")[1]) for a in argv if a.startswith("--n=")), P.N_PATHS)

    cal = calibrate()
    P.PRICE_CALIBRATION_JSON.write_text(json.dumps(cal, indent=2))
    st = cal["short_term"]
    print(f"Calibrated on {cal['metadata']['history_window'][0]} .. "
          f"{cal['metadata']['history_window'][1]} ({st['n_months']} months)")
    print(f"  short-term: kappa={st['kappa']:.2f} (half-life {st['half_life_days']:.0f} days), "
          f"sigma={st['sigma']:.3f}, level={st['level']:.3f}")
    print(f"  long-term : sigma={P.PRICE_LT_VOL:.3f}/yr (assumption)")

    paths = simulate_price_paths(n_paths=n_paths)
    pct = paths.percentiles()
    print(f"\nPrice fan over the horizon ({n_paths:,} paths):")
    print(f"  {'year':>5} {'P10':>7} {'P50':>7} {'P90':>7} {'P90/P10':>8}")
    horizon = paths.annual_prices.shape[1]
    for yr in (0, 4, 14, 24, horizon - 1):
        p10, p50, p90 = pct[10][yr], pct[50][yr], pct[90][yr]
        print(f"  {yr + 1:>5} {p10:>7.1f} {p50:>7.1f} {p90:>7.1f} {p90 / p10:>8.2f}")
    print("  (P90/P10 should GROW with the horizon under the two-factor model)")


if __name__ == "__main__":
    main()
