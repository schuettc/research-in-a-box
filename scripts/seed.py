"""Publish the sample package on a deployed archive as its admin: `just seed <stage>`.

It signs in through the browser with `archive_client`, creates a submission for the package's
files, uploads each to its presigned URL, submits it, approves it if it goes to review, and
waits for it to publish. It prints each new status once, then the dataset's URL, or the status
with its findings and events and exit 1 when the submission stops anywhere else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from archive_client.signin import AuthConfig, SignInError, Tokens
from archive_client.signin import sign_in as browser_sign_in

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "sample-package"
# The sample's generator and its notes, not part of the package.
NOT_PACKAGE = ("_build",)
POLL_SECONDS = 5.0
TIMEOUT_SECONDS = 15 * 60.0
STOPPED = ("needs-changes", "rejected", "failed", "expired", "abandoned")
HTTP_SECONDS = 60
UPLOAD_SECONDS = 300

Send = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


class Failed(Exception):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _package_files(folder: Path) -> list[Path]:
    return sorted(
        p
        for p in folder.rglob("*")
        if p.is_file() and p.relative_to(folder).parts[0] not in NOT_PACKAGE
    )


def file_list(folder: Path) -> list[dict[str, Any]]:
    """The submissions API's `files`: each file's relative path, size and SHA-256 in hex."""
    return [
        {"path": p.relative_to(folder).as_posix(), "size": p.stat().st_size, "sha256": _sha256(p)}
        for p in _package_files(folder)
    ]


def http_send(
    method: str, url: str, headers: dict[str, str], data: bytes | None
) -> tuple[int, bytes]:
    """Send a request: its status and body, whatever the status."""
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    timeout = UPLOAD_SECONDS if method == "PUT" else HTTP_SECONDS
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), cast(bytes, response.read())
    except urllib.error.HTTPError as error:
        return int(error.code), error.read()


class Seed:
    def __init__(
        self,
        domain: str,
        token: str,
        send: Send,
        sleep: Callable[[float], None],
        clock: Callable[[], float],
        poll_seconds: float,
        timeout_seconds: float,
    ) -> None:
        self.domain = domain
        self.token = token
        self.send = send
        self.sleep = sleep
        self.clock = clock
        self.poll_seconds = poll_seconds
        self.timeout_seconds = timeout_seconds

    def call(self, method: str, path: str = "", body: Any = None, expect: int = 200) -> Any:
        # The API's Cognito authorizer takes the ID token as the raw header, with no "Bearer".
        headers = {"Authorization": self.token}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["content-type"] = "application/json"
        url = f"https://{self.domain}/api/submissions{path}"
        status, raw = self.send(method, url, headers, data)
        if status != expect:
            raise Failed(f"{method} /api/submissions{path} answered {status}: {raw[:300]!r}")
        return json.loads(raw) if raw else None

    def submit(self, folder: Path) -> str:
        created = self.call("POST", body={"files": file_list(folder)}, expect=201)
        for item in created["uploads"]:
            data = (folder / item["path"]).read_bytes()
            status, _ = self.send("PUT", item["url"], dict(item["headers"]), data)
            if status != 200:
                raise Failed(f"the upload of {item['path']} answered {status}")
        sid = str(created["submissionId"])
        self.call("POST", f"/{sid}/submit", expect=202)
        print(f"submitted {sid}")
        return sid

    def follow(self, sid: str) -> str:
        """Poll until published (the dataset's URL) or stopped; approve once when in review."""
        deadline = self.clock() + self.timeout_seconds
        seen = ""
        approved = False
        while True:
            answer = self.call("GET", f"/{sid}")
            submission = answer["submission"]
            status = str(submission.get("status"))
            if status != seen:
                print(f"status: {status}")
                seen = status
            if status == "published":
                return f"https://{self.domain}/datasets/{submission['datasetId']}"
            if status in STOPPED:
                raise Failed(f"stopped: {status}\n{self.details(answer)}")
            # A decision completes the review's wait, so it goes only once the wait is open.
            if status == "in-review" and submission.get("callbackId") and not approved:
                self.call(
                    "POST",
                    f"/{sid}/decision",
                    body={"decision": "approve", "note": "seed"},
                    expect=202,
                )
                print("approved")
                approved = True
            if self.clock() >= deadline:
                raise Failed(
                    f"still {status} after {self.timeout_seconds:g} seconds\n{self.details(answer)}"
                )
            self.sleep(self.poll_seconds)

    def details(self, answer: dict[str, Any]) -> str:
        """The check's findings, from the report when there is one, and the events so far."""
        lines = []
        report_url = answer.get("reportUrl")
        if report_url:
            status, raw = self.send("GET", str(report_url), {}, None)
            if status == 200:
                for finding in json.loads(raw).get("findings", []):
                    lines.append(
                        f"  {finding.get('severity')} {finding.get('ruleId')}: "
                        f"{finding.get('message')}"
                    )
            else:
                lines.append(f"  the report answered {status}: {report_url}")
        events = ", ".join(str(e.get("type")) for e in answer.get("events", []))
        lines.append(f"events: {events or 'none'}")
        return "\n".join(lines)


def main(
    argv: list[str] | None = None,
    *,
    from_archive: Callable[[str], AuthConfig] = AuthConfig.from_archive,
    sign_in: Callable[[AuthConfig], Tokens] = browser_sign_in,
    send: Send = http_send,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    poll_seconds: float = POLL_SECONDS,
    timeout_seconds: float = TIMEOUT_SECONDS,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    parser.add_argument("domain", help="the site's domain, the stack's SiteDomain output")
    parser.add_argument("--package", type=Path, default=SAMPLE)
    args = parser.parse_args(argv)
    try:
        config = from_archive(f"https://{args.domain}")
        print("signing in: finish it in the browser")
        tokens = sign_in(config)
    except (SignInError, OSError) as error:
        print(f"sign-in failed: {error}")
        return 1
    seed = Seed(args.domain, tokens.id_token, send, sleep, clock, poll_seconds, timeout_seconds)
    try:
        sid = seed.submit(args.package)
        print(seed.follow(sid))
    except (Failed, OSError) as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
