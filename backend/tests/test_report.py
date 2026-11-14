"""Report generation tests. All values are SYNTHETIC TEST DATA."""

import json

import pandas as pd

from app.analytics.baselines import assess
from app.analytics.report import build_report, to_markdown

SERIES = pd.DataFrame(
    [
        {"platform": "Aqua", "year": y, "month": 3, "coverage_status": "complete",
         "detections": v}
        for y, v in {2015: 100, 2016: 110, 2017: 90, 2018: 105, 2019: 95, 2020: 300}.items()
    ]
    + [{"platform": "Terra", "year": 2020, "month": 3, "coverage_status": "missing",
        "detections": float("nan")}]
)  # fmt: skip


def make_report():
    target = pd.DataFrame([assess(SERIES, p, 2020, 3).__dict__ for p in ("Aqua", "Terra")])
    return build_report(
        area={"bbox": [76, 12, 85, 20], "country": None},
        period={"start": "2015-03-01", "end": "2020-03-31", "target": "2020-03"},
        metric="detections",
        series=SERIES,
        target=target,
        hai=pd.DataFrame(),
        calibrations=[],
        matching=[],
        settings={"min_history_years": 5},
    )


def test_report_is_json_serialisable_without_nan():
    report = make_report()
    text = json.dumps(report, default=str)
    assert "NaN" not in text
    assert report["status"].startswith("EXPERIMENTAL")
    assert report["coverage_months_by_platform"]["Terra"]["missing"] == 1


def test_markdown_states_results_and_limitations():
    md = to_markdown(make_report())
    assert "| Aqua | 300 | complete | 5 |" in md
    assert "unusually high" in md
    assert "not assessed (incomplete_coverage)" in md
    assert "Unavailable: no platform could be assessed" in md
    assert "not fire incidents" in md
