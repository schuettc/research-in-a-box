"""The shapes of `/api/submissions`, `/api/people` and `/api/curators`, as Pydantic models.

The submissions handler validates request bodies with the request models (their checks raise
the API's own 400 messages) and builds every answer through the answer models, so the item's
`callbackId`, which only the pipeline needs, never leaves the API. `paths()` declares the routes
for the OpenAPI spec the read API writes, with these models' JSON Schemas as its components.
"""

from __future__ import annotations

import re
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import models_json_schema

from archive_backend.people import MAX_PEOPLE
from archive_contract import ReviewPolicy
from archive_contract.findings import Finding
from archive_contract.manifest import QualityVerdict, ValidationVerdict

Status = Literal[
    "draft",
    "checking",
    "needs-changes",
    "in-review",
    "publishing",
    "published",
    "rejected",
    "abandoned",
    "expired",
    "failed",
]
STATUSES: tuple[Status, ...] = get_args(Status)

EventType = Literal[
    "created",
    "submitted",
    "scanned",
    "checked",
    "held",
    "entered-review",
    "reminded",
    "stale",
    "decided",
    "resubmitted",
    "published",
    "rejected",
    "abandoned",
    "expired",
    "failed",
]

Decision = Literal["approve", "reject", "request-changes"]
DECISIONS: tuple[Decision, ...] = get_args(Decision)

MAX_PUT = 5 * 1024**3
MAX_FILES = 1000
SHA256 = re.compile(r"[0-9a-fA-F]{64}")
DATASET_ID = re.compile(r"[A-Za-z0-9_-]{1,200}")


class Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    def answer(self) -> dict[str, Any]:
        """The JSON answer: absent optional fields are left out, never sent as null."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


# Requests


class SubmittedFile(Model):
    """One file of a round: a relative path, its size in bytes and its SHA-256 in hex."""

    path: str
    size: int = Field(ge=0, le=MAX_PUT)
    sha256: str = Field(pattern=SHA256.pattern)


def _safe_path(path: object) -> bool:
    if not isinstance(path, str) or not path or len(path) > 900:
        return False
    if path.startswith("/") or "\\" in path or any(ord(ch) < 32 for ch in path):
        return False
    return all(part not in ("", ".", "..") for part in path.split("/"))


def check_files(value: object) -> list[dict[str, Any]]:
    """A round's file list: relative safe paths, each once, sizes up to 5 GB, SHA-256 in hex."""
    if not isinstance(value, list) or not value or len(value) > MAX_FILES:
        raise ValueError(f"files must list 1 to {MAX_FILES} files")
    files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("each file needs path, size and sha256")
        path, size, digest = entry.get("path"), entry.get("size"), entry.get("sha256")
        if not _safe_path(path) or not isinstance(path, str):
            raise ValueError(f"unsafe path: {path!r}")
        if path in seen:
            raise ValueError(f"path listed twice: {path}")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_PUT:
            raise ValueError(f"size of {path} must be 0 to {MAX_PUT} bytes")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError(f"sha256 of {path} must be 64 hex digits")
        seen.add(path)
        files.append({"path": path, "size": size, "sha256": digest.lower()})
    return files


class FilesRequest(Model):
    """`POST /api/submissions/{id}/uploads`: the round's files."""

    files: list[SubmittedFile] = Field(min_length=1, max_length=MAX_FILES)

    @model_validator(mode="before")
    @classmethod
    def _checked(cls, data: Any) -> Any:
        return cls._also({**data, "files": check_files(data.get("files"))})

    @classmethod
    def _also(cls, data: dict[str, Any]) -> dict[str, Any]:
        """A subclass's own checks, after the files'."""
        return data


class CreateRequest(FilesRequest):
    """`POST /api/submissions`: the first round's files, and the dataset it is for."""

    # No '.' or '/': the site function routes /datasets/<id> only for such an id.
    dataset_id: str | None = Field(default=None, alias="datasetId", pattern=DATASET_ID.pattern)

    @classmethod
    def _also(cls, data: dict[str, Any]) -> dict[str, Any]:
        dataset_id = data.get("datasetId")
        if dataset_id is not None and (
            not isinstance(dataset_id, str) or not DATASET_ID.fullmatch(dataset_id)
        ):
            raise ValueError("datasetId must be a dataset id")
        return data


