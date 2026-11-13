"""The schema.org Dataset carries what Google Dataset Search requires and recommends."""

from pathlib import Path

from archive_contract.exports.schemaorg import to_schemaorg
from archive_contract.manifest import Manifest, TemporalCoverage
from archive_contract.project import Link, Project

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"


def sample() -> Manifest:
    return Manifest.model_validate_json((SAMPLE / "datapackage.json").read_text(encoding="utf-8"))


def test_google_required_name_and_description_are_present() -> None:
    data = to_schemaorg(sample())

    assert data["@context"] == "https://schema.org/"
    assert data["@type"] == "Dataset"
    assert data["name"] == "Stream temperature at three invented sites"
    assert 50 <= len(data["description"]) <= 5000


def test_ongoing_coverage_is_an_open_interval() -> None:
    assert to_schemaorg(sample())["temporalCoverage"] == "2024-06-01/.."


def test_closed_coverage_is_a_closed_interval() -> None:
    manifest = sample().model_copy(
        update={
            "temporal_coverage": TemporalCoverage.model_validate(
                {"start": "2024-06-01", "end": "2024-06-30"}
            )
        }
    )

    assert to_schemaorg(manifest)["temporalCoverage"] == "2024-06-01/2024-06-30"


def test_spatial_coverage_is_a_geoshape_box() -> None:
    place = to_schemaorg(sample())["spatialCoverage"]

    assert place["@type"] == "Place"
    assert place["geo"] == {"@type": "GeoShape", "box": "44.23 -72.74 44.32 -72.66"}


def test_distribution_lists_local_files_and_the_linked_resource() -> None:
    data = to_schemaorg(sample(), url="https://archive.example.org/p/stream-temperature-sample/")
    by_name = {d["name"]: d for d in data["distribution"]}

    assert by_name["logger"]["@type"] == "DataDownload"
    assert by_name["logger"]["encodingFormat"] == "text/csv"
    assert by_name["logger"]["contentUrl"] == (
        "https://archive.example.org/p/stream-temperature-sample/data/logger.csv"
    )
    assert by_name["discharge"]["contentUrl"] == (
        "https://example.org/stream-temperature/discharge.csv"
    )


def test_license_creator_keywords_version_identifier_and_project() -> None:
    project = Project(
        id="streams", title="Invented stream monitoring", links=[Link(url="https://example.org/s")]
    )
    data = to_schemaorg(sample().model_copy(update={"project": "streams"}), project=project)

    assert data["license"] == "https://creativecommons.org/licenses/by/4.0/"
    assert data["creator"] == [
        {
            "@type": "Person",
            "name": "Ada Invented",
            "affiliation": {"@type": "Organization", "name": "Example Lab"},
        }
    ]
    assert data["keywords"] == ["stream temperature", "water quality", "loggers"]
    assert data["version"] == "1"
    assert data["identifier"] == "stream-temperature-sample"
    assert data["isPartOf"] == {
        "@type": "CreativeWork",
        "name": "Invented stream monitoring",
        "url": "https://example.org/s",
    }
