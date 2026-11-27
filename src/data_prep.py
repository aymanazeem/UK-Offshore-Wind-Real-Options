"""
Build the calibration-ready daily price series from the raw Elexon Market Index download.

The raw feed carries two index providers, APXMIDP and N2EXMIDP. Over this period N2EX reports
zero price and volume for almost all half-hours, so it must be excluded. Averaging it in would
dilute the daily price toward half its true level. The Market Index Price is volume-weighted, so
we volume-weight the surviving APX half-hourly prices within each day. Negative prices are real
trades, common in windy hours of low demand, so they stay in.

Elexon reports prices in the pounds of the day. The model works in real pounds of PRICE_BASE_YEAR,
so each day is also restated with the ONS consumer price index for its month.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import parameters as P


def to_base_year_pounds(nominal: np.ndarray, months: np.ndarray, cpi_path: Path = P.CPI_CSV) -> np.ndarray:
    """Restate prices in PRICE_BASE_YEAR pounds: scale each by base-year CPI / its month's CPI.
    `months` holds 'YYYY-MM' strings."""
    cpi = pd.read_csv(cpi_path, dtype={"month": str}).set_index("month")["cpi_index"]
    missing = sorted(set(months) - set(cpi.index))
    if missing:
        raise ValueError(f"{cpi_path.name} has no CPI for {missing[0]} to {missing[-1]}; "
                         "run `make data` to update it")
    return nominal * P.CPI_ANNUAL_AVERAGE[P.PRICE_BASE_YEAR] / cpi.loc[months].to_numpy()


def build_daily_price(raw_path: Path = P.PRICE_RAW_CSV, cpi_path: Path = P.CPI_CSV) -> pd.DataFrame:
    """Volume-weighted daily APX Market Index Price, dropping the zero-reporting N2EX feed, in
    nominal pounds and in real PRICE_BASE_YEAR pounds."""
    if not raw_path.exists():
        raise FileNotFoundError(f"{raw_path} not found; run `make data` to download it")
    df = pd.read_csv(raw_path)

    # keep APX half-hours that traded, negative prices included, and drop the dead N2EX feed
    keep = (df["data_provider"] == "APXMIDP") & (df["volume"] > 0)
    sub = df[keep]
    dates = sub["settlement_date"].to_numpy()          # 'YYYY-MM-DD' sorts chronologically
    price = sub["price"].to_numpy(dtype=float)
    vol = sub["volume"].to_numpy(dtype=float)

    # group the half-hours by day, inv maps each row to its day bucket
    days, inv = np.unique(dates, return_inverse=True)
    # volume-weighted mean per day, sum(price * volume) / sum(volume), so busy half-hours count more
    nominal = np.bincount(inv, weights=price * vol) / np.bincount(inv, weights=vol)
    real = to_base_year_pounds(nominal, days.astype("U7"), cpi_path)
    return pd.DataFrame({"date": days, "price_nominal_gbp_per_mwh": nominal,
                         "price_real_gbp_per_mwh": real})


def write_daily_csv(out_path: Path = P.PRICE_DAILY_CSV, raw_path: Path = P.PRICE_RAW_CSV) -> pd.DataFrame:
    daily = build_daily_price(raw_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(out_path, index=False)
    return daily


def main() -> None:
    daily = write_daily_csv()
    d = daily["date"].to_numpy()
    nominal = daily["price_nominal_gbp_per_mwh"].to_numpy()
    real = daily["price_real_gbp_per_mwh"].to_numpy()
    yr = d.astype("U4")
    print(f"Wrote {len(daily):,} daily prices from {P.PRICE_RAW_CSV.name} -> {P.PRICE_DAILY_CSV.name}")
    print(f"  {d[0]} -> {d[-1]}   mean £{nominal.mean():.1f}/MWh nominal, "
          f"£{real.mean():.1f}/MWh in {P.PRICE_BASE_YEAR} pounds")
    for y in np.unique(yr):
        print(f"  {y}: £{nominal[yr == y].mean():.1f} nominal, £{real[yr == y].mean():.1f} real")


if __name__ == "__main__":
    main()
