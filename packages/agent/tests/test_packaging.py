import tomllib
from pathlib import Path

from packaging.requirements import Requirement

PYPROJECT = Path(__file__).parents[1] / "pyproject.toml"


def test_mcp_is_bounded_to_the_2x_line_with_mcpserver() -> None:
    # uvx installs resolve without uv.lock, so the bound is all that picks the SDK.
    dependencies = tomllib.loads(PYPROJECT.read_text())["project"]["dependencies"]
    mcp = next(Requirement(d) for d in dependencies if Requirement(d).name == "mcp")

    assert "2.3.0" in mcp.specifier
    assert "2.2.0" not in mcp.specifier
    assert "1.20.0" not in mcp.specifier
    assert "3.0.0" not in mcp.specifier
