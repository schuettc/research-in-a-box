"""The ingest: one durable execution per submission, named by its id, from submit to its end.

Each round is scanned (GuardDuty's tag on every file), checked (`cruise.diagnose` under the
archive config), held (copied to `held/<id>/`, which never expires) and matched against the
review policy, read once. A round under review waits on a curator's callback, reminding and
marking stale on the policy's days; a blocked round or a request for changes waits 30 days on
the contributor's resubmit callback. Every wait is capped to end by 360 days after the start,
so a submission still open then ends itself as `expired` before the platform's one-year
execution timeout ends it without a word. Every call that reads the clock, the network or a random
value runs inside a named step, every status change writes its event in the same step, and a
step that fails after its retries ends the submission as `failed` with an admin alert.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast, get_args

import boto3
from aws_durable_execution_sdk_python import (
    DurableContext,
    StepContext,
    durable_execution,
    durable_step,
)
from aws_durable_execution_sdk_python.config import Duration, WaitForCallbackConfig
from aws_durable_execution_sdk_python.exceptions import (
    CallbackTimeoutError,
    DurableOperationError,
)
from aws_durable_execution_sdk_python.waits import (
    WaitForConditionConfig,
    WaitForConditionDecision,
)

from archive_backend.submissions import Table, put_event, stored_policy
from archive_contract import SubmissionFacts, match, reminder_schedule
from archive_contract.config import ArchiveConfig
from archive_contract.findings import Finding, Target
from archive_contract.manifest import AccessLevel
from cruise.diagnose import diagnose

DAY = 86400
RESUBMIT_DAYS = 30
EXPIRY_DAYS = 360
SCAN_TAG = "GuardDutyMalwareScanStatus"
CLEAN = "NO_THREATS_FOUND"
MANIFEST = "datapackage.json"
THEMES = "archive:themes"
PIPELINE = "pipeline"
ALL = "all"
MAX_SCAN_DELAY = 3600
DELETE_BATCH = 1000


class S3(Protocol):
    def get_object_tagging(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_object(self, **kwargs: Any) -> dict[str, Any]: ...
    def put_object(self, **kwargs: Any) -> Any: ...
    def copy_object(self, **kwargs: Any) -> Any: ...
    def get_paginator(self, name: str) -> Any: ...
    def delete_objects(self, **kwargs: Any) -> Any: ...


class SNS(Protocol):
    def publish(self, **kwargs: Any) -> Any: ...


class SSM(Protocol):
    def get_parameter(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Clients:
    s3: S3
    sns: SNS
    ssm: SSM
    submissions: Table
    reviews: Table
    settings: Table


@dataclass(frozen=True)
class Env:
    submissions_table: str
    reviews_table: str
    settings_table: str
    staging_bucket: str
    curator_topic_arn: str
    alert_topic_arn: str
    archive_config_parameter: str

    @classmethod
    def from_environ(cls) -> Env:
        return cls(
            submissions_table=os.environ["SUBMISSIONS_TABLE"],
            reviews_table=os.environ["REVIEWS_TABLE"],
            settings_table=os.environ["SETTINGS_TABLE"],
            staging_bucket=os.environ["STAGING_BUCKET"],
            curator_topic_arn=os.environ["CURATOR_TOPIC_ARN"],
            alert_topic_arn=os.environ["ALERT_TOPIC_ARN"],
            archive_config_parameter=os.environ["ARCHIVE_CONFIG_PARAMETER"],
        )


def clients(env: Env) -> Clients:
    dynamodb = boto3.resource("dynamodb")

    def table(name: str) -> Table:
        return cast(Table, dynamodb.Table(name))

    return Clients(
        s3=cast(S3, boto3.client("s3")),
        sns=cast(SNS, boto3.client("sns")),
        ssm=cast(SSM, boto3.client("ssm")),
        submissions=table(env.submissions_table),
        reviews=table(env.reviews_table),
        settings=table(env.settings_table),
    )


def _clock() -> datetime:
    return datetime.now(UTC)


class BadCallback(Exception):
    """A callback result the pipeline can't act on."""


