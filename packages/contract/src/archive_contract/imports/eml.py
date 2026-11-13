"""Read a standard EML 2.1.1 or 2.2.0 record into a manifest.

Elements are matched by local name, so a record whose children carry the `eml:` prefix reads
the same as one whose children are unqualified. Anything else that isn't standard EML is not
guessed at: it is skipped and listed in `EmlImport.skipped`, as is every standard element the
manifest has no place for. Tolerating one archive's non-standard EML is left to that archive's
converter.

The conventions the EML export writes (see `archive_contract.exports.eml`) are read back, so a
package exported to EML imports to the same title, creators, description, keywords, rights,
coverage, fields and code lists.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any, get_args
from xml.etree import ElementTree as ET

from archive_contract.exports.eml import (
    DATE_FORMATS,
    NO_DEFINITION,
    TABLE_SCHEMA_TYPES,
    UNDOCUMENTED_CODES,
    CodeRow,
    strptime_format,
)
from archive_contract.fields import FieldType
from archive_contract.manifest import Manifest
from archive_contract.project import Person, Project
from archive_contract.resources import ResourceKind

SUPPORTED_NAMESPACES = {
    "eml://ecoinformatics.org/eml-2.1.1": "2.1.1",
    "https://eml.ecoinformatics.org/eml-2.2.0": "2.2.0",
}

# The standard children of each element this importer walks, from the EML 2.1.1 and 2.2.0
# schemas. A child not listed is not standard EML at that place.
STANDARD: dict[str, frozenset[str]] = {
    "eml": frozenset(
        {"access", "dataset", "citation", "software", "protocol", "additionalMetadata"}
    ),
    "dataset": frozenset(
        {
            "alternateIdentifier",
            "shortName",
            "title",
            "creator",
            "metadataProvider",
            "associatedParty",
            "pubDate",
            "language",
            "series",
            "abstract",
            "keywordSet",
            "additionalInfo",
            "intellectualRights",
            "licensed",
            "distribution",
            "coverage",
            "annotation",
            "purpose",
            "introduction",
            "gettingStarted",
            "acknowledgements",
            "maintenance",
            "contact",
            "publisher",
            "pubPlace",
            "methods",
            "project",
            "dataTable",
            "spatialRaster",
            "spatialVector",
            "storedProcedure",
            "view",
            "otherEntity",
            "referencePublication",
            "usageCitation",
            "literatureCited",
            "references",
        }
    ),
    "project": frozenset(
        {
            "title",
            "personnel",
            "abstract",
            "funding",
            "award",
            "studyAreaDescription",
            "designDescription",
            "relatedProject",
            "references",
        }
    ),
    "entity": frozenset(
        {
            "alternateIdentifier",
            "entityName",
            "entityDescription",
            "physical",
            "coverage",
            "methods",
            "additionalInfo",
            "annotation",
            "attributeList",
            "constraint",
            "caseSensitive",
            "numberOfRecords",
            "entityType",
            "references",
            # spatialRaster and spatialVector
            "spatialReference",
            "georeferenceInfo",
            "horizontalAccuracy",
            "verticalAccuracy",
            "cellSizeXDirection",
            "cellSizeYDirection",
            "numberOfBands",
            "rasterOrigin",
            "rows",
            "columns",
            "verticals",
            "cellGeometry",
            "toneGradation",
            "scaleFactor",
            "offset",
            "imageDescription",
            "geometry",
            "geometricObjectCount",
            "topologyLevel",
        }
    ),
    "physical": frozenset(
        {
            "objectName",
            "size",
            "authentication",
            "compressionMethod",
            "encodingMethod",
            "characterEncoding",
            "dataFormat",
            "distribution",
            "references",
        }
    ),
    "attribute": frozenset(
        {
            "attributeName",
            "attributeLabel",
            "attributeDefinition",
            "storageType",
            "measurementScale",
            "missingValueCode",
            "accuracy",
            "coverage",
            "methods",
            "annotation",
            "references",
        }
    ),
}

READ: dict[str, frozenset[str]] = {
    "eml": frozenset({"dataset"}),
    "dataset": frozenset(
        {
            "alternateIdentifier", "title", "creator", "metadataProvider", "associatedParty",
            "pubDate", "abstract", "keywordSet", "intellectualRights", "licensed", "coverage",
            "maintenance", "contact", "methods", "project", "dataTable", "spatialRaster",
            "spatialVector", "otherEntity",
        }
    ),
    "project": frozenset({"title", "personnel", "abstract", "award"}),
    "entity": frozenset(
        {"entityName", "entityDescription", "physical", "attributeList", "entityType"}
    ),
    "physical": frozenset(
        {"objectName", "size", "authentication", "characterEncoding", "dataFormat"}
    ),
    "attribute": frozenset(
        {
            "attributeName", "attributeLabel", "attributeDefinition", "storageType",
            "measurementScale", "missingValueCode",
        }
    ),
}  # fmt: skip

KNOWN_LICENSES: tuple[tuple[str, str, str, str], ...] = (
    # (pattern, SPDX id, URL, title)
    (
        r"creativecommons\.org/licenses/by/4\.0|\bCC[- ]BY[- ]4\.0\b"
        r"|Creative Commons Attribution 4\.0",
        "CC-BY-4.0",
        "https://creativecommons.org/licenses/by/4.0/",
        "Creative Commons Attribution 4.0 International",
    ),
    (
        r"creativecommons\.org/publicdomain/zero/1\.0|\bCC0\b",
        "CC0-1.0",
        "https://creativecommons.org/publicdomain/zero/1.0/",
        "Creative Commons Zero v1.0 Universal",
    ),
)

STORAGE_TYPES: dict[str, FieldType] = {
    "string": "string",
    "float": "number",
    "double": "number",
    "decimal": "number",
    "real": "number",
    "integer": "integer",
    "int": "integer",
    "long": "integer",
    "short": "integer",
    "datetime": "datetime",
    "date": "date",
    "time": "time",
    "boolean": "boolean",
    "gyear": "year",
}

KINDS: frozenset[str] = frozenset(get_args(ResourceKind))
FIELD_TYPES: frozenset[str] = frozenset(get_args(FieldType))
NOT_ONGOING = frozenset({"notPlanned", "unknown"})


@dataclass
class EmlImport:
    """What an EML record gives: the manifest, the rows of each code list to write under
    `data/codes/` (by resource name), the project when the record names one, and what was
    skipped, one line per element path."""

    manifest: Manifest
    code_lists: dict[str, list[CodeRow]] = field(default_factory=dict)
    project: Project | None = None
    skipped: list[str] = field(default_factory=list)


def _local(tag: str) -> str:
    return tag.rpartition("}")[2]


def _kids(element: ET.Element | None, name: str) -> list[ET.Element]:
    return [] if element is None else [c for c in element if _local(c.tag) == name]


def _kid(element: ET.Element | None, name: str) -> ET.Element | None:
    found = _kids(element, name)
    return found[0] if found else None


def _text(element: ET.Element | None) -> str | None:
    """An element's text with whitespace collapsed, paragraphs joined by a blank line."""
    if element is None:
        return None
    paras = [p for p in element.iter() if _local(p.tag) == "para"]
    chunks = paras if paras else [element]
    texts = [" ".join("".join(c.itertext()).split()) for c in chunks]
    joined = "\n\n".join(t for t in texts if t)
    return joined or None


