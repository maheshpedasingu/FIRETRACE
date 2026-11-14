"""Baseline / anomaly / HAI tests. All series values are SYNTHETIC TEST DATA."""

import math

import pandas as pd
import pytest

from app.analytics.baselines import assess, assess_all, harmonized_index


def series(platform, values_by_year, month=3, status="complete"):
    rows = []
    for year, value in values_by_year.items():
        st = status(year) if callable(status) else status
        rows.append(
            {"platform": platform, "year": year, "month": month, "coverage_status": st,
             "detections": value}
        )  # fmt: skip
    return pd.DataFrame(rows)


HISTORY = {2015: 100, 2016: 110, 2017: 90, 2018: 105, 2019: 95, 2020: 120, 2021: 80}


def test_modified_z_against_hand_calculation():
    s = series("Aqua", {**HISTORY, 2022: 200})
    r = assess(s, "Aqua", 2022, 3)
    # history sorted: 80 90 95 100 105 110 120 → median 100; |dev| 20 10 5 0 5 10 20 → MAD 10
    assert (r.median, r.mad, r.history_years) == (100.0, 10.0, 7)
    assert r.modified_z == pytest.approx(0.6745 * (200 - 100) / 10)
    assert (r.status, r.label) == ("assessed", "unusually high")
    assert r.percentile_rank == 100.0


def test_within_normal_and_unusually_low():
    assert (
        assess(series("Aqua", {**HISTORY, 2022: 104}), "Aqua", 2022, 3).label
        == "within normal range"
    )
    assert assess(series("Aqua", {**HISTORY, 2022: 20}), "Aqua", 2022, 3).label == "unusually low"


def test_only_earlier_years_and_complete_months_form_the_baseline():
    s = series("Aqua", {**HISTORY, 2022: 200, 2023: 5000},
               status=lambda y: "partial" if y == 2016 else "complete")  # fmt: skip
    r = assess(s, "Aqua", 2022, 3)
    assert r.history_years == 6  # 2016 partial excluded, 2023 is later


def test_insufficient_history_is_explicit():
    r = assess(series("NOAA-21", {2023: 50, 2024: 60, 2025: 70}), "NOAA-21", 2025, 3)
    assert (r.status, r.label) == ("insufficient_history", "not assessed")
    assert math.isnan(r.modified_z)


def test_incomplete_target_month_is_not_assessed():
    s = series(
        "Aqua", {**HISTORY, 2022: 200}, status=lambda y: "partial" if y == 2022 else "complete"
    )
    assert assess(s, "Aqua", 2022, 3).status == "incomplete_coverage"


def test_zero_dispersion_reports_percentile_not_z():
    s = series("Terra", {2015: 0, 2016: 0, 2017: 0, 2018: 0, 2019: 0, 2020: 3})
    r = assess(s, "Terra", 2020, 3)
    assert r.status == "zero_dispersion" and math.isnan(r.modified_z)
    assert r.percentile_rank == 100.0


def test_harmonized_index_weights_sensors_equally_and_lists_contributors():
    viirs = {**HISTORY, 2022: 200}
    frames = [
        series("Aqua", {**HISTORY, 2022: 100}),  # z = 0
        series("NOAA-20", viirs),  # z ≈ 6.745
        series("Suomi-NPP", viirs),  # z ≈ 6.745
        series("NOAA-21", {2021: 1, 2022: 2}),  # insufficient history
    ]
    assessments = assess_all(pd.concat(frames, ignore_index=True))
    hai = harmonized_index(assessments)
    row = hai[(hai.year == 2022) & (hai.month == 3)].iloc[0]
    assert row.sensors == "MODIS,VIIRS"
    assert row.hai == pytest.approx((0 + 6.745) / 2)  # two VIIRS platforms do not outvote MODIS
    assert row.sensor_disagreement == pytest.approx(6.745)
    assert "NOAA-21:insufficient_history" in row.not_assessed
    assert row.status == "experimental"


def test_harmonized_index_unavailable_without_assessable_platforms():
    hai = harmonized_index(assess_all(series("NOAA-21", {2023: 1, 2024: 2})))
    assert set(hai.status) == {"unavailable"} and hai.hai.isna().all()
