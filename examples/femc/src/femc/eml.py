"""FEMC's EML, rewritten into standard EML so the unchanged `from_eml` reads it.

Every FEMC record shares one non-standard shape: the dataset's title, description, purpose
and coverage sit on its one `dataTable`, project people are elements named for their role,
`publisher` wraps a `metadataProvider`, attributes have `measurementType` (with lower-case
`datetime`) and a bare `enumeratedDomain`, and `physical` holds a misspelled `distibution`
and FEMC's preferred citation. `standardize` moves each into its standard place, keeps
nothing it can't place, and returns the lines of what it dropped.
"""

from typing import NamedTuple
from xml.etree import ElementTree as ET

from archive_contract.exports.eml import END_UNKNOWN, PROJECT_KEYWORDS
from archive_contract.imports.eml import STANDARD, _refuse_dtd

UNKNOWN_FREQUENCY = "unknown"
"""The update frequency the EML export writes beside `END_UNKNOWN`."""


class Standardized(NamedTuple):
    """The rewritten record, the lines of what was dropped, FEMC's preferred citation (taken
    out of `physical`) and FEMC's object name (such as `VMC.23.214`)."""

    xml: str
    dropped: list[str]
    citation: str | None
    object_name: str | None


def _local(element: ET.Element) -> str:
    return element.tag.rpartition("}")[2]


def _namespace(element: ET.Element) -> str:
    """The `{uri}` prefix of an element's tag, or '' when it has none."""
    return element.tag[: element.tag.index("}") + 1] if element.tag.startswith("{") else ""


def _kids(element: ET.Element | None, name: str) -> list[ET.Element]:
    return [] if element is None else [c for c in element if _local(c) == name]


def _kid(element: ET.Element | None, name: str) -> ET.Element | None:
    found = _kids(element, name)
    return found[0] if found else None


def _text(element: ET.Element | None) -> str:
    return "" if element is None else " ".join("".join(element.itertext()).split())


def _new(parent: ET.Element, name: str, text: str | None = None) -> ET.Element:
    """A new element in the parent's namespace, not yet attached."""
    element = ET.Element(_namespace(parent) + name)
    element.text = text
    return element


def _rename(element: ET.Element, name: str) -> None:
    element.tag = _namespace(element) + name


def _para(parent: ET.Element, name: str, text: str) -> ET.Element:
    """A TextType element holding one paragraph."""
    element = _new(parent, name)
    element.append(_new(parent, "para", text))
    return element


def _publisher(dataset: ET.Element) -> None:
    for publisher in _kids(dataset, "publisher"):
        for provider in _kids(publisher, "metadataProvider"):
            index = list(publisher).index(provider)
            publisher.remove(provider)
            for offset, child in enumerate(provider):
                publisher.insert(index + offset, child)


def _personnel(project: ET.Element) -> None:
    """Role-named children become personnel with `individualName` and `role`."""
    for personnel in _kids(project, "personnel"):
        index = list(project).index(personnel)
        project.remove(personnel)
        standard = [c for c in personnel if _local(c) in STANDARD["party"]]
        people: list[ET.Element] = []
        if standard:
            kept = _new(project, "personnel")
            kept.extend(standard)
            people.append(kept)
        for child in personnel:
            if _local(child) in STANDARD["party"]:
                continue
            person = _new(project, "personnel")
            individual = _new(project, "individualName")
            for part in ("givenName", "surName"):
                for name in _kids(child, part):
                    individual.append(_new(project, part, _text(name)))
            if len(individual):
                person.append(individual)
            person.extend(c for c in child if _local(c) not in ("givenName", "surName"))
            person.append(_new(project, "role", _local(child)))
            people.append(person)
        for offset, person in enumerate(people):
            project.insert(index + offset, person)


def _project_keywords(project: ET.Element) -> None:
    """The project's keyword set becomes the descriptor the EML export writes for them."""
    for keyword_set in _kids(project, "keywordSet"):
        project.remove(keyword_set)
        words = [w for w in (_text(k) for k in _kids(keyword_set, "keyword")) if w]
        if not words:
            continue
        study_area = _new(project, "studyAreaDescription")
        descriptor = _new(project, "descriptor")
        descriptor.set("name", PROJECT_KEYWORDS)
        descriptor.set("citableClassificationSystem", "false")
        descriptor.extend(_new(project, "descriptorValue", w) for w in words)
        study_area.append(descriptor)
        project.append(study_area)


