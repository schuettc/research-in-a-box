"""Profiles: YAML files that promote recommended fields to required and switch on rules."""

from importlib import resources
from typing import Self

import yaml
from pydantic import Field as PydanticField
from pydantic import model_validator

from archive_contract._base import ArchiveModel
from archive_contract.manifest import CORE_FIELDS, RECOMMENDED_FIELDS

KNOWN_FIELDS: frozenset[str] = frozenset(CORE_FIELDS + RECOMMENDED_FIELDS)


def check_known_fields(fields: list[str]) -> None:
    unknown = [f for f in fields if f not in KNOWN_FIELDS]
    if unknown:
        raise ValueError(f"unknown field(s) {unknown}; known: {sorted(KNOWN_FIELDS)}")


class Vocabulary(ArchiveModel):
    """A vocabulary for a manifest field, named by URL or given as terms."""

    field: str
    name: str
    url: str | None = None
    terms: list[str] = PydanticField(default_factory=list)


class Profile(ArchiveModel):
    """The fields a profile requires, its vocabularies and the ids of the rules it switches on.

    The rules themselves are code in the audit, not in the contract.
    """

    name: str
    description: str | None = None
    required: list[str] = PydanticField(default_factory=list)
    vocabularies: list[Vocabulary] = PydanticField(default_factory=list)
    rules: list[str] = PydanticField(default_factory=list)

    @model_validator(mode="after")
    def _known_fields(self) -> Self:
        check_known_fields(self.required)
        return self


def _profile_files() -> dict[str, resources.abc.Traversable]:
    folder = resources.files("archive_contract") / "profiles"
    return {
        entry.name.removesuffix(".yaml"): entry
        for entry in folder.iterdir()
        if entry.name.endswith(".yaml")
    }


def available_profiles() -> list[str]:
    return sorted(_profile_files())


def load_profile(name: str) -> Profile:
    files = _profile_files()
    if name not in files:
        raise ValueError(f"no profile named {name!r}; available: {sorted(files)}")
    return Profile.model_validate(yaml.safe_load(files[name].read_text(encoding="utf-8")))
