"""Export detections, the activity calendar and analytics for an area.

Run from the backend folder:

    python -m app.cli.export hotspots --bbox W,S,E,N --start D --end D --out hotspots.csv
        [--platform NOAA-20] [--confidence nominal --confidence high] [--daynight D]
        [--include-source-attributes] [--no-supersede]
    python -m app.cli.export calendar  --bbox ... --start ... --end ... --out cal.csv [--grid]
    python -m app.cli.export analytics --bbox ... --start ... --end ... --out analytics.json

Each export gets a ``<file>.provenance.json`` sidecar (area, period, filters, sources,
coverage, caveats).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from app.analytics.baselines import DEFAULT_MIN_HISTORY_YEARS
from app.analytics.calendar import build_calendar, calendar_grid
from app.analytics.distributions import platform_distributions
from app.analytics.observations import iter_observations
from app.analytics.series import (
    AreaBBox,
    drop_superseded,
    monthly_series,
    sp_days_by_platform,
)
from app.analytics.yearly import yearly_summary
from app.cli.area_summary import load_coverage
from app.cli.args import attach_negative_values
from app.core.config import Settings, get_settings
from app.exports.writers import export_hotspots, write_csv, write_json, write_provenance
from app.harmonization.aggregate_store import AggregateStore
from app.ingestion.firms_schema import Platform

PLATFORMS = [p.value for p in Platform]
METRICS = ("detections", "unique_cells", "cell_days")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FIRETRACE exports.")
    sub = parser.add_subparsers(dest="kind", required=True)
    for kind in ("hotspots", "calendar", "analytics"):
        p = sub.add_parser(kind)
        p.add_argument("--bbox", required=True, help="west,south,east,north")
        p.add_argument("--country", help="country name, if the area is a whole country")
        p.add_argument("--start", type=date.fromisoformat, required=True)
        p.add_argument("--end", type=date.fromisoformat, required=True)
        p.add_argument("--out", type=Path, required=True)
        p.add_argument("--platform", action="append", choices=PLATFORMS)
        if kind == "hotspots":
            p.add_argument("--confidence", action="append", choices=["low", "nominal", "high"])
            p.add_argument("--daynight", action="append", choices=["D", "N"])
            p.add_argument("--include-source-attributes", action="store_true")
            p.add_argument("--no-supersede", action="store_true",
                           help="keep NRT rows even where SP data exists")  # fmt: skip
        else:
            p.add_argument("--metric", choices=METRICS, default="detections")
            p.add_argument("--min-history-years", type=int, default=DEFAULT_MIN_HISTORY_YEARS)
        if kind == "calendar":
            p.add_argument("--grid", action="store_true", help="also write one grid per platform")
    return parser


def run(argv: list[str] | None = None, *, settings: Settings | None = None, out=print) -> int:
    raw = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(attach_negative_values(raw))
    if args.end < args.start:
        out("ERROR: --end is before --start")
        return 2
    settings = settings or get_settings()
    processed = Path(settings.processed_data_dir)
    aggregates = AggregateStore(processed, settings.grid_resolution_m)
    aggregates.build_stale()
    west, south, east, north = (float(v) for v in args.bbox.split(","))
    aoi = AreaBBox(west, south, east, north, country=args.country)
    coverage = load_coverage(settings)
    platforms = args.platform or PLATFORMS
    common = {
        "area": {"bbox": [west, south, east, north], "country": args.country},
        "period": {"start": args.start, "end": args.end},
        "platforms": platforms,
    }

    cell_days = aggregates.read(start=args.start, end=args.end)
    if args.kind == "hotspots":
        sp_days = None
        if not args.no_supersede and len(cell_days):
            in_area = cell_days[
                aoi.contains_points(cell_days["cell_lat"], cell_days["cell_lon"]).to_numpy()
            ]
            sp_days = sp_days_by_platform(in_area, aoi, args.start, args.end, coverage)
        stats = export_hotspots(
            iter_observations(processed, aoi, args.start, args.end),
            args.out,
            sp_days=sp_days,
            platforms=platforms,
            confidence=args.confidence,
            day_night=args.daynight,
            include_source_attributes=args.include_source_attributes,
        )
        write_provenance(
            args.out,
            {
                **common,
                "kind": "filtered hotspot detections",
                "filters": {
                    "confidence": args.confidence,
                    "day_night": args.daynight,
                    "nrt_superseded_by_sp": not args.no_supersede,
                },  # fmt: skip
                **stats,
            },
        )
        out(f"wrote {stats['rows']} detections to {args.out}")
        return 0

    series = monthly_series(cell_days, aoi, args.start, args.end, coverage, platforms)
    calendar = build_calendar(series, args.metric, args.min_history_years)
    details = {**common, "metric": args.metric, "min_history_years": args.min_history_years}

    if args.kind == "calendar":
        write_csv(calendar, args.out)
        write_provenance(args.out, {**details, "kind": "activity calendar (long format)",
                                    "states": sorted(calendar["state"].unique())})  # fmt: skip
        out(f"wrote {len(calendar)} calendar cells to {args.out}")
        if args.grid:
            for platform in platforms:
                grid_path = args.out.with_name(f"{args.out.stem}_{platform}_grid.csv")
                write_csv(calendar_grid(calendar, platform), grid_path)
                out(f"wrote {grid_path}")
        return 0

    observations = list(iter_observations(processed, aoi, args.start, args.end))
    detections = pd.concat(observations, ignore_index=True) if observations else pd.DataFrame()
    if len(detections) and len(cell_days):
        in_area = cell_days[
            aoi.contains_points(cell_days["cell_lat"], cell_days["cell_lon"]).to_numpy()
        ]
        detections = drop_superseded(
            detections, sp_days_by_platform(in_area, aoi, args.start, args.end, coverage)
        )
    if len(detections):
        detections = detections[detections["platform"].isin(platforms).to_numpy()]
    payload = {
        **details,
        "kind": "analytics",
        "status": "baselines and anomalies are EXPERIMENTAL",
        "yearly": yearly_summary(series, args.metric).to_dict(orient="records"),
        "distributions": platform_distributions(detections).to_dict(orient="records"),
        "calendar": calendar.to_dict(orient="records"),
        "monthly_series": series.to_dict(orient="records"),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.out, payload)
    write_provenance(args.out, {**details, "kind": "analytics JSON"})
    out(f"wrote analytics to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
