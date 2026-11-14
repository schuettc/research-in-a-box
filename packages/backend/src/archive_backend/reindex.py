"""The reindex: rebuild the inactive catalog table from the archive's manifests, then flip to it.

A published version sits at `<open|restricted>/<datasetId>/<version>/` with `datapackage.json`
at its root. The durable handler empties the inactive table, writes every manifest's catalog
items as DynamoDB JSON lines under the derived bucket's `reindex/<run>/data/`, bulk-loads them
into that table, waits for the load to end, and flips the active-catalog parameter only when the
load ends COMPLETED, then rewrites the catalog file from the table it flipped to. Every stage is
a checkpointed step, so a replay never repeats one.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol, cast

import boto3
from aws_durable_execution_sdk_python import (
    DurableContext,
    StepContext,
    durable_execution,
    durable_step,
)
from aws_durable_execution_sdk_python.config import Duration
from aws_durable_execution_sdk_python.waits import (
    WaitForConditionConfig,
    WaitForConditionDecision,
)

from archive_backend.catalog_file import write_catalog_file
from archive_contract.manifest import Manifest

if TYPE_CHECKING:
    # Dev-only stubs: the Lambda asset is built without them.
    from mypy_boto3_s3 import S3Client
    from mypy_boto3_sns import SNSClient

MANIFEST = "datapackage.json"
PREFIXES = ("open", "restricted")
BATCH = 200
DELETE_BATCH = 25
RUNNING = ("IN_PROGRESS", "CANCELLING")


class DynamoDB(Protocol):
    """The DynamoDB calls the reindex makes (boto3-stubs has no dynamodb extra installed)."""

    def scan(self, **kwargs: Any) -> dict[str, Any]: ...
    def batch_write_item(self, **kwargs: Any) -> dict[str, Any]: ...
    def start_bulk_put_items(self, **kwargs: Any) -> dict[str, Any]: ...
    def describe_bulk_operation(self, **kwargs: Any) -> dict[str, Any]: ...


class SSM(Protocol):
    def get_parameter(self, **kwargs: Any) -> dict[str, Any]: ...
    def put_parameter(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Clients:
    s3: S3Client
    dynamodb: DynamoDB
    ssm: SSM
    sns: SNSClient


def clients() -> Clients:
    return Clients(
        s3=boto3.client("s3"),
        dynamodb=cast(DynamoDB, boto3.client("dynamodb")),
        ssm=cast(SSM, boto3.client("ssm")),
        sns=boto3.client("sns"),
    )


def _s(value: Any) -> dict[str, str]:
    return {"S": str(value)}


def _n(value: int) -> dict[str, str]:
    return {"N": str(value)}


def _sk(version: int) -> str:
    return f"V#{version:06d}"


def _paths(path: Any) -> list[str]:
    if isinstance(path, str):
        return [path]
    if isinstance(path, list):
        return [p for p in path if isinstance(p, str)]
    return []


def _file_item(
    pk: str, sk: str, path: str, name: Any, fmt: Any, size: Any, digest: Any
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "PK": _s(pk),
        "SK": _s(f"{sk}#FILE#{path}"),
        "path": _s(path),
        "name": _s(name),
    }
    if fmt is not None:
        item["format"] = _s(fmt)
    if isinstance(size, int):
        item["bytes"] = _n(size)
    if digest is not None:
        item["hash"] = _s(digest)
    return item


def _published(manifest: dict[str, Any]) -> str | None:
    """`archive:published` read through the contract's field, as UTC to the second.

    Only that field is validated, so a manifest the current contract would refuse elsewhere
    still reindexes.
    """
    field = Manifest.model_validate({"archive:published": manifest.get("archive:published")})
    if field.published is None:
        return None
    when = field.published
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def catalog_items(
    prefix: str, dataset_id: str, version: int, manifest_text: str
) -> list[dict[str, Any]]:
    """The version item and one file item per resource path and `archive:files` member.

    The version item carries the manifest's `archive:published` as `publishedAt` when it has one.
    """
    manifest = json.loads(manifest_text)
    pk = f"DATASET#{dataset_id}"
    sk = _sk(version)
    version_item: dict[str, Any] = {
        "PK": _s(pk),
        "SK": _s(sk),
        "version": _n(version),
        "prefix": _s(prefix),
        "manifest": _s(manifest_text),
    }
    published = _published(manifest)
    if published:
        version_item["publishedAt"] = _s(published)
    items: list[dict[str, Any]] = [version_item]
    files: dict[str, dict[str, Any]] = {}
    for resource in manifest.get("resources") or []:
        name, fmt = resource.get("name"), resource.get("format")
        for path in _paths(resource.get("path")):
            files[path] = _file_item(
                pk, sk, path, name, fmt, resource.get("bytes"), resource.get("hash")
            )
        for member in resource.get("archive:files") or []:
            path = member.get("path")
            if isinstance(path, str):
                files[path] = _file_item(
                    pk, sk, path, name, fmt, member.get("bytes"), member.get("hash")
                )
    items.extend(files.values())
    return items


def dataset_item(
    dataset_id: str, versions: list[tuple[str, int, dict[str, Any]]]
) -> dict[str, Any]:
    """The dataset item, from the highest of one dataset's `(prefix, version, manifest)`.

    It keys on the folder's dataset id, as the version and file items do, never on the
    manifest's `id`, so all of a dataset's items share one partition.
    """
    prefix, version, manifest = max(versions, key=lambda v: v[1])
    item: dict[str, Any] = {
        "PK": _s(f"DATASET#{dataset_id}"),
        "SK": _s("META"),
        "id": _s(dataset_id),
        "title": _s(manifest.get("title") or dataset_id),
        "access": _s(manifest.get("archive:access") or "open"),
        "currentVersion": _n(version),
        "prefix": _s(prefix),
    }
    project = manifest.get("archive:project")
    if project:
        item["project"] = _s(project)
        item["GSI1PK"] = _s(f"PROJECT#{project}")
        item["GSI1SK"] = _s(f"DATASET#{dataset_id}")
    return item


def to_lines(items: list[dict[str, Any]]) -> str:
    """Bulk put items input: one `{"Item": {...}}` per line, newline-terminated."""
    return "".join(json.dumps({"Item": item}) + "\n" for item in items)


def _parts(key: str) -> tuple[str, str, int] | None:
    parts = key.split("/")
    if len(parts) != 4 or parts[0] not in PREFIXES or parts[3] != MANIFEST:
        return None
    if not parts[1] or not parts[2].isdigit():
        return None
    return parts[0], parts[1], int(parts[2])


def manifest_keys(s3: S3Client, bucket: str) -> list[str]:
    """Every `<open|restricted>/<datasetId>/<version>/datapackage.json`, sorted."""
    paginator = s3.get_paginator("list_objects_v2")
    keys: list[str] = []
    for prefix in PREFIXES:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix + "/"):
            for item in page.get("Contents", []):
                key = item.get("Key", "")
                if _parts(key):
                    keys.append(key)
    return sorted(keys)


@durable_step
def _list(_: StepContext, c: Clients, archive: str) -> list[str]:
    return manifest_keys(c.s3, archive)


def _batches(keys: list[str]) -> list[list[str]]:
    """Batches of at most BATCH keys that never split a dataset; a bigger dataset stands alone."""
    by_dataset: dict[str, list[str]] = {}
    for key in keys:
        parts = _parts(key)
        if parts:
            by_dataset.setdefault(parts[1], []).append(key)
    batches: list[list[str]] = []
    current: list[str] = []
    for dataset_id in sorted(by_dataset):
        group = by_dataset[dataset_id]
        if current and len(current) + len(group) > BATCH:
            batches.append(current)
            current = []
        current.extend(group)
    if current:
        batches.append(current)
    return batches


@durable_step
def _write(
    _: StepContext, c: Clients, archive: str, derived: str, run: str, n: int, keys: list[str]
) -> int:
    items: list[dict[str, Any]] = []
    versions: dict[str, list[tuple[str, int, dict[str, Any]]]] = {}
    for key in keys:
        parts = _parts(key)
        if not parts:
            continue
        prefix, dataset_id, version = parts
        text = c.s3.get_object(Bucket=archive, Key=key)["Body"].read().decode("utf-8")
        items.extend(catalog_items(prefix, dataset_id, version, text))
        versions.setdefault(dataset_id, []).append((prefix, version, json.loads(text)))
    items.extend(dataset_item(d, v) for d, v in versions.items())
    c.s3.put_object(
        Bucket=derived,
        Key=f"reindex/{run}/data/part-{n:05d}.json",
        Body=to_lines(items).encode("utf-8"),
    )
    return len(items)


@durable_step
def _empty_page(
    _: StepContext, c: Clients, table: str, start: dict[str, Any] | None
) -> dict[str, Any] | None:
    scan: dict[str, Any] = {
        "TableName": table,
        "ProjectionExpression": "#pk, #sk",
        "ExpressionAttributeNames": {"#pk": "PK", "#sk": "SK"},
    }
    if start:
        scan["ExclusiveStartKey"] = start
    page = c.dynamodb.scan(**scan)
    keys = page.get("Items", [])
    for i in range(0, len(keys), DELETE_BATCH):
        requests: dict[str, Any] = {
            table: [{"DeleteRequest": {"Key": k}} for k in keys[i : i + DELETE_BATCH]]
        }
        attempt = 0
        while requests:
            if attempt:
                time.sleep(min(0.05 * 2**attempt, 5))
            requests = c.dynamodb.batch_write_item(RequestItems=requests).get(
                "UnprocessedItems", {}
            )
            attempt += 1
    last: dict[str, Any] | None = page.get("LastEvaluatedKey")
    return last


def _until_ended(state: dict[str, Any], attempt: int) -> WaitForConditionDecision:
    if state["status"] not in RUNNING:
        return WaitForConditionDecision.stop_polling()
    return WaitForConditionDecision.continue_waiting(Duration.from_seconds(min(30 * attempt, 300)))


def run(event: dict[str, Any], context: DurableContext) -> dict[str, Any]:
    """Empty, write, load, wait and flip, each a checkpointed step."""
    c = clients()
    archive = os.environ["ARCHIVE_BUCKET"]
    derived = os.environ["DERIVED_BUCKET"]
    tables = {"A": os.environ["CATALOG_TABLE_A"], "B": os.environ["CATALOG_TABLE_B"]}
    parameter = os.environ["ACTIVE_CATALOG_PARAMETER"]
    topic = os.environ["ALERT_TOPIC_ARN"]

    def start(_: object) -> dict[str, str]:
        active = c.ssm.get_parameter(Name=parameter)["Parameter"]["Value"]
        return {"run": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"), "active": active}

    begun = context.step(start, name="start")
    run_id: str = begun["run"]
    target = "A" if begun["active"] == "B" else "B"
    table = tables[target]

    page: dict[str, Any] | None = None
    while True:
        page = context.step(_empty_page(c, table, page), name="empty")
        if not page:
            break

    keys = context.step(_list(c, archive), name="list")

    count = 0
    for n, batch in enumerate(_batches(keys)):
        count += context.step(
            _write(c, archive, derived, run_id, n, batch),
            name=f"write-{n}",
        )

    status = "COMPLETED"
    if keys:
        data = f"reindex/{run_id}/data/"
        report = f"reindex/{run_id}/report/"

        def load(_: object) -> str:
            started = c.dynamodb.start_bulk_put_items(
                TableName=table,
                InputS3Configuration={
                    "S3Bucket": derived,
                    "S3KeyPrefix": data,
                    "InputFormat": "DYNAMODB_JSON",
                },
                OutputS3Configuration={
                    "S3Bucket": derived,
                    "S3KeyPrefix": report,
                    "OutputType": ["ERROR"],
                },
                PerformanceTier="STANDARD",
                ClientToken=run_id,
            )
            arn: str = started["BulkOperationDescription"]["BulkOperationArn"]
            return arn

        operation = context.step(load, name="load")

        def check(state: dict[str, Any], _: object) -> dict[str, Any]:
            described = c.dynamodb.describe_bulk_operation(BulkOperationArn=operation)
            d = described["BulkOperationDescription"]
            return {
                "status": d["BulkOperationStatus"],
                "processed": d.get("ProcessedItemCount", 0),
                "failed": d.get("FailedItemCount", 0),
            }

        ended = context.wait_for_condition(
            check,
            WaitForConditionConfig(
                wait_strategy=_until_ended,
                initial_state={"status": "IN_PROGRESS", "processed": 0, "failed": 0},
            ),
            name="wait-load",
        )
        status = str(ended["status"])

    flipped = status == "COMPLETED"
    rows: int | None = None
    if flipped:

        def flip(_: object) -> None:
            c.ssm.put_parameter(Name=parameter, Value=target, Overwrite=True)

        context.step(flip, name="flip")

        def catalog(_: object) -> dict[str, Any]:
            try:
                return {"rows": write_catalog_file(table, derived, dynamodb=c.dynamodb, s3=c.s3)}
            except Exception as error:
                return {"error": f"{type(error).__name__}: {error}"}

        written = context.step(catalog, name="catalog")
        rows = written.get("rows")
        if "error" in written:
            subject = f"Reindex {run_id} could not write the catalog file"
            error = str(written["error"])

            def catalog_alert(_: object) -> None:
                c.sns.publish(
                    TopicArn=topic,
                    Subject=subject[:100],
                    Message=f"Reindex {run_id} flipped to {target} but writing "
                    f"s3://{derived}/site/catalog.json failed: {error}",
                )

            context.step(catalog_alert, name="alert")
    else:
        subject = f"Reindex {run_id} on {target} ended {status}"

        def alert(_: object) -> None:
            c.sns.publish(
                TopicArn=topic,
                Subject=subject[:100],
                Message=f"{subject}. Report: s3://{derived}/reindex/{run_id}/report/",
            )

        context.step(alert, name="alert")

    return {
        "run": run_id,
        "target": target,
        "status": status,
        "items": count,
        "flipped": flipped,
        "catalog": rows,
    }


handler = durable_execution(run)
