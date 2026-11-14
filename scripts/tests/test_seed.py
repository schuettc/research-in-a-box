import json
from pathlib import Path
from typing import Any

import pytest

import seed
from archive_client.signin import AuthConfig, Tokens

DOMAIN = "d111.cloudfront.net"
BASE = f"https://{DOMAIN}/api/submissions"
SID = "11111111-2222-3333-4444-555555555555"
DATASET = "stream-temperature-sample"
ID_TOKEN = "id-token"
REPORT = "https://staging.example/report.json?signed"


def _package(tmp_path: Path) -> Path:
    folder = tmp_path / "package"
    (folder / "data").mkdir(parents=True)
    (folder / "_build").mkdir()
    (folder / "datapackage.json").write_text('{"id": "x"}\n', encoding="utf-8")
    (folder / "data" / "logger.csv").write_text("t,v\n1,2\n", encoding="utf-8")
    (folder / "_build" / "make.py").write_text("print('not part of it')\n", encoding="utf-8")
    return folder


class FakeArchive:
    """The submissions API and S3's presigned PUTs, answering from a list of statuses that
    `GET /api/submissions/{id}` walks through one read at a time (the last one repeats)."""

    def __init__(self, statuses: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
        self.statuses = statuses
        self.events = events
        self.reads = 0
        self.calls: list[tuple[str, str, dict[str, str], Any]] = []

    def __call__(
        self, method: str, url: str, headers: dict[str, str], data: bytes | None
    ) -> tuple[int, bytes]:
        body: Any = json.loads(data) if data and url.startswith(BASE) else data
        self.calls.append((method, url, headers, body))
        if url.startswith("https://uploads.example/"):
            return 200, b""
        if url == REPORT:
            report = {
                "findings": [
                    {"ruleId": "core.description", "severity": "error", "message": "no description"}
                ]
            }
            return 200, json.dumps(report).encode()
        assert headers.get("Authorization") == ID_TOKEN
        if (method, url) == ("POST", BASE):
            uploads = [
                {
                    "path": f["path"],
                    "url": f"https://uploads.example/{f['path']}",
                    "headers": {"x-amz-checksum-sha256": f"b64-{f['sha256'][:8]}"},
                }
                for f in body["files"]
            ]
            return 201, json.dumps({"submissionId": SID, "round": 1, "uploads": uploads}).encode()
        if (method, url) == ("POST", f"{BASE}/{SID}/submit"):
            return 202, json.dumps({"submissionId": SID, "status": "checking"}).encode()
        if (method, url) == ("POST", f"{BASE}/{SID}/decision"):
            return 202, json.dumps({"submissionId": SID, "decision": body["decision"]}).encode()
        if (method, url) == ("GET", f"{BASE}/{SID}"):
            current = self.statuses[min(self.reads, len(self.statuses) - 1)]
            self.reads += 1
            answer: dict[str, Any] = {
                "submission": {"submissionId": SID, **current},
                "events": self.events,
            }
            if current.get("reportKey"):
                answer["reportUrl"] = REPORT
            return 200, json.dumps(answer).encode()
        return 404, b'{"message": "not found"}'

    def decisions(self) -> list[Any]:
        return [c[3] for c in self.calls if c[1].endswith("/decision")]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def _run(archive: FakeArchive, package: Path, clock: Clock | None = None) -> int:
    clock = clock or Clock()
    signed: list[AuthConfig] = []

    def from_archive(url: str) -> AuthConfig:
        assert url == f"https://{DOMAIN}"
        return AuthConfig(region="us-east-1", cognito_domain="auth.example", cli_client_id="cli")

    def sign_in(config: AuthConfig) -> Tokens:
        signed.append(config)
        return Tokens(access_token="access-token", id_token=ID_TOKEN, expires_at=3600.0)

    code = seed.main(
        [DOMAIN, "--package", str(package)],
        from_archive=from_archive,
        sign_in=sign_in,
        send=archive,
        sleep=clock.sleep,
        clock=clock.time,
        poll_seconds=5,
        timeout_seconds=60,
    )
    assert len(signed) == 1
    return code


def test_a_policy_that_skips_review_publishes_with_no_decision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    package = _package(tmp_path)
    archive = FakeArchive(
        [
            {"status": "checking"},
            {"status": "checking"},
            {"status": "publishing"},
            {"status": "published", "datasetId": DATASET},
        ],
        [],
    )

    code = _run(archive, package)

    assert code == 0
    assert archive.decisions() == []
    out = capsys.readouterr().out.splitlines()
    assert out[-1] == f"https://{DOMAIN}/datasets/{DATASET}"
    # Each new status once, in order.
    assert [line for line in out if line.startswith("status:")] == [
        "status: checking",
        "status: publishing",
        "status: published",
    ]
    created = archive.calls[0]
    assert created[:2] == ("POST", BASE)
    assert [f["path"] for f in created[3]["files"]] == ["data/logger.csv", "datapackage.json"]
    puts = [c for c in archive.calls if c[0] == "PUT"]
    assert [c[1] for c in puts] == [
        "https://uploads.example/data/logger.csv",
        "https://uploads.example/datapackage.json",
    ]
    assert all(c[2]["x-amz-checksum-sha256"].startswith("b64-") for c in puts)
    assert puts[0][3] == b"t,v\n1,2\n"


def test_in_review_is_approved_once_its_wait_is_open_then_published(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archive = FakeArchive(
        [
            {"status": "checking"},
            {"status": "in-review"},
            {"status": "in-review", "callbackId": "cb-1"},
            {"status": "in-review", "callbackId": "cb-1"},
            {"status": "publishing"},
            {"status": "published", "datasetId": DATASET},
        ],
        [],
    )

    code = _run(archive, _package(tmp_path))

    assert code == 0
    assert archive.decisions() == [{"decision": "approve", "note": "seed"}]
    assert capsys.readouterr().out.splitlines()[-1] == f"https://{DOMAIN}/datasets/{DATASET}"


def test_needs_changes_stops_with_the_status_and_its_findings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archive = FakeArchive(
        [{"status": "checking"}, {"status": "needs-changes", "reportKey": "reports/x.json"}],
        [{"type": "created"}, {"type": "submitted"}, {"type": "checked", "errors": 1}],
    )

    code = _run(archive, _package(tmp_path))

    assert code == 1
    assert archive.decisions() == []
    out = capsys.readouterr().out
    assert "stopped: needs-changes" in out
    assert "error core.description: no description" in out
    assert "events: created, submitted, checked" in out


def test_it_gives_up_when_the_time_runs_out(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    archive = FakeArchive([{"status": "checking"}], [{"type": "submitted"}])
    clock = Clock()

    code = _run(archive, _package(tmp_path), clock)

    assert code == 1
    assert clock.now >= 60
    out = capsys.readouterr().out
    assert "still checking after 60 seconds" in out
    assert "events: submitted" in out


def test_the_sample_package_list_leaves_out_its_build_folder() -> None:
    files = seed.file_list(seed.SAMPLE)
    paths = [f["path"] for f in files]
    assert "datapackage.json" in paths and "checksums.sha256" in paths
    assert not [p for p in paths if p.startswith("_build/")]
    listed = (seed.SAMPLE / "checksums.sha256").read_text(encoding="utf-8").split()
    sums = dict(zip(listed[1::2], listed[0::2], strict=True))
    assert {f["path"]: f["sha256"] for f in files if f["path"] != "checksums.sha256"} == sums
