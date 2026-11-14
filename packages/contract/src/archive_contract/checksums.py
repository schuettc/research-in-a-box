"""The one writer of a package's `checksums.sha256`."""

import hashlib
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path

from archive_contract.validate import CHECKSUMS, package_files


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def checksums_text(root: Path, replaced: Mapping[str, bytes] | None = None) -> str:
    """The text of `checksums.sha256` for the package at `root`: `<sha256>  <path>` lines.

    Every path `package_files` lists (so not `_build/`, and no symlink) except the checksums
    file itself, sorted, in the format `validate_package` reads. `replaced` maps relative
    paths to content about to be written, which is hashed instead of the file on disk, so a
    writer can build every file before writing any.
    """
    replaced = replaced or {}
    paths, _ = package_files(root)
    lines = []
    for path in sorted(set(paths) | set(replaced)):
        if path == CHECKSUMS:
            continue
        data = replaced.get(path)
        digest = hashlib.sha256(data).hexdigest() if data is not None else _sha256(root / path)
        lines.append(f"{digest}  {path}\n")
    return "".join(lines)


def write_checksums(root: Path) -> None:
    """Rewrite `checksums.sha256` at `root` from `checksums_text`.

    The file is written to a temporary name and moved into place.
    """
    lines = checksums_text(root)
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
