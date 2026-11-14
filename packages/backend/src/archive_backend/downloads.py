"""The daily download rollup: CloudFront's open downloads into DownloadCounts, each day once.

CloudFront writes standard logs to the derived bucket's `logs/` as gzip files named
`<distribution>.<YYYY-MM-DD-HH>.<id>.gz`, possibly hours after the day ends, so the rollup counts
through two days ago. A download is a `GET` under `/data/<datasetId>/` that answered 200; range
reads (206) and `HEAD` don't count. Each day's counts are added, then the day is written to the
Settings item `downloads-rolled-up-through`, so a rerun reads only days not yet marked. Each
increment also adds the day to the item's `countedDays` set on condition the day isn't there, so
a run that stops before marking the day, or two runs that overlap, count each dataset's day once.
"""

from __future__ import annotations

import gzip
import os
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol, cast

import boto3
from botocore.exceptions import ClientError

if TYPE_CHECKING:
    # Dev-only stubs: the Lambda asset is built without them.
    from mypy_boto3_s3 import S3Client

LOGS = "logs/"
MARK = "downloads-rolled-up-through"
LAG_DAYS = 2
# CloudFront's standard log columns, used when a file has no #Fields line.
DEFAULT_FIELDS = ["date", "time", "x-edge-location", "sc-bytes", "c-ip", "cs-method", "cs(Host)"]
DEFAULT_FIELDS += ["cs-uri-stem", "sc-status"]


class DynamoDB(Protocol):
    def get_item(self, **kwargs: Any) -> dict[str, Any]: ...
    def put_item(self, **kwargs: Any) -> dict[str, Any]: ...
    def update_item(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Clients:
    s3: S3Client
    dynamodb: DynamoDB


def clients() -> Clients:
    return Clients(s3=boto3.client("s3"), dynamodb=cast(DynamoDB, boto3.client("dynamodb")))


def _today() -> date:
    return datetime.now(UTC).date()


def count_log(text: str) -> Counter[str]:
    """Open downloads per dataset in one log file's text."""
    fields = DEFAULT_FIELDS
    counts: Counter[str] = Counter()
    for line in text.splitlines():
        if line.startswith("#Fields:"):
            fields = line.split()[1:]
            continue
        if not line or line.startswith("#"):
            continue
        row = dict(zip(fields, line.split("\t"), strict=False))
        stem = row.get("cs-uri-stem", "")
        if row.get("cs-method") != "GET" or row.get("sc-status") != "200":
            continue
        if not stem.startswith("/data/"):
            continue
        dataset_id = stem.split("/")[2]
        if dataset_id:
            counts[dataset_id] += 1
    return counts


def _log_keys(s3: S3Client, bucket: str) -> list[str]:
    keys: list[str] = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=LOGS):
        keys.extend(item.get("Key", "") for item in page.get("Contents", []))
    return keys


def _days(last: str | None, through: date) -> list[date]:
    start = date.fromisoformat(last) + timedelta(days=1) if last else _today() - timedelta(LAG_DAYS)
    return [start + timedelta(n) for n in range((through - start).days + 1)]


def _add(c: Clients, table: str, dataset_id: str, day: date, count: int) -> None:
    """Add one dataset's count for a day, unless that day is already in its `countedDays`."""
    try:
        c.dynamodb.update_item(
            TableName=table,
            Key={"datasetId": {"S": dataset_id}, "month": {"S": day.strftime("%Y-%m")}},
            UpdateExpression="ADD #n :count, countedDays :days",
            ConditionExpression=(
                "attribute_not_exists(countedDays) OR NOT contains(countedDays, :day)"
            ),
            ExpressionAttributeNames={"#n": "open"},
            ExpressionAttributeValues={
                ":count": {"N": str(count)},
                ":days": {"SS": [day.isoformat()]},
                ":day": {"S": day.isoformat()},
            },
        )
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise


def run(event: dict[str, Any], c: Clients) -> dict[str, Any]:
    bucket = os.environ["DERIVED_BUCKET"]
    counts_table = os.environ["DOWNLOAD_COUNTS_TABLE"]
    settings = os.environ["SETTINGS_TABLE"]
    key = {"name": {"S": MARK}}

    item = c.dynamodb.get_item(TableName=settings, Key=key, ConsistentRead=True).get("Item")
    last = item["value"]["S"] if item else None
    through = (
        date.fromisoformat(event["through"])
        if event.get("through")
        else _today() - timedelta(LAG_DAYS)
    )
    days = _days(last, through)
    keys = _log_keys(c.s3, bucket) if days else []

    counted = 0
    for day in days:
        marker = f".{day.isoformat()}-"
        counts: Counter[str] = Counter()
        for log in (k for k in keys if marker in k):
            body = c.s3.get_object(Bucket=bucket, Key=log)["Body"].read()
            counts += count_log(gzip.decompress(body).decode("utf-8", errors="replace"))
        for dataset_id, count in sorted(counts.items()):
            _add(c, counts_table, dataset_id, day, count)
        c.dynamodb.put_item(TableName=settings, Item={**key, "value": {"S": day.isoformat()}})
        counted += sum(counts.values())

    return {"days": [d.isoformat() for d in days], "counted": counted}


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    return run(event or {}, clients())
