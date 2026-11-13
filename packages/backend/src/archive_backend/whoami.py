"""GET /api/whoami: the signed-in user's id, email and groups, from the Cognito authorizer."""

import json
from typing import Any


def _groups(value: object) -> list[str]:
    # API Gateway passes the token's claims as strings, so a list of groups arrives joined.
    if isinstance(value, list):
        return [str(group) for group in value]
    if not isinstance(value, str):
        return []
    return [group.strip() for group in value.strip("[]").split(",") if group.strip()]


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    claims: dict[str, Any] = event["requestContext"]["authorizer"]["claims"]
    body = {
        "sub": claims.get("sub"),
        "email": claims.get("email"),
        "groups": _groups(claims.get("cognito:groups")),
    }
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }
