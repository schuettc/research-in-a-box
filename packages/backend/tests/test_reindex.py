import io
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from aws_durable_execution_sdk_python import DurableContext
from aws_durable_execution_sdk_python.waits import WaitForConditionConfig
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client
from mypy_boto3_sns import SNSClient

from archive_backend import reindex
from archive_backend.reindex import (
    Clients,
    catalog_items,
    dataset_item,
    manifest_keys,
    to_lines,
)

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package" / "datapackage.json"
ARCHIVE = "archive"
DERIVED = "derived"
TABLE_A = "catalog-a"
TABLE_B = "catalog-b"
PARAMETER = "/research-archive/test/catalog-active"
TOPIC = "arn:aws:sns:us-east-1:1:alerts"
CONFIG_PARAMETER = "/research-archive/test/archive-config"
DOMAIN = "d111.cloudfront.net"
EMBEDDINGS_ON = json.dumps(
    {"publisher": "P", "infrastructure": {"alertEmail": "a@b.c", "modules": {"embeddings": {}}}}
)


def _manifest(dataset_id: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": dataset_id,
        "title": f"Title of {dataset_id}",
        "resources": [{"name": "data", "path": "data/a.csv", "format": "csv", "bytes": 8}],
        **extra,
    }


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.metadata: dict[tuple[str, str], dict[str, str]] = {}
        self.puts: list[str] = []

    def put(self, key: str, manifest: dict[str, Any]) -> None:
        self.objects[(ARCHIVE, key)] = json.dumps(manifest).encode()

    def get_paginator(self, name: str) -> "FakeS3":
        assert name == "list_objects_v2"
        return self

    def paginate(self, *, Bucket: str, Prefix: str) -> Iterator[dict[str, Any]]:
        keys = sorted(k for b, k in self.objects if b == Bucket and k.startswith(Prefix))
        for start in range(0, len(keys), 2):
            yield {"Contents": [{"Key": k} for k in keys[start : start + 2]]}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {"Metadata": self.metadata.get((Bucket, Key), {})}

    def put_object(
        self, *, Bucket: str, Key: str, Body: Any, Metadata: dict[str, str] | None = None, **_: Any
    ) -> dict[str, Any]:
        body = Body.read() if hasattr(Body, "read") else Body
        self.objects[(Bucket, Key)] = body.encode() if isinstance(body, str) else body
        self.metadata[(Bucket, Key)] = Metadata or {}
        self.puts.append(Key)
        return {}


