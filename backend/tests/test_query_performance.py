"""Caching, store generation and aggregate-based statistics (SYNTHETIC TEST DATA only)."""

from __future__ import annotations

import threading
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.analytics.distributions import distributions_from_cell_days, platform_distributions
from app.harmonization.cell_days import aggregate, combine
from app.services.area_analysis import _ContextCache
from app.storage import generation

D1, D2 = date(2023, 1, 15), date(2023, 1, 16)
COLUMNS = ["sensor", "platform", "processing_status", "acquisition_date", "latitude",
           "longitude", "day_night", "frp_mw", "confidence_class"]  # fmt: skip
SYNTHETIC = pd.DataFrame(
    [
        ("VIIRS", "NOAA-20", "NRT", D1, 15.1000, 80.2000, "D", 5.0, "nominal"),
        ("VIIRS", "NOAA-20", "NRT", D1, 15.1003, 80.2003, "N", np.nan, "high"),
        ("VIIRS", "NOAA-20", "NRT", D2, 15.1000, 80.2000, "D", 2.0, "low"),
        ("VIIRS", "Suomi-NPP", "NRT", D1, 15.1000, 80.2000, "D", 1.0, "nominal"),
        ("MODIS", "Aqua", "SP", D1, -8.0, -55.0, "", 10.0, ""),
    ],
    columns=COLUMNS,
)


def test_generation_marker_changes_on_bump(tmp_path: Path):
    assert generation.current(tmp_path) == "initial"
    first = generation.bump(tmp_path)
    assert generation.current(tmp_path) == first
    second = generation.bump(tmp_path)
    assert second != first and generation.current(tmp_path) == second
    assert not list(tmp_path.glob("*.partial"))


def test_distributions_from_cell_days_match_detection_level_counts():
    cells = combine([aggregate(SYNTHETIC)])
    fast = distributions_from_cell_days(cells, SYNTHETIC).set_index("platform")
    exact = platform_distributions(SYNTHETIC).set_index("platform")
    exact_cols = ["detections", "frp_values", "frp_missing", "frp_sum_mw", "frp_mean_mw",
                  "frp_median_mw", "frp_p90_mw", "frp_max_mw", "confidence_low",
                  "confidence_nominal", "confidence_high", "confidence_missing", "day",
                  "night", "daynight_unknown"]  # fmt: skip
    pd.testing.assert_frame_equal(
        fast[exact_cols], exact[exact_cols], check_dtype=False, check_exact=False
    )
    assert fast.loc["NOAA-20", "frp_percentile_detections"] == 2


def test_frp_percentiles_may_come_from_a_shorter_period():
    cells = combine([aggregate(SYNTHETIC)])
    recent = SYNTHETIC[SYNTHETIC["acquisition_date"] == D2]
    table = distributions_from_cell_days(cells, recent).set_index("platform")
    assert table.loc["NOAA-20", "detections"] == 3  # counts: whole period
    assert table.loc["NOAA-20", "frp_median_mw"] == 2.0  # percentiles: D2 only
    assert np.isnan(table.loc["Suomi-NPP", "frp_median_mw"])


def test_context_cache_builds_once_for_concurrent_requests():
    cache = _ContextCache(size=2)
    calls = []

    def build():
        calls.append(1)
        time.sleep(0.05)
        return object()

    results = []
    threads = [threading.Thread(target=lambda: results.append(cache.get(("k",), build)))
               for _ in range(5)]  # fmt: skip
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1 and len({id(r) for r in results}) == 1


def test_context_cache_evicts_oldest():
    cache = _ContextCache(size=2)
    a = cache.get(("a",), object)
    cache.get(("b",), object)
    cache.get(("c",), object)
    assert cache.get(("a",), object) is not a  # rebuilt after eviction


