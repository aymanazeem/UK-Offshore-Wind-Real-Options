"""Checks on the Elexon download, with the API replaced by a fake that labels each half-hour with
its UK settlement day as Elexon does. Requests respect the API's 7-day limit and leave no gaps,
every half-hour of each requested day is kept once (46 and 50 on clock-change days), the file
feeds data_prep's volume-weighted daily price, and a day that is not over yet is refused."""

from __future__ import annotations

import csv
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from config import parameters as P
from src import data_prep
from src import download_prices as dl

UK = ZoneInfo("Europe/London")
HALF_HOUR = timedelta(minutes=30)


def _fake_api(first, last):
    """One APX and one dead N2EX row per half-hour starting in [first, last]. Odd periods trade
    3 MWh at £40, even periods 1 MWh at £100, so each full day's weighted price is £55."""
    rows, t = [], first
    while t <= last:
        day = t.astimezone(UK).date()
        midnight = datetime.combine(day, time(), UK).astimezone(timezone.utc)
        period = (t - midnight) // HALF_HOUR + 1
        common = {"settlementDate": day.isoformat(), "settlementPeriod": period,
                  "startTime": f"{t:%Y-%m-%dT%H:%M:%SZ}"}
        rows.append({**common, "dataProvider": "APXMIDP",
                     "price": 40.0 if period % 2 else 100.0, "volume": 3.0 if period % 2 else 1.0})
        rows.append({**common, "dataProvider": "N2EXMIDP", "price": 0.0, "volume": 0.0})
        t += HALF_HOUR
    return rows


@pytest.fixture
def fake_api(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(dl, "_fetch", lambda first, last: calls.append((first, last)) or
                        _fake_api(first, last))
    monkeypatch.setattr(P, "DATA_RAW_DIR", tmp_path)
    return calls


def _periods_per_day(path):
    with path.open() as f:
        return Counter(r["settlement_date"] for r in csv.DictReader(f) if r["data_provider"] == "APXMIDP")


def test_requests_stay_within_the_api_limit_and_leave_no_gaps(fake_api):
    dl.download("2024-03-01", "2024-04-15")
    assert all(last - first <= timedelta(days=7) for first, last in fake_api)
    assert all(nxt[0] - prev[1] == HALF_HOUR for prev, nxt in zip(fake_api, fake_api[1:]))


@pytest.mark.parametrize("start, end, clock_change, n_periods", [
    ("2024-10-20", "2024-11-15", "2024-10-27", 50),   # summer start, clocks go back, winter end
    ("2024-03-29", "2024-04-02", "2024-03-31", 46),   # clocks go forward
])
def test_every_half_hour_of_each_requested_day_is_kept_once(fake_api, start, end, clock_change,
                                                            n_periods):
    counts = _periods_per_day(dl.download(start, end))
    days = [(date.fromisoformat(start) + timedelta(days=i)).isoformat()
            for i in range((date.fromisoformat(end) - date.fromisoformat(start)).days + 1)]
    assert list(counts) == days
    assert all(n == (n_periods if day == clock_change else 48) for day, n in counts.items())


def test_download_feeds_the_volume_weighted_daily_price(fake_api):
    daily = data_prep.build_daily_price(dl.download("2024-07-01", "2024-07-03"))
    assert list(daily["date"]) == ["2024-07-01", "2024-07-02", "2024-07-03"]
    assert daily["price_gbp_per_mwh"].to_numpy() == pytest.approx(55.0)


def test_refuses_a_day_that_is_not_over(monkeypatch, tmp_path):
    monkeypatch.setattr(dl, "_fetch", lambda first, last: pytest.fail("must not reach the API"))
    monkeypatch.setattr(P, "DATA_RAW_DIR", tmp_path)
    with pytest.raises(ValueError, match="not over yet"):
        dl.download("2024-01-01", (date.today() + timedelta(days=2)).isoformat())
