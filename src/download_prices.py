"""
Downloads the public price data the model starts from: the GB wholesale price history from
Elexon, which runs the electricity market's settlement, and the UK consumer price index from the
Office for National Statistics (ONS), used to restate those prices in 2024 pounds.

Elexon's Market Index Data (MID) gives, for every half-hour settlement period, the price and traded
volume reported by each index provider. It is free to use and needs no account or key. One request
may span at most 7 days, so we step through the range a week at a time and write every row to
data/raw/, where src/data_prep.py turns it into the daily series the model is calibrated on.

    python -m src.download_prices                                    # the range the model uses
    python -m src.download_prices --start=2024-01-01 --end=2024-12-31
"""

from __future__ import annotations

import csv
import http.client
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from config import parameters as P

API = "https://data.elexon.co.uk/bmrs/api/v1/datasets/MID"
WINDOW = timedelta(days=7)          # the longest span the API accepts in one request
PERIOD = timedelta(minutes=30)
COLUMNS = ["settlement_date", "settlement_period", "start_time", "data_provider", "price", "volume"]
CPI_URL = ("https://www.ons.gov.uk/generator?format=csv"
           "&uri=/economy/inflationandpriceindices/timeseries/d7bt/mm23")


def _fetch(first: datetime, last: datetime, retries: int = 3) -> list[dict]:
    """Every MID row whose start time lies in [first, last]; the API includes both ends. Server
    faults and cut-off responses are retried; a rejected request is not."""
    url = f"{API}?from={first:%Y-%m-%dT%H:%MZ}&to={last:%Y-%m-%dT%H:%MZ}&format=json"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                return json.load(response)["data"]
        except urllib.error.HTTPError as err:
            if err.code < 500 or attempt == retries - 1:
                raise
        except (OSError, http.client.IncompleteRead, ValueError):
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)


def download(start: str = P.PRICE_DOWNLOAD_START, end: str = P.PRICE_DOWNLOAD_END) -> Path:
    """Write every half-hourly MID row for settlement dates start..end, inclusive, to data/raw/.

    A settlement date is a UK local day, so in summer its first period starts at 23:00 UTC the
    evening before. We query a day either side of the range and keep rows by settlement date."""
    first_day, last_day = date.fromisoformat(start), date.fromisoformat(end)
    start, end = first_day.isoformat(), last_day.isoformat()   # the API's YYYY-MM-DD form
    if first_day > last_day:
        raise ValueError(f"start {start} is after end {end}")
    # a UK settlement day ends by midnight UTC; one still in progress would be averaged over only
    # the half-hours published so far
    today = datetime.now(timezone.utc).date()
    if last_day >= today:
        raise ValueError(f"{end} is not over yet, so its prices are incomplete; "
                         f"choose an end date before {today}")

    t = datetime.combine(first_day - timedelta(days=1), datetime.min.time(), timezone.utc)
    stop = datetime.combine(last_day + timedelta(days=2), datetime.min.time(), timezone.utc)
    rows = {}
    while t < stop:
        for r in _fetch(t, min(t + WINDOW, stop) - PERIOD):
            if start <= r["settlementDate"] <= end:
                rows[(r["settlementDate"], r["settlementPeriod"], r["dataProvider"])] = r
        t += WINDOW

    out = P.DATA_RAW_DIR / f"elexon_market_index_{start}_{end}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        for key in sorted(rows):
            r = rows[key]
            writer.writerow([r["settlementDate"], r["settlementPeriod"], r["startTime"],
                             r["dataProvider"], r["price"], r["volume"]])
    return out


def download_cpi(out: Path = P.CPI_CSV) -> Path:
    """The monthly ONS consumer price index (series D7BT, 2015 = 100). Picking out the monthly
    rows is the only cleaning it needs, so it goes straight to data/processed/."""
    request = urllib.request.Request(CPI_URL, headers={"User-Agent": "UK-Offshore-Wind-Real-Options"})
    with urllib.request.urlopen(request, timeout=60) as response:
        rows = csv.reader(io.StringIO(response.read().decode("utf-8-sig")))
        monthly = [(datetime.strptime(row[0].title(), "%Y %b").strftime("%Y-%m"), row[1])
                   for row in rows if len(row) == 2 and re.fullmatch(r"\d{4} [A-Z]{3}", row[0])]
    if not monthly:
        raise ValueError(f"no monthly rows in the ONS download, so {out.name} was left as it was; "
                         "the ONS format may have changed")
    with out.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["month", "cpi_index"])
        writer.writerows(monthly)
    return out


def main(argv=None) -> None:
    argv = sys.argv[1:] if argv is None else argv
    start = next((a.split("=")[1] for a in argv if a.startswith("--start=")), P.PRICE_DOWNLOAD_START)
    end = next((a.split("=")[1] for a in argv if a.startswith("--end=")), P.PRICE_DOWNLOAD_END)
    print(f"Downloading Elexon market index data for {start} to {end}, a week per request...",
          flush=True)
    t0 = time.time()
    out = download(start, end)
    with out.open() as f:
        n_rows = sum(1 for _ in f) - 1
    print(f"Wrote {n_rows:,} half-hourly rows to {out.relative_to(P.PROJECT_ROOT)} "
          f"in {time.time() - t0:.0f}s")
    cpi = download_cpi()
    with cpi.open() as f:
        months = list(csv.reader(f))[1:]
    print(f"Wrote {len(months):,} months of ONS CPI, {months[0][0]} to {months[-1][0]}, "
          f"to {cpi.relative_to(P.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
