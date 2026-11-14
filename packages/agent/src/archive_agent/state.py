"""What the server remembers: the archive's URL on disk, the sign-in tokens in memory only."""

import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from archive_agent.archive import Archive
from archive_agent.errors import NotConnected
from archive_client.signin import AuthConfig, Tokens, sign_in


def config_file() -> Path:
    """`archive.json` under `$XDG_CONFIG_HOME/research-in-a-box`, else `~/.config/...`."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "research-in-a-box" / "archive.json"


def saved_url() -> str | None:
    """The saved archive URL, or None when there is none or the file can't be read."""
    try:
        document = json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    url = document.get("url") if isinstance(document, dict) else None
    return url if isinstance(url, str) and url else None


def save_url(url: str) -> Path:
    """Save the archive URL, replacing the file whole."""
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=".archive.", delete=False
    ) as stream:
        json.dump({"url": url}, stream)
        stream.write("\n")
    os.replace(stream.name, path)
    return path


@dataclass
class Session:
    """One server's state: tokens in memory, and the sign-in to run (a stand-in in tests)."""

    tokens: Tokens | None = None
    sign_in: Callable[[AuthConfig], Tokens] = field(default=sign_in)

    def url(self) -> str:
        url = saved_url()
        if url is None:
            raise NotConnected(
                "No archive is set yet. Ask the person for their archive's web address, then "
                "call connect with it."
            )
        return url

    def archive(self) -> Archive:
        return Archive(self.url(), self.tokens)
