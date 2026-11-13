"""A DataCite 4.x record in DataCite's JSON form, generated from the manifest.

The archive supplies the publisher and the publication year at publish; the identifier is the
version's DOI once one is minted, and the package id until then.
"""

from typing import Any

from archive_contract.exports._common import creators, person_name
from archive_contract.manifest import Contributor, Manifest
from archive_contract.project import Project

SCHEMA_VERSION = "http://datacite.org/schema/kernel-4"

CONTRIBUTOR_TYPES: dict[str, str] = {
    "contact": "ContactPerson",
    "contact-person": "ContactPerson",
    "data-collector": "DataCollector",
    "data-curator": "DataCurator",
    "data-manager": "DataManager",
    "distributor": "Distributor",
    "editor": "Editor",
    "hosting-institution": "HostingInstitution",
    "producer": "Producer",
    "project-leader": "ProjectLeader",
    "project-manager": "ProjectManager",
    "project-member": "ProjectMember",
    "researcher": "Researcher",
    "research-group": "ResearchGroup",
    "rights-holder": "RightsHolder",
    "sponsor": "Sponsor",
    "supervisor": "Supervisor",
}


def _name(contributor: Contributor) -> dict[str, Any]:
    name = person_name(contributor) or "Unknown"
    out: dict[str, Any] = {"name": name}
    if contributor.given_name or contributor.family_name:
        out["nameType"] = "Personal"
        if contributor.given_name:
            out["givenName"] = contributor.given_name
        if contributor.family_name:
            out["familyName"] = contributor.family_name
    elif contributor.organization and name == contributor.organization:
        out["nameType"] = "Organizational"
    if contributor.organization and name != contributor.organization:
        out["affiliation"] = [{"name": contributor.organization}]
    return out


def _contributors(manifest: Manifest) -> list[dict[str, Any]]:
    out = []
    for contributor in manifest.contributors or []:
        if contributor.is_creator():
            continue
        roles = contributor.roles or []
        kind = next((CONTRIBUTOR_TYPES[r] for r in roles if r in CONTRIBUTOR_TYPES), "Other")
        out.append({"contributorType": kind, **_name(contributor)})
    return out


def _rights(manifest: Manifest) -> list[dict[str, Any]]:
    """The rights list, or a ValueError when the rights do not allow publishing."""
    if manifest.licenses:
        out = []
        for license_ in manifest.licenses:
            entry: dict[str, Any] = {"rights": license_.title or license_.name or license_.path}
            if license_.path:
                entry["rightsUri"] = license_.path
            if license_.name:
                entry["rightsIdentifier"] = license_.name
                entry["rightsIdentifierScheme"] = "SPDX"
                entry["schemeUri"] = "https://spdx.org/licenses/"
            out.append(entry)
        return out
    status = manifest.rights_status
    if status is None:
        raise ValueError("a DataCite record needs rights: the package has no license or status")
    if status.status == "undetermined":
        raise ValueError(
            "rights status 'undetermined' can't be published: "
            "add a license or state the rights before exporting to DataCite"
        )
    if status.status == "public-domain":
        statement = f": {status.statement}" if status.statement else ""
        return [{"rights": f"Public domain{statement}"}]
    return [{"rights": status.statement}]


def _identifier(manifest: Manifest, identifier: str | None) -> dict[str, str]:
    if identifier:
        return {"identifier": identifier, "identifierType": "DOI"}
    if manifest.id:
        return {"identifier": manifest.id, "identifierType": "Local"}
    raise ValueError("a DataCite record needs an identifier: pass a DOI or give the package an id")


def to_datacite(
    manifest: Manifest,
    project: Project | None = None,
    *,
    publisher: str,
    year: int | str,
    identifier: str | None = None,
) -> dict[str, Any]:
    """The manifest as a DataCite 4.x JSON record.

    Raises ValueError when the package has no title, creator or publishable rights.
    """
    if not manifest.title:
        raise ValueError("a DataCite record needs a title")
    people = [_name(c) for c in creators(manifest)]
    if not people:
        raise ValueError("a DataCite record needs at least one creator")

    record: dict[str, Any] = {
        "identifiers": [_identifier(manifest, identifier)],
        "creators": people,
        "titles": [{"title": manifest.title}],
        "publisher": publisher,
        "publicationYear": str(year),
        "types": {"resourceTypeGeneral": "Dataset", "resourceType": "Dataset"},
        "schemaVersion": SCHEMA_VERSION,
    }
    if contributors := _contributors(manifest):
        record["contributors"] = contributors

    descriptions = []
    if manifest.description:
        descriptions.append({"description": manifest.description, "descriptionType": "Abstract"})
    if manifest.methods:
        descriptions.append({"description": manifest.methods, "descriptionType": "Methods"})
    if manifest.purpose:
        descriptions.append({"description": manifest.purpose, "descriptionType": "Other"})
    if project is not None:
        descriptions.append({"description": project.title, "descriptionType": "SeriesInformation"})
    if descriptions:
        record["descriptions"] = descriptions

    if manifest.keywords:
        record["subjects"] = [{"subject": k} for k in manifest.keywords]

    temporal = manifest.temporal_coverage
    if temporal is not None:
        end = "" if temporal.ongoing or temporal.end == "unknown" else str(temporal.end)
        record["dates"] = [{"date": f"{temporal.start}/{end}", "dateType": "Collected"}]

    spatial = manifest.spatial_coverage
    if spatial is not None:
        west, south, east, north = spatial.bbox
        location: dict[str, Any] = {
            "geoLocationBox": {
                "westBoundLongitude": west,
                "eastBoundLongitude": east,
                "southBoundLatitude": south,
                "northBoundLatitude": north,
            }
        }
        if spatial.description:
            location["geoLocationPlace"] = spatial.description
        record["geoLocations"] = [location]

    record["rightsList"] = _rights(manifest)

    related = [
        {
            "relatedIdentifier": r.identifier,
            "relatedIdentifierType": r.identifier_type,
            "relationType": r.relation_type,
        }
        for r in manifest.related_identifiers or []
    ]
    if project is not None and project.links:
        related.append(
            {
                "relatedIdentifier": project.links[0].url,
                "relatedIdentifierType": "URL",
                "relationType": "IsPartOf",
            }
        )
    if related:
        record["relatedIdentifiers"] = related

    funding = []
    for f in manifest.funding or []:
        entry: dict[str, Any] = {"funderName": f.funder}
        if f.award_number:
            entry["awardNumber"] = f.award_number
        if f.award_title:
            entry["awardTitle"] = f.award_title
        if f.award_uri:
            entry["awardUri"] = f.award_uri
        funding.append(entry)
    if funding:
        record["fundingReferences"] = funding

    formats = sorted({r.format for r in manifest.resources if r.format})
    if formats:
        record["formats"] = formats
    if manifest.version:
        record["version"] = manifest.version
    return record
