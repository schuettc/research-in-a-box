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


def test_unit_and_measurement_scale_parse_and_dump() -> None:
    field = Field.model_validate(
        {"name": "temp_c", "archive:unit": "degC", "archive:measurementScale": "interval"}
    )

    assert field.unit == "degC"
    assert field.measurement_scale == "interval"
    assert field.dump()["archive:unit"] == "degC"
    assert field.dump()["archive:measurementScale"] == "interval"


@pytest.mark.parametrize("scale", ["nominal", "ordinal", "interval", "ratio", "dateTime"])
def test_measurement_scale_takes_emls_five(scale: str) -> None:
    field = Field.model_validate({"name": "x", "archive:measurementScale": scale})

    assert field.measurement_scale == scale


def test_measurement_scale_refuses_other_values() -> None:
    with pytest.raises(ValidationError):
        Field.model_validate({"name": "x", "archive:measurementScale": "continuous"})


def _schema_with_ancillary(of: str, role: str = "uncertainty") -> dict[str, object]:
    return {
        "fields": [
            {"name": "temp_c", "type": "number"},
            {
                "name": "temp_sd",
                "type": "number",
                "archive:ancillaryOf": {"field": of, "role": role},
            },
        ]
    }


@pytest.mark.parametrize("role", ["uncertainty", "detection-limit", "quality-flag"])
def test_ancillary_column_names_another_column_and_a_role(role: str) -> None:
    schema = TableSchema.model_validate(_schema_with_ancillary("temp_c", role))

    ancillary = schema.fields[1].ancillary_of
    assert ancillary is not None
    assert (ancillary.field, ancillary.role) == ("temp_c", role)


def test_ancillary_of_a_missing_column_is_refused() -> None:
    with pytest.raises(ValidationError, match="ancillaryOf"):
        TableSchema.model_validate(_schema_with_ancillary("air_temp_c"))


def test_ancillary_of_itself_is_refused() -> None:
    with pytest.raises(ValidationError, match="ancillaryOf"):
        TableSchema.model_validate(_schema_with_ancillary("temp_sd"))


def test_ancillary_role_refuses_other_values() -> None:
    with pytest.raises(ValidationError):
        TableSchema.model_validate(_schema_with_ancillary("temp_c", "error-bar"))
