"""EML 2.1.1 and 2.2.0 import into a manifest, and the sample's EML round trip."""

from pathlib import Path

import pytest

from archive_contract.exports._common import person_name
from archive_contract.exports.eml import read_code_list, to_eml
from archive_contract.fields import Field
from archive_contract.imports.eml import from_eml
from archive_contract.manifest import Manifest, TemporalCoverage
from archive_contract.project import Project

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"
FIXTURES = Path(__file__).parent / "fixtures" / "eml"


def sample() -> Manifest:
    return Manifest.model_validate_json((SAMPLE / "datapackage.json").read_text(encoding="utf-8"))


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fields(manifest: Manifest, table: str) -> dict[str, Field]:
    resource = manifest.resource(table)
    assert resource is not None and resource.table_schema is not None
    return {f.name: f for f in resource.table_schema.fields}


def test_eml_2_1_1_record_imports_its_metadata() -> None:
    result = from_eml(fixture("invented-2.1.1.xml"))
    m = result.manifest

    assert m.title == "Snow depth at two invented plots"
    assert [(person_name(c), c.organization) for c in m.contributors or [] if c.is_creator()] == [
        ("Cora Madeup", "Invented Field Station"),
        ("Invented Snow Survey", "Invented Snow Survey"),
    ]
    assert m.description is not None and m.description.startswith("Weekly snow depth")
    assert m.keywords == ["snow depth", "winter"]
    assert m.licenses is None
    assert m.rights_status is not None and m.rights_status.status == "all-rights-reserved"
    assert m.rights_status.statement == "Copyright Invented Field Station. All rights reserved."
    assert m.spatial_coverage is not None and m.spatial_coverage.bbox == (-71.5, 44.0, -71.4, 44.1)
    assert m.temporal_coverage is not None
    assert str(m.temporal_coverage.start) == "2018-11-01"
    assert str(m.temporal_coverage.end) == "2019-04-30"
    assert m.methods == "Depth was read from a graduated stake each week."
    assert result.project is not None and result.project.title == "Invented winter monitoring"
    assert m.project == result.project.id


def test_eml_package_id_becomes_a_legacy_identifier() -> None:
    m = from_eml(fixture("invented-2.1.1.xml")).manifest

    assert [(i.scheme, i.value) for i in m.legacy_identifiers or []] == [
        ("eml-package-id", "knb-lter-inv.7.2"),
        ("local-catalogue", "INV-0007"),
    ]


def test_data_table_attributes_become_fields_and_code_lists() -> None:
    result = from_eml(fixture("invented-2.1.1.xml"))
    snow = fields(result.manifest, "snow")

    assert {name: f.type for name, f in snow.items()} == {
        "date": "date",
        "plot": "string",
        "depth": "number",
    }
    assert snow["plot"].title == "Plot"
    assert snow["depth"].description == "Snow depth"
    assert result.code_lists["plot-codes"] == [
        {"code": "N", "label": "North plot", "description": "under conifers"},
        {"code": "S", "label": "South plot", "description": ""},
    ]
    codes = result.manifest.resource("plot-codes")
    assert codes is not None and codes.path == "data/codes/plot-codes.csv"
    snow_table = result.manifest.resource("snow")
    assert snow_table is not None and snow_table.table_schema is not None
    [key] = snow_table.table_schema.foreign_keys or []
    assert key.field_names() == ["plot"] and key.reference.resource == "plot-codes"
    assert snow_table.table_schema.missing_values == ["-999"]


def test_non_standard_tags_are_skipped_and_listed() -> None:
    result = from_eml(fixture("invented-2.1.1.xml"))

    assert any("fieldNotebook" in s and "not standard" in s for s in result.skipped)
    assert any("stakeColour" in s and "not standard" in s for s in result.skipped)
    assert result.manifest.title is not None


def test_eml_2_2_0_record_reads_its_license() -> None:
    result = from_eml(fixture("invented-2.2.0.xml"))
    m = result.manifest

    assert m.licenses is not None and m.licenses[0].name == "CC-BY-4.0"
    assert m.rights_status is None
    other = m.resource("basket-map")
    assert other is not None and other.kind == "document" and other.path == "baskets.pdf"


