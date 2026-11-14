import hashlib
import json

import pytest

import smoke

DOMAIN = "d111.cloudfront.net"
DATASET = "stream-temperature-sample"
FILE_BODY = b"timestamp,temperature\n2024-06-01T00:00,12.5\n"
FILE_HASH = hashlib.sha256(FILE_BODY).hexdigest()

HTML = {"content-type": "text/html; charset=utf-8"}
JSON = {"content-type": "application/json"}


def _json(value: object) -> tuple[int, dict[str, str], bytes]:
    return 200, JSON, json.dumps(value).encode()


def _answers(
    file_hash: str = f"sha256:{FILE_HASH}",
) -> dict[str, tuple[int, dict[str, str], bytes]]:
    base = f"https://{DOMAIN}"
    return {
        f"{base}/": (200, HTML, b"<!doctype html><html></html>"),
        f"{base}/api/health": _json({"status": "ok"}),
        f"{base}/api/search?q=stream": _json(
            {"rows": [{"id": DATASET, "version": 1}], "total": 1, "facets": {}}
        ),
        f"{base}/datasets/{DATASET}": (200, HTML, b"<html>Stream temperature</html>"),
        f"{base}/api/datasets/{DATASET}": _json({"id": DATASET, "currentVersion": 1}),
        f"{base}/data/{DATASET}/1/datapackage.json": _json(
            {
                "resources": [
                    {"name": "remote", "path": "https://example.org/x.csv"},
                    {"name": "parts", "path": ["data/a.csv", "data/b.csv"], "hash": "sha256:00"},
                    {"name": "nohash", "path": "data/methods.md"},
                    {"name": "logger", "path": "data/logger.csv", "hash": file_hash},
                ]
            }
        ),
        f"{base}/data/{DATASET}/1/data/logger.csv": (200, {"content-type": "text/csv"}, FILE_BODY),
    }


class FakeFetch:
    def __init__(self, answers: dict[str, tuple[int, dict[str, str], bytes]]) -> None:
        self.answers = answers
        self.urls: list[str] = []

    def __call__(self, url: str) -> tuple[int, dict[str, str], bytes]:
        self.urls.append(url)
        if url not in self.answers:
            return 404, JSON, b'{"message": "not found"}'
        return self.answers[url]


def test_every_check_passes_on_a_seeded_archive(capsys: pytest.CaptureFixture[str]) -> None:
    fetch = FakeFetch(_answers())

    assert smoke.main([DOMAIN], fetch=fetch) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "site: ok",
        "health: ok",
        "search: ok",
        "dataset page: ok",
        "download: ok",
    ]
    assert fetch.urls[-1] == f"https://{DOMAIN}/data/{DATASET}/1/data/logger.csv"


def test_with_no_seed_the_dataset_checks_are_skipped_and_it_passes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    answers = _answers()
    answers[f"https://{DOMAIN}/api/search?q=stream"] = _json({"rows": [], "total": 0, "facets": {}})

    assert smoke.main([DOMAIN], fetch=FakeFetch(answers)) == 0
    assert capsys.readouterr().out.splitlines() == [
        "site: ok",
        "health: ok",
        "search: skipped: no seed yet",
        "dataset page: skipped: no seed yet",
        "download: skipped: no seed yet",
    ]


def test_a_wrong_hash_fails_the_download(capsys: pytest.CaptureFixture[str]) -> None:
    fetch = FakeFetch(_answers(file_hash="sha256:" + "0" * 64))

    assert smoke.main([DOMAIN], fetch=fetch) == 1
    last = capsys.readouterr().out.splitlines()[-1]
    assert last.startswith("download: failed: data/logger.csv has SHA-256 ")
    assert "0" * 64 in last


def test_a_500_from_health_fails_and_the_other_checks_still_run(
    capsys: pytest.CaptureFixture[str],
) -> None:
    answers = _answers()
    answers[f"https://{DOMAIN}/api/health"] = (500, JSON, b'{"message": "Internal server error"}')

    assert smoke.main([DOMAIN], fetch=FakeFetch(answers)) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[1] == "health: failed: /api/health answered 500"
    assert lines[0] == "site: ok"
    assert lines[2:] == ["search: ok", "dataset page: ok", "download: ok"]


def test_another_dataset_can_be_named(capsys: pytest.CaptureFixture[str]) -> None:
    answers = _answers()
    fetch = FakeFetch(answers)

    assert smoke.main([DOMAIN, "--dataset", "other"], fetch=fetch) == 0
    assert "search: skipped: no seed yet" in capsys.readouterr().out
