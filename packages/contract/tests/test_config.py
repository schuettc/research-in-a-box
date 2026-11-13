from pathlib import Path

import pytest
from pydantic import ValidationError

from archive_contract.config import ArchiveConfig, Infrastructure, Stage, load_config

REPO_ROOT = Path(__file__).resolve().parents[3]


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


def test_infrastructure_reads_from_yaml(tmp_path: Path) -> None:
    path = tmp_path / "archive.yaml"
    path.write_text(
        "publisher: P\n"
        "infrastructure:\n"
        "  alertEmail: data@example.edu\n"
        "  monthlyBudgetUsd: 80\n"
        "  stages:\n"
        "    - name: prod\n"
        "      account: '123456789012'\n"
        "      region: us-east-2\n"
        "    - name: dev\n"
        "  modules:\n"
        "    waf: true\n"
        "    objectLock: {retentionDays: 3650}\n",
        encoding="utf-8",
    )

    infrastructure = load_config(path).infrastructure

    assert infrastructure is not None
    assert infrastructure.alert_email == "data@example.edu"
    assert infrastructure.monthly_budget_usd == 80
    assert [s.name for s in infrastructure.stages] == ["prod", "dev"]
    assert infrastructure.stages[0].account == "123456789012"
    assert infrastructure.stages[0].region == "us-east-2"
    assert infrastructure.stages[1].account is None
    assert infrastructure.modules.waf is True
    assert infrastructure.modules.object_lock is not None
    assert infrastructure.modules.object_lock.retention_days == 3650


def test_infrastructure_defaults_to_prod_only() -> None:
    infrastructure = Infrastructure.model_validate({"alertEmail": "a@b.c"})

    assert [s.name for s in infrastructure.stages] == ["prod"]
    assert infrastructure.monthly_budget_usd == 50
    assert infrastructure.modules.waf is False
    assert infrastructure.modules.object_lock is None


def test_infrastructure_refuses_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        Infrastructure.model_validate({"alertEmail": "a@b.c", "modules": {"wafs": True}})


def test_infrastructure_refuses_duplicate_stage_names() -> None:
    with pytest.raises(ValidationError, match="unique"):
        Infrastructure.model_validate(
            {"alertEmail": "a@b.c", "stages": [{"name": "prod"}, {"name": "prod"}]}
        )
    with pytest.raises(ValidationError):
        Infrastructure.model_validate({"alertEmail": "a@b.c", "stages": []})


def test_stage_refuses_bad_names_and_accounts() -> None:
    with pytest.raises(ValidationError):
        Stage(name="Prod")
    with pytest.raises(ValidationError):
        Stage(name="prod", account="123")


def test_root_archive_yaml_is_valid() -> None:
    config = load_config(REPO_ROOT / "archive.yaml")

    assert config.infrastructure is not None
