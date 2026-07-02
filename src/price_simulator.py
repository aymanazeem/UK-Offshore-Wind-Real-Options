"""
Simulates many possible futures for the UK wholesale electricity price.

The wind farm's revenue depends on a price nobody can know in advance, so rather than
betting on a single forecast we generate thousands of plausible price paths over the
project's life and pass them to the cash-flow and option-valuation models.

How it works. Electricity prices tend to drift back toward a long-run average rather than
wander off, so we use a mean-reverting model, an Ornstein-Uhlenbeck process, fitted to
historical prices. We strip out the seasonal pattern first, model what's left, then add
the season back and convert to yearly average prices.

Why we fit to monthly data. Fitting to daily prices makes the model snap back to average
within about a day, which wrongly squashes the year-to-year spread. Fitting to monthly
averages captures a realistic snap-back of about a month and gives a believable range of
future prices, so that is the default.

Caveat. This simple model settles into a fixed band of uncertainty after about a year and
then stays there, so it under-states how uncertain prices really are decades out. A richer
two-factor model would fix this and is the natural next step.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # headless, write PNG without a display
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402

from config import parameters as P  # noqa: E402

# frequency -> (steps_per_year, dt in years)
FREQUENCIES = {
    "daily": (365, 1.0 / 365.25),
    "weekly": (52, 7.0 / 365.25),
    "monthly": (12, 1.0 / 12.0),
}

# Seasonal design, intercept + annual + semiannual harmonics in fractional year tau.
SEASONAL_LABELS = ["1", "sin(2pi tau)", "cos(2pi tau)", "sin(4pi tau)", "cos(4pi tau)"]


# Seasonal component
def fractional_year(dates: pd.Series) -> np.ndarray:
    """Position within the calendar year in [0, 1), day-of-year / days-in-year."""
    doy = dates.dt.dayofyear.to_numpy()
    ylen = np.where(dates.dt.is_leap_year.to_numpy(), 366.0, 365.0)
    return doy / ylen


def seasonal_design(tau: np.ndarray) -> np.ndarray:
    """The predictor columns for the seasonal fit, evaluated at each date.

    A constant, plus one sine and cosine cycle per year and two cycles per year. Those four waves
    let the fit bend to the winter peak, the summer dip and a smaller twice-a-year ripple. tau is
    the position in the calendar year from 0 to 1, so the waves repeat cleanly every year."""
    tau = np.asarray(tau, dtype=float)
    return np.column_stack(
        [
            np.ones_like(tau),
            np.sin(2 * np.pi * tau),
            np.cos(2 * np.pi * tau),
            np.sin(4 * np.pi * tau),
            np.cos(4 * np.pi * tau),
        ]
    )


def fit_seasonal(dates: pd.Series, prices: np.ndarray) -> np.ndarray:
    """Fit the seasonal waves to log price by least squares, return the 5 coefficients.

    We fit in log price so the season is a percentage swing rather than a fixed pound amount,
    which is how power prices move."""
    tau = fractional_year(dates)
    logp = np.log(prices)
    coef, *_ = np.linalg.lstsq(seasonal_design(tau), logp, rcond=None)
    return coef


def deseasonalise(tau: np.ndarray, prices: np.ndarray, seasonal_coef: np.ndarray) -> np.ndarray:
    """Strip the fitted season out of log price, X = ln P - s(tau).

    What is left is the deseasonalised series, the part we treat as random and hand to the OU fit.
    Removing the season first stops the model mistaking the yearly pattern for randomness."""
    return np.log(prices) - seasonal_design(tau) @ seasonal_coef


# Frequency aggregation. numpy only, pandas .resample() segfaults under this env.
def aggregate_prices(df: pd.DataFrame, frequency: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (tau, price) at the requested frequency.

    daily   -> as-is.
    weekly  -> mean over consecutive 7-day blocks, series must be contiguous daily.
    monthly -> mean over calendar (year, month) buckets.
    """
    dates = df["date"]
    price = df["price_gbp_per_mwh"].to_numpy()
    tau = fractional_year(dates)

    if frequency == "daily":
        return tau, price

    if frequency == "weekly":
        n = len(price)
        grp = np.arange(n) // 7
        keep = grp < (n // 7)  # drop trailing partial week
        g = grp[keep]
        counts = np.bincount(g)
        price_w = np.bincount(g, weights=price[keep]) / counts
        tau_w = np.bincount(g, weights=tau[keep]) / counts
        return tau_w, price_w

    if frequency == "monthly":
        ym = (dates.dt.year * 12 + dates.dt.month).to_numpy()
        _, inv = np.unique(ym, return_inverse=True)
        counts = np.bincount(inv)
        price_m = np.bincount(inv, weights=price) / counts
        tau_m = np.bincount(inv, weights=tau) / counts
        return tau_m, price_m

    raise ValueError(f"Unknown frequency {frequency!r}, expected one of {list(FREQUENCIES)}")


# OU calibration by OLS AR(1)
def fit_ou_ar1(X: np.ndarray, dt: float) -> dict:
    """Fit the deseasonalised series as an AR(1), then convert to the three OU numbers kappa, mu,
    sigma.

    AR(1) means each step is a straight line on the step before plus noise, x1 = a + b*x0 + e. We
    fit that line by OLS. For an OU process this OLS fit is the exact maximum likelihood estimate,
    so it is not an approximation. b is the memory carried from one step to the next. We then back
    out the OU parameters, kappa the reversion speed, mu the long-run level, sigma the volatility."""
    x0, x1 = X[:-1], X[1:]
    A = np.column_stack([np.ones_like(x0), x0])
    (a, b), *_ = np.linalg.lstsq(A, x1, rcond=None)
    resid = x1 - (a + b * x0)
    resid_sd = float(resid.std(ddof=2))  # residual SD, 2 params fitted

    kappa = float(-np.log(b) / dt)          # reversion speed, b near 1 reverts slowly, near 0 fast
    mu = float(a / (1.0 - b))               # long-run level the series reverts to
    sigma = float(resid_sd * np.sqrt(-2.0 * np.log(b) / (dt * (1.0 - b**2))))  # volatility per year
    return {
        "kappa": kappa,
        "mu": mu,
        "sigma": sigma,
        "ar1_a": float(a),
        "ar1_b": float(b),
        "resid_sd": resid_sd,
        "dt": float(dt),
        "n_obs": int(len(x1)),
        "half_life_years": float(np.log(2.0) / kappa),          # time for a gap from mu to halve
        "stationary_sd": float(sigma / np.sqrt(2.0 * kappa)),   # long-run (stationary) SD
    }


def calibrate_all(csv_path=P.PRICE_DAILY_CSV, since: str | None = P.POST_CRISIS_START) -> dict:
    """Fit the seasonal curve and an OU at each frequency. Return the dict written to
    config/price_calibrated.json.

    The CSV spans 2018-2026. `since` defaults to P.POST_CRISIS_START and trims to the
    post-crisis base window so the 2021-23 gas crisis can't dominate a 35-yr forward sim.
    Pass since=None to fit the full history for the robustness comparison."""
    df = (
        pd.read_csv(csv_path, parse_dates=["date"])
        .sort_values("date")
        .reset_index(drop=True)
    )
    df = df[df["price_gbp_per_mwh"] > 0].reset_index(drop=True)  # log needs P > 0
    if since is not None:
        # df is date-sorted, boolean-mask indexing on a datetime compare SIGBUSes in this
        # env, py3.14 and pandas3.0.4, so locate the cut positionally and iloc-slice instead.
        pos = int(np.searchsorted(df["date"].to_numpy(), np.datetime64(since), side="left"))
        df = df.iloc[pos:].reset_index(drop=True)

    seasonal_coef = fit_seasonal(df["date"], df["price_gbp_per_mwh"].to_numpy())

    per_freq = {}
    for freq, (spy, dt) in FREQUENCIES.items():
        tau, price = aggregate_prices(df, freq)
        X = deseasonalise(tau, price, seasonal_coef)
        params = fit_ou_ar1(X, dt)
        params["steps_per_year"] = spy
        params["X_last"] = float(X[-1])  # simulation anchor
        per_freq[freq] = params

    yr = df["date"].dt.year.to_numpy()
    annual_means = {
        int(y): float(df["price_gbp_per_mwh"].to_numpy()[yr == y].mean())
        for y in np.unique(yr)
    }

    return {
        "metadata": {
            "model": "single-factor Ornstein-Uhlenbeck on deseasonalised log-price",
            "method": "OLS AR(1) on deseasonalised log-price (exact MLE for OU)",
            "calibrated_on": str(csv_path.relative_to(P.PROJECT_ROOT)),
            "data_window": {
                "start": str(df["date"].min().date()),
                "end": str(df["date"].max().date()),
                "n_obs": int(len(df)),
            },
            "generated_by": "src/price_simulator.py:write_calibration_json",
            "calibration_since": since,
            "note": (
                f"The price CSV spans 2018-2026, but the base case is fit from {since} only. "
                "The 2021-23 gas crisis is a once-in-a-generation shock, deliberately excluded "
                "from the base so it can't dominate a 35-yr forward sim. It is kept in the data "
                "for a separate robustness calibration, call with since=None."
                if since is not None else
                "Fit on the full 2018-2026 history including the 2021-23 gas crisis, the "
                "robustness window, not the base case."
            ),
        },
        "seasonal": {
            "form": "intercept + annual + semiannual harmonics",
            "design": SEASONAL_LABELS,
            "tau_definition": "day_of_year / days_in_year",
            "coefficients": [float(c) for c in seasonal_coef],
        },
        "base_post_crisis": {
            "recommended_frequency": "monthly",
            "recommended_reason": (
                "Fitting to daily or weekly prices makes the model snap back to its average "
                "too quickly, which wrongly narrows the year-to-year range. Monthly prices "
                "give a realistic range that matches what has been seen historically."
            ),
            "daily": per_freq["daily"],
            "weekly": per_freq["weekly"],
            "monthly": per_freq["monthly"],
        },
        "simulation": {"start_date": P.SIM_START_DATE},
        "historical_reference": {
            "mean_price": float(df["price_gbp_per_mwh"].mean()),
            "min_price": float(df["price_gbp_per_mwh"].min()),
            "max_price": float(df["price_gbp_per_mwh"].max()),
            "annual_means": annual_means,
        },
    }


def write_calibration_json(path=P.PRICE_CALIBRATION_JSON, csv_path=P.PRICE_DAILY_CSV) -> dict:
    """Calibrate and write config/price_calibrated.json. Returns the calibration dict."""
    cal = calibrate_all(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(cal, fh, indent=2)
    return cal


def load_calibration(
    window: str = P.PRICE_CALIBRATION_WINDOW,
    frequency: str = P.PRICE_FREQUENCY,
    path=P.PRICE_CALIBRATION_JSON,
) -> dict:
    """Load one (window, frequency) calibration, merged with the shared seasonal curve.

    Regenerates the JSON on the fly if it is missing.
    """
    if not path.exists():
        write_calibration_json(path)
    with open(path) as fh:
        cal = json.load(fh)

    if window not in cal:
        raise KeyError(f"window {window!r} not in calibration, have {list(cal)}")
    if frequency not in cal[window]:
        raise KeyError(f"frequency {frequency!r} not under {window!r}")

    out = dict(cal[window][frequency])
    out["seasonal_coef"] = np.asarray(cal["seasonal"]["coefficients"], dtype=float)
    out["start_date"] = cal["simulation"]["start_date"]
    out["window"] = window
    out["frequency"] = frequency
    return out


# Simulation
@dataclass
class PricePaths:
    """Simulated annual-average price paths in £/MWh, with provenance for downstream use."""

    annual_prices: np.ndarray
    calendar_year: np.ndarray
    frequency: str
    window: str
    ou_params: dict
    sample_paths: np.ndarray = field(default=None)

    def percentiles(self, qs=(10, 50, 90)) -> dict:
        return {q: np.percentile(self.annual_prices, q, axis=0) for q in qs}


def simulate_price_paths(
    n_paths: int = P.N_PATHS,
    horizon: int = P.OPERATING_LIFE_YEARS,
    frequency: str = P.PRICE_FREQUENCY,
    window: str = P.PRICE_CALIBRATION_WINDOW,
    antithetic: bool = P.ANTITHETIC,
    seed: int = P.RANDOM_SEED,
    n_sample_paths: int = 150,
) -> PricePaths:
    """Simulate N annual-average price paths and return them in £/MWh.

    Each path steps forward with the exact OU transition, then we add the season back and undo the
    log to land in pounds. Antithetic variates run every set of random draws alongside its mirror
    image, so a lucky run in one path is offset by its opposite and the average settles down with
    fewer paths."""
    cal = load_calibration(window, frequency)
    kappa, mu, sigma = cal["kappa"], cal["mu"], cal["sigma"]
    dt = cal["dt"]
    spy = cal["steps_per_year"]
    x0 = cal["X_last"]
    seasonal_coef = cal["seasonal_coef"]

    if antithetic and n_paths % 2:
        n_paths += 1  # need an even count to mirror

    # Exact one-step OU update. ek is how much of the gap from mu survives one step, sd_step is the
    # exact noise SD for a step of length dt. Both come straight from the OU solution, so stepping
    # monthly carries no discretisation error, unlike a naive Euler step.
    ek = np.exp(-kappa * dt)
    sd_step = sigma * np.sqrt((1.0 - np.exp(-2.0 * kappa * dt)) / (2.0 * kappa))

    # precompute the seasonal value at every step
    start = pd.Timestamp(cal["start_date"])
    start_off = float(fractional_year(pd.Series([start]))[0])
    total_steps = horizon * spy
    step_i = np.arange(total_steps)
    tau_steps = (start_off + (step_i + 1) * dt) % 1.0
    s_steps = seasonal_design(tau_steps) @ seasonal_coef

    rng = np.random.default_rng(seed)
    half = n_paths // 2

    x = np.full(n_paths, x0, dtype=float)
    annual = np.empty((n_paths, horizon), dtype=float)

    step = 0
    for yr in range(horizon):
        acc = np.zeros(n_paths)
        for _ in range(spy):
            if antithetic:
                z_half = rng.standard_normal(half)
                z = np.concatenate([z_half, -z_half])  # each draw paired with its negative
            else:
                z = rng.standard_normal(n_paths)
            x = mu + (x - mu) * ek + sd_step * z  # one OU step, revert toward mu then add the noise
            acc += np.exp(s_steps[step] + x)      # add the season back and undo the log, into £/MWh
            step += 1
        annual[:, yr] = acc / spy                 # average the within-year steps into one price

    # x = midpoint of each annual-average window, anchored at the true start fraction
    calendar_year = float(start.year) + start_off + 0.5 + np.arange(horizon)
    sample = annual[:n_sample_paths].copy()
    return PricePaths(
        annual_prices=annual,
        calendar_year=calendar_year,
        frequency=frequency,
        window=window,
        ou_params={k: cal[k] for k in ("kappa", "mu", "sigma", "half_life_years", "n_obs")},
        sample_paths=sample,
    )


# Chart 1, fan chart
def _load_history(csv_path=P.PRICE_DAILY_CSV) -> pd.DataFrame:
    df = pd.read_csv(csv_path, parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    df["year_frac"] = df["date"].dt.year + fractional_year(df["date"])
    return df


def _history_aggregates(history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monthly- and annual-average historical series with calendar-x positions."""
    yf = history["year_frac"].to_numpy()
    price = history["price_gbp_per_mwh"].to_numpy()

    ym = (history["date"].dt.year * 12 + history["date"].dt.month).to_numpy()
    _, inv = np.unique(ym, return_inverse=True)
    cnt = np.bincount(inv)
    monthly = pd.DataFrame({
        "year_frac": np.bincount(inv, weights=yf) / cnt,
        "price": np.bincount(inv, weights=price) / cnt,
    })

    yr = history["date"].dt.year.to_numpy()
    uy, inv_y = np.unique(yr, return_inverse=True)
    cnt_y = np.bincount(inv_y)
    annual = pd.DataFrame({
        "year": uy,
        "year_frac": np.bincount(inv_y, weights=yf) / cnt_y,
        "price": np.bincount(inv_y, weights=price) / cnt_y,
    })
    return monthly, annual


def plot_fan_chart(
    paths: PricePaths,
    history: pd.DataFrame,
    save_path=None,
    title: str | None = None,
) -> "tuple[plt.Figure, plt.Axes]":
    """Chart 1, the simulated price fan. Shows sample paths, the P10 to P90 band with the
    P50 median, and a historical overlay.

    The forecast is an annual average, so it is compared against historical monthly and
    annual averages. Raw daily prices are shown faintly for context."""
    if save_path is None:
        save_path = P.CHARTS_DIR / "chart1_price_fan.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    x = paths.calendar_year
    pct = paths.percentiles((10, 50, 90))
    forecast_start = float(history["year_frac"].iloc[-1])
    monthly, annual = _history_aggregates(history)

    fig, ax = plt.subplots(figsize=(12, 6.5))

    # faint daily history for context
    ax.plot(history["year_frac"], history["price_gbp_per_mwh"],
            color="0.45", lw=0.5, alpha=0.35, zorder=2,
            label="Historical daily (context)")
    # monthly average, like-for-like with the model
    ax.plot(monthly["year_frac"], monthly["price"],
            color="#222222", lw=1.6, alpha=0.9, zorder=6,
            label="Historical monthly avg")
    # annual means
    ax.scatter(annual["year_frac"], annual["price"], color="#d62728", s=55,
               zorder=7, edgecolor="white", linewidth=0.8,
               label="Historical annual mean")

    # Sample simulated paths, light grey.
    for i in range(paths.sample_paths.shape[0]):
        ax.plot(x, paths.sample_paths[i], color="0.6", alpha=0.08, lw=0.6, zorder=3)

    # P10-P90 band and P50 median.
    ax.fill_between(x, pct[10], pct[90], color="#1f77b4", alpha=0.22,
                    label="Forecast P10-P90", zorder=4)
    ax.plot(x, pct[50], color="#1f77b4", lw=2.2, label="Forecast P50 (median)", zorder=5)
    ax.plot(x, pct[10], color="#1f77b4", lw=1.0, ls="--", alpha=0.8, zorder=5)
    ax.plot(x, pct[90], color="#1f77b4", lw=1.0, ls="--", alpha=0.8, zorder=5)

    # scale y to the averaged series, not the daily spikes
    daily_max = float(history["price_gbp_per_mwh"].max())
    y_top = max(float(monthly["price"].max()), float(pct[90].max())) * 1.35
    ax.set_ylim(0, y_top)
    if daily_max > y_top:
        ax.text(history["year_frac"].iloc[0] + 0.05, y_top * 0.97,
                f"(daily peaks to £{daily_max:.0f}, clipped)", fontsize=8,
                color="0.4", va="top")

    # Forecast start marker.
    ax.axvline(forecast_start, color="grey", ls=":", lw=1.2, zorder=4)
    ax.text(forecast_start + 0.25, y_top * 0.04, "forecast →", fontsize=9, color="grey")

    op = paths.ou_params
    box = (
        f"Single-factor OU · {paths.window} · {paths.frequency}\n"
        f"κ={op['kappa']:.2f}   μ={op['mu']:.3f}   σ={op['sigma']:.3f}\n"
        f"half-life={op['half_life_years'] * 365:.0f} days   "
        f"n_paths={paths.annual_prices.shape[0]:,}"
    )
    ax.text(0.015, 0.97, box, transform=ax.transAxes, fontsize=9, va="top", ha="left",
            family="monospace",
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="0.7", alpha=0.92))

    if title is None:
        title = "Chart 1: Simulated GB wholesale price fan (single-factor OU, monthly-calibrated)"
    ax.set_title(title, fontsize=12.5, pad=12)
    ax.set_xlabel("Year")
    ax.set_ylabel("Wholesale price (£/MWh, real 2024), annual average")
    ax.xaxis.set_major_locator(mticker.MultipleLocator(5))
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right", fontsize=8.5, framealpha=0.92, ncol=2)
    fig.tight_layout()
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig, ax


# Diagnostics and CLI
def realism_report(paths: PricePaths, cal_full: dict) -> str:
    pct = paths.percentiles((10, 50, 90))
    lines = [
        f"Annual-average price band, {paths.window}, {paths.frequency} "
        f"(n={paths.annual_prices.shape[0]:,})",
        f"  {'year':>5} {'P10':>7} {'P50':>7} {'P90':>7} {'P90/P10':>8}",
    ]
    for yr in (0, 4, 14, 29):
        p10, p50, p90 = pct[10][yr], pct[50][yr], pct[90][yr]
        lines.append(f"  {yr + 1:>5} {p10:>7.1f} {p50:>7.1f} {p90:>7.1f} {p90 / p10:>8.2f}")
    hist = cal_full["historical_reference"]
    am = ", ".join(f"{y}: £{v:.1f}" for y, v in hist["annual_means"].items())
    lines.append(f"  historical annual means -> {am}   (overall £{hist['mean_price']:.1f})")
    return "\n".join(lines)


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    frequency = P.PRICE_FREQUENCY
    n_paths = P.N_PATHS
    for arg in argv:
        if arg.startswith("--freq="):
            frequency = arg.split("=", 1)[1]
        elif arg.startswith("--n="):
            n_paths = int(arg.split("=", 1)[1])

    print("Calibrating and writing", P.PRICE_CALIBRATION_JSON.name, "...")
    cal_full = write_calibration_json()
    for f in FREQUENCIES:
        d = cal_full["base_post_crisis"][f]
        print(f"  {f:8s} kappa={d['kappa']:8.3f}  mu={d['mu']:7.4f}  "
              f"sigma={d['sigma']:7.4f}  half-life={d['half_life_years'] * 365:6.1f}d")

    print(f"\nSimulating {n_paths:,} paths at '{frequency}' frequency ...")
    paths = simulate_price_paths(n_paths=n_paths, frequency=frequency)
    print(realism_report(paths, cal_full))

    history = _load_history()
    out = P.CHARTS_DIR / "chart1_price_fan.png"
    plot_fan_chart(paths, history, save_path=out)
    print(f"\nSaved fan chart -> {out}")


if __name__ == "__main__":
    main()
