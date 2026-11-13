from pathlib import Path

import pytest
from pydantic import ValidationError

from archive_contract.config import ArchiveConfig, load_config


def test_config_reads_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "archive.yaml"
    path.write_text(
        "publisher: Invented Research Cooperative\n"
        "profiles: [core, ecology]\n"
        "required: [keywords]\n"
        "themes: [water]\n"
        "licenses: [CC-BY-4.0, CC0-1.0]\n"
        "access: [open, by-request]\n"
        "vocabularies:\n"
        "  - field: keywords\n"
        "    name: Invented terms\n"
        "    terms: [temperature, streams]\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.publisher == "Invented Research Cooperative"
    assert [p.name for p in config.load_profiles()] == ["core", "ecology"]
    assert config.access == ["open", "by-request"]
    assert config.vocabularies[0].terms == ["temperature", "streams"]


def test_config_defaults_to_core_and_every_access_level() -> None:
    config = ArchiveConfig(publisher="P")

    assert config.profiles == ["core"]
    assert config.access == ["open", "restricted", "by-request", "description-only"]


def test_config_needs_a_publisher() -> None:
    with pytest.raises(ValidationError):
        ArchiveConfig.model_validate({})


def test_config_refuses_unknown_access_levels_and_fields() -> None:
    with pytest.raises(ValidationError):
        ArchiveConfig.model_validate({"publisher": "P", "access": ["unpublished"]})
    with pytest.raises(ValidationError, match="unknown field"):
        ArchiveConfig.model_validate({"publisher": "P", "required": ["colour"]})


def test_config_naming_an_unknown_profile_fails_when_loading_profiles() -> None:
    config = ArchiveConfig.model_validate({"publisher": "P", "profiles": ["astronomy"]})

    with pytest.raises(ValueError, match="no profile named"):
        config.load_profiles()
