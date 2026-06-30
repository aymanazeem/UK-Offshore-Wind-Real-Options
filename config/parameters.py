"""
All model input numbers live here in one place. Every other file reads them from here
rather than writing numbers inline, so there is one sourced place to check or change any
assumption.

Each value is backed by a public source and annotated with where it came from. The sources
are UK government offshore wind cost reports, the latest CfD auction results, and published
capacity factor data. Money is in real 2023/24 pounds. Where a source gives a range, we keep
the low, central and high figures and use the central one by default.

Two inputs for the flexibility options are not pinned to a single source. They are marked
PLACEHOLDER and reported as a sensitivity, not as a result.
"""

from __future__ import annotations

from pathlib import Path

# Paths (robust to the working directory)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
DATA_RAW_DIR = DATA_DIR / "raw"
DATA_PROCESSED_DIR = DATA_DIR / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
CHARTS_DIR = OUTPUTS_DIR / "charts"

PRICE_DAILY_CSV = DATA_PROCESSED_DIR / "gb_price_daily.csv"
CF_BENCHMARKS_CSV = DATA_PROCESSED_DIR / "capacity_factor_benchmarks.csv"
COST_BENCHMARKS_CSV = DATA_PROCESSED_DIR / "cost_benchmarks.csv"
CFD_STRIKE_CSV = DATA_PROCESSED_DIR / "cfd_strike_prices.csv"
PRICE_CALIBRATION_JSON = CONFIG_DIR / "price_calibrated.json"

# Project and physical configuration
CAPACITY_MW = 1000.0                # Phase 1, 1 GW, AR7-scale mid-point
PHASE2_CAPACITY_MW = 500.0          # Expand option, +0.5 GW
OPERATING_LIFE_YEARS = 35           # DESNZ, unanimous stakeholder response
CONSTRUCTION_PERIOD = {"low": 4, "central": 5, "high": 5}      # years. CAPEX spread over this
CONSTRUCTION_PERIOD_YEARS = CONSTRUCTION_PERIOD["central"]
PREDEVELOPMENT_PERIOD = {"low": 7, "central": 7, "high": 15}   # years
PREDEVELOPMENT_PERIOD_YEARS = PREDEVELOPMENT_PERIOD["central"]
HOURS_PER_YEAR = 8760.0
DEGRADATION_RATE = 0.005            # about 0.5% per year output decline, industry placeholder

# CAPEX and OPEX, real 2023/24 GBP. Arup for DESNZ Offshore Wind LCOE 2024, Table 3.
CAPEX_PER_KW = {"low": 3321.0, "central": 3976.0, "high": 4439.0}      # £/kW total
CAPEX_PER_KW_CENTRAL = CAPEX_PER_KW["central"]
CAPEX_COMPONENTS_PER_KW = {                                            # £/kW, central
    "predevelopment": {"low": 104.0, "central": 216.0, "high": 308.0},
    "construction":   {"low": 2415.0, "central": 2823.0, "high": 3101.0},
    "infrastructure": {"low": 802.0, "central": 937.0, "high": 1030.0},  # excludes OFTO, which sits in TNUoS
}

OPEX_PER_MW_YEAR_K = {"low": 73.7, "central": 138.5, "high": 207.2}    # k£/MW/yr total
OPEX_PER_MW_YEAR_K_CENTRAL = OPEX_PER_MW_YEAR_K["central"]
OPEX_COMPONENTS_PER_MW_YEAR_K = {                                      # k£/MW/yr, central
    "om":             {"low": 30.5, "central": 46.5, "high": 64.6},
    "insurance":      {"low": 8.0, "central": 8.6, "high": 9.7},
    "connection_uos": {"low": 35.3, "central": 83.4, "high": 132.9},   # TNUoS, location-specific
}

# Decommissioning treated as a terminal LIABILITY in the final year.
DECOMMISSIONING_PER_MW = 300_000.0  # £/MW central. DNV €200-600k/MW, Crown Estate about £426k/MW gross

# Financial parameters
WACC = 0.062                        # pre-tax real, DESNZ and Arup central hurdle rate
WACC_SENSITIVITY = {"low": 0.05, "central": 0.062, "high": 0.09}
TAX_RATE = 0.25                     # UK corporation main rate, simplified
INFLATION_CPI = 0.02                # used only to index the CfD strike. Model is real terms

