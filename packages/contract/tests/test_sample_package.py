"""The committed sample package passes our structural validation and the frictionless library."""

import json
from pathlib import Path
from typing import Any

import frictionless
import pytest
import requests

from archive_contract.changes import read_changes
from archive_contract.manifest import Manifest
from archive_contract.validate import validate_package

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"


def manifest() -> Manifest:
    return Manifest.model_validate_json((SAMPLE / "datapackage.json").read_text(encoding="utf-8"))


def is_url(path: object) -> bool:
    return isinstance(path, str) and path.startswith(("http://", "https://"))


@pytest.fixture
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(f"remote fetch attempted: {args[1:3]}")

    monkeypatch.setattr(requests.Session, "request", refuse)


def test_sample_is_structurally_valid() -> None:
    assert validate_package(SAMPLE) == []


@pytest.mark.usefixtures("no_network")
def test_sample_passes_frictionless_without_fetching_the_linked_resource() -> None:
    descriptor = json.loads((SAMPLE / "datapackage.json").read_text(encoding="utf-8"))

    descriptor_report = frictionless.Package.validate_descriptor(descriptor, basepath=str(SAMPLE))
    assert descriptor_report.valid, descriptor_report.flatten(["type", "note"])

    package = frictionless.Package(descriptor, basepath=str(SAMPLE))
    remote = [r.name for r in package.resources if is_url(r.path)]
    checked = []
    for resource in package.resources:
        if resource.name in remote:
            continue
        report = resource.validate()
        assert report.valid, (resource.name, report.flatten(["rowNumber", "type", "note"]))
        checked.append(resource.name)

    assert "logger" in checked
    assert remote == ["discharge"]


def test_sample_has_every_kind_of_resource() -> None:
    kinds = {r.kind for r in manifest().resources}

    assert {"table", "vector", "raster", "document", "media", "linked"} <= kinds


def test_sample_states_its_license_and_ongoing_coverage() -> None:
    m = manifest()

    assert m.licenses is not None and m.licenses[0].name == "CC-BY-4.0"
    assert m.temporal_coverage is not None and m.temporal_coverage.ongoing
    assert m.spatial_coverage is not None


def test_sample_xlsx_is_an_alternate_of_the_logger_table() -> None:
    xlsx = manifest().resource("logger-xlsx")

    assert xlsx is not None and xlsx.alternate_of == "logger" and xlsx.table_schema is None


def test_sample_records_one_accepted_rename() -> None:
    [change] = read_changes(SAMPLE / "changes.jsonl")
    logger = manifest().resource("logger")
    assert logger is not None and logger.table_schema is not None
    renamed = {f.name: f for f in logger.table_schema.fields}[change.after]

    assert change.kind == "rename"
    assert change.accepted_by is not None and change.accepted_by.kind == "person"
    assert renamed.source_name == change.before


def test_sample_seeds_the_gaps_its_gap_list_names() -> None:
    logger = manifest().resource("logger")
    assert logger is not None and logger.table_schema is not None
    fields = logger.table_schema.fields
    gaps = (SAMPLE / "_build" / "GAPS.md").read_text(encoding="utf-8")

    no_description = [f.name for f in fields if not f.description]
    repeats_name = [f.name for f in fields if f.description == f.name]
    undocumented = [f.name for f in fields if f.code_list == "undocumented"]
    rows = (SAMPLE / "data" / "logger.csv").read_text(encoding="utf-8").splitlines()
    header = rows[0].split(",")
    columns = list(zip(*(row.split(",") for row in rows[1:]), strict=True))
    constant = [header[i] for i, values in enumerate(columns) if len(set(values)) == 1]

    assert len(rows) - 1 >= 50
    for gap in [no_description, repeats_name, undocumented, constant]:
        assert len(gap) == 1
        assert f"`{gap[0]}`" in gaps
