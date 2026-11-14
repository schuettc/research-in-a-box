"""The archive config: the one file an adopter edits."""

from pathlib import Path
from typing import Literal, Self, get_args
from xml.etree import ElementTree

import yaml
from pydantic import ConfigDict, PositiveInt, ValidationInfo, field_validator, model_validator
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


BRAND_FILE_MAX_BYTES = 200 * 1024
_BRAND_FILE_SUFFIXES = {"logo": (".svg", ".png"), "favicon": (".svg", ".ico")}
# Cognito's managed login refuses an SVG asset with role or aria-* attributes, failing the
# deploy; script, event handlers and foreignObject would run in the app, which serves the
# logo from its own origin. Refusing them here turns a rolled-back deploy into a config error.
_SVG_REFUSED_ELEMENTS = {"script", "foreignobject"}


def _svg_refusal(text: str) -> str | None:
    """Why this SVG can't be a brand file, or None when it can."""
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        return f"isn't a well-formed SVG ({error})"
    for element in root.iter():
        tag = str(element.tag).rsplit("}", 1)[-1]
        if tag.lower() in _SVG_REFUSED_ELEMENTS:
            return f"has a <{tag}> element, which is not allowed"
        for name in element.attrib:
            attribute = name.rsplit("}", 1)[-1]
            if attribute == "role" or attribute.startswith(("aria-", "on")):
                return f"has a {attribute} attribute on <{tag}>, which is not allowed"
    return None


class Brand(_Strict):
    """How the archive presents itself: the app, the sign-in page and the invitation email.

    `logo` and `favicon` are paths relative to the config file; they are checked only when
    the config is loaded from its file, since a deployed copy travels without them.
    """

    name: str | None = PydanticField(default=None, min_length=1, max_length=120)
    intro: str | None = PydanticField(default=None, min_length=1, max_length=600)
    contact: str | None = PydanticField(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    logo: str | None = None
    favicon: str | None = None
    primary_color: str | None = PydanticField(
        default=None, alias="primaryColor", pattern=r"^#[0-9a-fA-F]{6}$"
    )
    font: str | None = PydanticField(
        default=None, min_length=1, max_length=300, pattern=r"""^[\w ,'"-]+$"""
    )

    @field_validator("logo", "favicon")
    @classmethod
    def _brand_file(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        field = info.field_name or ""
        suffixes = _BRAND_FILE_SUFFIXES[field]
        if not value.lower().endswith(suffixes):
            raise ValueError(f"the {field} must be one of {', '.join(suffixes)}")
        base = info.context.get("config_dir") if isinstance(info.context, dict) else None
        if base is not None:
            path = Path(base) / value
            if not path.is_file():
                raise ValueError(f"no {field} file at {path}")
            if path.stat().st_size > BRAND_FILE_MAX_BYTES:
                raise ValueError(f"the {field} is over 200 KB")
            if path.suffix.lower() == ".svg":
                refusal = _svg_refusal(path.read_text(encoding="utf-8"))
                if refusal:
                    raise ValueError(f"the {field} {refusal}")
        return value


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
    brand: Brand | None = None

    @model_validator(mode="after")
    def _known_fields(self) -> Self:
        check_known_fields(self.required)
        return self

    @model_validator(mode="after")
    def _brand_name_defaults_to_publisher(self) -> Self:
        if self.brand is not None and self.brand.name is None:
            self.brand.name = self.publisher
        return self

    def load_profiles(self) -> list[Profile]:
        return [load_profile(name) for name in self.profiles]


def load_config(path: Path) -> ArchiveConfig:
    """The config at `path`, with its brand files checked beside it."""
    return ArchiveConfig.model_validate(
        yaml.safe_load(path.read_text(encoding="utf-8")),
        context={"config_dir": path.parent},
    )
