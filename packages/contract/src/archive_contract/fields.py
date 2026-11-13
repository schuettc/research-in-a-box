"""Table Schema fields and schemas, with the archive's additions to columns."""

from typing import Any, Literal, Self

from pydantic import Field as PydanticField
from pydantic import model_validator

from archive_contract._base import ArchiveModel

FieldType = Literal[
    "string",
    "number",
    "integer",
    "boolean",
    "object",
    "array",
    "list",
    "datetime",
    "date",
    "time",
    "year",
    "yearmonth",
    "duration",
    "geopoint",
    "geojson",
    "any",
]

Sensitivity = Literal["personal", "sensitive-location", "confidential"]

MeasurementScale = Literal["nominal", "ordinal", "interval", "ratio", "dateTime"]
"""EML's measurement scales."""

AncillaryRole = Literal["uncertainty", "detection-limit", "quality-flag"]


def _as_list(value: list[str] | str) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


class AncillaryOf(ArchiveModel):
    """The column this one qualifies, and how: its uncertainty, detection limit or flag."""

    field: str
    role: AncillaryRole


class Field(ArchiveModel):
    """One column of a table, described by logical type rather than file format.

    `name` is the column's name in the tidy table. When a rename was accepted, the column's
    name in the source file is kept in `archive:sourceName`. `archive:unit` is free text
    (`degC`, `mg/L`); `archive:ancillaryOf` names another column of the same schema that
    this one qualifies.
    """

    name: str
    type: FieldType | None = None
    format: str | None = None
    title: str | None = None
    description: str | None = None
    example: Any = None
    constraints: dict[str, Any] | None = None
    source_name: str | None = PydanticField(default=None, alias="archive:sourceName")
    code_list: Literal["undocumented"] | None = PydanticField(
        default=None, alias="archive:codeList"
    )
    sensitivity: Sensitivity | None = PydanticField(default=None, alias="archive:sensitivity")
    unit: str | None = PydanticField(default=None, alias="archive:unit")
    measurement_scale: MeasurementScale | None = PydanticField(
        default=None, alias="archive:measurementScale"
    )
    ancillary_of: AncillaryOf | None = PydanticField(default=None, alias="archive:ancillaryOf")


class ForeignKeyReference(ArchiveModel):
    """What a foreign key points at. With no `resource` it points into the same table."""

    resource: str | None = None
    fields: list[str] | str

    def field_names(self) -> list[str]:
        return _as_list(self.fields)


class ForeignKey(ArchiveModel):
    """A link from columns of this table to columns of another, such as a code list."""

    fields: list[str] | str
    reference: ForeignKeyReference

    def field_names(self) -> list[str]:
        return _as_list(self.fields)


class TableSchema(ArchiveModel):
    """A Frictionless Table Schema."""

    fields: list[Field] = PydanticField(default_factory=list)
    primary_key: list[str] | str | None = PydanticField(default=None, alias="primaryKey")
    foreign_keys: list[ForeignKey] | None = PydanticField(default=None, alias="foreignKeys")
    missing_values: list[Any] | None = PydanticField(default=None, alias="missingValues")

    @model_validator(mode="after")
    def _ancillary_names_another_column(self) -> Self:
        names = set(self.field_names())
        for field in self.fields:
            target = field.ancillary_of
            if target is None:
                continue
            if target.field == field.name or target.field not in names:
                raise ValueError(
                    f"archive:ancillaryOf on {field.name} must name another column of the "
                    f"same schema, not {target.field}"
                )
        return self

    def field_names(self) -> list[str]:
        return [field.name for field in self.fields]
