import base64
import hashlib
import json
import re
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError

from archive_backend import submissions
from archive_backend.submissions import Clients, Env

STAGING = "staging"
ALIAS = "arn:aws:lambda:us-east-1:1:function:ingest:live"
PARAMETER = "/research-archive/test/catalog-active"
DIGEST = hashlib.sha256(b"a,b\n").hexdigest()
ENV = Env(
    submissions_table="submissions",
    reviews_table="reviews",
    settings_table="settings",
    staging_bucket=STAGING,
    ingest_alias_arn=ALIAS,
    active_catalog_parameter=PARAMETER,
    catalog_tables={"A": "catalog-a", "B": "catalog-b"},
)


def _failed(operation: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "no"}}, operation
    )


class FakeTable:
    """A table of plain items, understanding only the expressions the API writes."""

    def __init__(self, key: tuple[str, ...]) -> None:
        self.key = key
        self.items: dict[tuple[Any, ...], dict[str, Any]] = {}

    def _id(self, item: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(item[k] for k in self.key)

    def _check(self, current: dict[str, Any] | None, kwargs: dict[str, Any]) -> None:
        condition = kwargs.get("ConditionExpression")
        if condition is None:
            return
        if condition.startswith("attribute_not_exists("):
            if current is not None:
                raise _failed("PutItem")
            return
        name, value = (part.strip() for part in condition.split("="))
        field = kwargs["ExpressionAttributeNames"][name]
        if current is None or current.get(field) != kwargs["ExpressionAttributeValues"][value]:
            raise _failed("UpdateItem")

    def get_item(self, *, Key: dict[str, Any]) -> dict[str, Any]:
        item = self.items.get(self._id(Key))
        return {"Item": dict(item)} if item is not None else {}

    def put_item(self, *, Item: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        self._check(self.items.get(self._id(Item)), kwargs)
        self.items[self._id(Item)] = dict(Item)
        return {}

    def update_item(self, *, Key: dict[str, Any], UpdateExpression: str, **kwargs: Any) -> Any:
        current = self.items.get(self._id(Key))
        self._check(current, kwargs)
        assert current is not None
        assert UpdateExpression.startswith("SET ")
        for assignment in UpdateExpression[4:].split(","):
            name, value = (part.strip() for part in assignment.split("="))
            field = kwargs["ExpressionAttributeNames"][name]
            current[field] = kwargs["ExpressionAttributeValues"][value]
        return {}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        name, value = (part.strip() for part in kwargs["KeyConditionExpression"].split("="))
        field = kwargs["ExpressionAttributeNames"][name]
        wanted = kwargs["ExpressionAttributeValues"][value]
        found = [dict(i) for i in self.items.values() if i.get(field) == wanted]
        sort = {"bySubmitter": "createdAt", "byStatus": "createdAt"}.get(
            kwargs.get("IndexName", ""), self.key[-1]
        )
        return {"Items": sorted(found, key=lambda i: str(i.get(sort, "")))}


class FakeS3:
    def __init__(self) -> None:
        self.presigned: list[dict[str, Any]] = []

    def generate_presigned_url(self, method: str, Params: dict[str, Any], ExpiresIn: int) -> str:
        self.presigned.append({"method": method, **Params})
        return f"https://{Params['Bucket']}.s3/{Params['Key']}?signed"


class FakeLambda:
    def __init__(self) -> None:
        self.invocations: list[dict[str, Any]] = []
        self.callbacks: list[dict[str, Any]] = []

    def invoke(self, **kwargs: Any) -> dict[str, Any]:
        self.invocations.append(kwargs)
        return {"StatusCode": 202}

    def send_durable_execution_callback_success(self, **kwargs: Any) -> dict[str, Any]:
        self.callbacks.append({**kwargs, "Result": json.loads(kwargs["Result"])})
        return {}


class FakeSSM:
    def get_parameter(self, *, Name: str) -> dict[str, Any]:
        assert Name == PARAMETER
        return {"Parameter": {"Value": "B"}}


class World:
    def __init__(self) -> None:
        self.s3 = FakeS3()
        self.lambda_ = FakeLambda()
        self.submissions = FakeTable(("submissionId",))
        self.reviews = FakeTable(("submissionId", "eventKey"))
        self.settings = FakeTable(("name",))
        self.catalog = {"catalog-a": FakeTable(("PK", "SK")), "catalog-b": FakeTable(("PK", "SK"))}
        self.clients = Clients(
            s3=self.s3,
            lambda_=self.lambda_,
            ssm=cast(submissions.SSM, FakeSSM()),
            submissions=cast(submissions.Table, self.submissions),
            reviews=cast(submissions.Table, self.reviews),
            settings=cast(submissions.Table, self.settings),
            table=lambda name: cast(submissions.Table, self.catalog[name]),
        )

    def call(
        self,
        method: str,
        resource: str,
        user: str,
        groups: str,
        body: Any = None,
        sid: str | None = None,
        query: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        event = {
            "httpMethod": method,
            "resource": resource,
            "pathParameters": {"id": sid} if sid else None,
            "queryStringParameters": query,
            "body": json.dumps(body) if body is not None else None,
            "requestContext": {"authorizer": {"claims": {"sub": user, "cognito:groups": groups}}},
        }
        response = submissions.handle(event, self.clients, ENV)
        return response["statusCode"], json.loads(response["body"])

    def create(self, user: str = "alice", **extra: Any) -> str:
        status, body = self.call(
            "POST",
            "/api/submissions",
            user,
            "contributor",
            {"files": [{"path": "data/a.csv", "size": 4, "sha256": DIGEST}], **extra},
        )
        assert status == 201, body
        sid: str = body["submissionId"]
        return sid

    def events(self, sid: str) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = self.reviews.query(
            KeyConditionExpression="#k = :k",
            ExpressionAttributeNames={"#k": "submissionId"},
            ExpressionAttributeValues={":k": sid},
        )["Items"]
        return found


@pytest.fixture
def world() -> World:
    return World()


ROUTES = [
    ("POST", "/api/submissions", "curator,admin"),
    ("GET", "/api/submissions", "admin"),
    ("GET", "/api/submissions/policy", "contributor,curator"),
    ("PUT", "/api/submissions/policy", "contributor,curator"),
    ("POST", "/api/submissions/{id}/uploads", "contributor"),
    ("POST", "/api/submissions/{id}/submit", "contributor"),
    ("GET", "/api/submissions/{id}", "contributor"),
    ("POST", "/api/submissions/{id}/decision", "contributor,admin"),
]


@pytest.mark.parametrize(("method", "resource", "groups"), ROUTES)
def test_each_route_refuses_the_wrong_role(
    world: World, method: str, resource: str, groups: str
) -> None:
    sid = world.create("alice")
    status, body = world.call(method, resource, "mallory", groups, {}, sid=sid)
    assert status == 403, body


def test_create_records_the_submission_and_returns_checksummed_urls(world: World) -> None:
    sid = world.create("alice")

    item = world.submissions.items[(sid,)]
    assert item["submitter"] == "alice"
    assert item["status"] == "draft"
    assert item["round"] == 1
    assert item["newVersion"] is False
    assert item["files"] == {"1": [{"path": "data/a.csv", "size": 4, "sha256": DIGEST}]}
    checksum = base64.b64encode(bytes.fromhex(DIGEST)).decode()
    assert world.s3.presigned == [
        {
            "method": "put_object",
            "Bucket": STAGING,
            "Key": f"incoming/{sid}/1/data/a.csv",
            "ChecksumSHA256": checksum,
        }
    ]
    assert [e["type"] for e in world.events(sid)] == ["created"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT[^#]+#[0-9a-f-]{36}", world.events(sid)[0]["eventKey"])


def test_a_real_presigned_put_signs_the_checksum_header() -> None:
    s3 = boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="x",
        aws_secret_access_key="y",
        config=submissions.S3_CONFIG,
    )
    assert isinstance(submissions.S3_CONFIG, Config)
    upload = submissions.presigned_put(s3, STAGING, "incoming/s/1/a.csv", DIGEST)
    query = parse_qs(urlparse(upload["url"]).query)
    assert "x-amz-checksum-sha256" in query["X-Amz-SignedHeaders"][0].split(";")
    assert upload["headers"] == {
        "x-amz-checksum-sha256": base64.b64encode(bytes.fromhex(DIGEST)).decode()
    }


@pytest.mark.parametrize(
    "file",
    [
        {"path": "../escape.csv", "size": 4, "sha256": DIGEST},
        {"path": "/abs.csv", "size": 4, "sha256": DIGEST},
        {"path": "data//a.csv", "size": 4, "sha256": DIGEST},
        {"path": "data/a.csv", "size": -1, "sha256": DIGEST},
        {"path": "data/a.csv", "size": 4, "sha256": "not-hex"},
    ],
)
def test_create_refuses_a_bad_file(world: World, file: dict[str, Any]) -> None:
    status, body = world.call("POST", "/api/submissions", "alice", "contributor", {"files": [file]})
    assert status == 400, body
    assert world.submissions.items == {}


def _publish(world: World, dataset_id: str, submitter: str) -> None:
    # The catalog's dataset item carries no submitter; ownership is a published submission.
    world.catalog["catalog-b"].items[(f"DATASET#{dataset_id}", "META")] = {
        "PK": f"DATASET#{dataset_id}",
        "SK": "META",
        "currentVersion": 1,
    }
    world.submissions.items[(f"published-{dataset_id}",)] = {
        "submissionId": f"published-{dataset_id}",
        "submitter": submitter,
        "status": "published",
        "createdAt": "2026-01-01T00:00:00Z",
        "datasetId": dataset_id,
    }


FILES = [{"path": "a.csv", "size": 4, "sha256": DIGEST}]


def test_a_new_version_is_allowed_to_the_submitter_who_published_it(world: World) -> None:
    _publish(world, "rain", "alice")

    own = world.create("alice", datasetId="rain")

    assert world.submissions.items[(own,)]["newVersion"] is True


def test_a_new_version_is_refused_to_a_stranger(world: World) -> None:
    _publish(world, "rain", "alice")
    # bob's own submission of rain that never published gives no ownership.
    world.submissions.items[("bob-draft",)] = {
        "submissionId": "bob-draft",
        "submitter": "bob",
        "status": "rejected",
        "createdAt": "2026-01-02T00:00:00Z",
        "datasetId": "rain",
    }

    status, body = world.call(
        "POST", "/api/submissions", "bob", "contributor", {"files": FILES, "datasetId": "rain"}
    )

    assert status == 403, body


def test_a_curator_may_always_version_a_dataset(world: World) -> None:
    _publish(world, "rain", "alice")

    status, body = world.call(
        "POST",
        "/api/submissions",
        "carol",
        "contributor,curator",
        {"files": FILES, "datasetId": "rain"},
    )

    assert status == 201, body
    assert world.submissions.items[(body["submissionId"],)]["newVersion"] is True


def test_create_records_whether_the_submitter_is_a_curator(world: World) -> None:
    plain = world.create("alice")
    status, body = world.call(
        "POST", "/api/submissions", "carol", "contributor,curator", {"files": FILES}
    )

    assert status == 201, body
    assert world.submissions.items[(plain,)]["submitterIsCurator"] is False
    assert world.submissions.items[(body["submissionId"],)]["submitterIsCurator"] is True


@pytest.mark.parametrize("dataset_id", ["rain.v2", "rain/2", "", "a" * 201, 7])
def test_create_refuses_a_dataset_id_the_site_could_not_route(
    world: World, dataset_id: object
) -> None:
    # The site function routes /datasets/<id> only for an id with no '.' or '/'.
    status, body = world.call(
        "POST",
        "/api/submissions",
        "alice",
        "contributor",
        {"files": FILES, "datasetId": dataset_id},
    )

    assert status == 400, body
    assert world.submissions.items == {}


def test_an_unknown_dataset_id_is_a_new_dataset(world: World) -> None:
    fresh = world.create("bob", datasetId="snow")

    assert world.submissions.items[(fresh,)]["newVersion"] is False
    assert world.submissions.items[(fresh,)]["datasetId"] == "snow"


def test_submit_starts_the_execution_named_by_the_submission(world: World) -> None:
    sid = world.create("alice")

    status, body = world.call(
        "POST", "/api/submissions/{id}/submit", "alice", "contributor", sid=sid
    )

    assert status == 202, body
    assert world.lambda_.invocations == [
        {
            "FunctionName": ALIAS,
            "InvocationType": "Event",
            "DurableExecutionName": sid,
            "Payload": json.dumps({"submissionId": sid}).encode(),
        }
    ]
    assert world.submissions.items[(sid,)]["status"] == "checking"
    assert [e["type"] for e in world.events(sid)] == ["created", "submitted"]
    again, _ = world.call("POST", "/api/submissions/{id}/submit", "alice", "contributor", sid=sid)
    assert again == 409
    assert len(world.lambda_.invocations) == 1


def test_resubmit_completes_the_stored_callback(world: World) -> None:
    sid = world.create("alice")
    world.submissions.items[(sid,)].update(status="needs-changes", callbackId="cb-resubmit")

    status, body = world.call(
        "POST",
        "/api/submissions/{id}/uploads",
        "alice",
        "contributor",
        {"files": [{"path": "data/a.csv", "size": 5, "sha256": DIGEST}]},
        sid=sid,
    )
    assert status == 200, body
    assert body["round"] == 2
    assert world.s3.presigned[-1]["Key"] == f"incoming/{sid}/2/data/a.csv"

    status, body = world.call(
        "POST", "/api/submissions/{id}/submit", "alice", "contributor", sid=sid
    )

    assert status == 202, body
    assert world.lambda_.invocations == []
    assert world.lambda_.callbacks == [
        {"CallbackId": "cb-resubmit", "Result": {"kind": "resubmit", "round": 2}}
    ]
    assert world.submissions.items[(sid,)]["round"] == 2
    assert [e["type"] for e in world.events(sid)] == ["created", "resubmitted"]


def _in_review(world: World, submitter: str = "alice") -> str:
    sid = world.create(submitter)
    world.submissions.items[(sid,)].update(status="in-review", callbackId="cb-review")
    return sid


def test_a_decision_writes_its_event_then_completes_the_callback(world: World) -> None:
    sid = _in_review(world)

    status, body = world.call(
        "POST",
        "/api/submissions/{id}/decision",
        "carol",
        "curator",
        {"decision": "request-changes", "note": "Add units"},
        sid=sid,
    )

    assert status == 202, body
    decided = world.events(sid)[-1]
    assert decided["type"] == "decided"
    assert decided["actor"] == "carol"
    assert decided["decision"] == "request-changes"
    assert decided["note"] == "Add units"
    assert "selfReview" not in decided
    assert world.lambda_.callbacks == [
        {
            "CallbackId": "cb-review",
            "Result": {
                "kind": "decision",
                "decision": "request-changes",
                "by": "carol",
                "note": "Add units",
            },
        }
    ]


def test_a_curator_deciding_their_own_submission_is_recorded(world: World) -> None:
    sid = _in_review(world, submitter="carol")

    status, _ = world.call(
        "POST",
        "/api/submissions/{id}/decision",
        "carol",
        "curator",
        {"decision": "approve"},
        sid=sid,
    )

    assert status == 202
    assert world.events(sid)[-1]["selfReview"] is True


def test_a_second_approval_from_the_same_curator_is_refused(world: World) -> None:
    sid = _in_review(world)
    world.submissions.items[(sid,)]["approvals"] = ["carol"]

    status, body = world.call(
        "POST",
        "/api/submissions/{id}/decision",
        "carol",
        "curator",
        {"decision": "approve"},
        sid=sid,
    )

    assert status == 409, body
    assert world.lambda_.callbacks == []
    assert [e["type"] for e in world.events(sid)] == ["created"]
    other, _ = world.call(
        "POST",
        "/api/submissions/{id}/decision",
        "dave",
        "curator",
        {"decision": "approve"},
        sid=sid,
    )
    assert other == 202


def test_the_policy_round_trips_and_an_invalid_policy_is_refused(world: World) -> None:
    status, body = world.call("GET", "/api/submissions/policy", "root", "admin")
    assert status == 200
    assert body == {
        "required": True,
        "rules": [],
        "reviewers": {},
        "reminders": [],
        "staleDays": 14,
    }

    policy = {
        "required": True,
        "rules": [{"submitters": ["curators"], "outcome": "skip"}],
        "reviewers": {"climate": ["carol"]},
        "reminders": [3, 7],
        "staleDays": 10,
    }
    status, body = world.call("PUT", "/api/submissions/policy", "root", "admin", policy)
    assert status == 200, body
    status, body = world.call("GET", "/api/submissions/policy", "root", "admin")
    assert body["rules"] == [{"submitters": ["curators"], "outcome": "skip"}]
    assert body["staleDays"] == 10

    status, _ = world.call(
        "PUT", "/api/submissions/policy", "root", "admin", {"reminders": [20], "staleDays": 14}
    )
    assert status == 400
    _, body = world.call("GET", "/api/submissions/policy", "root", "admin")
    assert body["staleDays"] == 10


def test_lists_and_reads_follow_the_caller(world: World) -> None:
    mine = world.create("alice")
    world.create("bob")
    world.submissions.items[(mine,)].update(status="in-review")

    _, own = world.call("GET", "/api/submissions", "alice", "contributor")
    assert [s["submissionId"] for s in own["submissions"]] == [mine]
    _, queue = world.call(
        "GET", "/api/submissions", "carol", "curator", query={"status": "in-review"}
    )
    assert [s["submissionId"] for s in queue["submissions"]] == [mine]

    status, body = world.call("GET", "/api/submissions/{id}", "carol", "curator", sid=mine)
    assert status == 200
    assert body["submission"]["submissionId"] == mine
    assert [e["type"] for e in body["events"]] == ["created"]
    stranger, _ = world.call("GET", "/api/submissions/{id}", "bob", "contributor", sid=mine)
    assert stranger == 403
