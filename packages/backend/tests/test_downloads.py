import gzip
import io
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from botocore.exceptions import ClientError

from archive_backend import downloads

DERIVED = "derived"
COUNTS = "download-counts"
SETTINGS = "settings"
FIELDS = (
    "#Fields: date time x-edge-location sc-bytes c-ip cs-method cs(Host) cs-uri-stem sc-status "
    "cs(Referer) cs(User-Agent) cs-uri-query"
)


def _line(day: str, method: str, stem: str, status: int) -> str:
    return "\t".join(
        [day, "10:00:00", "IAD89-C1", "100", "192.0.2.1", method, "d1.cloudfront.net", stem]
        + [str(status), "-", "curl/8", "-"]
    )


def _log(day: str, lines: list[str]) -> bytes:
    text = "#Version: 1.0\n" + FIELDS + "\n" + "".join(line + "\n" for line in lines)
    return gzip.compress(text.encode())


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.reads: list[str] = []

    def get_paginator(self, name: str) -> "FakeS3":
        assert name == "list_objects_v2"
        return self

    def paginate(self, *, Bucket: str, Prefix: str) -> Iterator[dict[str, Any]]:
        assert Bucket == DERIVED
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        for start in range(0, len(keys), 2):
            yield {"Contents": [{"Key": k} for k in keys[start : start + 2]]}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.reads.append(Key)
        return {"Body": io.BytesIO(self.objects[Key])}


class FakeDynamoDB:
    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = {}
        self.days: dict[tuple[str, str], set[str]] = {}
        self.settings: dict[str, str] = {}
        self.events: list[str] = []
        self.fail_after: int | None = None

    def get_item(self, *, TableName: str, Key: dict[str, Any], **_: Any) -> dict[str, Any]:
        assert TableName == SETTINGS
        value = self.settings.get(Key["name"]["S"])
        return {"Item": {"name": Key["name"], "value": {"S": value}}} if value else {}

    def put_item(self, *, TableName: str, Item: dict[str, Any]) -> dict[str, Any]:
        assert TableName == SETTINGS
        self.events.append(f"mark:{Item['value']['S']}")
        self.settings[Item["name"]["S"]] = Item["value"]["S"]
        return {}

    def update_item(self, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["TableName"] == COUNTS
        assert kwargs["UpdateExpression"] == "ADD #n :count, countedDays :days"
        assert kwargs["ConditionExpression"] == (
            "attribute_not_exists(countedDays) OR NOT contains(countedDays, :day)"
        )
        assert kwargs["ExpressionAttributeNames"] == {"#n": "open"}
        values = kwargs["ExpressionAttributeValues"]
        key = (kwargs["Key"]["datasetId"]["S"], kwargs["Key"]["month"]["S"])
        day = values[":day"]["S"]
        assert values[":days"] == {"SS": [day]}
        if day in self.days.get(key, set()):
            raise ClientError(
                {"Error": {"Code": "ConditionalCheckFailedException", "Message": "x"}},
                "UpdateItem",
            )
        added = int(values[":count"]["N"])
        self.events.append(f"add:{key[0]}:{key[1]}:{added}")
        self.counts[key] = self.counts.get(key, 0) + added
        self.days.setdefault(key, set()).add(day)
        if self.fail_after is not None:
            self.fail_after -= 1
            if self.fail_after == 0:
                raise RuntimeError("crashed after an increment")
        return {}


class World:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, today: date) -> None:
        self.s3 = FakeS3()
        self.dynamodb = FakeDynamoDB()
        self.today = today
        clients = downloads.Clients(s3=self.s3, dynamodb=self.dynamodb)  # type: ignore[arg-type]
        monkeypatch.setattr(downloads, "clients", lambda: clients)
        monkeypatch.setattr(downloads, "_today", lambda: self.today)
        monkeypatch.setenv("DERIVED_BUCKET", DERIVED)
        monkeypatch.setenv("DOWNLOAD_COUNTS_TABLE", COUNTS)
        monkeypatch.setenv("SETTINGS_TABLE", SETTINGS)

    def log(self, day: str, hour: int, lines: list[str]) -> None:
        self.s3.objects[f"logs/E2ABC.{day}-{hour:02d}.a1b2c3.gz"] = _log(day, lines)

    def run(self, event: dict[str, Any] | None = None) -> dict[str, Any]:
        return downloads.handler(event or {}, None)


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    return World(monkeypatch, today=date(2026, 11, 13))


