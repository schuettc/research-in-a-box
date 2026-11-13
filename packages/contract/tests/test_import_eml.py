"""EML 2.1.1 and 2.2.0 import into a manifest, and the sample's EML round trip."""

from pathlib import Path

from archive_contract.exports._common import person_name
from archive_contract.exports.eml import read_code_list, to_eml
from archive_contract.fields import Field
from archive_contract.imports.eml import from_eml
from archive_contract.manifest import Manifest

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


def test_eml_2_2_0_record_reads_its_license_and_ongoing_coverage() -> None:
    result = from_eml(fixture("invented-2.2.0.xml"))
    m = result.manifest

    assert m.licenses is not None and m.licenses[0].name == "CC-BY-4.0"
    assert m.rights_status is None
    assert m.temporal_coverage is not None and m.temporal_coverage.ongoing
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

    def compare(f: Field) -> tuple[object, ...]:
        return (f.name, f.type, f.title, f.description, f.code_list, f.format)

    for table in ["logger", "condition-codes"]:
        assert [compare(f) for f in fields(back, table).values()] == [
            compare(f) for f in fields(original, table).values()
        ]

    codes = original.resource("condition-codes")
    assert codes is not None
    assert result.code_lists == {"condition-codes": read_code_list(SAMPLE, codes)}
    logger = back.resource("logger")
    assert logger is not None and logger.table_schema is not None
    [key] = logger.table_schema.foreign_keys or []
    assert key.field_names() == ["condition"] and key.reference.resource == "condition-codes"
