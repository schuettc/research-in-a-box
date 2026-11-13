"""Write the JSON Schema of the archive contract's root model.

Usage: python -m archive_contract.schema <path>
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel


class ArchiveContract(BaseModel):
    """The root model of an archive package. Empty until Plan 2 defines the format."""


def render() -> str:
    return json.dumps(ArchiveContract.model_json_schema(), indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m archive_contract.schema")
    parser.add_argument("path", type=Path, help="where to write the JSON Schema")
    args = parser.parse_args(argv)
    args.path.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
