import hashlib
import io
import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from aws_durable_execution_sdk_python import DurableContext
from aws_durable_execution_sdk_python.config import WaitForCallbackConfig
from aws_durable_execution_sdk_python.exceptions import CallbackTimeoutError, StepError
from aws_durable_execution_sdk_python.waits import WaitForConditionConfig

from archive_backend import ingest, submissions
from archive_backend.ingest import Clients, Env

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"
SID = "sub-1"
STAGING = "staging"
CURATORS = "arn:aws:sns:us-east-1:1:curators"
ALERTS = "arn:aws:sns:us-east-1:1:alerts"
CONFIG = "/research-archive/test/archive-config"
DAY = 86400
ENV = Env(
    submissions_table="submissions",
    reviews_table="reviews",
    settings_table="settings",
    staging_bucket=STAGING,
    curator_topic_arn=CURATORS,
    alert_topic_arn=ALERTS,
    archive_config_parameter=CONFIG,
)


def _package(themes: list[str] | None = None, broken: bool = False) -> dict[str, bytes]:
    """The sample package's files; with themes, its manifest and checksum line rewritten."""
    files = {
        str(p.relative_to(SAMPLE)): p.read_bytes()
        for p in sorted(SAMPLE.rglob("*"))
        if p.is_file() and "_build" not in p.relative_to(SAMPLE).parts
    }
    if themes is not None:
        manifest = json.loads(files["datapackage.json"])
        manifest["archive:themes"] = themes
        text = json.dumps(manifest, indent=2).encode()
        old = hashlib.sha256(files["datapackage.json"]).hexdigest()
        files["datapackage.json"] = text
        files["checksums.sha256"] = (
            files["checksums.sha256"]
            .decode()
            .replace(old, hashlib.sha256(text).hexdigest())
            .encode()
        )
    if broken:
        files["data/logger.csv"] += b"2024-06-02T00:00:00,S1,9.0,0.20,ok,C,TL-100,3.5,30\n"
    return files


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.tags: dict[str, str] = {}
        self.pending: dict[str, str] = {}
        self.copies: list[tuple[str, str]] = []
        self.fail_copy = False

    def get_object_tagging(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        assert Bucket == STAGING
        assert Key in self.objects, Key
        tag = self.tags.get(Key)
        return {"TagSet": [{"Key": "GuardDutyMalwareScanStatus", "Value": tag}] if tag else []}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        assert Bucket == STAGING
        return {"Body": io.BytesIO(self.objects[Key])}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, **_: Any) -> dict[str, Any]:
        assert Bucket == STAGING
        self.objects[Key] = Body
        return {}

    def copy_object(
        self, *, Bucket: str, Key: str, CopySource: dict[str, str], **_: Any
    ) -> dict[str, Any]:
        if self.fail_copy:
            raise RuntimeError("copy refused")
        assert Bucket == STAGING and CopySource["Bucket"] == STAGING
        self.objects[Key] = self.objects[CopySource["Key"]]
        self.copies.append((CopySource["Key"], Key))
        return {}

    def get_paginator(self, name: str) -> "FakeS3":
        assert name == "list_objects_v2"
        return self

    def paginate(self, *, Bucket: str, Prefix: str) -> Iterator[dict[str, Any]]:
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        for start in range(0, len(keys), 3):
            yield {"Contents": [{"Key": k} for k in keys[start : start + 3]]}

    def delete_objects(self, *, Bucket: str, Delete: dict[str, Any]) -> dict[str, Any]:
        for entry in Delete["Objects"]:
            self.objects.pop(entry["Key"], None)
        return {}

    def keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))


