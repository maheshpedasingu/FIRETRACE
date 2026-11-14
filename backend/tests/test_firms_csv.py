"""Tests for the FIRMS CSV parser.

ALL DATA IN THIS FILE IS SYNTHETIC TEST DATA. The rows imitate the documented FIRMS
column layout but are invented values; they are not NASA observations.
"""

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.ingestion.firms_csv import (
    FirmsFormatError,
    SourceContext,
    iter_csv_chunks,
    iter_firms_file,
    parse_version,
)
from app.ingestion.firms_schema import CANONICAL_COLUMNS, Platform, ProcessingStatus, Sensor

# --- SYNTHETIC TEST DATA ---------------------------------------------------------------

SYNTHETIC_MODIS_CSV = """latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type
-8.1234,-55.4321,330.5,1.2,1.1,2019-08-20,1745,A,MODIS,85,6.1,300.1,45.2,D,0
61.5000,150.2500,315.0,1.0,1.0,2021-07-01,5,T,MODIS,29,6.1NRT,290.0,12.0,N,
-33.8000,150.9000,340.0,2.1,1.4,2019-12-31,0310,Terra,MODIS,30,6.1,301.0,120.5,D,0
"""

SYNTHETIC_VIIRS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
9.12345,2.54321,340.1,0.39,0.36,2023-01-15,1302,N,VIIRS,n,2.0NRT,295.2,5.4,D
-16.50000,179.95000,330.0,0.4,0.4,2023-03-02,2359,N20,VIIRS,h,2,290.0,10.1,N
65.00000,-179.90000,310.0,0.5,0.4,2024-06-30,0001,N21,VIIRS,l,2.0URT,280.0,,N
"""

SYNTHETIC_BAD_ROWS_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
95.0,10.0,340,0.4,0.4,2023-01-15,1200,N,VIIRS,n,2.0NRT,290,5,D
10.0,181.0,340,0.4,0.4,2023-01-15,1200,N,VIIRS,n,2.0NRT,290,5,D
10.0,10.0,340,0.4,0.4,2023-02-30,1200,N,VIIRS,n,2.0NRT,290,5,D
10.0,10.0,340,0.4,0.4,2023-01-15,2460,N,VIIRS,n,2.0NRT,290,5,D
10.0,10.0,340,0.4,0.4,2023-01-15,1200,X9,VIIRS,n,2.0NRT,290,5,D
10.0,10.0,340,0.4,0.4,2023-01-15,1200,N,VIIRS,maybe,2.0NRT,290,5,D
10.0,10.0,340,0.4,0.4,2023-01-15,1200,N,VIIRS,n,2.0NRT,290,-3,D
10.0,10.0,340,0.4,0.4,2023-01-15,1200,N,VIIRS,n,2.0NRT,290,5,Q
12.0,12.0,340,0.4,0.4,2023-01-15,1200,N,VIIRS,n,2.0NRT,290,5,D
"""

# ---------------------------------------------------------------------------------------


