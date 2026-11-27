"""
All model inputs in one place. Every number here is backed by a public source and used
somewhere in the model. Money is in real 2024 pounds throughout, so there is no inflation;
figures published in another year's prices are restated with the consumer price index.

Where a source gives a range we keep the low / central / high figures; the central one is the
default and the low/high feed the sensitivity analysis. A few real-options inputs are not pinned
to a single source and are marked PLACEHOLDER; they are always reported as a sensitivity, never
as a headline result.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------------------------
# File locations (resolved relative to the repo root, so the working directory does not matter)
# --------------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CHARTS_DIR = PROJECT_ROOT / "outputs" / "charts"

PRICE_DAILY_CSV = DATA_PROCESSED_DIR / "gb_price_daily.csv"
CPI_CSV = DATA_PROCESSED_DIR / "cpi_index.csv"
CF_ANNUAL_CSV = DATA_PROCESSED_DIR / "cf_annual.csv"
CF_BENCHMARKS_CSV = DATA_PROCESSED_DIR / "capacity_factor_benchmarks.csv"
COST_BENCHMARKS_CSV = DATA_PROCESSED_DIR / "cost_benchmarks.csv"
PRICE_CALIBRATION_JSON = CONFIG_DIR / "price_calibrated.json"

# --------------------------------------------------------------------------------------------
# Price base: all money is in real pounds of PRICE_BASE_YEAR
# --------------------------------------------------------------------------------------------
# Figures published in another year's prices are restated with the ONS consumer price index (CPI,
# series D7BT, 2015 = 100, in cpi_index.csv). These are its published annual averages; data_prep
# restates the wholesale prices month by month against the base-year average.
PRICE_BASE_YEAR = 2024
CPI_ANNUAL_AVERAGE = {2012: 96.1, 2023: 130.5, 2024: 133.9}

# --------------------------------------------------------------------------------------------
# The wind farm (Arup for DESNZ Offshore Wind LCOE 2024, unless noted)
# --------------------------------------------------------------------------------------------
CAPACITY_MW = 1000.0            # Phase 1: a 1 GW project, AR7-scale
PHASE2_CAPACITY_MW = 500.0      # the optional +0.5 GW Phase-2 expansion
OPERATING_LIFE_YEARS = 35       # years of operation after commissioning
CONSTRUCTION_YEARS = 5          # years of construction before first power; CAPEX is spread over these
HOURS_PER_YEAR = 8760.0
DEGRADATION_RATE = 0.005        # output falls ~0.5%/yr with age (industry placeholder)

# CAPEX and OPEX from Arup for DESNZ Table 3, which publishes them in 2023 prices; the figures
# below are Arup's, restated in PRICE_BASE_YEAR prices by ARUP_TO_BASE_YEAR. Arup's report builds
# them up with the GDP deflator (up 3.8% from 2023 to 2024, against 2.6% for CPI); CPI keeps them
# in the same unit as the CfD and the wholesale prices.
ARUP_PRICE_YEAR = 2023
ARUP_TO_BASE_YEAR = CPI_ANNUAL_AVERAGE[PRICE_BASE_YEAR] / CPI_ANNUAL_AVERAGE[ARUP_PRICE_YEAR]


def _restate_arup(published: dict) -> dict:
    return {case: value * ARUP_TO_BASE_YEAR for case, value in published.items()}


CAPEX_PER_KW = _restate_arup({"low": 3321.0, "central": 3976.0, "high": 4439.0})   # £/kW, installed
OPEX_PER_MW_YEAR_K = _restate_arup({"low": 73.7, "central": 138.5, "high": 207.2})  # k£/MW/yr, total
# OPEX split out so the sensitivity can flex the big, location-specific grid charge (TNUoS)
# separately from the rest. The two add up to OPEX_PER_MW_YEAR_K.
OPEX_OM_INSURANCE_K = _restate_arup({"low": 38.5, "central": 55.1, "high": 74.3})  # O&M + insurance
OPEX_TNUOS_K = _restate_arup({"low": 35.3, "central": 83.4, "high": 132.9})        # grid charge

# £/MW, paid in the final year: a central gross figure within the DNV and Crown Estate ranges,
# whose price year is not stated, so it is used as it stands. Arup's survey average is lower,
# £86k/MW in 2023 prices, net of scrap sales.
DECOMMISSIONING_PER_MW = 300_000.0

# --------------------------------------------------------------------------------------------
# Money and tax
# --------------------------------------------------------------------------------------------
WACC = 0.062                                       # pre-tax real discount rate (DESNZ/Arup central)
WACC_RANGE = {"low": 0.05, "central": 0.062, "high": 0.09}
TAX_RATE = 0.25                                    # UK corporation tax main rate

# Capital allowances: the tax deduction the CAPEX earns. We use the UK 18% writing-down
# allowance (reducing balance) on the whole CAPEX, with a balancing allowance clearing whatever
# is left in the final year. This is the standard UK plant-and-machinery treatment, so it is the
# realistic base case. The total deduction always equals CAPEX; only its timing is front-loaded,
# which brings the tax shield forward and raises NPV versus spreading it straight-line.
WDA_RATE = 0.18

# --------------------------------------------------------------------------------------------
# Generation: capacity factor (how much of the nameplate the wind actually delivers)
# --------------------------------------------------------------------------------------------
# Net load factor for a modern farm (net of wake and availability losses), Arup for DESNZ Table 3,
# the same source as the costs and the LCOE benchmark.
CF_MEAN = 0.505
CF_RANGE = {"low": 0.460, "central": CF_MEAN, "high": 0.561}
# Year-to-year variability. Measured from cf_annual.csv, a 20-year renewables.ninja series for one
# turbine in the Dogger Bank grid cell (MERRA-2 weather, 2000-2019). If that file is missing, the
# fallback is the UK fleet's measured variability, about 4% of the mean (Potisomporn & Vogel 2022).
CF_SD_FALLBACK = 0.04 * CF_MEAN

# --------------------------------------------------------------------------------------------
# Revenue: the CfD contract then the merchant market
# --------------------------------------------------------------------------------------------
# Years 1-20 are paid a fixed Contract-for-Difference strike price; the remaining years sell at
# the wholesale market price. DESNZ CfD AR7 results, Jan 2026, in 2024 prices.
CFD_STRIKE = 90.91              # £/MWh, the AR7 fixed-offshore average across its regions
CFD_TERM_YEARS = 20
CFD_ADMIN_CAP = 113.0           # £/MWh, the AR7 administrative strike cap (the high case)
# The low case is the previous round's price: AR6 (Sep 2024) awarded new fixed offshore wind
# £58.87/MWh in 2012 prices, restated with CPI (DESNZ's own 2024-to-2012 factor, 0.7177, is the
# same ratio). AR6 contracts ran 15 years, not 20, and a longer contract would clear lower, so this
# is a cautious low end.
CFD_AR6_STRIKE = 58.87 * CPI_ANNUAL_AVERAGE[PRICE_BASE_YEAR] / CPI_ANNUAL_AVERAGE[2012]
CFD_STRIKE_RANGE = {"low": CFD_AR6_STRIKE, "central": CFD_STRIKE, "high": CFD_ADMIN_CAP}

# Capture factor: in merchant years, wind sells for less than the time-average price, because it
# generates when every other wind farm does and that depresses the price ("cannibalisation").
# Merchant revenue = capture_factor * market_price * generation. CfD years are unaffected.
MERCHANT_CAPTURE_FACTOR = 0.85
MERCHANT_CAPTURE_RANGE = {"low": 0.70, "central": 0.85, "high": 1.00}

# --------------------------------------------------------------------------------------------
# Real-options settings
# --------------------------------------------------------------------------------------------
DEFERRAL_MAX_YEARS = 4                  # how long Phase-1 commitment may be delayed
EXPAND_WINDOW_YEARS = (3, 8)            # Phase 2 may be built 3-8 years after Phase-1 commissioning
EXPAND_CAPEX_LEARNING = 0.075           # Phase 2 CAPEX is ~7.5% cheaper (build-out learning)

# Abandon = a mid-life sale of the operating asset to a lower-cost-of-capital buyer. Both inputs
# are PLACEHOLDERS, reported only as a sensitivity.
BUYER_WACC = 0.05                       # PLACEHOLDER: the buyer's lower discount rate
TRANSACTION_COST = 0.02                 # PLACEHOLDER: sale cost, as a fraction of asset value

# Longstaff-Schwartz regression: fit the "value of waiting" with a quadratic in the price.
LSM_BASIS_DEGREE = 2

# --------------------------------------------------------------------------------------------
# Monte-Carlo settings
# --------------------------------------------------------------------------------------------
N_PATHS = 50_000                # simulated futures for the base case
N_PATHS_FINAL = 100_000         # higher-quality final run
ANTITHETIC = True               # pair each random draw with its mirror image to steady the average
RANDOM_SEED = 42

# --------------------------------------------------------------------------------------------
# Price model (two-factor, calibrated in src/price_simulator.py -> config/price_calibrated.json)
# --------------------------------------------------------------------------------------------
# Raw half-hourly prices: Elexon Market Index Data (MID), free with no key, from
# https://data.elexon.co.uk/bmrs/api/v1/datasets/MID. src/download_prices.py fetches these
# settlement dates; Elexon has no market index prices for 35 of them, all in 2018 to 2021.
PRICE_DOWNLOAD_START = "2018-01-01"
PRICE_DOWNLOAD_END = "2026-06-30"
PRICE_RAW_CSV = DATA_RAW_DIR / f"elexon_market_index_{PRICE_DOWNLOAD_START}_{PRICE_DOWNLOAD_END}.csv"

# We fit the short-term (fast-reverting) part of the price to recent history, from this date on.
# Starting in 2024 deliberately excludes the 2021-23 gas-crisis spike, a once-in-a-generation
# shock that would otherwise dominate a 40-year forward simulation.
PRICE_HISTORY_START = "2024-01-01"
SIM_START_DATE = "2026-07-01"           # first simulated month (day after the last price observation)

# The long-term price level drifts on a slow random walk. Its volatility cannot be pinned down
# from only ~2.5 years of data, so it is a forward-looking assumption (Schwartz-Smith style,
# power-market literature ~5-15%/yr) and is always reported as a sensitivity. This is what makes
# the price fan keep widening with horizon, so that decades-out uncertainty is real.
PRICE_LT_VOL = 0.06                     # sigma of the long-run level, per year (log terms)
PRICE_LT_VOL_RANGE = {"low": 0.04, "central": 0.06, "high": 0.10}
PRICE_LT_DRIFT = 0.0                    # no deterministic real-terms price trend
