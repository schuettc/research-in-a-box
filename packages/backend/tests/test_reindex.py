import io
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import pytest
from aws_durable_execution_sdk_python import DurableContext
from aws_durable_execution_sdk_python.waits import WaitForConditionConfig
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
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes | str, **_: Any) -> dict[str, Any]:
        self.objects[(Bucket, Key)] = Body.encode() if isinstance(Body, str) else Body
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
        assert kwargs["ProjectionExpression"] == "#pk, #sk"
        start = 0
        if "ExclusiveStartKey" in kwargs:
            last = kwargs["ExclusiveStartKey"]
            after = (last["PK"]["S"], last["SK"]["S"])
            start = sum(1 for k, _ in items if k <= after)
        page = items[start : start + 2]
        result: dict[str, Any] = {
            "Items": [{"PK": item["PK"], "SK": item["SK"]} for _, item in page]
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
        return {"BulkOperationArn": "arn:bulk/1"}

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


class FakeSSM:
    def __init__(self, value: str) -> None:
        self.value = value

    def get_parameter(self, *, Name: str) -> dict[str, Any]:
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


class FakeContext:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.waits: list[int] = []

    def step(self, func: Callable[[Any], Any], name: str | None = None) -> Any:
        self.events.append(f"step:{name}")
        return func(None)

    def wait_for_condition(
        self,
        check: Callable[[Any, Any], Any],
        config: WaitForConditionConfig[Any],
        name: str | None = None,
    ) -> Any:
        self.events.append(f"step:{name}")
        state = config.initial_state
        attempt = 0
        while True:
            attempt += 1
            state = check(state, None)
            decision = config.wait_strategy(state, attempt)
            if not decision.should_continue:
                return state
            self.waits.append(decision.delay_seconds)


class World:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, active: str, outcome: str) -> None:
        self.events: list[str] = []
        self.s3 = FakeS3()
        self.dynamodb = FakeDynamoDB(self.s3, self.events, outcome)
        self.ssm = FakeSSM(active)
        self.sns = FakeSNS()
        self.context = FakeContext(self.events)
        clients = Clients(
            s3=cast(S3Client, self.s3),
            dynamodb=cast(reindex.DynamoDB, self.dynamodb),
            ssm=cast(reindex.SSM, self.ssm),
            sns=cast(SNSClient, self.sns),
        )
        monkeypatch.setattr(reindex, "clients", lambda: clients)
        for name, value in {
            "ARCHIVE_BUCKET": ARCHIVE,
            "DERIVED_BUCKET": DERIVED,
            "CATALOG_TABLE_A": TABLE_A,
            "CATALOG_TABLE_B": TABLE_B,
            "ACTIVE_CATALOG_PARAMETER": PARAMETER,
            "ALERT_TOPIC_ARN": TOPIC,
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
    assert set(files) == expected
    assert len(items) == 1 + len(expected)
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
        [
            ("restricted", 2, _manifest("ds", title="Second", **{"archive:access": "restricted"})),
            ("open", 1, _manifest("ds", title="First")),
        ]
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
    plain = dataset_item([("open", 1, _manifest("ds", **{"archive:project": None}))])
    with_project = dataset_item([("open", 1, _manifest("ds", **{"archive:project": "lakes"}))])

    assert not {"project", "GSI1PK", "GSI1SK"} & set(plain)
    assert plain["access"] == {"S": "open"}
    assert with_project["project"] == {"S": "lakes"}
    assert with_project["GSI1PK"] == {"S": "PROJECT#lakes"}
    assert with_project["GSI1SK"] == {"S": "DATASET#ds"}


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
    assert result == {"run": run, "target": "B", "status": "COMPLETED", "items": 8, "flipped": True}
    assert len(run) == 16 and run[8] == "T" and run.endswith("Z")
    assert world.ssm.value == "B"
    assert world.dynamodb.tables[TABLE_A] == {}
    assert len(world.dynamodb.tables[TABLE_B]) == 8
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
    ]


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
    assert len(world.dynamodb.tables[TABLE_B]) == 8
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

    assert result["items"] == 8
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
