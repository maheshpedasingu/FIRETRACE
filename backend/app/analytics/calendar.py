"""Burning activity calendar: years × months per platform, with explicit cell states.

Cell states (never collapsed into a single number):
- ``value``       complete coverage, at least one detection
- ``zero``        complete coverage, no detections (a real zero)
- ``partial``     some days covered; the value covers only those days
- ``uncovered``   detections exist but no import covered the whole area (value is a
                  lower bound; zero cannot be inferred)
- ``missing``     no coverage and no detections — unknown, not zero

An anomaly (modified z and label) is attached where the baseline allows it.
"""

from __future__ import annotations

import pandas as pd

from app.analytics.baselines import DEFAULT_MIN_HISTORY_YEARS, assess_all

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def cell_state(coverage_status: str, value: float) -> str:
    has_value = pd.notna(value)
    if coverage_status == "complete":
        return "value" if has_value and value > 0 else "zero"
    if coverage_status == "partial":
        return "partial"
    return "uncovered" if has_value and value > 0 else "missing"


def build_calendar(
    series: pd.DataFrame,
    metric: str = "detections",
    min_history_years: int = DEFAULT_MIN_HISTORY_YEARS,
) -> pd.DataFrame:
    """Long calendar table: one row per platform × year × month."""
    if series.empty:
        return pd.DataFrame(
            columns=["platform", "year", "month", "state", "value", "coverage_status",
                     "days_covered", "days_in_range", "modified_z", "anomaly", "anomaly_status"]
        )  # fmt: skip
    assessed = assess_all(series, metric, min_history_years)[
        ["platform", "year", "month", "modified_z", "label", "status"]
    ]
    table = series.merge(assessed, on=["platform", "year", "month"], how="left")
    table["state"] = [
        cell_state(c, v) for c, v in zip(table["coverage_status"], table[metric], strict=True)
    ]
    return pd.DataFrame(
        {
            "platform": table["platform"],
            "year": table["year"].astype(int),
            "month": table["month"].astype(int),
            "state": table["state"],
            "value": table[metric],
            "coverage_status": table["coverage_status"],
            "days_covered": table["days_covered"].astype(int),
            "days_in_range": table["days_in_range"].astype(int),
            "modified_z": table["modified_z"],
            "anomaly": table["label"],
            "anomaly_status": table["status"],
        }
    )


def calendar_grid(calendar: pd.DataFrame, platform: str) -> pd.DataFrame:
    """Wide view for one platform: rows = years, columns = Jan..Dec, cells = 'state:value'."""
    part = calendar[calendar["platform"] == platform]
    if part.empty:
        return pd.DataFrame(columns=["year", *MONTH_NAMES])

    def label(row) -> str:
        if row.state in ("missing",):
            return "missing"
        value = "" if pd.isna(row.value) else f"{row.value:g}"
        return f"{row.state}:{value}"

    cells = part.assign(cell=[label(r) for r in part.itertuples(index=False)])
    grid = cells.pivot(index="year", columns="month", values="cell")
    # Months absent from the requested range come back as float NaN columns; cast to
    # object before filling with text (pandas 4 will refuse str fill on float columns).
    grid = grid.reindex(columns=range(1, 13)).astype(object)
    grid.columns = MONTH_NAMES
    return grid.where(grid.notna(), "outside range").reset_index()
