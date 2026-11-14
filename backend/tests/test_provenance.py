"""Provenance tests. File contents here are SYNTHETIC TEST DATA."""

import hashlib
from pathlib import Path

from app.ingestion.provenance import sha256_file, store_raw_file


def test_sha256_matches_hashlib(tmp_path: Path):
    path = tmp_path / "SYNTHETIC.csv"
    payload = b"SYNTHETIC TEST DATA\n" * 100_000  # > 1 MiB, exercises block reads
    path.write_bytes(payload)
    assert sha256_file(path) == hashlib.sha256(payload).hexdigest()


def test_raw_store_is_unchanged_copy_and_idempotent(tmp_path: Path):
    source = tmp_path / "SYNTHETIC.csv"
    source.write_bytes(b"latitude,longitude\n1,2\n")
    checksum = sha256_file(source)
    raw_dir = tmp_path / "raw"
    first = store_raw_file(source, raw_dir, checksum)
    second = store_raw_file(source, raw_dir, checksum)
    assert first == second
    assert first.read_bytes() == source.read_bytes()
    assert len(list(raw_dir.iterdir())) == 1
    named = store_raw_file(source, tmp_path / "raw2", checksum, name="original.csv")
    assert named.name == f"{checksum[:16]}_original.csv"
