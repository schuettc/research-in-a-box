"""Write the JSON Schema of the archive contract.

The root is the package manifest; the project record, change log line, finding, archive
config and review policy sit under `$defs` beside the manifest's own definitions.

Usage: python -m archive_contract.schema <path>
"""

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import JsonSchemaMode, models_json_schema

from archive_contract.changes import Change
from archive_contract.config import ArchiveConfig
from archive_contract.findings import Finding
from archive_contract.manifest import Manifest
from archive_contract.project import Project
from archive_contract.review import ReviewPolicy

ROOT: type[BaseModel] = Manifest
ALSO: tuple[type[BaseModel], ...] = (Project, Change, Finding, ArchiveConfig, ReviewPolicy)


def build() -> dict[str, Any]:
    models: list[tuple[type[BaseModel], JsonSchemaMode]] = [
        (model, "validation") for model in (ROOT, *ALSO)
    ]
    _, combined = models_json_schema(models, ref_template="#/$defs/{model}")
    defs: dict[str, Any] = combined["$defs"]
    root: dict[str, Any] = defs.pop(ROOT.__name__)
    return {**root, "$defs": defs}


def render() -> str:
    return json.dumps(build(), indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m archive_contract.schema")
    parser.add_argument("path", type=Path, help="where to write the JSON Schema")
    args = parser.parse_args(argv)
    args.path.write_text(render(), encoding="utf-8")


if __name__ == "__main__":
    main()
