"""Yearly totals and year-over-year change per platform.

A year total is only reported as complete when all 12 months had complete coverage.
Year-over-year change is computed only between two complete years of the same platform;
otherwise it is left blank with the reason.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def yearly_summary(series: pd.DataFrame, metric: str = "detections") -> pd.DataFrame:
    rows = []
    for (platform, year), group in series.groupby(["platform", "year"], sort=True):
        complete = int((group["coverage_status"] == "complete").sum())
        months_with_data = int(group[metric].notna().sum())
        total = float(group[metric].sum()) if months_with_data else np.nan
        rows.append(
            {
                "platform": platform,
                "year": int(year),
                "complete_months": complete,
                "months_with_values": months_with_data,
                "total": total,
                "complete_year": complete == 12,
            }
        )
    table = pd.DataFrame(rows)
    if table.empty:
        return table
    changes, pct, notes = [], [], []
    for row in table.itertuples(index=False):
        prev = table[(table.platform == row.platform) & (table.year == row.year - 1)]
        if prev.empty:
            changes.append(np.nan), pct.append(np.nan), notes.append("no previous year")
        elif not (row.complete_year and bool(prev.complete_year.iloc[0])):
            changes.append(np.nan), pct.append(np.nan)
            notes.append("not computed: a year lacks complete coverage")
        else:
            before = float(prev.total.iloc[0])
            changes.append(row.total - before)
            pct.append((row.total - before) / before * 100 if before else np.nan)
            notes.append("")
    return table.assign(yoy_change=changes, yoy_change_pct=pct, yoy_note=notes)
