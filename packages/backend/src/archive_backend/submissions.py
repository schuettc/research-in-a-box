"""Submissions: the record, its audit events, and the `/api/submissions` API.

A submission is one item in the Submissions table, keyed by `submissionId`; every state change
and decision is one event in the Reviews table, keyed by `submissionId` and `eventKey` =
`<ISO time>#<uuid>`. The API checks the caller's role from the token's `cognito:groups` claim,
hands out presigned PUTs that require each file's SHA-256, starts the ingest execution (named by
the submission id) through its `live` alias, and completes the execution's open callback on a
resubmit or a curator's decision.
"""

from __future__ import annotations

import base64
import json
import os
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, TypedDict, cast

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import BaseModel, ValidationError

from archive_backend import people
from archive_backend.people import Cognito as Cognito
from archive_backend.submissions_api import STATUSES as STATUSES
from archive_backend.submissions_api import (
    CreateRequest,
    Curator,
    DecisionAnswer,
    DecisionRequest,
    Event,
    EventType,
    FilesRequest,
    HeldFiles,
    People,
    Status,
    SubmissionList,
    SubmissionRead,
    SubmitAnswer,
    UploadsAnswer,
)
from archive_backend.submissions_api import Submission as SubmissionAnswer
from archive_backend.whoami import _groups
from archive_contract import ReviewPolicy

CONTRIBUTOR = "contributor"
CURATOR = "curator"
ADMIN = "admin"
POLICY_SETTING = "review-policy"
URL_SECONDS = 3600
HELD_URL_SECONDS = 300
HELD: tuple[Status, ...] = ("in-review", "publishing")
S3_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "virtual"})


class FileEntry(TypedDict):
    path: str
    size: int
    sha256: str


class Submission(TypedDict, total=False):
    """The Submissions item. `files` maps each round (as a string) to its files."""

    submissionId: str
    submitter: str
    submitterIsCurator: bool
    status: Status
    createdAt: str
    round: int
    files: dict[str, list[FileEntry]]
    datasetId: str
    newVersion: bool
    rule: int | None
    approvals: list[str]
    stale: bool
    callbackId: str
    reportKey: str


class Table(Protocol):
    """A boto3 DynamoDB Table resource (boto3-stubs has no dynamodb extra installed)."""

    def get_item(self, **kwargs: Any) -> dict[str, Any]: ...
    def put_item(self, **kwargs: Any) -> Any: ...
    def update_item(self, **kwargs: Any) -> Any: ...
    def query(self, **kwargs: Any) -> dict[str, Any]: ...


class S3(Protocol):
    def generate_presigned_url(self, *args: Any, **kwargs: Any) -> str: ...
    def head_object(self, **kwargs: Any) -> dict[str, Any]: ...


class Lambda(Protocol):
    def invoke(self, **kwargs: Any) -> Any: ...
    def send_durable_execution_callback_success(self, **kwargs: Any) -> Any: ...


