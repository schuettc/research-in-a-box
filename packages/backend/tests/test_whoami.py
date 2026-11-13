import json

from archive_backend import whoami


def _event(claims: dict[str, str]) -> dict[str, object]:
    return {"requestContext": {"authorizer": {"claims": claims}}}


def test_whoami_returns_sub_email_and_groups() -> None:
    response = whoami.handler(
        _event({"sub": "u-1", "email": "a@example.org", "cognito:groups": "curator,admin"}),
        object(),
    )

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {
        "sub": "u-1",
        "email": "a@example.org",
        "groups": ["curator", "admin"],
    }

    no_groups = whoami.handler(_event({"sub": "u-2", "email": "b@example.org"}), object())
    assert json.loads(no_groups["body"])["groups"] == []