class FakeDynamoDB:
    """Tables of items keyed by (PK, SK); a bulk load copies the written lines into the target."""

    def __init__(self, s3: FakeS3, events: list[str], outcome: str = "COMPLETED") -> None:
        self.s3 = s3
        self.events = events
        self.outcome = outcome
        self.tables: dict[str, dict[tuple[str, str], dict[str, Any]]] = {TABLE_A: {}, TABLE_B: {}}
        self.loads: list[dict[str, Any]] = []
        self.unprocessed_once = True
        self.describes = 0

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        items = sorted(self.tables[kwargs["TableName"]].items())
        keys_only = "ProjectionExpression" in kwargs
        if keys_only:
            assert kwargs["ProjectionExpression"] == "#pk, #sk"
        start = 0
        if "ExclusiveStartKey" in kwargs:
            last = kwargs["ExclusiveStartKey"]
            after = (last["PK"]["S"], last["SK"]["S"])
            start = sum(1 for k, _ in items if k <= after)
        page = items[start : start + 2]
        result: dict[str, Any] = {
            "Items": [
                {"PK": item["PK"], "SK": item["SK"]} if keys_only else item for _, item in page
            ]
        }
        if start + 2 < len(items):
            result["LastEvaluatedKey"] = {"PK": page[-1][1]["PK"], "SK": page[-1][1]["SK"]}
        return result

    def batch_write_item(self, *, RequestItems: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        self.events.append("delete")
        unprocessed: dict[str, list[dict[str, Any]]] = {}
        for table, requests in RequestItems.items():
            assert len(requests) <= 25
            for i, request in enumerate(requests):
                if self.unprocessed_once and i == 0:
                    self.unprocessed_once = False
                    unprocessed.setdefault(table, []).append(request)
                    continue
                key = request["DeleteRequest"]["Key"]
                del self.tables[table][(key["PK"]["S"], key["SK"]["S"])]
        return {"UnprocessedItems": unprocessed}

    def start_bulk_put_items(self, **kwargs: Any) -> dict[str, Any]:
        self.events.append("load")
        self.loads.append(kwargs)
        source = kwargs["InputS3Configuration"]
        for (bucket, key), body in sorted(self.s3.objects.items()):
            if bucket == source["S3Bucket"] and key.startswith(source["S3KeyPrefix"]):
                for line in body.decode().splitlines():
                    item = json.loads(line)["Item"]
                    self.tables[kwargs["TableName"]][(item["PK"]["S"], item["SK"]["S"])] = item
        return {
            "BulkOperationDescription": {
                "BulkOperationArn": "arn:bulk/1",
                "BulkOperationStatus": "IN_PROGRESS",
            }
        }

    def describe_bulk_operation(self, *, BulkOperationArn: str) -> dict[str, Any]:
        assert BulkOperationArn == "arn:bulk/1"
        self.describes += 1
        status = "IN_PROGRESS" if self.describes == 1 else self.outcome
        return {
            "BulkOperationDescription": {
                "BulkOperationStatus": status,
                "ProcessedItemCount": 3,
                "FailedItemCount": 0 if status == "COMPLETED" else 1,
            }
        }


def test_fake_bulk_responses_match_botocore_shapes() -> None:
    # The live deploy found the start response wraps the ARN; keep the fake honest.
    import boto3

    model = boto3.client("dynamodb", region_name="us-east-1").meta.service_model
    fake = FakeDynamoDB(FakeS3(), [], outcome="COMPLETED")
    fake.tables.setdefault("t", {})
    started = fake.start_bulk_put_items(
        TableName="t",
        InputS3Configuration={"S3Bucket": "b", "S3KeyPrefix": "p/", "InputFormat": "DYNAMODB_JSON"},
        OutputS3Configuration={"S3Bucket": "b", "S3KeyPrefix": "r/", "OutputType": ["ERROR"]},
    )
    described = fake.describe_bulk_operation(BulkOperationArn="arn:bulk/1")
    for operation, response in (
        ("StartBulkPutItems", started),
        ("DescribeBulkOperation", described),
    ):
        shape = model.operation_model(operation).output_shape
        assert set(response) <= set(shape.members), operation
        inner = shape.members["BulkOperationDescription"]
        assert set(response["BulkOperationDescription"]) <= set(inner.members), operation


class FakeSSM:
    def __init__(self, value: str) -> None:
        self.value = value
        self.config = json.dumps({"publisher": "P"})
        self.config_reads = 0

    def get_parameter(self, *, Name: str) -> dict[str, Any]:
        if Name == CONFIG_PARAMETER:
            self.config_reads += 1
            return {"Parameter": {"Value": self.config}}
        assert Name == PARAMETER
        return {"Parameter": {"Value": self.value}}

    def put_parameter(self, *, Name: str, Value: str, Overwrite: bool, **_: Any) -> dict[str, Any]:
        assert Name == PARAMETER and Overwrite
        self.value = Value
        return {}


class FakeSNS:
    def __init__(self) -> None:
        self.published: list[dict[str, str]] = []

    def publish(self, **kwargs: str) -> dict[str, str]:
        self.published.append(kwargs)
        return {"MessageId": "m"}


class FakeBedrock:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def invoke_model(self, **kwargs: Any) -> dict[str, Any]:
        body = json.loads(kwargs["body"])
        self.texts.append(body["inputText"])
        answer = {"embedding": [0.5] * body["dimensions"]}
        return {"body": io.BytesIO(json.dumps(answer).encode())}


class FakeContext:
    """Runs each step, recording its result; with `replay` on it hands the recorded results back
    in order without running them, as a durable replay does."""

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.waits: list[int] = []
        self.recorded: list[Any] = []
        self.replay = False
        self._at = 0

    def _checkpoint(self, run: Callable[[], Any]) -> Any:
        if self.replay:
            self._at += 1
            return self.recorded[self._at - 1]
        result = run()
        self.recorded.append(result)
        return result

    def step(self, func: Callable[[Any], Any], name: str | None = None) -> Any:
        self.events.append(f"step:{name}")
        return self._checkpoint(lambda: func(None))

    def wait_for_condition(
        self,
        check: Callable[[Any, Any], Any],
        config: WaitForConditionConfig[Any],
        name: str | None = None,
    ) -> Any:
        self.events.append(f"step:{name}")

        def poll() -> Any:
            state = config.initial_state
            attempt = 0
            while True:
                attempt += 1
                state = check(state, None)
                decision = config.wait_strategy(state, attempt)
                if not decision.should_continue:
                    return state
                self.waits.append(decision.delay_seconds)

        return self._checkpoint(poll)


class World:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, active: str, outcome: str) -> None:
        self.events: list[str] = []
        self.s3 = FakeS3()
        self.dynamodb = FakeDynamoDB(self.s3, self.events, outcome)
        self.ssm = FakeSSM(active)
        self.sns = FakeSNS()
        self.bedrock = FakeBedrock()
        self.context = FakeContext(self.events)
        clients = Clients(
            s3=cast(S3Client, self.s3),
            dynamodb=cast(reindex.DynamoDB, self.dynamodb),
            ssm=cast(reindex.SSM, self.ssm),
            sns=cast(SNSClient, self.sns),
            bedrock=self.bedrock,
        )
        monkeypatch.setattr(reindex, "clients", lambda: clients)
        for name, value in {
            "ARCHIVE_BUCKET": ARCHIVE,
            "DERIVED_BUCKET": DERIVED,
            "CATALOG_TABLE_A": TABLE_A,
            "CATALOG_TABLE_B": TABLE_B,
            "ACTIVE_CATALOG_PARAMETER": PARAMETER,
            "ALERT_TOPIC_ARN": TOPIC,
            "ARCHIVE_CONFIG_PARAMETER": CONFIG_PARAMETER,
            "SITE_DOMAIN": DOMAIN,
        }.items():
            monkeypatch.setenv(name, value)

    def run(self) -> dict[str, Any]:
        return reindex.run({}, cast(DurableContext, self.context))