def _kid_text(element: ET.Element | None, name: str) -> str | None:
    return _text(_kid(element, name))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "unnamed"


class _Skips:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def check(self, element: ET.Element, place: str, path: str) -> None:
        for child in element:
            if not isinstance(child.tag, str):
                continue
            name = _local(child.tag)
            if name in READ[place]:
                continue
            reason = "not read" if name in STANDARD[place] else "not standard EML"
            self.counts[f"{path}/{name}: {reason}"] += 1

    def add(self, line: str) -> None:
        self.counts[line] += 1

    def lines(self) -> list[str]:
        return [line if n == 1 else f"{line} ({n} times)" for line, n in self.counts.items()]


def _party(element: ET.Element, roles: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"roles": roles}
    individual = _kid(element, "individualName")
    if individual is not None:
        given = " ".join(t for t in (_text(g) for g in _kids(individual, "givenName")) if t)
        family = _kid_text(individual, "surName")
        if given:
            out["givenName"] = given
        if family:
            out["familyName"] = family
        name = " ".join(p for p in (given, family) if p)
        if name:
            out["title"] = name
    organization = _kid_text(element, "organizationName")
    if organization:
        out["organization"] = organization
    out.setdefault("title", organization or _kid_text(element, "positionName"))
    email = _kid_text(element, "electronicMailAddress")
    if email:
        out["email"] = email
    url = _kid_text(element, "onlineUrl")
    if url:
        out["path"] = url
    return {k: v for k, v in out.items() if v is not None}


