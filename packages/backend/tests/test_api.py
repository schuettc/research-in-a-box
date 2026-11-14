import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from archive_backend import api
from archive_backend.reindex import catalog_items, dataset_item

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package" / "datapackage.json"
ARCHIVE = "archive"
DERIVED = "derived"
TABLE_A = "catalog-a"
TABLE_B = "catalog-b"
PARAMETER = "/research-archive/test/catalog-active"
COUNTS = "download-counts"
USAGE = "usage-responses"
DOMAIN = "d123.cloudfront.net"
CLAIMS = {"sub": "user-1", "email": "a@example.org"}
ADMIN = CLAIMS | {"cognito:groups": "[admin]"}


def _missing(operation: str) -> ClientError:
    return ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, operation)


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.heads = 0
        self.gets = 0
        self.presigned: list[dict[str, Any]] = []

    def put(self, bucket: str, key: str, body: Any, etag: str = '"1"') -> None:
        self.objects[(bucket, key)] = (json.dumps(body).encode(), etag)

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.heads += 1
        if (Bucket, Key) not in self.objects:
            raise _missing("HeadObject")
        return {"ETag": self.objects[(Bucket, Key)][1]}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.gets += 1
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")
        body, etag = self.objects[(Bucket, Key)]

        class Body:
            def read(self) -> bytes:
                return body

        return {"Body": Body(), "ETag": etag}

    def generate_presigned_url(
        self, operation: str, *, Params: dict[str, str], ExpiresIn: int
    ) -> str:
        self.presigned.append({"operation": operation, "Params": Params, "ExpiresIn": ExpiresIn})
        return f"https://{Params['Bucket']}.s3.example/{Params['Key']}?signed"


