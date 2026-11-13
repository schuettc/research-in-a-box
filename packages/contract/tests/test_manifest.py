from typing import Any

import pytest
from pydantic import ValidationError

from archive_contract.manifest import CORE_FIELDS, Manifest, missing_core_fields

LONG_DESCRIPTION = "Hourly water temperature at three invented stream sites, 2024 onward."


def complete() -> dict[str, Any]:
    return {
        "id": "stream-temperature",
        "version": "1",
        "title": "Stream temperature",
        "description": LONG_DESCRIPTION,
        "contributors": [{"title": "A. Researcher", "roles": ["creator"]}],
        "licenses": [{"name": "CC-BY-4.0"}],
        "resources": [
            {"name": "logger", "path": "data/logger.csv", "description": "Logger readings"}
        ],
    }


def test_complete_manifest_misses_no_core_field() -> None:
    assert missing_core_fields(Manifest.model_validate(complete())) == []


def test_empty_manifest_parses_and_misses_every_core_field() -> None:
    manifest = Manifest.model_validate({})

    assert missing_core_fields(manifest) == list(CORE_FIELDS)
    assert list(CORE_FIELDS) == ["title", "description", "creator", "rights", "resources"]


def test_short_description_counts_as_missing() -> None:
    raw = complete() | {"description": "Too short."}

    assert missing_core_fields(Manifest.model_validate(raw)) == ["description"]


def test_contributor_without_creator_role_is_no_creator() -> None:
    raw = complete() | {"contributors": [{"title": "B. Helper", "roles": ["contributor"]}]}

    assert missing_core_fields(Manifest.model_validate(raw)) == ["creator"]


def test_undetermined_rights_count_as_missing() -> None:
    raw = complete()
    del raw["licenses"]
    raw["archive:rightsStatus"] = {"status": "undetermined"}

    assert missing_core_fields(Manifest.model_validate(raw)) == ["rights"]


def test_a_stated_rights_status_counts_as_rights() -> None:
    raw = complete()
    del raw["licenses"]
    raw["archive:rightsStatus"] = {"status": "third-party", "statement": "Set by the agency"}

    assert missing_core_fields(Manifest.model_validate(raw)) == []


def test_resource_with_no_description_or_title_is_not_described() -> None:
    raw = complete() | {"resources": [{"name": "logger", "path": "data/logger.csv"}]}

    assert missing_core_fields(Manifest.model_validate(raw)) == ["resources"]


@pytest.mark.parametrize("version", ["1", "2", "17"])
def test_version_is_an_integer_string(version: str) -> None:
    assert Manifest.model_validate({"version": version}).version == version


def test_integer_version_is_written_as_a_string() -> None:
    assert Manifest.model_validate({"version": 3}).dump()["version"] == "3"


@pytest.mark.parametrize("version", ["0", "1.0.0", "v2", "01", ""])
def test_other_versions_are_refused(version: str) -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"version": version})


def test_dump_drops_unset_standard_properties_and_keeps_archive_nulls() -> None:
    dumped = Manifest.model_validate({"title": "T"}).dump()

    assert "description" not in dumped
    assert "licenses" not in dumped
    assert "version" not in dumped
    assert dumped["archive:project"] is None
    assert dumped["archive:access"] is None
    assert dumped["archive:validation"] is None


def test_dump_round_trips() -> None:
    raw = complete() | {
        "archive:project": "stream-monitoring",
        "archive:access": "open",
        "archive:temporalCoverage": {"start": "2024-06-01", "ongoing": True},
        "archive:spatialCoverage": {"bbox": [-72.9, 44.1, -72.6, 44.4]},
        "archive:legacyIdentifiers": [{"scheme": "eml-package-id", "value": "knb-lter-xyz.12.3"}],
        "archive:metadataHistory": [
            {"when": "2026-11-13T10:00:00Z", "who": "A. Researcher", "fields": ["title"]}
        ],
        "archive:validation": {
            "valid": True,
            "contractVersion": "0.1.0",
            "checkedAt": "2026-11-13T10:00:00Z",
        },
        "archive:quality": {
            "errors": 0,
            "warnings": 3,
            "notes": 1,
            "auditedAt": "2026-11-13T10:00:00Z",
        },
        "x-extra": [1, 2],
    }
    manifest = Manifest.model_validate(raw)

    dumped = manifest.dump()

    assert Manifest.model_validate(dumped) == manifest
    assert dumped["x-extra"] == [1, 2]
    assert dumped["archive:spatialCoverage"]["bbox"] == [-72.9, 44.1, -72.6, 44.4]
    assert dumped["archive:temporalCoverage"] == {"start": "2024-06-01", "ongoing": True}


def test_validation_and_quality_are_separate_verdicts() -> None:
    manifest = Manifest.model_validate(
        {
            "archive:validation": {
                "valid": True,
                "contractVersion": "0.1.0",
                "checkedAt": "2026-11-13T10:00:00Z",
            },
            "archive:quality": {
                "errors": 4,
                "warnings": 0,
                "notes": 0,
                "auditedAt": "2026-11-13T10:00:00Z",
            },
        }
    )

    assert manifest.validation is not None and manifest.validation.valid
    assert manifest.quality is not None and manifest.quality.errors == 4