def test_sample_round_trips_through_eml() -> None:
    original = sample()
    result = from_eml(to_eml(original, root=SAMPLE))
    back = result.manifest

    assert back.title == original.title
    assert back.description == original.description
    assert back.keywords == original.keywords

    def people(m: Manifest) -> list[tuple[str | None, str | None, list[str] | None]]:
        return [(person_name(c), c.organization, c.roles) for c in m.contributors or []]

    assert people(back) == people(original)
    assert back.licenses == original.licenses
    assert back.rights_status == original.rights_status
    assert back.temporal_coverage == original.temporal_coverage
    assert back.spatial_coverage == original.spatial_coverage

    assert back.purpose == original.purpose

    def compare(f: Field) -> tuple[object, ...]:
        return (
            f.name,
            f.type,
            f.title,
            f.description,
            f.code_list,
            f.format,
            f.unit,
            f.measurement_scale,
            f.ancillary_of,
        )

    for table in ["logger", "condition-codes"]:
        assert [compare(f) for f in fields(back, table).values()] == [
            compare(f) for f in fields(original, table).values()
        ]
    sites, sites_back = original.resource("sites"), back.resource("sites")
    assert sites is not None and sites.attributes is not None
    assert sites_back is not None and sites_back.attributes is not None
    assert sites_back.kind == "vector"
    assert [compare(f) for f in sites_back.attributes.fields] == [
        compare(f) for f in sites.attributes.fields
    ]
    assert any(f.unit for f in fields(original, "logger").values())
    assert any(f.ancillary_of for f in fields(original, "logger").values())

    codes = original.resource("condition-codes")
    assert codes is not None
    assert result.code_lists == {"condition-codes": read_code_list(SAMPLE, codes)}
    logger = back.resource("logger")
    assert logger is not None and logger.table_schema is not None
    [key] = logger.table_schema.foreign_keys or []
    assert key.field_names() == ["condition"] and key.reference.resource == "condition-codes"


def test_skipped_lists_what_sits_inside_unread_parts() -> None:
    xml = """<eml:eml xmlns:eml="eml://ecoinformatics.org/eml-2.1.1" packageId="x.1.1" system="x">
      <eml:dataset>
        <eml:title>Invented</eml:title>
        <eml:project>
          <eml:title>Invented program</eml:title>
          <eml:personnel><eml:leadPerson><eml:surName>Nobody</eml:surName></eml:leadPerson></eml:personnel>
        </eml:project>
        <eml:dataTable>
          <eml:title>No entity name</eml:title>
          <eml:physical><eml:objectName>t.csv</eml:objectName><eml:distibution/></eml:physical>
          <eml:attributeList>
            <eml:attribute><eml:attributeName>a</eml:attributeName><eml:measurementType/></eml:attribute>
          </eml:attributeList>
        </eml:dataTable>
      </eml:dataset>
    </eml:eml>"""
    result = from_eml(xml)

    assert result.manifest.title == "Invented"
    assert result.manifest.resources == []
    assert "dataset/dataTable: no entityName, so no resource" in result.skipped
    assert "dataset/dataTable/physical/distibution: not standard EML" in result.skipped
    assert (
        "dataset/dataTable/attributeList/attribute/measurementType: not standard EML"
        in result.skipped
    )
    assert "dataset/project/personnel/leadPerson: not standard EML" in result.skipped
    assert "dataset/project/personnel: no name, so no person" in result.skipped


BILLION_LAUGHS = """<?xml version="1.0"?>
<!DOCTYPE eml [
  <!ENTITY lol "lol">
  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
]>
<eml:eml xmlns:eml="eml://ecoinformatics.org/eml-2.1.1">
  <dataset><title>&lol3;</title></dataset>
</eml:eml>"""

DOCTYPE_ONLY = """<?xml version="1.0"?>
<!DOCTYPE eml SYSTEM "http://example.org/eml.dtd">
<eml:eml xmlns:eml="eml://ecoinformatics.org/eml-2.1.1">
  <dataset><title>Invented</title></dataset>
</eml:eml>"""