class Expired(Exception):
    """The submission reached its 360 days still open."""


def _set(c: Clients, sid: str, fields: dict[str, Any], remove: tuple[str, ...] = ()) -> None:
    """Set and remove attributes on a submission."""
    names = {f"#f{i}": name for i, name in enumerate(fields)}
    names.update({f"#r{i}": name for i, name in enumerate(remove)})
    parts = []
    if fields:
        parts.append("SET " + ", ".join(f"#f{i} = :f{i}" for i in range(len(fields))))
    if remove:
        parts.append("REMOVE " + ", ".join(f"#r{i}" for i in range(len(remove))))
    update: dict[str, Any] = {
        "Key": {"submissionId": sid},
        "UpdateExpression": " ".join(parts),
        "ExpressionAttributeNames": names,
    }
    if fields:
        update["ExpressionAttributeValues"] = {
            f":f{i}": value for i, value in enumerate(fields.values())
        }
    c.submissions.update_item(**update)


def _submission(c: Clients, sid: str) -> dict[str, Any]:
    item = c.submissions.get_item(Key={"submissionId": sid}).get("Item")
    if item is None:
        raise KeyError(f"no submission {sid}")
    return cast(dict[str, Any], item)


def _incoming(sid: str, round: int, path: str) -> str:
    return f"incoming/{sid}/{round}/{path}"


def _delete_prefix(c: Clients, env: Env, prefix: str) -> None:
    keys: list[str] = []
    for page in c.s3.get_paginator("list_objects_v2").paginate(
        Bucket=env.staging_bucket, Prefix=prefix
    ):
        keys.extend(item["Key"] for item in page.get("Contents", []))
    for i in range(0, len(keys), DELETE_BATCH):
        c.s3.delete_objects(
            Bucket=env.staging_bucket,
            Delete={"Objects": [{"Key": k} for k in keys[i : i + DELETE_BATCH]], "Quiet": True},
        )


def _notify(c: Clients, env: Env, audience: str, subject: str, message: str) -> None:
    """A message on the curators' topic, for one named reviewer or `all` curators."""
    c.sns.publish(
        TopicArn=env.curator_topic_arn,
        Subject=subject[:100],
        Message=message,
        MessageAttributes={"audience": {"DataType": "String", "StringValue": audience}},
    )


def _alert(c: Clients, env: Env, subject: str, message: str) -> None:
    c.sns.publish(TopicArn=env.alert_topic_arn, Subject=subject[:100], Message=message)


def _payload(result: Any) -> dict[str, Any]:
    """A callback's result: the SDK passes the sent JSON through as text."""
    if isinstance(result, bytes | str):
        result = json.loads(result)
    if not isinstance(result, dict):
        raise BadCallback(f"callback result is not an object: {result!r}")
    return result


@durable_step
def _start(_: StepContext, c: Clients, sid: str) -> dict[str, Any]:
    return {"round": int(_submission(c, sid)["round"]), "startedAt": _clock().isoformat()}


@durable_step
def _left(_: StepContext, started: str) -> int:
    """Seconds until the submission's 360 days are up."""
    end = datetime.fromisoformat(started) + timedelta(days=EXPIRY_DAYS)
    return int((end - _clock()).total_seconds())


@durable_step
def _files(_: StepContext, c: Clients, sid: str, round: int) -> list[str]:
    files = (_submission(c, sid).get("files") or {}).get(str(round)) or []
    return [str(f["path"]) for f in files]


@durable_step
def _scanned(_: StepContext, c: Clients, sid: str, round: int, tags: dict[str, str]) -> None:
    threats = {path: status for path, status in sorted(tags.items()) if status != CLEAN}
    put_event(c.reviews, sid, "scanned", PIPELINE, round, files=len(tags), threats=threats)


