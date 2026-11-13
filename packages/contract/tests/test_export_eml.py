"""The EML 2.2.0 export validates against the EML schema and carries the package's code lists."""

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from lxml import etree

from archive_contract.exports.eml import UNDOCUMENTED_CODES, to_eml
from archive_contract.manifest import Manifest
from archive_contract.project import Person, Project
from archive_contract.rights import RightsStatus

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"
XSD = Path(__file__).parent / "fixtures" / "schemas" / "eml-2.2.0" / "eml.xsd"


def sample() -> Manifest:
    return Manifest.model_validate_json((SAMPLE / "datapackage.json").read_text(encoding="utf-8"))


def assert_valid(xml: str) -> None:
    schema = etree.XMLSchema(etree.parse(str(XSD)))
    document = etree.fromstring(xml.encode("utf-8"))
    assert schema.validate(document), schema.error_log


def attribute(xml: str, table: str, name: str) -> ET.Element:
    root = ET.fromstring(xml)
    for data_table in root.iter("dataTable"):
        if data_table.findtext("entityName") == table:
            for attr in data_table.iter("attribute"):
                if attr.findtext("attributeName") == name:
                    return attr
    raise AssertionError(f"no attribute {table}.{name}")


def test_sample_export_validates_against_eml_2_2_0() -> None:
    assert_valid(to_eml(sample(), root=SAMPLE))


def test_export_with_a_project_and_a_rights_statement_validates() -> None:
    manifest = sample().model_copy(
        update={
            "project": "streams",
            "licenses": None,
            "rights_status": RightsStatus(status="all-rights-reserved", statement="(c) Example"),
        }
    )
    project = Project(
        id="streams",
        title="Invented stream monitoring",
        abstract="Monitoring of invented streams.",
        people=[Person(name="Cy Example", roles=["principalInvestigator"])],
    )
    xml = to_eml(manifest, project, root=SAMPLE)

    assert_valid(xml)
    root = ET.fromstring(xml)
    assert root.findtext("dataset/project/title") == "Invented stream monitoring"
    assert root.findtext("dataset/intellectualRights/para") == "(c) Example"


def test_dataset_carries_title_creator_abstract_keywords_and_coverage() -> None:
    root = ET.fromstring(to_eml(sample(), root=SAMPLE))
    dataset = root.find("dataset")
    assert dataset is not None

    assert dataset.findtext("title") == "Stream temperature at three invented sites"
    assert dataset.findtext("creator/individualName/surName") == "Invented"
    assert [k.text for k in dataset.iter("keyword")] == [
        "stream temperature",
        "water quality",
        "loggers",
    ]
    assert dataset.findtext("licensed/identifier") == "CC-BY-4.0"
    box = dataset.find("coverage/geographicCoverage/boundingCoordinates")
    assert box is not None and box.findtext("westBoundingCoordinate") == "-72.74"


def test_code_list_column_is_an_enumerated_domain() -> None:
    attr = attribute(to_eml(sample(), root=SAMPLE), "logger", "condition")

    codes = [c.findtext("code") for c in attr.iter("codeDefinition")]
    assert codes == ["ok", "drift", "buried", "dry"]


def test_undocumented_code_list_is_a_text_domain_with_a_note() -> None:
    attr = attribute(to_eml(sample(), root=SAMPLE), "logger", "qc_flag")

    assert attr.find(".//enumeratedDomain") is None
    assert attr.findtext(".//textDomain/definition") == UNDOCUMENTED_CODES


def test_every_other_local_resource_is_an_other_entity() -> None:
    root = ET.fromstring(to_eml(sample(), root=SAMPLE))

    tables = [t.findtext("entityName") for t in root.iter("dataTable")]
    others = [o.findtext("entityName") for o in root.iter("otherEntity")]
    assert tables == ["logger", "condition-codes"]
    assert others == ["sites", "depth", "logger-xlsx", "logger-original", "methods", "site-photo"]


def test_a_code_list_column_needs_the_package_folder() -> None:
    with pytest.raises(ValueError, match="condition-codes"):
        to_eml(sample())
