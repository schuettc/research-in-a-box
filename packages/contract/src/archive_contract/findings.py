"""Findings: what an audit or a validation reports about a package."""

from typing import Any, Literal

from pydantic import Field as PydanticField

from archive_contract._base import ArchiveModel

Severity = Literal["error", "warning", "note"]


class Target(ArchiveModel):
    """What a finding or a change is about: a resource and field, or a file in the package."""

    resource: str | None = None
    field: str | None = None
    path: str | None = None


class Evidence(ArchiveModel):
    """The rows or values that show the problem or justify the change."""

    rows: list[int] | None = None
    values: list[Any] | None = None


class Finding(ArchiveModel):
    """One problem found in a package, by the rule with id `ruleId`."""

    rule_id: str = PydanticField(alias="ruleId")
    severity: Severity
    message: str
    target: Target | None = None
    evidence: Evidence | None = None
    suggested_fix: str | None = PydanticField(default=None, alias="suggestedFix")
