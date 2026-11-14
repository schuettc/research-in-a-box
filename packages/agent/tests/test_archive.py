import socket
import time
from typing import Any

import pytest

from archive_agent.archive import Archive
from archive_agent.errors import Conflict, NotAllowed, Refused, SignedOut, Unreachable
from archive_client.signin import Tokens

# `stub` is the local archive from conftest.py; test modules can't import its class.


def test_get_answers_json_and_passes_repeated_params(stub: Any) -> None:
    stub.json("GET /api/search", {"rows": [], "total": 0})

    answer = Archive(stub.url).get("/api/search", params={"q": "ozone", "access": ["open", "x"]})

    assert answer == {"rows": [], "total": 0}
    assert stub.seen[0].query == {"q": ["ozone"], "access": ["open", "x"]}
    assert "authorization" not in stub.seen[0].headers


def test_a_signed_in_archive_sends_the_id_token(stub: Any, tokens: Tokens) -> None:
    stub.json("GET /api/whoami", {"email": "a@b.c"})

    Archive(stub.url, tokens).get("/api/whoami", signed_in=True)

    assert stub.seen[0].headers["authorization"] == "id-token"


def test_unreachable_names_the_archive() -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"

    with pytest.raises(Unreachable, match=f"{port} can't be reached"):
        Archive(url).get("/api/search")


def test_a_signed_in_route_with_no_tokens_is_signed_out_without_calling(stub: Any) -> None:
    with pytest.raises(SignedOut, match="sign_in"):
        Archive(stub.url).get("/api/whoami", signed_in=True)

    assert stub.seen == []


def test_expired_tokens_are_signed_out_without_calling(stub: Any) -> None:
    expired = Tokens(access_token="a", id_token="i", expires_at=time.time() - 1)

    with pytest.raises(SignedOut, match="expired"):
        Archive(stub.url, expired).get("/api/whoami", signed_in=True)

    assert stub.seen == []


def test_a_401_is_signed_out(stub: Any, tokens: Tokens) -> None:
    stub.json("GET /api/whoami", {"message": "Unauthorized"}, status=401)

    with pytest.raises(SignedOut):
        Archive(stub.url, tokens).get("/api/whoami", signed_in=True)


def test_a_403_is_not_allowed_naming_the_group(stub: Any, tokens: Tokens) -> None:
    stub.json("POST /api/submissions/s1/decision", {"message": "Forbidden"}, status=403)

    with pytest.raises(NotAllowed, match="curator"):
        Archive(stub.url, tokens).post("/api/submissions/s1/decision", {}, group="curator")


def test_a_409_is_a_conflict_with_the_archives_message(stub: Any, tokens: Tokens) -> None:
    stub.json("POST /api/submissions/s1/submit", {"message": "already in review"}, status=409)

    with pytest.raises(Conflict, match="already in review"):
        Archive(stub.url, tokens).post("/api/submissions/s1/submit", {})


@pytest.mark.parametrize("status", [400, 404, 500, 502])
def test_any_other_failure_is_refused_with_the_archives_message(stub: Any, status: int) -> None:
    stub.json("GET /api/datasets/x", {"message": "no dataset x"}, status=status)

    with pytest.raises(Refused, match=f"{status}.*no dataset x"):
        Archive(stub.url).get("/api/datasets/x")


def test_a_refusal_with_a_plain_text_body_keeps_the_text(stub: Any) -> None:
    stub.raw("GET /api/datasets/x", b"Bad Gateway", status=502)

    with pytest.raises(Refused, match="Bad Gateway"):
        Archive(stub.url).get("/api/datasets/x")


def test_fetch_answers_the_bytes_of_a_path_or_an_absolute_link(stub: Any, tokens: Tokens) -> None:
    stub.raw("GET /data/x/1/a.csv", b"a,b\n")

    assert Archive(stub.url, tokens).fetch("/data/x/1/a.csv") == b"a,b\n"
    assert Archive(stub.url, tokens).fetch(stub.url + "/data/x/1/a.csv") == b"a,b\n"
    # `/data` is public and a presigned link carries its own signature, so no token goes.
    assert all("authorization" not in seen.headers for seen in stub.seen)
