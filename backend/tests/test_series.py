"""Coverage-aware area series tests. All values are SYNTHETIC TEST DATA."""

import json
from datetime import date

import numpy as np
import pandas as pd

from app.analytics.series import AreaBBox, coverage_contains, monthly_series
from app.harmonization.cell_days import aggregate, combine


def cov(platform, start, end, bbox=(70, 10, 90, 25), status="NRT", extent_type="bbox", value=None):
    if value is None and extent_type == "bbox":
        value = json.dumps(dict(zip(["west", "south", "east", "north"], bbox, strict=True)))
    return {
        "platform": platform,
        "processing_status": status,
        "start_date": start,
        "end_date": end,
        "extent_type": extent_type,
        "extent_value": value,
        "basis": "api_request",
    }


AOI = AreaBBox(76, 12, 85, 20)


def cell_days(rows):
    columns = ["sensor", "platform", "processing_status", "acquisition_date", "latitude",
               "longitude", "day_night", "frp_mw", "confidence_class"]  # fmt: skip
    return combine([aggregate(pd.DataFrame(rows, columns=columns))])


SYNTHETIC = cell_days(
    [
        ("VIIRS", "NOAA-20", "NRT", date(2026, 11, 11), 15.1, 80.2, "D", 5.0, "nominal"),
        ("VIIRS", "NOAA-20", "NRT", date(2026, 11, 11), 15.1001, 80.2001, "D", 1.0, "low"),
        ("VIIRS", "NOAA-20", "NRT", date(2026, 11, 12), 15.1, 80.2, "N", 2.0, "high"),
        ("VIIRS", "NOAA-20", "NRT", date(2026, 11, 12), 18.0, 78.0, "D", 3.0, "high"),
        (
            "VIIRS",
            "NOAA-20",
            "NRT",
            date(2026, 11, 12),
            40.0,
            10.0,
            "D",
            3.0,
            "high",
        ),  # outside AOI
    ]
)


def row(table, platform, year, month):
    return table[(table.platform == platform) & (table.year == year) & (table.month == month)].iloc[
        0
    ]


def test_coverage_contains_bbox_country_unknown_and_antimeridian():
    assert coverage_contains(cov("NOAA-20", None, None), AOI)
    assert not coverage_contains(cov("NOAA-20", None, None, bbox=(78, 10, 90, 25)), AOI)
    across = AreaBBox(175, -20, -175, -10)
    assert coverage_contains(cov("x", None, None, bbox=(170, -30, -170, 0)), across)
    assert not coverage_contains(cov("x", None, None, bbox=(170, -30, 180, 0)), across)
    country = cov("x", None, None, extent_type="country", value="Synthetic Land")
    assert not coverage_contains(country, AOI)
    assert coverage_contains(country, AreaBBox(0, 0, 1, 1, country="synthetic land"))
    assert not coverage_contains(cov("x", None, None, extent_type="unknown", value=None), AOI)


def test_counts_unique_cells_and_cell_days_inside_aoi_only():
    coverage = [cov("NOAA-20", date(2026, 11, 11), date(2026, 11, 13))]
    table = monthly_series(
        SYNTHETIC, AOI, date(2026, 11, 11), date(2026, 11, 13), coverage, ["NOAA-20"]
    )
    r = row(table, "NOAA-20", 2026, 11)
    assert (r.detections, r.cell_days, r.unique_cells) == (4, 3, 2)
    # every selected day is covered, but only 3 of November's 30 days are selected
    assert (r.days_in_range, r.days_covered, r.coverage_status) == (3, 3, "partial")
    assert r.frp_sum_mw == 11.0 and r.frp_max_mw == 5.0


def test_covered_month_without_detections_is_zero_uncovered_is_missing():
    coverage = [cov("Terra", date(2026, 11, 1), date(2026, 11, 30), status="NRT")]
    table = monthly_series(
        SYNTHETIC, AOI, date(2026, 10, 1), date(2026, 11, 30), coverage, ["Terra"]
    )
    nov, oct_ = row(table, "Terra", 2026, 11), row(table, "Terra", 2026, 10)
    assert nov.coverage_status == "complete" and nov.detections == 0
    assert oct_.coverage_status == "missing" and np.isnan(oct_.detections)


