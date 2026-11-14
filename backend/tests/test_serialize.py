"""JSON serialization tests. Values are SYNTHETIC TEST DATA."""

import json
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from app.api.serialize import to_jsonable


def test_missing_values_become_null_not_zero():
    payload = {"a": float("nan"), "b": pd.NA, "c": pd.NaT, "d": np.float64("nan"), "e": None}
    assert to_jsonable(payload) == dict.fromkeys("abcde")


def test_numpy_and_time_types():
    out = to_jsonable(
        {"i": np.int64(3), "f": np.float32(1.5), "b": np.bool_(True),
         "d": date(2026, 11, 14), "t": pd.Timestamp("2026-11-14T07:39", tz="UTC"),
         "dt": datetime(2026, 11, 14, tzinfo=UTC)}
    )  # fmt: skip
    assert out == {"i": 3, "f": 1.5, "b": True, "d": "2026-11-14",
                   "t": "2026-11-14T07:39:00+00:00", "dt": "2026-11-14T00:00:00+00:00"}  # fmt: skip
    json.dumps(out, allow_nan=False)


def test_naive_database_datetimes_are_labelled_utc():
    assert to_jsonable(datetime(2026, 11, 14, 7, 19, 51)) == "2026-11-14T07:19:51+00:00"


def test_dataframe_with_nullable_int_and_nan():
    frame = pd.DataFrame({"x": pd.array([1, None], dtype="Int64"), "y": [np.nan, 2.0]})
    assert to_jsonable(frame) == [{"x": 1, "y": None}, {"x": None, "y": 2.0}]
