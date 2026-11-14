"""The catalog file: one row per published dataset, built from a catalog table.

The writer scans a catalog table, keeps each dataset's `META` item, its current version item
and that version's file items, and writes the rows to the derived bucket's `site/catalog.json`,
which CloudFront serves at `/catalog.json` and the search route reads. The reindex calls it after
it flips the active table; Plan 7's publish step calls it too.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Protocol, cast

import boto3

if TYPE_CHECKING:
    # Dev-only stubs: the Lambda asset is built without them.
    from mypy_boto3_s3 import S3Client

KEY = "site/catalog.json"


class DynamoDB(Protocol):
    def scan(self, **kwargs: Any) -> dict[str, Any]: ...


def _str(item: dict[str, Any], name: str) -> str | None:
    value = item.get(name, {}).get("S")
    return value if isinstance(value, str) else None


def _int(item: dict[str, Any], name: str) -> int | None:
    value = item.get(name, {}).get("N")
    return int(value) if isinstance(value, str) else None


def _sk(version: int) -> str:
    return f"V#{version:06d}"


def _creator(contributor: dict[str, Any]) -> str | None:
    if contributor.get("title"):
        return str(contributor["title"])
    name = " ".join(str(contributor[k]) for k in ("givenName", "familyName") if contributor.get(k))
    if name:
        return name
    organization = contributor.get("organization")
    return str(organization) if organization else None


def _row(
    meta: dict[str, Any], version: dict[str, Any], files: list[dict[str, Any]]
) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(_str(version, "manifest") or "{}")
    row: dict[str, Any] = {
        "id": _str(meta, "id"),
        "version": _int(meta, "currentVersion"),
        "title": _str(meta, "title"),
    }
    if manifest.get("description"):
        row["description"] = manifest["description"]
    if manifest.get("keywords"):
        row["keywords"] = list(manifest["keywords"])
    row["access"] = _str(meta, "access")
    licenses = [
        str(lic.get("name") or lic.get("path"))
        for lic in manifest.get("licenses") or []
        if isinstance(lic, dict) and (lic.get("name") or lic.get("path"))
    ]
    if licenses:
        row["licenses"] = licenses
    rights = manifest.get("archive:rightsStatus")
    if isinstance(rights, dict) and rights.get("status"):
        row["rightsStatus"] = rights["status"]
    if manifest.get("archive:project"):
        row["project"] = manifest["archive:project"]
    creators = [
        name
        for c in manifest.get("contributors") or []
        if isinstance(c, dict) and "creator" in (c.get("roles") or [])
        for name in [_creator(c)]
        if name
    ]
    if creators:
        row["creators"] = creators
    formats = sorted(
        {
            str(r["format"])
            for r in manifest.get("resources") or []
            if isinstance(r, dict) and r.get("format")
        }
    )
    if formats:
        row["formats"] = formats
    temporal = manifest.get("archive:temporalCoverage")
    if isinstance(temporal, dict) and temporal.get("start"):
        row["start"] = temporal["start"]
        if temporal.get("end"):
            row["end"] = temporal["end"]
        row["ongoing"] = bool(temporal.get("ongoing"))
    spatial = manifest.get("archive:spatialCoverage")
    if isinstance(spatial, dict) and isinstance(spatial.get("bbox"), list):
        row["bbox"] = list(spatial["bbox"])
    sizes = [size for f in files if (size := _int(f, "bytes")) is not None]
    if sizes:
        row["bytes"] = sum(sizes)
    published = _str(version, "publishedAt")
    if published:
        row["published"] = published
    return row


def catalog_rows(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per dataset `META` item, from its current version and that version's files."""
    by_dataset: dict[str | None, dict[str, dict[str, Any]]] = {}
    for item in items:
        by_dataset.setdefault(_str(item, "PK"), {})[_str(item, "SK") or ""] = item
    rows: list[dict[str, Any]] = []
    for dataset in by_dataset.values():
        meta = dataset.get("META")
        current = _int(meta, "currentVersion") if meta else None
        if meta is None or current is None:
            continue
        sk = _sk(current)
        version = dataset.get(sk)
        if version is None:
            continue
        prefix = f"{sk}#FILE#"
        files = [item for key, item in dataset.items() if key.startswith(prefix)]
        rows.append(_row(meta, version, files))
    return sorted(rows, key=lambda r: str(r["id"]))


def _scan(dynamodb: DynamoDB, table: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    scan: dict[str, Any] = {"TableName": table}
    while True:
        page = dynamodb.scan(**scan)
        items.extend(page.get("Items", []))
        last = page.get("LastEvaluatedKey")
        if not last:
            return items
        scan["ExclusiveStartKey"] = last


def write_catalog_file(
    table_name: str,
    derived_bucket: str,
    *,
    dynamodb: DynamoDB | None = None,
    s3: S3Client | None = None,
) -> int:
    """Write `site/catalog.json` from the catalog table and return how many rows it holds."""
    dynamodb = dynamodb or cast(DynamoDB, boto3.client("dynamodb"))
    s3 = s3 or boto3.client("s3")
    rows = catalog_rows(_scan(dynamodb, table_name))
    s3.put_object(
        Bucket=derived_bucket,
        Key=KEY,
        Body=json.dumps(rows).encode("utf-8"),
        ContentType="application/json",
        CacheControl="max-age=60",
    )
    return len(rows)
