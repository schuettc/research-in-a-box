"""How a package states its rights: licenses, or a rights status with a statement."""

from collections.abc import Sequence
from typing import Literal, Self

from pydantic import model_validator

from archive_contract._base import ArchiveModel

RightsStatusValue = Literal["public-domain", "third-party", "all-rights-reserved", "undetermined"]

STATUSES_NEEDING_A_STATEMENT: frozenset[str] = frozenset({"third-party", "all-rights-reserved"})


class License(ArchiveModel):
    """A Frictionless license: an SPDX id in `name`, a license URL in `path`, or both."""

    name: str | None = None
    path: str | None = None
    title: str | None = None

    @model_validator(mode="after")
    def _name_or_path(self) -> Self:
        if not self.name and not self.path:
            raise ValueError("a license needs a name or a path")
        return self


class RightsStatus(ArchiveModel):
    """`archive:rightsStatus`: the rights of a package that has no license.

    `third-party` needs a statement of where the terms are set, `all-rights-reserved` the
    rights statement itself.
    """

    status: RightsStatusValue
    statement: str | None = None

    @model_validator(mode="after")
    def _statement_when_needed(self) -> Self:
        if self.status in STATUSES_NEEDING_A_STATEMENT and not (self.statement or "").strip():
            raise ValueError(f"rights status {self.status!r} needs a statement")
        return self


def rights_stated(licenses: Sequence[License] | None, status: RightsStatus | None) -> bool:
    """True when the rights allow publishing: a license, or a status other than undetermined."""
    if licenses:
        return True
    return status is not None and status.status != "undetermined"
