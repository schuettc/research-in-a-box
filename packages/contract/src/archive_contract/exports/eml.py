"""An EML 2.2.0 document, generated from the manifest with the standard library's XML writer.

How the manifest maps where EML has no direct equivalent:

- A table's code-list column becomes an `enumeratedDomain`, its rows read from the code-list
  table in the package folder (`root`). Each code's `definition` is `label: description`.
- A column marked `archive:codeList: "undocumented"` becomes a `textDomain` whose definition is
  `UNDOCUMENTED_CODES`.
- A column with no description gets `NO_DEFINITION` as its required `attributeDefinition`.
- Each column's logical type is kept as its `storageType`, in the `TABLE_SCHEMA_TYPES` system.
  Numbers need a unit in EML and the format records none, so they carry the custom unit
  `UNKNOWN_UNIT`.
- Ongoing coverage, which EML can't write as a range, is the start date as a single date plus
  a `maintenance` element with update frequency `continually`.
"""

import csv
from collections.abc import Iterable
from pathlib import Path
from xml.etree import ElementTree as ET

from archive_contract.exports._common import code_list_resource, creators, person_name
from archive_contract.fields import Field, TableSchema
from archive_contract.manifest import Contributor, Manifest
from archive_contract.project import Project
from archive_contract.resources import MemberFile, Resource

EML_NAMESPACE = "https://eml.ecoinformatics.org/eml-2.2.0"
SYSTEM = "research-in-a-box"
TABLE_SCHEMA_TYPES = "https://datapackage.org/standard/table-schema/"
UNDOCUMENTED_CODES = "Codes with no documented code list."
NO_DEFINITION = "No definition was given for this column."
UNKNOWN_UNIT = "unknown"
ONGOING = "Data collection is ongoing."

DATE_FORMATS: dict[str, str] = {
    "datetime": "YYYY-MM-DDThh:mm:ss",
    "date": "YYYY-MM-DD",
    "time": "hh:mm:ss",
    "year": "YYYY",
    "yearmonth": "YYYY-MM",
}

CodeRow = dict[str, str]


def _sub(parent: ET.Element, tag: str, text: str | None = None, **attrs: str) -> ET.Element:
    element = ET.SubElement(parent, tag, attrs)
    if text is not None:
        element.text = text
    return element


def _text(parent: ET.Element, tag: str, text: str) -> ET.Element:
    """A TextType element holding one paragraph."""
    element = _sub(parent, tag)
    _sub(element, "para", " ".join(text.split()))
    return element


def split_name(name: str) -> tuple[str | None, str]:
    """A person's name as EML's given name and surname: the last word is the surname."""
    given, _, sur = name.strip().rpartition(" ")
    return (given or None), sur


def _individual(parent: ET.Element, given: str | None, family: str) -> None:
    individual = _sub(parent, "individualName")
    if given:
        _sub(individual, "givenName", given)
    _sub(individual, "surName", family)


def _party(parent: ET.Element, tag: str, contributor: Contributor) -> ET.Element:
    party = _sub(parent, tag)
    if contributor.family_name:
        _individual(party, contributor.given_name, contributor.family_name)
    elif contributor.title:
        _individual(party, *split_name(contributor.title))
    if contributor.organization:
        _sub(party, "organizationName", contributor.organization)
    if len(party) == 0:
        _sub(party, "organizationName", person_name(contributor) or "Unknown")
    if contributor.email:
        _sub(party, "electronicMailAddress", contributor.email)
    if contributor.path:
        _sub(party, "onlineUrl", contributor.path)
    return party


