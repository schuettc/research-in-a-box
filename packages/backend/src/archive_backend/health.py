"""GET /api/health: answers ok, with no auth."""

from typing import Any


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": '{"status": "ok"}',
    }