class SSM(Protocol):
    def get_parameter(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Clients:
    s3: S3
    lambda_: Lambda
    ssm: SSM
    submissions: Table
    reviews: Table
    settings: Table
    table: Callable[[str], Table]
    cognito: Cognito


@dataclass(frozen=True)
class Env:
    submissions_table: str
    reviews_table: str
    settings_table: str
    staging_bucket: str
    ingest_alias_arn: str
    active_catalog_parameter: str
    catalog_tables: dict[str, str]
    user_pool_id: str

    @classmethod
    def from_environ(cls) -> Env:
        return cls(
            submissions_table=os.environ["SUBMISSIONS_TABLE"],
            reviews_table=os.environ["REVIEWS_TABLE"],
            settings_table=os.environ["SETTINGS_TABLE"],
            staging_bucket=os.environ["STAGING_BUCKET"],
            ingest_alias_arn=os.environ["INGEST_ALIAS_ARN"],
            active_catalog_parameter=os.environ["ACTIVE_CATALOG_PARAMETER"],
            catalog_tables={"A": os.environ["CATALOG_TABLE_A"], "B": os.environ["CATALOG_TABLE_B"]},
            user_pool_id=os.environ["USER_POOL_ID"],
        )


def clients(env: Env) -> Clients:
    dynamodb = boto3.resource("dynamodb")

    def table(name: str) -> Table:
        return cast(Table, dynamodb.Table(name))

    return Clients(
        s3=cast(S3, boto3.client("s3", config=S3_CONFIG)),
        lambda_=cast(Lambda, boto3.client("lambda")),
        ssm=cast(SSM, boto3.client("ssm")),
        submissions=table(env.submissions_table),
        reviews=table(env.reviews_table),
        settings=table(env.settings_table),
        table=table,
        cognito=cast(Cognito, boto3.client("cognito-idp")),
    )


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def put_event(
    table: Table, submission_id: str, type: EventType, actor: str, round: int, **details: Any
) -> dict[str, Any]:
    """Write one audit event; `actor` is a user id or `pipeline`."""
    at = now()
    item: dict[str, Any] = {
        "submissionId": submission_id,
        "eventKey": f"{at}#{uuid.uuid4()}",
        "type": type,
        "actor": actor,
        "round": round,
        "at": at,
        **details,
    }
    table.put_item(Item=item)
    return item


class Refused(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status


def _response(status: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=_plain),
    }


def _answer(status: int, model: BaseModel) -> dict[str, Any]:
    return _response(status, model.model_dump(mode="json", by_alias=True, exclude_none=True))


def _plain(value: object) -> object:
    # The Table resource reads numbers back as Decimal.
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _parse[M: BaseModel](model: type[M], body: dict[str, Any]) -> M:
    """The body as `model`, or a 400 with the model's own message."""
    try:
        return model.model_validate(body)
    except ValidationError as error:
        first = error.errors()[0]
        cause = (first.get("ctx") or {}).get("error")
        raise Refused(400, str(cause) if cause is not None else first["msg"]) from error


def _close_callback(c: Clients, sid: str, callback: str) -> None:
    """Forget a callback this call completed, so `waiting` turns false until the pipeline
    opens its next wait; a wait it opened since is a different id and is kept."""
    try:
        c.submissions.update_item(
            Key={"submissionId": sid},
            UpdateExpression="REMOVE #c",
            ConditionExpression="#c = :c",
            ExpressionAttributeNames={"#c": "callbackId"},
            ExpressionAttributeValues={":c": callback},
        )
    except ClientError:
        # The callback went through; a stale id only leaves `waiting` true a little longer.
        pass


def presigned_put(s3: S3, bucket: str, key: str, digest: str) -> dict[str, Any]:
    """A PUT URL that signs the file's SHA-256, so S3 refuses a file that doesn't match."""
    checksum = base64.b64encode(bytes.fromhex(digest)).decode()
    url = s3.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ChecksumSHA256": checksum},
        ExpiresIn=URL_SECONDS,
    )
    return {"url": url, "headers": {"x-amz-checksum-sha256": checksum}}


def _uploads(c: Clients, env: Env, sid: str, round: int, files: list[FileEntry]) -> list[Any]:
    return [
        {
            "path": f["path"],
            **presigned_put(
                c.s3, env.staging_bucket, f"incoming/{sid}/{round}/{f['path']}", f["sha256"]
            ),
        }
        for f in files
    ]


def _uploads_answer(
    c: Clients, env: Env, sid: str, round: int, files: list[FileEntry]
) -> UploadsAnswer:
    uploads = _uploads(c, env, sid, round, files)
    return UploadsAnswer.model_validate({"submissionId": sid, "round": round, "uploads": uploads})


def _missing(c: Clients, env: Env, sid: str, round: int, files: list[Any]) -> list[str]:
    """The round's declared files not in `incoming/`: not uploaded yet, or expired."""
    missing: list[str] = []
    for f in files:
        try:
            c.s3.head_object(Bucket=env.staging_bucket, Key=f"incoming/{sid}/{round}/{f['path']}")
        except ClientError as error:
            # Without ListBucket, S3 answers 403 rather than 404 for a missing key.
            if error.response["Error"]["Code"] not in ("403", "404", "NoSuchKey"):
                raise
            missing.append(str(f["path"]))
    return missing