def read_code_list(root: Path, resource: Resource) -> list[CodeRow]:
    """The rows of a code-list table: its `code`, `label` and `description` columns."""
    if not isinstance(resource.path, str):
        raise ValueError(f"code list {resource.name!r} has no single local path")
    with (root / resource.path).open(encoding="utf-8", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def code_definition(row: CodeRow) -> str:
    label = (row.get("label") or "").strip()
    description = (row.get("description") or "").strip()
    if label and description and label != description:
        return f"{label}: {description}"
    return label or description or row["code"]


def _measurement(
    parent: ET.Element, field: Field, codes: list[CodeRow] | None, definition: str
) -> None:
    scale = _sub(parent, "measurementScale")
    kind = field.type or "string"
    if codes is not None:
        domain = _sub(_sub(_sub(scale, "nominal"), "nonNumericDomain"), "enumeratedDomain")
        for row in codes:
            code = _sub(domain, "codeDefinition")
            _sub(code, "code", row["code"])
            _sub(code, "definition", code_definition(row))
    elif kind in ("number", "integer"):
        ratio = _sub(scale, "ratio")
        _sub(_sub(ratio, "unit"), "customUnit", UNKNOWN_UNIT)
        _sub(_sub(ratio, "numericDomain"), "numberType", "integer" if kind == "integer" else "real")
    elif kind in DATE_FORMATS:
        _sub(_sub(scale, "dateTime"), "formatString", field.format or DATE_FORMATS[kind])
    else:
        text = _sub(_sub(_sub(scale, "nominal"), "nonNumericDomain"), "textDomain")
        if field.code_list == "undocumented":
            _sub(text, "definition", UNDOCUMENTED_CODES)
        else:
            _sub(text, "definition", definition)


def _attributes(
    parent: ET.Element, schema: TableSchema, code_lists: dict[str, list[CodeRow]]
) -> None:
    attribute_list = _sub(parent, "attributeList")
    missing = [v for v in schema.missing_values or [] if isinstance(v, str)]
    for field in schema.fields:
        attribute = _sub(attribute_list, "attribute")
        _sub(attribute, "attributeName", field.name)
        if field.title:
            _sub(attribute, "attributeLabel", field.title)
        definition = field.description or NO_DEFINITION
        _sub(attribute, "attributeDefinition", definition)
        if field.type:
            _sub(attribute, "storageType", field.type, typeSystem=TABLE_SCHEMA_TYPES)
        codes_from = code_list_resource(schema, field)
        codes = code_lists[codes_from] if codes_from else None
        _measurement(attribute, field, codes, definition)
        for value in missing:
            code = _sub(attribute, "missingValueCode")
            _sub(code, "code", value)
            _sub(code, "codeExplanation", "Missing value")


def _physical(parent: ET.Element, resource: Resource, member: MemberFile | None) -> None:
    path = member.path if member else resource.path
    if not isinstance(path, str):
        return
    physical = _sub(parent, "physical")
    _sub(physical, "objectName", path)
    size = member.bytes if member else resource.bytes
    if size is not None:
        _sub(physical, "size", str(size), unit="byte")
    digest = member.hash if member else resource.hash
    if digest:
        method, _, value = digest.rpartition(":")
        _sub(
            physical,
            "authentication",
            value,
            method=(method or "md5").upper().replace("SHA", "SHA-"),
        )
    if resource.encoding and member is None:
        _sub(physical, "characterEncoding", resource.encoding)
    data_format = _sub(physical, "dataFormat")
    if resource.format == "csv" and member is None:
        text = _sub(data_format, "textFormat")
        _sub(text, "numHeaderLines", "1")
        _sub(text, "attributeOrientation", "column")
        _sub(_sub(text, "simpleDelimited"), "fieldDelimiter", ",")
    else:
        name = Path(path).suffix.lstrip(".") or resource.format or resource.mediatype or "unknown"
        _sub(_sub(data_format, "externallyDefinedFormat"), "formatName", name)


def _entity(parent: ET.Element, tag: str, resource: Resource) -> ET.Element:
    entity = _sub(parent, tag)
    _sub(entity, "entityName", resource.name)
    if resource.description or resource.title:
        _sub(entity, "entityDescription", resource.description or resource.title)
    members: Iterable[MemberFile | None] = resource.files or [None]
    for member in members:
        _physical(entity, resource, member)
    return entity


def _code_lists(manifest: Manifest, root: Path | None) -> dict[str, list[CodeRow]]:
    names = {
        code_list_resource(r.table_schema, f)
        for r in manifest.resources
        if r.table_schema is not None
        for f in r.table_schema.fields
    } - {None}
    lists: dict[str, list[CodeRow]] = {}
    for name in sorted(n for n in names if n):
        resource = manifest.resource(name)
        if resource is None:
            raise ValueError(f"code list {name!r} is not a resource of the package")
        if root is None:
            raise ValueError(f"reading code list {name!r} needs the package folder: pass root")
        lists[name] = read_code_list(root, resource)
    return lists


def _coverage(parent: ET.Element, manifest: Manifest) -> None:
    spatial, temporal = manifest.spatial_coverage, manifest.temporal_coverage
    if spatial is None and temporal is None:
        return
    coverage = _sub(parent, "coverage")
    if spatial is not None:
        geographic = _sub(coverage, "geographicCoverage")
        _sub(geographic, "geographicDescription", spatial.description or "Bounding box")
        west, south, east, north = spatial.bbox
        box = _sub(geographic, "boundingCoordinates")
        for tag, value in [
            ("westBoundingCoordinate", west),
            ("eastBoundingCoordinate", east),
            ("northBoundingCoordinate", north),
            ("southBoundingCoordinate", south),
        ]:
            _sub(box, tag, str(value))
    if temporal is not None:
        when = _sub(coverage, "temporalCoverage")
        if temporal.end is not None:
            dates = _sub(when, "rangeOfDates")
            _sub(_sub(dates, "beginDate"), "calendarDate", temporal.start.isoformat())
            _sub(_sub(dates, "endDate"), "calendarDate", temporal.end.isoformat())
        else:
            _sub(_sub(when, "singleDateTime"), "calendarDate", temporal.start.isoformat())


def _rights(parent: ET.Element, manifest: Manifest) -> None:
    licenses = manifest.licenses or []
    status = manifest.rights_status
    if licenses:
        lines = []
        for license_ in licenses:
            label = license_.title or license_.name or license_.path
            link = f" ({license_.path})" if license_.path and license_.path != label else ""
            lines.append(f"This work is licensed under {label}{link}.")
        _text(parent, "intellectualRights", " ".join(lines))
    elif status is not None and status.status != "undetermined":
        if status.status == "public-domain":
            _text(parent, "intellectualRights", f"Public domain. {status.statement or ''}")
        else:
            _text(parent, "intellectualRights", status.statement or "")
    for license_ in licenses:
        licensed = _sub(parent, "licensed")
        _sub(licensed, "licenseName", license_.title or license_.name or license_.path or "")
        if license_.path:
            _sub(licensed, "url", license_.path)
        if license_.name:
            _sub(licensed, "identifier", license_.name)


def _project(parent: ET.Element, manifest: Manifest, project: Project) -> None:
    element = _sub(parent, "project")
    _sub(element, "title", project.title)
    people = [(p.name, p.roles or ["member"], p.email, p.organization) for p in project.people]
    if not people:
        people = [
            (person_name(c) or "Unknown", ["creator"], c.email, c.organization)
            for c in creators(manifest)
        ]
    for name, roles, email, organization in people:
        personnel = _sub(element, "personnel")
        _individual(personnel, *split_name(name))
        if organization:
            _sub(personnel, "organizationName", organization)
        if email:
            _sub(personnel, "electronicMailAddress", email)
        for role in roles:
            _sub(personnel, "role", role)
    if project.abstract:
        _text(element, "abstract", project.abstract)
    for funding in manifest.funding or []:
        award = _sub(element, "award")
        _sub(award, "funderName", funding.funder)
        if funding.award_number:
            _sub(award, "awardNumber", funding.award_number)
        _sub(award, "title", funding.award_title or funding.award_number or funding.funder)
        if funding.award_uri:
            _sub(award, "awardUrl", funding.award_uri)


def package_id(manifest: Manifest) -> str:
    """The EML package id: an earlier one when the package came from EML, else id.version."""
    for legacy in manifest.legacy_identifiers or []:
        if legacy.scheme == "eml-package-id":
            return legacy.value
    base = manifest.id or manifest.name or "package"
    return f"{base}.{manifest.version}" if manifest.version else base


def to_eml(manifest: Manifest, project: Project | None = None, *, root: Path | None = None) -> str:
    """The manifest as an EML 2.2.0 document.

    `root` is the package folder, read for the rows of each code list a column uses; without
    it a package with code-list columns raises ValueError.
    """
    code_lists = _code_lists(manifest, root)
    ET.register_namespace("eml", EML_NAMESPACE)
    eml = ET.Element(
        f"{{{EML_NAMESPACE}}}eml", {"packageId": package_id(manifest), "system": SYSTEM}
    )
    dataset = _sub(eml, "dataset")
    for legacy in manifest.legacy_identifiers or []:
        if legacy.scheme != "eml-package-id":
            _sub(dataset, "alternateIdentifier", legacy.value, system=legacy.scheme)
    _sub(dataset, "title", manifest.title or manifest.name or package_id(manifest))
    people = creators(manifest)
    for creator in people:
        _party(dataset, "creator", creator)
    if not people:
        _sub(_sub(dataset, "creator"), "organizationName", "Unknown")
    for contributor in manifest.contributors or []:
        if not contributor.is_creator():
            party = _party(dataset, "associatedParty", contributor)
            _sub(party, "role", (contributor.roles or ["contributor"])[0])
    if manifest.description:
        _text(dataset, "abstract", manifest.description)
    if manifest.keywords:
        keyword_set = _sub(dataset, "keywordSet")
        for keyword in manifest.keywords:
            _sub(keyword_set, "keyword", keyword)
    _rights(dataset, manifest)
    _coverage(dataset, manifest)
    if manifest.temporal_coverage is not None and manifest.temporal_coverage.ongoing:
        maintenance = _sub(dataset, "maintenance")
        _text(maintenance, "description", ONGOING)
        _sub(maintenance, "maintenanceUpdateFrequency", "continually")
    for creator in people:
        _party(dataset, "contact", creator)
    if not people:
        _sub(_sub(dataset, "contact"), "organizationName", "Unknown")
    if manifest.methods:
        methods = _sub(dataset, "methods")
        _text(_sub(methods, "methodStep"), "description", manifest.methods)
    if project is not None:
        _project(dataset, manifest, project)
    for resource in manifest.resources:
        if resource.kind == "linked":
            continue
        if resource.kind == "table" and resource.table_schema is not None:
            table = _entity(dataset, "dataTable", resource)
            _attributes(table, resource.table_schema, code_lists)
        else:
            other = _entity(dataset, "otherEntity", resource)
            _sub(other, "entityType", resource.kind)
    ET.indent(eml)
    return ET.tostring(eml, encoding="unicode", xml_declaration=True) + "\n"
