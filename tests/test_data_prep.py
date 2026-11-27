"""Checks on the daily price series: each day is the volume-weighted APX price with negative
trades kept and the dead N2EX feed and untraded half-hours dropped, restated in base-year pounds
with the consumer price index of its month."""

from __future__ import annotations

import pandas as pd
import pytest

from config import parameters as P
from src import data_prep


def test_daily_price_keeps_negative_trades_and_restates_by_month(tmp_path):
    raw = tmp_path / "raw.csv"
    pd.DataFrame([
        # settlement_date, data_provider, price, volume
        ("2025-01-15", "APXMIDP", 100.0, 3.0),
        ("2025-01-15", "APXMIDP", -20.0, 1.0),     # a negative trade counts
        ("2025-01-15", "APXMIDP", 500.0, 0.0),     # no trade, so no weight
        ("2025-01-15", "N2EXMIDP", 0.0, 0.0),      # the dead feed
        ("2025-02-15", "APXMIDP", 60.0, 2.0),
    ], columns=["settlement_date", "data_provider", "price", "volume"]).to_csv(raw, index=False)
    cpi = tmp_path / "cpi.csv"
    base = P.CPI_ANNUAL_AVERAGE[P.PRICE_BASE_YEAR]
    pd.DataFrame({"month": ["2025-01", "2025-02"],
                  "cpi_index": [base * 1.25, base * 1.5]}).to_csv(cpi, index=False)

    daily = data_prep.build_daily_price(raw, cpi)
    assert list(daily["date"]) == ["2025-01-15", "2025-02-15"]
    assert daily["price_nominal_gbp_per_mwh"].tolist() == pytest.approx([70.0, 60.0])
    assert daily["price_real_gbp_per_mwh"].tolist() == pytest.approx([70.0 / 1.25, 60.0 / 1.5])


def test_published_cpi_averages_match_the_monthly_file():
    # ONS averages the unrounded months but publishes both to one decimal place
    cpi = pd.read_csv(P.CPI_CSV, dtype={"month": str})
    for year, published in P.CPI_ANNUAL_AVERAGE.items():
        months = cpi[cpi["month"].str.startswith(str(year))]["cpi_index"]
        assert len(months) == 12
        assert months.mean() == pytest.approx(published, abs=0.1)


def test_missing_cpi_months_are_reported(tmp_path):
    cpi = tmp_path / "cpi.csv"
    pd.DataFrame({"month": ["2025-01"], "cpi_index": [130.0]}).to_csv(cpi, index=False)
    with pytest.raises(ValueError, match="no CPI for 2025-02"):
        data_prep.to_base_year_pounds(pd.Series([50.0]).to_numpy(), pd.Series(["2025-02"]).to_numpy(), cpi)