def _end_unknown(dataset: ET.Element, coverage: ET.Element) -> None:
    """A begin date with no end becomes a single date plus the export's end-unknown marker."""
    marked = False
    for temporal in _kids(coverage, "temporalCoverage"):
        for dates in _kids(temporal, "rangeOfDates"):
            begin = _kid(_kid(dates, "beginDate"), "calendarDate")
            if _kid(dates, "endDate") is not None or begin is None:
                continue
            index = list(temporal).index(dates)
            temporal.remove(dates)
            single = _new(temporal, "singleDateTime")
            single.append(_new(temporal, "calendarDate", _text(begin)))
            temporal.insert(index, single)
            marked = True
    if marked and _kid(dataset, "maintenance") is None:
        maintenance = _new(dataset, "maintenance")
        maintenance.append(_para(dataset, "description", END_UNKNOWN))
        maintenance.append(_new(dataset, "maintenanceUpdateFrequency", UNKNOWN_FREQUENCY))
        dataset.append(maintenance)


def _table(
    dataset: ET.Element, table: ET.Element, dropped: list[str]
) -> tuple[str | None, str | None]:
    """Move the table's title, description, purpose and coverage up to the dataset, name the
    table, and take its citation out. Returns the citation and the object name."""
    path = f"dataset/{_local(table)}"
    title = _text(_kid(table, "title"))
    description = _text(_kid(table, "description"))
    purpose = _text(_kid(table, "purpose"))
    moved_up: list[ET.Element] = []
    if title and _kid(dataset, "title") is None:
        moved_up.append(_new(dataset, "title", title))
    if description and _kid(dataset, "abstract") is None:
        moved_up.append(_para(dataset, "abstract", description))
    for coverage in _kids(table, "coverage"):
        table.remove(coverage)
        if _kid(dataset, "coverage") is None:
            moved_up.append(coverage)
            _end_unknown(dataset, coverage)
        else:
            dropped.append(f"{path}/coverage: the dataset already has a coverage, dropped")
    if purpose and _kid(dataset, "purpose") is None:
        moved_up.append(_para(dataset, "purpose", purpose))
    elif purpose:
        dropped.append(f"{path}/purpose: the dataset already has a purpose, dropped: {purpose}")
    for offset, element in enumerate(moved_up):
        dataset.insert(offset, element)

    for name in ("title", "description", "purpose"):
        for element in _kids(table, name):
            table.remove(element)
    for short_name in _kids(table, "shortName"):
        table.remove(short_name)
        if value := _text(short_name):
            dropped.append(f"{path}/shortName: not standard EML, dropped: {value}")
    named: list[ET.Element] = []
    if title:
        named.append(_new(table, "entityName", title))
    if description:
        named.append(_new(table, "entityDescription", description))
    for offset, element in enumerate(named):
        table.insert(offset, element)

    citation: str | None = None
    object_name: str | None = None
    for physical in _kids(table, "physical"):
        for misspelled in _kids(physical, "distibution"):
            _rename(misspelled, "distribution")
        for element in _kids(physical, "citation"):
            physical.remove(element)
            citation = citation or _text(element) or None
        object_name = object_name or _text(_kid(physical, "objectName")) or None
    for attribute in table.iter():
        if _local(attribute) == "attribute":
            _attribute(attribute)
    return citation, object_name


def _attribute(attribute: ET.Element) -> None:
    """`measurementType` becomes `measurementScale` (with `dateTime` spelled the standard
    way), and a bare `enumeratedDomain` moves into its nominal or ordinal scale."""
    for measurement in _kids(attribute, "measurementType"):
        _rename(measurement, "measurementScale")
    scale = _kid(attribute, "measurementScale")
    for misspelled in _kids(scale, "datetime"):
        _rename(misspelled, "dateTime")
    level = _kid(scale, "nominal")
    if level is None:
        level = _kid(scale, "ordinal")
    if level is None:
        return
    for enumerated in _kids(attribute, "enumeratedDomain"):
        attribute.remove(enumerated)
        domain = _kid(level, "nonNumericDomain")
        if domain is None:
            domain = _new(level, "nonNumericDomain")
            level.append(domain)
        domain.append(enumerated)


def standardize(xml: str) -> Standardized:
    """Rewrite a FEMC record into standard EML. Raises ValueError on a DOCTYPE or entity, or
    when the record is not well-formed XML or has no dataset."""
    _refuse_dtd(xml)
    root = ET.fromstring(xml)
    dataset = _kid(root, "dataset")
    if dataset is None:
        raise ValueError("the EML record has no dataset")
    dropped: list[str] = []
    for project in _kids(dataset, "researchProject"):
        _rename(project, "project")
    _publisher(dataset)
    for project in _kids(dataset, "project"):
        _personnel(project)
        _project_keywords(project)
    citation: str | None = None
    object_name: str | None = None
    for table in _kids(dataset, "dataTable"):
        found_citation, found_object = _table(dataset, table, dropped)
        citation = citation or found_citation
        object_name = object_name or found_object
    return Standardized(ET.tostring(root, encoding="unicode"), dropped, citation, object_name)
