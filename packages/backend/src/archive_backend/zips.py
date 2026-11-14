"""The version's zips: `package.zip` and one `<resource>.zip` per multi-file resource.

They sit beside the version, at `<open|restricted>/<datasetId>/<version>/_zips/`, and are
written by the page step at publish and by the reindex. `package.zip` holds every file
`checksums.sha256` lists, and `checksums.sha256` itself; a resource's zip holds its paths and
`archive:files` members. Each zip is built in a temporary file and written in one PUT with its
full-object SHA-256, like every archived object, and carries the hash of its members' checksum
lines as metadata, so a zip whose members haven't changed is left as it is.
"""

from __future__ import annotations

import base64
import hashlib
import tempfile
import zipfile
from dataclasses import dataclass
from typing import IO, Any, Protocol

from botocore.exceptions import ClientError

CHECKSUMS = "checksums.sha256"
FOLDER = "_zips/"
PACKAGE = "package"
FINGERPRINT = "members-sha256"
CHUNK = 8 * 1024 * 1024
# Fixed, so the same members always make the same bytes.
STAMP = (1980, 1, 1, 0, 0, 0)


class S3(Protocol):
    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def put_object(self, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class Zip:
    """One zip: its path under the version and the version paths it holds, in order."""

    path: str
    members: tuple[str, ...]


def _stored(path: Any) -> list[str]:
    paths = [path] if isinstance(path, str) else path if isinstance(path, list) else []
    return [p for p in paths if isinstance(p, str) and "://" not in p]


def resource_members(resource: dict[str, Any]) -> list[str]:
    """A resource's files in the archive, its paths first, each once."""
    found = _stored(resource.get("path"))
    for member in resource.get("archive:files") or []:
        found += _stored(member.get("path") if isinstance(member, dict) else None)
    return list(dict.fromkeys(found))


def resource_zips(manifest: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """`(resource name, members)` for each resource with more than one file in the archive."""
    found = []
    for resource in manifest.get("resources") or []:
        name = resource.get("name")
        members = resource_members(resource)
        if isinstance(name, str) and name and "/" not in name and len(members) > 1:
            found.append((name, members))
    return found


def zip_paths(manifest: dict[str, Any]) -> list[str]:
    """The version paths of its zips, from the manifest alone."""
    return [f"{FOLDER}{PACKAGE}.zip"] + [
        f"{FOLDER}{name}.zip" for name, _ in resource_zips(manifest)
    ]


def checksum_lines(text: str) -> dict[str, str]:
    """`checksums.sha256` as `{path: hex digest}`."""
    listed: dict[str, str] = {}
    for line in text.splitlines():
        if line.strip():
            digest, path = line.split(maxsplit=1)
            listed[path.lstrip("*")] = digest.lower()
    return listed


def plan(manifest: dict[str, Any], listed: dict[str, str]) -> list[Zip]:
    """The version's zips: the package's every listed file and checksums.sha256, then each
    multi-file resource's members."""
    zips = [Zip(f"{FOLDER}{PACKAGE}.zip", (*sorted(listed), CHECKSUMS))]
    zips += [
        Zip(f"{FOLDER}{name}.zip", tuple(members)) for name, members in resource_zips(manifest)
    ]
    return zips


def fingerprint(members: tuple[str, ...], hashes: dict[str, str]) -> str:
    lines = "".join(f"{hashes.get(path, '-')}  {path}\n" for path in members)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def _current(s3: S3, bucket: str, key: str) -> str | None:
    """The fingerprint the zip at `key` was written with, or None when there is no zip."""
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    value = (head.get("Metadata") or {}).get(FINGERPRINT)
    return str(value) if value else None


def _build(s3: S3, bucket: str, root: str, members: tuple[str, ...], into: IO[bytes]) -> None:
    with zipfile.ZipFile(into, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
        for path in members:
            info = zipfile.ZipInfo(path, date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            body = s3.get_object(Bucket=bucket, Key=root + path)["Body"]
            with archive.open(info, "w", force_zip64=True) as entry:
                while chunk := body.read(CHUNK):
                    entry.write(chunk)


def write_zips(s3: S3, bucket: str, root: str, manifest: dict[str, Any]) -> list[str]:
    """Write the zips of the version at `root` (`<prefix>/<id>/<version>/`) whose members
    changed, and return the keys written. A version with no checksums.sha256 gets none."""
    try:
        text = s3.get_object(Bucket=bucket, Key=root + CHECKSUMS)["Body"].read()
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return []
        raise
    listed = checksum_lines(text.decode("utf-8"))
    hashes = {**listed, CHECKSUMS: hashlib.sha256(text).hexdigest()}
    written: list[str] = []
    for item in plan(manifest, listed):
        key = root + item.path
        mark = fingerprint(item.members, hashes)
        if _current(s3, bucket, key) == mark:
            continue
        with tempfile.TemporaryFile() as stream:
            _build(s3, bucket, root, item.members, stream)
            stream.seek(0)
            digest = hashlib.sha256()
            while chunk := stream.read(CHUNK):
                digest.update(chunk)
            stream.seek(0)
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=stream,
                ChecksumSHA256=base64.b64encode(digest.digest()).decode("ascii"),
                ContentType="application/zip",
                Metadata={FINGERPRINT: mark},
            )
        written.append(key)
    return written
