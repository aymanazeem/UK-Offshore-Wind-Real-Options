"""
Models annual electricity output, which rises and falls year to year with the wind.

Capacity factor is bounded in [0, 1], so we fit a Beta distribution by method of moments to a
target mean and interannual SD, then draw one CF per year per path. Output applies a small
linear degradation with age. The interannual SD comes from a renewables.ninja annual series in
data/processed/cf_annual.csv when present, while the net mean stays the sourced figure because
the ninja single-cell mean is gross of farm wake and availability losses. P.CF_NINJA_MODE sets
this, and with no file present both moments fall back to the sourced literature config.

Draws go through a Gaussian copula, normal to uniform to Beta inverse-CDF, so antithetic
variates work and the mild negative CF-vs-price correlation can be switched on by tilting the
driving normals against price. Pass price_annual and cf_price_corr=rho to simulate_generation
for that. The default is independent. It is the base case, and the correlation moves NPV by
less than £1m.

Generation is second-order here. Interannual CF variability, about 4 to 9% of the mean, is far
smaller than price variability, so option value is overwhelmingly price-driven.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy import stats  # noqa: E402

from config import parameters as P  # noqa: E402
from src.price_simulator import fractional_year  # noqa: E402

CF_ANNUAL_CSV = P.DATA_PROCESSED_DIR / "cf_annual.csv"


def fit_beta_moments(mean: float, sd: float) -> tuple[float, float]:
    """Pick the Beta(alpha, beta) whose mean and SD match the targets, by method of moments.
    A Beta is used because capacity factor is trapped between 0 and 1, and its two shape
    parameters follow in closed form from the first two moments."""
    var = sd**2
    m1m = mean * (1.0 - mean)  # the widest variance any 0-to-1 distribution with this mean allows
    if var >= m1m:
        raise ValueError(f"variance {var:.4g} too large for mean {mean}, need < {m1m:.4g}")
    k = m1m / var - 1.0  # concentration, larger k gives a tighter Beta
    return mean * k, (1.0 - mean) * k


def load_cf_moments(csv_path=CF_ANNUAL_CSV, mode: str | None = None) -> dict:
    """CF mean and sd for the Beta fit.

    With cf_annual.csv present, P.CF_NINJA_MODE decides how much of the ninja series to use.
      sd_only  keep the sourced net mean CF_MEAN, adopt the ninja interannual SD. Default.
      both     adopt the ninja mean and SD.
      off      ignore the file, use the sourced config moments.
    The ninja raw mean, about 0.589, is a single-cell figure gross of wake and availability
    losses, so sd_only is the honest upgrade, it takes the measured year to year variability
    without the gross mean. With no file present both moments fall back to the sourced config."""
    mode = P.CF_NINJA_MODE if mode is None else mode
    if mode not in {"sd_only", "both", "off"}:
        raise ValueError(f"CF_NINJA_MODE must be sd_only, both or off, got {mode!r}")
    if csv_path.exists() and mode != "off":
        ann = pd.read_csv(csv_path)
        col = "annual_mean_cf" if "annual_mean_cf" in ann.columns else ann.columns[-1]
        cf = ann[col].to_numpy(dtype=float)
        ninja_mean, ninja_sd, n = float(cf.mean()), float(cf.std(ddof=1)), int(len(cf))
        if mode == "both":
            return {
                "mean": ninja_mean, "sd": ninja_sd, "n_years": n,
                "source": f"renewables.ninja annual series ({csv_path.name}, {n} yrs), mean and SD",
            }
        return {
            "mean": P.CF_MEAN, "sd": ninja_sd, "n_years": n,
            "source": (f"net mean {P.CF_MEAN:.2f} sourced (DESNZ, Potisomporn, DNV), interannual "
                       f"SD {ninja_sd:.4f} from renewables.ninja {n} yr. Ninja gross mean "
                       f"{ninja_mean:.3f} not used, single-cell before wake and availability"),
        }
    return {
        "mean": P.CF_MEAN,
        "sd": P.CF_SD,
        "n_years": None,
        "source": "sourced literature moments (Potisomporn & Vogel, DNV, DESNZ)",
    }


@dataclass
class GenerationPaths:
    """Simulated annual capacity factor and generation (MWh), with the fitted Beta."""

    capacity_factor: np.ndarray  # (n_paths, horizon)
    generation_mwh: np.ndarray   # (n_paths, horizon)
    calendar_year: np.ndarray
    alpha: float
    beta: float
    moments: dict

    @staticmethod
    def percentiles(arr: np.ndarray, qs=(10, 50, 90)) -> dict:
        return {q: np.percentile(arr, q, axis=0) for q in qs}


def price_normal_scores(annual_price: np.ndarray) -> np.ndarray:
    """Per-year standard-normal scores of the annual price, the van der Waerden transform, one
    column at a time. Rank across paths -> uniform -> Phi^-1. The driver for the CF-price Gaussian
    copula."""
    n = annual_price.shape[0]
    ranks0 = np.argsort(np.argsort(annual_price, axis=0), axis=0)  # 0-based rank per column
    u = (ranks0 + 0.5) / n  # ranks to evenly spread uniforms, the +0.5 keeps them off 0 and 1
    return stats.norm.ppf(u)  # uniforms to standard-normal scores through Phi^-1


def simulate_capacity_factors(
    n_paths: int, horizon: int, alpha: float, beta: float, seed: int, antithetic: bool,
    price_normal: np.ndarray | None = None, cf_price_corr: float = 0.0,
) -> np.ndarray:
    """Draw one CF per year per path through a Gaussian copula, a standard-normal draw pushed
    through Phi to a uniform in (0, 1), then through the Beta inverse-CDF back to a capacity factor.

    Antithetic mirroring (z, -z) maps to (u, 1-u), giving paired high and low wind years.
    With price_normal, the per-year normal scores of price, and cf_price_corr=rho, the CF normal
    is tilted z' = rho*price_normal + sqrt(1-rho^2)*z to induce the cannibalisation correlation,
    so rho<0 makes high-price years draw lower CF. z' is still standard normal, so the Beta
    marginal is preserved exactly. Only the dependence on price changes. The default, no
    price_normal, is the independent draw, bit-identical to before."""
    if antithetic and n_paths % 2:
        n_paths += 1
    rng = np.random.default_rng(seed)
    if antithetic:
        half = n_paths // 2
        z_half = rng.standard_normal((half, horizon))
        z = np.concatenate([z_half, -z_half], axis=0)
    else:
        z = rng.standard_normal((n_paths, horizon))
    if price_normal is not None and cf_price_corr:
        w = price_normal[:n_paths]
        # tilt the CF driver toward price by rho, this stays standard normal so the Beta is unchanged
        z = cf_price_corr * w + np.sqrt(1.0 - cf_price_corr**2) * z
    u = stats.norm.cdf(z)  # normal scores to uniforms in (0, 1)
    return stats.beta.ppf(u, alpha, beta)  # uniforms to capacity factors through the fitted Beta


def annual_generation_mwh(
    cf: np.ndarray,
    capacity_mw: float = P.CAPACITY_MW,
    degradation: float = P.DEGRADATION_RATE,
    hours: float = P.HOURS_PER_YEAR,
) -> np.ndarray:
    """Generation = capacity * CF * hours * (1 - degradation*age). Age is 0-based, so the first year is full output."""
    age = np.arange(cf.shape[1])
    return capacity_mw * cf * hours * (1.0 - degradation * age)


def simulate_generation(
    n_paths: int = P.N_PATHS,
    horizon: int = P.OPERATING_LIFE_YEARS,
    seed: int = P.RANDOM_SEED,
    antithetic: bool = P.ANTITHETIC,
    capacity_mw: float = P.CAPACITY_MW,
    price_annual: np.ndarray | None = None,
    cf_price_corr: float = 0.0,
) -> GenerationPaths:
    """Pass price_annual, shaped (n_paths, horizon), with cf_price_corr=rho to correlate CF with
    price. The default is the independent draw."""
    mom = load_cf_moments()
    alpha, beta = fit_beta_moments(mom["mean"], mom["sd"])
    price_normal = price_normal_scores(price_annual) if (price_annual is not None and cf_price_corr) else None
    cf = simulate_capacity_factors(n_paths, horizon, alpha, beta, seed, antithetic,
                                   price_normal=price_normal, cf_price_corr=cf_price_corr)
    gen = annual_generation_mwh(cf, capacity_mw)
    # mid-point calendar year of each operating year, same convention as the price sim
    start = pd.Timestamp(P.SIM_START_DATE)
    start_off = float(fractional_year(pd.Series([start]))[0])
    calendar_year = start.year + start_off + 0.5 + np.arange(horizon)
    return GenerationPaths(cf, gen, calendar_year, alpha, beta, mom)


def _benchmark_cfs(csv_path=P.CF_BENCHMARKS_CSV) -> dict:
    """A few literature CF reference points to overlay on the distribution chart."""
    want = {
        "mean_cf_potisomporn": "Potisomporn 0.459",
        "irena_europe_cf": "IRENA EU 0.48",
        "desnz_net_lf_central": "DESNZ 0.505",
    }
    df = pd.read_csv(csv_path)
    out = {}
    for _, row in df.iterrows():
        if row["metric"] in want:
            out[want[row["metric"]]] = float(row["value"])
    return out


def plot_generation_chart(gp: GenerationPaths, save_path=None, title: str | None = None):
    """Verification chart. Left panel shows the simulated CF distribution against the fitted Beta
    and literature benchmarks. Right panel shows the annual generation P10-P90 band over the
    project life."""
    if save_path is None:
        save_path = P.CHARTS_DIR / "chart_generation.png"
    save_path.parent.mkdir(parents=True, exist_ok=True)

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13, 5.2))

    # Left panel, CF distribution in year 1 with the fitted Beta pdf and benchmarks
    cf0 = gp.capacity_factor[:, 0]
    axL.hist(cf0, bins=60, density=True, color="#1f77b4", alpha=0.35, label="Simulated CF (yr 1)")
    grid = np.linspace(max(0.0, cf0.min() - 0.05), min(1.0, cf0.max() + 0.05), 400)
    axL.plot(grid, stats.beta.pdf(grid, gp.alpha, gp.beta), color="#1f77b4", lw=2,
             label=f"Beta({gp.alpha:.1f}, {gp.beta:.1f})")
    for lab, val in _benchmark_cfs().items():
        axL.axvline(val, color="0.4", ls="--", lw=1)
        axL.text(val, axL.get_ylim()[1] * 0.96, lab, rotation=90, fontsize=7.5,
                 va="top", ha="right", color="0.35")
    m = gp.moments
    axL.axvline(m["mean"], color="#d62728", lw=2, label=f"mean {m['mean']:.3f}")
    axL.set_xlabel("Annual capacity factor")
    axL.set_ylabel("Density")
    axL.set_title("Capacity-factor distribution")
    axL.legend(loc="upper left", fontsize=8)
    axL.grid(True, alpha=0.25)

    # Right panel, annual generation band in TWh over the life
    gen_twh = gp.generation_mwh / 1e6
    pct = GenerationPaths.percentiles(gen_twh)
    x = gp.calendar_year
    axR.fill_between(x, pct[10], pct[90], color="#2ca02c", alpha=0.22, label="P10-P90")
    axR.plot(x, pct[50], color="#2ca02c", lw=2, label="P50 (median)")
    axR.set_xlabel("Year")
    axR.set_ylabel("Annual generation (TWh)")
    axR.set_title(f"Generation over life: {gp.capacity_factor.shape[1]} yr, "
                  f"{P.CAPACITY_MW:.0f} MW, {P.DEGRADATION_RATE:.1%}/yr degradation")
    axR.set_ylim(0, float(pct[90].max()) * 1.1)
    axR.legend(loc="lower left", fontsize=8)
    axR.grid(True, alpha=0.25)

    if title is None:
        title = f"Capacity factor and generation: Beta from {m['source']}"
    fig.suptitle(title, fontsize=12.5)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig, (axL, axR)


def realism_report(gp: GenerationPaths) -> str:
    cf = gp.capacity_factor
    gen_twh = gp.generation_mwh / 1e6
    m = gp.moments
    lines = [
        f"CF moments source: {m['source']}",
        f"  target  mean={m['mean']:.4f}  sd={m['sd']:.4f}"
        + (f"  (n={m['n_years']} yrs)" if m["n_years"] else ""),
        f"  fitted  Beta(alpha={gp.alpha:.2f}, beta={gp.beta:.2f})",
        f"  sampled mean={cf.mean():.4f}  sd={cf.std():.4f}  "
        f"min={cf.min():.3f}  max={cf.max():.3f}",
        f"Annual generation (TWh): {'year':>4} {'P10':>6} {'P50':>6} {'P90':>6}",
    ]
    pct = GenerationPaths.percentiles(gen_twh)
    for yr in (0, 4, 14, 34):
        lines.append(f"  {'':22}{yr + 1:>4} {pct[10][yr]:>6.2f} {pct[50][yr]:>6.2f} {pct[90][yr]:>6.2f}")
    mean_gen = gen_twh.mean(axis=0)
    lines.append(f"  mean annual generation: yr1 {mean_gen[0]:.2f} TWh -> yr{cf.shape[1]} {mean_gen[-1]:.2f} TWh")
    return "\n".join(lines)


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    n_paths = P.N_PATHS
    for arg in argv:
        if arg.startswith("--n="):
            n_paths = int(arg.split("=", 1)[1])

    print(f"Simulating {n_paths:,} generation paths over {P.OPERATING_LIFE_YEARS} years ...")
    gp = simulate_generation(n_paths=n_paths)
    print(realism_report(gp))

    out = P.CHARTS_DIR / "chart_generation.png"
    plot_generation_chart(gp, save_path=out)
    print(f"\nSaved generation chart -> {out}")


if __name__ == "__main__":
    main()
