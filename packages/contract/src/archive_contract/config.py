"""The archive config: the one file an adopter edits."""

from pathlib import Path
from typing import Literal, Self, get_args

import yaml
from pydantic import ConfigDict, PositiveInt, model_validator
from pydantic import Field as PydanticField

from archive_contract._base import ArchiveModel
from archive_contract.manifest import AccessLevel
from archive_contract.profile import Profile, Vocabulary, check_known_fields, load_profile


def _every_access_level() -> list[AccessLevel]:
    return list(get_args(AccessLevel))


class _Strict(ArchiveModel):
    """An infrastructure model: an unknown key is a typo, so it fails validation."""

    model_config = ConfigDict(extra="forbid")


class Stage(_Strict):
    """One deployment of the archive, its own stack, optionally in its own account and region."""

    name: str = PydanticField(pattern=r"^[a-z][a-z0-9-]{0,19}$")
    account: str | None = PydanticField(default=None, pattern=r"^[0-9]{12}$")
    region: str | None = None


class ObjectLock(_Strict):
    """Write-once locking of the archive bucket, in governance mode."""

    retention_days: PositiveInt = PydanticField(alias="retentionDays")


class Embeddings(_Strict):
    """Semantic search: an embedding on each dataset item and a vector index to search them."""

    model: Literal["amazon.titan-embed-text-v2:0"] = "amazon.titan-embed-text-v2:0"


class Modules(_Strict):
    """The optional parts, each built only when switched on."""

    waf: bool = False
    object_lock: ObjectLock | None = PydanticField(default=None, alias="objectLock")
    embeddings: Embeddings | None = PydanticField(default=None, alias="embeddings")


class Infrastructure(_Strict):
    """Where and how the archive is deployed."""

    stages: list[Stage] = PydanticField(default_factory=lambda: [Stage(name="prod")], min_length=1)
    alert_email: str = PydanticField(alias="alertEmail")
    monthly_budget_usd: PositiveInt = PydanticField(default=50, alias="monthlyBudgetUsd")
    modules: Modules = PydanticField(default_factory=Modules)

    @model_validator(mode="after")
    def _unique_stage_names(self) -> Self:
        names = [stage.name for stage in self.stages]
        if len(names) != len(set(names)):
            raise ValueError("stage names must be unique")
        return self


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
    infrastructure: Infrastructure | None = None

    @model_validator(mode="after")
    def _known_fields(self) -> Self:
        check_known_fields(self.required)
        return self

    def load_profiles(self) -> list[Profile]:
        return [load_profile(name) for name in self.profiles]


def load_config(path: Path) -> ArchiveConfig:
    return ArchiveConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