@pytest.mark.parametrize("xml", [BILLION_LAUGHS, DOCTYPE_ONLY], ids=["entities", "doctype"])
def test_documents_with_a_doctype_or_entities_are_refused(xml: str) -> None:
    with pytest.raises(ValueError, match="DOCTYPE"):
        from_eml(xml)


def test_columns_sharing_a_name_keep_their_own_code_lists() -> None:
    def table(name: str, codes: list[tuple[str, str]]) -> str:
        definitions = "".join(
            f"<codeDefinition><code>{c}</code><definition>{d}</definition></codeDefinition>"
            for c, d in codes
        )
        return f"""<dataTable><entityName>{name}</entityName>
          <physical><objectName>{name}.csv</objectName></physical>
          <attributeList><attribute><attributeName>status</attributeName>
            <attributeDefinition>Status</attributeDefinition>
            <measurementScale><nominal><nonNumericDomain><enumeratedDomain>{definitions}
            </enumeratedDomain></nonNumericDomain></nominal></measurementScale>
          </attribute></attributeList></dataTable>"""

    xml = f"""<eml:eml xmlns:eml="https://eml.ecoinformatics.org/eml-2.2.0">
      <dataset><title>Invented</title>
        {table("plots", [("A", "Active"), ("R", "Retired")])}
        {table("traps", [("O", "Open"), ("C", "Closed")])}
      </dataset></eml:eml>"""
    result = from_eml(xml)

    def target(name: str) -> str:
        resource = result.manifest.resource(name)
        assert resource is not None and resource.table_schema is not None
        [key] = resource.table_schema.foreign_keys or []
        assert key.reference.resource is not None
        return key.reference.resource

    plots, traps = target("plots"), target("traps")
    assert plots != traps
    assert [r["code"] for r in result.code_lists[plots]] == ["A", "R"]
    assert [r["code"] for r in result.code_lists[traps]] == ["O", "C"]
    assert result.manifest.resource(plots) is not None
    assert result.manifest.resource(traps) is not None


def test_identical_code_lists_are_shared() -> None:
    attribute = """<attribute><attributeName>status</attributeName>
      <measurementScale><nominal><nonNumericDomain><enumeratedDomain>
        <codeDefinition><code>A</code><definition>Active</definition></codeDefinition>
      </enumeratedDomain></nonNumericDomain></nominal></measurementScale></attribute>"""
    xml = f"""<eml:eml xmlns:eml="https://eml.ecoinformatics.org/eml-2.2.0">
      <dataset><title>Invented</title>
        <dataTable><entityName>plots</entityName>
          <attributeList>{attribute}</attributeList></dataTable>
        <dataTable><entityName>traps</entityName>
          <attributeList>{attribute}</attributeList></dataTable>
      </dataset></eml:eml>"""
    result = from_eml(xml)

    assert list(result.code_lists) == ["status-codes"]


def single_date_with_maintenance(description: str, frequency: str) -> str:
    return f"""<eml:eml xmlns:eml="https://eml.ecoinformatics.org/eml-2.2.0">
      <dataset><title>Invented</title>
        <coverage><temporalCoverage>
          <singleDateTime><calendarDate>2021-05-01</calendarDate></singleDateTime>
        </temporalCoverage></coverage>
        <maintenance>
          <description><para>{description}</para></description>
          <maintenanceUpdateFrequency>{frequency}</maintenanceUpdateFrequency>
        </maintenance>
      </dataset></eml:eml>"""


def test_the_exports_ongoing_convention_reads_as_ongoing() -> None:
    m = from_eml(
        single_date_with_maintenance("Data collection is ongoing.", "continually")
    ).manifest

    assert m.temporal_coverage is not None and m.temporal_coverage.ongoing
    assert str(m.temporal_coverage.start) == "2021-05-01"


