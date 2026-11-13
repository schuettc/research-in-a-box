"""The DataCite record validates against DataCite's JSON Schema and refuses unpublishable rights."""

import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

from archive_contract.exports.datacite import to_datacite
from archive_contract.manifest import Manifest
from archive_contract.project import Link, Project
from archive_contract.rights import RightsStatus

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"
SCHEMA = Path(__file__).parent / "fixtures" / "schemas" / "datacite" / "datacite_4.3_schema.json"


def sample() -> Manifest:
    return Manifest.model_validate_json((SAMPLE / "datapackage.json").read_text(encoding="utf-8"))


def record(manifest: Manifest, **kwargs: Any) -> dict[str, Any]:
    return to_datacite(manifest, publisher="Example Archive", year=2024, **kwargs)


def validate(data: dict[str, Any]) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator(schema).validate(data)


def test_sample_record_validates() -> None:
    validate(record(sample()))


def test_sample_record_carries_the_manifest() -> None:
    data = record(sample(), identifier="10.1234/example")

    assert data["identifiers"] == [{"identifier": "10.1234/example", "identifierType": "DOI"}]
    assert data["titles"] == [{"title": "Stream temperature at three invented sites"}]
    assert data["creators"][0]["name"] == "Ada Invented"
    assert data["publisher"] == "Example Archive"
    assert data["publicationYear"] == "2024"
    assert data["types"]["resourceTypeGeneral"] == "Dataset"
    assert [d["descriptionType"] for d in data["descriptions"]] == ["Abstract", "Methods"]
    assert {"date": "2024-06-01/", "dateType": "Collected"} in data["dates"]
    assert data["geoLocations"][0]["geoLocationBox"]["westBoundLongitude"] == -72.74
    assert data["rightsList"][0]["rightsIdentifier"] == "CC-BY-4.0"
    assert data["version"] == "1"
    validate(data)


def test_project_is_a_related_identifier_of_type_is_part_of() -> None:
    project = Project(
        id="streams",
        title="Invented stream monitoring",
        links=[Link(url="https://example.org/streams")],
    )
    data = record(sample().model_copy(update={"project": "streams"}), project=project)

    assert {
        "relatedIdentifier": "https://example.org/streams",
        "relatedIdentifierType": "URL",
        "relationType": "IsPartOf",
    } in data["relatedIdentifiers"]
    assert {
        "description": "Invented stream monitoring",
        "descriptionType": "SeriesInformation",
    } in data["descriptions"]
    validate(data)


def test_undetermined_rights_are_refused() -> None:
    manifest = sample().model_copy(
        update={"licenses": None, "rights_status": RightsStatus(status="undetermined")}
    )

    with pytest.raises(ValueError, match="undetermined"):
        record(manifest)


def test_third_party_rights_write_their_statement() -> None:
    statement = "Terms set by the Example Water Authority: https://example.org/terms"
    manifest = sample().model_copy(
        update={
            "licenses": None,
            "rights_status": RightsStatus(status="third-party", statement=statement),
        }
    )
    data = record(manifest)

    assert data["rightsList"] == [{"rights": statement}]
    validate(data)
