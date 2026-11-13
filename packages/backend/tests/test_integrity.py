import base64
import hashlib
import io
from collections.abc import Iterator
from typing import Any, cast

import pytest
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from archive_backend import integrity
from archive_backend.integrity import Problem, check_archive

BUCKET = "archive"


def _hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


class FakeS3:
    """Objects keyed by S3 key, each with its body and stored ChecksumSHA256 (or None)."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, str | None]] = {}

    def put(self, key: str, body: bytes, checksum: str | None = "auto") -> None:
        self.objects[key] = (body, _b64(body) if checksum == "auto" else checksum)

    def publish_version(self, prefix: str, files: dict[str, bytes]) -> None:
        lines = "".join(f"{_hex(body)}  {path}\n" for path, body in files.items())
        for path, body in files.items():
            self.put(prefix + path, body)
        self.put(prefix + "checksums.sha256", lines.encode())

    def get_paginator(self, name: str) -> "FakeS3":
        assert name == "list_objects_v2"
        return self

    def paginate(self, *, Bucket: str, Prefix: str) -> Iterator[dict[str, Any]]:
        assert Bucket == BUCKET
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        yield {"Contents": [{"Key": k} for k in keys[:2]]} if keys[:2] else {}
        if keys[2:]:
            yield {"Contents": [{"Key": k} for k in keys[2:]]}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def head_object(self, *, Bucket: str, Key: str, ChecksumMode: str) -> dict[str, Any]:
        assert ChecksumMode == "ENABLED"
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        checksum = self.objects[Key][1]
        return {} if checksum is None else {"ChecksumSHA256": checksum}


class FakeSNS:
    def __init__(self) -> None:
        self.published: list[dict[str, str]] = []

    def publish(self, **kwargs: str) -> dict[str, str]:
        self.published.append(kwargs)
        return {"MessageId": "m"}


def _sample() -> FakeS3:
    s3 = FakeS3()
    s3.publish_version("open/ds-1/1/", {"datapackage.json": b"{}", "data/a.csv": b"a,b\n1,2\n"})
    s3.publish_version("restricted/ds-2/3/", {"README.md": b"# R\n"})
    return s3


def _check(s3: FakeS3) -> list[Problem]:
    return check_archive(cast(S3Client, s3), BUCKET)


def test_matching_objects_have_no_problems() -> None:
    assert _check(_sample()) == []


def test_changed_object_is_a_mismatch() -> None:
    s3 = _sample()
    s3.put("open/ds-1/1/data/a.csv", b"a,b\n9,9\n")

    assert _check(s3) == [Problem(key="open/ds-1/1/data/a.csv", kind="mismatch")]


def test_listed_file_that_is_gone_is_missing() -> None:
    s3 = _sample()
    del s3.objects["restricted/ds-2/3/README.md"]

    assert _check(s3) == [Problem(key="restricted/ds-2/3/README.md", kind="missing")]


def test_object_without_a_full_sha256_is_no_checksum() -> None:
    s3 = _sample()
    s3.put("open/ds-1/1/datapackage.json", b"{}", checksum=None)
    s3.put("restricted/ds-2/3/README.md", b"# R\n", checksum="abc-2")

    assert _check(s3) == [
        Problem(key="open/ds-1/1/datapackage.json", kind="no-checksum"),
        Problem(key="restricted/ds-2/3/README.md", kind="no-checksum"),
    ]


def test_handler_alerts_only_when_there_are_problems(monkeypatch: pytest.MonkeyPatch) -> None:
    s3 = _sample()
    sns = FakeSNS()
    clients: dict[str, object] = {"s3": s3, "sns": sns}
    monkeypatch.setattr("boto3.client", lambda name: clients[name])
    monkeypatch.setenv("ARCHIVE_BUCKET", BUCKET)
    monkeypatch.setenv("ALERT_TOPIC_ARN", "arn:aws:sns:us-east-1:1:alerts")

    assert integrity.handler({}, object()) == {"checked": 3, "problems": 0}
    assert sns.published == []

    del s3.objects["open/ds-1/1/data/a.csv"]
    s3.put("restricted/ds-2/3/README.md", b"changed")
    assert integrity.handler({}, object()) == {"checked": 3, "problems": 2}
    assert sns.published == [
        {
            "TopicArn": "arn:aws:sns:us-east-1:1:alerts",
            "Subject": "Archive integrity check: 2 problems",
            "Message": "missing open/ds-1/1/data/a.csv\nmismatch restricted/ds-2/3/README.md",
        }
    ]
