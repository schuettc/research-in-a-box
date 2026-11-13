"""The package's README.md, generated from the manifest and never edited by hand.

The Markdown is written the way prettier formats it (tables aligned, whatever their width),
so a generated README passes `prettier --check` unchanged.
"""

from archive_contract.exports._common import code_list_resource, creators, person_name
from archive_contract.fields import Field, TableSchema
from archive_contract.manifest import Manifest
from archive_contract.project import Project
from archive_contract.resources import Resource


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _table(header: list[str], rows: list[list[str]]) -> list[str]:
    """A Markdown table as prettier writes it, with every column padded to its widest cell."""
    cells = [[_cell(c) for c in row] for row in [header, *rows]]
    widths = [max(3, *(len(row[i]) for row in cells)) for i in range(len(header))]

    def line(row: list[str]) -> str:
        return "| " + " | ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)) + " |"

    rule = "| " + " | ".join("-" * w for w in widths) + " |"
    return [line(cells[0]), rule, *(line(r) for r in cells[1:])]


def _citation(manifest: Manifest) -> str | None:
    names = [n for n in (person_name(c) for c in creators(manifest)) if n]
    if not manifest.title:
        return None
    parts = []
    if names:
        year = f" ({manifest.created[:4]})" if manifest.created else ""
        parts.append(", ".join(names) + year + ".")
    parts.append(manifest.title.rstrip(".") + ".")
    if manifest.version:
        parts.append(f"Version {manifest.version}.")
    if manifest.id:
        parts.append(f"`{manifest.id}`.")
    return " ".join(parts)


def _rights(manifest: Manifest) -> list[str]:
    lines = []
    for license_ in manifest.licenses or []:
        label = license_.name or license_.title or license_.path or ""
        title = f" ({license_.title})" if license_.title and license_.name else ""
        link = f": <{license_.path}>" if license_.path and license_.path != label else ""
        lines.append(f"- Licensed {label}{title}{link}")
    status = manifest.rights_status
    if status is not None:
        statement = f": {' '.join(status.statement.split())}" if status.statement else ""
        lines.append(f"- Rights status {status.status}{statement}")
    return lines


def _about(manifest: Manifest, project: Project | None) -> list[str]:
    lines = []
    if project is not None:
        lines.append(f"- **Project:** {project.title}")
    elif manifest.project:
        lines.append(f"- **Project:** `{manifest.project}`")
    if manifest.access:
        lines.append(f"- **Access:** {manifest.access}")
    if manifest.keywords:
        lines.append(f"- **Keywords:** {', '.join(manifest.keywords)}")
    temporal = manifest.temporal_coverage
    if temporal is not None:
        end = "ongoing" if temporal.ongoing else str(temporal.end)
        lines.append(f"- **Temporal coverage:** {temporal.start} to {end}")
    spatial = manifest.spatial_coverage
    if spatial is not None:
        west, south, east, north = spatial.bbox
        box = f"west {west}, south {south}, east {east}, north {north}"
        place = f". {' '.join(spatial.description.split())}" if spatial.description else ""
        lines.append(f"- **Spatial coverage:** {box}{place}")
    return lines


def _codes(schema: TableSchema, field: Field) -> str:
    resource = code_list_resource(schema, field)
    if resource:
        return f"`{resource}`"
    return "undocumented" if field.code_list == "undocumented" else ""


def _resource(resource: Resource) -> list[str]:
    heading = f"### `{resource.name}`"
    if resource.title:
        heading += f": {resource.title}"
    facts = [f"Kind: {resource.kind}."]
    if resource.kind == "linked":
        facts.append(f"Held at <{resource.path}>.")
    elif isinstance(resource.path, str):
        facts.append(f"File: `{resource.path}`.")
    if resource.alternate_of:
        facts.append(f"The same data as `{resource.alternate_of}`, in another format.")
    lines = [heading, "", " ".join(facts)]
    if resource.description:
        lines += ["", " ".join(resource.description.split())]
    members = [m.path for m in resource.files or [] if m.path != resource.path]
    if members:
        lines += ["", "With " + ", ".join(f"`{m}`" for m in members) + "."]
    schema = resource.table_schema
    if schema is not None and schema.fields:
        rows = [
            [f"`{f.name}`", f.title or "", f.type or "", f.description or "", _codes(schema, f)]
            for f in schema.fields
        ]
        lines += ["", *_table(["Column", "Title", "Type", "Description", "Codes"], rows)]
    return lines


def render_readme(manifest: Manifest, project: Project | None = None) -> str:
    """The package's README.md. A property the manifest leaves out is left out here too."""
    lines = [f"# {manifest.title or manifest.name or manifest.id or 'Untitled package'}", ""]
    if manifest.description:
        lines += [" ".join(manifest.description.split()), ""]
    lines += [
        "This README is generated from `datapackage.json`. Edit the manifest, not this file.",
        "",
    ]
    citation = _citation(manifest)
    if citation:
        lines += ["## Citation", "", citation, ""]
    names = [n for n in (person_name(c) for c in creators(manifest)) if n]
    if names:
        lines += ["## Creators", "", *(f"- {n}" for n in names), ""]
    rights = _rights(manifest)
    if rights:
        lines += ["## Rights", "", *rights, ""]
    about = _about(manifest, project)
    if about:
        lines += ["## About", "", *about, ""]
    if manifest.resources:
        lines += ["## Resources", ""]
        for resource in manifest.resources:
            lines += [*_resource(resource), ""]
    return "\n".join(lines).rstrip("\n") + "\n"