def _date(text: str | None, end: bool = False) -> date | None:
    if not text:
        return None
    text = text.strip()
    if re.fullmatch(r"\d{4}", text):
        return date(int(text), 12, 31) if end else date(int(text), 1, 1)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _coverage(dataset: ET.Element, raw: dict[str, Any], skips: _Skips) -> None:
    coverage = _kid(dataset, "coverage")
    boxes, places = [], []
    for geographic in _kids(coverage, "geographicCoverage"):
        box = _kid(geographic, "boundingCoordinates")
        try:
            values = [
                float(_kid_text(box, f"{side}BoundingCoordinate") or "")
                for side in ("west", "south", "east", "north")
            ]
        except ValueError:
            skips.add("dataset/coverage/geographicCoverage: no readable bounding box")
            continue
        boxes.append(values)
        if place := _kid_text(geographic, "geographicDescription"):
            places.append(place)
    if boxes:
        bbox = [
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ]
        raw["archive:spatialCoverage"] = {"bbox": bbox}
        if places:
            raw["archive:spatialCoverage"]["description"] = "; ".join(places)

    starts: list[date] = []
    ends: list[date] = []
    singles: list[date] = []
    for temporal in _kids(coverage, "temporalCoverage"):
        for dates in _kids(temporal, "rangeOfDates"):
            begin = _date(_kid_text(_kid(dates, "beginDate"), "calendarDate"))
            finish = _date(_kid_text(_kid(dates, "endDate"), "calendarDate"), end=True)
            if begin and finish:
                starts.append(begin)
                ends.append(finish)
        for single in _kids(temporal, "singleDateTime"):
            if day := _date(_kid_text(single, "calendarDate")):
                singles.append(day)
    frequency = _kid_text(_kid(dataset, "maintenance"), "maintenanceUpdateFrequency")
    if starts:
        raw["archive:temporalCoverage"] = {
            "start": min(starts + singles).isoformat(),
            "end": max(ends + singles).isoformat(),
        }
    elif singles and frequency and frequency not in NOT_ONGOING:
        raw["archive:temporalCoverage"] = {"start": min(singles).isoformat(), "ongoing": True}
    elif singles:
        raw["archive:temporalCoverage"] = {
            "start": min(singles).isoformat(),
            "end": max(singles).isoformat(),
        }
    if coverage is not None:
        for child in coverage:
            name = _local(child.tag)
            if name not in ("geographicCoverage", "temporalCoverage"):
                known = name in ("taxonomicCoverage", "references")
                skips.add(f"dataset/coverage/{name}: {'not read' if known else 'not standard EML'}")


def _rights(dataset: ET.Element, raw: dict[str, Any]) -> None:
    licenses = []
    for licensed in _kids(dataset, "licensed"):
        entry = {
            "name": _kid_text(licensed, "identifier"),
            "path": _kid_text(licensed, "url"),
            "title": _kid_text(licensed, "licenseName"),
        }
        entry = {k: v for k, v in entry.items() if v}
        if entry.get("name") or entry.get("path"):
            licenses.append(entry)
    statement = _kid_text(dataset, "intellectualRights")
    if not licenses and statement:
        for pattern, spdx, url, title in KNOWN_LICENSES:
            if re.search(pattern, statement, re.IGNORECASE):
                licenses.append({"name": spdx, "path": url, "title": title})
                break
    if licenses:
        raw["licenses"] = licenses
    elif statement:
        if re.search(r"\bpublic domain\b", statement, re.IGNORECASE):
            status = "public-domain"
        elif re.search(r"all rights reserved", statement, re.IGNORECASE):
            status = "all-rights-reserved"
        else:
            status = "third-party"
        raw["archive:rightsStatus"] = {"status": status, "statement": statement}


def _project(dataset: ET.Element, raw: dict[str, Any], skips: _Skips) -> Project | None:
    element = _kid(dataset, "project")
    if element is None:
        return None
    skips.check(element, "project", "dataset/project")
    title = _kid_text(element, "title")
    if not title:
        skips.add("dataset/project: no title, so no project")
        return None
    people = []
    for personnel in _kids(element, "personnel"):
        roles = [r for r in (_text(x) for x in _kids(personnel, "role")) if r]
        party = _party(personnel, roles)
        if party.get("title"):
            people.append(
                Person(
                    name=party["title"],
                    roles=roles,
                    email=party.get("email"),
                    organization=party.get("organization"),
                )
            )
    funding = []
    for award in _kids(element, "award"):
        funder = _kid_text(award, "funderName")
        if funder:
            entry = {
                "funder": funder,
                "awardNumber": _kid_text(award, "awardNumber"),
                "awardTitle": _kid_text(award, "title"),
                "awardUri": _kid_text(award, "awardUrl"),
            }
            funding.append({k: v for k, v in entry.items() if v})
    if funding:
        raw["archive:funding"] = funding
    project = Project(
        id=slug(title), title=title, abstract=_kid_text(element, "abstract"), people=people
    )
    raw["archive:project"] = project.id
    return project


