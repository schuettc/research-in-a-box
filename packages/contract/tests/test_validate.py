import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from archive_contract.findings import Finding
from archive_contract.validate import validate_package

FIXTURES = Path(__file__).parent / "fixtures"


def rule_ids(findings: list[Finding]) -> list[str]:
    return [f.rule_id for f in findings]


def edited(
    tmp_path: Path, edit: Callable[[dict[str, Any]], None], *, refresh_checksums: bool = True
) -> Path:
    """A copy of the valid fixture with its manifest edited and its checksums rewritten."""
    root = tmp_path / "package"
    shutil.copytree(FIXTURES / "valid", root)
    manifest_path = root / "datapackage.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    edit(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    if refresh_checksums:
        write_checksums(root)
    return root


def write_checksums(root: Path) -> None:
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root).as_posix()}\n"
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name != "checksums.sha256"
    ]
    (root / "checksums.sha256").write_text("".join(lines), encoding="utf-8")


def test_valid_package_has_no_findings() -> None:
    assert validate_package(FIXTURES / "valid") == []


@pytest.mark.parametrize(
    ("fixture", "rule"),
    [
        ("fk-missing-resource", "structure.foreign-key"),
        ("member-missing", "structure.file-missing"),
        ("wrong-hash", "structure.hash-mismatch"),
        ("stale-checksums", "structure.checksums-mismatch"),
    ],
)
def test_each_broken_fixture_gives_its_one_finding(fixture: str, rule: str) -> None:
    findings = validate_package(FIXTURES / fixture)

    assert rule_ids(findings) == [rule]
    assert findings[0].severity == "error"


def test_finding_names_its_target() -> None:
    [finding] = validate_package(FIXTURES / "member-missing")

    assert finding.target is not None
    assert finding.target.resource == "sites"
    assert finding.target.path == "data/sites/sites.dbf"


def test_missing_manifest(tmp_path: Path) -> None:
    assert rule_ids(validate_package(tmp_path)) == ["structure.manifest-missing"]


def test_manifest_that_is_not_json(tmp_path: Path) -> None:
    (tmp_path / "datapackage.json").write_text("{not json", encoding="utf-8")

    assert rule_ids(validate_package(tmp_path)) == ["structure.manifest-invalid"]


def test_manifest_that_breaks_the_model(tmp_path: Path) -> None:
    (tmp_path / "datapackage.json").write_text('{"version": "1.0.0"}', encoding="utf-8")

    [finding] = validate_package(tmp_path)

    assert finding.rule_id == "structure.manifest-invalid"
    assert "version" in finding.message


def test_foreign_key_to_a_missing_field(tmp_path: Path) -> None:
    def edit(m: dict[str, Any]) -> None:
        m["resources"][1]["schema"]["foreignKeys"][0]["reference"]["fields"] = ["nope"]

    assert rule_ids(validate_package(edited(tmp_path, edit))) == ["structure.foreign-key"]


def test_foreign_key_from_a_missing_local_field(tmp_path: Path) -> None:
    def edit(m: dict[str, Any]) -> None:
        m["resources"][1]["schema"]["foreignKeys"][0]["fields"] = ["nope"]

    assert rule_ids(validate_package(edited(tmp_path, edit))) == ["structure.foreign-key"]


def test_alternate_of_a_missing_resource(tmp_path: Path) -> None:
    def edit(m: dict[str, Any]) -> None:
        m["resources"][3]["archive:alternateOf"] = "nothing-here"

    assert rule_ids(validate_package(edited(tmp_path, edit))) == ["structure.alternate-of"]


def test_alternate_of_itself(tmp_path: Path) -> None:
    def edit(m: dict[str, Any]) -> None:
        m["resources"][3]["archive:alternateOf"] = "methods"

    assert rule_ids(validate_package(edited(tmp_path, edit))) == ["structure.alternate-of"]


def test_listed_file_without_size_and_hash(tmp_path: Path) -> None:
    def edit(m: dict[str, Any]) -> None:
        del m["resources"][3]["hash"]
        del m["resources"][2]["archive:files"][1]["bytes"]

    assert rule_ids(validate_package(edited(tmp_path, edit))) == [
        "structure.size-hash-missing",
        "structure.size-hash-missing",
    ]


def test_wrong_size(tmp_path: Path) -> None:
    def edit(m: dict[str, Any]) -> None:
        m["resources"][3]["bytes"] = 1

    assert rule_ids(validate_package(edited(tmp_path, edit))) == ["structure.size-mismatch"]


def test_main_file_not_among_members(tmp_path: Path) -> None:
    def edit(m: dict[str, Any]) -> None:
        m["resources"][2]["archive:files"] = m["resources"][2]["archive:files"][1:]

    assert rule_ids(validate_package(edited(tmp_path, edit))) == ["structure.main-not-member"]


def test_path_outside_the_package_is_refused_and_not_read(tmp_path: Path) -> None:
    (tmp_path / "secret.txt").write_text("outside", encoding="utf-8")

    def edit(m: dict[str, Any]) -> None:
        m["resources"][3]["path"] = "../secret.txt"

    assert rule_ids(validate_package(edited(tmp_path, edit))) == ["structure.path-unsafe"]


def test_linked_resource_is_not_looked_for_on_disk(tmp_path: Path) -> None:
    def edit(m: dict[str, Any]) -> None:
        m["resources"].append(
            {
                "name": "discharge",
                "path": "https://example.org/discharge.csv",
                "archive:kind": "linked",
            }
        )

    assert validate_package(edited(tmp_path, edit)) == []


def test_missing_checksums_file(tmp_path: Path) -> None:
    root = edited(tmp_path, lambda m: None)
    (root / "checksums.sha256").unlink()

    assert rule_ids(validate_package(root)) == ["structure.checksums-missing"]


def test_file_with_no_checksums_line(tmp_path: Path) -> None:
    root = edited(tmp_path, lambda m: None)
    (root / "docs" / "extra.txt").write_text("not listed", encoding="utf-8")

    assert rule_ids(validate_package(root)) == ["structure.checksums-unlisted"]


def test_checksums_line_for_a_missing_file(tmp_path: Path) -> None:
    root = edited(tmp_path, lambda m: None)
    with (root / "checksums.sha256").open("a", encoding="utf-8") as out:
        out.write(f"{'0' * 64}  docs/gone.txt\n")

    assert rule_ids(validate_package(root)) == ["structure.checksums-orphan"]


def test_hidden_and_underscore_files_are_not_package_content(tmp_path: Path) -> None:
    root = edited(tmp_path, lambda m: None)
    (root / ".DS_Store").write_text("x", encoding="utf-8")
    (root / "_build").mkdir()
    (root / "_build" / "make.py").write_text("print()", encoding="utf-8")

    assert validate_package(root) == []
