"""Submitting and reviewing: submit, submissions, submission_files and decide.

The request and answer shapes are those of `archive_backend.submissions` (Plan 7).
"""

import base64
import hashlib
import json
import urllib.parse
from pathlib import Path, PurePosixPath
from typing import Any

from archive_agent import local
from archive_agent.archive import Archive
from archive_agent.errors import ArchiveError, Conflict, LocalError, Refused
from archive_agent.state import Session
from archive_contract.validate import CHECKSUMS

CONTRIBUTOR = "contributor"
CURATOR = "curator"
DECISIONS = ("approve", "reject", "request-changes")
CHUNK = 1024 * 1024


def _quote(segment: str) -> str:
    return urllib.parse.quote(segment, safe="")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _file(root: Path, path: str) -> Path:
    pure = PurePosixPath(path)
    target = (root / Path(*pure.parts)).resolve()
    if pure.is_absolute() or ".." in pure.parts or not target.is_relative_to(root):
        raise LocalError(f"{CHECKSUMS} lists {path}, which is outside {root}; nothing was sent.")
    if not target.is_file():
        raise LocalError(f"{CHECKSUMS} lists {path}, but there is no such file; nothing was sent.")
    return target


def _files(root: Path) -> list[dict[str, Any]]:
    """The files in checksums.sha256, then checksums.sha256 itself, with sizes and SHA-256."""
    try:
        text = (root / CHECKSUMS).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise LocalError(
            f"{root} has no {CHECKSUMS}, so nothing was sent. Call edit_manifest to write it."
        ) from exc
    paths: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        _, _, path = line.partition("  ")
        if path and path not in paths and path != CHECKSUMS:
            paths.append(path)
    paths.append(CHECKSUMS)
    files = []
    for path in paths:
        target = _file(root, path)
        files.append({"path": path, "size": target.stat().st_size, "sha256": _sha256(target)})
    return files


def submit(session: Session, folder: str, submission: str | None = None) -> dict[str, Any]:
    """Check the folder, upload every file in checksums.sha256 and send it to review.

    With no `submission`, a new submission; else the next round of that one. A failure part
    way answers the plain error; nothing is retried.
    """
    findings = local.diagnose(folder)["findings"]
    errors = sum(1 for f in findings if f.get("severity") == "error")
    if errors:
        noun = "error finding" if errors == 1 else "error findings"
        raise Refused(
            f"The package has {errors} {noun}, so nothing was sent. Call diagnose to see "
            "them, fix them, then submit again."
        )
    root = Path(folder).expanduser().resolve()
    files = _files(root)
    archive = session.archive()
    if submission is None:
        # The manifest's id names the dataset: a published one gets its next version.
        body: dict[str, Any] = {"files": files}
        dataset_id = json.loads((root / "datapackage.json").read_text(encoding="utf-8")).get("id")
        if isinstance(dataset_id, str) and dataset_id:
            body["datasetId"] = dataset_id
        started = archive.post("/api/submissions", body, group=CONTRIBUTOR)
    else:
        started = archive.post(
            f"/api/submissions/{_quote(submission)}/uploads", {"files": files}, group=CONTRIBUTOR
        )
    sid = str(started["submissionId"])
    links = {upload["path"]: upload for upload in started.get("uploads", [])}
    for f in files:
        upload = links.get(f["path"])
        if upload is None:
            raise Refused(
                f"The archive gave no upload link for {f['path']}; nothing was submitted."
            )
        # The archive signs each PUT with the file's SHA-256; S3 refuses a file that differs.
        checksum = base64.b64encode(bytes.fromhex(f["sha256"])).decode()
        headers = {**upload.get("headers", {}), "x-amz-checksum-sha256": checksum}
        with (root / f["path"]).open("rb") as stream:
            archive.put(upload["url"], stream, f["size"], headers)
    sent = archive.post(f"/api/submissions/{_quote(sid)}/submit", {}, group=CONTRIBUTOR)
    return {"id": sid, "round": sent.get("round"), "status": sent.get("status")}


def _report(archive: Archive, link: str) -> Any:
    """The findings report behind its short-lived link, or None when it can't be read."""
    try:
        return json.loads(archive.fetch(link))
    except (ArchiveError, ValueError):
        return None


def submissions(session: Session, id: str | None = None, queue: bool = False) -> dict[str, Any]:
    """One submission with its events and findings report, the curator queue, or your own."""
    archive = session.archive()
    if id is not None:
        one: dict[str, Any] = archive.get(f"/api/submissions/{_quote(id)}", signed_in=True)
        if one.get("reportUrl"):
            one["report"] = _report(archive, str(one["reportUrl"]))
        return one
    if queue:
        found: dict[str, Any] = archive.get(
            "/api/submissions", params={"status": "in-review"}, signed_in=True, group=CURATOR
        )
        rows = found.get("submissions", [])
        # Stale ones first, then the longest waiting.
        rows.sort(key=lambda r: (not r.get("stale"), str(r.get("createdAt", ""))))
        return {"submissions": rows}
    mine: dict[str, Any] = archive.get(
        "/api/submissions", params={"mine": "1"}, signed_in=True, group=CONTRIBUTOR
    )
    return mine


def submission_files(session: Session, id: str) -> dict[str, Any]:
    """The current round's files of a submission in review, each with a five-minute link."""
    try:
        files: dict[str, Any] = session.archive().get(
            f"/api/submissions/{_quote(id)}/files", signed_in=True, group=CURATOR
        )
    except Conflict as exc:
        raise Conflict(
            f"Submission {id} isn't in review, so its files can't be read. Call submissions "
            f"with its id to see where it stands. ({exc})"
        ) from exc
    return files


def decide(session: Session, id: str, decision: str, note: str) -> dict[str, Any]:
    """Post a curator's decision and note on a submission in review."""
    if decision not in DECISIONS:
        raise Refused(f"{decision!r} isn't a decision; give approve, reject or request-changes.")
    answer: dict[str, Any] = session.archive().post(
        f"/api/submissions/{_quote(id)}/decision",
        {"decision": decision, "note": note},
        group=CURATOR,
    )
    return answer