def _field_type(attribute: ET.Element, scale: ET.Element | None) -> tuple[str | None, str | None]:
    """The field's logical type and strptime format, from storageType or measurementScale."""
    storage = _kid(attribute, "storageType")
    storage_text = (_text(storage) or "").strip()
    format_string = _kid_text(_kid(scale, "dateTime"), "formatString")
    kind: str | None = None
    if storage is not None and storage.get("typeSystem") == TABLE_SCHEMA_TYPES:
        kind = storage_text if storage_text in FIELD_TYPES else None
    elif storage_text:
        kind = STORAGE_TYPES.get(storage_text.rpartition(":")[2].lower())
    if kind is None and scale is not None:
        for name in ("ratio", "interval"):
            if (domain := _kid(_kid(scale, name), "numericDomain")) is not None:
                number = _kid_text(domain, "numberType")
                kind = "number" if number == "real" else "integer"
        if _kid(scale, "dateTime") is not None:
            text = format_string or ""
            if "hh" in text:
                kind = "datetime" if "DD" in text else "time"
            elif text == "YYYY":
                kind = "year"
            else:
                kind = "date"
        if _kid(scale, "nominal") is not None or _kid(scale, "ordinal") is not None:
            kind = "string"
    fmt = None
    if format_string and kind in DATE_FORMATS and format_string != DATE_FORMATS[kind]:
        fmt = strptime_format(format_string)
    return kind, fmt


def _code_rows(enumerated: ET.Element) -> list[CodeRow]:
    rows = []
    for definition in _kids(enumerated, "codeDefinition"):
        code = _kid_text(definition, "code") or ""
        text = _kid_text(definition, "definition") or ""
        label, sep, description = text.partition(": ")
        rows.append({"code": code, "label": label, "description": description if sep else ""})
    return rows


def _attributes(
    entity: ET.Element, table: str, path: str, skips: _Skips
) -> tuple[list[dict[str, Any]], dict[str, list[CodeRow]], list[str]]:
    fields: list[dict[str, Any]] = []
    codes: dict[str, list[CodeRow]] = {}
    missing: list[str] = []
    for attribute in _kids(_kid(entity, "attributeList"), "attribute"):
        skips.check(attribute, "attribute", f"{path}/attributeList/attribute")
        name = _kid_text(attribute, "attributeName")
        if not name:
            skips.add(f"{path}/attributeList/attribute: no attributeName, so no field")
            continue
        out: dict[str, Any] = {"name": name}
        definition = _kid_text(attribute, "attributeDefinition")
        label = _kid_text(attribute, "attributeLabel")
        if label and label != name:
            out["title"] = label
        if definition and definition != NO_DEFINITION:
            out["description"] = definition
        scale = _kid(attribute, "measurementScale")
        kind, fmt = _field_type(attribute, scale)
        if kind:
            out["type"] = kind
        if fmt:
            out["format"] = fmt
        domain = None
        for level in ("nominal", "ordinal"):
            found = _kid(_kid(scale, level), "nonNumericDomain")
            domain = found if found is not None else domain
        enumerated = _kid(domain, "enumeratedDomain")
        if enumerated is not None and _kids(enumerated, "codeDefinition"):
            codes[name] = _code_rows(enumerated)
        elif enumerated is not None:
            skips.add(
                f"{path}/attributeList/attribute/.../enumeratedDomain: only codeDefinition is read"
            )
        if _kid_text(_kid(domain, "textDomain"), "definition") == UNDOCUMENTED_CODES:
            out["archive:codeList"] = "undocumented"
        for code in _kids(attribute, "missingValueCode"):
            value = _kid_text(code, "code")
            if value and value not in missing:
                missing.append(value)
        fields.append(out)
    return fields, codes, missing


