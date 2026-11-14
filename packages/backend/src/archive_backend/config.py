"""The one way a backend Lambda reads the archive config.

The CDK app writes the validated config as JSON to the stage's standard SSM parameter,
`/research-archive/<stage>/archive-config`, at synth.
"""

from typing import Any, Protocol

from archive_contract.config import ArchiveConfig


class ParameterReader(Protocol):
    def get_parameter(self, **kwargs: Any) -> dict[str, Any]: ...


def read_archive_config(ssm: ParameterReader, name: str) -> ArchiveConfig:
    """The archive config held in the SSM parameter `name`."""
    value: str = ssm.get_parameter(Name=name)["Parameter"]["Value"]
    return ArchiveConfig.model_validate_json(value)
