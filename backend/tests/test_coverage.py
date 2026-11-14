"""Coverage tests. Country names and file names are SYNTHETIC TEST DATA."""

import json
from datetime import date

import pytest

from app.ingestion.coverage import bbox_coverage, country_coverage, coverage_from_archive_name


def test_archive_name_gives_country_year_with_unverified_note():
    spec = coverage_from_archive_name("modis/2020/modis_2020_Synthetic_Land.csv")
    assert spec is not None
    assert (spec.extent_type, spec.extent_value) == ("country", "Synthetic Land")
    assert (spec.start_date, spec.end_date) == (date(2020, 1, 1), date(2020, 12, 31))
    assert spec.basis == "archive_filename"
    assert "not verified" in spec.note


def test_viirs_style_archive_name():
    spec = coverage_from_archive_name("viirs-snpp_2019_Synthetic_Land.csv")
    assert spec is not None and spec.extent_value == "Synthetic Land"


@pytest.mark.parametrize("name", ["export.csv", "fire_archive_M-C61_123.csv", "modis_1899_X.csv"])
def test_unrecognised_names_give_no_coverage(name):
    assert coverage_from_archive_name(name) is None


def test_bbox_coverage_validates_and_flags_antimeridian():
    spec = bbox_coverage(170, -20, -170, 10, date(2023, 1, 1), date(2023, 1, 5))
    assert json.loads(spec.extent_value) == {"west": 170, "south": -20, "east": -170, "north": 10}
    assert "antimeridian" in spec.note
    with pytest.raises(ValueError):
        bbox_coverage(0, 10, 10, 5, date(2023, 1, 1), date(2023, 1, 2))
    with pytest.raises(ValueError):
        bbox_coverage(0, 0, 10, 10, date(2023, 1, 2), date(2023, 1, 1))


def test_country_coverage_rejects_reversed_dates():
    with pytest.raises(ValueError):
        country_coverage("Synthetic Land", date(2023, 2, 1), date(2023, 1, 1))
