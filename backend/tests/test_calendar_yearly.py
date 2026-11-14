"""Calendar, yearly and distribution tests. All values are SYNTHETIC TEST DATA."""

import math

import numpy as np
import pandas as pd
import pytest

from app.analytics.calendar import MONTH_NAMES, build_calendar, calendar_grid, cell_state
from app.analytics.distributions import platform_distributions
from app.analytics.yearly import yearly_summary


@pytest.mark.parametrize(
    ("coverage", "value", "state"),
    [
        ("complete", 12, "value"),
        ("complete", 0, "zero"),
        ("partial", 3, "partial"),
        ("partial", 0, "partial"),
        ("missing", 4, "uncovered"),
        ("missing", np.nan, "missing"),
    ],
)
def test_cell_states(coverage, value, state):
    assert cell_state(coverage, value) == state


def month_rows(platform, year, values, status="complete"):
    return [
        {"platform": platform, "year": year, "month": m, "coverage_status": status,
         "days_covered": 30 if status == "complete" else 0, "days_in_range": 30,
         "detections": v}
        for m, v in enumerate(values, start=1)
    ]  # fmt: skip


def synthetic_series():
    rows = []
    for year in range(2015, 2021):
        rows += month_rows("Aqua", year, [10] * 12)
    rows += month_rows("Aqua", 2021, [10, 10, 80, 10, 10, 10, 10, 10, 10, 10, 10, 0])
    rows += month_rows("NOAA-21", 2021, [np.nan] * 12, status="missing")
    return pd.DataFrame(rows)


def test_calendar_states_and_anomalies():
    cal = build_calendar(synthetic_series(), min_history_years=5)
    march = cal[(cal.platform == "Aqua") & (cal.year == 2021) & (cal.month == 3)].iloc[0]
    assert march.state == "value"
    # every history year had exactly 10 → MAD 0 → zero dispersion, honestly not scored
    assert march.anomaly_status == "zero_dispersion" and math.isnan(march.modified_z)
    dec = cal[(cal.platform == "Aqua") & (cal.year == 2021) & (cal.month == 12)].iloc[0]
    assert dec.state == "zero"
    assert set(cal[cal.platform == "NOAA-21"].state) == {"missing"}


@pytest.mark.filterwarnings("error")  # regression: Pandas4Warning on str fill of float columns
def test_calendar_grid_partial_year_has_no_dtype_warning():
    rows = month_rows("NOAA-20", 2026, [np.nan] * 10, status="missing")
    rows.append({"platform": "NOAA-20", "year": 2026, "month": 11, "coverage_status": "partial",
                 "days_covered": 3, "days_in_range": 14, "detections": 462})  # fmt: skip
    grid = calendar_grid(build_calendar(pd.DataFrame(rows)), "NOAA-20")
    assert grid.loc[0, "Nov"] == "partial:462" and grid.loc[0, "Dec"] == "outside range"


def test_calendar_grid_rows_are_years_columns_are_months():
    grid = calendar_grid(build_calendar(synthetic_series()), "Aqua")
    assert list(grid.columns) == ["year", *MONTH_NAMES]
    assert grid.year.tolist() == list(range(2015, 2022))
    row_2021 = grid[grid.year == 2021].iloc[0]
    assert row_2021["Mar"] == "value:80" and row_2021["Dec"] == "zero:0"
    assert calendar_grid(build_calendar(synthetic_series()), "NOAA-21").iloc[0]["Jan"] == "missing"


def test_yearly_totals_and_year_over_year_only_for_complete_years():
    rows = month_rows("Aqua", 2020, [10] * 12) + month_rows("Aqua", 2021, [20] * 12)
    rows += month_rows("Aqua", 2022, [5] * 11) + month_rows("Aqua", 2022, [np.nan], "missing")[:1]
    table = yearly_summary(pd.DataFrame(rows))
    y = {int(r.year): r for r in table.itertuples(index=False)}
    assert y[2020].total == 120 and y[2020].yoy_note == "no previous year"
    assert y[2021].complete_year and y[2021].yoy_change == 120 and y[2021].yoy_change_pct == 100
    assert not y[2022].complete_year and math.isnan(y[2022].yoy_change)
    assert "lacks complete coverage" in y[2022].yoy_note


def test_distributions_exclude_missing_frp_and_count_classes():
    obs = pd.DataFrame(
        {
            "platform": ["NOAA-20"] * 5 + ["Aqua"],
            "frp_mw": [1.0, 2.0, 3.0, 4.0, np.nan, 50.0],
            "confidence_class": ["low", "nominal", "nominal", "high", None, "high"],
            "day_night": ["D", "D", "N", "N", "", "D"],
        }
    )
    dist = platform_distributions(obs).set_index("platform")
    n20 = dist.loc["NOAA-20"]
    assert (n20.detections, n20.frp_values, n20.frp_missing) == (5, 4, 1)
    assert n20.frp_median_mw == 2.5 and n20.frp_max_mw == 4.0 and n20.frp_sum_mw == 10.0
    assert (n20.confidence_low, n20.confidence_nominal, n20.confidence_high,
            n20.confidence_missing) == (1, 2, 1, 1)  # fmt: skip
    assert (n20.day, n20.night, n20.daynight_unknown) == (2, 2, 1)
    assert dist.loc["Aqua"].frp_max_mw == 50.0