@pytest.mark.parametrize("module", ["pyarrow"])
def test_store_commit_and_aggregate_freshness(tmp_path: Path, module):
    pytest.importorskip(module)
    from app.harmonization.aggregate_store import AggregateStore

    store = AggregateStore(tmp_path)
    scans = []
    store.stale_months = lambda: scans.append(1) or []  # type: ignore[method-assign]
    store.ensure_fresh("g1")
    store.ensure_fresh("g1")
    assert len(scans) == 1  # unchanged generation: no rescan
    store.ensure_fresh("g2")
    assert len(scans) == 2


def test_streamed_area_equals_the_in_memory_path(tmp_path: Path):
    """Month-by-month (bounded memory) must give exactly the in-memory results,
    including SP superseding NRT on a day that has both (SYNTHETIC TEST DATA)."""
    pytest.importorskip("pyarrow")
    import json

    from app.analytics.area_stream import stream_area
    from app.analytics.series import AreaBBox, monthly_series, select_cell_days
    from app.harmonization.aggregate_store import AggregateStore, MonthKey

    rows = [
        ("VIIRS", "NOAA-20", "NRT", date(2023, 1, 15), 15.10, 80.20, "D", 5.0, "nominal"),
        ("VIIRS", "NOAA-20", "SP", date(2023, 1, 15), 15.10, 80.20, "D", 3.0, "high"),
        ("VIIRS", "NOAA-20", "NRT", date(2023, 2, 2), 15.20, 80.30, "N", np.nan, "low"),
        ("VIIRS", "Suomi-NPP", "SP", date(2023, 2, 3), 15.30, 80.40, "D", 7.0, "nominal"),
        ("MODIS", "Aqua", "SP", date(2023, 1, 20), 16.00, 81.00, "D", 9.0, ""),
        ("MODIS", "Aqua", "SP", date(2023, 1, 20), 40.00, 10.00, "D", 9.0, ""),  # outside
    ]
    frame = pd.DataFrame(rows, columns=COLUMNS)
    store = AggregateStore(tmp_path)
    for (sensor, month), part in frame.groupby(
        [frame["sensor"], pd.to_datetime(frame["acquisition_date"]).dt.month]
    ):
        path = store.month_path(MonthKey(sensor, 2023, int(month)))
        path.parent.mkdir(parents=True, exist_ok=True)
        combine([aggregate(part)]).to_parquet(path, index=False)
    aoi = AreaBBox(79, 14, 82, 17)
    extent = json.dumps({"west": 70, "south": 10, "east": 90, "north": 25})
    coverage = [{"platform": p, "processing_status": "NRT", "extent_type": "bbox",
                 "extent_value": extent, "start_date": date(2023, 1, 1),
                 "end_date": date(2023, 2, 28)} for p in ("NOAA-20", "Suomi-NPP", "Aqua")]  # fmt: skip
    platforms = ["Terra", "Aqua", "Suomi-NPP", "NOAA-20"]
    start, end = date(2023, 1, 1), date(2023, 2, 28)

    streamed = stream_area(store, aoi, start, end, coverage, platforms)
    in_memory = monthly_series(store.read(), aoi, start, end, coverage, platforms)
    pd.testing.assert_frame_equal(streamed.series, in_memory, check_dtype=False)

    sel = select_cell_days(store.read(), aoi, start, end, coverage)
    totals = streamed.totals.set_index("platform")
    assert totals.loc["NOAA-20", "detections"] == 2  # SP replaced the NRT row on 15 Jan
    assert totals.loc["NOAA-20", "detections"] == int(
        sel[sel.platform == "NOAA-20"].detections.sum()
    )
    assert totals.loc["Aqua", "detections"] == 1  # the second Aqua row is outside the area
    assert totals.loc["NOAA-20", "first_date"] == date(2023, 1, 15)
    assert (
        totals.loc["NOAA-20", "confidence_high"] == 1
        and totals.loc["NOAA-20", "confidence_low"] == 1
    )
    assert date(2023, 1, 15) in streamed.sp_days["NOAA-20"]
    assert "Terra" not in totals.index  # no detections, no totals row
