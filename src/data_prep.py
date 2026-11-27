"""
Build the calibration-ready daily price series from the raw Elexon Market Index download.

The raw feed carries two index providers, APXMIDP and N2EXMIDP. Over this period N2EX reports
zero price and volume for almost all half-hours, so it must be excluded. Averaging it in would
dilute the daily price toward half its true level. The Market Index Price is volume-weighted, so
we volume-weight the surviving APX half-hourly prices within each day.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import parameters as P


def build_daily_price(raw_path: Path = P.PRICE_RAW_CSV) -> pd.DataFrame:
    """Volume-weighted daily APX Market Index Price, dropping the zero-reporting N2EX feed."""
    if not raw_path.exists():
        raise FileNotFoundError(f"{raw_path} not found; run `make data` to download it")
    df = pd.read_csv(raw_path)

    # keep only APX rows with a real trade, drop the dead N2EX feed and any zero-price half-hours
    keep = (df["data_provider"] == "APXMIDP") & (df["price"] > 0) & (df["volume"] > 0)
    sub = df[keep]
    dates = sub["settlement_date"].to_numpy()          # 'YYYY-MM-DD' sorts chronologically
    price = sub["price"].to_numpy(dtype=float)
    vol = sub["volume"].to_numpy(dtype=float)

    # group the half-hours by day, inv maps each row to its day bucket
    days, inv = np.unique(dates, return_inverse=True)
    # volume-weighted mean per day, sum(price * volume) / sum(volume), so busy half-hours count more
    vw = np.bincount(inv, weights=price * vol) / np.bincount(inv, weights=vol)
    return pd.DataFrame({"date": days, "price_gbp_per_mwh": vw})


def write_daily_csv(out_path: Path = P.PRICE_DAILY_CSV, raw_path: Path = P.PRICE_RAW_CSV) -> pd.DataFrame:
    daily = build_daily_price(raw_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(out_path, index=False)
    return daily


def main() -> None:
    daily = write_daily_csv()
    d = daily["date"].to_numpy()
    p = daily["price_gbp_per_mwh"].to_numpy()
    yr = d.astype("U4")
    print(f"Wrote {len(daily):,} daily prices from {P.PRICE_RAW_CSV.name} -> {P.PRICE_DAILY_CSV.name}")
    print(f"  {d[0]} -> {d[-1]}   overall mean £{p.mean():.1f}/MWh")
    for y in np.unique(yr):
        print(f"  {y}: £{p[yr == y].mean():.1f}/MWh")


if __name__ == "__main__":
    main()
