"""The weekly integrity check: every archived file against its package's checksums.sha256.

Each published version sits at `<open|restricted>/<datasetId>/<version>/` with
`checksums.sha256` at its root, in `sha256sum` format. Each object was written in one PUT with
a full-object SHA-256 checksum, which S3 returns from a HEAD with checksum mode on.
"""

from __future__ import annotations

import base64
import binascii
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    # Dev-only stubs: the Lambda asset is built without them.
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_sns import SNSClient

CHECKSUMS = "checksums.sha256"
PREFIXES = ("open/", "restricted/")
ALERT_LINES = 50


@dataclass(frozen=True)
class Problem:
    key: str
    kind: Literal["mismatch", "missing", "no-checksum"]


@dataclass(frozen=True)
class _Result:
    checked: int
    problems: list[Problem]


def _manifests(s3: S3Client, bucket: str) -> list[str]:
    paginator = s3.get_paginator("list_objects_v2")
    keys: list[str] = []
    for prefix in PREFIXES:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                key = item.get("Key", "")
                if key.endswith("/" + CHECKSUMS):
                    keys.append(key)
    return keys


def _entries(s3: S3Client, bucket: str, manifest: str) -> list[tuple[str, str]]:
    text = s3.get_object(Bucket=bucket, Key=manifest)["Body"].read().decode("utf-8")
    entries = []
    for line in text.splitlines():
        if line.strip():
            digest, path = line.split(maxsplit=1)
            entries.append((digest.lower(), path.lstrip("*")))
    return entries


def _problem(s3: S3Client, bucket: str, key: str, digest: str) -> Problem | None:
    try:
        head = s3.head_object(Bucket=bucket, Key=key, ChecksumMode="ENABLED")
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return Problem(key=key, kind="missing")
        raise
    stored = head.get("ChecksumSHA256")
    if not stored or "-" in stored:
        return Problem(key=key, kind="no-checksum")
    try:
        actual = base64.b64decode(stored, validate=True).hex()
    except binascii.Error:
        return Problem(key=key, kind="no-checksum")
    return None if actual == digest else Problem(key=key, kind="mismatch")


def _run(s3: S3Client, bucket: str) -> _Result:
    checked = 0
    problems: list[Problem] = []
    for manifest in _manifests(s3, bucket):
        folder = manifest[: -len(CHECKSUMS)]
        for digest, path in _entries(s3, bucket, manifest):
            checked += 1
            problem = _problem(s3, bucket, folder + path, digest)
            if problem:
                problems.append(problem)
    return _Result(checked=checked, problems=problems)


def check_archive(s3: S3Client, bucket: str) -> list[Problem]:
    """Every listed file that is missing, has no full SHA-256, or differs from its line."""
    return _run(s3, bucket).problems


def handler(event: dict[str, Any], context: object) -> dict[str, int]:
    # Problems are reported, never raised: a raise makes Lambda's async invoke retry the scan.
    s3: S3Client = boto3.client("s3")
    result = _run(s3, os.environ["ARCHIVE_BUCKET"])
    if result.problems:
        sns: SNSClient = boto3.client("sns")
        sns.publish(
            TopicArn=os.environ["ALERT_TOPIC_ARN"],
            Subject=f"Archive integrity check: {len(result.problems)} problems",
            Message="\n".join(f"{p.kind} {p.key}" for p in result.problems[:ALERT_LINES]),
        )
    return {"checked": result.checked, "problems": len(result.problems)}
