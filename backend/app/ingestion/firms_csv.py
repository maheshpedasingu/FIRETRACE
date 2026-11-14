"""Streaming parser for NASA FIRMS MODIS / VIIRS active-fire CSV files.

Turns FIRMS CSV rows (from the Area API, the Archive Download Tool, or the yearly
per-country archive ZIPs) into canonical hotspot records, in bounded-size chunks.

Guarantees:
- Every input row ends up either in a chunk's ``valid`` frame or in its ``invalid``
  frame with a reason. Nothing is dropped silently.
- The complete original row is kept in ``source_attributes`` (JSON, original strings).
- Sensor-specific values are kept raw (``confidence_raw``, ``collection_version``);
  normalised categories are only derived where the source documentation supports it.
- ``observation_id`` is a deterministic hash of the record identity, so the same
  detection imported twice gets the same id (deduplication happens in storage).
"""

from __future__ import annotations

import hashlib
import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import IO

import numpy as np
import pandas as pd

from app.ingestion.firms_schema import (
    BRIGHTNESS_COLUMNS,
    CANONICAL_COLUMNS,
    HOTSPOT_TYPES,
    MODIS_CONFIDENCE_HIGH_MIN,
    MODIS_CONFIDENCE_NOMINAL_MIN,
    PLATFORM_PRODUCT,
    PLATFORM_SENSOR,
    REQUIRED_COMMON,
    SATELLITE_CODES,
    VIIRS_CONFIDENCE,
    ConfidenceClass,
    Platform,
    ProcessingStatus,
    Sensor,
)

DEFAULT_CHUNK_ROWS = 200_000
CSV_SUFFIXES = (".csv",)


class FirmsFormatError(ValueError):
    """The file (or ZIP member) cannot be interpreted as a FIRMS active-fire CSV."""


@dataclass(frozen=True)
class SourceContext:
    """Provenance shared by every row of one source file."""

    source_file: str
    source_checksum: str
    ingestion_timestamp: datetime
    source_member: str | None = None
    declared_platform: Platform | None = None
    declared_status: ProcessingStatus | None = None


@dataclass
class ParsedChunk:
    sensor: Sensor
    source_member: str | None
    valid: pd.DataFrame
    invalid: pd.DataFrame


# --------------------------------------------------------------------------- helpers


def _blank(series: pd.Series) -> pd.Series:
    return series == ""


