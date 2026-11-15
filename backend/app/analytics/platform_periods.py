"""First day of FIRMS active-fire records for each platform.

Coverage comes from requests and archive names, which know nothing about satellite
lifetimes: a MODIS request for 2001 also "covers" Aqua, whose data begin in July 2002.
Days before a platform's first record are therefore never treated as covered, so they
can never produce a false zero.

Sources (checked 2026-11-14):
- Terra MODIS: FIRMS Archive Download, "MODIS Collection 6.1: Temporal Coverage:
  1 November 2000 - present".
- Aqua MODIS: NASA Earthdata FIRMS, "MODIS C6 is available from November 2000 (for
  Terra) and from July 2002 (for Aqua)". The Aqua MODIS fire products (MYD14) begin on
  4 July 2002; earlier July 2002 days are treated as not covered.
- Suomi-NPP VIIRS: FIRMS Archive Download, "20 January 2012 - present".
- NOAA-20 VIIRS: FIRMS Archive Download, "1 April 2018 - present".
- NOAA-21 VIIRS: FIRMS Archive Download, "17 January 2024 - present".

End dates are not applied: all five platforms were still delivering data when this was
written (Suomi-NPP end of life is expected on or before October 2026). Known outages
(e.g. the August 2020 Aqua outage in the MODIS C6/C6.1 User's Guide §7.2.4) are not
modelled; a covered day inside an outage can show as a zero.
"""

from __future__ import annotations

from datetime import date

PLATFORM_DATA_START: dict[str, date] = {
    "Terra": date(2000, 11, 1),
    "Aqua": date(2002, 7, 4),
    "Suomi-NPP": date(2012, 1, 20),
    "NOAA-20": date(2018, 4, 1),
    "NOAA-21": date(2024, 1, 17),
}


def first_record_day(platform: str) -> date | None:
    """First day with FIRMS records for ``platform`` (None if unknown)."""
    return PLATFORM_DATA_START.get(platform)