def _world(monkeypatch: pytest.MonkeyPatch, active: str = "A", outcome: str = "COMPLETED") -> World:
    return World(monkeypatch, active, outcome)


def test_catalog_items_for_the_sample_package() -> None:
    text = SAMPLE.read_text()
    items = catalog_items("open", "stream-temperature-sample", 1, text)

    version = [i for i in items if i["SK"] == {"S": "V#000001"}]
    assert version == [
        {
            "PK": {"S": "DATASET#stream-temperature-sample"},
            "SK": {"S": "V#000001"},
            "version": {"N": "1"},
            "prefix": {"S": "open"},
            "manifest": {"S": text},
        }
    ]
    files = {i["path"]["S"]: i for i in items if i["SK"]["S"].startswith("V#000001#FILE#")}
    manifest = json.loads(text)
    expected = {r["path"] for r in manifest["resources"]} | {
        f["path"] for r in manifest["resources"] for f in r["archive:files"] or []
    }
    zips = {"_zips/package.zip", "_zips/sites.zip", "_zips/depth.zip"}
    assert set(files) == expected | zips
    assert len(items) == 1 + len(expected) + len(zips)
    assert files["_zips/sites.zip"]["name"] == {"S": "sites"}
    assert files["_zips/sites.zip"]["format"] == {"S": "zip"}
    assert files["_zips/package.zip"]["name"] == {"S": "package"}
    for path, item in files.items():
        assert item["PK"] == {"S": "DATASET#stream-temperature-sample"}
        assert item["SK"] == {"S": f"V#000001#FILE#{path}"}
    assert files["data/logger.csv"] == {
        "PK": {"S": "DATASET#stream-temperature-sample"},
        "SK": {"S": "V#000001#FILE#data/logger.csv"},
        "path": {"S": "data/logger.csv"},
        "name": {"S": "logger"},
        "format": {"S": "csv"},
        "bytes": {"N": "3400"},
        "hash": {"S": "sha256:1b8a6b3736dfbb165673581395b27d1a4e29ec3d90de3acb9a3cc98a72eeb341"},
    }
    assert files["data/sites/sites.dbf"]["name"] == {"S": "sites"}
    assert files["data/sites/sites.dbf"]["format"] == {"S": "shp"}
    assert files["data/sites/sites.dbf"]["bytes"] == {"N": "244"}
    assert files["data/sites/sites.dbf"]["hash"]["S"].startswith("sha256:3b3459")
    linked = files["https://example.org/stream-temperature/discharge.csv"]
    assert "bytes" not in linked and "hash" not in linked


