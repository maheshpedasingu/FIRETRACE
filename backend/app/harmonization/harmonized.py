"""Harmonized burning activity calendar: one series in a single reference unit.

The per-platform calendars stay the primary, unaltered record. This module builds ONE
additional series in which every month is expressed in the unit of a reference sensor,
so MODIS (from 2000) and VIIRS (from 2012) form one continuous record.

Method (documented in docs/science/harmonization.md, "Harmonized calendar"):

1. Sources. Each platform is a source, plus "MODIS (Terra+Aqua)", the sum of Terra and
   Aqua for months where BOTH are completely covered (the MCD14ML-style combined record).
2. Reference unit.
   - ``modis``: MODIS (Terra+Aqua) detections — the longest record (default).
   - ``viirs``: Suomi-NPP VIIRS detections — the higher-resolution record.
3. Conversion factors. For each other source, a single area-specific factor
   ``reference ≈ factor × source`` is fitted as a ratio of sums over months where both
   the source and the reference are completely covered (training years), then evaluated
   on held-out validation years (every third overlap year): bias, MAE, RMSE, relative
   RMSE and log correlation in reference units. Too little overlap → no factor; months
   that would need it are left unharmonized (reported, never guessed).
4. Month value. For every month the first source in a fixed priority order that has
   COMPLETE coverage (and a factor) supplies the value, converted to reference units.
   If no source is complete, the first partially covered source gives a ``partial``
   value; detections without coverage give an ``uncovered`` lower bound; otherwise the
   month is ``missing`` (unknown, never zero).
5. Uncertainty. Reference months have none from conversion; converted months carry the
   factor's relative validation RMSE.
6. Anomalies. The harmonized series is compared with the same calendar month in other
   years (median, MAD, modified z), exactly as for single platforms. Because months from
   different sources are mixed, this is labelled experimental.

It is a statistical bridge, not a physical correction: MODIS and VIIRS differ in pixel
size, sensitivity and overpass time, and a constant factor cannot capture every
seasonal or fire-type difference. The fit diagnostics are always returned with it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from app.analytics.baselines import DEFAULT_MIN_HISTORY_YEARS, assess_all
from app.analytics.calendar import cell_state

MODIS_COMBINED = "MODIS (Terra+Aqua)"
HARMONIZED = "Harmonized"

REFERENCES: dict[str, dict] = {
    "modis": {
        "reference": MODIS_COMBINED,
        "unit": "MODIS (Terra+Aqua)-equivalent",
        "priority": [MODIS_COMBINED, "Aqua", "Terra", "Suomi-NPP", "NOAA-20", "NOAA-21"],
    },
    "viirs": {
        "reference": "Suomi-NPP",
        "unit": "Suomi-NPP VIIRS-equivalent",
        "priority": ["Suomi-NPP", "NOAA-20", "NOAA-21", MODIS_COMBINED, "Aqua", "Terra"],
    },
}

DEFAULT_MIN_TRAIN_MONTHS = 12
DEFAULT_MIN_VALIDATION_MONTHS = 6


@dataclass(frozen=True)
class ConversionFit:
    source: str
    reference: str
    status: str  # reference | estimated | unavailable
    reason: str
    factor: float  # reference ≈ factor × source
    n_train: int
    n_validation: int
    train_years: str
    validation_years: str
    bias: float  # mean(predicted − observed reference), validation months
    mae: float
    rmse: float
    relative_rmse: float  # rmse / mean observed reference, validation months
    log_correlation: float

    def as_dict(self) -> dict:
        return asdict(self)


def with_modis_combined(series: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Add MODIS (Terra+Aqua) rows: a sum only where both platforms are complete."""
    terra = series[series["platform"] == "Terra"].set_index(["year", "month"])
    aqua = series[series["platform"] == "Aqua"].set_index(["year", "month"])
    if terra.empty or aqua.empty:
        return series
    # merge(suffixes=...) instead of join(lsuffix/rsuffix), deprecated in pandas 3.1.
    both = terra.merge(aqua, how="inner", left_index=True, right_index=True, suffixes=("_t", "_a"))
    rows = []
    for (year, month), r in both.iterrows():
        complete = r["coverage_status_t"] == "complete" and r["coverage_status_a"] == "complete"
        if complete:
            status = "complete"
        elif "missing" == r["coverage_status_t"] == r["coverage_status_a"]:
            status = "missing"
        else:
            status = "partial"
        t, a = r[f"{metric}_t"], r[f"{metric}_a"]
        value = np.nan if pd.isna(t) and pd.isna(a) else float(np.nansum([t, a]))
        rows.append(
            {
                "platform": MODIS_COMBINED,
                "year": int(year),
                "month": int(month),
                "days_in_range": int(r["days_in_range_t"]),
                "days_covered": int(min(r["days_covered_t"], r["days_covered_a"])),
                "coverage_status": status,
                metric: value,
            }
        )
    return pd.concat([series, pd.DataFrame(rows)], ignore_index=True)