def _scan_findings(tags: dict[str, str]) -> list[Finding]:
    return [
        Finding(
            rule_id=f"scan.{status}",
            severity="error",
            message=f"The malware scan of {path} ended {status}.",
            target=Target(path=path),
        )
        for path, status in sorted(tags.items())
        if status != CLEAN
    ]


def _download(c: Clients, env: Env, sid: str, round: int, paths: list[str], into: Path) -> None:
    for path in paths:
        target = into / path
        target.parent.mkdir(parents=True, exist_ok=True)
        body = c.s3.get_object(Bucket=env.staging_bucket, Key=_incoming(sid, round, path))["Body"]
        with target.open("wb") as stream:
            shutil.copyfileobj(body, stream)


def _facts(manifest: dict[str, Any]) -> dict[str, Any]:
    access = manifest.get("archive:access")
    themes = manifest.get(THEMES)
    return {
        "title": str(manifest.get("title") or ""),
        "access": access if access in get_args(AccessLevel) else "open",
        "themes": [t for t in themes if isinstance(t, str)] if isinstance(themes, list) else [],
    }


@durable_step
def _check(
    _: StepContext,
    c: Clients,
    env: Env,
    sid: str,
    round: int,
    paths: list[str],
    tags: dict[str, str],
) -> dict[str, Any]:
    """Diagnose the round (unless the scan blocked it), store the report, block on an error."""
    report: dict[str, Any] = {"round": round, "validation": None, "quality": None}
    findings = _scan_findings(tags)
    facts = _facts({})
    if not findings:
        value = c.ssm.get_parameter(Name=env.archive_config_parameter)["Parameter"]["Value"]
        config = ArchiveConfig.model_validate_json(value)
        with tempfile.TemporaryDirectory(prefix="ingest-") as tmp:
            folder = Path(tmp)
            _download(c, env, sid, round, paths, folder)
            result = diagnose(folder, config.load_profiles(), config.required)
            try:
                manifest = json.loads((folder / MANIFEST).read_text(encoding="utf-8"))
            except (OSError, ValueError):
                manifest = {}
        findings = result.findings
        report["validation"] = result.validation.dump()
        report["quality"] = result.quality.dump() if result.quality else None
        facts = _facts(manifest if isinstance(manifest, dict) else {})
    report["findings"] = [f.dump() for f in findings]
    counts = {s: sum(1 for f in findings if f.severity == s) for s in ("error", "warning", "note")}
    key = f"reports/{sid}/{round}.json"
    c.s3.put_object(
        Bucket=env.staging_bucket,
        Key=key,
        Body=json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
    )
    blocked = counts["error"] > 0
    if blocked:
        _set(c, sid, {"reportKey": key, "status": "needs-changes"}, remove=("callbackId",))
    else:
        _set(c, sid, {"reportKey": key})
    put_event(
        c.reviews,
        sid,
        "checked",
        PIPELINE,
        round,
        errors=counts["error"],
        warnings=counts["warning"],
        notes=counts["note"],
        reportKey=key,
        blocked=blocked,
    )
    return {"blocked": blocked, **facts}


@durable_step
def _hold(_: StepContext, c: Clients, env: Env, sid: str, round: int, paths: list[str]) -> None:
    """Replace `held/<id>/` with this round's files."""
    held = f"held/{sid}/"
    _delete_prefix(c, env, held)
    for path in paths:
        c.s3.copy_object(
            Bucket=env.staging_bucket,
            Key=held + path,
            CopySource={"Bucket": env.staging_bucket, "Key": _incoming(sid, round, path)},
        )
    put_event(c.reviews, sid, "held", PIPELINE, round, files=len(paths))


