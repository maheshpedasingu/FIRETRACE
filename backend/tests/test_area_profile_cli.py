"""area_profile CLI on an empty store (SYNTHETIC; needs the Windows-target libraries)."""

from pathlib import Path

import pytest

for module in ("sqlalchemy", "pyarrow"):
    pytest.importorskip(module)

from app.cli.area_profile import run  # noqa: E402
from app.core.config import Settings  # noqa: E402


def test_area_profile_runs_and_reports_each_step(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'meta.sqlite').as_posix()}",
        raw_data_dir=str(tmp_path / "raw"),
        processed_data_dir=str(tmp_path / "processed"),
    )
    lines: list[str] = []
    argv = ["--bbox", "70,10,90,25", "--start", "2026-01-01", "--end", "2026-03-31"]
    assert run(argv, settings=settings, out=lines.append) == 0
    labels = [line.split("  ")[0] for line in lines[:-1]]
    assert labels[2].startswith("area context") and "peak" in lines[2]
    assert lines[-1].startswith("total detections 0; months 3")