class FakeSubmissions:
    """The Submissions table, understanding the `SET ... REMOVE ...` updates ingest writes."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, Any]] = {}

    def get_item(self, *, Key: dict[str, Any]) -> dict[str, Any]:
        item = self.items.get(Key["submissionId"])
        return {"Item": json.loads(json.dumps(item))} if item is not None else {}

    def update_item(self, *, Key: dict[str, Any], UpdateExpression: str, **kwargs: Any) -> Any:
        item = self.items[Key["submissionId"]]
        names = kwargs.get("ExpressionAttributeNames", {})
        values = kwargs.get("ExpressionAttributeValues", {})
        sets, _, removes = UpdateExpression.partition(" REMOVE ")
        if sets.startswith("REMOVE "):
            sets, removes = "", sets[len("REMOVE ") :]
        if sets:
            assert sets.startswith("SET ")
            for assignment in sets[4:].split(","):
                name, value = (part.strip() for part in assignment.split("="))
                item[names[name]] = values[value]
        for name in filter(None, (part.strip() for part in removes.split(","))):
            item.pop(names[name], None)
        return {}


class FakeReviews:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def put_item(self, *, Item: dict[str, Any], **_: Any) -> Any:
        self.events.append(Item)
        return {}


class FakeSettings:
    def __init__(self) -> None:
        self.policy: dict[str, Any] | None = None

    def get_item(self, *, Key: dict[str, Any]) -> dict[str, Any]:
        assert Key == {"name": "review-policy"}
        if self.policy is None:
            return {}
        return {"Item": {"name": "review-policy", "policy": json.dumps(self.policy)}}


class FakeSNS:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    def publish(self, **kwargs: Any) -> dict[str, str]:
        self.published.append(kwargs)
        return {"MessageId": "m"}

    def to(self, topic: str) -> list[dict[str, Any]]:
        return [p for p in self.published if p["TopicArn"] == topic]


class FakeSSM:
    def get_parameter(self, *, Name: str) -> dict[str, Any]:
        assert Name == CONFIG
        return {"Parameter": {"Value": json.dumps({"publisher": "Test", "profiles": ["core"]})}}


Script = list[Any]
"""Each callback wait's outcome in order: a payload, "timeout", or a callable returning one."""


class FakeContext:
    """Runs steps once, recording each operation's name and result for a replay."""

    def __init__(self, world: "World", script: Script) -> None:
        self.world = world
        self.script = list(script)
        self.log: list[tuple[str, str | None, Any]] = []
        self.timeouts: list[tuple[str | None, int]] = []
        self.polls: list[int] = []

    def step(self, func: Callable[[Any], Any], name: str | None = None) -> Any:
        try:
            result = func(None)
        except Exception as error:
            # The SDK raises StepError once a step's retries are spent.
            self.log.append(("step", name, StepError(str(error))))
            raise StepError(str(error)) from error
        self.log.append(("step", name, result))
        return result

    def wait_for_condition(
        self,
        check: Callable[[Any, Any], Any],
        config: WaitForConditionConfig[Any],
        name: str | None = None,
    ) -> Any:
        state = config.initial_state
        attempt = 0
        while True:
            attempt += 1
            state = check(state, None)
            decision = config.wait_strategy(state, attempt)
            if not decision.should_continue:
                self.log.append(("condition", name, state))
                return state
            self.polls.append(decision.delay_seconds)
            self.world.s3.tags.update(self.world.s3.pending)
            self.world.s3.pending = {}

    def wait_for_callback(
        self,
        submitter: Callable[[str, Any], None],
        name: str | None = None,
        config: WaitForCallbackConfig | None = None,
    ) -> Any:
        assert config is not None and config.timeout_seconds > 0
        self.timeouts.append((name, config.timeout_seconds))
        callback = f"cb-{len(self.timeouts)}"
        submitter(callback, None)
        assert self.world.item["callbackId"] == callback
        entry = self.script.pop(0)
        if callable(entry):
            entry = entry()
        if entry == "timeout":
            self.world.now += timedelta(seconds=config.timeout_seconds)
            self.log.append(("callback", name, "timeout"))
            raise CallbackTimeoutError("timed out")
        self.world.now += timedelta(hours=1)
        result = json.dumps(entry)
        self.log.append(("callback", name, result))
        return result