def test_legacy_identifiers_are_scheme_and_value() -> None:
    manifest = Manifest.model_validate(
        {"archive:legacyIdentifiers": [{"scheme": "eml-package-id", "value": "knb-lter-xyz.12.3"}]}
    )

    assert manifest.legacy_identifiers is not None
    assert manifest.legacy_identifiers[0].scheme == "eml-package-id"
    with pytest.raises(ValidationError):
        Manifest.model_validate({"archive:legacyIdentifiers": [{"value": "x"}]})


@pytest.mark.parametrize("level", ["open", "restricted", "by-request", "description-only"])
def test_access_takes_the_four_levels(level: str) -> None:
    assert Manifest.model_validate({"archive:access": level}).access == level


def test_unpublished_is_not_an_access_level() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"archive:access": "unpublished"})


def test_project_is_named_by_id_never_copied() -> None:
    assert Manifest.model_validate({"archive:project": "p1"}).project == "p1"
    with pytest.raises(ValidationError):
        Manifest.model_validate({"archive:project": {"id": "p1", "title": "Copied"}})


def test_coverage_can_be_ongoing_without_an_end() -> None:
    manifest = Manifest.model_validate(
        {"archive:temporalCoverage": {"start": "2024-06-01", "ongoing": True}}
    )

    assert manifest.temporal_coverage is not None
    assert manifest.temporal_coverage.ongoing
    assert manifest.temporal_coverage.end is None


def test_coverage_with_an_end_and_ongoing_is_refused() -> None:
    with pytest.raises(ValidationError, match="ongoing"):
        Manifest.model_validate(
            {
                "archive:temporalCoverage": {
                    "start": "2024-06-01",
                    "end": "2024-09-01",
                    "ongoing": True,
                }
            }
        )


def test_coverage_ending_before_it_starts_is_refused() -> None:
    with pytest.raises(ValidationError, match="before"):
        Manifest.model_validate(
            {"archive:temporalCoverage": {"start": "2024-06-01", "end": "2024-01-01"}}
        )


@pytest.mark.parametrize(
    "bbox",
    [[-72.9, 44.4, -72.6, 44.1], [-190.0, 44.1, -72.6, 44.4], [-72.9, -91.0, -72.6, 44.4]],
)
def test_bounding_box_out_of_range_or_upside_down_is_refused(bbox: list[float]) -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"archive:spatialCoverage": {"bbox": bbox}})


def test_bounding_box_needs_four_numbers() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"archive:spatialCoverage": {"bbox": [1.0, 2.0, 3.0]}})


def test_recommended_fields_parse() -> None:
    manifest = Manifest.model_validate(
        {
            "keywords": ["stream temperature"],
            "archive:relatedIdentifiers": [
                {
                    "identifier": "10.1234/abc",
                    "identifierType": "DOI",
                    "relationType": "IsSupplementTo",
                }
            ],
            "archive:funding": [{"funder": "Invented Foundation", "awardNumber": "X-1"}],
            "archive:methods": "Loggers read every hour.",
        }
    )

    assert manifest.related_identifiers is not None
    assert manifest.related_identifiers[0].relation_type == "IsSupplementTo"
    assert manifest.funding is not None and manifest.funding[0].award_number == "X-1"
    assert manifest.methods == "Loggers read every hour."


def test_coverage_with_a_start_alone_is_refused() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate({"archive:temporalCoverage": {"start": "2024-06-01"}})


def test_coverage_can_end_unknown() -> None:
    manifest = Manifest.model_validate(
        {"archive:temporalCoverage": {"start": "1991-01-01", "end": "unknown"}}
    )

    assert manifest.temporal_coverage is not None
    assert manifest.temporal_coverage.end == "unknown"
    assert manifest.dump()["archive:temporalCoverage"] == {
        "start": "1991-01-01",
        "end": "unknown",
        "ongoing": False,
    }


def test_coverage_ending_unknown_and_ongoing_is_refused() -> None:
    with pytest.raises(ValidationError, match="ongoing"):
        Manifest.model_validate(
            {"archive:temporalCoverage": {"start": "1991-01-01", "end": "unknown", "ongoing": True}}
        )


def test_coverage_end_refuses_other_words() -> None:
    with pytest.raises(ValidationError):
        Manifest.model_validate(
            {"archive:temporalCoverage": {"start": "1991-01-01", "end": "someday"}}
        )


def test_citation_and_purpose_parse_and_dump() -> None:
    manifest = Manifest.model_validate(
        {"archive:citation": "Researcher, A. (2026). Streams.", "archive:purpose": "To track."}
    )

    assert manifest.citation == "Researcher, A. (2026). Streams."
    assert manifest.purpose == "To track."
    assert manifest.dump()["archive:purpose"] == "To track."