def validation_years(years: list[int]) -> list[int]:
    """Every third overlap year (2nd, 5th, ...): spread over the record, deterministic."""
    ordered = sorted(years)
    return [y for i, y in enumerate(ordered) if i % 3 == 1]


def fit_conversion(
    series: pd.DataFrame,
    source: str,
    reference: str,
    metric: str = "detections",
    min_train: int = DEFAULT_MIN_TRAIN_MONTHS,
    min_validation: int = DEFAULT_MIN_VALIDATION_MONTHS,
) -> ConversionFit:
    nan = float("nan")
    if source == reference:
        return ConversionFit(source, reference, "reference", "reference unit", 1.0,
                             0, 0, "", "", 0.0, 0.0, 0.0, 0.0, nan)  # fmt: skip

    def complete(platform: str) -> pd.DataFrame:
        part = series[(series["platform"] == platform) & (series["coverage_status"] == "complete")]
        return part[["year", "month", metric]].rename(columns={metric: platform})

    pairs = complete(source).merge(complete(reference), on=["year", "month"]).dropna()
    held_out = validation_years(sorted(pairs["year"].unique().tolist()))
    is_val = pairs["year"].isin(held_out)
    train, val = pairs[~is_val], pairs[is_val]
    train_years = ",".join(str(y) for y in sorted(train["year"].unique()))
    val_years = ",".join(str(y) for y in sorted(val["year"].unique()))

    def unavailable(reason: str) -> ConversionFit:
        return ConversionFit(source, reference, "unavailable", reason, nan, len(train),
                             len(val), train_years, val_years, nan, nan, nan, nan, nan)  # fmt: skip

    if len(train) < min_train or len(val) < min_validation:
        return unavailable(
            f"needs ≥{min_train} training and ≥{min_validation} validation months where both "
            f"are completely covered; have {len(train)} and {len(val)}"
        )
    source_sum = float(train[source].sum())
    if source_sum == 0:
        return unavailable(f"no {source} detections in the training months")
    factor = float(train[reference].sum()) / source_sum
    predicted = factor * val[source].astype(float)
    observed = val[reference].astype(float)
    residual = predicted - observed
    rmse = float(np.sqrt((residual**2).mean()))
    mean_obs = float(observed.mean())
    corr = (
        float(np.corrcoef(np.log1p(predicted), np.log1p(observed))[0, 1])
        if len(val) > 2 and predicted.std() > 0 and observed.std() > 0
        else nan
    )
    return ConversionFit(
        source,
        reference,
        "estimated",
        "ratio of sums on training years; evaluated on held-out validation years",
        factor,
        len(train),
        len(val),
        train_years,
        val_years,
        float(residual.mean()),
        float(residual.abs().mean()),
        rmse,
        rmse / mean_obs if mean_obs > 0 else nan,
        corr,
    )


