"""Tests for FIRMS API planning helpers. All values are SYNTHETIC TEST DATA."""

from datetime import date

import pytest

from app.ingestion.firms_api_plan import (
    BBox,
    DateWindow,
    TransactionBudget,
    area_filename,
    parse_source,
    plan_windows,
    redact,
)
from app.ingestion.firms_schema import Platform, ProcessingStatus


def test_plan_windows_covers_range_exactly_without_overlap():
    windows = plan_windows(date(2026, 1, 1), date(2026, 1, 12), 5)
    assert [(w.start, w.days) for w in windows] == [
        (date(2026, 1, 1), 5),
        (date(2026, 1, 6), 5),
        (date(2026, 1, 11), 2),
    ]
    assert windows[-1].end == date(2026, 1, 12)


def test_plan_windows_single_day_and_errors():
    assert plan_windows(date(2026, 1, 1), date(2026, 1, 1), 5) == [DateWindow(date(2026, 1, 1), 1)]
    with pytest.raises(ValueError):
        plan_windows(date(2026, 1, 2), date(2026, 1, 1), 5)
    with pytest.raises(ValueError):
        plan_windows(date(2026, 1, 1), date(2026, 1, 2), 0)


def test_bbox_parse_format_and_validation():
    bbox = BBox.parse("76,12.5,85,20")
    assert bbox.area_param() == "76,12.5,85,20"
    with pytest.raises(ValueError):
        BBox.parse("1,2,3")
    with pytest.raises(ValueError):
        BBox(0, 10, 5, 5)  # south >= north
    with pytest.raises(ValueError):
        BBox(-190, 0, 5, 5)


def test_antimeridian_bbox_is_split_in_two():
    parts = BBox(170, -20, -170, 10).split_antimeridian()
    assert [p.area_param() for p in parts] == ["170,-20,180,10", "-180,-20,-170,10"]
    assert BBox(10, 0, 20, 5).split_antimeridian() == [BBox(10, 0, 20, 5)]


@pytest.mark.parametrize(
    ("source", "platforms", "status"),
    [
        ("MODIS_NRT", (Platform.TERRA, Platform.AQUA), ProcessingStatus.NRT),
        ("MODIS_SP", (Platform.TERRA, Platform.AQUA), ProcessingStatus.SP),
        ("VIIRS_SNPP_SP", (Platform.SUOMI_NPP,), ProcessingStatus.SP),
        ("viirs_noaa20_nrt", (Platform.NOAA_20,), ProcessingStatus.NRT),
        ("VIIRS_NOAA21_NRT", (Platform.NOAA_21,), ProcessingStatus.NRT),
    ],
)
def test_parse_source(source, platforms, status):
    info = parse_source(source)
    assert (info.platforms, info.status) == (platforms, status)
    assert info.declared_platform == (platforms[0] if len(platforms) == 1 else None)


@pytest.mark.parametrize("source", ["LANDSAT_NRT", "VIIRS_NOAA20", "MODIS_URT", ""])
def test_unknown_sources_rejected(source):
    with pytest.raises(ValueError):
        parse_source(source)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_budget_waits_when_exhausted():
    fake = FakeClock()
    budget = TransactionBudget(10, 600, clock=fake.clock, sleep=fake.sleep)
    assert budget.acquire(5) == 0
    assert budget.acquire(5) == 0
    waited = budget.acquire(5)  # needs 5 tokens at 10 per 600 s → 300 s
    assert waited == pytest.approx(300)
    with pytest.raises(ValueError):
        budget.acquire(11)


def test_redact_removes_key_everywhere():
    key = "0123456789abcdef0123456789abcdef"  # SYNTHETIC, not a real key
    text = f"GET /api/area/csv/{key}/X failed; key={key}"
    assert key not in redact(text, key)
    assert redact("nothing secret", None) == "nothing secret"


def test_area_filename_is_filesystem_safe_and_unique_per_window():
    name = area_filename("VIIRS_NOAA20_NRT", "-180,-20,-170.5,10", DateWindow(date(2026, 1, 6), 5))
    assert name == "firms_area_VIIRS_NOAA20_NRT_m180_m20_m170p5_10_2026-01-06_5d.csv"
    assert ":" not in name and "/" not in name
