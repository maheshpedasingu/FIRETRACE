"""Harmonized calendar tests. SYNTHETIC TEST DATA only (not NASA observations)."""

from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.analytics.platform_periods import PLATFORM_DATA_START, first_record_day
from app.analytics.series import AreaBBox, covered_days
from app.harmonization.harmonized import (
    MODIS_COMBINED,
    fit_conversion,
    harmonize,
    validation_years,
    with_modis_combined,
)

# Seasonal shape: same for every year so the true conversion factors are exact.
SEASON = [5, 8, 20, 40, 30, 10, 4, 3, 3, 6, 12, 7]


def row(platform, year, month, value, status="complete"):
    return {
        "platform": platform, "year": year, "month": month, "coverage_status": status,
        "days_covered": 30 if status == "complete" else (10 if status == "partial" else 0),
        "days_in_range": 30, "detections": value,
    }  # fmt: skip


def synthetic(years_modis=range(2003, 2016), years_viirs=range(2012, 2018), snpp_ratio=3.0):
    """Terra = Aqua = SEASON; Suomi-NPP = ratio × (Terra + Aqua). MODIS ends after 2015."""
    rows = []
    for y in years_modis:
        for m, v in enumerate(SEASON, start=1):
            rows += [row("Terra", y, m, v), row("Aqua", y, m, v)]
    for y in years_viirs:
        for m, v in enumerate(SEASON, start=1):
            rows.append(row("Suomi-NPP", y, m, snpp_ratio * 2 * v))
            if y not in years_modis:
                rows += [
                    row("Terra", y, m, np.nan, "missing"),
                    row("Aqua", y, m, np.nan, "missing"),
                ]
    return pd.DataFrame(rows)


def cell(result, year, month):
    t = result["cells"]
    return t[(t.year == year) & (t.month == month)].iloc[0]


def fit(result, source):
    return next(f for f in result["fits"] if f["source"] == source)


def test_validation_years_every_third_overlap_year():
    assert validation_years([2012, 2013, 2014, 2015, 2016, 2017]) == [2013, 2016]
    assert validation_years([2014, 2012]) == [2014]


def test_modis_combined_only_where_both_complete():
    s = pd.DataFrame([row("Terra", 2010, 1, 4), row("Aqua", 2010, 1, 6),
                      row("Terra", 2010, 2, 4), row("Aqua", 2010, 2, np.nan, "missing")])  # fmt: skip
    combined = with_modis_combined(s, "detections")
    c = combined[combined.platform == MODIS_COMBINED].set_index("month")
    assert c.loc[1, "coverage_status"] == "complete" and c.loc[1, "detections"] == 10
    assert c.loc[2, "coverage_status"] == "partial"


def test_modis_reference_converts_viirs_after_modis_ends():
    result = harmonize(synthetic(), reference="modis")
    assert result["reference_source"] == MODIS_COMBINED
    snpp = fit(result, "Suomi-NPP")
    assert snpp["status"] == "estimated"
    assert snpp["factor"] == pytest.approx(1 / 3)
    assert snpp["rmse"] == pytest.approx(0, abs=1e-9)
    # overlap month: the reference itself, not converted
    c2013 = cell(result, 2013, 4)
    assert c2013.source == MODIS_COMBINED and not c2013.converted
    assert c2013.value == 80 and c2013.relative_uncertainty == 0
    # after MODIS: Suomi-NPP converted into MODIS (Terra+Aqua) units
    c2017 = cell(result, 2017, 4)
    assert c2017.source == "Suomi-NPP" and c2017.converted
    assert c2017.value == pytest.approx(80) and c2017.state == "value"
    assert "converted from Suomi-NPP" in c2017.note


def test_viirs_reference_backcasts_modis_years():
    result = harmonize(synthetic(), reference="viirs")
    modis = fit(result, MODIS_COMBINED)
    assert modis["factor"] == pytest.approx(3.0)
    c2005 = cell(result, 2005, 4)
    assert c2005.source == MODIS_COMBINED and c2005.converted
    assert c2005.value == pytest.approx(240)
    assert cell(result, 2013, 4).source == "Suomi-NPP"


