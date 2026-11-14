import json
import threading
import time
import urllib.parse
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from archive_client.signin import Tokens


@dataclass
class Seen:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]
    body: bytes


@dataclass
class Answer:
    status: int
    body: bytes
    content_type: str = "application/json"


@dataclass
class Stub:
    """A local archive: each `METHOD /path` answers a status and a body; every request is kept."""

    url: str = ""
    routes: dict[str, Answer] = field(default_factory=dict)
    seen: list[Seen] = field(default_factory=list)

    def json(self, route: str, body: Any, status: int = 200) -> None:
        self.routes[route] = Answer(status, json.dumps(body).encode())

    def raw(self, route: str, body: bytes, status: int = 200) -> None:
        self.routes[route] = Answer(status, body, "application/octet-stream")


@pytest.fixture
def stub() -> Iterator[Stub]:
    archive = Stub()

    class Handler(BaseHTTPRequestHandler):
        def _answer(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            parts = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(parts.path)
            archive.seen.append(
                Seen(
                    self.command,
                    path,
                    urllib.parse.parse_qs(parts.query),
                    {k.lower(): v for k, v in self.headers.items()},
                    body,
                )
            )
            answer = archive.routes.get(
                f"{self.command} {path}", Answer(404, b'{"message": "Not found"}')
            )
            self.send_response(answer.status)
            self.send_header("Content-Type", answer.content_type)
            self.send_header("Content-Length", str(len(answer.body)))
            self.end_headers()
            self.wfile.write(answer.body)

        do_GET = _answer
        do_POST = _answer
        do_PUT = _answer

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    archive.url = f"http://127.0.0.1:{server.server_address[1]}"
    threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    ).start()
    yield archive
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every test saves its archive URL under a temporary folder."""
    home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    return home


@pytest.fixture
def tokens() -> Tokens:
    """Tokens good for another hour."""
    return Tokens(access_token="access", id_token="id-token", expires_at=time.time() + 3600)


@pytest.fixture
def archive(stub: Stub) -> Stub:
    """The stub answering `/auth-config.json` as a deployed archive does."""
    stub.json(
        "GET /auth-config.json",
        {
            "region": "us-east-1",
            "cognitoDomain": "archive.auth.us-east-1.amazoncognito.com",
            "webClientId": "web",
            "cliClientId": "cli",
        },
    )
    return stub
