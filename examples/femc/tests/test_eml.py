from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from archive_contract.exports.eml import END_UNKNOWN, PROJECT_KEYWORDS
from archive_contract.imports.eml import from_eml
from femc.eml import standardize

FIXTURES = Path(__file__).parent / "fixtures" / "eml"


def record(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def local(element: ET.Element) -> str:
    return element.tag.rpartition("}")[2]


def find(element: ET.Element, path: str) -> list[ET.Element]:
    """The elements at a slash-separated path of local names below `element`."""
    found = [element]
    for name in path.split("/"):
        found = [c for e in found for c in e if local(c) == name]
    return found


def text(element: ET.Element) -> str:
    return " ".join("".join(element.itertext()).split())


def standardized(name: str) -> ET.Element:
    return ET.fromstring(standardize(record(name)).xml)


def test_research_project_becomes_project() -> None:
    root = standardized("femc-full.xml")

    assert find(root, "dataset/researchProject") == []
    assert [text(t) for t in find(root, "dataset/project/title")] == [
        "Invented Stream Insect Survey"
    ]


def test_table_title_description_purpose_and_coverage_move_up() -> None:
    root = standardized("femc-full.xml")

    assert [text(e) for e in find(root, "dataset/title")] == ["Invented Insect Counts"]
    assert [text(e) for e in find(root, "dataset/abstract/para")] == [
        "Counts of invented insects at invented stream sites, one row per visit."
    ]
    assert [text(e) for e in find(root, "dataset/purpose/para")] == [
        "Test that every part of an invented FEMC record is read or listed."
    ]
    assert len(find(root, "dataset/coverage/temporalCoverage")) == 1
    table = find(root, "dataset/dataTable")[0]
    assert [local(c) for c in table] == [
        "entityName",
        "entityDescription",
        "physical",
        "attributeList",
    ]
    assert text(find(table, "entityName")[0]) == "Invented Insect Counts"
    assert text(find(table, "entityDescription")[0]).startswith("Counts of invented insects")


def test_a_non_empty_short_name_is_dropped_and_reported() -> None:
    result = standardize(record("femc-full.xml"))

    assert result.dropped == [
        "dataset/dataTable/shortName: not standard EML, dropped: Z9001_insects"
    ]


def test_an_empty_purpose_short_name_and_personnel_go_silently() -> None:
    result = standardize(record("femc-closed.xml"))
    root = ET.fromstring(result.xml)

    assert result.dropped == []
    assert find(root, "dataset/purpose") == []
    assert find(root, "dataset/dataTable/shortName") == []
    assert find(root, "dataset/project/personnel") == []


def test_role_named_personnel_become_individual_names_with_roles() -> None:
    root = standardized("femc-full.xml")

    people = [
        (
            text(find(p, "individualName/givenName")[0]),
            text(find(p, "individualName/surName")[0]),
            text(find(p, "role")[0]),
        )
        for p in find(root, "dataset/project/personnel")
    ]
    assert people == [
        ("Ada", "Placeholder", "principalInvestigator"),
        ("Ben", "Example", "contentProvider"),
    ]


def test_project_keywords_become_the_project_keywords_descriptor() -> None:
    root = standardized("femc-full.xml")

    assert find(root, "dataset/project/keywordSet") == []
    descriptor = find(root, "dataset/project/studyAreaDescription/descriptor")[0]
    assert descriptor.get("name") == PROJECT_KEYWORDS
    assert [text(v) for v in find(descriptor, "descriptorValue")] == ["insects", "streams"]


def test_publisher_metadata_provider_moves_up_into_publisher() -> None:
    root = standardized("femc-full.xml")

    publisher = find(root, "dataset/publisher")[0]
    assert find(publisher, "metadataProvider") == []
    assert text(find(publisher, "organizationName")[0]) == "Invented Monitoring Cooperative"
    assert text(find(publisher, "address/city")[0]) == "Nowhere"


def test_measurement_type_becomes_measurement_scale_with_its_domain() -> None:
    root = standardized("femc-full.xml")

    attributes = find(root, "dataset/dataTable/attributeList/attribute")
    assert find(root, "dataset/dataTable/attributeList/attribute/measurementType") == []
    habitat = attributes[2]
    assert find(habitat, "enumeratedDomain") == []
    codes = find(
        habitat, "measurementScale/nominal/nonNumericDomain/enumeratedDomain/codeDefinition"
    )
    assert [text(find(c, "code")[0]) for c in codes] == ["R", "P", "-1"]
    assert find(attributes[1], "measurementScale/dateTime/formatString") != []
    assert find(attributes[3], "measurementScale") == []


def test_distibution_becomes_distribution() -> None:
    root = standardized("femc-full.xml")

    assert find(root, "dataset/dataTable/physical/distibution") == []
    assert len(find(root, "dataset/dataTable/physical/distribution/online/url")) == 1


def test_a_begin_date_alone_gets_the_end_unknown_marker() -> None:
    root = standardized("femc-full.xml")

    assert find(root, "dataset/coverage/temporalCoverage/rangeOfDates") == []
    single = find(root, "dataset/coverage/temporalCoverage/singleDateTime/calendarDate")
    assert [text(d) for d in single] == ["1999-05-01"]
    assert [text(d) for d in find(root, "dataset/maintenance/description")] == [END_UNKNOWN]
    assert [text(d) for d in find(root, "dataset/maintenance/maintenanceUpdateFrequency")] == [
        "unknown"
    ]


def test_a_full_range_is_left_as_it_is() -> None:
    root = standardized("femc-closed.xml")

    assert len(find(root, "dataset/coverage/temporalCoverage/rangeOfDates/endDate")) == 1
    assert find(root, "dataset/maintenance") == []


def test_the_citation_is_removed_and_returned() -> None:
    result = standardize(record("femc-full.xml"))

    assert find(ET.fromstring(result.xml), "dataset/dataTable/physical/citation") == []
    assert result.citation == (
        "Placeholder, A. 2001. Invented Insect Counts. Invented Monitoring Cooperative. "
        "Can be found at: https://example.org/imc/dataset/invented-insect-counts"
    )
    assert result.object_name == "VMC.9001.9002"


def test_an_empty_citation_is_none() -> None:
    assert standardize(record("femc-closed.xml")).citation is None


def test_a_record_with_a_doctype_is_refused() -> None:
    with pytest.raises(ValueError, match="DOCTYPE"):
        standardize('<?xml version="1.0"?><!DOCTYPE eml [<!ENTITY a "b">]><eml/>')


def test_from_eml_reads_the_whole_standardized_record() -> None:
    result = standardize(record("femc-full.xml"))
    imported = from_eml(result.xml)
    manifest = imported.manifest

    assert manifest.title == "Invented Insect Counts"
    assert manifest.description == (
        "Counts of invented insects at invented stream sites, one row per visit."
    )
    assert manifest.purpose == "Test that every part of an invented FEMC record is read or listed."
    assert manifest.temporal_coverage is not None
    assert manifest.temporal_coverage.dump() == {
        "start": "1999-05-01",
        "end": "unknown",
        "ongoing": False,
    }
    assert [c.title for c in manifest.contributors or []] == ["Invented University"]
    assert imported.project is not None
    assert imported.project.title == "Invented Stream Insect Survey"
    assert imported.project.keywords == ["insects", "streams"]
    assert [(p.name, p.roles) for p in imported.project.people] == [
        ("Ada Placeholder", ["principalInvestigator"]),
        ("Ben Example", ["contentProvider"]),
    ]
    tables = [r for r in manifest.resources if r.name == "invented-insect-counts"]
    assert len(tables) == 1
    schema = tables[0].table_schema
    assert schema is not None
    assert [f.dump() for f in schema.fields] == [
        {
            "name": "COUNT",
            "type": "integer",
            "description": "Number of insects counted in the kick net",
            "archive:sourceName": None,
            "archive:codeList": None,
            "archive:sensitivity": None,
            "archive:unit": None,
            "archive:measurementScale": "ratio",
            "archive:ancillaryOf": None,
        },
        {
            "name": "VISIT_DATE",
            "type": "date",
            "format": "%d/%m/%Y",
            "description": "Date of the visit",
            "archive:sourceName": None,
            "archive:codeList": None,
            "archive:sensitivity": None,
            "archive:unit": None,
            "archive:measurementScale": "dateTime",
            "archive:ancillaryOf": None,
        },
        {
            "name": "HABITAT",
            "type": "string",
            "title": "Habitat",
            "description": "Habitat code at the site",
            "archive:sourceName": None,
            "archive:codeList": None,
            "archive:sensitivity": None,
            "archive:unit": None,
            "archive:measurementScale": "nominal",
            "archive:ancillaryOf": None,
        },
        {
            "name": "SITE",
            "archive:sourceName": None,
            "archive:codeList": None,
            "archive:sensitivity": None,
            "archive:unit": None,
            "archive:measurementScale": None,
            "archive:ancillaryOf": None,
        },
    ]
    assert imported.code_lists == {
        "habitat-codes": [
            {"code": "R", "label": "Riffle", "description": ""},
            {"code": "P", "label": "Pool", "description": ""},
            {"code": "-1", "label": "No data", "description": ""},
        ]
    }
    assert imported.skipped == [
        "dataset/publisher: not read",
        "dataset/project/shortName: not standard EML",
        "dataset/dataTable/physical/distribution: not read",
        "dataset/dataTable/physical/dataFormat/formatName: not standard EML",
    ]
