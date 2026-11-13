"""The base every contract model shares: aliases, extra properties and the null rule."""

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, SerializerFunctionWrapHandler, model_serializer

ARCHIVE_PREFIX = "archive:"


class ArchiveModel(BaseModel):
    """A contract model.

    Unknown properties are accepted and kept, since Frictionless allows them. When dumped,
    the model's own standard properties are left out when null (Frictionless never writes
    null), while `archive:` properties and unknown extras keep their value, null included.
    A model lists in `_explicit_nulls` the properties whose null is kept when it was given
    and left out only when the property was never set.
    """

    _explicit_nulls: ClassVar[frozenset[str]] = frozenset()

    model_config = ConfigDict(
        extra="allow",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    @model_serializer(mode="wrap")
    def _drop_unset_standard(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        standard = {
            (info.alias or name): name
            for name, info in type(self).model_fields.items()
            if not (info.alias or name).startswith(ARCHIVE_PREFIX)
        }

        def keep(key: str, value: object) -> bool:
            name = standard.get(key)
            if value is not None or name is None:
                return True
            return name in self._explicit_nulls and name in self.model_fields_set

        return {k: v for k, v in data.items() if keep(k, v)}

    def dump(self) -> dict[str, Any]:
        """The JSON form, with `archive:` names and null standard properties left out."""
        return self.model_dump(mode="json", by_alias=True)
