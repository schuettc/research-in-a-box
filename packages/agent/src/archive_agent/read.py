"""Finding and fetching data: search, get_dataset and download."""

import hashlib
import os
import tempfile
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from archive_agent.errors import LocalError, Refused
from archive_agent.state import Session
from archive_contract.exports.readme import citation
from archive_contract.manifest import Manifest


def search(
    session: Session,
    q: str | None = None,
    access: list[str] | None = None,
    license: list[str] | None = None,
    format: list[str] | None = None,
    project: list[str] | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    bbox: list[float] | None = None,
    page: int | None = None,
    size: int | None = None,
) -> dict[str, Any]:
    """One page of matching datasets: rows, total and a count per facet value."""
    if bbox is not None and len(bbox) != 4:
        raise Refused("bbox is four numbers: west, south, east, north.")
    params = {
        "q": q,
        "access": access,
        "license": license,
        "format": format,
        "project": project,
        "from": from_date,
        "to": to_date,
        "bbox": ",".join(str(v) for v in bbox) if bbox is not None else None,
        "page": page,
        "size": size,
    }
    answer: dict[str, Any] = session.archive().get("/api/search", params=params)
    return answer


def _quote(segment: str) -> str:
    return urllib.parse.quote(segment, safe="")


def _citation(manifest: dict[str, Any]) -> str | None:
    try:
        return citation(Manifest.model_validate(manifest))
    except ValidationError:
        return None


def get_dataset(session: Session, id: str, version: int | None = None) -> dict[str, Any]:
    """The dataset, one version's manifest and files (the current one by default), a citation."""
    archive = session.archive()
    dataset: dict[str, Any] = archive.get(f"/api/datasets/{_quote(id)}")
    if version is None or version == dataset.get("currentVersion"):
        number = dataset.get("currentVersion")
        manifest, files = dataset.get("manifest", {}), dataset.get("files", [])
    else:
        found: dict[str, Any] = archive.get(f"/api/datasets/{_quote(id)}/versions/{version}")
        number, manifest, files = found.get("version"), found.get("manifest", {}), found["files"]
    return {
        "id": dataset.get("id", id),
        "title": dataset.get("title"),
        "access": dataset.get("access"),
        "project": dataset.get("project"),
        "currentVersion": dataset.get("currentVersion"),
        "version": number,
        "manifest": manifest,
        "files": files,
        "citation": _citation(manifest),
    }


def _target(root: Path, path: str) -> Path:
    pure = PurePosixPath(path)
    target = (root / Path(*pure.parts)).resolve() if pure.parts else root
    if pure.is_absolute() or "\\" in path or ".." in pure.parts or not target.is_relative_to(root):
        raise LocalError(f"{path} would be written outside {root}, so nothing was downloaded.")
    return target


def _write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".download.", delete=False) as out:
        out.write(data)
    os.replace(out.name, target)


def download(session: Session, id: str, version: int, paths: list[str], to: str) -> dict[str, Any]:
    """Write the named files of one version under `to`, each checked against its SHA-256.

    Open files come from `/data/...`; restricted ones through the signed-in link route. A file
    whose hash doesn't match is not kept and is listed under `failed`.
    """
    root = Path(to).expanduser().resolve()
    targets = {path: _target(root, path) for path in paths}
    archive = session.archive()
    found: dict[str, Any] = archive.get(f"/api/datasets/{_quote(id)}/versions/{version}")
    items = {item["path"]: item for item in found.get("files", [])}
    missing = [path for path in paths if path not in items]
    if missing:
        raise Refused(f"Version {version} of {id} has no file {', '.join(missing)}.")
    is_open = found.get("prefix") == "open"
    written: list[dict[str, Any]] = []
    failed: list[dict[str, str]] = []
    for path, target in targets.items():
        if is_open:
            data = archive.fetch(f"/data/{_quote(id)}/{version}/{urllib.parse.quote(path)}")
        else:
            link: dict[str, Any] = archive.get(
                f"/api/datasets/{_quote(id)}/versions/{version}/download",
                params={"path": path},
                signed_in=True,
            )
            data = archive.fetch(link["url"])
        recorded = items[path].get("hash")
        checked = isinstance(recorded, str) and recorded.lower().startswith("sha256:")
        if checked:
            actual = "sha256:" + hashlib.sha256(data).hexdigest()
            if actual != str(recorded).lower():
                failed.append({"path": path, "reason": f"its hash is {actual}, not {recorded}"})
                continue
        _write(target, data)
        written.append({"path": path, "to": str(target), "bytes": len(data), "checked": checked})
    return {"written": written, "failed": failed}
