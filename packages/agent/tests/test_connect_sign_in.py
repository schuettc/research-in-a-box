import asyncio
import base64
import json
import socket
import time
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from archive_agent import server, state
from archive_agent.errors import NotConnected, Refused, SignInFailed, Unreachable
from archive_agent.state import Session
from archive_client.signin import AuthConfig, SignInError, Tokens


def jwt(claims: dict[str, Any]) -> str:
    def part(value: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'none'})}.{part(claims)}.signature"


def test_the_saved_file_follows_xdg_config_home(config_home: Path) -> None:
    assert state.config_file() == config_home / "research-in-a-box" / "archive.json"


def test_connect_checks_the_archive_answers_then_saves_its_url(
    archive: Any, config_home: Path
) -> None:
    session = Session()

    answer = server.connect(session, archive.url + "/")

    assert answer["url"] == archive.url
    saved = json.loads((config_home / "research-in-a-box" / "archive.json").read_text())
    assert saved == {"url": archive.url}
    assert Session().url() == archive.url
    assert [(s.method, s.path) for s in archive.seen] == [("GET", "/auth-config.json")]


def test_connect_saves_nothing_when_the_archive_cant_be_reached(config_home: Path) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed = f"http://127.0.0.1:{sock.getsockname()[1]}"

    with pytest.raises(Unreachable):
        server.connect(Session(), closed)

    assert not (config_home / "research-in-a-box" / "archive.json").exists()


def test_connect_refuses_a_site_that_isnt_an_archive(stub: Any, config_home: Path) -> None:
    stub.json("GET /auth-config.json", {"hello": "world"})

    with pytest.raises(Refused, match="research archive"):
        server.connect(Session(), stub.url)

    assert not (config_home / "research-in-a-box" / "archive.json").exists()


def test_connect_refuses_an_address_that_isnt_a_web_address(config_home: Path) -> None:
    with pytest.raises(NotConnected, match="http"):
        server.connect(Session(), "archive.example.org")


def test_a_tool_before_connect_says_to_call_connect() -> None:
    with pytest.raises(NotConnected, match="connect"):
        server.sign_in(Session())


def test_connect_forgets_the_last_archives_sign_in(archive: Any, tokens: Tokens) -> None:
    session = Session(tokens=tokens)

    server.connect(session, archive.url)

    assert session.tokens is None


def test_sign_in_answers_the_email_and_groups_and_keeps_the_tokens(archive: Any) -> None:
    seen: list[AuthConfig] = []
    signed = Tokens(
        access_token="access",
        id_token=jwt({"email": "ana@example.org", "cognito:groups": ["contributor", "curator"]}),
        expires_at=time.time() + 3600,
    )

    def fake_sign_in(config: AuthConfig) -> Tokens:
        seen.append(config)
        return signed

    session = Session(sign_in=fake_sign_in)
    server.connect(session, archive.url)

    answer = server.sign_in(session)

    assert answer["email"] == "ana@example.org"
    assert answer["groups"] == ["contributor", "curator"]
    assert "expires_at" in answer
    assert session.tokens == signed
    assert seen == [
        AuthConfig(
            region="us-east-1",
            cognito_domain="archive.auth.us-east-1.amazoncognito.com",
            cli_client_id="cli",
        )
    ]


def test_sign_in_with_no_groups_answers_an_empty_list(archive: Any) -> None:
    signed = Tokens(access_token="a", id_token=jwt({"email": "e@x"}), expires_at=time.time() + 60)
    session = Session(sign_in=lambda config: signed)
    server.connect(session, archive.url)

    assert server.sign_in(session)["groups"] == []


def test_a_failed_sign_in_says_why_and_keeps_no_tokens(archive: Any) -> None:
    def refused(config: AuthConfig) -> Tokens:
        raise SignInError("sign-in failed: access_denied")

    session = Session(sign_in=refused)
    server.connect(session, archive.url)

    with pytest.raises(SignInFailed, match="access_denied"):
        server.sign_in(session)

    assert session.tokens is None


def test_the_server_lists_its_tools_and_answers_errors_in_plain_words() -> None:
    mcp = server.build(Session())

    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert {
        "connect",
        "sign_in",
        "search",
        "get_dataset",
        "download",
        "diagnose",
        "edit_manifest",
    } <= names

    # An anticipated error: the protocol layer answers it as is_error with this message.
    with pytest.raises(ToolError, match="No archive is set yet.*call connect"):
        asyncio.run(mcp.call_tool("sign_in", {}))