# Depreciation for the tax shield. Base case is straight-line over the operating life. The
# realism refinements add front-loaded UK capital allowances. Switching method changes only
# the timing of the shield across operating years, never the total, which always equals CAPEX.
DEPRECIATION_METHOD = "straight_line"   # {"straight_line", "wda_18", "full_expensing"}
WDA_RATE = 0.18                         # UK main-rate writing-down allowance, reducing balance

# Generation and capacity factor, from capacity_factor_benchmarks.csv
CF_MEAN = 0.50                      # modern AR7-era farm, DESNZ net LF central 0.505
CF_SD = 0.045                       # interannual SD, about 9% of mean, conservative vs measured 4-5.5%
CF_RANGE = {"low": 0.46, "central": 0.50, "high": 0.56}   # DESNZ low and high net load factor
CF_PRICE_CORRELATION = -0.15        # mild negative, cannibalisation. Sensitivity 0 and -0.3
CF_PRICE_CORRELATION_SENSITIVITY = {"low": -0.30, "central": -0.15, "high": 0.0}

# Revenue and CfD, from cfd_strike_prices.csv, DESNZ AR7 Results Jan 2026
CFD_STRIKE = 90.91                  # £/MWh, 2024 price basis, fixed-bottom offshore, AR7
CFD_PRICE_BASIS_YEAR = 2024
CFD_TERM_YEARS = 20                 # contract extended from 15 to 20 yr
CFD_ADMIN_STRIKE_CAP = 113.0        # £/MWh, AR7 fixed-bottom administrative cap
# high is the sourced AR7 admin cap. low is a symmetric ±£22 band for sensitivity only, not a clearing price
CFD_STRIKE_SENSITIVITY = {"low": 68.82, "central": 90.91, "high": 113.0}
# Merchant tail is the remaining life after the CfD term
MERCHANT_TAIL_YEARS = OPERATING_LIFE_YEARS - CFD_TERM_YEARS   # 15 years

# Real-options parameters
DEFERRAL_MAX_YEARS = 4              # bounded by CfD delivery window and consents

EXPAND_DECISION_WINDOW_YEARS = (3, 8)   # years after Phase-1 COD
EXPAND_CAPEX_LEARNING_RATE = 0.075      # 5-10% lower £/kW for Phase 2, from Arup and IRENA learning rates

# Abandon is a mid-life divestment, selling the operating asset. These two are PLACEHOLDERS,
# not pinned to a single source. Treat as unsourced and report them as a sensitivity.
DIVESTMENT_BUYER_WACC = 0.05            # PLACEHOLDER, buyer's lower cost of capital, below our WACC
DIVESTMENT_TRANSACTION_COST = 0.02      # PLACEHOLDER, fraction of enterprise value

# Longstaff-Schwartz regression settings
LSM_BASIS = "monomial"             # base, {1, X, X^2}
LSM_BASIS_DEGREE = 2               # robustness 3, and first-3 Laguerre
LSM_ITM_ONLY = True                # regress only on in-the-money paths
LSM_STATE_VARS = ("price",)        # primary state variable, price dominates

# Monte-Carlo simulation settings
N_PATHS = 50_000                   # base case
N_PATHS_FINAL = 100_000            # final production run
ANTITHETIC = True                  # antithetic-variate variance reduction
RANDOM_SEED = 42                   # our choice, fixed for reproducibility, PCG64

# Price process and simulation linkage. See config/price_calibrated.json
PRICE_CALIBRATION_WINDOW = "base_post_crisis"   # the base case window
# Data file spans 2018-2026 and includes the 2021-23 gas crisis. The base case is calibrated
# from POST_CRISIS_START on, so a once-in-a-generation shock cannot dominate a 35-yr forward sim.
POST_CRISIS_START = "2024-01-01"
# OU calibration and simulation frequency. "monthly" is the base case. Daily and weekly
# over-amplify fast reversion and collapse the annual band. See the price_simulator docstring.
PRICE_FREQUENCY = "monthly"
SIM_START_DATE = "2026-07-01"      # day after the last historical observation. The fan starts here
