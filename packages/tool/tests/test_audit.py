import json
import shutil
from pathlib import Path

import pytest

from archive_contract.findings import Finding
from cruise.audit import audit, find_packages
from cruise.cli import main

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"
MESSY = Path(__file__).parent / "fixtures" / "messy-package"


@pytest.fixture
def archive(tmp_path: Path) -> Path:
    """The sample, the messy package and a copy of the sample whose manifest is broken."""
    shutil.copytree(SAMPLE, tmp_path / "sample")
    shutil.copytree(MESSY, tmp_path / "nested" / "messy")
    shutil.copytree(SAMPLE, tmp_path / "broken")
    (tmp_path / "broken" / "datapackage.json").write_text("{", encoding="utf-8")
    return tmp_path


def test_find_packages_skips_build_and_node_modules(tmp_path: Path) -> None:
    for folder in ["a", "a/_build/old", "node_modules/x", "b/c"]:
        (tmp_path / folder).mkdir(parents=True)
        (tmp_path / folder / "datapackage.json").write_text("{}", encoding="utf-8")

    assert find_packages([tmp_path]) == [tmp_path / "a", tmp_path / "b" / "c"]


def test_audit_ranks_unreadable_first_then_by_errors_then_by_score(archive: Path) -> None:
    rows = audit([archive])

    assert [row.path for row in rows] == [
        archive / "broken",
        archive / "nested" / "messy",
        archive / "sample",
    ]
    assert rows[0].top_rule == "structure.manifest-invalid"
    assert (rows[1].errors, rows[2].errors) == (1, 0)


def test_audit_prints_one_row_per_package_messy_first(
    archive: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (archive / "broken").rename(archive / "_build")  # skipped, so not listed

    assert main(["audit", str(archive)]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["path", "errors", "warnings", "notes", "score", "most", "fired"]
    assert lines[1].startswith(str(archive / "nested" / "messy"))
    assert lines[1].endswith("package.core-missing")
    assert lines[2].startswith(str(archive / "sample"))
    assert "(find 5 of 5, understand 42 of 45, trust 30 of 31)" in lines[2]
    assert len(lines) == 3


def test_audit_json_round_trips_through_the_contract(
    archive: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["audit", str(archive), "--json", "--profile", "ecology"]) == 0

    packages = json.loads(capsys.readouterr().out)["packages"]
    assert [Path(p["path"]).name for p in packages] == ["broken", "messy", "sample"]
    assert packages[1]["errors"] == 2
    for package in packages:
        findings = [Finding.model_validate(f) for f in package["findings"]]
        assert [f.dump() for f in findings] == package["findings"]


def test_audit_exits_2_when_a_folder_does_not_exist(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["audit", str(tmp_path / "missing")]) == 2
    assert "missing" in capsys.readouterr().err
