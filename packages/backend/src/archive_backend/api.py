"""The read API: search, dataset, version and project reads, download links and the usage form.

One Powertools resolver serves every route. Search reads the catalog file, `site/catalog.json`
in the derived bucket, checking its ETag at most once a minute. Dataset, version and file reads
come from the active catalog table, named by the active-catalog parameter and cached a minute.
With the embeddings module on, search also asks the vector index for the datasets nearest `q`.

Usage: python -m archive_backend.api <path> writes the OpenAPI spec.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, Protocol, cast
from urllib.parse import quote

import boto3
from aws_lambda_powertools.event_handler import APIGatewayRestResolver, Response
from aws_lambda_powertools.event_handler.exceptions import (
    BadRequestError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from aws_lambda_powertools.event_handler.openapi.params import Query
from aws_lambda_powertools.utilities.typing import LambdaContext
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import BaseModel
from pydantic import Field as PydanticField

from archive_backend import search as catalog_search
from archive_backend.catalog_file import KEY as CATALOG_KEY
from archive_backend.config import read_archive_config
from archive_backend.embeddings import Bedrock, embed, vector_attribute
from archive_backend.whoami import _groups
from archive_contract.usage import UsageAnswers

if TYPE_CHECKING:
    # Dev-only stubs: the Lambda asset is built without them.
    from mypy_boto3_s3 import S3Client

CACHE_SECONDS = 60
LINK_SECONDS = 300
MISSING = ("404", "NoSuchKey", "NotFound")
VECTOR_INDEX = "datasets"
NEAREST = 50

logger = logging.getLogger(__name__)


class DynamoDB(Protocol):
    """The DynamoDB calls the API makes (boto3-stubs has no dynamodb extra installed)."""

    def get_item(self, **kwargs: Any) -> dict[str, Any]: ...
    def query(self, **kwargs: Any) -> dict[str, Any]: ...
    def put_item(self, **kwargs: Any) -> dict[str, Any]: ...
    def update_item(self, **kwargs: Any) -> dict[str, Any]: ...
    def search_vectors(self, **kwargs: Any) -> dict[str, Any]: ...


class SSM(Protocol):
    def get_parameter(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Clients:
    s3: S3Client
    dynamodb: DynamoDB
    ssm: SSM
    bedrock: Bedrock


@cache
def clients() -> Clients:
    # A regional, SigV4 S3 client, so presigned links work in any region.
    s3_config = Config(signature_version="s3v4", s3={"addressing_style": "virtual"})
    return Clients(
        s3=boto3.client("s3", region_name=os.environ.get("AWS_REGION"), config=s3_config),
        dynamodb=cast(DynamoDB, boto3.client("dynamodb")),
        ssm=cast(SSM, boto3.client("ssm")),
        bedrock=cast(Bedrock, boto3.client("bedrock-runtime")),
    )


def _monotonic() -> float:
    return time.monotonic()


_catalog: dict[str, Any] = {}
_active: dict[str, Any] = {}


def reset_caches() -> None:
    _catalog.clear()
    _active.clear()


def _is_none(value: object) -> bool:
    return value is None


def _absent() -> Any:
    """An optional response field, left out when unset as the catalog file leaves it out."""
    return PydanticField(default=None, exclude_if=_is_none)


class CatalogRow(BaseModel):
    id: str
    version: int
    title: str
    access: str
    description: str | None = _absent()
    keywords: list[str] | None = _absent()
    licenses: list[str] | None = _absent()
    rightsStatus: str | None = _absent()
    project: str | None = _absent()
    creators: list[str] | None = _absent()
    formats: list[str] | None = _absent()
    start: str | None = _absent()
    end: str | None = _absent()
    ongoing: bool | None = _absent()
    bbox: list[float] | None = _absent()
    bytes: int | None = _absent()
    published: str | None = _absent()


class SearchAnswer(BaseModel):
    rows: list[CatalogRow]
    total: int
    facets: dict[str, dict[str, int]]


class FileEntry(BaseModel):
    path: str
    name: str | None = _absent()
    format: str | None = _absent()
    bytes: int | None = _absent()
    hash: str | None = _absent()


class VersionEntry(BaseModel):
    version: int
    prefix: str
    publishedAt: str | None = _absent()


class VersionsAnswer(BaseModel):
    versions: list[VersionEntry]


class VersionAnswer(VersionEntry):
    manifest: dict[str, Any]
    files: list[FileEntry]


class DatasetSummary(BaseModel):
    id: str
    title: str
    access: str
    currentVersion: int


class DatasetAnswer(DatasetSummary):
    prefix: str
    project: str | None = _absent()
    manifest: dict[str, Any]
    files: list[FileEntry]


class ProjectAnswer(BaseModel):
    project: dict[str, Any]
    datasets: list[DatasetSummary]


class DownloadAnswer(BaseModel):
    url: str


class UsageEntry(BaseModel):
    datasetId: str
    entry: str
    at: str
    organisation: str | None = _absent()
    purpose: str | None = _absent()
    note: str | None = _absent()


class UsageList(BaseModel):
    entries: list[UsageEntry]


app = APIGatewayRestResolver(enable_validation=True)


def _plain(item: dict[str, Any]) -> dict[str, Any]:
    """A DynamoDB item's string and number attributes as plain values."""
    plain: dict[str, Any] = {}
    for name, value in item.items():
        if "S" in value:
            plain[name] = value["S"]
        elif "N" in value:
            plain[name] = int(value["N"])
    return plain