def test_dataset_item_takes_the_highest_version_and_its_prefix() -> None:
    item = dataset_item(
        "ds",
        [
            ("restricted", 2, _manifest("ds", title="Second", **{"archive:access": "restricted"})),
            ("open", 1, _manifest("ds", title="First")),
        ],
    )

    assert item == {
        "PK": {"S": "DATASET#ds"},
        "SK": {"S": "META"},
        "id": {"S": "ds"},
        "title": {"S": "Second"},
        "access": {"S": "restricted"},
        "currentVersion": {"N": "2"},
        "prefix": {"S": "restricted"},
    }


def test_dataset_item_has_gsi1_only_with_a_project() -> None:
    plain = dataset_item("ds", [("open", 1, _manifest("ds", **{"archive:project": None}))])
    with_project = dataset_item(
        "ds", [("open", 1, _manifest("ds", **{"archive:project": "lakes"}))]
    )

    assert not {"project", "GSI1PK", "GSI1SK"} & set(plain)
    assert plain["access"] == {"S": "open"}
    assert with_project["project"] == {"S": "lakes"}
    assert with_project["GSI1PK"] == {"S": "PROJECT#lakes"}
    assert with_project["GSI1SK"] == {"S": "DATASET#ds"}


def test_dataset_item_keys_on_the_folder_id_not_the_manifest_id() -> None:
    # A package copied to a new folder can keep its old manifest id; its dataset item must
    # still sit beside its version and file items, which key on the folder.
    item = dataset_item(
        "second-sample",
        [("open", 1, _manifest("stream-temperature-sample", **{"archive:project": "lakes"}))],
    )

    assert item["PK"] == {"S": "DATASET#second-sample"}
    assert item["id"] == {"S": "second-sample"}
    assert item["GSI1SK"] == {"S": "DATASET#second-sample"}


def test_dataset_item_works_without_a_manifest_id() -> None:
    manifest = _manifest("ds")
    del manifest["id"]

    assert dataset_item("ds", [("open", 1, manifest)])["id"] == {"S": "ds"}


def test_to_lines_is_one_item_per_line() -> None:
    items = catalog_items("open", "ds", 3, json.dumps(_manifest("ds")))
    text = to_lines(items)

    assert text.endswith("\n")
    lines = text.splitlines()
    assert len(lines) == len(items)
    assert [json.loads(line) for line in lines] == [{"Item": item} for item in items]


def test_manifest_keys_skips_nested_and_other_prefixes() -> None:
    s3 = FakeS3()
    for key in [
        "restricted/b/2/datapackage.json",
        "open/a/1/datapackage.json",
        "open/a/1/docs/datapackage.json",
        "open/a/1/data/a.csv",
        "staging/a/1/datapackage.json",
    ]:
        s3.put(key, {})

    assert manifest_keys(cast(S3Client, s3), ARCHIVE) == [
        "open/a/1/datapackage.json",
        "restricted/b/2/datapackage.json",
    ]


def _publish_two(world: World) -> None:
    world.s3.put("open/ds-1/1/datapackage.json", _manifest("ds-1"))
    world.s3.put("restricted/ds-1/2/datapackage.json", _manifest("ds-1"))
    world.s3.put("open/ds-2/1/datapackage.json", _manifest("ds-2"))


def test_reindex_loads_the_inactive_table_and_flips_on_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world(monkeypatch, active="A")
    _publish_two(world)

    result = world.run()

    run = result["run"]
    assert result == {
        "run": run,
        "target": "B",
        "status": "COMPLETED",
        "items": 11,
        "flipped": True,
        "catalog": 2,
        "pages": 2,
    }
    assert len(run) == 16 and run[8] == "T" and run.endswith("Z")
    assert world.ssm.value == "B"
    assert world.dynamodb.tables[TABLE_A] == {}
    assert len(world.dynamodb.tables[TABLE_B]) == 11
    assert ("DATASET#ds-1", "META") in world.dynamodb.tables[TABLE_B]
    assert world.dynamodb.loads == [
        {
            "TableName": TABLE_B,
            "InputS3Configuration": {
                "S3Bucket": DERIVED,
                "S3KeyPrefix": f"reindex/{run}/data/",
                "InputFormat": "DYNAMODB_JSON",
            },
            "OutputS3Configuration": {
                "S3Bucket": DERIVED,
                "S3KeyPrefix": f"reindex/{run}/report/",
                "OutputType": ["ERROR"],
            },
            "PerformanceTier": "STANDARD",
            "ClientToken": run,
        }
    ]
    assert (DERIVED, f"reindex/{run}/data/part-00000.json") in world.s3.objects
    assert world.context.waits == [30]
    assert world.sns.published == []
    steps = [e for e in world.events if e.startswith("step:")]
    assert steps == [
        "step:start",
        "step:empty",
        "step:list",
        "step:write-0",
        "step:load",
        "step:wait-load",
        "step:flip",
        "step:catalog",
        "step:pages",
        "step:versions",
        "step:zips-0",
        "step:zips-1",
    ]
    catalog = json.loads(world.s3.objects[(DERIVED, "site/catalog.json")])
    assert [row["id"] for row in catalog] == ["ds-1", "ds-2"]