def test_only_a_200_get_under_data_counts(world: World) -> None:
    day = "2026-11-11"
    world.log(
        day,
        3,
        [
            _line(day, "GET", "/data/ds-1/1/data/logger.csv", 200),
            _line(day, "GET", "/data/ds-1/1/data/logger.csv", 206),
            _line(day, "HEAD", "/data/ds-1/1/data/logger.csv", 200),
            _line(day, "GET", "/data/ds-1/1/data/missing.csv", 404),
            _line(day, "GET", "/catalog.json", 200),
        ],
    )

    result = world.run()

    assert result == {"days": [day], "counted": 1}
    assert world.dynamodb.counts == {("ds-1", "2026-11"): 1}
    assert world.dynamodb.settings == {"downloads-rolled-up-through": day}


def test_a_second_run_the_same_day_counts_nothing(world: World) -> None:
    day = "2026-11-11"
    world.log(day, 3, [_line(day, "GET", "/data/ds-1/1/a.csv", 200)])

    world.run()
    second = world.run()

    assert second == {"days": [], "counted": 0}
    assert world.dynamodb.counts == {("ds-1", "2026-11"): 1}


def test_missed_days_are_each_counted_once(world: World) -> None:
    world.dynamodb.settings["downloads-rolled-up-through"] = "2026-10-30"
    world.today = date(2026, 11, 3)
    world.log("2026-10-31", 23, [_line("2026-10-31", "GET", "/data/ds-1/1/a.csv", 200)])
    world.log("2026-11-01", 0, [_line("2026-11-01", "GET", "/data/ds-1/1/a.csv", 200)])
    world.log(
        "2026-11-01",
        5,
        [
            _line("2026-11-01", "GET", "/data/ds-2/3/b.csv", 200),
            _line("2026-11-01", "GET", "/data/ds-1/2/c.csv", 200),
        ],
    )
    world.log("2026-11-02", 0, [_line("2026-11-02", "GET", "/data/ds-1/1/a.csv", 200)])

    result = world.run()
    world.run()

    assert result == {"days": ["2026-10-31", "2026-11-01"], "counted": 4}
    assert world.dynamodb.counts == {
        ("ds-1", "2026-10"): 1,
        ("ds-1", "2026-11"): 2,
        ("ds-2", "2026-11"): 1,
    }
    assert world.dynamodb.settings["downloads-rolled-up-through"] == "2026-11-01"
    assert world.dynamodb.events == [
        "add:ds-1:2026-10:1",
        "mark:2026-10-31",
        "add:ds-1:2026-11:2",
        "add:ds-2:2026-11:1",
        "mark:2026-11-01",
    ]


def test_through_in_the_event_replaces_two_days_ago(world: World) -> None:
    world.log("2026-11-13", 9, [_line("2026-11-13", "GET", "/data/ds-1/1/a.csv", 200)])

    result = world.run({"through": "2026-11-13"})

    assert result == {"days": ["2026-11-11", "2026-11-12", "2026-11-13"], "counted": 1}
    assert world.dynamodb.settings["downloads-rolled-up-through"] == "2026-11-13"


def test_a_day_with_no_logs_is_still_marked(world: World) -> None:
    result = world.run()

    assert result == {"days": ["2026-11-11"], "counted": 0}
    assert world.dynamodb.counts == {}
    assert world.dynamodb.settings["downloads-rolled-up-through"] == "2026-11-11"


def test_a_rerun_after_a_crash_mid_day_counts_each_dataset_once(world: World) -> None:
    day = "2026-11-11"
    world.log(
        day,
        3,
        [
            _line(day, "GET", "/data/ds-1/1/a.csv", 200),
            _line(day, "GET", "/data/ds-2/1/b.csv", 200),
            _line(day, "GET", "/data/ds-2/1/b.csv", 200),
        ],
    )
    world.dynamodb.fail_after = 1

    with pytest.raises(RuntimeError):
        world.run()
    assert "downloads-rolled-up-through" not in world.dynamodb.settings
    world.dynamodb.fail_after = None
    world.run()

    assert world.dynamodb.counts == {("ds-1", "2026-11"): 1, ("ds-2", "2026-11"): 2}
    assert world.dynamodb.settings["downloads-rolled-up-through"] == day
