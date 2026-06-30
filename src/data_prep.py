"""
Build the calibration-ready daily price series from the raw Elexon Market Index download.

The raw feed carries two index providers, APXMIDP and N2EXMIDP. Over this period N2EX reports
zero price and volume for almost all half-hours, so it must be excluded. Averaging it in would
dilute the daily price toward half its true level. The Market Index Price is volume-weighted, so
we volume-weight the surviving APX half-hourly prices within each day.

This uses numpy aggregation only. pandas .resample() and .groupby().apply() segfault in this env.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config import parameters as P


def _find_raw(raw_dir: Path = P.DATA_RAW_DIR) -> Path:
    """Pick the widest download, the earliest start date, so dropping in a shorter recent pull
    cannot silently shorten the calibration series. Filename is
    elexon_market_index_{start}_{end}.csv and the YYYY-MM-DD start sorts chronologically."""
    matches = list(raw_dir.glob("elexon_market_index_*.csv"))
    if not matches:
        raise FileNotFoundError(f"no elexon_market_index_*.csv found in {raw_dir}")
    return min(matches, key=lambda p: p.stem.split("_")[-2])


def build_daily_price(raw_path: Path | None = None) -> pd.DataFrame:
    """Volume-weighted daily APX Market Index Price, dropping the zero-reporting N2EX feed."""
    raw_path = _find_raw() if raw_path is None else raw_path
    df = pd.read_csv(raw_path)

    keep = (df["data_provider"] == "APXMIDP") & (df["price"] > 0) & (df["volume"] > 0)
    sub = df[keep]
    dates = sub["settlement_date"].to_numpy()          # 'YYYY-MM-DD' sorts chronologically
    price = sub["price"].to_numpy(dtype=float)
    vol = sub["volume"].to_numpy(dtype=float)

    days, inv = np.unique(dates, return_inverse=True)
    vw = np.bincount(inv, weights=price * vol) / np.bincount(inv, weights=vol)
    return pd.DataFrame({"date": days, "price_gbp_per_mwh": vw})


def write_daily_csv(out_path: Path = P.PRICE_DAILY_CSV, raw_path: Path | None = None) -> pd.DataFrame:
    daily = build_daily_price(raw_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    daily.to_csv(out_path, index=False)
    return daily


def main() -> None:
    raw_path = _find_raw()
    daily = write_daily_csv(raw_path=raw_path)
    d = daily["date"].to_numpy()
    p = daily["price_gbp_per_mwh"].to_numpy()
    yr = d.astype("U4")
    print(f"Wrote {len(daily):,} daily prices from {raw_path.name} -> {P.PRICE_DAILY_CSV.name}")
    print(f"  {d[0]} -> {d[-1]}   overall mean £{p.mean():.1f}/MWh")
    for y in np.unique(yr):
        print(f"  {y}: £{p[yr == y].mean():.1f}/MWh")


if __name__ == "__main__":
    main()
