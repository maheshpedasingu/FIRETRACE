"""CSV / JSON exports with provenance.

Every export ``X`` gets a sidecar ``X.provenance.json`` describing the area, period,
filters, data sources and caveats, so the CSV itself stays a plain table that any tool
can read. Hotspot exports are streamed file by file: memory use does not depend on the
size of the area or period.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from app.analytics.series import drop_superseded
from app.ingestion.firms_schema import CANONICAL_COLUMNS

HOTSPOT_COLUMNS = [c for c in CANONICAL_COLUMNS if c != "source_attributes"]

CAVEATS = [
    "Rows are satellite active-fire detections, not individual fires.",
    "FRP is fire radiative power of a detected pixel (MW), not burned area.",
    "MODIS (~1 km) and VIIRS (375 m) detections are listed separately by platform and "
    "must not be added without sensor-aware normalization.",
    "Absence of rows does not mean absence of fire unless the area and dates were covered "
    "by an import; see coverage in this file.",
]


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, float) and math.isnan(value):
        return None
    return str(value)


def _clean(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".partial")
    tmp.write_text(json.dumps(_clean(payload), indent=2, default=_json_default), encoding="utf-8")
    os.replace(tmp, path)


def write_provenance(export_path: Path, details: dict) -> Path:
    path = export_path.with_name(export_path.name + ".provenance.json")
    write_json(
        path,
        {
            "export": export_path.name,
            "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "generator": "FIRETRACE",
            **details,
            "caveats": CAVEATS,
        },
    )
    return path


def export_hotspots(
    frames: Iterable[pd.DataFrame],
    out_path: Path,
    *,
    sp_days: dict[str, set[date]] | None = None,
    platforms: list[str] | None = None,
    confidence: list[str] | None = None,
    day_night: list[str] | None = None,
    include_source_attributes: bool = False,
) -> dict:
    """Stream filtered detections to CSV. Returns counts for the provenance file."""
    columns = list(CANONICAL_COLUMNS) if include_source_attributes else HOTSPOT_COLUMNS
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".partial")
    rows = superseded = 0
    by_platform: dict[str, int] = {}
    sources: dict[str, str] = {}
    with tmp.open("w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(columns) + "\n")
        for frame in frames:
            if sp_days:
                before = len(frame)
                frame = drop_superseded(frame, sp_days)
                superseded += before - len(frame)
            if platforms:
                frame = frame[frame["platform"].isin(platforms).to_numpy()]
            if confidence:
                frame = frame[frame["confidence_class"].isin(confidence).to_numpy()]
            if day_night:
                frame = frame[frame["day_night"].isin(day_night).to_numpy()]
            if frame.empty:
                continue
            frame[columns].to_csv(handle, header=False, index=False, lineterminator="\n")
            rows += len(frame)
            for platform, n in frame["platform"].value_counts().items():
                by_platform[str(platform)] = by_platform.get(str(platform), 0) + int(n)
            for name, checksum in (
                frame[["source_file", "source_checksum"]].drop_duplicates().itertuples(index=False)
            ):
                sources[str(checksum)] = str(name)
    os.replace(tmp, out_path)
    return {
        "rows": rows,
        "rows_by_platform": by_platform,
        "nrt_rows_superseded_by_sp": superseded,
        "source_files": [{"name": n, "sha256": c} for c, n in sorted(sources.items())],
        "columns": columns,
    }


def write_csv(frame: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".partial")
    frame.to_csv(tmp, index=False, lineterminator="\n")
    os.replace(tmp, out_path)
