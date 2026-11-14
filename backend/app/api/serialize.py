"""Convert pandas / NumPy values into strict JSON (no NaN, no numpy scalars).

Starlette's JSONResponse rejects NaN, and pandas produces NaN, pd.NA, NaT, Timestamps
and NumPy scalars. Missing values become ``null`` — never 0.
"""

from __future__ import annotations

import math
from datetime import date, datetime

import numpy as np
import pandas as pd


def to_jsonable(value):
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return [to_jsonable(r) for r in value.to_dict(orient="records")]
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value
