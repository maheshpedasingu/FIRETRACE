"""Cell-day aggregation tests. Every observation here is SYNTHETIC TEST DATA."""

from datetime import date

import numpy as np
import pandas as pd

from app.harmonization.cell_days import CELL_DAY_COLUMNS, aggregate, combine


def obs(rows):
    columns = ["sensor", "platform", "processing_status", "acquisition_date", "latitude",
               "longitude", "day_night", "frp_mw", "confidence_class"]  # fmt: skip
    return pd.DataFrame(rows, columns=columns)


D1, D2 = date(2023, 1, 15), date(2023, 1, 16)
SYNTHETIC = obs(
    [
        # two NOAA-20 detections ~50 m apart: same 1 km cell, same day
        ("VIIRS", "NOAA-20", "NRT", D1, 15.1000, 80.2000, "D", 5.0, "nominal"),
        ("VIIRS", "NOAA-20", "NRT", D1, 15.1003, 80.2003, "N", np.nan, "high"),
        # same place, next day
        ("VIIRS", "NOAA-20", "NRT", D2, 15.1000, 80.2000, "D", 2.0, "low"),
        # same place and day, different platform and processing status
        ("VIIRS", "Suomi-NPP", "NRT", D1, 15.1000, 80.2000, "D", 1.0, "nominal"),
        ("VIIRS", "NOAA-20", "SP", D1, 15.1000, 80.2000, "D", 3.0, "nominal"),
        # MODIS, far away (Southern Hemisphere, west of Greenwich)
        ("MODIS", "Aqua", "SP", D1, -8.0, -55.0, "", 10.0, ""),
    ]
)


def test_detections_and_cells_are_separated_by_platform_status_day():
    result = combine([aggregate(SYNTHETIC)])
    assert list(result.columns) == CELL_DAY_COLUMNS
    assert len(result) == 5  # 6 detections → 5 cell-days
    n20_nrt_d1 = result[
        (result.platform == "NOAA-20") & (result.processing_status == "NRT")
        & (result.acquisition_date == D1)
    ]  # fmt: skip
    row = n20_nrt_d1.iloc[0]
    assert (row.detections, row.day_detections, row.night_detections) == (2, 1, 1)
    assert (row.confidence_nominal, row.confidence_high) == (1, 1)
    assert row.frp_count == 1 and row.frp_sum_mw == 5.0 and row.frp_max_mw == 5.0


def test_missing_frp_and_daynight_are_not_turned_into_values():
    result = combine([aggregate(SYNTHETIC)])
    aqua = result[result.platform == "Aqua"].iloc[0]
    assert aqua.unknown_daynight_detections == 1 and aqua.confidence_missing == 1
    only_nan = combine([aggregate(SYNTHETIC.iloc[[1]])]).iloc[0]
    assert only_nan.frp_count == 0 and np.isnan(only_nan.frp_max_mw)


def test_combining_partial_aggregates_equals_aggregating_everything():
    whole = combine([aggregate(SYNTHETIC)])
    split = combine([aggregate(SYNTHETIC.iloc[:2]), aggregate(SYNTHETIC.iloc[2:])])
    pd.testing.assert_frame_equal(whole, split)


def test_cell_centres_are_within_a_cell_of_the_detections():
    result = combine([aggregate(SYNTHETIC)])
    aqua = result[result.platform == "Aqua"].iloc[0]
    assert abs(aqua.cell_lat - (-8.0)) < 0.01 and abs(aqua.cell_lon - (-55.0)) < 0.01


def test_empty_input():
    assert combine([aggregate(SYNTHETIC.iloc[:0])]).empty