def harmonize(
    series: pd.DataFrame,
    reference: str = "modis",
    metric: str = "detections",
    min_history_years: int = DEFAULT_MIN_HISTORY_YEARS,
    min_train: int = DEFAULT_MIN_TRAIN_MONTHS,
    min_validation: int = DEFAULT_MIN_VALIDATION_MONTHS,
) -> dict:
    """Harmonized calendar cells plus the conversion fits that produced them."""
    if reference not in REFERENCES:
        raise ValueError(f"reference must be one of {sorted(REFERENCES)}")
    spec = REFERENCES[reference]
    ref_name = spec["reference"]
    full = with_modis_combined(series, metric) if not series.empty else series
    present = set(full["platform"]) if not full.empty else set()
    priority = [p for p in spec["priority"] if p in present]
    fits = {
        p: fit_conversion(full, p, ref_name, metric, min_train, min_validation) for p in priority
    }
    usable = [p for p in priority if fits[p].status in ("reference", "estimated")]

    cells = []
    if not full.empty:
        indexed = {(r.platform, r.year, r.month): r for r in full.itertuples(index=False)}
        months = sorted(
            {(int(y), int(m)) for y, m in zip(full["year"], full["month"], strict=True)}
        )
        for year, month in months:
            rows = [(p, indexed.get((p, year, month))) for p in usable]
            rows = [(p, r) for p, r in rows if r is not None]
            pick = next((pr for pr in rows if pr[1].coverage_status == "complete"), None)
            if pick is None:
                pick = next((pr for pr in rows if pr[1].coverage_status == "partial"), None)
            if pick is None:
                pick = next(
                    (pr for pr in rows if pd.notna(getattr(pr[1], metric))
                     and getattr(pr[1], metric) > 0),
                    None,
                )  # fmt: skip
            if pick is None:
                any_rows = [(p, indexed.get((p, year, month))) for p in priority]
                with_data = [p for p, r in any_rows if _has_data(r, metric)]
                note = (
                    f"data from {', '.join(with_data)} but no conversion factor to "
                    f"{ref_name} (not enough overlap months)"
                    if with_data
                    else "no imported data"
                )
                sample = next((r for _, r in any_rows if r is not None), None)
                cells.append(_cell(year, month, None, None, sample, metric, None, note))
                continue
            platform, row = pick
            note = (
                "reference sensor"
                if fits[platform].status == "reference"
                else (f"converted from {platform} × {fits[platform].factor:.3g}")
            )
            cells.append(
                _cell(year, month, platform, fits[platform], row, metric, row.coverage_status, note)
            )

    table = pd.DataFrame(cells, columns=CELL_COLUMNS)
    if not table.empty:
        assessed = assess_all(
            table.assign(platform=HARMONIZED, value=table["value"].astype(float)),
            "value",
            min_history_years,
        )[["year", "month", "modified_z", "label", "status"]]
        table = table.drop(columns=["modified_z", "anomaly", "anomaly_status"]).merge(
            assessed.rename(columns={"label": "anomaly", "status": "anomaly_status"}),
            on=["year", "month"],
            how="left",
        )[CELL_COLUMNS]
    return {
        "status": "EXPERIMENTAL",
        "reference": reference,
        "reference_source": ref_name,
        "unit": f"{spec['unit']} {metric.replace('_', ' ')}",
        "metric": metric,
        "priority": spec["priority"],
        "fits": [fits[p].as_dict() for p in priority],
        "cells": table,
    }


def _has_data(row, metric: str) -> bool:
    if row is None:
        return False
    value = getattr(row, metric)
    return row.coverage_status != "missing" or (pd.notna(value) and value > 0)


CELL_COLUMNS = [
    "platform", "year", "month", "state", "value", "coverage_status", "days_covered",
    "days_in_range", "source", "source_value", "factor", "relative_uncertainty",
    "converted", "note", "modified_z", "anomaly", "anomaly_status",
]  # fmt: skip


def _cell(year, month, platform, fit, row, metric, coverage_status, note: str) -> dict:
    nan = float("nan")
    if platform is None:
        return {
            "platform": HARMONIZED, "year": year, "month": month, "state": "missing",
            "value": nan, "coverage_status": "missing",
            "days_covered": 0, "days_in_range": int(row.days_in_range) if row is not None else 0,
            "source": None, "source_value": nan, "factor": nan,
            "relative_uncertainty": nan, "converted": False, "note": note,
            "modified_z": nan, "anomaly": None, "anomaly_status": None,
        }  # fmt: skip
    raw = getattr(row, metric)
    raw = float(raw) if pd.notna(raw) else nan
    value = raw * fit.factor if pd.notna(raw) else nan
    converted = fit.status == "estimated"
    # complete/partial/missing keep their meaning; detections without coverage are a
    # lower bound ("uncovered"), exactly as in the per-platform calendar.
    status = coverage_status if coverage_status in ("complete", "partial") else "missing"
    return {
        "platform": HARMONIZED,
        "year": year,
        "month": month,
        "state": cell_state(status, value),
        "value": round(value, 1) if pd.notna(value) else nan,
        "coverage_status": status,
        "days_covered": int(row.days_covered),
        "days_in_range": int(row.days_in_range),
        "source": platform,
        "source_value": raw,
        "factor": fit.factor,
        "relative_uncertainty": fit.relative_rmse if converted else 0.0,
        "converted": converted,
        "note": note,
        "modified_z": nan,
        "anomaly": None,
        "anomaly_status": None,
    }
