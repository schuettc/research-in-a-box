"""The base every contract model shares: aliases, extra properties and the null rule."""

from typing import Any

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, model_serializer

ARCHIVE_PREFIX = "archive:"


class ArchiveModel(BaseModel):
    """A contract model.

    Unknown properties are accepted and kept, since Frictionless allows them. When dumped,
    standard properties that are unset are left out (Frictionless never writes null), while
    `archive:` properties are written under their prefixed names and may be null.
    """

    model_config = ConfigDict(
        extra="allow",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    @model_serializer(mode="wrap")
    def _drop_unset_standard(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        return {k: v for k, v in data.items() if v is not None or k.startswith(ARCHIVE_PREFIX)}

    def dump(self) -> dict[str, Any]:
        """The JSON form, with `archive:` names and unset standard properties left out."""
        return self.model_dump(mode="json", by_alias=True)