def test_month_cut_short_by_the_period_is_partial_not_complete():
    """Real case: period ending 7 Nov compared 7 days with 26 full Novembers."""
    coverage = [cov("Terra", date(2026, 10, 1), date(2026, 11, 30), status="NRT")]
    table = monthly_series(
        SYNTHETIC, AOI, date(2026, 10, 1), date(2026, 11, 7), coverage, ["Terra"]
    )
    assert row(table, "Terra", 2026, 10).coverage_status == "complete"
    nov = row(table, "Terra", 2026, 11)
    assert (nov.days_in_range, nov.days_covered, nov.coverage_status) == (7, 7, "partial")


def test_partial_coverage_is_reported():
    coverage = [cov("NOAA-20", date(2026, 11, 11), date(2026, 11, 13))]
    table = monthly_series(
        SYNTHETIC, AOI, date(2026, 11, 1), date(2026, 11, 30), coverage, ["NOAA-20"]
    )
    r = row(table, "NOAA-20", 2026, 11)
    assert (r.days_covered, r.coverage_status, r.detections) == (3, "partial", 4)


def test_detections_without_coverage_are_counted_but_month_stays_missing():
    table = monthly_series(SYNTHETIC, AOI, date(2026, 11, 11), date(2026, 11, 13), [], ["NOAA-20"])
    r = row(table, "NOAA-20", 2026, 11)
    assert r.coverage_status == "missing" and r.detections == 4


def test_sp_supersedes_nrt_for_the_same_day():
    data = cell_days(
        [
            ("VIIRS", "NOAA-20", "NRT", date(2026, 7, 1), 15.1, 80.2, "D", 5.0, "nominal"),
            ("VIIRS", "NOAA-20", "SP", date(2026, 7, 1), 15.1002, 80.2002, "D", 4.0, "nominal"),
            ("VIIRS", "NOAA-20", "NRT", date(2026, 7, 2), 15.1, 80.2, "D", 5.0, "nominal"),
        ]
    )
    coverage = [cov("NOAA-20", date(2026, 7, 1), date(2026, 7, 2))]
    table = monthly_series(data, AOI, date(2026, 7, 1), date(2026, 7, 2), coverage, ["NOAA-20"])
    r = row(table, "NOAA-20", 2026, 7)
    assert r.detections == 2  # SP on 1 July, NRT on 2 July — never both
    assert r.processing_status_used == "NRT,SP"


def test_platforms_are_never_summed():
    data = cell_days(
        [
            ("VIIRS", "NOAA-20", "NRT", date(2026, 11, 11), 15.1, 80.2, "D", 5.0, "nominal"),
            ("MODIS", "Aqua", "NRT", date(2026, 11, 11), 15.1, 80.2, "D", 9.0, "high"),
        ]
    )
    table = monthly_series(
        data, AOI, date(2026, 11, 11), date(2026, 11, 11), [], ["NOAA-20", "Aqua"]
    )
    assert sorted(table.platform) == ["Aqua", "NOAA-20"]
    assert list(table.detections) == [1, 1]


def test_antimeridian_aoi_selects_both_sides():
    data = cell_days(
        [
            ("VIIRS", "NOAA-20", "NRT", date(2026, 11, 11), -16.5, 179.95, "N", 1.0, "high"),
            ("VIIRS", "NOAA-20", "NRT", date(2026, 11, 11), -16.5, -179.95, "N", 1.0, "high"),
            ("VIIRS", "NOAA-20", "NRT", date(2026, 11, 11), -16.5, 170.0, "N", 1.0, "high"),
        ]
    )
    aoi = AreaBBox(175, -20, -175, -10)
    table = monthly_series(data, aoi, date(2026, 11, 11), date(2026, 11, 11), [], ["NOAA-20"])
    assert row(table, "NOAA-20", 2026, 11).detections == 2