def _update(
    c: Clients, sid: str, fields: dict[str, Any], expect: Status, call: str = "update"
) -> None:
    """Set fields on a submission only while its status is `expect`."""
    names = {f"#f{i}": name for i, name in enumerate(fields)}
    values = {f":f{i}": value for i, value in enumerate(fields.values())}
    names["#status"] = "status"
    values[":expected"] = expect
    try:
        c.submissions.update_item(
            Key={"submissionId": sid},
            UpdateExpression="SET " + ", ".join(f"#f{i} = :f{i}" for i in range(len(fields))),
            ConditionExpression="#status = :expected",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise Refused(409, f"submission is no longer {expect}") from error
        raise


def _load(c: Clients, sid: str | None) -> dict[str, Any]:
    if not sid:
        raise Refused(404, "no such submission")
    item = c.submissions.get_item(Key={"submissionId": sid}).get("Item")
    if item is None:
        raise Refused(404, "no such submission")
    return cast(dict[str, Any], item)


@dataclass(frozen=True)
class Caller:
    user: str
    groups: frozenset[str]

    def need(self, *groups: str) -> None:
        if not self.groups & set(groups):
            raise Refused(403, f"needs the {' or '.join(groups)} group")


def _own(caller: Caller, submission: dict[str, Any]) -> None:
    if submission.get("submitter") != caller.user:
        raise Refused(403, "only its submitter may do this")


def _dataset(c: Clients, env: Env, dataset_id: str) -> dict[str, Any] | None:
    active = c.ssm.get_parameter(Name=env.active_catalog_parameter)["Parameter"]["Value"]
    table = c.table(env.catalog_tables[active])
    item = table.get_item(Key={"PK": f"DATASET#{dataset_id}", "SK": "META"}).get("Item")
    return cast(dict[str, Any] | None, item)


def _published_by(c: Clients, user: str, dataset_id: str) -> bool:
    """Whether one of `user`'s own submissions published `dataset_id`.

    The catalog's dataset items are rebuilt from manifests by the reindex, so ownership comes
    from the Submissions table, never from the catalog.
    """
    query: dict[str, Any] = {
        "IndexName": "bySubmitter",
        "KeyConditionExpression": "#k = :k",
        "ExpressionAttributeNames": {"#k": "submitter"},
        "ExpressionAttributeValues": {":k": user},
    }
    while True:
        page = c.submissions.query(**query)
        for item in page.get("Items", []):
            if item.get("status") == "published" and item.get("datasetId") == dataset_id:
                return True
        last = page.get("LastEvaluatedKey")
        if not last:
            return False
        query["ExclusiveStartKey"] = last


def create(c: Clients, env: Env, caller: Caller, body: dict[str, Any]) -> dict[str, Any]:
    caller.need(CONTRIBUTOR)
    request = _parse(CreateRequest, body)
    files = cast(list[FileEntry], [f.model_dump() for f in request.files])
    record: dict[str, Any] = {"newVersion": False}
    dataset_id = request.dataset_id
    if dataset_id is not None:
        record["datasetId"] = dataset_id
        published = _dataset(c, env, dataset_id)
        if published is not None:
            if CURATOR not in caller.groups and not _published_by(c, caller.user, dataset_id):
                raise Refused(403, f"only {dataset_id}'s submitter or a curator may version it")
            record["newVersion"] = True
    sid = str(uuid.uuid4())
    item: dict[str, Any] = {
        "submissionId": sid,
        "submitter": caller.user,
        "submitterIsCurator": CURATOR in caller.groups,
        "status": "draft",
        "createdAt": now(),
        "round": 1,
        "files": {"1": files},
        "approvals": [],
        "stale": False,
        **record,
    }
    c.submissions.put_item(Item=item, ConditionExpression="attribute_not_exists(submissionId)")
    put_event(c.reviews, sid, "created", caller.user, 1)
    return _answer(201, _uploads_answer(c, env, sid, 1, files))


def uploads(c: Clients, env: Env, caller: Caller, sid: str | None, body: Any) -> dict[str, Any]:
    """The next round's URLs while `needs-changes`; asked again before submit, the same round's.

    A round-1 draft asks again when its links expired before every file was uploaded.
    """
    caller.need(CONTRIBUTOR)
    submission = _load(c, sid)
    _own(caller, submission)
    files = cast(list[FileEntry], [f.model_dump() for f in _parse(FilesRequest, body).files])
    current = int(submission["round"])
    status = submission.get("status")
    expect: Status
    if status == "needs-changes":
        round, expect = current + 1, "needs-changes"
    elif status == "draft":
        round, expect = current, "draft"
    else:
        raise Refused(409, f"no uploads while {status}")
    sid = cast(str, sid)
    rounds = dict(submission.get("files") or {})
    rounds[str(round)] = files
    _update(c, sid, {"files": rounds, "round": round, "status": "draft"}, expect)
    return _answer(200, _uploads_answer(c, env, sid, round, files))


def submit(c: Clients, env: Env, caller: Caller, sid: str | None) -> dict[str, Any]:
    """Round 1 starts the execution; a later round completes its resubmit callback."""
    caller.need(CONTRIBUTOR)
    submission = _load(c, sid)
    _own(caller, submission)
    sid = cast(str, sid)
    round = int(submission["round"])
    if submission.get("status") != "draft":
        raise Refused(409, f"cannot submit while {submission.get('status')}")
    callback = submission.get("callbackId")
    if round > 1 and not callback:
        raise Refused(409, "the pipeline is not waiting for a resubmit")
    missing = _missing(c, env, sid, round, (submission.get("files") or {}).get(str(round)) or [])
    if missing:
        raise Refused(409, f"not uploaded yet: {', '.join(missing)}")
    _update(c, sid, {"status": "checking"}, "draft")
    try:
        if round == 1:
            c.lambda_.invoke(
                FunctionName=env.ingest_alias_arn,
                InvocationType="Event",
                DurableExecutionName=sid,
                Payload=json.dumps({"submissionId": sid}).encode(),
            )
        else:
            c.lambda_.send_durable_execution_callback_success(
                CallbackId=callback,
                Result=json.dumps({"kind": "resubmit", "round": round}).encode(),
            )
    except ClientError:
        _update(c, sid, {"status": "draft"}, "checking")
        raise
    if callback and round > 1:
        _close_callback(c, sid, str(callback))
    put_event(c.reviews, sid, "submitted" if round == 1 else "resubmitted", caller.user, round)
    return _answer(202, SubmitAnswer(submission_id=sid, round=round, status="checking"))


def decide(c: Clients, caller: Caller, sid: str | None, body: dict[str, Any]) -> dict[str, Any]:
    caller.need(CURATOR)
    submission = _load(c, sid)
    sid = cast(str, sid)
    request = _parse(DecisionRequest, body)
    decision, note = request.decision, request.note
    callback = submission.get("callbackId")
    if submission.get("status") != "in-review" or not callback:
        raise Refused(409, f"not in review ({submission.get('status')})")
    if decision == "approve" and caller.user in (submission.get("approvals") or []):
        raise Refused(409, "a second approval must come from a different curator")
    details: dict[str, Any] = {"decision": decision}
    if note is not None:
        details["note"] = note
    if submission.get("submitter") == caller.user:
        details["selfReview"] = True
    put_event(c.reviews, sid, "decided", caller.user, int(submission["round"]), **details)
    result = {"kind": "decision", "decision": decision, "by": caller.user, "note": note}
    try:
        c.lambda_.send_durable_execution_callback_success(
            CallbackId=callback, Result=json.dumps(result).encode()
        )
    except ClientError as error:
        raise Refused(409, "the review wait has already closed") from error
    _close_callback(c, sid, str(callback))
    return _answer(202, DecisionAnswer(submission_id=sid, decision=decision))


def listing(c: Clients, caller: Caller, query: dict[str, str]) -> dict[str, Any]:
    """A curator's queue by status (default `in-review`), or a contributor's own submissions."""
    caller.need(CONTRIBUTOR, CURATOR)
    value: str
    if CURATOR in caller.groups and "mine" not in query:
        wanted = query.get("status", "in-review")
        if wanted not in STATUSES:
            raise Refused(400, f"unknown status {wanted}")
        index, field, value = "byStatus", "status", str(wanted)
    else:
        index, field, value = "bySubmitter", "submitter", caller.user
    found = c.submissions.query(
        IndexName=index,
        KeyConditionExpression="#k = :k",
        ExpressionAttributeNames={"#k": field},
        ExpressionAttributeValues={":k": value},
    )
    listed = [SubmissionAnswer.of(item) for item in found.get("Items", [])]
    return _answer(200, SubmissionList(submissions=listed))


def read(c: Clients, env: Env, caller: Caller, sid: str | None) -> dict[str, Any]:
    caller.need(CONTRIBUTOR, CURATOR)
    submission = _load(c, sid)
    if CURATOR not in caller.groups:
        _own(caller, submission)
    events = c.reviews.query(
        KeyConditionExpression="#k = :k",
        ExpressionAttributeNames={"#k": "submissionId"},
        ExpressionAttributeValues={":k": sid},
    ).get("Items", [])
    report = submission.get("reportKey")
    url = (
        c.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": env.staging_bucket, "Key": report},
            ExpiresIn=URL_SECONDS,
        )
        if report
        else None
    )
    answer = SubmissionRead(
        submission=SubmissionAnswer.of(submission),
        events=[Event.model_validate(event) for event in events],
        report_url=url,
    )
    return _answer(200, answer)


