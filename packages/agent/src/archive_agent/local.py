"""The local tools, which need no network: diagnose and edit_manifest."""

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from archive_agent.errors import LocalError
from archive_contract import write_checksums
from archive_contract.exports.readme import render_readme
from archive_contract.manifest import Manifest
from archive_contract.project import Project
from archive_contract.validate import BUILD, CHECKSUMS, MANIFEST
from cruise.cli import counts, verdict
from cruise.diagnose import diagnose as run_diagnose

README = "README.md"
PROJECT = "project.json"
"""A package built from an imported record keeps its project record at `_build/project.json`."""

PACKAGE_TARGETS = frozenset(
    {
        "title",
        "description",
        "keywords",
        "licenses",
        "archive:rightsStatus",
        "archive:temporalCoverage",
        "archive:spatialCoverage",
        "archive:methods",
        "contributors",
    }
)
COLUMN_TARGETS = frozenset({"title", "description", "archive:unit"})


def _folder(folder: str) -> Path:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise LocalError(f"There is no folder at {root}.")
    return root


def diagnose(folder: str) -> dict[str, Any]:
    """`cruise diagnose --json` for the folder, plus the verdict line cruise prints."""
    result = run_diagnose(_folder(folder))
    return {
        "validation": result.validation.dump(),
        "quality": result.quality.dump() if result.quality else None,
        "findings": [f.dump() for f in result.findings],
        "verdict": verdict(*counts(result.findings)),
    }


def _column(document: dict[str, Any], resource: object, column: object) -> dict[str, Any]:
    """The field named `column` in the resource's table schema or vector attributes."""
    found = next(
        (r for r in document.get("resources", []) if r.get("name") == resource and resource),
        None,
    )
    if found is None:
        raise ValueError(f"there is no resource {resource!r}")
    for key in ("schema", "archive:attributes"):
        schema = found.get(key)
        if not isinstance(schema, dict):
            continue
        for field in schema.get("fields", []):
            if field.get("name") == column:
                result: dict[str, Any] = field
                return result
    raise ValueError(f"resource {resource!r} has no column {column!r}")


def _apply(document: dict[str, Any], edit: object) -> None:
    """Apply one edit to the manifest's JSON form; raise ValueError when it can't be."""
    if not isinstance(edit, dict) or "target" not in edit or "value" not in edit:
        raise ValueError("an edit is an object with a target and a value")
    target, value = edit["target"], edit["value"]
    if "resource" in edit or "column" in edit:
        if target not in COLUMN_TARGETS:
            allowed = ", ".join(sorted(COLUMN_TARGETS))
            raise ValueError(f"a column's {target!r} can't be edited here; only {allowed}")
        owner = _column(document, edit.get("resource"), edit.get("column"))
    elif target in PACKAGE_TARGETS:
        owner = document
    else:
        allowed = ", ".join(sorted(PACKAGE_TARGETS))
        raise ValueError(f"{target!r} can't be edited here; only {allowed}, or a column's text")
    if value is None:
        owner.pop(target, None)
    else:
        owner[target] = value


def _reason(error: Exception) -> str:
    if isinstance(error, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'manifest'}: {e['msg']}"
            for e in error.errors()
        )
    return str(error)


def _replace(target: Path, data: str) -> None:
    """Write `data` to a temporary name beside `target`, then move it into place."""
    try:
        mode = target.stat().st_mode & 0o777
    except FileNotFoundError:
        mode = 0o644
    with tempfile.NamedTemporaryFile(
        dir=target.parent, prefix=f".{target.name}.", delete=False
    ) as out:
        out.write(data.encode("utf-8"))
    os.chmod(out.name, mode)
    os.replace(out.name, target)


def _project(root: Path) -> Project | None:
    path = root / BUILD / PROJECT
    if not path.is_file():
        return None
    try:
        return Project.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, ValidationError):
        return None


def edit_manifest(folder: str, edits: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply approved edits through the contract's Manifest, all or none.

    Every edit is applied and the manifest validated after each; if any fails, nothing is
    written and every failing edit is named. Otherwise `datapackage.json`, `README.md` and
    `checksums.sha256` are each replaced whole.
    """
    root = _folder(folder)
    path = root / MANIFEST
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        Manifest.model_validate(document)
    except FileNotFoundError as exc:
        raise LocalError(f"{root} has no {MANIFEST}.") from exc
    except (ValueError, ValidationError) as exc:
        raise LocalError(f"{path} can't be read as a manifest: {_reason(exc)}") from exc
    if not edits:
        raise LocalError("No edits were given, so nothing was written.")
    failures: list[str] = []
    for number, edit in enumerate(edits, start=1):
        attempt = copy.deepcopy(document)
        try:
            _apply(attempt, edit)
            Manifest.model_validate(attempt)
        except (ValueError, ValidationError) as exc:
            failures.append(f"edit {number}: {_reason(exc)}")
            continue
        document = attempt
    if failures:
        raise LocalError("Nothing was written. " + " ".join(failures))
    manifest = Manifest.model_validate(document)
    data = manifest.model_dump(mode="json", by_alias=True, exclude_unset=True)
    _replace(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    _replace(root / README, render_readme(manifest, _project(root)))
    write_checksums(root)
    return {"applied": len(edits), "written": [MANIFEST, README, CHECKSUMS]}
