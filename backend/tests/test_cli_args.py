"""CLI argument tests. Coordinates are SYNTHETIC TEST DATA."""

from app.cli.args import attach_negative_values


def test_negative_bbox_value_is_attached():
    argv = ["--source", "MODIS_NRT", "--bbox", "-150,-30,-140,-20", "--start", "2026-11-12"]
    assert attach_negative_values(argv) == [
        "--source", "MODIS_NRT", "--bbox=-150,-30,-140,-20", "--start", "2026-11-12",
    ]  # fmt: skip


def test_positive_and_equals_forms_unchanged():
    assert attach_negative_values(["--bbox", "76,12,85,20"]) == ["--bbox", "76,12,85,20"]
    assert attach_negative_values(["--bbox=-1,-2,3,4"]) == ["--bbox=-1,-2,3,4"]


def test_real_options_are_never_swallowed():
    assert attach_negative_values(["--bbox", "--world"]) == ["--bbox", "--world"]
    assert attach_negative_values(["--bbox"]) == ["--bbox"]


def test_only_listed_options_are_rewritten():
    assert attach_negative_values(["--start", "-5"]) == ["--start", "-5"]