def files(c: Clients, env: Env, caller: Caller, sid: str | None) -> dict[str, Any]:
    """A curator's five-minute links to the held round's listed files, and only those."""
    caller.need(CURATOR)
    submission = _load(c, sid)
    status = submission.get("status")
    # held/<id>/ exists only from hold until publish or a closing decision empties it.
    if status not in HELD:
        raise Refused(409, f"nothing is held while {status}")
    round = int(submission["round"])
    listed = (submission.get("files") or {}).get(str(round)) or []
    held = HeldFiles.model_validate(
        {
            "round": round,
            "files": [
                {
                    "path": f["path"],
                    "size": f["size"],
                    "sha256": f["sha256"],
                    "url": c.s3.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": env.staging_bucket, "Key": f"held/{sid}/{f['path']}"},
                        ExpiresIn=HELD_URL_SECONDS,
                    ),
                }
                for f in listed
            ],
        }
    )
    return _answer(200, held)


def stored_policy(settings: Table) -> ReviewPolicy:
    """The Settings item `review-policy`, or the defaults when none is set."""
    item = settings.get_item(Key={"name": POLICY_SETTING}).get("Item")
    if item is None:
        return ReviewPolicy()
    return ReviewPolicy.model_validate_json(str(item["policy"]))


def get_policy(c: Clients, caller: Caller) -> dict[str, Any]:
    caller.need(ADMIN)
    return _response(200, stored_policy(c.settings).dump())


