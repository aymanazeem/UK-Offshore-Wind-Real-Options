"""
Models how much electricity the farm produces each year.

Output in a year = capacity x capacity_factor x hours x (age profile).

The capacity factor (the fraction of nameplate actually delivered) varies year to year with the
wind. It must sit between 0 and 1, so we model it with a Beta distribution, chosen to match two
numbers:
  - mean: the net load factor of a modern farm (config.CF_MEAN), a sourced average over the
    farm's whole life that already nets off every loss, wear with age included,
  - spread: the year-to-year variability, measured from a 20-year renewables.ninja series
    (data/processed/cf_annual.csv).

We draw one capacity factor per path per year, then apply the age profile: output falls ~0.5%/yr
as the turbines wear, scaled so that it averages 1 over the life. The profile only shapes output
over time; it must not lower the lifetime average again, or wear would be counted twice.

Generation is second-order for the options: year-to-year wind variability (~4% of the mean) is
far smaller than price uncertainty, so option value is overwhelmingly price-driven. Wind is
modelled as independent of price; the price side of cannibalisation is handled by the merchant
capture factor in the cash-flow model, not here.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from config import parameters as P
from src.price_simulator import fractional_year


def capacity_factor_moments(csv_path=P.CF_ANNUAL_CSV) -> tuple[float, float]:
    """Return (mean, sd) for the capacity factor.

    The mean is always the sourced net figure. The spread is the year-to-year standard deviation
    measured from the renewables.ninja annual series when available, else a config fallback. (We
    keep only that series' spread, not its mean: it is a single-cell figure gross of farm losses,
    so its level sits above every net benchmark.)"""
    if csv_path.exists():
        cf = pd.read_csv(csv_path)["annual_mean_cf"].to_numpy(dtype=float)
        return P.CF_MEAN, float(cf.std(ddof=1))
    return P.CF_MEAN, P.CF_SD_FALLBACK


def fit_beta(mean: float, sd: float) -> tuple[float, float]:
    """Beta(a, b) shape parameters matching a target mean and standard deviation (method of
    moments). A tighter spread gives a larger, more concentrated pair."""
    max_var = mean * (1.0 - mean)  # the largest variance possible for a [0,1] variable at this mean
    if sd ** 2 >= max_var:
        raise ValueError(f"sd {sd} too large for mean {mean}")
    concentration = max_var / sd ** 2 - 1.0
    return mean * concentration, (1.0 - mean) * concentration


def age_profile(life: int = P.OPERATING_LIFE_YEARS) -> np.ndarray:
    """Output in each operating year relative to the lifetime average: falls DEGRADATION_RATE a
    year and averages 1, so the lifetime-average capacity factor stays CF_MEAN."""
    profile = (1.0 - P.DEGRADATION_RATE) ** np.arange(life)
    return profile / profile.mean()


@dataclass
class GenerationPaths:
    """Simulated capacity factors and generation (MWh), shape (n_paths, horizon)."""
    capacity_factor: np.ndarray
    generation_mwh: np.ndarray
    calendar_year: np.ndarray
    alpha: float
    beta: float
    mean: float
    sd: float

    def percentiles(self, arr, qs=(10, 50, 90)) -> dict:
        return {q: np.percentile(arr, q, axis=0) for q in qs}


def simulate_generation(
    n_paths: int = P.N_PATHS,
    horizon: int = P.OPERATING_LIFE_YEARS,
    seed: int = P.RANDOM_SEED,
    antithetic: bool = P.ANTITHETIC,
    capacity_mw: float = P.CAPACITY_MW,
) -> GenerationPaths:
    """Draw a capacity factor for each path and year from the fitted Beta, then convert to MWh.
    `horizon` is the operating life: output wears around its average over these years."""
    mean, sd = capacity_factor_moments()
    alpha, beta = fit_beta(mean, sd)

    if antithetic and n_paths % 2:
        n_paths += 1
    rng = np.random.default_rng(seed)
    if antithetic:
        half = n_paths // 2
        u_half = rng.random((half, horizon))
        u = np.concatenate([u_half, 1.0 - u_half], axis=0)  # mirror: pairs a windy draw with a calm one
    else:
        u = rng.random((n_paths, horizon))
    cf = stats.beta.ppf(u, alpha, beta)  # turn uniforms into capacity factors via the fitted Beta

    age = np.arange(horizon)
    generation = capacity_mw * cf * P.HOURS_PER_YEAR * age_profile(horizon)

    # output starts once a farm committed today has finished its build
    start = pd.Timestamp(P.SIM_START_DATE)
    calendar_year = (start.year + float(fractional_year(pd.Series([start]))[0]) + 0.5
                     + P.CONSTRUCTION_YEARS + age)
    return GenerationPaths(cf, generation, calendar_year, alpha, beta, mean, sd)


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    n_paths = next((int(a.split("=")[1]) for a in argv if a.startswith("--n=")), P.N_PATHS)

    gp = simulate_generation(n_paths=n_paths)
    twh = gp.generation_mwh / 1e6
    print(f"Capacity factor: target mean={gp.mean:.3f} sd={gp.sd:.4f} -> "
          f"Beta({gp.alpha:.1f}, {gp.beta:.1f}); sampled mean={gp.capacity_factor.mean():.3f}")
    print(f"Generation (TWh): yr1 {twh[:, 0].mean():.2f} -> yr{twh.shape[1]} {twh[:, -1].mean():.2f}, "
          f"lifetime average {twh.mean():.2f} ({P.DEGRADATION_RATE:.1%}/yr wear, averaging out "
          f"at the {P.CF_MEAN:.3f} load factor)")


if __name__ == "__main__":
    main()