class ReplayContext:
    """Replays a finished run from its log: no step runs again, and the names must match."""

    def __init__(self, log: list[tuple[str, str | None, Any]]) -> None:
        self.log = list(log)

    def _next(self, kind: str, name: str | None) -> Any:
        logged_kind, logged_name, result = self.log.pop(0)
        assert (logged_kind, logged_name) == (kind, name)
        if isinstance(result, Exception):
            raise result
        return result

    def step(self, func: Callable[[Any], Any], name: str | None = None) -> Any:
        return self._next("step", name)

    def wait_for_condition(self, check: Any, config: Any, name: str | None = None) -> Any:
        return self._next("condition", name)

    def wait_for_callback(self, submitter: Any, name: str | None = None, config: Any = None) -> Any:
        result = self._next("callback", name)
        if result == "timeout":
            raise CallbackTimeoutError("timed out")
        return result


class World:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.s3 = FakeS3()
        self.sns = FakeSNS()
        self.submissions = FakeSubmissions()
        self.reviews = FakeReviews()
        self.settings = FakeSettings()
        self.now = datetime(2026, 11, 1, tzinfo=UTC)
        self.clients = Clients(
            s3=cast(ingest.S3, self.s3),
            sns=cast(ingest.SNS, self.sns),
            ssm=cast(ingest.SSM, FakeSSM()),
            submissions=cast(submissions.Table, self.submissions),
            reviews=cast(submissions.Table, self.reviews),
            settings=cast(submissions.Table, self.settings),
        )
        monkeypatch.setattr(ingest, "clients", lambda env: self.clients)
        monkeypatch.setattr(ingest, "_clock", lambda: self.now)
        for name, value in {
            "SUBMISSIONS_TABLE": ENV.submissions_table,
            "REVIEWS_TABLE": ENV.reviews_table,
            "SETTINGS_TABLE": ENV.settings_table,
            "STAGING_BUCKET": STAGING,
            "CURATOR_TOPIC_ARN": CURATORS,
            "ALERT_TOPIC_ARN": ALERTS,
            "ARCHIVE_CONFIG_PARAMETER": CONFIG,
        }.items():
            monkeypatch.setenv(name, value)
        self.submissions.items[SID] = {
            "submissionId": SID,
            "submitter": "alice",
            "status": "checking",
            "round": 1,
            "files": {},
            "newVersion": False,
            "approvals": [],
            "stale": False,
        }
        self.upload(1, _package())

    @property
    def item(self) -> dict[str, Any]:
        return self.submissions.items[SID]

    def upload(
        self,
        round: int,
        files: dict[str, bytes],
        scan: str = "NO_THREATS_FOUND",
        late: bool = False,
    ) -> None:
        """What the API and S3 hold after a round's upload, and GuardDuty's tags on it."""
        entries = []
        for path, body in files.items():
            key = f"incoming/{SID}/{round}/{path}"
            self.s3.objects[key] = body
            (self.s3.pending if late else self.s3.tags)[key] = scan
            entries.append(
                {"path": path, "size": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            )
        self.item["files"][str(round)] = entries

    def resubmit(self, round: int, files: dict[str, bytes]) -> Callable[[], dict[str, Any]]:
        def send() -> dict[str, Any]:
            self.upload(round, files)
            self.item.update(round=round, status="checking")
            return {"kind": "resubmit", "round": round}

        return send

    def run(self, script: Script) -> tuple[dict[str, Any], FakeContext]:
        context = FakeContext(self, script)
        result = ingest.run({"submissionId": SID}, cast(DurableContext, context))
        assert context.script == [], "every scripted callback was used"
        return result, context

    def types(self) -> list[str]:
        return [e["type"] for e in self.reviews.events]


def _decision(decision: str, by: str = "carol", note: str | None = None) -> dict[str, Any]:
    return {"kind": "decision", "decision": decision, "by": by, "note": note}


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    return World(monkeypatch)


REVIEWED = ["scanned", "checked", "held", "entered-review"]


def test_approve_publishes_after_the_scan_check_hold_and_one_review(world: World) -> None:
    world.s3.tags.clear()
    world.upload(1, _package(), late=True)

    result, context = world.run([_decision("approve")])

    assert result["status"] == "published"
    assert world.item["status"] == "published"
    assert world.types() == [*REVIEWED, "published"]
    assert context.polls == [30]
    report = json.loads(world.s3.objects[f"reports/{SID}/1.json"])
    assert report["quality"]["errors"] == 0
    assert world.item["reportKey"] == f"reports/{SID}/1.json"
    assert world.s3.keys(f"held/{SID}/") == sorted(
        f"held/{SID}/{e['path']}" for e in world.item["files"]["1"]
    )
    assert world.item["rule"] is None
    assert world.item["approvals"] == ["carol"]
    assert "callbackId" not in world.item
    checked = world.reviews.events[1]
    assert (checked["errors"], checked["blocked"], checked["actor"]) == (0, False, "pipeline")
    entered = world.reviews.events[3]
    assert (entered["rule"], entered["outcome"], entered["audience"]) == (None, "one", "all")
    [message] = world.sns.to(CURATORS)
    assert message["MessageAttributes"]["audience"] == {"DataType": "String", "StringValue": "all"}
    assert world.sns.to(ALERTS) == []


def test_reject_ends_rejected_and_deletes_the_held_copy(world: World) -> None:
    result, _ = world.run([_decision("reject", note="Out of scope")])

    assert result["status"] == "rejected"
    assert world.item["status"] == "rejected"
    assert world.types() == [*REVIEWED, "rejected"]
    rejected = world.reviews.events[-1]
    assert (rejected["actor"], rejected["note"]) == ("carol", "Out of scope")
    assert world.s3.keys(f"held/{SID}/") == []
    assert "callbackId" not in world.item


def test_request_changes_then_approve_publishes_round_two(world: World) -> None:
    def changes() -> dict[str, Any]:
        assert world.item["status"] == "in-review"
        return _decision("request-changes", note="Add units")

    def resubmit() -> dict[str, Any]:
        assert world.item["status"] == "needs-changes"
        return world.resubmit(2, _package())()

    result, context = world.run([changes, resubmit, _decision("approve", by="dave")])

    assert result["status"] == "published"
    assert world.item["status"] == "published"
    assert world.item["round"] == 2
    assert world.types() == [*REVIEWED, *REVIEWED, "published"]
    assert [e["round"] for e in world.reviews.events] == [1, 1, 1, 1, 2, 2, 2, 2, 2]
    assert [t for _, t in context.timeouts][1] == 30 * DAY
    assert f"reports/{SID}/2.json" in world.s3.objects
    assert world.item["approvals"] == ["dave"]


def test_a_blocking_error_returns_the_round_without_review(world: World) -> None:
    world.s3.objects = {}
    world.upload(1, _package(broken=True))

    def resubmit() -> dict[str, Any]:
        assert world.item["status"] == "needs-changes"
        assert world.item["callbackId"] == "cb-1"
        return world.resubmit(2, _package())()

    result, context = world.run([resubmit, _decision("approve")])

    assert result["status"] == "published"
    assert world.types() == ["scanned", "checked", *REVIEWED, "published"]
    first = world.reviews.events[1]
    assert first["blocked"] is True and first["errors"] > 0
    report = json.loads(world.s3.objects[f"reports/{SID}/1.json"])
    assert any(f["severity"] == "error" for f in report["findings"])
    assert world.s3.copies and all("/2/" in source for source, _ in world.s3.copies)
    assert context.timeouts[0] == ("resubmit-1", 30 * DAY)


def test_a_threat_tag_blocks_the_round_with_a_scan_finding(world: World) -> None:
    world.s3.tags[f"incoming/{SID}/1/data/logger.csv"] = "THREATS_FOUND"

    result, _ = world.run(["timeout"])

    assert result["status"] == "abandoned"
    assert world.types() == ["scanned", "checked", "abandoned"]
    assert world.reviews.events[0]["threats"] == {"data/logger.csv": "THREATS_FOUND"}
    report = json.loads(world.s3.objects[f"reports/{SID}/1.json"])
    assert [(f["ruleId"], f["severity"], f["target"]) for f in report["findings"]] == [
        ("scan.THREATS_FOUND", "error", {"path": "data/logger.csv"})
    ]
    assert world.s3.copies == []


def test_a_skip_rule_publishes_without_review(world: World) -> None:
    world.settings.policy = {"rules": [{"submitters": ["alice"], "outcome": "skip"}]}

    result, context = world.run([])

    assert result["status"] == "published"
    assert world.types() == ["scanned", "checked", "held", "published"]
    assert world.item["rule"] == 0
    assert world.reviews.events[-1]["rule"] == 0
    assert context.timeouts == []
    assert world.sns.published == []


def test_two_curators_wait_after_the_first_approval_and_publish_after_the_second(
    world: World,
) -> None:
    world.settings.policy = {
        "rules": [
            {"kind": "new-version", "outcome": "skip"},
            {"themes": ["soils"], "outcome": "two"},
        ],
        "reviewers": {"soils": ["rev-1", "rev-2"]},
    }
    world.s3.objects = {}
    world.upload(1, _package(themes=["soils", "water"]))

    def second() -> dict[str, Any]:
        assert world.item["approvals"] == ["carol"]
        assert world.item["status"] == "in-review"
        return _decision("approve", by="dave")

    result, context = world.run([_decision("approve"), second])

    assert result["status"] == "published"
    assert world.types() == [*REVIEWED, "published"]
    assert world.item["approvals"] == ["carol", "dave"]
    assert world.item["rule"] == 1
    assert [n for n, _ in context.timeouts] == ["review-1-1", "review-1-2"]
    [message] = world.sns.to(CURATORS)
    assert message["MessageAttributes"]["audience"]["StringValue"] == "rev-1"


def test_a_reminder_then_the_stale_mark_then_a_decision(world: World) -> None:
    world.settings.policy = {"reminders": [3], "staleDays": 5, "reviewers": {"soils": ["rev-1"]}}
    world.s3.objects = {}
    world.upload(1, _package(themes=["soils"]))

    result, context = world.run(["timeout", "timeout", "timeout", _decision("approve")])

    assert result["status"] == "published"
    assert world.types() == [*REVIEWED, "reminded", "stale", "published"]
    assert [t for _, t in context.timeouts] == [3 * DAY, 2 * DAY, 5 * DAY, 5 * DAY]
    assert world.item["stale"] is True
    audiences = [m["MessageAttributes"]["audience"]["StringValue"] for m in world.sns.to(CURATORS)]
    assert audiences == ["rev-1", "rev-1", "rev-1"]
    [alert] = world.sns.to(ALERTS)
    assert SID in alert["Message"]


def test_no_resubmit_within_thirty_days_ends_abandoned(world: World) -> None:
    result, context = world.run([_decision("request-changes"), "timeout"])

    assert result["status"] == "abandoned"
    assert world.item["status"] == "abandoned"
    assert world.types() == [*REVIEWED, "abandoned"]
    assert context.timeouts[-1] == ("resubmit-1", 30 * DAY)
    assert world.s3.keys(f"held/{SID}/") == []
    assert "callbackId" not in world.item


def test_a_failing_step_ends_failed_with_an_admin_alert(world: World) -> None:
    world.s3.fail_copy = True

    result, _ = world.run([])

    assert result["status"] == "failed"
    assert world.item["status"] == "failed"
    assert world.types() == ["scanned", "checked", "failed"]
    assert "copy refused" in world.reviews.events[-1]["error"]
    [alert] = world.sns.to(ALERTS)
    assert SID in alert["Subject"]


def test_a_replay_repeats_no_step_and_names_each_operation_once(world: World) -> None:
    world.settings.policy = {"reminders": [3], "staleDays": 5}
    first, context = world.run(
        [
            "timeout",
            _decision("request-changes"),
            world.resubmit(2, _package()),
            _decision("request-changes"),
            "timeout",
        ]
    )
    names = [name for _, name, _ in context.log]
    assert len(names) == len(set(names))
    events, messages = len(world.reviews.events), len(world.sns.published)

    replayed = ingest.run({"submissionId": SID}, cast(DurableContext, ReplayContext(context.log)))

    assert replayed == first
    assert (len(world.reviews.events), len(world.sns.published)) == (events, messages)