@durable_step
def _policy(
    _: StepContext, c: Clients, env: Env, sid: str, round: int, checked: dict[str, Any]
) -> dict[str, Any]:
    """Read the policy once, record the rule that matched, and enter review unless skipped."""
    item = _submission(c, sid)
    policy = stored_policy(c.settings)
    themes: list[str] = checked["themes"]
    facts = SubmissionFacts(
        submitter=str(item["submitter"]),
        submitter_is_curator=bool(item.get("submitterIsCurator")),
        kind="new-version" if item.get("newVersion") else "new-dataset",
        access=checked["access"],
        themes=tuple(themes),
    )
    outcome, rule = match(policy, facts)
    named = policy.reviewers.get(themes[0]) if themes else None
    audience = named[0] if named else ALL
    entered = _clock().isoformat()
    if outcome == "skip":
        _set(c, sid, {"rule": rule})
    else:
        _set(
            c,
            sid,
            {"rule": rule, "status": "in-review", "stale": False, "approvals": []},
            remove=("callbackId",),
        )
        put_event(
            c.reviews,
            sid,
            "entered-review",
            PIPELINE,
            round,
            rule=rule,
            outcome=outcome,
            audience=audience,
        )
        _notify(
            c,
            env,
            audience,
            f"Review: {checked['title'] or sid}",
            f"Submission {sid} round {round} is waiting for review"
            f" ({'two curators' if outcome == 'two' else 'one curator'}).",
        )
    return {
        "outcome": outcome,
        "rule": rule,
        "audience": audience,
        "enteredAt": entered,
        "reminders": reminder_schedule(policy),
        "staleDays": policy.stale_days,
    }


@durable_step
def _elapsed(_: StepContext, entered: str) -> int:
    return int((_clock() - datetime.fromisoformat(entered)).total_seconds())


@durable_step
def _remind(
    _: StepContext, c: Clients, env: Env, sid: str, round: int, day: int, audience: str
) -> None:
    put_event(c.reviews, sid, "reminded", PIPELINE, round, day=day, audience=audience)
    _notify(
        c,
        env,
        audience,
        f"Reminder: submission {sid} waits for review",
        f"Submission {sid} round {round} has waited {day} days for review.",
    )


@durable_step
def _stale(
    _: StepContext, c: Clients, env: Env, sid: str, round: int, days: int, audience: str
) -> None:
    _set(c, sid, {"stale": True})
    put_event(c.reviews, sid, "stale", PIPELINE, round, days=days, audience=audience)
    text = f"Submission {sid} round {round} has waited {days} days for review and is stale."
    _notify(c, env, audience, f"Stale: submission {sid} waits for review", text)
    _alert(c, env, f"Stale review: submission {sid}", text)


@durable_step
def _approve(_: StepContext, c: Clients, sid: str, by: str) -> list[str]:
    approvals = [str(a) for a in _submission(c, sid).get("approvals") or []]
    if by not in approvals:
        approvals.append(by)
    _set(c, sid, {"approvals": approvals})
    return approvals


@durable_step
def _reject(_: StepContext, c: Clients, env: Env, sid: str, round: int, by: str, note: Any) -> None:
    _delete_prefix(c, env, f"held/{sid}/")
    _set(c, sid, {"status": "rejected"}, remove=("callbackId",))
    put_event(c.reviews, sid, "rejected", by, round, note=note)


@durable_step
def _changes(_: StepContext, c: Clients, sid: str) -> None:
    # The API wrote the `decided` event before it sent this decision.
    _set(c, sid, {"status": "needs-changes"}, remove=("callbackId",))


@durable_step
def _abandon(_: StepContext, c: Clients, env: Env, sid: str, round: int) -> None:
    _delete_prefix(c, env, f"held/{sid}/")
    _set(c, sid, {"status": "abandoned"}, remove=("callbackId",))
    put_event(c.reviews, sid, "abandoned", PIPELINE, round, days=RESUBMIT_DAYS)


@durable_step
def _expire(_: StepContext, c: Clients, env: Env, sid: str) -> int:
    round = int(_submission(c, sid)["round"])
    _delete_prefix(c, env, f"held/{sid}/")
    _set(c, sid, {"status": "expired"}, remove=("callbackId",))
    put_event(c.reviews, sid, "expired", PIPELINE, round, days=EXPIRY_DAYS)
    return round


