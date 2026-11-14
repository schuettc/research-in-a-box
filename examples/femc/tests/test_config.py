from pathlib import Path

from archive_contract.config import load_config

FEMC = Path(__file__).resolve().parents[1]


def test_femc_archive_config_loads() -> None:
    config = load_config(FEMC / "archive.yaml")

    assert config.publisher == "Forest Ecosystem Monitoring Cooperative"
    assert [p.name for p in config.load_profiles()] == ["core", "ecology"]
    assert config.themes == ["air", "climate change", "forest", "soil", "water", "wildlife"]
    assert config.infrastructure is None