def _physical(entity: ET.Element, path: str, skips: _Skips) -> list[dict[str, Any]]:
    files = []
    for physical in _kids(entity, "physical"):
        skips.check(physical, "physical", f"{path}/physical")
        name = _kid_text(physical, "objectName")
        if not name:
            continue
        member: dict[str, Any] = {"path": name}
        size = _kid(physical, "size")
        if size is not None and (size.get("unit") in (None, "byte", "bytes")):
            text = _text(size) or ""
            if text.isdigit():
                member["bytes"] = int(text)
        auth = _kid(physical, "authentication")
        if auth is not None and (value := _text(auth)):
            method = (auth.get("method") or "md5").lower().replace("-", "")
            member["hash"] = f"{method}:{value}"
        if encoding := _kid_text(physical, "characterEncoding"):
            member["encoding"] = encoding
        data_format = _kid(physical, "dataFormat")
        if _kid(data_format, "textFormat") is not None:
            member["format"] = (
                "csv"
                if _kid(_kid(data_format, "textFormat"), "simpleDelimited") is not None
                else None
            )
        elif (external := _kid(data_format, "externallyDefinedFormat")) is not None:
            member["format"] = _kid_text(external, "formatName")
        elif data_format is not None:
            for child in data_format:
                known = _local(child.tag) == "binaryRasterFormat"
                reason = "not read" if known else "not standard EML"
                skips.add(f"{path}/physical/dataFormat/{_local(child.tag)}: {reason}")
        files.append({k: v for k, v in member.items() if v is not None})
    return files


def _resource(
    entity: ET.Element,
    tag: str,
    taken: set[str],
    raw_resources: list[dict[str, Any]],
    pending: list[tuple[dict[str, Any], dict[str, list[CodeRow]]]],
    skips: _Skips,
) -> None:
    """Add the entity as a resource. A table's code lists go to `pending`, resolved once every
    entity is read so a code-list table the record lists is reused rather than duplicated."""
    path = f"dataset/{tag}"
    skips.check(entity, "entity", path)
    entity_name = _kid_text(entity, "entityName")
    if not entity_name:
        skips.add(f"{path}: no entityName, so no resource")
        return
    name, n = slug(entity_name), 1
    while name in taken:
        n += 1
        name = f"{slug(entity_name)}-{n}"
    taken.add(name)
    resource: dict[str, Any] = {"name": name}
    if entity_name != name:
        resource["title"] = entity_name
    if description := _kid_text(entity, "entityDescription"):
        resource["description"] = description
    files = _physical(entity, path, skips)
    if files:
        first = files[0]
        resource["path"] = first["path"]
        for key in ("format", "encoding"):
            if key in first:
                resource[key] = first[key]
        if len(files) == 1:
            for key in ("bytes", "hash"):
                if key in first:
                    resource[key] = first[key]
        else:
            resource["archive:files"] = [
                {k: v for k, v in f.items() if k in ("path", "bytes", "hash")} for f in files
            ]
    if tag == "dataTable":
        resource["type"] = "table"
        resource["archive:kind"] = "table"
        fields, codes, missing = _attributes(entity, name, path, skips)
        schema: dict[str, Any] = {"fields": fields}
        if codes:
            pending.append((resource, codes))
        if missing:
            schema["missingValues"] = missing
        resource["schema"] = schema
    elif tag == "spatialVector":
        resource["archive:kind"] = "vector"
    elif tag == "spatialRaster":
        resource["archive:kind"] = "raster"
    else:
        entity_type = (_kid_text(entity, "entityType") or "").lower()
        resource["archive:kind"] = (
            entity_type if entity_type in KINDS - {"table", "linked"} else "file"
        )
    raw_resources.append(resource)


CODE_COLUMNS = ["code", "label", "description"]


def _code_list_name(
    table: str, column: str, taken: set[str], raw_resources: list[dict[str, Any]]
) -> str:
    """The code list's resource name: `<column>-codes`, reusing a code-list table of that name
    the record already lists, and adding a resource for it otherwise."""
    candidates = [slug(f"{column}-codes"), slug(f"{table}-{column}-codes")]
    for candidate in candidates:
        existing = next((r for r in raw_resources if r["name"] == candidate), None)
        if existing is not None:
            names = [f["name"] for f in existing.get("schema", {}).get("fields", [])]
            if names == CODE_COLUMNS:
                return candidate
            continue
        if candidate in taken:
            continue
        taken.add(candidate)
        raw_resources.append(
            {
                "name": candidate,
                "path": f"data/codes/{candidate}.csv",
                "type": "table",
                "title": f"Codes for {column}",
                "format": "csv",
                "mediatype": "text/csv",
                "encoding": "utf-8",
                "archive:kind": "table",
                "schema": {
                    "fields": [{"name": c, "type": "string"} for c in CODE_COLUMNS],
                    "primaryKey": ["code"],
                },
            }
        )
        return candidate
    raise ValueError(f"no free resource name for the code list of {table}.{column}")


