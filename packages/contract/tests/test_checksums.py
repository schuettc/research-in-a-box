import hashlib
import shutil
from pathlib import Path

from archive_contract import checksums_text, write_checksums
from archive_contract.validate import validate_package

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"


def test_an_unchanged_sample_copy_gets_its_committed_checksums_byte_for_byte(
    tmp_path: Path,
) -> None:
    root = tmp_path / "sample"
    shutil.copytree(SAMPLE, root)
    (root / "checksums.sha256").unlink()

    write_checksums(root)

    assert (root / "checksums.sha256").read_bytes() == (SAMPLE / "checksums.sha256").read_bytes()
    assert sorted(p.name for p in root.iterdir() if p.name.startswith(".")) == []


def test_checksums_cover_every_package_file_but_build_and_themselves(tmp_path: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "a.csv").write_bytes(b"a\n")
    (tmp_path / "_build").mkdir()
    (tmp_path / "_build" / "make.py").write_bytes(b"print()\n")
    (tmp_path / "checksums.sha256").write_text("stale  data/a.csv\n")

    write_checksums(tmp_path)

    digest = hashlib.sha256(b"a\n").hexdigest()
    assert (tmp_path / "checksums.sha256").read_text() == f"{digest}  data/a.csv\n"


def test_a_package_with_rewritten_checksums_validates(tmp_path: Path) -> None:
    root = tmp_path / "sample"
    shutil.copytree(SAMPLE, root)
    (root / "README.md").write_text("# Changed\n", encoding="utf-8")

    write_checksums(root)

    assert validate_package(root) == []


def test_checksums_text_hashes_replaced_content_instead_of_the_file_on_disk(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.txt").write_bytes(b"old\n")

    text = checksums_text(tmp_path, {"a.txt": b"new\n", "b.txt": b"added\n"})

    assert text == (
        f"{hashlib.sha256(b'new\n').hexdigest()}  a.txt\n"
        f"{hashlib.sha256(b'added\n').hexdigest()}  b.txt\n"
    )
    assert (tmp_path / "a.txt").read_bytes() == b"old\n"
