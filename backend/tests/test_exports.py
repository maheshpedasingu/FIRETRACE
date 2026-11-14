"""Export writer tests. All rows are SYNTHETIC TEST DATA."""

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from app.exports.writers import HOTSPOT_COLUMNS, export_hotspots, write_json, write_provenance
from app.ingestion.firms_schema import CANONICAL_COLUMNS


def frame(rows):
    base = {c: None for c in CANONICAL_COLUMNS}
    records = []
    for i, (platform, status, day, conf, dn) in enumerate(rows):
        records.append(
            base | {
                "observation_id": f"id{i}", "platform": platform, "processing_status": status,
                "acquisition_date": day, "confidence_class": conf, "day_night": dn,
                "latitude": 15.0, "longitude": 80.0, "frp_mw": 1.0 + i,
                "source_file": f"SYNTHETIC_{status}.csv", "source_checksum": f"sum-{status}",
                "source_attributes": "{}",
            }
        )  # fmt: skip
    return pd.DataFrame(records)


D1, D2 = date(2026, 7, 1), date(2026, 7, 2)
CHUNK_A = frame([("NOAA-20", "NRT", D1, "nominal", "D"), ("NOAA-20", "SP", D1, "nominal", "D")])
CHUNK_B = frame([("NOAA-20", "NRT", D2, "high", "N"), ("Aqua", "SP", D2, "low", "D")])


def read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def test_streamed_export_supersedes_nrt_and_records_sources(tmp_path: Path):
    out = tmp_path / "hotspots.csv"
    stats = export_hotspots([CHUNK_A, CHUNK_B], out, sp_days={"NOAA-20": {D1}})
    data = read(out)
    assert list(data.columns) == HOTSPOT_COLUMNS  # source_attributes excluded by default
    assert stats["rows"] == 3 and stats["nrt_rows_superseded_by_sp"] == 1
    assert stats["rows_by_platform"] == {"NOAA-20": 2, "Aqua": 1}
    assert {s["sha256"] for s in stats["source_files"]} == {"sum-NRT", "sum-SP"}
    assert not list(tmp_path.glob("*.partial"))


def test_filters_by_platform_confidence_and_daynight(tmp_path: Path):
    out = tmp_path / "f.csv"
    stats = export_hotspots([CHUNK_A, CHUNK_B], out, platforms=["NOAA-20"],
                            confidence=["high"], day_night=["N"])  # fmt: skip
    data = read(out)
    assert stats["rows"] == 1 and data.loc[0, "confidence_class"] == "high"


def test_empty_export_still_has_header(tmp_path: Path):
    out = tmp_path / "empty.csv"
    stats = export_hotspots([], out)
    assert stats["rows"] == 0
    assert out.read_text(encoding="utf-8").strip() == ",".join(HOTSPOT_COLUMNS)


def test_source_attributes_optional(tmp_path: Path):
    out = tmp_path / "full.csv"
    export_hotspots([CHUNK_A], out, include_source_attributes=True)
    assert "source_attributes" in read(out).columns


def test_provenance_and_json_have_no_nan(tmp_path: Path):
    out = tmp_path / "x.csv"
    out.write_text("a\n", encoding="utf-8")
    prov = write_provenance(out, {"period": {"start": D1}, "value": np.nan})
    payload = json.loads(prov.read_text(encoding="utf-8"))
    assert payload["value"] is None and payload["period"]["start"] == "2026-07-01"
    assert any("not individual fires" in c for c in payload["caveats"])
    j = tmp_path / "a.json"
    write_json(j, {"x": [1.0, float("nan")]})
    assert json.loads(j.read_text(encoding="utf-8")) == {"x": [1.0, None]}
