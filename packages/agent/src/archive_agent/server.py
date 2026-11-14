"""The MCP server, run over stdio by Claude Code from the plugin.

Each tool is a plain function taking the session, so tests call it directly; `build` registers
them on an MCPServer bound to one session.
"""

import argparse
import base64
import json
import urllib.parse
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from mcp.server.mcpserver import MCPServer

from archive_agent import __version__, state
from archive_agent.archive import Archive
from archive_agent.errors import NotConnected, Refused, SignInFailed, Unreachable
from archive_agent.state import Session
from archive_client.signin import AuthConfig, SignInError

INSTRUCTIONS = (
    "Tools for one research data archive: find and fetch datasets, check and fix a package "
    "folder locally, and submit or review datasets. Call connect once with the archive's web "
    "address. Never write to a manifest or send anything to the archive without the person's "
    "yes."
)


def _normalise(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in ("https", "http") or not parts.netloc:
        raise NotConnected(
            f"{url!r} isn't a web address. Give the archive's address with https://, "
            "such as https://d111111abcdef8.cloudfront.net."
        )
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def connect(session: Session, url: str) -> dict[str, Any]:
    """Check the archive at `url` answers, then save its address."""
    address = _normalise(url)
    document = Archive(address).get("/auth-config.json")
    if not isinstance(document, dict) or not all(
        isinstance(document.get(k), str) for k in ("region", "cognitoDomain", "cliClientId")
    ):
        raise Refused(f"{address} answered, but it doesn't look like a research archive.")
    path = state.save_url(address)
    session.tokens = None
    return {"url": address, "saved_to": str(path)}


def _claims(id_token: str) -> dict[str, Any]:
    """The ID token's claims, read for display only; the archive checks the signature."""
    try:
        payload = id_token.split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError) as exc:
        raise SignInFailed("Sign-in answered an ID token that can't be read.") from exc
    return claims if isinstance(claims, dict) else {}


def _groups(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(group) for group in value]
    if isinstance(value, str) and value:
        return value.split(",")
    return []


def sign_in(session: Session) -> dict[str, Any]:
    """Sign in through the browser; answer who you are and your groups."""
    url = session.url()
    try:
        config = AuthConfig.from_archive(url)
    except SignInError as exc:
        raise Refused(f"{url} can't start a sign-in: {exc}") from exc
    except OSError as exc:
        raise Unreachable(f"The archive at {url} can't be reached ({exc}). Retry later.") from exc
    try:
        tokens = session.sign_in(config)
    except SignInError as exc:
        raise SignInFailed(f"Sign-in didn't finish: {exc}. Call sign_in to try again.") from exc
    claims = _claims(tokens.id_token)
    session.tokens = tokens
    return {
        "email": claims.get("email"),
        "groups": _groups(claims.get("cognito:groups")),
        "expires_at": datetime.fromtimestamp(tokens.expires_at, UTC).isoformat(),
    }


def build(session: Session) -> MCPServer:
    """The MCP server with every tool bound to `session`."""
    mcp: MCPServer = MCPServer("research-archive", instructions=INSTRUCTIONS, version=__version__)

    @mcp.tool(name="connect")
    def connect_tool(url: str) -> dict[str, Any]:
        """Save the archive's web address (such as https://d111.cloudfront.net) and check it
        answers. Call once; the address is remembered across sessions."""
        return connect(session, url)

    @mcp.tool(name="sign_in")
    def sign_in_tool() -> dict[str, Any]:
        """Open the browser to sign in to the archive. Answers your email and groups. Tokens
        last an hour and are kept only while this server runs."""
        return sign_in(session)

    return mcp


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="archive-mcp",
        description="The research-in-a-box MCP server, over stdio. Claude Code starts it "
        "from the plugin; there is nothing to run by hand.",
    )
    parser.add_argument("--version", action="version", version=f"archive-mcp {__version__}")
    parser.parse_args(argv)
    build(Session()).run("stdio")
