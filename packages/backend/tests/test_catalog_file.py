import json
from pathlib import Path
from typing import Any, cast

from archive_backend import catalog_file
from archive_backend.catalog_file import catalog_rows, write_catalog_file
from archive_backend.reindex import catalog_items, dataset_item

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package" / "datapackage.json"
TABLE = "catalog-b"
DERIVED = "derived"


def _items(dataset_id: str, manifest: dict[str, Any], version: int = 1) -> list[dict[str, Any]]:
    text = json.dumps(manifest)
    return [
        *catalog_items("open", dataset_id, version, text),
        dataset_item(dataset_id, [("open", version, manifest)]),
    ]


def test_version_item_carries_the_publish_time() -> None:
    published = {"title": "T", "archive:published": "2026-11-13T10:00:00Z"}

    with_time = catalog_items("open", "ds", 1, json.dumps(published))[0]
    without = catalog_items("open", "ds", 1, json.dumps({"title": "T"}))[0]

    assert with_time["publishedAt"] == {"S": "2026-11-13T10:00:00Z"}
    assert "publishedAt" not in without


def test_publish_time_is_read_through_the_contract_and_written_in_utc() -> None:
    offset = {"title": "T", "archive:published": "2026-11-13T12:00:00.250+02:00"}

    item = catalog_items("open", "ds", 1, json.dumps(offset))[0]

    assert item["publishedAt"] == {"S": "2026-11-13T10:00:00Z"}


def test_rows_from_the_sample_package() -> None:
    manifest = json.loads(SAMPLE.read_text())
    manifest["archive:published"] = "2026-11-13T10:00:00Z"
    manifest["archive:project"] = "streams"

    rows = catalog_rows(_items("stream-temperature-sample", manifest))

    assert rows == [
        {
            "id": "stream-temperature-sample",
            "version": 1,
            "title": "Stream temperature at three invented sites",
            "description": manifest["description"],
            "keywords": ["stream temperature", "water quality", "loggers"],
            "access": "open",
            "licenses": ["CC-BY-4.0"],
            "project": "streams",
            "creators": ["Ada Invented"],
            "formats": ["asc", "csv", "md", "png", "shp", "xlsx"],
            "start": "2024-06-01",
            "ongoing": True,
            "bbox": [-72.74, 44.23, -72.66, 44.32],
            "bytes": 3400 + 258 + 184 + 124 + 244 + 145 + 124 + 145 + 41879 + 3051 + 472 + 656,
            "published": "2026-11-13T10:00:00Z",
        }
    ]


def test_rows_from_a_bare_manifest_hold_only_what_it_has() -> None:
    rows = catalog_rows(_items("bare", {"title": "Only a title"}))

    assert rows == [{"id": "bare", "version": 1, "title": "Only a title", "access": "open"}]


def test_rows_name_creators_and_licenses_by_their_fallbacks() -> None:
    manifest = {
        "title": "T",
        "contributors": [
            {"givenName": "Ada", "familyName": "Lovelace", "roles": ["creator"]},
            {"organization": "Example Lab", "roles": ["creator", "publisher"]},
            {"title": "Not a creator", "roles": ["data-curator"]},
        ],
        "licenses": [{"path": "https://example.org/terms"}],
        "archive:rightsStatus": {"status": "public-domain"},
        "archive:temporalCoverage": {"start": "2020-01-01", "end": "unknown"},
    }

    [row] = catalog_rows(_items("ds", manifest))

    assert row["creators"] == ["Ada Lovelace", "Example Lab"]
    assert row["licenses"] == ["https://example.org/terms"]
    assert row["rightsStatus"] == "public-domain"
    assert row["start"] == "2020-01-01"
    assert row["end"] == "unknown"
    assert row["ongoing"] is False


def test_rows_take_the_current_version_only() -> None:
    old = {"title": "Old", "resources": [{"name": "a", "path": "a.csv", "bytes": 5}]}
    new = {"title": "New", "resources": [{"name": "b", "path": "b.csv", "bytes": 7}]}
    items = [
        *catalog_items("open", "ds", 1, json.dumps(old)),
        *catalog_items("open", "ds", 2, json.dumps(new)),
        dataset_item("ds", [("open", 1, old), ("open", 2, new)]),
    ]

    [row] = catalog_rows(items)

    assert row["version"] == 2
    assert row["title"] == "New"
    assert row["bytes"] == 7


class FakeDynamoDB:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.scans: list[dict[str, Any]] = []

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["TableName"] == TABLE
        self.scans.append(kwargs)
        start = kwargs.get("ExclusiveStartKey", {}).get("n", 0)
        page: dict[str, Any] = {"Items": self.items[start : start + 3]}
        if start + 3 < len(self.items):
            page["LastEvaluatedKey"] = {"n": start + 3}
        return page


class FakeS3:
    def __init__(self) -> None:
        self.puts: list[dict[str, Any]] = []

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        self.puts.append(kwargs)
        return {}


def test_write_catalog_file_writes_one_object_with_every_row() -> None:
    items = _items("ds-b", {"title": "B"}) + _items(
        "ds-a", {"title": "A", "resources": [{"name": "x", "path": "x.csv", "bytes": 1}]}
    )
    dynamodb = FakeDynamoDB(items)
    s3 = FakeS3()

    count = write_catalog_file(
        TABLE, DERIVED, dynamodb=cast(catalog_file.DynamoDB, dynamodb), s3=cast(Any, s3)
    )

    assert count == 2
    assert len(dynamodb.scans) > 1
    [put] = s3.puts
    assert put["Bucket"] == DERIVED
    assert put["Key"] == "site/catalog.json"
    assert put["ContentType"] == "application/json"
    assert put["CacheControl"] == "max-age=60"
    assert [row["id"] for row in json.loads(put["Body"])] == ["ds-a", "ds-b"]
