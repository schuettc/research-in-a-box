"""Structural validation of a package folder.

Structure only: the manifest parses, every reference points at something that exists, every
listed file has its size and hash recorded and they match, and `checksums.sha256` matches the
files. Quality is the audit's business, not this module's.

Symlinks are refused wherever they appear and never followed, so nothing outside the package
is read or hashed.
"""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath

from pydantic import ValidationError

from archive_contract.findings import Evidence, Finding, Target
from archive_contract.manifest import Manifest
from archive_contract.resources import Resource

MANIFEST = "datapackage.json"
CHECKSUMS = "checksums.sha256"
BUILD = "_build"
HASH_ALGORITHMS = frozenset({"md5", "sha1", "sha256", "sha512"})
"""The hash algorithms Frictionless allows in a resource's `hash`."""


def _error(
    rule: str,
    message: str,
    *,
    resource: str | None = None,
    field: str | None = None,
    path: str | None = None,
    values: list[object] | None = None,
) -> Finding:
    target = None
    if resource is not None or field is not None or path is not None:
        target = Target(resource=resource, field=field, path=path)
    return Finding(
        rule_id=f"structure.{rule}",
        severity="error",
        message=message,
        target=target,
        evidence=Evidence(values=values) if values is not None else None,
    )


def is_package_content(relative: PurePosixPath) -> bool:
    """Everything is package content except the top-level `_build/` folder."""
    return not (len(relative.parts) > 1 and relative.parts[0] == BUILD)


def package_files(root: Path) -> tuple[list[str], list[str]]:
    """The package's files and its symlinks, as sorted relative paths.

    Symlinks, to files or folders, are listed and never followed; `_build/` is not walked.
    """
    files: list[str] = []
    links: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        for name in list(dirnames):
            relative = (here / name).relative_to(root).as_posix()
            if (here / name).is_symlink():
                links.append(relative)
                dirnames.remove(name)
            elif relative == BUILD:
                dirnames.remove(name)
        for name in filenames:
            relative = (here / name).relative_to(root).as_posix()
            if (here / name).is_symlink():
                links.append(relative)
            elif (here / name).is_file() and is_package_content(PurePosixPath(relative)):
                files.append(relative)
    return sorted(files), sorted(links)


def _symlink_in(root: Path, path: str) -> str | None:
    """The first part of `path` that is a symlink, or None when there is none."""
    parts = PurePosixPath(path).parts
    for i in range(1, len(parts) + 1):
        prefix = PurePosixPath(*parts[:i]).as_posix()
        if (root / prefix).is_symlink():
            return prefix
    return None


def _symlink(path: str, *, resource: str | None = None) -> Finding:
    return _error(
        "symlink",
        f"{path} is a symlink, which a package may not hold",
        resource=resource,
        path=path,
    )


def _safe(path: str) -> bool:
    pure = PurePosixPath(path)
    return not pure.is_absolute() and ".." not in pure.parts and "\\" not in path


def _digest(path: Path, algorithm: str) -> str:
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 16), b""):
            h.update(block)
    return h.hexdigest()


def _split_hash(recorded: str) -> tuple[str, str]:
    """A Frictionless hash is `<algorithm>:<hex>`, or bare hex meaning md5."""
    algorithm, _, value = recorded.rpartition(":")
    return (algorithm or "md5").lower(), value.lower()


def _listed_files(resource: Resource) -> list[tuple[str, int | None, str | None]]:
    """The files a resource lists, each with its recorded size and hash."""
    if resource.kind == "linked":
        return []
    if resource.files:
        return [(m.path, m.bytes, m.hash) for m in resource.files]
    if isinstance(resource.path, str):
        return [(resource.path, resource.bytes, resource.hash)]
    if isinstance(resource.path, list):
        # A multi-part resource has one size and hash in Frictionless; it can only be
        # checked per file through `archive:files`.
        return [(p, None, None) for p in resource.path]
    return []


def _check_file(
    root: Path, resource: Resource, path: str, size: int | None, recorded: str | None
) -> list[Finding]:
    name = resource.name
    if not _safe(path):
        return [_error("path-unsafe", f"{path} is outside the package", resource=name, path=path)]
    link = _symlink_in(root, path)
    if link is not None:
        return [_symlink(link, resource=name)]
    file = root / path
    if not file.is_file():
        return [_error("file-missing", f"{path} is listed but absent", resource=name, path=path)]
    if size is None or recorded is None:
        return [
            _error(
                "size-hash-missing",
                f"{path} has no recorded size and hash",
                resource=name,
                path=path,
            )
        ]
    findings: list[Finding] = []
    actual_size = file.stat().st_size
    if actual_size != size:
        findings.append(
            _error(
                "size-mismatch",
                f"{path} is {actual_size} bytes, recorded as {size}",
                resource=name,
                path=path,
                values=[size, actual_size],
            )
        )
    algorithm, expected = _split_hash(recorded)
    if algorithm not in HASH_ALGORITHMS:
        findings.append(
            _error(
                "hash-algorithm",
                f"{path} has a hash in {algorithm!r}, not one of md5, sha1, sha256 or sha512",
                resource=name,
                path=path,
                values=[recorded],
            )
        )
    else:
        actual = _digest(file, algorithm)
        if actual != expected:
            findings.append(
                _error(
                    "hash-mismatch",
                    f"{path} does not match its recorded {algorithm} hash",
                    resource=name,
                    path=path,
                    values=[recorded, f"{algorithm}:{actual}"],
                )
            )
    return findings