def test_insufficient_overlap_gives_no_factor_and_explains_missing_months():
    # Suomi-NPP overlaps MODIS for only one year: no factor may be invented.
    result = harmonize(synthetic(years_modis=range(2003, 2013), years_viirs=range(2012, 2015)))
    snpp = fit(result, "Suomi-NPP")
    assert snpp["status"] == "unavailable" and math.isnan(snpp["factor"])
    c2014 = cell(result, 2014, 4)
    assert c2014.state == "missing" and math.isnan(c2014.value)
    assert "no conversion factor" in c2014.note and "Suomi-NPP" in c2014.note


def test_real_zero_partial_and_missing_are_kept():
    s = synthetic()
    s.loc[(s.platform == "Terra") & (s.year == 2010) & (s.month == 1), "detections"] = 0
    s.loc[(s.platform == "Aqua") & (s.year == 2010) & (s.month == 1), "detections"] = 0
    s.loc[(s.platform.isin(["Terra", "Aqua"])) & (s.year == 2010) & (s.month == 2),
          "coverage_status"] = "partial"  # fmt: skip
    s = pd.concat([s, pd.DataFrame([row("Terra", 2018, 1, np.nan, "missing")])])
    result = harmonize(s)
    assert cell(result, 2010, 1).state == "zero"
    assert cell(result, 2010, 2).state == "partial"
    missing = cell(result, 2018, 1)
    assert missing.state == "missing" and missing.note == "no imported data"


def test_terra_only_months_before_aqua_are_converted_not_summed():
    s = synthetic()
    terra_2002 = [row("Terra", 2002, m, v) for m, v in enumerate(SEASON, start=1)]
    aqua_2002 = [row("Aqua", 2002, m, np.nan, "missing") for m in range(1, 13)]
    result = harmonize(pd.concat([s, pd.DataFrame(terra_2002 + aqua_2002)], ignore_index=True))
    terra = fit(result, "Terra")
    assert terra["factor"] == pytest.approx(2.0)  # Terra + Aqua = 2 × Terra here
    c = cell(result, 2002, 4)
    assert c.source == "Terra" and c.converted and c.value == pytest.approx(80)


def test_harmonized_anomaly_against_same_month_history():
    s = synthetic()
    # vary history so MAD > 0, then a spike in April 2015
    for y in range(2003, 2015):
        s.loc[(s.platform.isin(["Terra", "Aqua"])) & (s.year == y) & (s.month == 4),
              "detections"] = 40 + (y % 3)  # fmt: skip
    s.loc[(s.platform.isin(["Terra", "Aqua"])) & (s.year == 2015) & (s.month == 4),
          "detections"] = 400  # fmt: skip
    c = cell(harmonize(s, min_history_years=5), 2015, 4)
    assert c.anomaly_status == "assessed" and c.anomaly == "unusually high"


def test_unknown_reference_is_rejected():
    with pytest.raises(ValueError):
        harmonize(synthetic(), reference="landsat")


def test_fit_conversion_reports_validation_error():
    s = synthetic()
    noisy = s.platform == "Suomi-NPP"
    s.loc[noisy, "detections"] = s.loc[noisy, "detections"] * np.where(
        s.loc[noisy, "year"] % 2 == 0, 1.2, 0.8
    )
    f = fit_conversion(with_modis_combined(s, "detections"), "Suomi-NPP", MODIS_COMBINED)
    assert f.status == "estimated" and f.rmse > 0 and 0 < f.relative_rmse < 1


def test_platform_data_start_dates():
    assert PLATFORM_DATA_START["Aqua"] == date(2002, 7, 4)
    assert first_record_day("NOAA-21") == date(2024, 1, 17)
    assert first_record_day("Unknown") is None


def test_coverage_never_extends_before_a_platforms_first_record():
    aoi = AreaBBox(70, 10, 90, 25)
    extent = json.dumps({"west": 60, "south": 0, "east": 100, "north": 30})
    coverage = [{"platform": p, "processing_status": "SP", "extent_type": "bbox",
                 "extent_value": extent,
                 "start_date": date(2001, 1, 1), "end_date": date(2002, 7, 10)}
                for p in ("Terra", "Aqua")]  # fmt: skip
    terra = covered_days(coverage, aoi, "Terra", date(2001, 1, 1), date(2002, 7, 10))
    aqua = covered_days(coverage, aoi, "Aqua", date(2001, 1, 1), date(2002, 7, 10))
    assert min(terra) == date(2001, 1, 1)
    assert min(aqua) == date(2002, 7, 4) and len(aqua) == 7