class DecisionRequest(Model):
    """`POST /api/submissions/{id}/decision`: a curator's decision and an optional note."""

    decision: Decision
    note: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _checked(cls, data: Any) -> Any:
        if data.get("decision") not in DECISIONS:
            raise ValueError(f"decision must be one of {', '.join(DECISIONS)}")
        note = data.get("note")
        if note is not None and not isinstance(note, str):
            raise ValueError("note must be text")
        return data


# Answers


class UploadHeaders(Model):
    checksum: str = Field(alias="x-amz-checksum-sha256")


class Upload(Model):
    """A presigned PUT: send the file to `url` with `headers`, or S3 refuses it."""

    path: str
    url: str
    headers: UploadHeaders


class UploadsAnswer(Model):
    submission_id: str = Field(alias="submissionId")
    round: int
    uploads: list[Upload]


class SubmitAnswer(Model):
    submission_id: str = Field(alias="submissionId")
    round: int
    status: Literal["checking"]


class DecisionAnswer(Model):
    submission_id: str = Field(alias="submissionId")
    decision: Decision


class Submission(Model):
    """A submission as the API shows it.

    `waiting` is true while the pipeline holds an open callback: a resubmit or a decision is
    taken only then. `files` maps each round (as a string) to its files.
    """

    submission_id: str = Field(alias="submissionId")
    submitter: str
    submitter_is_curator: bool = Field(alias="submitterIsCurator")
    status: Status
    created_at: str = Field(alias="createdAt")
    round: int
    files: dict[str, list[SubmittedFile]]
    dataset_id: str | None = Field(default=None, alias="datasetId")
    new_version: bool = Field(alias="newVersion")
    rule: int | None = None
    approvals: list[str]
    stale: bool
    report_key: str | None = Field(default=None, alias="reportKey")
    waiting: bool

    @classmethod
    def of(cls, item: dict[str, Any]) -> Submission:
        """From the Submissions item, whose open `callbackId` becomes `waiting`."""
        return cls.model_validate({**item, "waiting": open_callback(item) is not None})


def open_callback(item: dict[str, Any]) -> str | None:
    """The pipeline's open callback on a Submissions item: its `callbackId`, unless the API has
    marked that id spent as `closedCallbackId` (it completed it but couldn't yet remove it)."""
    callback = item.get("callbackId")
    if not callback or callback == item.get("closedCallbackId"):
        return None
    return str(callback)


class Event(Model):
    """One audit event; the details present depend on `type`.

    scanned: files, threats. checked: errors, warnings, notes, reportKey, blocked. held: files.
    entered-review: rule, outcome, audience. reminded: day, audience. stale: days, audience.
    decided: decision, note, selfReview. rejected: note. published: rule, datasetId, version.
    abandoned and expired: days. failed: error.
    """

    submission_id: str = Field(alias="submissionId")
    event_key: str = Field(alias="eventKey")
    type: EventType
    actor: str = Field(description="A user id, or `pipeline`.")
    round: int
    at: str
    files: int | None = None
    threats: dict[str, str] | None = None
    errors: int | None = None
    warnings: int | None = None
    notes: int | None = None
    report_key: str | None = Field(default=None, alias="reportKey")
    blocked: bool | None = None
    rule: int | None = None
    outcome: Literal["one", "two"] | None = None
    audience: str | None = Field(default=None, description="A curator's user id, or `all`.")
    day: int | None = None
    days: int | None = None
    decision: Decision | None = None
    note: str | None = None
    self_review: bool | None = Field(default=None, alias="selfReview")
    dataset_id: str | None = Field(default=None, alias="datasetId")
    version: int | None = None
    error: str | None = None


class SubmissionList(Model):
    submissions: list[Submission]


class SubmissionRead(Model):
    """A submission, its events in order, and a link to its latest findings report."""

    submission: Submission
    events: list[Event]
    report_url: str | None = Field(default=None, alias="reportUrl")


class HeldFile(Model):
    """A held file with a five-minute download link."""

    path: str
    size: int
    sha256: str
    url: str


class HeldFiles(Model):
    round: int
    files: list[HeldFile]


class FindingsReport(Model):
    """The JSON at `reportUrl`: a round's checks. Both verdicts are null when the scan
    blocked the round, and `quality` is null when the manifest can't be read."""

    round: int
    validation: ValidationVerdict | None
    quality: QualityVerdict | None
    findings: list[Finding]


class Person(Model):
    email: str


class People(Model):
    """`GET /api/people`: each known id's email; unknown ids are left out."""

    people: dict[str, Person]