def test_ordinary_maintenance_leaves_a_single_date_and_is_skipped() -> None:
    result = from_eml(single_date_with_maintenance("Updated monthly.", "monthly"))
    coverage = result.manifest.temporal_coverage

    assert coverage is not None and not coverage.ongoing
    assert str(coverage.start) == "2021-05-01" and str(coverage.end) == "2021-05-01"
    assert any(s.startswith("dataset/maintenance") for s in result.skipped)


def test_units_are_read() -> None:
    result = from_eml(fixture("invented-2.1.1.xml"))

    assert fields(result.manifest, "snow")["depth"].unit == "centimeter"
    assert not any("/unit" in s for s in result.skipped)


def test_the_exports_unknown_unit_is_not_listed_as_lost() -> None:
    result = from_eml(to_eml(sample(), root=SAMPLE))

    assert not any("/unit:" in s for s in result.skipped)


def test_measurement_scales_are_read() -> None:
    xml = """<eml:eml xmlns:eml="https://eml.ecoinformatics.org/eml-2.2.0">
      <dataset><title>Invented</title>
        <dataTable><entityName>plots</entityName><attributeList>
          <attribute><attributeName>temp</attributeName><measurementScale><interval>
            <unit><customUnit>unknown</customUnit></unit>
            <numericDomain><numberType>real</numberType></numericDomain>
          </interval></measurementScale></attribute>
          <attribute><attributeName>rank</attributeName><measurementScale><ordinal>
            <nonNumericDomain><textDomain><definition>Rank</definition></textDomain>
            </nonNumericDomain></ordinal></measurementScale></attribute>
        </attributeList></dataTable>
      </dataset></eml:eml>"""
    result = from_eml(xml)
    plots = fields(result.manifest, "plots")

    assert plots["temp"].measurement_scale == "interval"
    assert plots["temp"].unit is None
    assert plots["rank"].measurement_scale == "ordinal"
    assert not any("measurementScale" in s for s in result.skipped)


def test_purpose_project_keywords_and_unknown_end_round_trip() -> None:
    manifest = sample().model_copy(
        update={
            "project": "streams",
            "temporal_coverage": TemporalCoverage.model_validate(
                {"start": "1991-01-01", "end": "unknown"}
            ),
        }
    )
    project = Project(id="streams", title="Streams", keywords=["temperature", "LTER"])
    result = from_eml(to_eml(manifest, project, root=SAMPLE))

    assert result.manifest.purpose == manifest.purpose
    assert result.manifest.temporal_coverage == manifest.temporal_coverage
    assert result.project is not None and result.project.keywords == ["temperature", "LTER"]
    assert not any(
        s.startswith(("dataset/purpose", "dataset/maintenance", "dataset/project/study"))
        for s in result.skipped
    )


def test_other_study_area_descriptors_are_skipped() -> None:
    xml = """<eml:eml xmlns:eml="https://eml.ecoinformatics.org/eml-2.2.0">
      <dataset><title>Invented</title>
        <project><title>P</title><personnel><surName>X</surName><role>pi</role></personnel>
          <studyAreaDescription><descriptor name="climate" citableClassificationSystem="false">
            <descriptorValue>Cold</descriptorValue></descriptor></studyAreaDescription>
        </project>
      </dataset></eml:eml>"""
    result = from_eml(xml)

    assert result.project is not None and result.project.keywords is None
    assert "dataset/project/studyAreaDescription/descriptor[climate]: not read" in result.skipped


def test_a_definition_naming_a_missing_column_keeps_its_text() -> None:
    xml = """<eml:eml xmlns:eml="https://eml.ecoinformatics.org/eml-2.2.0">
      <dataset><title>Invented</title>
        <dataTable><entityName>plots</entityName><attributeList>
          <attribute><attributeName>sd</attributeName>
            <attributeDefinition>Spread. Related column: gone (uncertainty).</attributeDefinition>
            <measurementScale><nominal><nonNumericDomain><textDomain><definition>x</definition>
            </textDomain></nonNumericDomain></nominal></measurementScale></attribute>
        </attributeList></dataTable>
      </dataset></eml:eml>"""
    sd = fields(from_eml(xml).manifest, "plots")["sd"]

    assert sd.ancillary_of is None
    assert sd.description == "Spread. Related column: gone (uncertainty)."
