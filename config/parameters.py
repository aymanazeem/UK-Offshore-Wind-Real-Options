"""
All model inputs in one place, each used somewhere in the model. Money is in real 2024 pounds
throughout, so there is no inflation; figures published in another year's prices are restated
with the consumer price index.

Each number comes from the public source named beside it, unless it is marked as my assumption
or my choice, whose effects docs/decisions.md reports, or as a PLACEHOLDER, which has no source
and only feeds the illustrative sale option. Where a source gives a range we keep the low /
central / high figures; the central one is the default and the low/high feed the sensitivity
analysis.
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
DEGRADATION_RATE = 0.005        # my assumption, a rule of thumb: output falls ~0.5%/yr with age.
                                # It shapes output over the life; the average stays CF_MEAN.

# CAPEX and OPEX from Arup for DESNZ Table 3, which publishes them in 2023 prices; the figures
# below are Arup's, restated in PRICE_BASE_YEAR prices by ARUP_TO_BASE_YEAR. Arup's report builds
# them up with the GDP deflator (up 3.8% from 2023 to 2024, against 2.6% for CPI); CPI keeps them
# in the same unit as the CfD and the wholesale prices.
ARUP_PRICE_YEAR = 2023
ARUP_TO_BASE_YEAR = CPI_ANNUAL_AVERAGE[PRICE_BASE_YEAR] / CPI_ANNUAL_AVERAGE[ARUP_PRICE_YEAR]


def _restate_arup(published: dict) -> dict:
    return {case: value * ARUP_TO_BASE_YEAR for case, value in published.items()}


# Arup's total CAPEX (£3,321 / 3,976 / 4,439 per kW) also includes £802 / 937 / 1,030 of
# infrastructure: the offshore transmission link. The developer sells that to an offshore
# transmission owner (OFTO) and the farm pays for it through the TNUoS grid charge in OPEX, so Arup
# leaves it out of its LCOE. The model does the same, or transmission would be paid for twice.
_ARUP_PREDEVELOPMENT = {"low": 104.0, "central": 216.0, "high": 308.0}
_ARUP_CONSTRUCTION = {"low": 2415.0, "central": 2823.0, "high": 3101.0}
CAPEX_PER_KW = _restate_arup({case: _ARUP_PREDEVELOPMENT[case] + _ARUP_CONSTRUCTION[case]
                              for case in _ARUP_CONSTRUCTION})                      # £/kW
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
# Arup's hurdle rate, 6.2%, is pre-tax and real: Arup converted BloombergNEF's post-tax nominal cost
# of capital with 2% inflation and 25% tax, by the BEIS 2018 method, which grosses up for tax in
# nominal terms. A pre-tax rate belongs with cash flows before tax, so the base case values
# pre-tax cash flows, as Arup's LCOE does; taxing them as well would count tax twice. The
# after-tax view taxes the cash flows and discounts them at the rate that conversion started from.
WACC = 0.062
WACC_RANGE = {"low": 0.05, "central": WACC, "high": 0.09}   # my test range; Arup gives one rate
TAX_RATE = 0.25                                    # UK corporation tax main rate (after-tax view)
INFLATION = 0.02                                   # Arup's, for that conversion and the allowances
POST_TAX_WACC = ((1.0 + (1.0 - TAX_RATE) * ((1.0 + WACC) * (1.0 + INFLATION) - 1.0))
                 / (1.0 + INFLATION) - 1.0)

# Capital allowances in the after-tax view: the tax deduction the CAPEX earns, at the UK main-pool
# writing-down allowance of 18% of the remaining balance a year, with a balancing allowance
# clearing what is left in the final year. Whether an offshore wind farm's assets qualify for this
# pool or another is not checked here. Allowances are set on the CAPEX in the pounds of the year
# it is spent and are not indexed, so at INFLATION they add up to less than the CAPEX in real terms.
WDA_RATE = 0.18

# --------------------------------------------------------------------------------------------
# Generation: capacity factor (how much of the nameplate the wind actually delivers)
# --------------------------------------------------------------------------------------------
# Net load factor for a modern farm, Arup for DESNZ Table 3: a lifetime average net of all losses,
# wear with age included, from the same source as the costs and the LCOE benchmark.
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
# My assumption for the 2050s and 2060s, when the merchant years fall; not a sourced figure.
MERCHANT_CAPTURE_FACTOR = 0.85
MERCHANT_CAPTURE_RANGE = {"low": 0.70, "central": 0.85, "high": 1.00}

# --------------------------------------------------------------------------------------------
# Real-options settings
# --------------------------------------------------------------------------------------------
DEFERRAL_MAX_YEARS = 4                  # my choice: how long Phase-1 commitment may be delayed
EXPAND_WINDOW_YEARS = (3, 8)            # my choice: Phase 2 may be built 3-8 years after first power
# My assumption: Phase 2 CAPEX is 7.5% cheaper, for lessons learned on Phase 1. Arup's medium
# case (Table 5) has industry build costs flat to 2035 and 4.2% lower by 2040.
EXPAND_CAPEX_LEARNING = 0.075

# Abandon = a mid-life sale of the operating asset to a lower-cost-of-capital buyer. Both inputs
# are PLACEHOLDERS, reported only as a sensitivity.
BUYER_WACC = 0.05                       # PLACEHOLDER: the buyer's lower discount rate, pre-tax
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

# The long-term price level drifts on a slow random walk (Schwartz and Smith, 2000). Its
# volatility cannot be pinned down from only ~2.5 years of data, so it is my assumption, tested
# from 4% to 10%. This is what makes the price fan keep widening with horizon, so that
# decades-out uncertainty is real.
PRICE_LT_VOL = 0.06                     # sigma of the long-run level, per year (log terms)
PRICE_LT_VOL_RANGE = {"low": 0.04, "central": 0.06, "high": 0.10}
PRICE_LT_DRIFT = 0.0                    # my assumption: no trend in the real price
