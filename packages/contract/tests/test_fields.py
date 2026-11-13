import pytest
from pydantic import ValidationError

from archive_contract.fields import Field, TableSchema


def test_renamed_field_keeps_its_source_name() -> None:
    field = Field.model_validate(
        {"name": "water_temp_c", "type": "number", "archive:sourceName": "WTemp"}
    )

    assert field.source_name == "WTemp"
    assert field.dump()["archive:sourceName"] == "WTemp"


def test_code_list_marker_only_takes_undocumented() -> None:
    field = Field.model_validate({"name": "flag", "archive:codeList": "undocumented"})
    assert field.code_list == "undocumented"

    with pytest.raises(ValidationError):
        Field.model_validate({"name": "flag", "archive:codeList": "documented"})


@pytest.mark.parametrize("level", ["personal", "sensitive-location", "confidential"])
def test_sensitivity_takes_the_three_levels(level: str) -> None:
    assert Field.model_validate({"name": "x", "archive:sensitivity": level}).sensitivity == level


def test_sensitivity_refuses_other_values() -> None:
    with pytest.raises(ValidationError):
        Field.model_validate({"name": "x", "archive:sensitivity": "secret"})


def test_no_sensitivity_flag_means_not_sensitive() -> None:
    assert Field.model_validate({"name": "x"}).sensitivity is None


def test_field_dump_drops_unset_standard_properties() -> None:
    dumped = Field.model_validate({"name": "x", "type": "string"}).dump()

    assert "description" not in dumped
    assert "title" not in dumped
    assert dumped["archive:codeList"] is None


def test_schema_reads_foreign_keys_to_a_code_list() -> None:
    schema = TableSchema.model_validate(
        {
            "fields": [{"name": "condition", "type": "string"}],
            "foreignKeys": [
                {
                    "fields": ["condition"],
                    "reference": {"resource": "condition-codes", "fields": ["code"]},
                }
            ],
        }
    )

    assert schema.foreign_keys is not None
    key = schema.foreign_keys[0]
    assert key.field_names() == ["condition"]
    assert key.reference.resource == "condition-codes"
    assert key.reference.field_names() == ["code"]
    dumped = schema.dump()
    assert dumped["foreignKeys"][0]["reference"]["resource"] == "condition-codes"
    assert "primaryKey" not in dumped


def test_foreign_key_with_string_fields_reads_as_a_list() -> None:
    schema = TableSchema.model_validate(
        {
            "fields": [{"name": "condition"}],
            "foreignKeys": [
                {"fields": "condition", "reference": {"resource": "codes", "fields": "code"}}
            ],
        }
    )

    assert schema.foreign_keys is not None
    assert schema.foreign_keys[0].field_names() == ["condition"]
    assert schema.foreign_keys[0].reference.field_names() == ["code"]


def test_unknown_field_type_is_refused() -> None:
    with pytest.raises(ValidationError):
        Field.model_validate({"name": "x", "type": "float"})
