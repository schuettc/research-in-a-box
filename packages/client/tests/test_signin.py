import base64
import hashlib
import json
import threading
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from archive_client.signin import AuthConfig, SignInError, Tokens, sign_in


class Stub:
    """A local HTTP server answering each path with a status and a JSON body."""

    def __init__(self) -> None:
        self.routes: dict[str, tuple[int, Any]] = {}
        self.requests: list[tuple[str, str, bytes]] = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def _answer(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                path = urllib.parse.urlsplit(self.path).path
                stub.requests.append((self.command, path, body))
                status, answer = stub.routes.get(path, (404, {"error": "not_found"}))
                data = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = _answer
            do_POST = _answer

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        ).start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub() -> Iterator[Stub]:
    server = Stub()
    yield server
    server.close()


def browser(
    answer: Callable[[dict[str, str]], dict[str, str]],
) -> tuple[Callable[[str], bool], list[str]]:
    """A fake browser: it records the URL it was opened at and calls the callback itself."""
    opened: list[str] = []

    def open_browser(url: str) -> bool:
        opened.append(url)
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
        callback = query["redirect_uri"] + "?" + urllib.parse.urlencode(answer(query))

        def visit() -> None:
            with urllib.request.urlopen(callback, timeout=5) as response:
                response.read()

        threading.Thread(target=visit, daemon=True).start()
        return True

    return open_browser, opened


def config(stub: Stub) -> AuthConfig:
    return AuthConfig(region="us-east-1", cognito_domain=stub.url, cli_client_id="cli-123")


def test_sign_in_round_trip_returns_the_tokens_and_drops_the_refresh_token(stub: Stub) -> None:
    stub.routes["/oauth2/token"] = (
        200,
        {
            "access_token": "access",
            "id_token": "id",
            "refresh_token": "refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
        },
    )
    open_browser, opened = browser(lambda q: {"code": "the-code", "state": q["state"]})
    before = time.time()

    tokens = sign_in(config(stub), open_browser=open_browser, port=0)

    assert tokens == Tokens(access_token="access", id_token="id", expires_at=tokens.expires_at)
    assert before + 3600 <= tokens.expires_at <= time.time() + 3600
    assert not hasattr(tokens, "refresh_token")

    authorize = urllib.parse.urlsplit(opened[0])
    query = dict(urllib.parse.parse_qsl(authorize.query))
    assert authorize.path == "/oauth2/authorize"
    assert query["response_type"] == "code"
    assert query["client_id"] == "cli-123"
    assert query["code_challenge_method"] == "S256"
    assert query["redirect_uri"].startswith("http://localhost:")
    assert query["redirect_uri"].endswith("/callback")

    method, path, body = stub.requests[-1]
    form = dict(urllib.parse.parse_qsl(body.decode()))
    assert (method, path) == ("POST", "/oauth2/token")
    assert form["grant_type"] == "authorization_code"
    assert form["code"] == "the-code"
    assert form["client_id"] == "cli-123"
    assert form["redirect_uri"] == query["redirect_uri"]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(form["code_verifier"].encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert challenge == query["code_challenge"]


def test_sign_in_refuses_a_state_mismatch(stub: Stub) -> None:
    open_browser, _ = browser(lambda q: {"code": "the-code", "state": "someone-else"})

    with pytest.raises(SignInError, match="state"):
        sign_in(config(stub), open_browser=open_browser, port=0)

    assert stub.requests == []


def test_sign_in_reports_an_error_callback(stub: Stub) -> None:
    open_browser, _ = browser(
        lambda q: {"error": "access_denied", "error_description": "no", "state": q["state"]}
    )

    with pytest.raises(SignInError, match="access_denied"):
        sign_in(config(stub), open_browser=open_browser, port=0)


def test_sign_in_reports_a_refused_exchange(stub: Stub) -> None:
    stub.routes["/oauth2/token"] = (400, {"error": "invalid_grant"})
    open_browser, _ = browser(lambda q: {"code": "the-code", "state": q["state"]})

    with pytest.raises(SignInError, match="invalid_grant"):
        sign_in(config(stub), open_browser=open_browser, port=0)


def test_sign_in_times_out_when_no_callback_comes(stub: Stub) -> None:
    with pytest.raises(SignInError, match="timed out"):
        sign_in(config(stub), open_browser=lambda url: True, port=0, timeout=0.3)


def test_https_is_the_default_scheme_for_a_bare_cognito_domain() -> None:
    opened: list[str] = []

    def open_browser(url: str) -> bool:
        opened.append(url)
        return True

    bare = AuthConfig(
        region="us-east-1",
        cognito_domain="example.auth.us-east-1.amazoncognito.com",
        cli_client_id="cli",
    )
    with pytest.raises(SignInError):
        sign_in(bare, open_browser=open_browser, port=0, timeout=0.1)

    assert opened[0].startswith(
        "https://example.auth.us-east-1.amazoncognito.com/oauth2/authorize?"
    )


def test_from_archive_reads_the_auth_config(stub: Stub) -> None:
    stub.routes["/auth-config.json"] = (
        200,
        {
            "region": "us-east-2",
            "cognitoDomain": "archive.auth.us-east-2.amazoncognito.com",
            "webClientId": "web-1",
            "cliClientId": "cli-1",
        },
    )

    assert AuthConfig.from_archive(stub.url + "/") == AuthConfig(
        region="us-east-2",
        cognito_domain="archive.auth.us-east-2.amazoncognito.com",
        cli_client_id="cli-1",
    )


def test_from_archive_refuses_a_document_missing_a_field(stub: Stub) -> None:
    stub.routes["/auth-config.json"] = (200, {"region": "us-east-2"})

    with pytest.raises(SignInError, match="cognitoDomain"):
        AuthConfig.from_archive(stub.url)


def test_from_archive_refuses_an_archive_with_no_auth_config(stub: Stub) -> None:
    with pytest.raises(SignInError, match="404"):
        AuthConfig.from_archive(stub.url)
