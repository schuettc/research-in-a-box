import json

from archive_backend import health


def test_health_answers_ok() -> None:
    response = health.handler({}, object())

    assert response["statusCode"] == 200
    assert response["headers"] == {"content-type": "application/json"}
    assert json.loads(response["body"]) == {"status": "ok"}
