"""Cognito lookups for the curation screens: user ids to email addresses, and the curators.

The token carries only the caller's own id and email; events and submissions name people by
their Cognito `sub`. These read the user pool with `ListUsers` (one call per id, filtered on
`sub`) and `ListUsersInGroup`.
"""

from __future__ import annotations

import re
from typing import Any, Protocol

MAX_PEOPLE = 50
CURATOR_GROUP = "curator"
# Cognito's subs are UUIDs; anything else could change the filter's meaning.
SUB = re.compile(r"[A-Za-z0-9-]{1,128}")


class Cognito(Protocol):
    def list_users(self, **kwargs: Any) -> dict[str, Any]: ...
    def list_users_in_group(self, **kwargs: Any) -> dict[str, Any]: ...


def _attributes(user: dict[str, Any]) -> dict[str, str]:
    return {a["Name"]: a["Value"] for a in user.get("Attributes", [])}


def emails(cognito: Cognito, pool: str, subs: list[str]) -> dict[str, dict[str, str]]:
    """Each known id's email; an id the pool doesn't know, or without an email, is left out."""
    found: dict[str, dict[str, str]] = {}
    for sub in dict.fromkeys(subs):
        users = cognito.list_users(UserPoolId=pool, Filter=f'sub = "{sub}"', Limit=1)["Users"]
        for user in users:
            attributes = _attributes(user)
            if attributes.get("sub") == sub and "email" in attributes:
                found[sub] = {"email": attributes["email"]}
    return found


def curators(cognito: Cognito, pool: str) -> list[dict[str, str]]:
    """Every member of the curator group, as its id and email."""
    listed: list[dict[str, str]] = []
    query: dict[str, Any] = {"UserPoolId": pool, "GroupName": CURATOR_GROUP}
    while True:
        page = cognito.list_users_in_group(**query)
        for user in page.get("Users", []):
            attributes = _attributes(user)
            if "sub" in attributes:
                listed.append({"sub": attributes["sub"], "email": attributes.get("email", "")})
        token = page.get("NextToken")
        if not token:
            return listed
        query["NextToken"] = token
