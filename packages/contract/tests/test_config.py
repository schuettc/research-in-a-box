import json
from pathlib import Path

import pytest
import yaml
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
    assert infrastructure.modules.embeddings is None


def test_embeddings_present_means_on_with_titan_v2() -> None:
    modules = Infrastructure.model_validate(
        {"alertEmail": "a@b.c", "modules": {"embeddings": {}}}
    ).modules

    assert modules.embeddings is not None
    assert modules.embeddings.model == "amazon.titan-embed-text-v2:0"
    with pytest.raises(ValidationError):
        Infrastructure.model_validate(
            {"alertEmail": "a@b.c", "modules": {"embeddings": {"model": "cohere.embed-v4"}}}
        )
    with pytest.raises(ValidationError):
        Infrastructure.model_validate(
            {"alertEmail": "a@b.c", "modules": {"embeddings": {"dimensions": 512}}}
        )


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


LOGO = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10"/></svg>'


def _brand_config(tmp_path: Path, brand: str) -> Path:
    (tmp_path / "logo.svg").write_text(LOGO, encoding="utf-8")
    (tmp_path / "favicon.svg").write_text(LOGO, encoding="utf-8")
    path = tmp_path / "archive.yaml"
    path.write_text(f"publisher: Invented Research Cooperative\nbrand:\n{brand}", encoding="utf-8")
    return path


VALID_BRAND = (
    "  intro: The cooperative shares the data behind its field studies.\n"
    "  contact: data@example.org\n"
    "  logo: logo.svg\n"
    "  favicon: favicon.svg\n"
    "  primaryColor: '#24395f'\n"
    "  font: Georgia, 'Times New Roman', serif\n"
)


def test_a_valid_brand_block_loads(tmp_path: Path) -> None:
    brand = load_config(_brand_config(tmp_path, VALID_BRAND)).brand

    assert brand is not None
    assert brand.name == "Invented Research Cooperative"
    assert brand.contact == "data@example.org"
    assert brand.logo == "logo.svg"
    assert brand.favicon == "favicon.svg"
    assert brand.primary_color == "#24395f"
    assert brand.font == "Georgia, 'Times New Roman', serif"


def test_a_brand_name_overrides_the_publisher(tmp_path: Path) -> None:
    brand = load_config(_brand_config(tmp_path, "  name: The Archive\n" + VALID_BRAND)).brand

    assert brand is not None
    assert brand.name == "The Archive"


def test_no_brand_block_gives_the_defaults() -> None:
    config = ArchiveConfig(publisher="P")

    assert config.brand is None


@pytest.mark.parametrize(
    ("change", "field"),
    [
        (("primaryColor: '#24395f'", "primaryColor: navy"), "primaryColor"),
        (("logo: logo.svg", "logo: missing.svg"), "logo"),
        (("contact: data@example.org", "contact: not-an-address"), "contact"),
        (("font: Georgia, 'Times New Roman', serif", 'font: "serif; } body { color: red"'), "font"),
        (("logo: logo.svg", "logo: favicon.ico"), "logo"),
    ],
)
def test_a_bad_brand_value_is_refused_naming_its_field(
    tmp_path: Path, change: tuple[str, str], field: str
) -> None:
    path = _brand_config(tmp_path, VALID_BRAND.replace(*change))
    (tmp_path / "favicon.ico").write_bytes(b"\0")

    with pytest.raises(ValidationError, match=rf"brand\.{field}"):
        load_config(path)


def test_a_300_kb_logo_is_refused(tmp_path: Path) -> None:
    path = _brand_config(tmp_path, VALID_BRAND)
    (tmp_path / "logo.svg").write_bytes(b" " * 300 * 1024)

    with pytest.raises(ValidationError, match=r"brand\.logo[\s\S]*200 KB"):
        load_config(path)


def test_an_unknown_brand_key_is_refused(tmp_path: Path) -> None:
    path = _brand_config(tmp_path, VALID_BRAND + "  colour: '#000000'\n")

    with pytest.raises(ValidationError, match=r"brand\.colour"):
        load_config(path)


def test_an_intro_over_600_characters_is_refused(tmp_path: Path) -> None:
    long = VALID_BRAND.replace("field studies.", "x" * 600)

    with pytest.raises(ValidationError, match=r"brand\.intro"):
        load_config(_brand_config(tmp_path, long))


def test_root_archive_yaml_has_a_brand_and_fits_the_ssm_parameter() -> None:
    config = load_config(REPO_ROOT / "archive.yaml")
    as_json = json.dumps(yaml.safe_load((REPO_ROOT / "archive.yaml").read_text("utf-8")))

    assert config.brand is not None
    assert config.brand.logo is not None
    assert len(as_json.encode("utf-8")) <= 4096


@pytest.mark.parametrize(
    "svg",
    [
        '<svg xmlns="http://www.w3.org/2000/svg" role="img"><rect width="1" height="1"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" aria-label="X"><rect width="1" height="1"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><rect onclick="x()" width="1" height="1"/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
    ],
)
def test_an_svg_cognito_or_a_browser_would_refuse_is_refused(tmp_path: Path, svg: str) -> None:
    # Cognito's managed login refused role and aria-label on a deploy; script, handlers and
    # foreignObject would run in the app, which serves the logo from its own origin.
    path = _brand_config(tmp_path, VALID_BRAND)
    (tmp_path / "logo.svg").write_text(svg, encoding="utf-8")

    with pytest.raises(ValidationError, match=r"brand\.logo[\s\S]*not allowed"):
        load_config(path)
