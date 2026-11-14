import base64
import hashlib
import json
import shutil
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

from archive_agent import state, submit
from archive_agent.errors import Conflict, NotAllowed, Refused
from archive_agent.state import Session
from archive_client.signin import Tokens

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"

# `stub` is the local archive from conftest.py; test modules can't import its class.


@pytest.fixture
def package(tmp_path: Path) -> Path:
    root = tmp_path / "sample"
    shutil.copytree(SAMPLE, root)
    return root


@pytest.fixture
def connected(stub: Any) -> Any:
    state.save_url(stub.url)
    return stub


@pytest.fixture
def session(tokens: Tokens) -> Session:
    return Session(tokens=tokens)


def listed(root: Path) -> list[str]:
    """The paths in checksums.sha256, then checksums.sha256 itself."""
    lines = (root / "checksums.sha256").read_text().splitlines()
    return [line.split("  ", 1)[1] for line in lines if line.strip()] + ["checksums.sha256"]


def checksum(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def answer_uploads(stub: Any, route: str, root: Path, sid: str, round: int) -> None:
    """Answer `route` as submissions.py does, and accept each presigned PUT on the stub."""
    uploads = []
    for path in listed(root):
        link = f"/put/{sid}/{round}/{path}"
        stub.raw(f"PUT {link}", b"")
        uploads.append(
            {
                "path": path,
                "url": stub.url + urllib.parse.quote(link),
                "headers": {"x-amz-checksum-sha256": checksum((root / path).read_bytes())},
            }
        )
    stub.json(route, {"submissionId": sid, "round": round, "uploads": uploads}, 201)


def test_submit_refuses_a_package_with_an_error_finding(
    connected: Any, package: Path, session: Session
) -> None:
    (package / "data" / "logger.csv").write_text("changed\n")

    with pytest.raises(Refused, match="3 error findings"):
        submit.submit(session, str(package))

    assert connected.seen == []


def test_submit_sends_exactly_the_checksummed_files_each_with_its_checksum_header(
    connected: Any, package: Path, session: Session
) -> None:
    answer_uploads(connected, "POST /api/submissions", package, "s1", 1)
    connected.json(
        "POST /api/submissions/s1/submit",
        {"submissionId": "s1", "round": 1, "status": "checking"},
        202,
    )

    result = submit.submit(session, str(package))

    assert result == {"id": "s1", "round": 1, "status": "checking"}
    create = connected.seen[0]
    assert (create.method, create.path) == ("POST", "/api/submissions")
    assert create.headers["authorization"] == "id-token"
    files = json.loads(create.body)["files"]
    assert [f["path"] for f in files] == listed(package)
    for f in files:
        data = (package / f["path"]).read_bytes()
        assert f == {
            "path": f["path"],
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    puts = [s for s in connected.seen if s.method == "PUT"]
    assert sorted(p.path for p in puts) == sorted(f"/put/s1/1/{p}" for p in listed(package))
    for put in puts:
        path = put.path.removeprefix("/put/s1/1/")
        data = (package / path).read_bytes()
        assert put.body == data
        assert put.headers["x-amz-checksum-sha256"] == checksum(data)
        assert "authorization" not in put.headers
    assert (connected.seen[-1].method, connected.seen[-1].path) == (
        "POST",
        "/api/submissions/s1/submit",
    )


def test_submit_with_a_submission_sends_the_next_round_through_uploads(
    connected: Any, package: Path, session: Session
) -> None:
    answer_uploads(connected, "POST /api/submissions/s1/uploads", package, "s1", 2)
    connected.json(
        "POST /api/submissions/s1/submit",
        {"submissionId": "s1", "round": 2, "status": "checking"},
        202,
    )

    result = submit.submit(session, str(package), submission="s1")

    assert result == {"id": "s1", "round": 2, "status": "checking"}
    assert [s.path for s in connected.seen if s.method == "POST"] == [
        "/api/submissions/s1/uploads",
        "/api/submissions/s1/submit",
    ]


def test_submit_stops_at_a_failed_upload_and_does_not_submit(
    connected: Any, package: Path, session: Session
) -> None:
    answer_uploads(connected, "POST /api/submissions", package, "s1", 1)
    connected.raw("PUT /put/s1/1/data/logger.csv", b"<Error>BadDigest</Error>", 400)

    with pytest.raises(Refused, match="400"):
        submit.submit(session, str(package))

    assert "/api/submissions/s1/submit" not in [s.path for s in connected.seen]


def test_submit_names_the_contributor_group_on_a_403(
    connected: Any, package: Path, session: Session
) -> None:
    connected.json("POST /api/submissions", {"error": "needs the contributor group"}, 403)

    with pytest.raises(NotAllowed, match="`contributor` group"):
        submit.submit(session, str(package))


def test_submissions_with_queue_reads_the_curator_queue_stale_first(
    connected: Any, session: Session
) -> None:
    rows = [
        {"submissionId": "a", "status": "in-review", "stale": False, "createdAt": "2026-11-02"},
        {"submissionId": "b", "status": "in-review", "stale": True, "createdAt": "2026-11-03"},
        {"submissionId": "c", "status": "in-review", "stale": False, "createdAt": "2026-11-01"},
    ]
    connected.json("GET /api/submissions", {"submissions": rows})

    result = submit.submissions(session, queue=True)

    assert [r["submissionId"] for r in result["submissions"]] == ["b", "c", "a"]
    assert connected.seen[0].query == {"status": ["in-review"]}


def test_submissions_with_no_arguments_reads_your_own(connected: Any, session: Session) -> None:
    connected.json("GET /api/submissions", {"submissions": []})

    assert submit.submissions(session) == {"submissions": []}
    assert connected.seen[0].query == {"mine": ["1"]}


def test_submissions_with_an_id_reads_one(connected: Any, session: Session) -> None:
    report = {"findings": [{"ruleId": "structure.hash-mismatch", "severity": "error"}]}
    connected.json("GET /reports/s1/1.json", report)
    body = {
        "submission": {"submissionId": "s1", "status": "needs-changes"},
        "events": [{"type": "decided", "note": "Add units."}],
        "reportUrl": connected.url + "/reports/s1/1.json",
    }
    connected.json("GET /api/submissions/s1", body)

    assert submit.submissions(session, id="s1") == {**body, "report": report}
    assert "authorization" not in connected.seen[1].headers


def test_submissions_keeps_the_report_link_when_the_report_cant_be_read(
    connected: Any, session: Session
) -> None:
    body = {
        "submission": {"submissionId": "s1", "status": "in-review"},
        "events": [],
        "reportUrl": connected.url + "/reports/gone.json",
    }
    connected.json("GET /api/submissions/s1", body)

    assert submit.submissions(session, id="s1") == {**body, "report": None}


def test_the_queue_names_the_curator_group_on_a_403(connected: Any, session: Session) -> None:
    connected.json("GET /api/submissions", {"error": "needs the curator group"}, 403)

    with pytest.raises(NotAllowed, match="`curator` group"):
        submit.submissions(session, queue=True)


def test_decide_posts_the_decision_and_note(connected: Any, session: Session) -> None:
    connected.json(
        "POST /api/submissions/s1/decision", {"submissionId": "s1", "decision": "approve"}, 202
    )

    result = submit.decide(session, "s1", "approve", "Looks complete.")

    assert result == {"submissionId": "s1", "decision": "approve"}
    assert json.loads(connected.seen[0].body) == {"decision": "approve", "note": "Looks complete."}


def test_decide_refuses_an_unknown_decision_without_sending(
    connected: Any, session: Session
) -> None:
    with pytest.raises(Refused, match="approve, reject or request-changes"):
        submit.decide(session, "s1", "maybe", "")

    assert connected.seen == []


def test_decide_names_the_curator_group_on_a_403(connected: Any, session: Session) -> None:
    connected.json("POST /api/submissions/s1/decision", {"error": "needs the curator group"}, 403)

    with pytest.raises(NotAllowed, match="`curator` group"):
        submit.decide(session, "s1", "reject", "Out of scope.")


def test_decide_passes_on_the_archives_conflict(connected: Any, session: Session) -> None:
    connected.json("POST /api/submissions/s1/decision", {"error": "not in review (published)"}, 409)

    with pytest.raises(Conflict, match="not in review"):
        submit.decide(session, "s1", "approve", "")


def test_submission_files_answers_the_round_and_links(connected: Any, session: Session) -> None:
    body = {
        "round": 2,
        "files": [
            {"path": "datapackage.json", "size": 10, "sha256": "ab" * 32, "url": "https://x/y"}
        ],
    }
    connected.json("GET /api/submissions/s1/files", body)

    assert submit.submission_files(session, "s1") == body
    assert connected.seen[0].headers["authorization"] == "id-token"


def test_submission_files_says_a_submission_outside_review_isnt_in_review(
    connected: Any, session: Session
) -> None:
    connected.json("GET /api/submissions/s1/files", {"error": "not in review (draft)"}, 409)

    with pytest.raises(Conflict, match="s1 isn't in review"):
        submit.submission_files(session, "s1")


def test_submission_files_names_the_curator_group_on_a_403(
    connected: Any, session: Session
) -> None:
    connected.json("GET /api/submissions/s1/files", {"error": "needs the curator group"}, 403)

    with pytest.raises(NotAllowed, match="`curator` group"):
        submit.submission_files(session, "s1")
