from pathlib import Path
from typing import Any

from archive_contract.manifest import Manifest
from cruise.rules import REGISTRY, Context


def table(fields: list[dict[str, Any]], path: str = "t.csv") -> dict[str, Any]:
    return {
        "name": "t",
        "path": path,
        "type": "table",
        "format": "csv",
        "schema": {"fields": fields},
    }


def run(rule: str, resources: list[dict[str, Any]], root: Path = Path(".")) -> Any:
    manifest = Manifest.model_validate({"resources": resources})
    return REGISTRY.get(rule).run(Context.for_package(root, manifest))


def targets(result: Any) -> list[tuple[str | None, str | None]]:
    return [(f.target.resource, f.target.field) for f in result.findings]


def test_description_missing_covers_table_columns_and_vector_attributes() -> None:
    vector = {
        "name": "sites",
        "path": "sites.shp",
        "archive:kind": "vector",
        "archive:attributes": {"fields": [{"name": "site"}, {"name": "id", "description": "Id"}]},
    }
    columns = [{"name": "a", "description": "A thing."}, {"name": "b", "description": " "}]

    result = run("field.description-missing", [table(columns), vector])

    assert targets(result) == [("t", "b"), ("sites", "site")]
    assert {f.severity for f in result.findings} == {"warning"}
    assert result.checks == 4


def test_description_repeating_the_name_or_source_name_ignores_case_and_punctuation() -> None:
    columns = [
        {"name": "depth_cm", "description": "Depth (CM)"},
        {"name": "temp", "archive:sourceName": "WTemp", "description": "w-temp."},
        {"name": "flow", "description": "Discharge in litres a second."},
        {"name": "bare"},
    ]

    result = run("field.description-repeats-name", [table(columns)])

    assert targets(result) == [("t", "depth_cm"), ("t", "temp")]
    assert result.checks == 3


def test_unit_missing_on_measurements_on_an_interval_ratio_or_unstated_scale() -> None:
    columns = [
        {"name": "ratio", "type": "number", "archive:measurementScale": "ratio"},
        {"name": "unstated", "type": "integer"},
        {"name": "interval", "type": "number", "archive:measurementScale": "interval"},
        {"name": "count_code", "type": "integer", "archive:measurementScale": "nominal"},
        {"name": "with_unit", "type": "number", "archive:unit": "mg/L"},
        {"name": "label", "type": "string"},
    ]

    result = run("field.unit-missing", [table(columns)])

    assert targets(result) == [("t", "ratio"), ("t", "unstated"), ("t", "interval")]
    assert result.checks == 4


def test_undocumented_codes_list_their_distinct_values(tmp_path: Path) -> None:
    (tmp_path / "t.csv").write_text("flag,other\nB,1\nA,2\nB,3\n,4\n", encoding="utf-8")
    columns = [
        {"name": "flag", "type": "string", "archive:codeList": "undocumented"},
        {"name": "other", "type": "integer"},
    ]

    result = run("field.codes-undocumented", [table(columns)], tmp_path)

    assert targets(result) == [("t", "flag")]
    evidence = result.findings[0].evidence
    assert evidence is not None and evidence.values == ["A", "B"]
    assert result.checks == 2
