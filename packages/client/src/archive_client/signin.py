"""Browser sign-in to an archive: authorization code with PKCE through its `cli` app client.

The browser opens Cognito's managed login; a one-shot listener on
`http://localhost:8765/callback` takes the code, which is exchanged for the one-hour access and
ID tokens. The refresh token is thrown away, so tokens live only as long as the caller keeps
them.
"""

import base64
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Self

CALLBACK_PORT = 8765
TIMEOUT = 300.0
"""Seconds to wait for the browser to come back to the callback."""
REQUEST_TIMEOUT = 10.0
"""Seconds one connection to the listener may take, so a silent one can't hold it."""

_PAGE = (
    b"<!doctype html><title>Signed in</title>"
    b"<p>You can close this tab and go back to your session.</p>"
)


class SignInError(Exception):
    """Sign-in didn't finish: the callback, the token exchange or the archive refused it."""


@dataclass(frozen=True)
class AuthConfig:
    """Where and how to sign in to one archive."""

    region: str
    cognito_domain: str
    cli_client_id: str

    @classmethod
    def from_archive(cls, url: str, *, timeout: float = 10.0) -> Self:
        """Read the archive's public `/auth-config.json`.

        Raises SignInError when the archive answers with an error or the document lacks a
        field, and OSError when the archive can't be reached.
        """
        address = url.rstrip("/") + "/auth-config.json"
        try:
            with urllib.request.urlopen(address, timeout=timeout) as response:
                document = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise SignInError(f"{address} answered {exc.code}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise SignInError(f"{address} is not JSON") from exc
        if not isinstance(document, dict):
            raise SignInError(f"{address} is not a JSON object")
        values = []
        for key in ("region", "cognitoDomain", "cliClientId"):
            value = document.get(key)
            if not isinstance(value, str) or not value:
                raise SignInError(f"{address} has no {key}")
            values.append(value)
        return cls(region=values[0], cognito_domain=values[1], cli_client_id=values[2])

    @property
    def base_url(self) -> str:
        """The managed login's base URL: https unless the domain names its own scheme."""
        domain = self.cognito_domain.rstrip("/")
        if domain.startswith(("https://", "http://")):
            return domain
        return f"https://{domain}"


@dataclass(frozen=True)
class Tokens:
    """The one-hour tokens from a sign-in. `expires_at` is seconds since the epoch."""

    access_token: str
    id_token: str
    expires_at: float


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class _Callback(HTTPServer):
    params: dict[str, str] | None = None


class _Handler(BaseHTTPRequestHandler):
    server: _Callback

    def setup(self) -> None:
        self.request.settimeout(REQUEST_TIMEOUT)
        super().setup()

    def do_GET(self) -> None:
        parts = urllib.parse.urlsplit(self.path)
        if parts.path != "/callback":
            self.send_error(404)
            return
        self.server.params = dict(urllib.parse.parse_qsl(parts.query))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(_PAGE)))
        self.end_headers()
        self.wfile.write(_PAGE)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def _wait(server: _Callback, timeout: float) -> dict[str, str]:
    deadline = time.monotonic() + timeout
    while server.params is None:
        left = deadline - time.monotonic()
        if left <= 0:
            raise SignInError("sign-in timed out waiting for the browser")
        server.timeout = left
        server.handle_request()
    return server.params


def _exchange(config: AuthConfig, code: str, redirect_uri: str, verifier: str) -> Tokens:
    form = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "client_id": config.cli_client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        }
    ).encode("ascii")
    request = urllib.request.Request(
        config.base_url + "/oauth2/token",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            answer = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise SignInError(f"the token exchange was refused ({exc.code}): {detail}") from exc
    except OSError as exc:
        raise SignInError(f"the token endpoint can't be reached: {exc}") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise SignInError("the token endpoint answered something that isn't JSON") from exc
    try:
        return Tokens(
            access_token=str(answer["access_token"]),
            id_token=str(answer["id_token"]),
            expires_at=time.time() + float(answer["expires_in"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SignInError(f"the token endpoint's answer lacks {exc}") from exc


def sign_in(
    config: AuthConfig,
    *,
    open_browser: Callable[[str], bool] = webbrowser.open,
    port: int = CALLBACK_PORT,
    timeout: float = TIMEOUT,
) -> Tokens:
    """Sign in through the browser and return the access and ID tokens.

    Raises SignInError on a state mismatch, an error callback, a refused exchange or the
    timeout. `port` stays 8765 outside tests: it is the `cli` client's registered callback.
    """
    verifier, challenge = _pkce()
    state = secrets.token_urlsafe(32)
    try:
        listener = _Callback(("127.0.0.1", port), _Handler)
    except OSError as exc:
        raise SignInError(
            f"port {port} is in use: another sign-in may still be waiting; finish it in the "
            "browser or wait a few minutes"
        ) from exc
    with listener as server:
        redirect_uri = f"http://localhost:{server.server_address[1]}/callback"
        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": config.cli_client_id,
                "redirect_uri": redirect_uri,
                "scope": "openid email profile",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        authorize = f"{config.base_url}/oauth2/authorize?{query}"
        if not open_browser(authorize):
            raise SignInError(
                f"no browser could be opened to sign in; the sign-in address is {authorize}"
            )
        params = _wait(server, timeout)
    if not secrets.compare_digest(params.get("state", ""), state):
        raise SignInError("the sign-in callback's state doesn't match; try again")
    if "error" in params:
        description = params.get("error_description", "")
        raise SignInError(f"sign-in failed: {params['error']} {description}".rstrip())
    code = params.get("code")
    if not code:
        raise SignInError("the sign-in callback carried no code")
    return _exchange(config, code, redirect_uri, verifier)
