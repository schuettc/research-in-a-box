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

from archive_agent import __version__, local, read, state, submit
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
    session.groups = []
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
    session.groups = _groups(claims.get("cognito:groups"))
    return {
        "email": claims.get("email"),
        "groups": session.groups,
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

    @mcp.tool(name="search")
    def search_tool(
        q: str | None = None,
        access: list[str] | None = None,
        license: list[str] | None = None,
        format: list[str] | None = None,
        project: list[str] | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        bbox: list[float] | None = None,
        page: int | None = None,
        size: int | None = None,
    ) -> dict[str, Any]:
        """Search the archive's published datasets; no sign-in needed. `q` is free text;
        access (open, restricted, by-request), license ids, formats and projects each match
        any of the values given; from_date and to_date (YYYY-MM-DD) bound the data's dates;
        bbox is [west, south, east, north]. Answers one page of rows, the total and a count
        per value of access, license, format and project. size is at most 100."""
        return read.search(
            session, q, access, license, format, project, from_date, to_date, bbox, page, size
        )

    @mcp.tool(name="get_dataset")
    def get_dataset_tool(id: str, version: int | None = None) -> dict[str, Any]:
        """One dataset: its title and access, the manifest (datapackage.json) and files of a
        version (the current one by default) and a citation built from the manifest."""
        return read.get_dataset(session, id, version)

    @mcp.tool(name="download")
    def download_tool(id: str, version: int, paths: list[str], to: str) -> dict[str, Any]:
        """Download the named files (paths as listed in the version's files) of one version
        into the local folder `to`, checking each against its recorded SHA-256. Restricted
        files need sign_in first. Answers what was written and anything that failed."""
        return read.download(session, id, version, paths, to)

    @mcp.tool(name="diagnose")
    def diagnose_tool(folder: str) -> dict[str, Any]:
        """Check a local package folder with cruise, as the archive's ingest does. Answers
        the structure verdict, the quality counts and score, every finding (errors block
        publishing; warnings and notes don't) and the verdict line. Needs no network."""
        return local.diagnose(folder)

    @mcp.tool(name="edit_manifest")
    def edit_manifest_tool(folder: str, edits: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply edits the person approved to a package folder's datapackage.json, then
        regenerate README.md and checksums.sha256. Each edit is {"target", "value"}, plus
        "resource" and "column" for a column. Package targets: title, description, keywords,
        licenses, archive:rightsStatus, archive:temporalCoverage, archive:spatialCoverage,
        archive:methods, contributors. Column targets: title, description, archive:unit. A
        null value removes the property. If any edit fails, nothing is written and each
        failing edit is named. Needs no network."""
        return local.edit_manifest(folder, edits)

    @mcp.tool(name="submit")
    def submit_tool(folder: str, submission: str | None = None) -> dict[str, Any]:
        """Submit a package folder for review, only with the person's yes. Runs diagnose
        first and refuses on any error finding. Uploads every file in checksums.sha256 plus
        that file, then sends it to review. With `submission` (an id that needs changes), it
        is that submission's next round. Answers the id, round and status. Needs sign_in and
        the contributor group."""
        return submit.submit(session, folder, submission)

    @mcp.tool(name="submissions")
    def submissions_tool(id: str | None = None, queue: bool = False) -> dict[str, Any]:
        """With `id`, one submission: its record and status, its events (decisions and
        their notes) and its findings report. With `queue` true, the curator queue: the
        submissions in review, stale ones first. Otherwise your own submissions. Needs
        sign_in; the queue needs the curator group."""
        return submit.submissions(session, id, queue)

    @mcp.tool(name="submission_files")
    def submission_files_tool(id: str) -> dict[str, Any]:
        """The current round's files of a submission in review, each with its path, size,
        SHA-256 and a link that lasts five minutes; call again for fresh links. Needs
        sign_in and the curator group."""
        return submit.submission_files(session, id)

    @mcp.tool(name="decide")
    def decide_tool(id: str, decision: str, note: str) -> dict[str, Any]:
        """Post a curator's decision on a submission in review, only with the curator's yes
        on the exact decision and note. decision is approve, reject or request-changes; the
        note goes to the submitter. Needs sign_in and the curator group."""
        return submit.decide(session, id, decision, note)

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
