from typing import Any

import pytest
from pydantic import ValidationError

from archive_backend.config import read_archive_config

NAME = "/research-archive/test/archive-config"


class FakeSSM:
    def __init__(self, value: str) -> None:
        self.value = value
        self.names: list[str] = []

    def get_parameter(self, **kwargs: Any) -> dict[str, Any]:
        self.names.append(kwargs["Name"])
        return {"Parameter": {"Value": self.value}}


def test_reads_the_config_from_the_named_parameter() -> None:
    ssm = FakeSSM('{"publisher": "Invented Research Cooperative", "profiles": ["core", "ecology"]}')
    config = read_archive_config(ssm, NAME)
    assert ssm.names == [NAME]
    assert config.publisher == "Invented Research Cooperative"
    assert config.profiles == ["core", "ecology"]


def test_refuses_a_config_that_does_not_validate() -> None:
    with pytest.raises(ValidationError):
        read_archive_config(FakeSSM('{"profiles": ["core"]}'), NAME)
