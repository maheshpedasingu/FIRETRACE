"""First day of FIRMS active-fire records for each platform.

Coverage comes from requests and archive names, which know nothing about satellite
lifetimes: a MODIS request for 2001 also "covers" Aqua, whose data begin in July 2002.
Days before a platform's first record are therefore never treated as covered, so they
can never produce a false zero.

Sources: the FIRMS Archive Download page, "Data availability" list, as shown on
2026-11-15 (MODIS Terra: November 01 2000 - present; MODIS Aqua: July 04 2002 - present;
VIIRS S-NPP: January 20 2012 - 2 November 2026; VIIRS NOAA-20: April 01 2018 - present;
VIIRS NOAA-21: March 01 2023 - present), consistent with NASA Earthdata FIRMS ("MODIS C6
is available from November 2000 (for Terra) and from July 2002 (for Aqua)"). An older
FIRMS page gave 17 January 2024 for NOAA-21; the current Archive Download list is used.

Days after a platform's last record are likewise never covered (Suomi-NPP ends on
2026-11-02). Platforms still delivering data have no end date. Known outages (e.g. the
August 2020 Aqua outage, MODIS C6/C6.1 User's Guide §7.2.4) are not modelled; a covered
day inside an outage can show as a zero.
"""

from __future__ import annotations

from datetime import date

PLATFORM_DATA_START: dict[str, date] = {
    "Terra": date(2000, 11, 1),
    "Aqua": date(2002, 7, 4),
    "Suomi-NPP": date(2012, 1, 20),
    "NOAA-20": date(2018, 4, 1),
    "NOAA-21": date(2023, 3, 1),
}

PLATFORM_DATA_END: dict[str, date] = {
    "Suomi-NPP": date(2026, 11, 2),
}


def first_record_day(platform: str) -> date | None:
    """First day with FIRMS records for ``platform`` (None if unknown)."""
    return PLATFORM_DATA_START.get(platform)


def last_record_day(platform: str) -> date | None:
    """Last day with FIRMS records for ``platform`` (None while it is still operating)."""
    return PLATFORM_DATA_END.get(platform)
