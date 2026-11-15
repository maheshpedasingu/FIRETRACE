"""Baselines, anomalies, harmonized index and cross-sensor diagnostics for an area.

Run from the backend folder:

    python -m app.cli.anomaly_report --bbox 76.7,12.6,84.8,19.9 \
        --start 2012-01-01 --end 2026-10-31 --target 2026-10

Writes JSON and Markdown to data/processed/reports/. Everything is per platform; months
without complete coverage are never treated as zero. Results are experimental.
"""

from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from app.analytics.area_stream import stream_area
from app.analytics.baselines import DEFAULT_MIN_HISTORY_YEARS, assess, assess_all, harmonized_index
from app.analytics.report import build_report, to_markdown
from app.analytics.series import AreaBBox
from app.cli.area_summary import load_coverage
from app.cli.args import attach_negative_values
from app.core.config import Settings, get_settings
from app.harmonization.aggregate_store import AggregateStore
from app.harmonization.cross_sensor import match_detections, monthly_calibration
from app.ingestion.firms_schema import Platform
from app.storage.files import visible_parquet_files

MODIS = [Platform.TERRA.value, Platform.AQUA.value]
VIIRS = [Platform.SUOMI_NPP.value, Platform.NOAA_20.value, Platform.NOAA_21.value]
METRICS = ("detections", "unique_cells", "cell_days")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="FIRETRACE anomaly and validation report.")
    p.add_argument("--bbox", required=True, help="west,south,east,north")
    p.add_argument("--country", help="country name, if the AOI is a whole country")
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.add_argument("--target", help="YYYY-MM to assess (default: last month of the period)")
    p.add_argument("--metric", choices=METRICS, default="detections")
    p.add_argument("--min-history-years", type=int, default=DEFAULT_MIN_HISTORY_YEARS)
    p.add_argument("--validation-years", help="comma-separated years held out for validation")
    p.add_argument("--tolerance-minutes", type=float, default=15.0)
    p.add_argument("--match-months", type=int, default=12, help="months of detections to match")
    return p


def default_validation_years(series: pd.DataFrame, a: str, b: str, n: int = 2) -> list[int]:
    def years(platform: str) -> set[int]:
        part = series[(series.platform == platform) & (series.coverage_status == "complete")]
        return set(part["year"].astype(int))

    overlap = sorted(years(a) & years(b))
    return overlap[-n:] if len(overlap) > n else []


def read_observations(processed: Path, aoi: AreaBBox, start: date, end: date, sensor: str):
    root = processed / "observations" / sensor
    columns = ["platform", "latitude", "longitude", "acquisition_datetime_utc", "frp_mw"]
    frames = []
    if root.is_dir():
        for path in visible_parquet_files(root):
            year, month = (int(x) for x in path.relative_to(root).parts[:2])
            if (year, month) < (start.year, start.month) or (year, month) > (end.year, end.month):
                continue
            frame = pd.read_parquet(path, columns=columns)
            frames.append(frame[aoi.contains_points(frame["latitude"], frame["longitude"])])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)


def run(argv: list[str] | None = None, *, settings: Settings | None = None, out=print) -> int:
    raw = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(attach_negative_values(raw))
    settings = settings or get_settings()
    processed = Path(settings.processed_data_dir)
    store = AggregateStore(processed, settings.grid_resolution_m)
    store.build_stale()

    west, south, east, north = (float(v) for v in args.bbox.split(","))
    aoi = AreaBBox(west, south, east, north, country=args.country)
    platforms = MODIS + VIIRS
    series = stream_area(
        store, aoi, args.start, args.end, load_coverage(settings), platforms
    ).series  # one aggregate month at a time (bounded memory)
    if args.target:
        ty, tm = (int(x) for x in args.target.split("-"))
    else:
        ty, tm = args.end.year, args.end.month
    target = pd.DataFrame(
        [assess(series, p, ty, tm, args.metric, args.min_history_years).__dict__ for p in platforms]
    )
    hai = harmonized_index(assess_all(series, args.metric, args.min_history_years))

    calibrations, matching = [], []
    match_start = date(ty, tm, 1)
    for _ in range(args.match_months - 1):
        match_start = date(match_start.year - (match_start.month == 1),
                           (match_start.month - 2) % 12 + 1, 1)  # fmt: skip
    match_end = date(ty, tm, calendar.monthrange(ty, tm)[1])
    modis_obs = read_observations(processed, aoi, match_start, match_end, "MODIS")
    viirs_obs = read_observations(processed, aoi, match_start, match_end, "VIIRS")
    for m in MODIS:
        for v in VIIRS:
            val_years = (
                [int(y) for y in args.validation_years.split(",")]
                if args.validation_years
                else default_validation_years(series, m, v)
            )
            calibrations.append(monthly_calibration(series, m, v, val_years, args.metric).as_dict())
            result = match_detections(
                modis_obs[modis_obs.platform == m],
                viirs_obs[viirs_obs.platform == v],
                args.tolerance_minutes,
                resolution_m=settings.grid_resolution_m,
            )
            matching.append({"modis_platform": m, "viirs_platform": v, **result})

    report = build_report(
        area={"bbox": [west, south, east, north], "country": args.country},
        period={
            "start": str(args.start),
            "end": str(args.end),
            "target": f"{ty}-{tm:02d}",
            "matching": f"{match_start}..{match_end}",
        },  # fmt: skip
        metric=args.metric,
        series=series,
        target=target,
        hai=hai,
        calibrations=calibrations,
        matching=matching,
        settings={
            "grid_resolution_m": settings.grid_resolution_m,
            "min_history_years": args.min_history_years,
            "tolerance_minutes": args.tolerance_minutes,
        },
    )
    out_dir = processed / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"report_{stamp}.json"
    md_path = out_dir / f"report_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
    for r in report["target_assessment"]:
        result = r["label"] if r["status"] == "assessed" else f"not assessed ({r['status']})"
        out(f"{r['platform']:<10} {ty}-{tm:02d} {args.metric}={r['value']} -> {result}")
    out(f"report: {md_path}")
    out(f"json:   {json_path}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
