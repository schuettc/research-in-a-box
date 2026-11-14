"""The HTTP client for one archive. Every failure becomes one of the plain errors."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from archive_agent.errors import Conflict, NotAllowed, Refused, SignedOut, Unreachable
from archive_client.signin import Tokens

Params = Mapping[str, str | int | float | Sequence[str] | None]

SIGN_IN_AGAIN = "Call sign_in to sign in again, then retry."


def _message(body: bytes) -> str:
    """The archive's own message from an error answer, else its text."""
    text = body.decode("utf-8", "replace").strip()
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return text[:500]
    if isinstance(document, dict):
        for key in ("message", "detail", "error"):
            value = document.get(key)
            if isinstance(value, str) and value:
                return value
    return text[:500]


class Archive:
    """Calls one archive, sending the ID token when signed in.

    The archive's Cognito authorizer reads the ID token from the `Authorization` header (its
    routes ask for no OAuth scopes, and the backend reads the email and groups claims, which
    only the ID token carries).
    """

    def __init__(
        self,
        url: str,
        tokens: Tokens | None = None,
        *,
        timeout: float = 30.0,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.url = url.rstrip("/")
        self.tokens = tokens
        self.timeout = timeout
        self._now = now

    def _token(self, signed_in: bool) -> str | None:
        tokens = self.tokens
        if tokens is not None and tokens.expires_at > self._now():
            return tokens.id_token
        if not signed_in:
            return None
        if tokens is None:
            raise SignedOut(f"You're not signed in to {self.url}. Call sign_in, then retry.")
        raise SignedOut(f"Your sign-in to {self.url} expired. {SIGN_IN_AGAIN}")

    def _open(self, request: urllib.request.Request, group: str | None) -> bytes:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body: bytes = response.read()
                return body
        except urllib.error.HTTPError as exc:
            message = _message(exc.read())
            if exc.code == 401:
                raise SignedOut(
                    f"{self.url} says you're signed out or your sign-in expired. {SIGN_IN_AGAIN}"
                ) from exc
            if exc.code == 403:
                need = (
                    f"it needs an account in the `{group}` group"
                    if group
                    else "your account isn't allowed to do this"
                )
                raise NotAllowed(
                    f"{self.url} refused this: {need}. Ask the archive's admin if you should "
                    f"have access. ({message})"
                ) from exc
            if exc.code == 409:
                raise Conflict(f"{self.url} answered a conflict: {message}") from exc
            raise Refused(f"{self.url} refused the request ({exc.code}): {message}") from exc
        except (urllib.error.URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            raise Unreachable(
                f"The archive at {self.url} can't be reached ({reason}). Check the address and "
                "your connection, then retry. Local tools (diagnose, edit_manifest) still work."
            ) from exc

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Params | None = None,
        body: Any = None,
        signed_in: bool = False,
        group: str | None = None,
    ) -> bytes:
        """Call `path` on the archive and answer the body; `signed_in` routes need a token."""
        token = self._token(signed_in)
        address = self.url + path
        if params:
            query = {k: v for k, v in params.items() if v is not None}
            address += "?" + urllib.parse.urlencode(query, doseq=True)
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if token is not None:
            headers["Authorization"] = token
        request = urllib.request.Request(address, data=data, headers=headers, method=method)
        return self._open(request, group)

    def _json(self, raw: bytes) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise Refused(f"{self.url} answered something that isn't JSON") from exc

    def get(
        self,
        path: str,
        *,
        params: Params | None = None,
        signed_in: bool = False,
        group: str | None = None,
    ) -> Any:
        """GET `path` and answer its JSON."""
        raw = self.request("GET", path, params=params, signed_in=signed_in, group=group)
        return self._json(raw)

    def post(
        self, path: str, body: Any, *, signed_in: bool = True, group: str | None = None
    ) -> Any:
        """POST JSON to `path` and answer its JSON. Every POST the tools make needs sign-in."""
        raw = self.request("POST", path, body=body, signed_in=signed_in, group=group)
        return self._json(raw)

    def fetch(self, link: str) -> bytes:
        """The bytes at an archive path (`/data/...`) or an absolute link, sent with no token."""
        address = link if link.startswith(("https://", "http://")) else self.url + link
        return self._open(urllib.request.Request(address, method="GET"), None)
