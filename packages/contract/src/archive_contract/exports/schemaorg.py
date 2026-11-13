"""A schema.org `Dataset` in JSON-LD, generated from the manifest, for Google Dataset Search."""

from typing import Any

from archive_contract.exports._common import creators, person_name
from archive_contract.manifest import Contributor, Manifest
from archive_contract.project import Project
from archive_contract.resources import Resource


def _creator(contributor: Contributor) -> dict[str, Any]:
    name = person_name(contributor) or "Unknown"
    if contributor.organization and name == contributor.organization:
        return {"@type": "Organization", "name": name}
    out: dict[str, Any] = {"@type": "Person", "name": name}
    if contributor.given_name:
        out["givenName"] = contributor.given_name
    if contributor.family_name:
        out["familyName"] = contributor.family_name
    if contributor.organization:
        out["affiliation"] = {"@type": "Organization", "name": contributor.organization}
    return out


def _download(resource: Resource, url: str | None) -> dict[str, Any] | None:
    if not isinstance(resource.path, str):
        return None
    if resource.kind == "linked" or url is None:
        content_url = resource.path
    else:
        content_url = url.rstrip("/") + "/" + resource.path
    out: dict[str, Any] = {"@type": "DataDownload", "name": resource.name}
    if resource.description:
        out["description"] = resource.description
    encoding = resource.mediatype or resource.format
    if encoding:
        out["encodingFormat"] = encoding
    out["contentUrl"] = content_url
    return out


def to_schemaorg(
    manifest: Manifest, project: Project | None = None, url: str | None = None
) -> dict[str, Any]:
    """The manifest as a schema.org Dataset. `url` is the package's landing page, when it has one;
    local files are given under it, and as package-relative paths without it."""
    data: dict[str, Any] = {"@context": "https://schema.org/", "@type": "Dataset"}
    if manifest.title:
        data["name"] = manifest.title
    if manifest.description:
        data["description"] = manifest.description
    if url:
        data["url"] = url
    if manifest.id:
        data["identifier"] = manifest.id
    if manifest.version:
        data["version"] = manifest.version
    if people := [_creator(c) for c in creators(manifest)]:
        data["creator"] = people
    licenses = [lic.path or lic.name for lic in manifest.licenses or []]
    if licenses:
        data["license"] = licenses[0] if len(licenses) == 1 else licenses
    if manifest.keywords:
        data["keywords"] = list(manifest.keywords)
    if manifest.citation:
        data["creditText"] = manifest.citation

    temporal = manifest.temporal_coverage
    if temporal is not None:
        end = ".." if temporal.ongoing or temporal.end == "unknown" else str(temporal.end)
        data["temporalCoverage"] = f"{temporal.start}/{end}"
    spatial = manifest.spatial_coverage
    if spatial is not None:
        west, south, east, north = spatial.bbox
        place: dict[str, Any] = {
            "@type": "Place",
            "geo": {"@type": "GeoShape", "box": f"{south} {west} {north} {east}"},
        }
        if spatial.description:
            place["description"] = spatial.description
        data["spatialCoverage"] = place

    downloads = [d for d in (_download(r, url) for r in manifest.resources) if d is not None]
    if downloads:
        data["distribution"] = downloads

    if project is not None:
        part: dict[str, Any] = {"@type": "CreativeWork", "name": project.title}
        if project.links:
            part["url"] = project.links[0].url
        data["isPartOf"] = part
    return data
