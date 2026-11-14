import hashlib
import json
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from archive_contract import write_checksums
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


def test_only_the_top_level_build_folder_is_exempt_from_checksums(tmp_path: Path) -> None:
    root = edited(tmp_path, lambda m: None)
    (root / "_build").mkdir()
    (root / "_build" / "make.py").write_text("print()", encoding="utf-8")

    assert validate_package(root) == []


@pytest.mark.parametrize("extra", [".DS_Store", "data/_readings.csv", "docs/_build/x.txt"])
def test_hidden_and_underscore_files_need_a_checksums_line(tmp_path: Path, extra: str) -> None:
    root = edited(tmp_path, lambda m: None)
    (root / extra).parent.mkdir(parents=True, exist_ok=True)
    (root / extra).write_text("x", encoding="utf-8")

    findings = validate_package(root)

    assert rule_ids(findings) == ["structure.checksums-unlisted"]
    assert findings[0].target is not None and findings[0].target.path == extra


def outside_copy(tmp_path: Path, relative: str) -> Path:
    """A copy of a fixture file or folder outside the package, for a symlink to point at."""
    source = FIXTURES / "valid" / relative
    target = tmp_path / "outside" / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target)
    else:
        shutil.copy(source, target)
    return target


@pytest.mark.parametrize(
    "relative",
    [
        "datapackage.json",
        "checksums.sha256",
        "docs/methods.md",
        "data/sites",
        "data/sites/sites.dbf",
    ],
)
def test_symlink_is_refused_and_not_followed(tmp_path: Path, relative: str) -> None:
    root = edited(tmp_path, lambda m: None)
    target = outside_copy(tmp_path, relative)
    link = root / relative
    if link.is_dir():
        shutil.rmtree(link)
    else:
        link.unlink()
    link.symlink_to(target)

    findings = validate_package(root)

    assert rule_ids(findings) == ["structure.symlink"]
    assert findings[0].target is not None and findings[0].target.path == relative


def test_unlisted_symlink_is_refused(tmp_path: Path) -> None:
    root = edited(tmp_path, lambda m: None)
    (root / "docs" / "elsewhere").symlink_to(outside_copy(tmp_path, "docs/methods.md"))

    assert rule_ids(validate_package(root)) == ["structure.symlink"]


def _hash_of(path: Path, algorithm: str) -> str:
    return hashlib.new(algorithm, path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "recorded",
    [
        lambda p: f"md5:{_hash_of(p, 'md5')}",
        lambda p: _hash_of(p, "md5"),
        lambda p: f"sha1:{_hash_of(p, 'sha1')}",
        lambda p: f"SHA256:{_hash_of(p, 'sha256')}",
        lambda p: f"sha512:{_hash_of(p, 'sha512')}",
    ],
)
def test_the_four_frictionless_hash_algorithms_are_accepted(
    tmp_path: Path, recorded: Callable[[Path], str]
) -> None:
    methods = FIXTURES / "valid" / "docs" / "methods.md"

    def edit(m: dict[str, Any]) -> None:
        m["resources"][3]["hash"] = recorded(methods)

    assert validate_package(edited(tmp_path, edit)) == []


@pytest.mark.parametrize("algorithm", ["shake_128", "shake_256", "sha224", "blake2b", "nope"])
def test_other_hash_algorithms_are_a_finding_not_an_exception(
    tmp_path: Path, algorithm: str
) -> None:
    def edit(m: dict[str, Any]) -> None:
        m["resources"][3]["hash"] = f"{algorithm}:abcdef"

    assert rule_ids(validate_package(edited(tmp_path, edit))) == ["structure.hash-algorithm"]


SITES_DBF = FIXTURES / "dbf" / "sites.dbf"
"""A real dBASE file with the columns site_id and elev_m."""


def with_attributes(tmp_path: Path, fields: list[dict[str, Any]], *, dbf: Path = SITES_DBF) -> Path:
    """The valid fixture with `dbf` as the sites shapefile's .dbf, described by `fields`."""

    def edit(m: dict[str, Any]) -> None:
        sites = m["resources"][2]
        sites["archive:attributes"] = {"fields": fields}
        member = next(f for f in sites["archive:files"] if f["path"].endswith(".dbf"))
        member["bytes"] = dbf.stat().st_size
        member["hash"] = f"sha256:{_hash_of(dbf, 'sha256')}"

    root = tmp_path / "package"
    shutil.copytree(FIXTURES / "valid", root)
    shutil.copy(dbf, root / "data" / "sites" / "sites.dbf")
    manifest_path = root / "datapackage.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    edit(manifest)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    write_checksums(root)
    return root


SITE_ID = {"name": "site_id", "type": "string"}
ELEV_M = {"name": "elev_m", "type": "number"}


def test_attributes_matching_the_dbf_have_no_findings(tmp_path: Path) -> None:
    assert validate_package(with_attributes(tmp_path, [SITE_ID, ELEV_M])) == []


def test_attribute_matched_by_its_source_name(tmp_path: Path) -> None:
    renamed = {"name": "elevation_m", "type": "number", "archive:sourceName": "elev_m"}

    assert validate_package(with_attributes(tmp_path, [SITE_ID, renamed])) == []


def test_attribute_described_but_absent_from_the_dbf(tmp_path: Path) -> None:
    extra = {"name": "habitat", "type": "string"}

    findings = validate_package(with_attributes(tmp_path, [SITE_ID, ELEV_M, extra]))

    assert rule_ids(findings) == ["structure.attributes-mismatch"]
    target = findings[0].target
    assert target is not None
    assert (target.resource, target.field, target.path) == (
        "sites",
        "habitat",
        "data/sites/sites.dbf",
    )


def test_dbf_column_not_described(tmp_path: Path) -> None:
    findings = validate_package(with_attributes(tmp_path, [SITE_ID]))

    assert rule_ids(findings) == ["structure.attributes-mismatch"]
    assert findings[0].target is not None and findings[0].target.field == "elev_m"


def test_unreadable_dbf_is_a_finding_not_an_exception(tmp_path: Path) -> None:
    findings = validate_package(
        with_attributes(tmp_path, [SITE_ID], dbf=FIXTURES / "valid" / "data/sites/sites.dbf")
    )

    assert rule_ids(findings) == ["structure.attributes-mismatch"]


def test_symlinked_dbf_is_refused_and_not_read(tmp_path: Path) -> None:
    root = with_attributes(tmp_path, [SITE_ID])
    outside = tmp_path / "outside.dbf"
    shutil.copy(SITES_DBF, outside)
    link = root / "data" / "sites" / "sites.dbf"
    link.unlink()
    link.symlink_to(outside)

    assert rule_ids(validate_package(root)) == ["structure.symlink"]


def test_vector_with_no_dbf_member_is_not_checked(tmp_path: Path) -> None:
    def edit(m: dict[str, Any]) -> None:
        sites = m["resources"][2]
        sites["archive:files"] = sites["archive:files"][:1]
        sites["archive:attributes"] = {"fields": [SITE_ID]}

    root = edited(tmp_path, edit)

    assert "structure.attributes-mismatch" not in rule_ids(validate_package(root))