def _numeric(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Parse numbers. Returns (values, garbage_mask); blanks become NaN, not garbage."""
    values = pd.to_numeric(series, errors="coerce")
    garbage = values.isna() & ~_blank(series)
    return values.astype("float64"), garbage


def _column(df: pd.DataFrame, *names: str) -> pd.Series | None:
    for name in names:
        if name in df.columns:
            return df[name]
    return None


def _empty_strings(index: pd.Index) -> pd.Series:
    return pd.Series("", index=index, dtype="object")


def detect_sensor(df: pd.DataFrame) -> Sensor:
    """Identify the sensor from the ``instrument`` column, else from channel columns."""
    instrument = _column(df, "instrument")
    if instrument is not None:
        values = {str(v).strip().upper() for v in instrument.unique() if str(v).strip()}
        if len(values) > 1:
            raise FirmsFormatError(f"Mixed instruments in one file: {sorted(values)}")
        if values:
            value = values.pop()
            if value in (Sensor.MODIS, Sensor.VIIRS):
                return Sensor(value)
            raise FirmsFormatError(f"Unrecognised instrument value: {value!r}")
    columns = set(df.columns)
    if columns & {"bright_ti4", "bright_ti5"}:
        return Sensor.VIIRS
    if "bright_t31" in columns:
        return Sensor.MODIS
    raise FirmsFormatError(
        "Cannot identify sensor: no 'instrument' column and no MODIS (bright_t31) "
        "or VIIRS (bright_ti4/bright_ti5) channel columns"
    )


def _parse_time(raw: pd.Series) -> tuple[pd.Series, pd.Series]:
    """FIRMS acq_time is HHMM UTC, sometimes without leading zeros, or HH:MM."""
    text = raw.str.replace(":", "", regex=False)
    ok_shape = text.str.fullmatch(r"\d{1,4}")
    padded = text.where(ok_shape, "").str.zfill(4)
    hours = pd.to_numeric(padded.str[:2], errors="coerce")
    minutes = pd.to_numeric(padded.str[2:], errors="coerce")
    ok = ok_shape & (hours < 24) & (minutes < 60)
    hhmm = padded.str[:2] + ":" + padded.str[2:]
    return hhmm.where(ok, None), ~ok


_VERSION_RE = re.compile(r"^\s*(?P<num>[0-9.]+)\s*(?P<suffix>URT|NRT|RT)?\s*$", re.IGNORECASE)


def parse_version(
    version: str, sensor: Sensor, declared: ProcessingStatus | None
) -> tuple[str, ProcessingStatus]:
    """Return (collection, processing_status) from a FIRMS version string.

    Documented forms: "6.1NRT" (C6.1 NRT), "6.1" (C6.1 standard), "2.0URT", "1.0NRT".
    A version with no suffix is standard processing. Anything else is "unknown".
    """
    match = _VERSION_RE.match(version or "")
    if not match:
        return "unknown", declared or ProcessingStatus.UNKNOWN
    number, suffix = match["num"], (match["suffix"] or "").upper()
    status = ProcessingStatus(suffix) if suffix else ProcessingStatus.SP
    if sensor is Sensor.MODIS:
        if number.startswith("6.1") or re.fullmatch(r"61(\.\d+)?", number):
            collection = "6.1"
        elif re.fullmatch(r"6(\.0+)?", number):
            collection = "6"
        else:
            collection = "unknown"
    else:
        major = number.split(".")[0]
        collection = major if major in {"1", "2"} else "unknown"
    return collection, status


def _fixed5(values: pd.Series) -> pd.Series:
    """Coordinates as integer 1e-5 degree units (stable across '12.5' vs '12.50000')."""
    return (values * 100_000).round().astype("int64").astype(str)


def _observation_ids(frame: pd.DataFrame) -> pd.Series:
    key = (
        frame["sensor"].astype(str)
        + "|"
        + frame["platform"].astype(str)
        + "|"
        + frame["acquisition_date"].astype(str)
        + "|"
        + frame["acquisition_time_utc"].astype(str)
        + "|"
        + _fixed5(frame["latitude"])
        + "|"
        + _fixed5(frame["longitude"])
        + "|"
        + frame["collection_version"].astype(str)
    )
    return key.map(lambda k: hashlib.blake2b(k.encode(), digest_size=16).hexdigest())


# --------------------------------------------------------------------------- core


def normalize_chunk(
    raw: pd.DataFrame, sensor: Sensor, context: SourceContext, first_row_number: int
) -> ParsedChunk:
    """Validate and map one chunk of FIRMS rows (all values as strings)."""
    # Strip whitespace once; every later step works on stripped strings.
    df = raw.fillna("").astype(str).apply(lambda col: col.str.strip())
    index = df.index
    row_numbers = pd.Series(np.arange(first_row_number, first_row_number + len(df)), index=index)
    reasons: dict[str, pd.Series] = {}

    def flag(mask: pd.Series, reason: str) -> None:
        reasons[reason] = mask.fillna(True).astype(bool)

    lat, lat_bad = _numeric(df["latitude"])
    lon, lon_bad = _numeric(df["longitude"])
    flag(lat_bad | lat.isna() | (lat < -90) | (lat > 90), "invalid latitude")
    flag(lon_bad | lon.isna() | (lon < -180) | (lon > 180), "invalid longitude")

    acq_date = pd.to_datetime(df["acq_date"], format="%Y-%m-%d", errors="coerce")
    flag(acq_date.isna(), "invalid acq_date (expected YYYY-MM-DD)")
    acq_time, time_bad = _parse_time(df["acq_time"])
    flag(time_bad, "invalid acq_time (expected HHMM UTC)")

    # Platform: from the satellite column, cross-checked with any declared platform.
    codes = SATELLITE_CODES[sensor]
    satellite = _column(df, "satellite")
    if satellite is not None:
        platform = satellite.str.lower().map(codes)
        flag(platform.isna(), f"unrecognised {sensor} satellite code")
        if context.declared_platform is not None:
            flag(
                platform.notna() & (platform != context.declared_platform),
                "satellite code contradicts declared platform",
            )
    elif context.declared_platform is not None:
        platform = pd.Series(context.declared_platform, index=index, dtype="object")
    else:
        platform = pd.Series(None, index=index, dtype="object")
        flag(pd.Series(True, index=index), "no satellite column and no declared platform")
    if context.declared_platform is not None:
        if PLATFORM_SENSOR[context.declared_platform] is not sensor:
            raise FirmsFormatError(
                f"Declared platform {context.declared_platform} is not a {sensor} platform"
            )

    # Confidence: keep raw; derive class only where documented.
    conf_raw = _column(df, "confidence")
    conf_raw = conf_raw if conf_raw is not None else _empty_strings(index)
    if sensor is Sensor.MODIS:
        conf_num, conf_bad = _numeric(conf_raw)
        flag(conf_bad | (conf_num < 0) | (conf_num > 100), "invalid MODIS confidence (0-100)")
        conf_class = pd.Series(
            np.select(
                [
                    conf_num >= MODIS_CONFIDENCE_HIGH_MIN,
                    conf_num >= MODIS_CONFIDENCE_NOMINAL_MIN,
                    conf_num >= 0,
                ],
                [
                    ConfidenceClass.HIGH.value,
                    ConfidenceClass.NOMINAL.value,
                    ConfidenceClass.LOW.value,
                ],
                default=None,
            ),
            index=index,
            dtype="object",
        )
    else:
        conf_class = (
            conf_raw.str.lower()
            .map(VIIRS_CONFIDENCE)
            .map(lambda c: c.value if isinstance(c, ConfidenceClass) else None)
        )
        flag(conf_class.isna() & (conf_raw != ""), "invalid VIIRS confidence (l/n/h)")

    def optional_number(names: tuple[str, ...], label: str, minimum: float | None = None):
        column = _column(df, *names)
        if column is None:
            return pd.Series(np.nan, index=index, dtype="float64")
        values, bad = _numeric(column)
        if minimum is not None:
            bad = bad | (values < minimum)
        flag(bad, f"invalid {label}")
        return values

    primary_cols, secondary_cols = BRIGHTNESS_COLUMNS[sensor]
    frp = optional_number(("frp",), "frp", minimum=0)
    bt_primary = optional_number(primary_cols, "brightness temperature", minimum=0)
    bt_secondary = optional_number(secondary_cols, "secondary brightness temperature", 0)
    scan = optional_number(("scan",), "scan", minimum=0)
    track = optional_number(("track",), "track", minimum=0)

    daynight = _column(df, "daynight")
    daynight = daynight.str.upper() if daynight is not None else _empty_strings(index)
    flag(~daynight.isin(["D", "N", ""]), "invalid daynight (D/N)")

    hotspot_type = optional_number(("type",), "type")
    flag(hotspot_type.notna() & ~hotspot_type.isin(list(HOTSPOT_TYPES)), "invalid type (0-3)")

    version = _column(df, "version")
    version = version if version is not None else _empty_strings(index)
    lookup = {v: parse_version(v, sensor, context.declared_status) for v in version.unique()}
    parsed = version.map(lookup)
    collection = parsed.map(lambda p: p[0])
    status = parsed.map(lambda p: p[1].value)
    no_version = version == ""
    if no_version.any():
        fallback = (context.declared_status or ProcessingStatus.UNKNOWN).value
        status = status.where(~no_version, fallback)
        collection = collection.where(~no_version, "unknown")

    # Combine reasons.
    reason_frame = pd.DataFrame(reasons, index=index)
    invalid_mask = reason_frame.any(axis=1)
    reason_text = (
        reason_frame.apply(lambda row: "; ".join(name for name, hit in row.items() if hit), axis=1)
        if invalid_mask.any()
        else pd.Series("", index=index)
    )

    # Original row as JSON (pandas' C serializer; one JSON object per line).
    if len(raw):
        raw_json = (
            raw.fillna("").astype(str).to_json(orient="records", lines=True, force_ascii=False)
        )
        attributes = pd.Series(raw_json.rstrip("\n").split("\n"), index=index)
    else:
        attributes = pd.Series([], index=index, dtype="object")

    invalid = pd.DataFrame(
        {
            "source_file": context.source_file,
            "source_member": context.source_member,
            "source_row_number": row_numbers[invalid_mask],
            "source_checksum": context.source_checksum,
            "reason": reason_text[invalid_mask],
            "source_attributes": attributes[invalid_mask],
        }
    ).reset_index(drop=True)

    ok = ~invalid_mask
    platform_ok = platform[ok]
    valid = pd.DataFrame(
        {
            "source_record_id": None,
            "latitude": lat[ok],
            "longitude": lon[ok],
            "acquisition_date": acq_date[ok].dt.date,
            "acquisition_time_utc": acq_time[ok],
            "acquisition_datetime_utc": pd.to_datetime(
                acq_date[ok].dt.strftime("%Y-%m-%d") + " " + acq_time[ok], utc=True
            ),
            "sensor": sensor.value,
            "platform": platform_ok.map(lambda p: Platform(p).value),
            "instrument": sensor.value,
            "product": platform_ok.map(lambda p: PLATFORM_PRODUCT[Platform(p)]),
            "collection": collection[ok],
            "collection_version": version[ok],
            "processing_status": status[ok],
            "confidence_raw": conf_raw[ok],
            "confidence_class": conf_class[ok],
            "frp_mw": frp[ok],
            "brightness_temperature": bt_primary[ok],
            "brightness_temperature_secondary": bt_secondary[ok],
            "day_night": daynight[ok].replace("", None),
            "scan": scan[ok],
            "track": track[ok],
            "hotspot_type": hotspot_type[ok].astype("Int64"),
            "source_file": context.source_file,
            "source_member": context.source_member,
            "source_row_number": row_numbers[ok],
            "source_checksum": context.source_checksum,
            "ingestion_timestamp": pd.Timestamp(context.ingestion_timestamp),
            "source_attributes": attributes[ok],
        },
        index=index[ok],
    )
    valid.insert(0, "observation_id", _observation_ids(valid) if len(valid) else [])
    valid = valid[list(CANONICAL_COLUMNS)].reset_index(drop=True)
    return ParsedChunk(sensor, context.source_member, valid, invalid)


def _guard_parser(reader, context: SourceContext) -> Iterator[pd.DataFrame]:
    """Turn malformed-CSV errors into a FirmsFormatError instead of dropping lines."""
    try:
        yield from reader
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        where = context.source_file + (
            f"::{context.source_member}" if context.source_member else ""
        )
        raise FirmsFormatError(f"Malformed CSV in {where}: {exc}") from exc


def iter_csv_chunks(
    handle: IO[bytes] | Path,
    context: SourceContext,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> Iterator[ParsedChunk]:
    """Read one FIRMS CSV in chunks of at most ``chunk_rows`` rows."""
    reader = pd.read_csv(
        handle,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        chunksize=chunk_rows,
        encoding="utf-8-sig",
    )
    sensor: Sensor | None = None
    next_row = 1
    for raw in _guard_parser(reader, context):
        raw.columns = [str(c).strip().lower() for c in raw.columns]
        missing = [c for c in REQUIRED_COMMON if c not in raw.columns]
        if missing:
            raise FirmsFormatError(f"Missing required FIRMS columns: {missing}")
        chunk_sensor = detect_sensor(raw)
        if sensor is None:
            sensor = chunk_sensor
        elif chunk_sensor is not sensor:
            raise FirmsFormatError("Sensor changes between chunks of the same file")
        yield normalize_chunk(raw, sensor, context, next_row)
        next_row += len(raw)


def iter_firms_file(
    path: Path,
    context: SourceContext,
    chunk_rows: int = DEFAULT_CHUNK_ROWS,
) -> Iterator[ParsedChunk]:
    """Parse a FIRMS ``.csv`` file or every ``.csv`` member of a ``.zip`` archive.

    ZIP members are streamed one at a time; nothing is extracted to disk.
    """
    suffix = path.suffix.lower()
    if suffix in CSV_SUFFIXES:
        yield from iter_csv_chunks(path, context, chunk_rows)
    elif suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [
                m
                for m in archive.infolist()
                if not m.is_dir() and m.filename.lower().endswith(CSV_SUFFIXES)
            ]
            if not members:
                raise FirmsFormatError(f"No .csv files inside {path.name}")
            for member in members:
                member_context = replace(context, source_member=member.filename)
                with archive.open(member) as handle:
                    yield from iter_csv_chunks(handle, member_context, chunk_rows)
    else:
        raise FirmsFormatError(f"Unsupported file type: {path.name} (expected .csv or .zip)")