class Curator(Model):
    sub: str
    email: str


class ApiError(Model):
    error: str


# The OpenAPI paths

REF = "#/components/schemas/{model}"
# Every schema is the validation one: the contract's models serialize through a wrap serializer,
# whose serialization schema is a bare object, and the answer models validate as they dump.
MODELS: tuple[type[BaseModel], ...] = (
    CreateRequest,
    FilesRequest,
    DecisionRequest,
    ReviewPolicy,
    UploadsAnswer,
    SubmitAnswer,
    DecisionAnswer,
    SubmissionList,
    SubmissionRead,
    HeldFiles,
    FindingsReport,
    People,
    Curator,
    ApiError,
)


def _ref(model: type[BaseModel]) -> dict[str, str]:
    return {"$ref": REF.format(model=model.__name__)}


def paths() -> tuple[dict[str, Any], dict[str, Any]]:
    """The routes as OpenAPI paths, and the component schemas they refer to."""
    _, top = models_json_schema([(m, "validation") for m in MODELS], ref_template=REF)
    schemas: dict[str, Any] = top["$defs"]

    def body(model: type[BaseModel]) -> dict[str, Any]:
        return {"required": True, "content": {"application/json": {"schema": _ref(model)}}}

    def answer(status: int, schema: dict[str, Any], description: str = "OK") -> dict[str, Any]:
        content = {"application/json": {"schema": schema}}
        return {str(status): {"description": description, "content": content}}

    error = _ref(ApiError)

    def op(
        summary: str,
        status: int,
        model: type[BaseModel] | dict[str, Any],
        refused: tuple[int, ...],
        request: type[BaseModel] | None = None,
        parameters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        schema = model if isinstance(model, dict) else _ref(model)
        responses = answer(status, schema)
        for code in refused:
            responses.update(answer(code, error, "Refused"))
        operation: dict[str, Any] = {
            "summary": summary,
            "operationId": re.sub(r"[^a-z0-9]+", "_", summary.lower()).strip("_"),
            "responses": responses,
        }
        if request is not None:
            operation["requestBody"] = body(request)
        if parameters:
            operation["parameters"] = parameters
        return operation

    sid = [{"in": "path", "name": "id", "required": True, "schema": {"type": "string"}}]
    statuses = {"type": "string", "enum": list(STATUSES)}
    listing = [
        {"in": "query", "name": "status", "required": False, "schema": statuses},
        {"in": "query", "name": "mine", "required": False, "schema": {"type": "string"}},
    ]
    subs = [
        {
            "in": "query",
            "name": "sub",
            "required": False,
            "style": "form",
            "explode": True,
            "schema": {"type": "array", "items": {"type": "string"}, "maxItems": MAX_PEOPLE},
        }
    ]
    curators = {"type": "array", "items": _ref(Curator)}
    declared: dict[str, Any] = {
        "/api/submissions": {
            "get": op("List submissions", 200, SubmissionList, (400, 403), parameters=listing),
            "post": op("Create a submission", 201, UploadsAnswer, (400, 403), CreateRequest),
        },
        "/api/submissions/policy": {
            "get": op("Read the review policy", 200, ReviewPolicy, (403,)),
            "put": op("Save the review policy", 200, ReviewPolicy, (400, 403), ReviewPolicy),
        },
        "/api/submissions/{id}": {
            "get": op("Read a submission", 200, SubmissionRead, (403, 404), parameters=sid),
        },
        "/api/submissions/{id}/uploads": {
            "post": op(
                "Renew upload links",
                200,
                UploadsAnswer,
                (400, 403, 404, 409),
                FilesRequest,
                sid,
            ),
        },
        "/api/submissions/{id}/submit": {
            "post": op("Submit a round", 202, SubmitAnswer, (403, 404, 409), parameters=sid),
        },
        "/api/submissions/{id}/decision": {
            "post": op(
                "Decide a submission",
                202,
                DecisionAnswer,
                (400, 403, 404, 409),
                DecisionRequest,
                sid,
            ),
        },
        "/api/submissions/{id}/files": {
            "get": op("List the held files", 200, HeldFiles, (403, 404, 409), parameters=sid),
        },
        "/api/people": {
            "get": op("Look up people", 200, People, (400, 403), parameters=subs),
        },
        "/api/curators": {"get": op("List the curators", 200, curators, (403,))},
    }
    return declared, schemas
