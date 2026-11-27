"""
All model inputs in one place. Every number here is backed by a public source and used
somewhere in the model. Money is in real 2023/24 pounds throughout, so there is no inflation.

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
CF_ANNUAL_CSV = DATA_PROCESSED_DIR / "cf_annual.csv"
CF_BENCHMARKS_CSV = DATA_PROCESSED_DIR / "capacity_factor_benchmarks.csv"
COST_BENCHMARKS_CSV = DATA_PROCESSED_DIR / "cost_benchmarks.csv"
PRICE_CALIBRATION_JSON = CONFIG_DIR / "price_calibrated.json"

# --------------------------------------------------------------------------------------------
# The wind farm (Arup for DESNZ Offshore Wind LCOE 2024, unless noted)
# --------------------------------------------------------------------------------------------
CAPACITY_MW = 1000.0            # Phase 1: a 1 GW project, AR7-scale
PHASE2_CAPACITY_MW = 500.0      # the optional +0.5 GW Phase-2 expansion
OPERATING_LIFE_YEARS = 35       # years of operation after commissioning
CONSTRUCTION_YEARS = 5          # years of construction before first power; CAPEX is spread over these
HOURS_PER_YEAR = 8760.0
DEGRADATION_RATE = 0.005        # output falls ~0.5%/yr with age (industry placeholder)

# CAPEX and OPEX, real 2023/24 GBP, from Arup for DESNZ Table 3.
CAPEX_PER_KW = {"low": 3321.0, "central": 3976.0, "high": 4439.0}   # £/kW, total installed cost
OPEX_PER_MW_YEAR_K = {"low": 73.7, "central": 138.5, "high": 207.2}  # k£/MW/yr, total running cost
# OPEX split out so the sensitivity can flex the big, location-specific grid charge (TNUoS)
# separately from the rest. The three add up to OPEX_PER_MW_YEAR_K.
OPEX_OM_INSURANCE_K = {"low": 38.5, "central": 55.1, "high": 74.3}   # O&M + insurance, k£/MW/yr
OPEX_TNUOS_K = {"low": 35.3, "central": 83.4, "high": 132.9}        # grid connection charge, k£/MW/yr

DECOMMISSIONING_PER_MW = 300_000.0  # £/MW, paid in the final year (DNV / Crown Estate range)

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
# Net load factor for a modern farm (net of wake and availability losses), DESNZ/IRENA central.
CF_MEAN = 0.50
CF_RANGE = {"low": 0.46, "central": 0.50, "high": 0.56}   # DESNZ low / central / high
# Year-to-year variability. Measured from cf_annual.csv, a 20-year renewables.ninja series for one
# turbine in the Dogger Bank grid cell (MERRA-2 weather, 2000-2019); this fallback is used only if
# that file is missing.
CF_SD_FALLBACK = 0.045

# --------------------------------------------------------------------------------------------
# Revenue: the CfD contract then the merchant market
# --------------------------------------------------------------------------------------------
# Years 1-20 are paid a fixed Contract-for-Difference strike price; the remaining years sell at
# the wholesale market price. DESNZ CfD AR7 results, Jan 2026.
CFD_STRIKE = 90.91              # £/MWh (2024 basis)
CFD_TERM_YEARS = 20
CFD_ADMIN_CAP = 113.0           # £/MWh, the AR7 administrative strike cap (used as the high case)
CFD_STRIKE_RANGE = {"low": 68.82, "central": CFD_STRIKE, "high": CFD_ADMIN_CAP}

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
# shock that would otherwise dominate a 35-year forward simulation.
PRICE_HISTORY_START = "2024-01-01"
SIM_START_DATE = "2026-07-01"           # first simulated month (day after the last price observation)

# The long-term price level drifts on a slow random walk. Its volatility cannot be pinned down
# from only ~2.5 years of data, so it is a forward-looking assumption (Schwartz-Smith style,
# power-market literature ~5-15%/yr) and is always reported as a sensitivity. This is what makes
# the price fan keep widening with horizon, so that decades-out uncertainty is real.
PRICE_LT_VOL = 0.06                     # sigma of the long-run level, per year (log terms)
PRICE_LT_VOL_RANGE = {"low": 0.04, "central": 0.06, "high": 0.10}
PRICE_LT_DRIFT = 0.0                    # no deterministic real-terms price trend
