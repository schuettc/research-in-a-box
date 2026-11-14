"""The plain errors a tool answers. Each names its cause and what to do next.

They are the MCP server's anticipated tool errors, so the message reaches the model as is.
"""

from mcp.server.mcpserver.exceptions import ToolError


class ArchiveError(ToolError):
    """A tool couldn't do what it was asked; the message says why in plain words."""


class NotConnected(ArchiveError):
    """No archive is set yet, or the address given isn't one."""


class Unreachable(ArchiveError):
    """The archive can't be reached: no connection, or it timed out."""


class SignedOut(ArchiveError):
    """No sign-in, an expired one, or the archive answered 401."""


class NotAllowed(ArchiveError):
    """The archive answered 403: the account lacks the group the route needs."""


class Conflict(ArchiveError):
    """The archive answered 409: the request doesn't fit the record's current state."""


class Refused(ArchiveError):
    """The archive answered any other error, or something that isn't what it should be."""


class SignInFailed(ArchiveError):
    """The browser sign-in didn't finish."""


class LocalError(ArchiveError):
    """A local folder or file can't be read or written as asked."""