def put_policy(c: Clients, caller: Caller, body: Any) -> dict[str, Any]:
    caller.need(ADMIN)
    try:
        policy = ReviewPolicy.model_validate(body)
    except ValidationError as error:
        raise Refused(400, f"invalid policy: {error}") from error
    c.settings.put_item(
        Item={
            "name": POLICY_SETTING,
            "policy": policy.model_dump_json(by_alias=True),
            "updatedBy": caller.user,
            "updatedAt": now(),
        }
    )
    return _response(200, policy.dump())


def lookup_people(c: Clients, env: Env, caller: Caller, subs: list[str]) -> dict[str, Any]:
    """Email addresses for the ids a curator or admin sees in submissions and events."""
    caller.need(CURATOR, ADMIN)
    if len(subs) > people.MAX_PEOPLE:
        raise Refused(400, f"at most {people.MAX_PEOPLE} ids at once")
    for sub in subs:
        if not people.SUB.fullmatch(sub):
            raise Refused(400, f"not a user id: {sub!r}")
    found = People.model_validate({"people": people.emails(c.cognito, env.user_pool_id, subs)})
    return _answer(200, found)


def list_curators(c: Clients, env: Env, caller: Caller) -> dict[str, Any]:
    """The curator group, for the admin choosing named reviewers."""
    caller.need(ADMIN)
    listed = [Curator.model_validate(p) for p in people.curators(c.cognito, env.user_pool_id)]
    return _response(200, [curator.answer() for curator in listed])


def handle(event: dict[str, Any], c: Clients, env: Env) -> dict[str, Any]:
    """Route one API Gateway proxy event by method and resource."""
    claims: dict[str, Any] = event["requestContext"]["authorizer"]["claims"]
    caller = Caller(str(claims["sub"]), frozenset(_groups(claims.get("cognito:groups"))))
    sid = (event.get("pathParameters") or {}).get("id")
    query = event.get("queryStringParameters") or {}
    multi = event.get("multiValueQueryStringParameters") or {}
    route = (event.get("httpMethod"), event.get("resource"))
    try:
        body = json.loads(event.get("body") or "{}")
        if route[0] in ("POST", "PUT") and not isinstance(body, dict):
            raise Refused(400, "the body must be a JSON object")
        match route:
            case ("POST", "/api/submissions"):
                return create(c, env, caller, body)
            case ("GET", "/api/submissions"):
                return listing(c, caller, query)
            case ("GET", "/api/submissions/policy"):
                return get_policy(c, caller)
            case ("PUT", "/api/submissions/policy"):
                return put_policy(c, caller, body)
            case ("POST", "/api/submissions/{id}/uploads"):
                return uploads(c, env, caller, sid, body)
            case ("POST", "/api/submissions/{id}/submit"):
                return submit(c, env, caller, sid)
            case ("GET", "/api/submissions/{id}"):
                return read(c, env, caller, sid)
            case ("GET", "/api/submissions/{id}/files"):
                return files(c, env, caller, sid)
            case ("POST", "/api/submissions/{id}/decision"):
                return decide(c, caller, sid, body)
            case ("GET", "/api/people"):
                return lookup_people(c, env, caller, list(multi.get("sub") or []))
            case ("GET", "/api/curators"):
                return list_curators(c, env, caller)
        return _response(404, {"error": f"no route {route[0]} {route[1]}"})
    except json.JSONDecodeError:
        return _response(400, {"error": "the body must be JSON"})
    except Refused as refused:
        return _response(refused.status, {"error": str(refused)})


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    env = Env.from_environ()
    return handle(event, clients(env), env)