def _sk(version: int) -> str:
    return f"V#{version:06d}"


def _now() -> datetime:
    return datetime.now(UTC)


def _claims() -> dict[str, Any] | None:
    context = app.current_event.raw_event.get("requestContext") or {}
    claims = (context.get("authorizer") or {}).get("claims")
    return claims if isinstance(claims, dict) and claims else None


def _signed_in() -> dict[str, Any]:
    claims = _claims()
    if claims is None:
        raise UnauthorizedError("sign in first")
    return claims


def _catalog_rows() -> list[dict[str, Any]]:
    now = _monotonic()
    if "rows" in _catalog and now - _catalog["checked"] < CACHE_SECONDS:
        rows: list[dict[str, Any]] = _catalog["rows"]
        return rows
    s3 = clients().s3
    bucket = os.environ["DERIVED_BUCKET"]
    try:
        etag = s3.head_object(Bucket=bucket, Key=CATALOG_KEY)["ETag"]
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") not in MISSING:
            raise
        _catalog.update(checked=now, etag=None, rows=[])
        return []
    if etag != _catalog.get("etag"):
        body = s3.get_object(Bucket=bucket, Key=CATALOG_KEY)["Body"].read()
        _catalog.update(etag=etag, rows=json.loads(body))
    _catalog["checked"] = now
    rows = _catalog["rows"]
    return rows


def _site_domain() -> str:
    """The CloudFront domain, from a parameter: an environment variable would make the
    distribution, the API that is its origin and this function depend on each other."""
    if "domain" not in _active:
        name = os.environ["SITE_DOMAIN_PARAMETER"]
        _active["domain"] = clients().ssm.get_parameter(Name=name)["Parameter"]["Value"]
    domain: str = _active["domain"]
    return domain


def _table() -> str:
    now = _monotonic()
    if "value" not in _active or now - _active["checked"] >= CACHE_SECONDS:
        name = os.environ["ACTIVE_CATALOG_PARAMETER"]
        value = clients().ssm.get_parameter(Name=name)["Parameter"]["Value"]
        if value not in ("A", "B"):
            raise RuntimeError(f"{name} names {value!r}, not A or B")
        _active.update(checked=now, value=value)
    return os.environ[f"CATALOG_TABLE_{_active['value']}"]


def _get(table: str, pk: str, sk: str) -> dict[str, Any] | None:
    item = (
        clients()
        .dynamodb.get_item(TableName=table, Key={"PK": {"S": pk}, "SK": {"S": sk}})
        .get("Item")
    )
    return cast(dict[str, Any], item) if item else None