@durable_step
def _publish(_: StepContext, c: Clients, sid: str, round: int, rule: int | None) -> None:
    """Publish: for now only the finish; the version, fill-in, copy, catalog and page steps
    come before it once the publisher is built."""
    _set(c, sid, {"status": "published"}, remove=("callbackId",))
    put_event(c.reviews, sid, "published", PIPELINE, round, rule=rule)


@durable_step
def _fail(_: StepContext, c: Clients, env: Env, sid: str, error: str) -> None:
    item = _submission(c, sid)
    round = int(item.get("round") or 1)
    _set(c, sid, {"status": "failed"}, remove=("callbackId",))
    put_event(c.reviews, sid, "failed", PIPELINE, round, error=error[:1000])
    _alert(
        c,
        env,
        f"Ingest failed: submission {sid}",
        f"Submission {sid} round {round} failed: {error}",
    )


def _store_callback(c: Clients, sid: str) -> Any:
    def submitter(callback_id: str, _: object) -> None:
        _set(c, sid, {"callbackId": callback_id})

    return submitter


def _wait(
    context: DurableContext, c: Clients, sid: str, name: str, timeout: int, started: str
) -> Any:
    """A callback wait capped to end by the 360th day; `Expired` when the cap ended it."""
    left = context.step(_left(started), name=f"{name}-deadline")
    if left <= 0:
        raise Expired(name)
    try:
        return context.wait_for_callback(
            _store_callback(c, sid),
            name=name,
            config=WaitForCallbackConfig(timeout=Duration.from_seconds(min(timeout, left))),
        )
    except CallbackTimeoutError:
        if left <= timeout:
            raise Expired(name) from None
        raise


def _scan(
    context: DurableContext, c: Clients, env: Env, sid: str, round: int, paths: list[str]
) -> dict[str, str]:
    """Wait until GuardDuty has tagged every file of the round, backing off up to an hour."""

    def check(state: dict[str, Any], _: object) -> dict[str, Any]:
        tags: dict[str, str] = {}
        for path in paths:
            tagging = c.s3.get_object_tagging(
                Bucket=env.staging_bucket, Key=_incoming(sid, round, path)
            )
            value = next((t["Value"] for t in tagging["TagSet"] if t["Key"] == SCAN_TAG), None)
            if value:
                tags[path] = str(value)
        return {"tags": tags}

    def strategy(state: dict[str, Any], attempt: int) -> WaitForConditionDecision:
        if len(state["tags"]) == len(paths):
            return WaitForConditionDecision.stop_polling()
        delay = min(30 * 2 ** (attempt - 1), MAX_SCAN_DELAY)
        return WaitForConditionDecision.continue_waiting(Duration.from_seconds(delay))

    done: dict[str, Any] = context.wait_for_condition(
        check,
        WaitForConditionConfig(wait_strategy=strategy, initial_state={"tags": {}}),
        name=f"scan-{round}",
    )
    return cast(dict[str, str], done["tags"])