def from_eml(xml: str) -> EmlImport:
    """Read an EML 2.1.1 or 2.2.0 record. Raises ValueError when it isn't an EML document."""
    root = ET.fromstring(xml)
    if _local(root.tag) != "eml":
        raise ValueError(f"not an EML document: the root element is {_local(root.tag)!r}")
    skips = _Skips()
    namespace = root.tag[1:].partition("}")[0] if root.tag.startswith("{") else ""
    if namespace not in SUPPORTED_NAMESPACES:
        skips.add(f"eml: namespace {namespace!r} is not EML 2.1.1 or 2.2.0; read as if it were")
    skips.check(root, "eml", "eml")

    raw: dict[str, Any] = {}
    legacy = []
    if package_id := root.get("packageId"):
        legacy.append({"scheme": "eml-package-id", "value": package_id})

    dataset = _kid(root, "dataset")
    if dataset is None:
        raise ValueError("the EML record has no dataset")
    skips.check(dataset, "dataset", "dataset")

    for alternate in _kids(dataset, "alternateIdentifier"):
        if value := _text(alternate):
            legacy.append(
                {"scheme": alternate.get("system") or "alternate-identifier", "value": value}
            )
    if legacy:
        raw["archive:legacyIdentifiers"] = legacy

    if title := _kid_text(dataset, "title"):
        raw["title"] = title
        raw["name"] = slug(title)
    if len(_kids(dataset, "title")) > 1:
        skips.add("dataset/title: only the first title is read")

    contributors = [_party(c, ["creator"]) for c in _kids(dataset, "creator")]
    for party in _kids(dataset, "associatedParty"):
        role = _kid_text(party, "role") or "contributor"
        contributors.append(_party(party, [role]))
    for party in _kids(dataset, "metadataProvider"):
        contributors.append(_party(party, ["metadata-provider"]))
    named = {c.get("title") for c in contributors}
    for party in _kids(dataset, "contact"):
        contact = _party(party, ["contact"])
        if contact.get("title") not in named:
            contributors.append(contact)
            named.add(contact.get("title"))
    contributors = [c for c in contributors if c.get("title")]
    if contributors:
        raw["contributors"] = contributors

    if pub_date := _kid_text(dataset, "pubDate"):
        raw["created"] = pub_date
    if abstract := _kid_text(dataset, "abstract"):
        raw["description"] = abstract
    keywords = [
        k
        for s in _kids(dataset, "keywordSet")
        for k in (_text(x) for x in _kids(s, "keyword"))
        if k
    ]
    if keywords:
        raw["keywords"] = keywords
    _rights(dataset, raw)
    _coverage(dataset, raw, skips)
    methods = _kid(dataset, "methods")
    steps = [_kid_text(step, "description") for step in _kids(methods, "methodStep")]
    if text := "\n\n".join(s for s in steps if s):
        raw["archive:methods"] = text
    if methods is not None:
        for child in methods:
            if _local(child.tag) != "methodStep":
                skips.add(f"dataset/methods/{_local(child.tag)}: not read")
    project = _project(dataset, raw, skips)

    resources: list[dict[str, Any]] = []
    pending: list[tuple[dict[str, Any], dict[str, list[CodeRow]]]] = []
    taken: set[str] = set()
    for child in dataset:
        tag = _local(child.tag)
        if tag in ("dataTable", "otherEntity", "spatialVector", "spatialRaster"):
            _resource(child, tag, taken, resources, pending, skips)
    code_lists: dict[str, list[CodeRow]] = {}
    for table, codes in pending:
        keys = []
        for column, rows in codes.items():
            code_name = _code_list_name(table["name"], column, taken, resources)
            code_lists[code_name] = rows
            reference = {"resource": code_name, "fields": ["code"]}
            keys.append({"fields": [column], "reference": reference})
        table["schema"]["foreignKeys"] = keys
    raw["resources"] = resources

    manifest = Manifest.model_validate(raw)
    return EmlImport(
        manifest=manifest, code_lists=code_lists, project=project, skipped=skips.lines()
    )
