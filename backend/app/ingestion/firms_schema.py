"""Canonical definitions for NASA FIRMS MODIS and VIIRS active-fire records.

Sources for the code tables below (checked 2026-11-14):
- NASA Earthdata, "FIRMS active fire data attributes (MODIS, VIIRS)":
  MODIS satellite A = Aqua, T = Terra; VIIRS satellite N = Suomi NPP, N20 = NOAA-20,
  N21 = NOAA-21; VIIRS confidence low / nominal / high; MODIS confidence 0-100 %;
  version "6.1NRT" = Collection 6.1 NRT, "6.1" = Collection 6.1 standard processing,
  suffix "URT" = Ultra Real-Time; type 0-3 only in standard-quality data;
  VIIRS I-4 brightness may be named "brightness" in web services.
- MODIS confidence class thresholds: MODIS Collection 6 and 6.1 Active Fire Product
  User's Guide v1.0 (Giglio et al.), FAQ 8.4.3, Table 11: low 0 <= C < 30,
  nominal 30 <= C < 80, high 80 <= C <= 100. Checked 2026-11-14.

Unrecognised codes are rejected with a reason, never guessed.
"""

from enum import StrEnum


class Sensor(StrEnum):
    MODIS = "MODIS"
    VIIRS = "VIIRS"


class Platform(StrEnum):
    TERRA = "Terra"
    AQUA = "Aqua"
    SUOMI_NPP = "Suomi-NPP"
    NOAA_20 = "NOAA-20"
    NOAA_21 = "NOAA-21"


class ProcessingStatus(StrEnum):
    SP = "SP"  # standard processing (science quality)
    NRT = "NRT"
    RT = "RT"
    URT = "URT"
    UNKNOWN = "unknown"


class ConfidenceClass(StrEnum):
    LOW = "low"
    NOMINAL = "nominal"
    HIGH = "high"


PLATFORM_SENSOR: dict[Platform, Sensor] = {
    Platform.TERRA: Sensor.MODIS,
    Platform.AQUA: Sensor.MODIS,
    Platform.SUOMI_NPP: Sensor.VIIRS,
    Platform.NOAA_20: Sensor.VIIRS,
    Platform.NOAA_21: Sensor.VIIRS,
}

# Level-2 active-fire product underlying each platform's FIRMS records.
PLATFORM_PRODUCT: dict[Platform, str] = {
    Platform.TERRA: "MOD14",
    Platform.AQUA: "MYD14",
    Platform.SUOMI_NPP: "VNP14IMG",
    Platform.NOAA_20: "VJ114IMG",
    Platform.NOAA_21: "VJ214IMG",
}

# Documented satellite codes, matched case-insensitively.
SATELLITE_CODES: dict[Sensor, dict[str, Platform]] = {
    Sensor.MODIS: {
        "t": Platform.TERRA,
        "terra": Platform.TERRA,
        "a": Platform.AQUA,
        "aqua": Platform.AQUA,
    },
    Sensor.VIIRS: {
        "n": Platform.SUOMI_NPP,
        # FIRMS Archive Download VIIRS S-NPP files (seen 2026-11-15 in a real India
        # download, fire_archive_SV-C2_*.csv and fire_nrt_SV-C2_*.csv) use "SNPP".
        "snpp": Platform.SUOMI_NPP,
        "n20": Platform.NOAA_20,
        "n21": Platform.NOAA_21,
    },
}

# Values of the ``instrument`` column, upper-cased. The Area API writes MODIS / VIIRS;
# FIRMS Archive Download VIIRS S-NPP files write "SNPP" (seen in a real file,
# 2026-11-15). Only values seen in real FIRMS files are listed; anything else is
# rejected with an error rather than guessed (NOAA-20/21 archive values are not yet
# confirmed).
INSTRUMENT_VALUES: dict[str, Sensor] = {
    "MODIS": Sensor.MODIS,
    "VIIRS": Sensor.VIIRS,
    "SNPP": Sensor.VIIRS,
}

VIIRS_CONFIDENCE: dict[str, ConfidenceClass] = {
    "l": ConfidenceClass.LOW,
    "low": ConfidenceClass.LOW,
    "n": ConfidenceClass.NOMINAL,
    "nominal": ConfidenceClass.NOMINAL,
    "h": ConfidenceClass.HIGH,
    "high": ConfidenceClass.HIGH,
}

# Plain-string lookup tables for pandas ``Series.map``. Enum members must not be put
# into pandas columns: with pyarrow-backed strings (pandas 3 + pyarrow) they are
# converted to plain ``str``, so identity/isinstance checks on them fail.
SATELLITE_CODE_VALUES: dict[Sensor, dict[str, str]] = {
    sensor: {code: platform.value for code, platform in codes.items()}
    for sensor, codes in SATELLITE_CODES.items()
}
VIIRS_CONFIDENCE_VALUES: dict[str, str] = {k: v.value for k, v in VIIRS_CONFIDENCE.items()}

MODIS_CONFIDENCE_NOMINAL_MIN = 30
MODIS_CONFIDENCE_HIGH_MIN = 80

HOTSPOT_TYPES: dict[int, str] = {
    0: "presumed vegetation fire",
    1: "active volcano",
    2: "other static land source",
    3: "offshore",
}

# Columns required to build a canonical record (lower-cased FIRMS names).
REQUIRED_COMMON = ("latitude", "longitude", "acq_date", "acq_time")

# Brightness columns: (primary, secondary) per sensor, in order of preference.
BRIGHTNESS_COLUMNS: dict[Sensor, tuple[tuple[str, ...], tuple[str, ...]]] = {
    Sensor.MODIS: (("brightness",), ("bright_t31",)),
    # Archive Download VIIRS files name the I4/I5 brightness temperatures "brightness" /
    # "bright_t31" (MODIS-style column names); the values are the VIIRS I4/I5 channels.
    Sensor.VIIRS: (("bright_ti4", "brightness"), ("bright_ti5", "bright_t31")),
}

CANONICAL_COLUMNS: tuple[str, ...] = (
    "observation_id",
    "source_record_id",
    "latitude",
    "longitude",
    "acquisition_date",
    "acquisition_time_utc",
    "acquisition_datetime_utc",
    "sensor",
    "platform",
    "instrument",
    "product",
    "collection",
    "collection_version",
    "processing_status",
    "confidence_raw",
    "confidence_class",
    "frp_mw",
    "brightness_temperature",
    "brightness_temperature_secondary",
    "day_night",
    "scan",
    "track",
    "hotspot_type",
    "source_file",
    "source_member",
    "source_row_number",
    "source_checksum",
    "ingestion_timestamp",
    "source_attributes",
)
