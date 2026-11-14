"""File listing shared by every reader of the observation store."""

from pathlib import Path


def visible_parquet_files(root: Path) -> list[Path]:
    """All Parquet files under root, skipping hidden (dot) directories and files.

    Compaction builds and retires partitions in hidden directories; skipping them means
    no reader can ever see a partition's rows twice.
    """
    root = Path(root)
    if not root.is_dir():
        return []
    return sorted(
        p
        for p in root.rglob("*.parquet")
        if not any(part.startswith(".") for part in p.relative_to(root).parts)
    )