def _review(
    context: DurableContext,
    c: Clients,
    env: Env,
    sid: str,
    round: int,
    policy: dict[str, Any],
    started: str,
) -> str:
    """Wait for decisions until one ends the review: `approved`, `rejected` or `changes`."""
    reminders: list[int] = policy["reminders"]
    stale_days: int = policy["staleDays"]
    audience: str = policy["audience"]
    needed = 2 if policy["outcome"] == "two" else 1
    sent = 0
    stale = False
    n = 0
    while True:
        n += 1
        elapsed = context.step(_elapsed(policy["enteredAt"]), name=f"review-clock-{round}-{n}")
        if stale:
            timeout = stale_days * DAY
        else:
            mark = ([d * DAY for d in reminders[sent:]] + [stale_days * DAY])[0]
            timeout = mark - elapsed
        try:
            if timeout <= 0:
                raise CallbackTimeoutError("the mark was already due")
            result = _wait(context, c, sid, f"review-{round}-{n}", timeout, started)
        except CallbackTimeoutError:
            if stale:
                continue
            if sent < len(reminders):
                day = reminders[sent]
                sent += 1
                context.step(
                    _remind(c, env, sid, round, day, audience), name=f"remind-{round}-{sent}"
                )
            else:
                stale = True
                context.step(
                    _stale(c, env, sid, round, stale_days, audience), name=f"stale-{round}"
                )
            continue
        payload = _payload(result)
        decision, by = payload.get("decision"), str(payload.get("by"))
        if payload.get("kind") != "decision":
            raise BadCallback(f"expected a decision, got {payload!r}")
        if decision == "approve":
            approvals = context.step(_approve(c, sid, by), name=f"approve-{round}-{n}")
            if len(set(approvals)) >= needed:
                return "approved"
        elif decision == "reject":
            context.step(
                _reject(c, env, sid, round, by, payload.get("note")), name=f"reject-{round}"
            )
            return "rejected"
        elif decision == "request-changes":
            context.step(_changes(c, sid), name=f"changes-{round}")
            return "changes"
        else:
            raise BadCallback(f"unknown decision {decision!r}")


def _resubmit(
    context: DurableContext, c: Clients, env: Env, sid: str, round: int, started: str
) -> int | None:
    """Wait 30 days for the next round; None when none arrives and the submission is abandoned."""
    try:
        result = _wait(context, c, sid, f"resubmit-{round}", RESUBMIT_DAYS * DAY, started)
    except CallbackTimeoutError:
        context.step(_abandon(c, env, sid, round), name=f"abandon-{round}")
        return None
    payload = _payload(result)
    next_round = payload.get("round")
    if payload.get("kind") != "resubmit" or not isinstance(next_round, int) or next_round <= round:
        raise BadCallback(f"expected a resubmit after round {round}, got {payload!r}")
    return next_round


def _ingest(context: DurableContext, c: Clients, env: Env, sid: str) -> dict[str, Any]:
    begun = context.step(_start(c, sid), name="start")
    round: int = begun["round"]
    started: str = begun["startedAt"]
    try:
        return _rounds(context, c, env, sid, round, started)
    except Expired:
        round = context.step(_expire(c, env, sid), name="expire")
        return {"submissionId": sid, "status": "expired", "round": round}


def _rounds(
    context: DurableContext, c: Clients, env: Env, sid: str, round: int, started: str
) -> dict[str, Any]:
    while True:
        paths = context.step(_files(c, sid, round), name=f"files-{round}")
        tags = _scan(context, c, env, sid, round, paths)
        context.step(_scanned(c, sid, round, tags), name=f"scanned-{round}")
        checked = context.step(_check(c, env, sid, round, paths, tags), name=f"check-{round}")
        if not checked["blocked"]:
            context.step(_hold(c, env, sid, round, paths), name=f"hold-{round}")
            policy = context.step(_policy(c, env, sid, round, checked), name=f"policy-{round}")
            outcome = "approved"
            if policy["outcome"] != "skip":
                outcome = _review(context, c, env, sid, round, policy, started)
            if outcome == "approved":
                context.step(_publish(c, sid, round, policy["rule"]), name=f"publish-{round}")
                return {"submissionId": sid, "status": "published", "round": round}
            if outcome == "rejected":
                return {"submissionId": sid, "status": "rejected", "round": round}
        next_round = _resubmit(context, c, env, sid, round, started)
        if next_round is None:
            return {"submissionId": sid, "status": "abandoned", "round": round}
        round = next_round


def run(event: dict[str, Any], context: DurableContext) -> dict[str, Any]:
    """The submission's whole path; a failed step or a bad callback ends it as `failed`."""
    sid = str(event["submissionId"])
    env = Env.from_environ()
    c = clients(env)
    try:
        return _ingest(context, c, env, sid)
    except (DurableOperationError, BadCallback) as error:
        context.step(_fail(c, env, sid, str(error) or type(error).__name__), name="fail")
        return {"submissionId": sid, "status": "failed"}


handler = durable_execution(run)
