"""The DataCite record carries DataCite 4.x's mandatory properties and refuses unpublishable
rights.

DataCite publishes no official, licensed JSON Schema (the one in `datacite/schema` is
unofficial and unlicensed), so the mandatory properties and their shapes are checked here
against the DataCite Metadata Schema 4.x documentation:
https://datacite-metadata-schema.readthedocs.io/en/4.6/properties/overview/
"""

import re
from pathlib import Path
from typing import Any

import pytest

from archive_contract.exports.datacite import to_datacite
from archive_contract.manifest import Manifest, TemporalCoverage
from archive_contract.project import Link, Project
from archive_contract.rights import RightsStatus

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"
RESOURCE_TYPES_GENERAL = {
    "Audiovisual", "Award", "Book", "BookChapter", "Collection", "ComputationalNotebook",
    "ConferencePaper", "ConferenceProceeding", "DataPaper", "Dataset", "Dissertation", "Event",
    "Image", "Instrument", "InteractiveResource", "Journal", "JournalArticle", "Model",
    "OutputManagementPlan", "PeerReview", "PhysicalObject", "Preprint", "Project", "Report",
    "Service", "Software", "Sound", "Standard", "StudyRegistration", "Text", "Workflow", "Other",
}  # fmt: skip


def sample() -> Manifest:
    return Manifest.model_validate_json((SAMPLE / "datapackage.json").read_text(encoding="utf-8"))


def record(manifest: Manifest, **kwargs: Any) -> dict[str, Any]:
    return to_datacite(manifest, publisher="Example Archive", year=2024, **kwargs)


def nonempty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def validate(data: dict[str, Any]) -> None:
    """DataCite 4.x's mandatory properties, in their JSON shapes, plus rightsList."""
    for identifier in data.get("identifiers", []):
        assert nonempty_str(identifier.get("identifier")), identifier
        assert nonempty_str(identifier.get("identifierType")), identifier
    creators = data.get("creators")
    assert isinstance(creators, list) and creators, "creators is mandatory"
    assert all(nonempty_str(c.get("name")) for c in creators), creators
    titles = data.get("titles")
    assert isinstance(titles, list) and titles, "titles is mandatory"
    assert all(nonempty_str(t.get("title")) for t in titles), titles
    publisher = data.get("publisher")
    if isinstance(publisher, dict):  # 4.5 and later write an object
        publisher = publisher.get("name")
    assert nonempty_str(publisher), "publisher is mandatory"
    assert re.fullmatch(r"\d{4}", str(data.get("publicationYear", ""))), "publicationYear"
    assert data.get("types", {}).get("resourceTypeGeneral") in RESOURCE_TYPES_GENERAL
    rights = data.get("rightsList")
    assert isinstance(rights, list) and rights, "rightsList must be present"
    assert all(
        nonempty_str(r.get("rights")) or nonempty_str(r.get("rightsIdentifier")) for r in rights
    ), rights


def test_sample_record_has_the_mandatory_properties() -> None:
    validate(record(sample()))


def test_a_record_without_rights_or_creators_fails_the_check() -> None:
    data = record(sample())

    for key in ("rightsList", "creators", "titles", "publicationYear"):
        broken = {k: v for k, v in data.items() if k != key}
        with pytest.raises(AssertionError):
            validate(broken)


def test_sample_record_carries_the_manifest() -> None:
    data = record(sample(), identifier="10.1234/example")

    assert data["identifiers"] == [{"identifier": "10.1234/example", "identifierType": "DOI"}]
    assert data["titles"] == [{"title": "Stream temperature at three invented sites"}]
    assert data["creators"][0]["name"] == "Ada Invented"
    assert data["publisher"] == "Example Archive"
    assert data["publicationYear"] == "2024"
    assert data["types"]["resourceTypeGeneral"] == "Dataset"
    assert [d["descriptionType"] for d in data["descriptions"]] == ["Abstract", "Methods", "Other"]
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


def test_purpose_is_a_description_of_type_other() -> None:
    manifest = sample()

    assert manifest.purpose
    descriptions = record(manifest)["descriptions"]
    assert {"description": manifest.purpose, "descriptionType": "Other"} in descriptions


def test_unknown_end_is_an_open_date_range() -> None:
    manifest = sample().model_copy(
        update={
            "temporal_coverage": TemporalCoverage.model_validate(
                {"start": "1991-01-01", "end": "unknown"}
            )
        }
    )

    assert record(manifest)["dates"] == [{"date": "1991-01-01/", "dateType": "Collected"}]