def test_reindex_embeds_each_dataset_item_before_writing_when_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world(monkeypatch, active="A")
    world.ssm.config = EMBEDDINGS_ON
    _publish_two(world)

    world.run()

    assert world.ssm.config_reads == 1

    assert world.bedrock.texts == ["Title of ds-1", "Title of ds-2"]
    table = world.dynamodb.tables[TABLE_B]
    for dataset_id in ("ds-1", "ds-2"):
        meta = table[(f"DATASET#{dataset_id}", "META")]
        assert len(meta["embedding"]["L"]) == 1024
        assert meta["id"] == {"S": dataset_id}
    assert all("embedding" not in item for key, item in table.items() if key[1] != "META")


def test_reindex_never_embeds_when_off(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _world(monkeypatch, active="A")
    _publish_two(world)

    world.run()

    assert world.bedrock.texts == []
    assert all("embedding" not in item for item in world.dynamodb.tables[TABLE_B].values())


def test_reindex_loads_table_a_when_b_is_active(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _world(monkeypatch, active="B")
    _publish_two(world)

    assert world.run()["target"] == "A"
    assert world.ssm.value == "A"
    assert world.dynamodb.loads[0]["TableName"] == TABLE_A


def test_reindex_empties_the_target_before_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _world(monkeypatch, active="A")
    _publish_two(world)
    stale = {
        (f"DATASET#old-{n}", "META"): {"PK": {"S": f"DATASET#old-{n}"}, "SK": {"S": "META"}}
        for n in range(30)
    }
    world.dynamodb.tables[TABLE_B] = dict(stale)
    world.dynamodb.tables[TABLE_A] = {
        ("DATASET#live", "META"): {"PK": {"S": "DATASET#live"}, "SK": {"S": "META"}}
    }

    world.run()

    assert not set(stale) & set(world.dynamodb.tables[TABLE_B])
    assert len(world.dynamodb.tables[TABLE_B]) == 11
    assert ("DATASET#live", "META") in world.dynamodb.tables[TABLE_A]
    assert world.events.index("delete") < world.events.index("load")
    assert world.events.count("step:empty") == 15
    assert world.events.index("step:empty") < world.events.index("step:load")


@pytest.mark.parametrize("outcome", ["COMPLETED_WITH_ERRORS", "FAILED"])
def test_reindex_does_not_flip_and_alerts_on_completed_with_errors(
    monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    world = _world(monkeypatch, active="A", outcome=outcome)
    _publish_two(world)

    result = world.run()

    run = result["run"]
    assert result["status"] == outcome
    assert result["flipped"] is False
    assert world.ssm.value == "A"
    assert "step:flip" not in world.events
    assert "step:catalog" not in world.events
    assert (DERIVED, "site/catalog.json") not in world.s3.objects
    assert world.events[-1] == "step:alert"
    assert len(world.sns.published) == 1
    alert = world.sns.published[0]
    assert alert["TopicArn"] == TOPIC
    assert f"Reindex {run} on B ended {outcome}" in alert["Message"]
    assert f"s3://{DERIVED}/reindex/{run}/report/" in alert["Message"]


def test_reindex_with_no_packages_flips_to_an_empty_table(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _world(monkeypatch, active="A")
    world.dynamodb.tables[TABLE_B] = {
        ("DATASET#old", "META"): {"PK": {"S": "DATASET#old"}, "SK": {"S": "META"}}
    }

    result = world.run()

    assert result["status"] == "COMPLETED"
    assert result["items"] == 0
    assert result["flipped"] is True
    assert world.ssm.value == "B"
    assert world.dynamodb.tables[TABLE_B] == {}
    assert world.dynamodb.loads == []
    assert "step:load" not in world.events


def test_write_batches_never_split_a_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reindex, "BATCH", 2)
    world = _world(monkeypatch, active="A")
    _publish_two(world)

    result = world.run()

    assert result["items"] == 11
    assert "step:write-0" in world.events and "step:write-1" in world.events
    run = result["run"]
    first = world.s3.objects[(DERIVED, f"reindex/{run}/data/part-00000.json")].decode()
    pks = {json.loads(line)["Item"]["PK"]["S"] for line in first.splitlines()}
    assert pks == {"DATASET#ds-1"}


def test_reindex_imports_without_the_type_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    import importlib
    import sys

    monkeypatch.setitem(sys.modules, "mypy_boto3_s3", None)
    monkeypatch.setitem(sys.modules, "mypy_boto3_sns", None)
    monkeypatch.delitem(sys.modules, "archive_backend.reindex", raising=False)

    module = importlib.import_module("archive_backend.reindex")

    assert callable(module.handler)


def test_a_failed_catalog_file_alerts_and_keeps_the_flip(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _world(monkeypatch, active="A")
    _publish_two(world)

    def broken(*_: Any, **__: Any) -> int:
        raise RuntimeError("no write")

    monkeypatch.setattr(reindex, "write_catalog_file", broken)

    result = world.run()

    assert result["flipped"] is True
    assert result["catalog"] is None
    assert world.ssm.value == "B"
    assert world.events[-6:-3] == ["step:catalog", "step:alert", "step:pages"]
    [alert] = world.sns.published
    assert f"Reindex {result['run']} flipped to B" in alert["Message"]
    assert "no write" in alert["Message"]


def test_reindex_writes_each_datasets_page_from_its_current_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world(monkeypatch, active="A")
    _publish_two(world)

    result = world.run()

    assert result["pages"] == 2
    pages = sorted(k for k in world.s3.puts if k.startswith("site/datasets/"))
    assert pages == ["site/datasets/ds-1/index.html", "site/datasets/ds-2/index.html"]
    first = world.s3.objects[(DERIVED, "site/datasets/ds-1/index.html")].decode()
    assert f"https://{DOMAIN}/datasets/ds-1/v2" in first
    assert f"https://{DOMAIN}/data/ds-1/2/data/a.csv" in first
    assert "/data/ds-1/1/" not in first
    second = world.s3.objects[(DERIVED, "site/datasets/ds-2/index.html")].decode()
    assert f"https://{DOMAIN}/data/ds-2/1/data/a.csv" in second
    assert '<div id="app">' in second
    assert world.events.index("step:catalog") < world.events.index("step:pages")


def test_a_replayed_reindex_does_not_write_the_pages_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = _world(monkeypatch, active="A")
    _publish_two(world)
    first = world.run()

    world.context.replay = True
    again = world.run()

    assert again == first
    pages = [k for k in world.s3.puts if k.startswith("site/datasets/")]
    assert len(pages) == 2


def _publish_sample(world: World, root: str) -> None:
    for path in sorted(SAMPLE.parent.rglob("*")):
        if path.is_file() and "_build" not in path.parts:
            world.s3.objects[(ARCHIVE, root + str(path.relative_to(SAMPLE.parent)))] = (
                path.read_bytes()
            )


def test_reindex_writes_every_versions_zips_once(monkeypatch: pytest.MonkeyPatch) -> None:
    world = _world(monkeypatch, active="A")
    _publish_sample(world, "open/stream/1/")
    _publish_sample(world, "restricted/stream/2/")

    world.run()

    zips = sorted(k for k in world.s3.puts if "/_zips/" in k)
    assert zips == [
        "open/stream/1/_zips/depth.zip",
        "open/stream/1/_zips/package.zip",
        "open/stream/1/_zips/sites.zip",
        "restricted/stream/2/_zips/depth.zip",
        "restricted/stream/2/_zips/package.zip",
        "restricted/stream/2/_zips/sites.zip",
    ]
    table = world.dynamodb.tables[TABLE_B]
    assert ("DATASET#stream", "V#000002#FILE#_zips/sites.zip") in table

    world.context = FakeContext(world.events)
    world.run()

    assert sorted(k for k in world.s3.puts if "/_zips/" in k) == zips
