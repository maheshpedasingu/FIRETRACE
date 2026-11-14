"""Cross-sensor diagnostics tests. All detections are SYNTHETIC TEST DATA."""

import math

import numpy as np
import pandas as pd
import pytest

from app.harmonization.cross_sensor import match_detections, monthly_calibration, spearman


def paired_series(factor=3.0, years=range(2018, 2024), noise=None):
    rng = np.random.default_rng(1)
    rows = []
    for year in years:
        for month in range(1, 13):
            modis = int(rng.integers(20, 200))
            viirs = modis * factor + (noise(rng) if noise else 0)
            rows += [
                {"platform": "Aqua", "year": year, "month": month,
                 "coverage_status": "complete", "detections": modis},
                {"platform": "NOAA-20", "year": year, "month": month,
                 "coverage_status": "complete", "detections": viirs},
            ]  # fmt: skip
    return pd.DataFrame(rows)


def test_exact_ratio_is_recovered_and_validated_on_held_out_years():
    result = monthly_calibration(paired_series(3.0), "Aqua", "NOAA-20", [2022, 2023])
    assert result.status == "estimated"
    assert (result.n_train, result.n_validation) == (48, 24)
    assert result.train_years == "2018,2019,2020,2021"
    assert result.scale_factor == pytest.approx(3.0)
    assert result.mae == pytest.approx(0.0, abs=1e-9)
    assert result.log_correlation == pytest.approx(1.0)


def test_noisy_relationship_reports_error_metrics():
    s = paired_series(2.5, noise=lambda rng: rng.normal(0, 20))
    r = monthly_calibration(s, "Aqua", "NOAA-20", [2023])
    assert r.status == "estimated"
    assert 2.3 < r.scale_factor < 2.7
    assert r.rmse >= r.mae > 0
    assert len(r.residuals) == 12


def test_too_few_months_means_unavailable_not_invented():
    s = paired_series(3.0, years=[2022, 2023])
    s = s[~((s.year == 2022) & (s.month == 1))]  # 11 training months, minimum is 12
    r = monthly_calibration(s, "Aqua", "NOAA-20", [2023])
    assert r.status == "unavailable" and math.isnan(r.scale_factor)
    assert "have 11 and 12" in r.reason


def test_incomplete_months_are_not_used():
    s = paired_series(3.0)
    s.loc[s.platform == "NOAA-20", "coverage_status"] = "partial"
    assert monthly_calibration(s, "Aqua", "NOAA-20", [2023]).status == "unavailable"


def dets(rows):
    return pd.DataFrame(
        rows, columns=["latitude", "longitude", "acquisition_datetime_utc", "frp_mw"]
    )


def test_matching_requires_space_and_time_proximity():
    modis = dets(
        [
            (15.1000, 80.2000, "2023-01-15T07:40:00Z", 20.0),  # matched (same cell, 5 min)
            (15.1000, 80.2000, "2023-01-15T09:40:00Z", 20.0),  # too late
            (18.0000, 78.0000, "2023-01-15T07:40:00Z", 10.0),  # no VIIRS nearby
            (16.0000, 79.0000, "2023-01-15T07:40:00Z", 30.0),  # matched via neighbour cell
        ]
    )
    viirs = dets(
        [
            (15.1002, 80.2002, "2023-01-15T07:45:00Z", 4.0),
            (15.1004, 80.2004, "2023-01-15T07:46:00Z", 6.0),
            (16.0060, 79.0000, "2023-01-15T07:41:00Z", 12.0),  # ~0.7 km north
        ]
    )
    r = match_detections(modis, viirs, tolerance_minutes=15)
    assert (r["modis_detections"], r["modis_matched"]) == (4, 2)
    assert r["match_fraction"] == 0.5
    assert r["frp_pairs"] == 2  # FRP ratio needs ≥3 pairs
    assert math.isnan(r["frp_median_ratio_viirs_to_modis"])
    strict = match_detections(modis, viirs, tolerance_minutes=15, neighbour_cells=0)
    assert strict["modis_matched"] == 1


def test_matching_frp_statistics():
    modis = dets([(10 + i, 20.0, "2023-01-15T07:40:00Z", 10.0 * (i + 1)) for i in range(4)])
    viirs = dets([(10 + i + 0.0001, 20.0, "2023-01-15T07:42:00Z", 2.0 * (i + 1)) for i in range(4)])
    r = match_detections(modis, viirs)
    assert r["frp_pairs"] == 4
    assert r["frp_median_ratio_viirs_to_modis"] == pytest.approx(0.2)
    assert r["frp_spearman"] == pytest.approx(1.0)


def test_empty_inputs():
    r = match_detections(dets([]), dets([]))
    assert r["modis_matched"] == 0 and math.isnan(r["match_fraction"])


def test_spearman_without_scipy():
    a = pd.Series([1, 2, 3, 4, 5])
    assert spearman(a, pd.Series([10, 20, 30, 40, 50])) == pytest.approx(1.0)
    assert spearman(a, pd.Series([5, 4, 3, 2, 1])) == pytest.approx(-1.0)
    assert math.isnan(spearman(a, pd.Series([1, 1, 1, 1, 1])))