def _key(item: dict[str, Any], names: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(item[n]["S"] for n in names)


class FakeDynamoDB:
    KEYS = {
        TABLE_A: ("PK", "SK"),
        TABLE_B: ("PK", "SK"),
        COUNTS: ("datasetId", "month"),
        USAGE: ("datasetId", "entry"),
    }

    def __init__(self) -> None:
        self.tables: dict[str, dict[tuple[str, ...], dict[str, Any]]] = {
            name: {} for name in self.KEYS
        }
        self.queries: list[dict[str, Any]] = []

    def load(self, table: str, items: list[dict[str, Any]]) -> None:
        for item in items:
            self.tables[table][_key(item, self.KEYS[table])] = item

    def get_item(self, *, TableName: str, Key: dict[str, Any], **_: Any) -> dict[str, Any]:
        item = self.tables[TableName].get(_key(Key, self.KEYS[TableName]))
        return {"Item": item} if item else {}

    def put_item(self, *, TableName: str, Item: dict[str, Any]) -> dict[str, Any]:
        self.load(TableName, [Item])
        return {}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        table, key = kwargs["TableName"], kwargs["Key"]
        assert kwargs["UpdateExpression"] == "ADD #n :one"
        name = kwargs["ExpressionAttributeNames"]["#n"]
        item = self.tables[table].setdefault(_key(key, self.KEYS[table]), dict(key))
        item[name] = {"N": str(int(item.get(name, {"N": "0"})["N"]) + 1)}
        return {}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        """Equality on the partition key, optional begins_with on the sort key, two per page."""
        self.queries.append(kwargs)
        values = kwargs["ExpressionAttributeValues"]
        names = kwargs.get("ExpressionAttributeNames", {})
        table = kwargs["TableName"]
        if kwargs.get("IndexName") == "GSI1":
            pk, sk = "GSI1PK", "GSI1SK"
        else:
            pk, sk = self.KEYS[table]
        rows = [
            i
            for _, i in sorted(self.tables[table].items())
            if i.get(pk) == values[":pk"]
            and (":sk" not in values or i.get(sk, {}).get("S", "").startswith(values[":sk"]["S"]))
        ]
        if "FilterExpression" in kwargs:
            assert kwargs["FilterExpression"] == "attribute_exists(#v)"
            rows = [r for r in rows if names["#v"] in r]
        if kwargs.get("ScanIndexForward") is False:
            rows.reverse()
        start = kwargs.get("ExclusiveStartKey", {}).get("n", 0)
        page: dict[str, Any] = {"Items": rows[start : start + 2]}
        if start + 2 < len(rows):
            page["LastEvaluatedKey"] = {"n": start + 2}
        return page


class FakeSSM:
    def __init__(self) -> None:
        self.value = "B"
        self.calls = 0

    def get_parameter(self, *, Name: str) -> dict[str, Any]:
        assert Name == PARAMETER
        self.calls += 1
        return {"Parameter": {"Value": self.value}}


class World:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.s3 = FakeS3()
        self.dynamodb = FakeDynamoDB()
        self.ssm = FakeSSM()
        self.now = 1000.0
        clients = api.Clients(s3=self.s3, dynamodb=self.dynamodb, ssm=self.ssm)  # type: ignore[arg-type]
        monkeypatch.setattr(api, "clients", lambda: clients)
        monkeypatch.setattr(api, "_monotonic", lambda: self.now)
        api.reset_caches()
        for name, value in {
            "ARCHIVE_BUCKET": ARCHIVE,
            "DERIVED_BUCKET": DERIVED,
            "CATALOG_TABLE_A": TABLE_A,
            "CATALOG_TABLE_B": TABLE_B,
            "ACTIVE_CATALOG_PARAMETER": PARAMETER,
            "DOWNLOAD_COUNTS_TABLE": COUNTS,
            "USAGE_TABLE": USAGE,
            "SITE_DOMAIN": DOMAIN,
        }.items():
            monkeypatch.setenv(name, value)

    def publish(
        self, dataset_id: str, manifest: dict[str, Any], versions: int = 1, table: str = TABLE_B
    ) -> None:
        access = manifest.get("archive:access", "open")
        prefix = "restricted" if access != "open" else "open"
        items: list[dict[str, Any]] = []
        for version in range(1, versions + 1):
            items += catalog_items(prefix, dataset_id, version, json.dumps(manifest))
        items.append(dataset_item(dataset_id, [(prefix, versions, manifest)]))
        self.dynamodb.load(table, items)

    def call(
        self,
        method: str,
        path: str,
        query: dict[str, list[str]] | None = None,
        body: Any = None,
        claims: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        event: dict[str, Any] = {
            "resource": path,
            "path": path,
            "httpMethod": method,
            "headers": {"content-type": "application/json"},
            "multiValueHeaders": {},
            "queryStringParameters": {k: v[-1] for k, v in query.items()} if query else None,
            "multiValueQueryStringParameters": query,
            "pathParameters": None,
            "body": json.dumps(body) if body is not None else None,
            "isBase64Encoded": False,
            "requestContext": {"stage": "prod", "path": path},
        }
        if claims is not None:
            event["requestContext"]["authorizer"] = {"claims": claims}
        response = api.handler(event, None)
        text = response.get("body")
        return int(response["statusCode"]), json.loads(text) if text else None


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    yield World(monkeypatch)
    api.reset_caches()


def _sample(**extra: Any) -> dict[str, Any]:
    return dict(json.loads(SAMPLE.read_text()), **extra)


ROWS = [
    {
        "id": "lake",
        "version": 1,
        "title": "Lake chemistry",
        "access": "open",
        "formats": ["csv"],
        "published": "2026-01-01T00:00:00Z",
    },
    {
        "id": "stream",
        "version": 2,
        "title": "Stream temperature",
        "description": "Hourly lake inflow loggers",
        "access": "restricted",
        "formats": ["csv", "shp"],
        "bbox": [177.0, -19.0, -179.0, -16.0],
    },
]


def test_search_filters_pages_and_counts(world: World) -> None:
    world.s3.put(DERIVED, "site/catalog.json", ROWS)

    status, body = world.call("GET", "/api/search", {"q": ["lake"], "access": ["restricted"]})

    assert status == 200
    assert body["total"] == 1
    assert body["rows"] == [ROWS[1]]
    assert body["facets"]["access"] == {"open": 1, "restricted": 1}
    assert body["facets"]["format"] == {"csv": 1, "shp": 1}


def test_search_reads_from_to_bbox_and_paging(world: World) -> None:
    world.s3.put(DERIVED, "site/catalog.json", ROWS)

    _, boxed = world.call("GET", "/api/search", {"bbox": ["178,-20,-178,-15"]})
    _, dated = world.call("GET", "/api/search", {"from": ["2020-01-01"], "to": ["2021-01-01"]})
    _, paged = world.call("GET", "/api/search", {"page": ["2"], "size": ["1"]})

    assert [r["id"] for r in boxed["rows"]] == ["stream"]
    assert dated["total"] == 0
    assert [r["id"] for r in paged["rows"]] == ["stream"]


@pytest.mark.parametrize(
    "query",
    [
        {"size": ["0"]},
        {"size": ["101"]},
        {"page": ["0"]},
        {"bbox": ["1,2,3"]},
        {"bbox": ["a,b,c,d"]},
    ],
)
def test_search_refuses_bad_paging_and_boxes(world: World, query: dict[str, list[str]]) -> None:
    world.s3.put(DERIVED, "site/catalog.json", ROWS)

    status, _ = world.call("GET", "/api/search", query)

    assert status in (400, 422)


def test_search_rereads_the_catalog_only_when_its_etag_changes(world: World) -> None:
    world.s3.put(DERIVED, "site/catalog.json", ROWS[:1])
    world.call("GET", "/api/search")
    world.s3.put(DERIVED, "site/catalog.json", ROWS, etag='"2"')

    world.now += 30
    _, cached = world.call("GET", "/api/search")
    world.now += 31
    _, fresh = world.call("GET", "/api/search")
    world.now += 61
    world.call("GET", "/api/search")

    assert cached["total"] == 1
    assert fresh["total"] == 2
    assert world.s3.heads == 3
    assert world.s3.gets == 2


def test_search_without_a_catalog_file_finds_nothing(world: World) -> None:
    status, body = world.call("GET", "/api/search")

    assert status == 200
    assert body["total"] == 0 and body["rows"] == []


def test_dataset_reads_the_active_table(world: World) -> None:
    world.publish("stream-temperature-sample", _sample(**{"archive:project": "streams"}))
    world.publish("other", {"title": "Only in A"}, table=TABLE_A)

    status, body = world.call("GET", "/api/datasets/stream-temperature-sample")
    missing, _ = world.call("GET", "/api/datasets/other")

    assert status == 200
    assert body["id"] == "stream-temperature-sample"
    assert body["title"] == "Stream temperature at three invented sites"
    assert body["access"] == "open"
    assert body["currentVersion"] == 1
    assert body["project"] == "streams"
    assert body["manifest"]["id"] == "stream-temperature-sample"
    paths = {f["path"] for f in body["files"]}
    assert "data/logger.csv" in paths and "data/sites/sites.dbf" in paths
    logger = next(f for f in body["files"] if f["path"] == "data/logger.csv")
    assert logger["bytes"] == 3400 and logger["format"] == "csv"
    assert missing == 404


def test_active_table_is_cached_for_a_minute(world: World) -> None:
    world.publish("ds", {"title": "In B"})
    world.publish("ds", {"title": "In A"}, table=TABLE_A)

    _, first = world.call("GET", "/api/datasets/ds")
    world.ssm.value = "A"
    world.now += 30
    _, cached = world.call("GET", "/api/datasets/ds")
    world.now += 31
    _, flipped = world.call("GET", "/api/datasets/ds")

    assert [first["title"], cached["title"], flipped["title"]] == ["In B", "In B", "In A"]
    assert world.ssm.calls == 2


def test_versions_and_one_version(world: World) -> None:
    world.publish("ds", {"title": "T", "archive:published": "2026-11-13T10:00:00Z"}, versions=3)

    status, versions = world.call("GET", "/api/datasets/ds/versions")
    one_status, one = world.call("GET", "/api/datasets/ds/versions/2")

    assert status == 200
    assert versions == {
        "versions": [
            {"version": n, "prefix": "open", "publishedAt": "2026-11-13T10:00:00Z"}
            for n in (1, 2, 3)
        ]
    }
    assert one_status == 200
    assert one["version"] == 2
    assert one["manifest"]["title"] == "T"
    assert [f["path"] for f in one["files"]] == []


@pytest.mark.parametrize(
    "path",
    [
        "/api/datasets/nope",
        "/api/datasets/nope/versions",
        "/api/datasets/nope/versions/1",
        "/api/datasets/ds/versions/9",
        "/api/projects/nope",
    ],
)
def test_missing_reads_answer_404(world: World, path: str) -> None:
    world.publish("ds", {"title": "T"})

    status, _ = world.call("GET", path)

    assert status == 404


def test_project_reads_its_record_and_its_datasets(world: World) -> None:
    world.s3.put(ARCHIVE, "projects/streams/project.json", {"id": "streams", "title": "Streams"})
    for name in ("a", "b", "c"):
        world.publish(name, {"title": name.upper(), "archive:project": "streams"})
    world.publish("elsewhere", {"title": "E", "archive:project": "lakes"})

    status, body = world.call("GET", "/api/projects/streams")

    assert status == 200
    assert body["project"] == {"id": "streams", "title": "Streams"}
    assert [d["id"] for d in body["datasets"]] == ["a", "b", "c"]
    assert body["datasets"][0] == {"id": "a", "title": "A", "access": "open", "currentVersion": 1}
    assert world.dynamodb.queries[-1]["IndexName"] == "GSI1"


def _download(world: World, dataset: str, path: str, claims: Any = CLAIMS) -> tuple[int, Any]:
    return world.call(
        "GET", f"/api/datasets/{dataset}/versions/1/download", {"path": [path]}, claims=claims
    )


def test_download_of_an_open_file_answers_its_data_url(world: World) -> None:
    world.publish("ds", _sample())

    status, body = _download(world, "ds", "data/logger.csv")

    assert status == 200
    assert body == {"url": f"https://{DOMAIN}/data/ds/1/data/logger.csv"}
    assert world.s3.presigned == []
    assert world.dynamodb.tables[COUNTS] == {}


def test_download_of_a_restricted_file_signs_it_for_five_minutes_and_counts_it(
    world: World,
) -> None:
    world.publish("ds", _sample(**{"archive:access": "restricted"}))

    status, body = _download(world, "ds", "data/sites/sites.dbf")

    assert status == 200
    assert world.s3.presigned == [
        {
            "operation": "get_object",
            "Params": {"Bucket": ARCHIVE, "Key": "restricted/ds/1/data/sites/sites.dbf"},
            "ExpiresIn": 300,
        }
    ]
    assert body == {
        "url": f"https://{ARCHIVE}.s3.example/restricted/ds/1/data/sites/sites.dbf?signed"
    }
    [count] = world.dynamodb.tables[COUNTS].values()
    assert count["datasetId"] == {"S": "ds"}
    assert len(count["month"]["S"]) == 7 and count["month"]["S"][4] == "-"
    assert count["restricted"] == {"N": "1"}


@pytest.mark.parametrize(
    ("access", "path", "claims", "expected"),
    [
        ("restricted", "data/logger.csv", None, 401),
        ("restricted", "data/../../open/other/1/x.csv", CLAIMS, 404),
        ("restricted", "data/nope.csv", CLAIMS, 404),
        ("by-request", "data/logger.csv", CLAIMS, 403),
        ("description-only", "data/logger.csv", CLAIMS, 404),
    ],
)
def test_download_refusals(
    world: World, access: str, path: str, claims: dict[str, str] | None, expected: int
) -> None:
    world.publish("ds", _sample(**{"archive:access": access}))

    status, _ = _download(world, "ds", path, claims)

    assert status == expected
    assert world.s3.presigned == []
    assert world.dynamodb.tables[COUNTS] == {}


def test_download_of_a_missing_dataset_or_version_answers_404(world: World) -> None:
    world.publish("ds", _sample(**{"archive:access": "restricted"}))

    assert _download(world, "nope", "data/logger.csv")[0] == 404
    status, _ = world.call(
        "GET", "/api/datasets/ds/versions/2/download", {"path": ["data/logger.csv"]}, claims=CLAIMS
    )
    assert status == 404


def test_usage_answers_are_stored(world: World) -> None:
    world.publish("ds", {"title": "T"})

    status, body = world.call(
        "POST",
        "/api/datasets/ds/usage",
        body={"organisation": "university", "purpose": "teaching", "note": "Class"},
    )

    assert status == 204 and body is None
    [entry] = world.dynamodb.tables[USAGE].values()
    month, _, uid = entry["entry"]["S"].partition("#")
    assert len(month) == 7 and len(uid) == 36
    assert entry["datasetId"] == {"S": "ds"}
    assert entry["organisation"] == {"S": "university"}
    assert entry["purpose"] == {"S": "teaching"}
    assert entry["note"] == {"S": "Class"}
    assert entry["at"]["S"].startswith(month)


def test_usage_with_no_answers_is_stored_bare(world: World) -> None:
    world.publish("ds", {"title": "T"})

    status, _ = world.call("POST", "/api/datasets/ds/usage", body={})

    assert status == 204
    [entry] = world.dynamodb.tables[USAGE].values()
    assert set(entry) == {"datasetId", "entry", "at"}


def test_usage_for_an_unknown_dataset_or_bad_answer_is_refused(world: World) -> None:
    world.publish("ds", {"title": "T"})

    unknown, _ = world.call("POST", "/api/datasets/nope/usage", body={})
    bad, _ = world.call("POST", "/api/datasets/ds/usage", body={"email": "a@example.org"})

    assert unknown == 404
    assert bad == 422
    assert world.dynamodb.tables[USAGE] == {}


def test_admin_usage_needs_the_admin_group(world: World) -> None:
    world.publish("ds", {"title": "T"})
    for n in range(3):
        world.dynamodb.load(
            USAGE,
            [
                {
                    "datasetId": {"S": "ds"},
                    "entry": {"S": f"2026-1{n}#id-{n}"},
                    "at": {"S": f"2026-1{n}-01T00:00:00Z"},
                    "purpose": {"S": "research"},
                }
            ],
        )

    signed_out, _ = world.call("GET", "/api/admin/usage", {"dataset": ["ds"]})
    not_admin, _ = world.call("GET", "/api/admin/usage", {"dataset": ["ds"]}, claims=CLAIMS)
    status, body = world.call("GET", "/api/admin/usage", {"dataset": ["ds"]}, claims=ADMIN)

    assert signed_out == 401
    assert not_admin == 403
    assert status == 200
    assert [e["entry"] for e in body["entries"]] == ["2026-12#id-2", "2026-11#id-1", "2026-10#id-0"]
    assert body["entries"][0] == {
        "datasetId": "ds",
        "entry": "2026-12#id-2",
        "at": "2026-12-01T00:00:00Z",
        "purpose": "research",
    }


def test_openapi_lists_every_route(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"

    api.main([str(out)])

    spec = json.loads(out.read_text())
    assert set(spec["paths"]) == {
        "/api/search",
        "/api/datasets/{id}",
        "/api/datasets/{id}/versions",
        "/api/datasets/{id}/versions/{version}",
        "/api/datasets/{id}/versions/{version}/download",
        "/api/datasets/{id}/usage",
        "/api/projects/{id}",
        "/api/admin/usage",
    }
    assert out.read_text() == json.dumps(spec, indent=2, sort_keys=True) + "\n"
