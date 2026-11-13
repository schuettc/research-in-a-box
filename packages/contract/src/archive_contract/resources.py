"""Resources: the files of a package, their kinds, member files and alternates."""

from typing import Any, Literal, Self

from pydantic import Field as PydanticField
from pydantic import field_validator, model_validator

from archive_contract._base import ArchiveModel
from archive_contract.fields import TableSchema
from archive_contract.rights import License

ResourceKind = Literal["table", "vector", "raster", "document", "media", "file", "linked"]


class MemberFile(ArchiveModel):
    """One file of a resource made of several files that only work together."""

    path: str
    bytes: int | None = None
    hash: str | None = None


class Resource(ArchiveModel):
    """A Frictionless resource with the archive's additions.

    - `archive:kind` says what the resource is; with none it reads as `table` when `type` is
      `table`, and as `file` otherwise. Frictionless's `type` is `table` for a table (written
      when absent) and is refused on any other kind.
    - `archive:files` lists every member file of a multi-file resource (a shapefile set),
      with `path` naming the main file.
    - `archive:alternateOf` names the primary when this is the same data in another format;
      only the primary carries the schema.
    - A `linked` resource is held elsewhere: `path` is its URL and it has no hash or size.
    """

    name: str
    path: str | list[str] | None = None
    data: Any = None
    type: Literal["table"] | None = None
    title: str | None = None
    description: str | None = None
    format: str | None = None
    mediatype: str | None = None
    encoding: str | None = None
    bytes: int | None = None
    hash: str | None = None
    table_schema: TableSchema | None = PydanticField(default=None, alias="schema")
    dialect: dict[str, Any] | None = None
    sources: list[dict[str, Any]] | None = None
    licenses: list[License] | None = None
    kind: ResourceKind = PydanticField(default="file", alias="archive:kind")
    files: list[MemberFile] | None = PydanticField(default=None, alias="archive:files")
    alternate_of: str | None = PydanticField(default=None, alias="archive:alternateOf")

    @model_validator(mode="before")
    @classmethod
    def _type_table_reads_as_table(cls, data: Any) -> Any:
        if not isinstance(data, dict) or data.get("type") != "table":
            return data
        if data.get("archive:kind") is None and data.get("kind") is None:
            return {k: v for k, v in data.items() if k != "kind"} | {"archive:kind": "table"}
        return data

    @field_validator("kind", mode="before")
    @classmethod
    def _no_kind_is_file(cls, value: object) -> object:
        return "file" if value is None else value

    @model_validator(mode="after")
    def _kind_rules(self) -> Self:
        if self.kind == "table":
            if self.type is None:
                self.type = "table"
        elif self.type is not None:
            raise ValueError(f"type table is for tables only, not archive:kind {self.kind}")
        if self.kind == "linked":
            if not self.is_remote():
                raise ValueError("a linked resource's path must be a URL")
            if self.hash is not None or self.bytes is not None or self.files:
                raise ValueError("a linked resource has no hash, bytes or member files")
        if self.alternate_of is not None and self.table_schema is not None:
            raise ValueError("an alternate has no schema: only the primary carries the schema")
        return self

    def is_remote(self) -> bool:
        return isinstance(self.path, str) and self.path.startswith(("http://", "https://"))
