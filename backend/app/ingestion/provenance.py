"""Source-file provenance: streaming checksums and immutable raw-file storage."""

import hashlib
import shutil
from pathlib import Path

_CHUNK_BYTES = 1024 * 1024


def sha256_file(path: Path) -> str:
    """SHA-256 of a file, read in 1 MiB blocks (constant memory for any file size)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(_CHUNK_BYTES):
            digest.update(block)
    return digest.hexdigest()


def store_raw_file(source: Path, raw_dir: Path, checksum: str, name: str | None = None) -> Path:
    """Copy a source file into the raw store unchanged, keyed by its checksum.

    The original filename (``name``, default the file's own name) is kept after the
    checksum prefix. If a file with the same
    checksum is already stored, the existing copy is returned and nothing is written.
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / f"{checksum[:16]}_{name or source.name}"
    if target.exists():
        if sha256_file(target) != checksum:
            raise RuntimeError(f"Raw store corruption: {target} does not match {checksum}")
        return target
    tmp = target.with_suffix(target.suffix + ".partial")
    shutil.copyfile(source, tmp)
    if sha256_file(tmp) != checksum:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Checksum changed while copying {source}")
    tmp.replace(target)
    return target