def _check_files(root: Path, manifest: Manifest) -> list[Finding]:
    findings: list[Finding] = []
    for resource in manifest.resources:
        if resource.files and isinstance(resource.path, str):
            if resource.path not in {m.path for m in resource.files}:
                findings.append(
                    _error(
                        "main-not-member",
                        f"main file {resource.path} is not in archive:files",
                        resource=resource.name,
                        path=resource.path,
                    )
                )
        for path, size, recorded in _listed_files(resource):
            findings.extend(_check_file(root, resource, path, size, recorded))
    return findings


def _check_references(manifest: Manifest) -> list[Finding]:
    findings: list[Finding] = []
    by_name = {r.name: r for r in manifest.resources}
    for resource in manifest.resources:
        if resource.alternate_of is not None:
            primary = by_name.get(resource.alternate_of)
            if primary is None or primary is resource:
                findings.append(
                    _error(
                        "alternate-of",
                        f"archive:alternateOf names {resource.alternate_of!r}, "
                        "which is not another resource",
                        resource=resource.name,
                        values=[resource.alternate_of],
                    )
                )
        schema = resource.table_schema
        if schema is None:
            continue
        own_fields = set(schema.field_names())
        for key in schema.foreign_keys or []:
            local = key.field_names()
            for field in local:
                if field not in own_fields:
                    findings.append(
                        _error(
                            "foreign-key",
                            f"foreign key uses {field!r}, which is not a field of this table",
                            resource=resource.name,
                            field=field,
                        )
                    )
            ref_name = key.reference.resource or resource.name
            target = by_name.get(ref_name)
            field_label = ", ".join(local)
            if target is None:
                findings.append(
                    _error(
                        "foreign-key",
                        f"foreign key on {field_label} points at resource {ref_name!r}, "
                        "which does not exist",
                        resource=resource.name,
                        field=local[0] if local else None,
                        values=[ref_name],
                    )
                )
                continue
            target_fields = set(target.table_schema.field_names() if target.table_schema else [])
            for ref_field in key.reference.field_names():
                if ref_field not in target_fields:
                    findings.append(
                        _error(
                            "foreign-key",
                            f"foreign key on {field_label} points at {ref_name}.{ref_field}, "
                            "which does not exist",
                            resource=resource.name,
                            field=local[0] if local else None,
                            values=[f"{ref_name}.{ref_field}"],
                        )
                    )
    return findings


def _check_checksums(root: Path) -> list[Finding]:
    checksums = root / CHECKSUMS
    if checksums.is_symlink():
        return [_symlink(CHECKSUMS)]
    if not checksums.is_file():
        return [_error("checksums-missing", f"{CHECKSUMS} is absent", path=CHECKSUMS)]
    findings: list[Finding] = []
    listed: dict[str, str] = {}
    for number, line in enumerate(checksums.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        digest, sep, rest = line.partition(" ")
        path = rest.lstrip(" *")
        if not sep or not path:
            findings.append(
                _error(
                    "checksums-mismatch",
                    f"line {number} of {CHECKSUMS} is not '<sha256>  <path>'",
                    path=CHECKSUMS,
                    values=[line],
                )
            )
            continue
        if path != CHECKSUMS:
            listed[path] = digest.lower()

    present, links = package_files(root)
    findings.extend(_symlink(link) for link in links)
    present_set = set(present)
    for path, digest in listed.items():
        if _safe(path) and _symlink_in(root, path) is not None:
            continue  # refused as a symlink above, and never hashed
        if not _safe(path) or path not in present_set:
            findings.append(
                _error("checksums-orphan", f"{CHECKSUMS} lists {path}, which is absent", path=path)
            )
        elif _digest(root / path, "sha256") != digest:
            findings.append(
                _error(
                    "checksums-mismatch",
                    f"{CHECKSUMS} has a stale hash for {path}",
                    path=path,
                    values=[digest],
                )
            )
    for path in present:
        if path != CHECKSUMS and path not in listed:
            findings.append(
                _error("checksums-unlisted", f"{path} has no line in {CHECKSUMS}", path=path)
            )
    return findings


def validate_package(path: Path) -> list[Finding]:
    """Check a package folder's structure. An empty list means structurally valid."""
    manifest_path = path / MANIFEST
    if manifest_path.is_symlink():
        return [_symlink(MANIFEST)]
    if not manifest_path.is_file():
        return [_error("manifest-missing", f"{MANIFEST} is absent", path=MANIFEST)]
    try:
        manifest = Manifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [_error("manifest-invalid", f"{MANIFEST} is not JSON: {exc}", path=MANIFEST)]
    except ValidationError as exc:
        return [
            _error(
                "manifest-invalid", f"{MANIFEST} does not fit the contract: {exc}", path=MANIFEST
            )
        ]
    findings = _check_references(manifest) + _check_files(path, manifest) + _check_checksums(path)
    return _once_per_symlink(findings)


def _once_per_symlink(findings: list[Finding]) -> list[Finding]:
    """A symlink both listed by a resource and found on disk is reported once."""
    seen: set[str] = set()
    kept: list[Finding] = []
    for finding in findings:
        if finding.rule_id == "structure.symlink" and finding.target is not None:
            if finding.target.path in seen:
                continue
            seen.add(finding.target.path or "")
        kept.append(finding)
    return kept
