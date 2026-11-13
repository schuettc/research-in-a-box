"""The package manifest, `datapackage.json`, and its `archive:` additions."""

import re
from datetime import date, datetime
from typing import Literal, Self

from pydantic import Field as PydanticField
from pydantic import NonNegativeInt, field_validator, model_validator

from archive_contract._base import ArchiveModel
from archive_contract.resources import Resource
from archive_contract.rights import License, RightsStatus, rights_stated

AccessLevel = Literal["open", "restricted", "by-request", "description-only"]

CORE_FIELDS: tuple[str, ...] = ("title", "description", "creator", "rights", "resources")
"""Required before a package can be published, in the order `missing_core_fields` lists them."""

RECOMMENDED_FIELDS: tuple[str, ...] = (
    "keywords",
    "contributors",
    "archive:temporalCoverage",
    "archive:spatialCoverage",
    "archive:relatedIdentifiers",
    "archive:funding",
    "archive:methods",
)
"""Recommended fields, any of which a profile can promote to required."""

MIN_DESCRIPTION_LENGTH = 50

_VERSION = re.compile(r"[1-9][0-9]*")


class Contributor(ArchiveModel):
    """A Frictionless v2 contributor. A creator is a contributor with the `creator` role."""

    title: str | None = None
    given_name: str | None = PydanticField(default=None, alias="givenName")
    family_name: str | None = PydanticField(default=None, alias="familyName")
    organization: str | None = None
    email: str | None = None
    path: str | None = None
    roles: list[str] | None = None

    def is_creator(self) -> bool:
        return "creator" in (self.roles or [])


class TemporalCoverage(ArchiveModel):
    """When the data covers: a start, and an end date or `ongoing`."""

    start: date
    end: date | None = None
    ongoing: bool = False

    @model_validator(mode="after")
    def _end_or_ongoing(self) -> Self:
        if self.ongoing and self.end is not None:
            raise ValueError("temporal coverage has an end date or is ongoing, not both")
        if self.end is not None and self.end < self.start:
            raise ValueError("temporal coverage ends before it starts")
        return self


class SpatialCoverage(ArchiveModel):
    """Where the data covers, as a WGS 84 bounding box: west, south, east, north.

    West may be greater than east for a box that crosses the antimeridian.
    """

    bbox: tuple[float, float, float, float]
    description: str | None = None

    @field_validator("bbox")
    @classmethod
    def _bbox_in_range(
        cls, bbox: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        west, south, east, north = bbox
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            raise ValueError("longitudes must be between -180 and 180")
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            raise ValueError("latitudes must be between -90 and 90")
        if south > north:
            raise ValueError("south must not be above north")
        return bbox


class RelatedIdentifier(ArchiveModel):
    """A DataCite related identifier, such as a paper the data supplements."""

    identifier: str
    identifier_type: str = PydanticField(alias="identifierType")
    relation_type: str = PydanticField(alias="relationType")


class Funding(ArchiveModel):
    funder: str
    award_number: str | None = PydanticField(default=None, alias="awardNumber")
    award_title: str | None = PydanticField(default=None, alias="awardTitle")
    award_uri: str | None = PydanticField(default=None, alias="awardUri")


class LegacyIdentifier(ArchiveModel):
    """An identifier the data had elsewhere, such as an EML package id."""

    scheme: str
    value: str


class MetadataEdit(ArchiveModel):
    """One in-place metadata edit of the current version."""

    when: datetime
    who: str
    fields: list[str]


class ValidationVerdict(ArchiveModel):
    """Whether the package is structurally valid, by which contract version, and when."""

    valid: bool
    contract_version: str = PydanticField(alias="contractVersion")
    checked_at: datetime = PydanticField(alias="checkedAt")


class QualityVerdict(ArchiveModel):
    """The counts of findings by severity from the last audit."""

    errors: NonNegativeInt
    warnings: NonNegativeInt
    notes: NonNegativeInt
    audited_at: datetime = PydanticField(alias="auditedAt")


class Manifest(ArchiveModel):
    """A package's `datapackage.json`: a Frictionless v2 Data Package with `archive:` additions.

    The core fields are optional here so a package can be built and audited before it is
    complete; `missing_core_fields` lists the ones still absent.
    """

    profile_url: str | None = PydanticField(default=None, alias="$schema")
    id: str | None = None
    name: str | None = None
    version: str | None = None
    title: str | None = None
    description: str | None = None
    homepage: str | None = None
    image: str | None = None
    created: str | None = None
    keywords: list[str] | None = None
    contributors: list[Contributor] | None = None
    licenses: list[License] | None = None
    sources: list[dict[str, object]] | None = None
    resources: list[Resource] = PydanticField(default_factory=list)

    project: str | None = PydanticField(default=None, alias="archive:project")
    access: AccessLevel | None = PydanticField(default=None, alias="archive:access")
    rights_status: RightsStatus | None = PydanticField(default=None, alias="archive:rightsStatus")
    temporal_coverage: TemporalCoverage | None = PydanticField(
        default=None, alias="archive:temporalCoverage"
    )
    spatial_coverage: SpatialCoverage | None = PydanticField(
        default=None, alias="archive:spatialCoverage"
    )
    related_identifiers: list[RelatedIdentifier] | None = PydanticField(
        default=None, alias="archive:relatedIdentifiers"
    )
    funding: list[Funding] | None = PydanticField(default=None, alias="archive:funding")
    methods: str | None = PydanticField(default=None, alias="archive:methods")
    legacy_identifiers: list[LegacyIdentifier] | None = PydanticField(
        default=None, alias="archive:legacyIdentifiers"
    )
    metadata_history: list[MetadataEdit] | None = PydanticField(
        default=None, alias="archive:metadataHistory"
    )
    validation: ValidationVerdict | None = PydanticField(default=None, alias="archive:validation")
    quality: QualityVerdict | None = PydanticField(default=None, alias="archive:quality")

    @field_validator("version", mode="before")
    @classmethod
    def _integer_string_version(cls, value: object) -> object:
        if isinstance(value, int) and not isinstance(value, bool):
            value = str(value)
        if isinstance(value, str) and not _VERSION.fullmatch(value):
            raise ValueError("version is a whole number from 1 up, written as a string")
        return value

    def resource(self, name: str) -> Resource | None:
        return next((r for r in self.resources if r.name == name), None)


def missing_core_fields(manifest: Manifest) -> list[str]:
    """The core fields a manifest still lacks, as ids from `CORE_FIELDS`."""
    missing: list[str] = []
    if not (manifest.title or "").strip():
        missing.append("title")
    if len((manifest.description or "").strip()) < MIN_DESCRIPTION_LENGTH:
        missing.append("description")
    if not any(c.is_creator() for c in manifest.contributors or []):
        missing.append("creator")
    if not rights_stated(manifest.licenses, manifest.rights_status):
        missing.append("rights")
    if not any(r.description or r.title for r in manifest.resources):
        missing.append("resources")
    return missing
