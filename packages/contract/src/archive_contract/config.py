"""The archive config: the one file an adopter edits."""

from pathlib import Path
from typing import Self, get_args

import yaml
from pydantic import Field as PydanticField
from pydantic import model_validator

from archive_contract._base import ArchiveModel
from archive_contract.manifest import AccessLevel
from archive_contract.profile import Profile, Vocabulary, check_known_fields, load_profile


def _every_access_level() -> list[AccessLevel]:
    return list(get_args(AccessLevel))


class ArchiveConfig(ArchiveModel):
    """Which profiles apply, extra required fields, vocabularies, themes, the licenses and
    access levels offered, and the publisher the archive fills in at publish."""

    publisher: str
    profiles: list[str] = PydanticField(default_factory=lambda: ["core"])
    required: list[str] = PydanticField(default_factory=list)
    vocabularies: list[Vocabulary] = PydanticField(default_factory=list)
    themes: list[str] = PydanticField(default_factory=list)
    licenses: list[str] = PydanticField(default_factory=list)
    access: list[AccessLevel] = PydanticField(default_factory=_every_access_level)

    @model_validator(mode="after")
    def _known_fields(self) -> Self:
        check_known_fields(self.required)
        return self

    def load_profiles(self) -> list[Profile]:
        return [load_profile(name) for name in self.profiles]


def load_config(path: Path) -> ArchiveConfig:
    return ArchiveConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
