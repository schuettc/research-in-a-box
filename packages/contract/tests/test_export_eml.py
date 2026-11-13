"""The EML 2.2.0 export validates against the EML schema and carries the package's code lists."""

from pathlib import Path
from xml.etree import ElementTree as ET

import pytest
from lxml import etree

from archive_contract.exports.eml import UNDOCUMENTED_CODES, shp_geometry, to_eml
from archive_contract.manifest import Manifest, TemporalCoverage
from archive_contract.project import Person, Project
from archive_contract.resources import Resource
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
    vectors = [v.findtext("entityName") for v in root.iter("spatialVector")]
    others = [o.findtext("entityName") for o in root.iter("otherEntity")]
    assert tables == ["logger", "condition-codes"]
    assert vectors == ["sites"]
    assert others == ["depth", "logger-xlsx", "logger-original", "methods", "site-photo"]


def test_a_code_list_column_needs_the_package_folder() -> None:
    with pytest.raises(ValueError, match="condition-codes"):
        to_eml(sample())


def test_a_unit_replaces_unknown() -> None:
    attr = attribute(to_eml(sample(), root=SAMPLE), "logger", "water_temp_c")

    assert attr.findtext("measurementScale/interval/unit/customUnit") == "degC"


def test_the_fields_measurement_scale_is_used() -> None:
    manifest = sample()
    logger = manifest.resource("logger")
    assert logger is not None and logger.table_schema is not None
    for field in logger.table_schema.fields:
        if field.name == "logger_model":
            field.measurement_scale = "ordinal"
        if field.name == "depth_cm":
            field.measurement_scale = "interval"
    xml = to_eml(manifest, root=SAMPLE)

    assert_valid(xml)
    model = attribute(xml, "logger", "logger_model")
    assert model.find("measurementScale/ordinal/nonNumericDomain/textDomain") is not None
    depth = attribute(xml, "logger", "depth_cm")
    assert depth.findtext("measurementScale/interval/unit/customUnit") == "cm"
    assert depth.findtext("measurementScale/interval/numericDomain/numberType") == "integer"


@pytest.mark.parametrize("scale", ["ratio", "interval", "dateTime"])
def test_a_coded_column_with_an_explicit_numeric_scale_is_refused(scale: str) -> None:
    manifest = sample()
    logger = manifest.resource("logger")
    assert logger is not None and logger.table_schema is not None
    for field in logger.table_schema.fields:
        if field.name == "condition":
            field.measurement_scale = scale  # type: ignore[assignment]
            field.unit = "degC"

    with pytest.raises(ValueError, match=f"condition.*{scale}.*code list"):
        to_eml(manifest, root=SAMPLE)


def test_a_coded_column_with_an_explicit_ordinal_scale_keeps_it() -> None:
    manifest = sample()
    logger = manifest.resource("logger")
    assert logger is not None and logger.table_schema is not None
    for field in logger.table_schema.fields:
        if field.name == "condition":
            field.measurement_scale = "ordinal"
    xml = to_eml(manifest, root=SAMPLE)

    assert_valid(xml)
    attr = attribute(xml, "logger", "condition")
    assert attr.find("measurementScale/ordinal/nonNumericDomain/enumeratedDomain") is not None


def test_a_related_column_is_an_attribute_annotation() -> None:
    attr = attribute(to_eml(sample(), root=SAMPLE), "logger", "water_temp_unc_c")

    assert "Related column" not in (attr.findtext("attributeDefinition") or "")
    [annotation] = attr.findall("annotation")
    prop, value = annotation.find("propertyURI"), annotation.find("valueURI")
    assert prop is not None and value is not None
    assert (prop.get("label"), prop.text) == (
        "ancillaryOf",
        "https://research-in-a-box.org/terms/ancillaryOf",
    )
    assert value.get("label") == "uncertainty:water_temp_c"


def test_purpose_is_written() -> None:
    manifest = sample()
    root = ET.fromstring(to_eml(manifest, root=SAMPLE))

    assert root.findtext("dataset/purpose/para") == manifest.purpose


def test_vector_attributes_are_the_spatial_vectors_attribute_list() -> None:
    root = ET.fromstring(to_eml(sample(), root=SAMPLE))
    vector = root.find("dataset/spatialVector")
    assert vector is not None

    names = [a.findtext("attributeName") for a in vector.iter("attribute")]
    assert names == ["site", "name"]
    assert vector.findtext("geometry") == "Point"


def test_project_keywords_and_an_unknown_end_validate() -> None:
    manifest = sample().model_copy(
        update={
            "project": "streams",
            "temporal_coverage": TemporalCoverage.model_validate(
                {"start": "1991-01-01", "end": "unknown"}
            ),
        }
    )
    project = Project(id="streams", title="Streams", keywords=["temperature", "LTER"])
    xml = to_eml(manifest, project, root=SAMPLE)

    assert_valid(xml)
    root = ET.fromstring(xml)
    descriptor = root.find("dataset/project/studyAreaDescription/descriptor")
    assert descriptor is not None and descriptor.get("name") == "keywords"
    assert [v.text for v in descriptor.iter("descriptorValue")] == ["temperature", "LTER"]
    assert root.findtext("dataset/coverage/temporalCoverage/singleDateTime/calendarDate") == (
        "1991-01-01"
    )
    assert root.findtext("dataset/maintenance/maintenanceUpdateFrequency") == "unknown"


def _sites_reading(shp: str) -> Resource:
    resource = sample().resource("sites")
    assert resource is not None and resource.files is not None
    member = resource.files[0].model_copy(update={"path": shp})
    return resource.model_copy(update={"files": [member], "path": shp})


def _outside_shp(tmp_path: Path) -> Path:
    outside = tmp_path / "outside" / "sites"
    outside.mkdir(parents=True)
    shp = outside / "sites.shp"
    shp.write_bytes((SAMPLE / "data" / "sites" / "sites.shp").read_bytes())
    return shp


def test_an_absolute_shp_path_is_not_read(tmp_path: Path) -> None:
    shp = _outside_shp(tmp_path)
    root = tmp_path / "package"
    root.mkdir()

    assert shp_geometry(root, _sites_reading(str(shp))) == "MultiGeometry"


def test_a_shp_path_out_of_the_package_is_not_read(tmp_path: Path) -> None:
    _outside_shp(tmp_path)
    root = tmp_path / "package"
    root.mkdir()

    assert shp_geometry(root, _sites_reading("../outside/sites/sites.shp")) == "MultiGeometry"


def test_a_shp_under_a_symlinked_folder_is_not_read(tmp_path: Path) -> None:
    shp = _outside_shp(tmp_path)
    root = tmp_path / "package"
    root.mkdir()
    (root / "data").symlink_to(shp.parent.parent, target_is_directory=True)

    assert shp_geometry(root, _sites_reading("data/sites/sites.shp")) == "MultiGeometry"


def test_a_shp_inside_the_package_is_read() -> None:
    assert shp_geometry(SAMPLE, _sites_reading("data/sites/sites.shp")) == "Point"
