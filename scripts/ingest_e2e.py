"""The ingest pipeline's scripted run on a deployed non-prod stage: `just ingest-e2e <stage>`.

It reads the stack's outputs, creates three throwaway users with the admin APIs (a contributor,
a curator who is also an admin, and a second curator), signs them in through the test-only `e2e`
client, sets a review policy, and drives the sample package through the submissions API:
approve, reject, request changes then approve, a blocking error, a skip rule, two curators and
a reminder. Each run checks the event types its submission recorded in Reviews, read back with
`GET /api/submissions/{id}`. At the end it restores the policy and deletes its users.

The policy's smallest reminder is one day, so the reminder run leaves its submission waiting and
records its id in a state file under the user's state dir. The next run a day later asserts the
`reminded` event and approves it, and starts no new one. Run it with the caller's AWS profile
and region; it prints one line per run and exits non-zero on any failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "sample-package"
MANIFEST = "datapackage.json"
CHECKSUMS = "checksums.sha256"
# The sample's generator and its notes, not part of the package.
NOT_PACKAGE = ("_build",)
THEMES = "archive:themes"
SKIP_THEME, TWO_THEME, REMIND_THEME = "e2e-skip", "e2e-two", "e2e-remind"
SKIP_RULE, TWO_RULE = 0, 1
POLL_SECONDS = 10
WAIT_SECONDS = 45 * 60
EVENT_SECONDS = 60
TOKEN_SECONDS = 50 * 60
REMINDER_GRACE = timedelta(hours=1)

REVIEWED = ["created", "submitted", "scanned", "checked", "held", "entered-review"]
ROUND = ["scanned", "checked", "held", "entered-review"]


# The pure parts: the package copies, the file list, the policy, the events and the state file.


def package_copy(into: Path, change: Callable[[dict[str, Any]], None] | None = None) -> Path:
    """A copy of the sample package in `into`, its manifest changed, its checksums rewritten."""
    folder = into / "package"
    shutil.copytree(SAMPLE, folder, ignore=shutil.ignore_patterns(*NOT_PACKAGE))
    if change is not None:
        path = folder / MANIFEST
        manifest = json.loads(path.read_text(encoding="utf-8"))
        change(manifest)
        path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", "utf-8")
    (folder / CHECKSUMS).write_text(checksum_text(folder), encoding="utf-8")
    return folder


def _package_files(folder: Path) -> list[Path]:
    return sorted(p for p in folder.rglob("*") if p.is_file())


def checksum_text(folder: Path) -> str:
    """`checksums.sha256` for every other file in the folder, in path order."""
    return "".join(
        f"{_sha256(p)}  {p.relative_to(folder).as_posix()}\n"
        for p in _package_files(folder)
        if p.relative_to(folder).as_posix() != CHECKSUMS
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def file_list(folder: Path) -> list[dict[str, Any]]:
    """The submissions API's `files`: each file's relative path, size and SHA-256 in hex."""
    return [
        {"path": p.relative_to(folder).as_posix(), "size": p.stat().st_size, "sha256": _sha256(p)}
        for p in _package_files(folder)
    ]


def themed(theme: str) -> Callable[[dict[str, Any]], None]:
    def change(manifest: dict[str, Any]) -> None:
        manifest[THEMES] = [theme]

    return change


def without(field_name: str) -> Callable[[dict[str, Any]], None]:
    def change(manifest: dict[str, Any]) -> None:
        manifest.pop(field_name, None)

    return change


def e2e_policy(reviewer: str | None) -> dict[str, Any]:
    """Skip by theme (rule 0), two curators by theme (rule 1), otherwise one; remind on day 1.

    `reviewer` names the curator asked first for the reminder run's theme, so the reminder goes
    to their email subscription; without one it goes to all curators.
    """
    return {
        "required": True,
        "rules": [
            {"themes": [SKIP_THEME], "outcome": "skip"},
            {"themes": [TWO_THEME], "outcome": "two"},
        ],
        "reviewers": {REMIND_THEME: [reviewer]} if reviewer else {},
        "reminders": [1],
        "staleDays": 14,
    }


def event_mismatch(expected: Iterable[str], events: Iterable[dict[str, Any]]) -> str | None:
    """None when the events' types are exactly `expected` (in any order), else what differs.

    Order isn't compared: an API event (submitted, resubmitted) and the pipeline's next event
    can land within the same moment.
    """
    want = Counter(expected)
    got = Counter(str(e.get("type")) for e in events)
    if want == got:
        return None
    missing, extra = want - got, got - want
    parts = []
    if missing:
        parts.append("missing " + ", ".join(sorted(missing.elements())))
    if extra:
        parts.append("extra " + ", ".join(sorted(extra.elements())))
    return "; ".join(parts)


def state_path(stage: str) -> Path:
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "research-archive" / f"ingest-e2e-{stage}.json"


def load_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return cast(dict[str, Any], value) if isinstance(value, dict) else None


def save_state(path: Path, state: dict[str, Any] | None) -> None:
    """Write the state, or remove the file when there is none."""
    if state is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def reminder_due(entered_at: str, now: datetime) -> bool:
    """Whether a day-1 reminder should have been sent by `now`, with an hour's grace."""
    entered = datetime.fromisoformat(entered_at.replace("Z", "+00:00"))
    return now >= entered + timedelta(days=1) + REMINDER_GRACE


