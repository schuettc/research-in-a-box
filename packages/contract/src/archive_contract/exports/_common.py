"""What every export reads the same way from a manifest."""

from archive_contract.fields import Field, TableSchema
from archive_contract.manifest import Contributor, Manifest
from archive_contract.resources import Resource


def person_name(contributor: Contributor) -> str | None:
    """A contributor's display name: its title, else given and family name, else organization."""
    if contributor.title:
        return contributor.title
    parts = [p for p in (contributor.given_name, contributor.family_name) if p]
    if parts:
        return " ".join(parts)
    return contributor.organization


def creators(manifest: Manifest) -> list[Contributor]:
    return [c for c in manifest.contributors or [] if c.is_creator()]


def code_list_resource(schema: TableSchema, field: Field) -> str | None:
    """The resource a field's codes come from, when a foreign key on that field alone names one."""
    for key in schema.foreign_keys or []:
        if key.field_names() == [field.name] and key.reference.resource:
            return key.reference.resource
    return None


def tables(manifest: Manifest) -> list[tuple[Resource, TableSchema]]:
    """The table resources that carry a schema, in manifest order."""
    return [
        (r, r.table_schema)
        for r in manifest.resources
        if r.kind == "table" and r.table_schema is not None
    ]