def _query(**kwargs: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    while True:
        page = clients().dynamodb.query(**kwargs)
        items.extend(page.get("Items", []))
        last = page.get("LastEvaluatedKey")
        if not last:
            return items
        kwargs["ExclusiveStartKey"] = last


def _meta(table: str, dataset_id: str) -> dict[str, Any]:
    item = _get(table, f"DATASET#{dataset_id}", "META")
    if item is None:
        raise NotFoundError(f"no dataset {dataset_id}")
    return _plain(item)


def _version_item(table: str, dataset_id: str, version: int) -> dict[str, Any]:
    item = _get(table, f"DATASET#{dataset_id}", _sk(version))
    if item is None:
        raise NotFoundError(f"no version {version} of {dataset_id}")
    return _plain(item)


def _files(table: str, dataset_id: str, version: int) -> list[FileEntry]:
    items = _query(
        TableName=table,
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        ExpressionAttributeValues={
            ":pk": {"S": f"DATASET#{dataset_id}"},
            ":sk": {"S": f"{_sk(version)}#FILE#"},
        },
    )
    return [FileEntry.model_validate(_plain(item)) for item in items]


def _version(table: str, dataset_id: str, version: int) -> VersionAnswer:
    item = _version_item(table, dataset_id, version)
    return VersionAnswer(
        version=item["version"],
        prefix=item["prefix"],
        publishedAt=item.get("publishedAt"),
        manifest=json.loads(item["manifest"]),
        files=_files(table, dataset_id, version),
    )


def embeddings_enabled() -> bool:
    """Whether the archive config switches the embeddings module on, read at most once a minute."""
    now = _monotonic()
    if "embeddings" not in _active or now - _active["embeddings_checked"] >= CACHE_SECONDS:
        cfg = read_archive_config(clients().ssm, os.environ["ARCHIVE_CONFIG_PARAMETER"])
        on = cfg.infrastructure is not None and cfg.infrastructure.modules.embeddings is not None
        _active.update(embeddings=on, embeddings_checked=now)
    enabled: bool = _active["embeddings"]
    return enabled


def _fallback_metric() -> None:
    """One `SemanticFallback` count, in CloudWatch embedded metric format on stdout."""
    print(
        json.dumps(
            {
                "_aws": {
                    "Timestamp": int(time.time() * 1000),
                    "CloudWatchMetrics": [
                        {
                            "Namespace": "ResearchArchive",
                            "Dimensions": [["Stage"]],
                            "Metrics": [{"Name": "SemanticFallback", "Unit": "Count"}],
                        }
                    ],
                },
                "Stage": os.environ.get("STAGE", "unknown"),
                "SemanticFallback": 1,
            }
        ),
        flush=True,
    )


def _nearest(q: str) -> list[str] | None:
    """The ids of the datasets nearest `q` in the vector index, or None when the module is off
    or any part of the semantic path, the config read included, fails."""
    c = clients()
    try:
        if not embeddings_enabled():
            return None
        vector = embed(c.bedrock, q)
        found = c.dynamodb.search_vectors(
            TableName=_table(),
            IndexName=VECTOR_INDEX,
            SearchVector=vector_attribute(vector),
            TopK=NEAREST,
        )
        pks = [result["Item"]["PK"]["S"] for result in found.get("SearchResults", [])]
    except Exception as error:
        logger.warning("semantic search failed, answering keyword results: %r", error)
        _fallback_metric()
        return None
    return [pk.removeprefix("DATASET#") for pk in pks if pk.startswith("DATASET#")]


def _bbox(value: str | None) -> catalog_search.Box | None:
    if value is None:
        return None
    try:
        west, south, east, north = (float(part) for part in value.split(","))
    except ValueError:
        raise BadRequestError("bbox is west,south,east,north") from None
    if south > north:
        raise BadRequestError("bbox south is above north")
    return west, south, east, north


@app.get("/api/search")
def search_datasets(
    q: Annotated[str | None, Query()] = None,
    access: Annotated[list[str] | None, Query()] = None,
    license: Annotated[list[str] | None, Query()] = None,
    format: Annotated[list[str] | None, Query()] = None,
    project: Annotated[list[str] | None, Query()] = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: Annotated[date | None, Query()] = None,
    bbox: Annotated[str | None, Query(description="west,south,east,north")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> SearchAnswer:
    query = catalog_search.SearchQuery(
        q=q,
        access=access or [],
        license=license or [],
        format=format or [],
        project=project or [],
        from_=from_,
        to=to,
        bbox=_bbox(bbox),
        page=page,
        size=size,
    )
    semantic = _nearest(q) if q and q.strip() else None
    result = catalog_search.search(_catalog_rows(), query, semantic)
    return SearchAnswer(
        rows=[CatalogRow.model_validate(row) for row in result.rows],
        total=result.total,
        facets=result.facets,
    )


@app.get("/api/datasets/<id>")
def get_dataset(id: str) -> DatasetAnswer:
    table = _table()
    meta = _meta(table, id)
    current = _version(table, id, meta["currentVersion"])
    return DatasetAnswer(
        id=meta["id"],
        title=meta["title"],
        access=meta["access"],
        currentVersion=meta["currentVersion"],
        prefix=meta["prefix"],
        project=meta.get("project"),
        manifest=current.manifest,
        files=current.files,
    )


@app.get("/api/datasets/<id>/versions")
def list_versions(id: str) -> VersionsAnswer:
    table = _table()
    _meta(table, id)
    items = _query(
        TableName=table,
        KeyConditionExpression="PK = :pk AND begins_with(SK, :sk)",
        FilterExpression="attribute_exists(#v)",
        ProjectionExpression="#v, prefix, publishedAt",
        ExpressionAttributeNames={"#v": "version"},
        ExpressionAttributeValues={":pk": {"S": f"DATASET#{id}"}, ":sk": {"S": "V#"}},
    )
    versions = [VersionEntry.model_validate(_plain(item)) for item in items]
    return VersionsAnswer(versions=sorted(versions, key=lambda v: v.version))


@app.get("/api/datasets/<id>/versions/<version>")
def get_version(id: str, version: int) -> VersionAnswer:
    return _version(_table(), id, version)


@app.get("/api/projects/<id>")
def get_project(id: str) -> ProjectAnswer:
    try:
        body = (
            clients()
            .s3.get_object(Bucket=os.environ["ARCHIVE_BUCKET"], Key=f"projects/{id}/project.json")[
                "Body"
            ]
            .read()
        )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in MISSING:
            raise NotFoundError(f"no project {id}") from None
        raise
    items = _query(
        TableName=_table(),
        IndexName="GSI1",
        KeyConditionExpression="GSI1PK = :pk",
        ExpressionAttributeValues={":pk": {"S": f"PROJECT#{id}"}},
    )
    datasets = [DatasetSummary.model_validate(_plain(item)) for item in items]
    return ProjectAnswer(project=json.loads(body), datasets=sorted(datasets, key=lambda d: d.id))


@app.get("/api/datasets/<id>/versions/<version>/download")
def download_link(id: str, version: int, path: Annotated[str, Query()]) -> DownloadAnswer:
    _signed_in()
    table = _table()
    meta = _meta(table, id)
    _version_item(table, id, version)
    access = meta["access"]
    if access == "by-request":
        raise ForbiddenError("this dataset is shared by request")
    if access not in ("open", "restricted"):
        raise NotFoundError("this dataset has no files")
    if _get(table, f"DATASET#{id}", f"{_sk(version)}#FILE#{path}") is None:
        raise NotFoundError(f"no file {path} in version {version} of {id}")
    if access == "open":
        data = quote(f"{id}/{version}/{path}", safe="/")
        return DownloadAnswer(url=f"https://{_site_domain()}/data/{data}")
    c = clients()
    url = c.s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": os.environ["ARCHIVE_BUCKET"], "Key": f"restricted/{id}/{version}/{path}"},
        ExpiresIn=LINK_SECONDS,
    )
    c.dynamodb.update_item(
        TableName=os.environ["DOWNLOAD_COUNTS_TABLE"],
        Key={"datasetId": {"S": id}, "month": {"S": _now().strftime("%Y-%m")}},
        UpdateExpression="ADD #n :one",
        ExpressionAttributeNames={"#n": "restricted"},
        ExpressionAttributeValues={":one": {"N": "1"}},
    )
    return DownloadAnswer(url=url)


@app.post("/api/datasets/<id>/usage", responses={204: {"description": "Stored"}})
def record_usage(id: str, answers: UsageAnswers) -> Response[None]:
    _meta(_table(), id)
    now = _now()
    item: dict[str, Any] = {
        "datasetId": {"S": id},
        "entry": {"S": f"{now.strftime('%Y-%m')}#{uuid.uuid4()}"},
        "at": {"S": now.strftime("%Y-%m-%dT%H:%M:%SZ")},
    }
    for name, value in answers.model_dump(exclude_none=True).items():
        item[name] = {"S": value}
    clients().dynamodb.put_item(TableName=os.environ["USAGE_TABLE"], Item=item)
    return Response(status_code=204, body=None)


@app.get("/api/admin/usage")
def list_usage(dataset: Annotated[str, Query()]) -> UsageList:
    if "admin" not in _groups(_signed_in().get("cognito:groups")):
        raise ForbiddenError("admins only")
    items = _query(
        TableName=os.environ["USAGE_TABLE"],
        KeyConditionExpression="datasetId = :pk",
        ExpressionAttributeValues={":pk": {"S": dataset}},
        ScanIndexForward=False,
    )
    entries = [UsageEntry.model_validate(_plain(item)) for item in items]
    # The sort key is `<month>#<uuid>`, so within a month only `at` gives the order.
    return UsageList(entries=sorted(entries, key=lambda e: e.at, reverse=True))


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    return app.resolve(event, cast(LambdaContext, context))


def render() -> str:
    spec = json.loads(app.get_openapi_json_schema(title="Research archive API", version="0.1.0"))
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Write the read API's OpenAPI spec.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args(argv)
    args.path.write_text(render())


if __name__ == "__main__":
    main()
