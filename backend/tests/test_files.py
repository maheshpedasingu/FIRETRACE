"""Store file-listing tests. File contents are SYNTHETIC TEST DATA."""

from pathlib import Path

from app.storage.files import visible_parquet_files


def test_hidden_directories_are_invisible_to_readers(tmp_path: Path):
    (tmp_path / "VIIRS" / "2026" / "11" / "r10c025").mkdir(parents=True)
    (tmp_path / "VIIRS" / "2026" / "11" / ".r10c025.old").mkdir(parents=True)
    (tmp_path / "VIIRS" / "2026" / "11" / "r10c025" / "a.parquet").write_bytes(b"x")
    (tmp_path / "VIIRS" / "2026" / "11" / ".r10c025.old" / "b.parquet").write_bytes(b"x")
    (tmp_path / "VIIRS" / "2026" / "11" / "r10c025" / ".hidden.parquet").write_bytes(b"x")
    assert [p.name for p in visible_parquet_files(tmp_path)] == ["a.parquet"]
