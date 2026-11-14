"""The one writer of a package's `checksums.sha256`."""

import hashlib
import os
import tempfile
from pathlib import Path

from archive_contract.validate import CHECKSUMS, package_files


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def write_checksums(root: Path) -> None:
    """Rewrite `checksums.sha256` at `root`: `<sha256>  <path>` for every package file.

    Every path `package_files` lists (so not `_build/`, and no symlink) except the checksums
    file itself, sorted, in the format `validate_package` reads. The file is written to a
    temporary name and moved into place.
    """
    paths, _ = package_files(root)
    lines = "".join(f"{_sha256(root / p)}  {p}\n" for p in paths if p != CHECKSUMS)
    target = root / CHECKSUMS
    with tempfile.NamedTemporaryFile(dir=root, prefix=f".{CHECKSUMS}.", delete=False) as stream:
        stream.write(lines.encode("utf-8"))
    os.chmod(stream.name, _mode(target))
    os.replace(stream.name, target)


def _mode(target: Path) -> int:
    """The mode a replaced file keeps: its own, or 0o644 for a new one."""
    try:
        return target.stat().st_mode & 0o777
    except FileNotFoundError:
        return 0o644
