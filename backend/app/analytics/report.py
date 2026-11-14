"""Validation / anomaly report (JSON + Markdown) for one area and period."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import pandas as pd


def _clean(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _records(frame: pd.DataFrame) -> list[dict]:
    return [_clean(r) for r in frame.to_dict(orient="records")] if len(frame) else []


def build_report(
    *,
    area: dict,
    period: dict,
    metric: str,
    series: pd.DataFrame,
    target: pd.DataFrame,
    hai: pd.DataFrame,
    calibrations: list[dict],
    matching: list[dict],
    settings: dict,
) -> dict:
    coverage = (
        series.groupby(["platform", "coverage_status"]).size().unstack(fill_value=0)
        if len(series)
        else pd.DataFrame()
    )
    return {
        "title": "FIRETRACE harmonization and anomaly report",
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": "EXPERIMENTAL — methods validated only with synthetic test data",
        "area": area,
        "period": period,
        "metric": metric,
        "settings": settings,
        "coverage_months_by_platform": {
            p: {k: int(v) for k, v in row.items()} for p, row in coverage.iterrows()
        },
        "target_assessment": _records(target),
        "harmonized_index": _records(hai),
        "cross_sensor_calibration": [_clean(c) for c in calibrations],
        "detection_matching": [_clean(m) for m in matching],
        "monthly_series": _records(series),
        "limitations": [
            "Values are satellite detections or active 1 km cells, not fire incidents.",
            "Months without complete coverage are excluded from baselines; missing is not zero.",
            "Modified z uses median/MAD of earlier years of the same calendar month and platform.",
            "The harmonized activity index is an experimental anomaly score, not a calibrated "
            "fire count.",
            "Cross-sensor calibration is a single area-specific ratio; it may not transfer to "
            "other regions, biomes or years.",
            "Detection matching measures agreement where both sensors detected fire; FIRMS has "
            "no record of overpasses without fire, so it is not a detection probability.",
        ],
    }


def _fmt(value, digits: int = 2) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def to_markdown(report: dict) -> str:
    lines = [
        f"# {report['title']}",
        "",
        f"**Status:** {report['status']}  ",
        f"**Generated:** {report['generated_utc']}  ",
        f"**Area:** `{json.dumps(report['area'])}`  ",
        f"**Period:** {report['period']['start']} → {report['period']['end']}; "
        f"target month {report['period']['target']}  ",
        f"**Metric:** {report['metric']}",
        "",
        "## Coverage (months per platform)",
        "",
        "| Platform | complete | partial | missing |",
        "|---|---|---|---|",
    ]
    for platform, counts in report["coverage_months_by_platform"].items():
        lines.append(
            f"| {platform} | {counts.get('complete', 0)} | {counts.get('partial', 0)} | "
            f"{counts.get('missing', 0)} |"
        )
    lines += [
        "",
        "## Target month vs. each platform's own history",
        "",
        "| Platform | Value | Coverage | History years | Median | MAD | Modified z | "
        "Percentile | Result |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in report["target_assessment"]:
        result = r["label"] if r["status"] == "assessed" else f"not assessed ({r['status']})"
        lines.append(
            f"| {r['platform']} | {_fmt(r['value'], 0)} | {r['coverage_status']} | "
            f"{r['history_years']} | {_fmt(r['median'], 1)} | {_fmt(r['mad'], 1)} | "
            f"{_fmt(r['modified_z'])} | {_fmt(r['percentile_rank'], 0)} | {result} |"
        )
    lines += ["", "## Harmonized activity index (experimental)", ""]
    target = report["period"]["target"]
    hai_rows = [h for h in report["harmonized_index"] if f"{h['year']}-{h['month']:02d}" == target]
    if hai_rows and hai_rows[0]["status"] == "experimental":
        h = hai_rows[0]
        lines.append(
            f"HAI {_fmt(h['hai'])} from sensors {h['sensors']} (platforms {h['platforms']}); "
            f"MODIS z {_fmt(h['modis_z'])}, VIIRS z {_fmt(h['viirs_z'])}, "
            f"disagreement {_fmt(h['sensor_disagreement'])}."
        )
    else:
        lines.append("Unavailable: no platform could be assessed for the target month.")
    lines += [
        "",
        "## Cross-sensor calibration (experimental)",
        "",
        "| MODIS | VIIRS | Status | Train / validation months | Factor | Bias | MAE | RMSE | "
        "log r | Note |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in report["cross_sensor_calibration"]:
        lines.append(
            f"| {c['modis_platform']} | {c['viirs_platform']} | {c['status']} | "
            f"{c['n_train']} / {c['n_validation']} | {_fmt(c['scale_factor'], 3)} | "
            f"{_fmt(c['bias'])} | {_fmt(c['mae'])} | {_fmt(c['rmse'])} | "
            f"{_fmt(c['log_correlation'])} | {c['reason']} |"
        )
    lines += [
        "",
        "## Detection matching (experimental)",
        "",
        "| MODIS | VIIRS | MODIS dets | VIIRS dets | Matched | Fraction | FRP pairs | "
        "Median FRP ratio V/M | FRP Spearman |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m in report["detection_matching"]:
        lines.append(
            f"| {m['modis_platform']} | {m['viirs_platform']} | {m['modis_detections']} | "
            f"{m['viirs_detections']} | {m['modis_matched']} | {_fmt(m['match_fraction'], 3)} | "
            f"{m['frp_pairs']} | {_fmt(m['frp_median_ratio_viirs_to_modis'])} | "
            f"{_fmt(m['frp_spearman'])} |"
        )
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"
