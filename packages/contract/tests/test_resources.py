import pytest
from pydantic import ValidationError

from archive_contract.resources import MemberFile, Resource


def test_resource_with_no_kind_reads_as_file() -> None:
    resource = Resource.model_validate({"name": "notes", "path": "docs/notes.txt"})

    assert resource.kind == "file"


def test_linked_resource_with_a_hash_is_refused() -> None:
    with pytest.raises(ValidationError, match="linked"):
        Resource.model_validate(
            {
                "name": "discharge",
                "path": "https://example.org/discharge.csv",
                "archive:kind": "linked",
                "hash": "sha256:" + "0" * 64,
            }
        )


def test_linked_resource_with_bytes_is_refused() -> None:
    with pytest.raises(ValidationError, match="linked"):
        Resource.model_validate(
            {
                "name": "discharge",
                "path": "https://example.org/discharge.csv",
                "archive:kind": "linked",
                "bytes": 10,
            }
        )


def test_linked_resource_needs_a_url_path() -> None:
    with pytest.raises(ValidationError, match="URL"):
        Resource.model_validate(
            {"name": "discharge", "path": "data/discharge.csv", "archive:kind": "linked"}
        )


def test_linked_resource_with_url_path_is_accepted() -> None:
    resource = Resource.model_validate(
        {
            "name": "discharge",
            "path": "https://example.org/discharge.csv",
            "archive:kind": "linked",
        }
    )

    assert resource.path == "https://example.org/discharge.csv"


def test_unknown_kind_is_refused() -> None:
    with pytest.raises(ValidationError):
        Resource.model_validate({"name": "x", "path": "x.bin", "archive:kind": "binary"})


def test_member_files_parse_from_archive_files() -> None:
    resource = Resource.model_validate(
        {
            "name": "sites",
            "path": "data/sites/sites.shp",
            "archive:kind": "vector",
            "archive:files": [
                {"path": "data/sites/sites.shp", "bytes": 100, "hash": "sha256:" + "a" * 64},
                {"path": "data/sites/sites.dbf", "bytes": 50, "hash": "sha256:" + "b" * 64},
            ],
        }
    )

    assert resource.files is not None
    assert [m.path for m in resource.files] == ["data/sites/sites.shp", "data/sites/sites.dbf"]
    assert resource.files[0] == MemberFile(
        path="data/sites/sites.shp", bytes=100, hash="sha256:" + "a" * 64
    )


def test_alternate_names_its_primary() -> None:
    resource = Resource.model_validate(
        {
            "name": "logger-xlsx",
            "path": "data/logger.xlsx",
            "archive:kind": "table",
            "archive:alternateOf": "logger",
        }
    )

    assert resource.alternate_of == "logger"


def test_alternate_carrying_a_schema_is_refused() -> None:
    with pytest.raises(ValidationError, match="primary"):
        Resource.model_validate(
            {
                "name": "logger-xlsx",
                "path": "data/logger.xlsx",
                "archive:kind": "table",
                "archive:alternateOf": "logger",
                "schema": {"fields": [{"name": "site", "type": "string"}]},
            }
        )


def test_dump_drops_unset_standard_properties_and_keeps_archive_nulls() -> None:
    dumped = Resource.model_validate({"name": "notes", "path": "docs/notes.txt"}).dump()

    assert "title" not in dumped
    assert "hash" not in dumped
    assert "schema" not in dumped
    assert dumped["archive:kind"] == "file"
    assert "archive:alternateOf" in dumped
    assert dumped["archive:alternateOf"] is None


def test_dump_writes_archive_names_and_the_schema_key() -> None:
    dumped = Resource.model_validate(
        {
            "name": "logger",
            "path": "data/logger.csv",
            "type": "table",
            "archive:kind": "table",
            "schema": {"fields": [{"name": "site", "type": "string"}]},
        }
    ).dump()

    assert dumped["schema"]["fields"][0]["name"] == "site"
    assert dumped["archive:kind"] == "table"
    assert "kind" not in dumped


def test_extra_properties_are_kept() -> None:
    raw = {"name": "notes", "path": "docs/notes.txt", "x-custom": {"a": 1}}

    assert Resource.model_validate(raw).dump()["x-custom"] == {"a": 1}