def _context(**overrides) -> SourceContext:
    base = dict(
        source_file="SYNTHETIC_TEST_DATA.csv",
        source_checksum="0" * 64,
        ingestion_timestamp=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(overrides)
    return SourceContext(**base)


def _parse(text: str, chunk_rows: int = 1000, **ctx) -> tuple[pd.DataFrame, pd.DataFrame]:
    chunks = list(iter_csv_chunks(io.BytesIO(text.encode()), _context(**ctx), chunk_rows))
    valid = pd.concat([c.valid for c in chunks], ignore_index=True)
    invalid = pd.concat([c.invalid for c in chunks], ignore_index=True)
    return valid, invalid


def test_modis_rows_map_to_canonical_schema():
    valid, invalid = _parse(SYNTHETIC_MODIS_CSV)
    assert invalid.empty
    assert list(valid.columns) == list(CANONICAL_COLUMNS)
    assert set(valid["sensor"]) == {"MODIS"}
    assert list(valid["platform"]) == ["Aqua", "Terra", "Terra"]
    assert list(valid["product"]) == ["MYD14", "MOD14", "MOD14"]


def test_modis_confidence_kept_raw_and_classified_at_documented_thresholds():
    valid, _ = _parse(SYNTHETIC_MODIS_CSV)
    assert list(valid["confidence_raw"]) == ["85", "29", "30"]
    assert list(valid["confidence_class"]) == ["high", "low", "nominal"]


def test_viirs_platforms_and_confidence_letters():
    valid, invalid = _parse(SYNTHETIC_VIIRS_CSV)
    assert invalid.empty
    assert list(valid["platform"]) == ["Suomi-NPP", "NOAA-20", "NOAA-21"]
    assert list(valid["product"]) == ["VNP14IMG", "VJ114IMG", "VJ214IMG"]
    assert list(valid["confidence_raw"]) == ["n", "h", "l"]
    assert list(valid["confidence_class"]) == ["nominal", "high", "low"]


def test_time_parsing_handles_missing_leading_zeros_and_is_utc():
    valid, _ = _parse(SYNTHETIC_MODIS_CSV)
    assert valid.loc[1, "acquisition_time_utc"] == "00:05"
    ts = valid.loc[0, "acquisition_datetime_utc"]
    assert ts == pd.Timestamp("2019-08-20 17:45", tz="UTC")


def test_processing_status_and_collection_from_version():
    valid, _ = _parse(SYNTHETIC_VIIRS_CSV)
    assert list(valid["processing_status"]) == ["NRT", "SP", "URT"]
    assert list(valid["collection"]) == ["2", "2", "2"]
    assert list(valid["collection_version"]) == ["2.0NRT", "2", "2.0URT"]


@pytest.mark.parametrize(
    ("version", "sensor", "expected"),
    [
        ("6.1NRT", Sensor.MODIS, ("6.1", ProcessingStatus.NRT)),
        ("6.1", Sensor.MODIS, ("6.1", ProcessingStatus.SP)),
        ("6.1URT", Sensor.MODIS, ("6.1", ProcessingStatus.URT)),
        ("2.0RT", Sensor.VIIRS, ("2", ProcessingStatus.RT)),
        ("1.0", Sensor.VIIRS, ("1", ProcessingStatus.SP)),
        ("garbage", Sensor.VIIRS, ("unknown", ProcessingStatus.UNKNOWN)),
    ],
)
def test_parse_version(version, sensor, expected):
    assert parse_version(version, sensor, None) == expected


def test_missing_values_stay_missing_not_zero():
    valid, _ = _parse(SYNTHETIC_VIIRS_CSV)
    assert pd.isna(valid.loc[2, "frp_mw"])  # blank FRP is NaN, never 0
    modis, _ = _parse(SYNTHETIC_MODIS_CSV)
    assert pd.isna(modis.loc[1, "hotspot_type"])  # NRT rows have no type


def test_antimeridian_and_southern_hemisphere_coordinates_are_valid():
    valid, _ = _parse(SYNTHETIC_VIIRS_CSV)
    assert valid["longitude"].tolist() == [2.54321, 179.95, -179.9]
    assert valid["latitude"].min() < 0


def test_every_bad_row_is_reported_with_a_reason_and_none_dropped():
    valid, invalid = _parse(SYNTHETIC_BAD_ROWS_CSV)
    assert len(valid) + len(invalid) == 9
    assert len(valid) == 1 and valid.loc[0, "latitude"] == 12.0
    reasons = list(invalid["reason"])
    assert any("latitude" in r for r in reasons)
    assert any("longitude" in r for r in reasons)
    assert any("acq_date" in r for r in reasons)
    assert any("acq_time" in r for r in reasons)
    assert any("satellite code" in r for r in reasons)
    assert any("VIIRS confidence" in r for r in reasons)
    assert any("frp" in r for r in reasons)
    assert any("daynight" in r for r in reasons)
    assert list(invalid["source_row_number"]) == [1, 2, 3, 4, 5, 6, 7, 8]


def test_source_attributes_preserve_original_row():
    valid, _ = _parse(SYNTHETIC_MODIS_CSV)
    original = json.loads(valid.loc[1, "source_attributes"])
    assert original["acq_time"] == "5"
    assert original["satellite"] == "T"
    assert original["type"] == ""


def test_observation_id_is_deterministic_and_unique_per_detection():
    first, _ = _parse(SYNTHETIC_VIIRS_CSV)
    second, _ = _parse(SYNTHETIC_VIIRS_CSV, source_file="SYNTHETIC_copy.csv")
    assert list(first["observation_id"]) == list(second["observation_id"])
    assert first["observation_id"].is_unique


def test_chunking_gives_identical_results_and_continuous_row_numbers():
    whole, _ = _parse(SYNTHETIC_VIIRS_CSV, chunk_rows=1000)
    chunked, _ = _parse(SYNTHETIC_VIIRS_CSV, chunk_rows=1)
    pd.testing.assert_frame_equal(whole, chunked)
    assert list(chunked["source_row_number"]) == [1, 2, 3]


def test_declared_platform_contradiction_is_reported():
    _, invalid = _parse(SYNTHETIC_VIIRS_CSV, declared_platform=Platform.NOAA_20)
    assert len(invalid) == 2
    assert all("contradicts declared platform" in r for r in invalid["reason"])


def test_declared_platform_used_when_satellite_column_absent():
    text = (
        SYNTHETIC_VIIRS_CSV.replace(",satellite", "")
        .replace(",N,", ",")
        .replace(",N20,", ",")
        .replace(",N21,", ",")
    )
    valid, invalid = _parse(text, declared_platform=Platform.SUOMI_NPP)
    assert invalid.empty
    assert set(valid["platform"]) == {"Suomi-NPP"}


def test_viirs_brightness_column_named_brightness_is_accepted():
    text = SYNTHETIC_VIIRS_CSV.replace("bright_ti4", "brightness")
    valid, _ = _parse(text)
    assert valid["brightness_temperature"].tolist() == [340.1, 330.0, 310.0]


def test_missing_required_column_is_a_format_error():
    with pytest.raises(FirmsFormatError, match="acq_time"):
        _parse(SYNTHETIC_VIIRS_CSV.replace("acq_time", "when"))


def test_unidentifiable_sensor_is_a_format_error():
    with pytest.raises(FirmsFormatError, match="Cannot identify sensor"):
        _parse("latitude,longitude,acq_date,acq_time\n1,2,2020-01-01,1200\n")


def test_malformed_csv_raises_instead_of_dropping_lines():
    text = SYNTHETIC_VIIRS_CSV + "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17\n"
    with pytest.raises(FirmsFormatError, match="Malformed CSV"):
        _parse(text)


def test_zip_archive_members_are_streamed_with_member_provenance(tmp_path: Path):
    archive = tmp_path / "SYNTHETIC_TEST_DATA_yearly.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("modis/2019/SYNTHETIC_modis_2019_CountryA.csv", SYNTHETIC_MODIS_CSV)
        zf.writestr("viirs/2023/SYNTHETIC_viirs_2023_CountryB.csv", SYNTHETIC_VIIRS_CSV)
        zf.writestr("README.txt", "SYNTHETIC TEST DATA")
    chunks = list(iter_firms_file(archive, _context(source_file=archive.name)))
    members = [c.source_member for c in chunks]
    assert members == [
        "modis/2019/SYNTHETIC_modis_2019_CountryA.csv",
        "viirs/2023/SYNTHETIC_viirs_2023_CountryB.csv",
    ]
    assert [c.sensor for c in chunks] == [Sensor.MODIS, Sensor.VIIRS]
    assert sum(len(c.valid) for c in chunks) == 6


def test_header_only_file_yields_no_rows_and_no_errors():
    header = SYNTHETIC_VIIRS_CSV.splitlines()[0] + "\n"
    valid, invalid = _parse(header)
    assert valid.empty and invalid.empty


def test_whitespace_around_values_is_tolerated_but_original_kept():
    text = SYNTHETIC_VIIRS_CSV.replace(",N20,", ", N20 ,")
    valid, invalid = _parse(text)
    assert invalid.empty
    assert valid.loc[1, "platform"] == "NOAA-20"
    assert json.loads(valid.loc[1, "source_attributes"])["satellite"] == " N20 "


def test_unsupported_file_type(tmp_path: Path):
    path = tmp_path / "SYNTHETIC.json"
    path.write_text("{}")
    with pytest.raises(FirmsFormatError, match="Unsupported file type"):
        list(iter_firms_file(path, _context()))