def password() -> str:
    """A throwaway password that meets Cognito's default policy."""
    return secrets.token_urlsafe(24) + "aA1!"


# The deployed stage: its outputs, its users and its API.


class CloudFormation(Protocol):
    def describe_stacks(self, **kwargs: Any) -> dict[str, Any]: ...


class CognitoIdp(Protocol):
    def admin_create_user(self, **kwargs: Any) -> dict[str, Any]: ...
    def admin_set_user_password(self, **kwargs: Any) -> Any: ...
    def admin_add_user_to_group(self, **kwargs: Any) -> Any: ...
    def admin_initiate_auth(self, **kwargs: Any) -> dict[str, Any]: ...
    def admin_delete_user(self, **kwargs: Any) -> Any: ...


def stack_outputs(cloudformation: CloudFormation, stage: str) -> dict[str, str]:
    stack = cloudformation.describe_stacks(StackName=f"ResearchArchive-{stage}")["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in stack.get("Outputs", [])}


class Failed(Exception):
    pass


@dataclass
class User:
    """A throwaway user; `token` is its ID token, which the API's Cognito authorizer takes."""

    cognito: CognitoIdp
    pool: str
    client: str
    email: str
    secret: str
    sub: str
    _token: str = ""
    _at: float = 0.0

    @property
    def token(self) -> str:
        if not self._token or time.monotonic() - self._at > TOKEN_SECONDS:
            result = self.cognito.admin_initiate_auth(
                UserPoolId=self.pool,
                ClientId=self.client,
                AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": self.email, "PASSWORD": self.secret},
            )
            self._token, self._at = result["AuthenticationResult"]["IdToken"], time.monotonic()
        return self._token


def create_user(
    cognito: CognitoIdp, pool: str, client: str, run: str, role: str, groups: list[str]
) -> User:
    """Accounts are invitation-only: an admin-created user, its password set, in its groups."""
    email = f"e2e-{run}-{role}@example.org"
    created = cognito.admin_create_user(
        UserPoolId=pool,
        Username=email,
        UserAttributes=[
            {"Name": "email", "Value": email},
            {"Name": "email_verified", "Value": "true"},
        ],
        MessageAction="SUPPRESS",
    )
    attributes = {a["Name"]: a["Value"] for a in created["User"]["Attributes"]}
    secret = password()
    cognito.admin_set_user_password(
        UserPoolId=pool, Username=email, Password=secret, Permanent=True
    )
    for group in groups:
        cognito.admin_add_user_to_group(UserPoolId=pool, Username=email, GroupName=group)
    return User(cognito, pool, client, email, secret, attributes["sub"])


def http(method: str, url: str, token: str | None = None, body: Any = None) -> tuple[int, bytes]:
    headers = {}
    data = None
    if token:
        headers["Authorization"] = token
    if body is not None:
        data = json.dumps(body).encode()
        headers["content-type"] = "application/json"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return int(response.status), cast(bytes, response.read())
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()


@dataclass
class Api:
    domain: str

    def call(
        self, user: User, method: str, path: str = "", body: Any = None, expect: int = 200
    ) -> Any:
        url = f"https://{self.domain}/api/submissions{path}"
        status, raw = http(method, url, user.token, body)
        if status != expect:
            raise Failed(f"{method} {path or '/'} returned {status}, not {expect}: {raw[:300]!r}")
        return json.loads(raw) if raw else None

    def read(self, user: User, sid: str) -> dict[str, Any]:
        return cast(dict[str, Any], self.call(user, "GET", f"/{sid}"))


def upload(uploads: list[dict[str, Any]], folder: Path) -> None:
    """PUT each file to its presigned URL with the headers the API returned for it."""
    for item in uploads:
        data = (folder / item["path"]).read_bytes()
        request = urllib.request.Request(
            item["url"], data=data, method="PUT", headers=dict(item["headers"])
        )
        try:
            with urllib.request.urlopen(request, timeout=300):
                pass
        except urllib.error.HTTPError as error:
            raise Failed(f"upload of {item['path']} returned {error.code}") from error


# The runs.


@dataclass
class Stage:
    api: Api
    contributor: User
    curator: User
    second: User
    tmp: Path

    def submit(self, folder: Path) -> str:
        created = self.api.call(
            self.contributor, "POST", body={"files": file_list(folder)}, expect=201
        )
        upload(created["uploads"], folder)
        sid = str(created["submissionId"])
        self.api.call(self.contributor, "POST", f"/{sid}/submit", expect=202)
        return sid

    def resubmit(self, sid: str, folder: Path) -> None:
        next_round = self.api.call(
            self.contributor, "POST", f"/{sid}/uploads", body={"files": file_list(folder)}
        )
        upload(next_round["uploads"], folder)
        self.api.call(self.contributor, "POST", f"/{sid}/submit", expect=202)

    def wait(
        self,
        sid: str,
        status: str,
        ready: Callable[[dict[str, Any]], bool] = lambda _: True,
        what: str = "",
    ) -> dict[str, Any]:
        """Poll as the curator until the submission has `status` and `ready` holds.

        A waiting status counts only once its callback is stored, since a decision or resubmit
        sent before then has nothing to complete.
        """
        waiting = status in ("in-review", "needs-changes")
        deadline = time.monotonic() + WAIT_SECONDS
        seen = ""
        while time.monotonic() < deadline:
            submission = self.api.read(self.curator, sid)["submission"]
            seen = str(submission.get("status"))
            if seen == status and (not waiting or submission.get("callbackId")):
                if ready(submission):
                    return cast(dict[str, Any], submission)
            elif seen in ("failed", "expired", "abandoned") or (
                seen in ("published", "rejected") and seen != status
            ):
                raise Failed(f"ended {seen} while waiting for {what or status}")
            time.sleep(POLL_SECONDS)
        raise Failed(f"still {seen} after {WAIT_SECONDS // 60} minutes, not {what or status}")

    def decide(self, user: User, sid: str, decision: str, expect: int = 202) -> None:
        body = {"decision": decision, "note": f"e2e: {decision}"}
        self.api.call(user, "POST", f"/{sid}/decision", body=body, expect=expect)

    def events(self, sid: str, expected: list[str]) -> list[dict[str, Any]]:
        """The submission's events once their types match `expected`; a step sets the status a
        moment before it writes its event, so this polls briefly."""
        deadline = time.monotonic() + EVENT_SECONDS
        while True:
            events = cast(list[dict[str, Any]], self.api.read(self.curator, sid)["events"])
            mismatch = event_mismatch(expected, events)
            if mismatch is None:
                return events
            if time.monotonic() > deadline:
                raise Failed(f"events: {mismatch}")
            time.sleep(POLL_SECONDS)

    def folder(self, change: Callable[[dict[str, Any]], None] | None = None) -> Path:
        return package_copy(Path(tempfile.mkdtemp(dir=self.tmp)), change)

    def readable(self, dataset_id: str, version: int) -> None:
        """The published manifest at /data/<id>/<version>/ and the page at /datasets/<id>."""
        base = f"https://{self.api.domain}"
        status, raw = http("GET", f"{base}/data/{dataset_id}/{version}/{MANIFEST}")
        if status != 200:
            raise Failed(f"/data/{dataset_id}/{version}/{MANIFEST} returned {status}")
        manifest = json.loads(raw)
        if manifest.get("id") != dataset_id or manifest.get("version") != str(version):
            raise Failed(f"published manifest says {manifest.get('id')} v{manifest.get('version')}")
        status, raw = http("GET", f"{base}/datasets/{dataset_id}")
        if status != 200 or str(manifest.get("title", "")).encode() not in raw:
            raise Failed(f"/datasets/{dataset_id} returned {status} without the title")


def _rule(events: list[dict[str, Any]], type: str) -> list[Any]:
    return [e.get("rule") for e in events if e.get("type") == type]


def run_approve(s: Stage) -> str:
    sid = s.submit(s.folder())
    s.wait(sid, "in-review")
    s.decide(s.curator, sid, "approve")
    done = s.wait(sid, "published")
    s.events(sid, [*REVIEWED, "decided", "published"])
    s.readable(str(done["datasetId"]), 1)
    return f"{sid} published {done['datasetId']} v1, readable at /data and /datasets"


def run_reject(s: Stage) -> str:
    sid = s.submit(s.folder())
    s.wait(sid, "in-review")
    s.decide(s.curator, sid, "reject")
    s.wait(sid, "rejected")
    s.events(sid, [*REVIEWED, "decided", "rejected"])
    return f"{sid} rejected"


def run_changes(s: Stage) -> str:
    sid = s.submit(s.folder())
    s.wait(sid, "in-review")
    s.decide(s.curator, sid, "request-changes")
    s.wait(sid, "needs-changes")
    s.resubmit(sid, s.folder())
    s.wait(sid, "in-review", lambda sub: int(sub["round"]) == 2, "round 2 in review")
    s.decide(s.curator, sid, "approve")
    done = s.wait(sid, "published")
    expected = [*REVIEWED, "decided", "resubmitted", *ROUND, "decided", "published"]
    events = s.events(sid, expected)
    published = [e for e in events if e.get("type") == "published"]
    if int(published[0].get("round", 0)) != 2 or int(published[0].get("version", 0)) != 1:
        raise Failed(f"published {published[0]}, not round 2 as version 1")
    s.readable(str(done["datasetId"]), 1)
    return f"{sid} published {done['datasetId']} v1 after round 2"


def run_blocked(s: Stage) -> str:
    """A core field removed blocks the round; the fixed round then goes to review, rejected so
    nothing is left waiting."""
    sid = s.submit(s.folder(without("description")))
    s.wait(sid, "needs-changes")
    checked = s.events(sid, ["created", "submitted", "scanned", "checked"])
    check = next(e for e in checked if e.get("type") == "checked")
    if not check.get("blocked") or int(check.get("errors", 0)) < 1:
        raise Failed(f"the check did not block: {check}")
    s.resubmit(sid, s.folder())
    s.wait(sid, "in-review", lambda sub: int(sub["round"]) == 2, "round 2 in review")
    s.decide(s.curator, sid, "reject")
    s.wait(sid, "rejected")
    expected = ["created", "submitted", "scanned", "checked", "resubmitted", *ROUND]
    s.events(sid, [*expected, "decided", "rejected"])
    return f"{sid} needs-changes ({check.get('errors')} errors), cleared and rejected"


def run_skip(s: Stage) -> str:
    sid = s.submit(s.folder(themed(SKIP_THEME)))
    done = s.wait(sid, "published")
    events = s.events(sid, ["created", "submitted", "scanned", "checked", "held", "published"])
    if _rule(events, "published") != [SKIP_RULE]:
        raise Failed(f"published under rule {_rule(events, 'published')}, not {SKIP_RULE}")
    s.readable(str(done["datasetId"]), 1)
    return f"{sid} published {done['datasetId']} without review under rule {SKIP_RULE}"


def run_two(s: Stage) -> str:
    sid = s.submit(s.folder(themed(TWO_THEME)))
    first = s.wait(sid, "in-review")
    s.decide(s.curator, sid, "approve")
    s.wait(
        sid,
        "in-review",
        lambda sub: (
            sub.get("approvals") == [s.curator.sub]
            and sub.get("callbackId") != first.get("callbackId")
        ),
        "waiting for a second curator",
    )
    s.decide(s.curator, sid, "approve", expect=409)
    s.decide(s.second, sid, "approve")
    done = s.wait(sid, "published")
    events = s.events(sid, [*REVIEWED, "decided", "decided", "published"])
    entered = [e for e in events if e.get("type") == "entered-review"][0]
    if entered.get("rule") != TWO_RULE or entered.get("outcome") != "two":
        raise Failed(f"entered review as {entered}, not rule {TWO_RULE} with two curators")
    return f"{sid} waited after one approval, published {done['datasetId']} after the second"


def run_reminder(s: Stage, path: Path, waiting: dict[str, Any] | None) -> str:
    """Check a submission left waiting by an earlier run, or leave one waiting for the next."""
    if waiting is None:
        sid = s.submit(s.folder(themed(REMIND_THEME)))
        s.wait(sid, "in-review")
        events = s.events(sid, REVIEWED)
        entered = [e for e in events if e.get("type") == "entered-review"][0]
        save_state(path, {"submissionId": sid, "enteredAt": entered["at"]})
        due = datetime.fromisoformat(str(entered["at"]).replace("Z", "+00:00"))
        due += timedelta(days=1) + REMINDER_GRACE
        return (
            f"{sid} left waiting for {entered.get('audience')}; run again after "
            f"{due:%Y-%m-%d %H:%M} UTC to check its reminder"
        )
    sid = str(waiting["submissionId"])
    events = s.api.read(s.curator, sid)["events"]
    if not any(e.get("type") == "reminded" for e in events):
        if reminder_due(str(waiting["enteredAt"]), datetime.now(UTC)):
            raise Failed(f"{sid} has no reminded event a day after entering review")
        return f"{sid} still waiting; its day-1 reminder isn't due yet (pending)"
    s.wait(sid, "in-review")
    s.decide(s.curator, sid, "approve")
    done = s.wait(sid, "published")
    s.events(sid, [*REVIEWED, "reminded", "decided", "published"])
    save_state(path, None)
    return f"{sid} reminded on day 1, then published {done['datasetId']}"


@dataclass
class Outcome:
    name: str
    ok: bool
    detail: str
    pending: bool = field(default=False)


def attempt(name: str, run: Callable[[], str]) -> Outcome:
    try:
        detail = run()
    except Failed as error:
        return Outcome(name, False, str(error))
    except Exception as error:  # one run's crash is that run's failure
        return Outcome(name, False, f"{type(error).__name__}: {error}")
    return Outcome(name, True, detail, pending="(pending)" in detail)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("stage")
    args = parser.parse_args(argv)
    if args.stage == "prod":
        print("ingest-e2e never runs on prod", file=sys.stderr)
        return 2

    import boto3

    outputs = stack_outputs(cast(CloudFormation, boto3.client("cloudformation")), args.stage)
    missing = {"E2eClientId", "UserPoolId", "SiteDomain"} - outputs.keys()
    if missing:
        print(f"ResearchArchive-{args.stage} has no {', '.join(sorted(missing))} output")
        return 2
    cognito = cast(CognitoIdp, boto3.client("cognito-idp"))
    pool, client = outputs["UserPoolId"], outputs["E2eClientId"]
    run = uuid.uuid4().hex[:8]
    path = state_path(args.stage)
    waiting = load_state(path)
    users: list[User] = []
    outcomes: list[Outcome] = []
    api = Api(outputs["SiteDomain"])
    previous: Any = None
    try:
        for role, groups in (
            ("contributor", ["contributor"]),
            ("curator", ["curator", "admin"]),
            ("second-curator", ["curator"]),
        ):
            users.append(create_user(cognito, pool, client, run, role, groups))
        contributor, curator, second = users
        previous = api.call(curator, "GET", "/policy")
        api.call(curator, "PUT", "/policy", body=e2e_policy(os.environ.get("INGEST_E2E_REVIEWER")))
        with tempfile.TemporaryDirectory(prefix="ingest-e2e-") as tmp:
            stage = Stage(api, contributor, curator, second, Path(tmp))
            runs: dict[str, Callable[[], str]] = {
                "approve": lambda: run_approve(stage),
                "reject": lambda: run_reject(stage),
                "request changes": lambda: run_changes(stage),
                "blocking error": lambda: run_blocked(stage),
                "skip rule": lambda: run_skip(stage),
                "two curators": lambda: run_two(stage),
                "reminder": lambda: run_reminder(stage, path, waiting),
            }
            with ThreadPoolExecutor(max_workers=len(runs)) as pool_:
                futures = [pool_.submit(attempt, name, fn) for name, fn in runs.items()]
                outcomes = [f.result() for f in futures]
    except Exception as error:  # setup failed; still clean up below
        outcomes.append(Outcome("setup", False, f"{type(error).__name__}: {error}"))
    finally:
        if previous is not None and users:
            restored = attempt(
                "restore policy", lambda: str(api.call(users[1], "PUT", "/policy", body=previous))
            )
            if not restored.ok:
                outcomes.append(restored)
        for user in users:
            cognito.admin_delete_user(UserPoolId=pool, Username=user.email)
    for outcome in outcomes:
        mark = "pending" if outcome.pending else "pass" if outcome.ok else "FAIL"
        print(f"{mark:7} {outcome.name}: {outcome.detail}")
    print(f"deleted {len(users)} users; state file {path}")
    return 0 if outcomes and all(o.ok for o in outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())
