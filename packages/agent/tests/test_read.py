import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from archive_agent import read, state
from archive_agent.errors import LocalError, Refused, SignedOut
from archive_agent.state import Session
from archive_client.signin import Tokens
from archive_contract.exports.readme import citation
from archive_contract.manifest import Manifest

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"

# `stub` is the local archive from conftest.py; test modules can't import its class.


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@pytest.fixture
def manifest() -> dict[str, Any]:
    document: dict[str, Any] = json.loads((SAMPLE / "datapackage.json").read_text())
    return document


@pytest.fixture
def connected(stub: Any) -> Any:
    state.save_url(stub.url)
    return stub


def test_search_passes_the_filters_and_answers_rows_total_and_facets(connected: Any) -> None:
    answer = {"rows": [{"id": "d1", "title": "Ozone"}], "total": 1, "facets": {"access": {}}}
    connected.json("GET /api/search", answer)

    result = read.search(
        Session(),
        q="ozone",
        access=["open"],
        license=["CC-BY-4.0"],
        format=["csv", "tif"],
        project=["p1"],
        from_date="2001-01-01",
        to_date="2010-12-31",
        bbox=[-73.5, 43.0, -71.5, 45.0],
        page=2,
        size=10,
    )

    assert result == answer
    assert connected.seen[0].query == {
        "q": ["ozone"],
        "access": ["open"],
        "license": ["CC-BY-4.0"],
        "format": ["csv", "tif"],
        "project": ["p1"],
        "from": ["2001-01-01"],
        "to": ["2010-12-31"],
        "bbox": ["-73.5,43.0,-71.5,45.0"],
        "page": ["2"],
        "size": ["10"],
    }


def test_search_leaves_out_the_filters_not_given(connected: Any) -> None:
    connected.json("GET /api/search", {"rows": [], "total": 0, "facets": {}})

    read.search(Session(), q="soil")

    assert connected.seen[0].query == {"q": ["soil"]}


def test_get_dataset_answers_the_dataset_its_manifest_files_and_citation(
    connected: Any, manifest: dict[str, Any]
) -> None:
    files = [{"path": "data/a.csv", "bytes": 4, "hash": sha(b"a,b\n")}]
    connected.json(
        "GET /api/datasets/d1",
        {
            "id": "d1",
            "title": "Sample",
            "access": "open",
            "currentVersion": 2,
            "prefix": "open",
            "manifest": manifest,
            "files": files,
        },
    )

    result = read.get_dataset(Session(), "d1")

    assert result["id"] == "d1"
    assert result["version"] == 2
    assert result["manifest"] == manifest
    assert result["files"] == files
    assert result["citation"] == citation(Manifest.model_validate(manifest))
    assert result["citation"]


def test_get_dataset_at_a_version_reads_that_version(
    connected: Any, manifest: dict[str, Any]
) -> None:
    connected.json(
        "GET /api/datasets/d1",
        {
            "id": "d1",
            "title": "Sample",
            "access": "open",
            "currentVersion": 2,
            "prefix": "open",
            "manifest": {},
            "files": [],
        },
    )
    connected.json(
        "GET /api/datasets/d1/versions/1",
        {"version": 1, "prefix": "open", "manifest": manifest, "files": [{"path": "x"}]},
    )

    result = read.get_dataset(Session(), "d1", version=1)

    assert result["version"] == 1
    assert result["manifest"] == manifest
    assert result["files"] == [{"path": "x"}]


def version(connected: Any, prefix: str, files: dict[str, bytes], hashes: bool = True) -> None:
    connected.json(
        "GET /api/datasets/d1/versions/3",
        {
            "version": 3,
            "prefix": prefix,
            "manifest": {},
            "files": [
                {"path": p, "bytes": len(b), **({"hash": sha(b)} if hashes else {})}
                for p, b in files.items()
            ],
        },
    )


def test_download_writes_open_files_from_data_and_checks_their_hashes(
    connected: Any, tmp_path: Path
) -> None:
    version(connected, "open", {"data/a.csv": b"a,b\n", "docs/my notes.txt": b"hi"})
    connected.raw("GET /data/d1/3/data/a.csv", b"a,b\n")
    connected.raw("GET /data/d1/3/docs/my notes.txt", b"hi")

    result = read.download(Session(), "d1", 3, ["data/a.csv", "docs/my notes.txt"], str(tmp_path))

    assert (tmp_path / "data" / "a.csv").read_bytes() == b"a,b\n"
    assert (tmp_path / "docs" / "my notes.txt").read_bytes() == b"hi"
    assert [w["path"] for w in result["written"]] == ["data/a.csv", "docs/my notes.txt"]
    assert all(w["checked"] for w in result["written"])
    assert result["failed"] == []


def test_download_fetches_restricted_files_through_the_link_route(
    connected: Any, tmp_path: Path, tokens: Tokens
) -> None:
    version(connected, "restricted", {"data/a.csv": b"secret\n"})
    connected.json(
        "GET /api/datasets/d1/versions/3/download", {"url": connected.url + "/signed/a.csv"}
    )
    connected.raw("GET /signed/a.csv", b"secret\n")

    result = read.download(Session(tokens=tokens), "d1", 3, ["data/a.csv"], str(tmp_path))

    assert (tmp_path / "data" / "a.csv").read_bytes() == b"secret\n"
    link = next(s for s in connected.seen if s.path.endswith("/download"))
    assert link.query == {"path": ["data/a.csv"]}
    assert link.headers["authorization"] == "id-token"
    assert result["written"][0]["checked"]


def test_download_of_a_restricted_file_signed_out_says_to_sign_in(
    connected: Any, tmp_path: Path
) -> None:
    version(connected, "restricted", {"data/a.csv": b"secret\n"})

    with pytest.raises(SignedOut, match="sign_in"):
        read.download(Session(), "d1", 3, ["data/a.csv"], str(tmp_path))


def test_download_keeps_no_file_whose_hash_doesnt_match(connected: Any, tmp_path: Path) -> None:
    version(connected, "open", {"data/a.csv": b"a,b\n"})
    connected.raw("GET /data/d1/3/data/a.csv", b"tampered\n")

    result = read.download(Session(), "d1", 3, ["data/a.csv"], str(tmp_path))

    assert not (tmp_path / "data" / "a.csv").exists()
    assert result["written"] == []
    assert result["failed"][0]["path"] == "data/a.csv"
    assert "hash" in result["failed"][0]["reason"]


def test_download_writes_a_file_with_no_recorded_hash_unchecked(
    connected: Any, tmp_path: Path
) -> None:
    version(connected, "open", {"data/a.csv": b"a,b\n"}, hashes=False)
    connected.raw("GET /data/d1/3/data/a.csv", b"a,b\n")

    result = read.download(Session(), "d1", 3, ["data/a.csv"], str(tmp_path))

    assert result["written"][0]["checked"] is False


@pytest.mark.parametrize("path", ["../escape.csv", "/etc/passwd", "data/../../x"])
def test_download_refuses_a_path_that_would_leave_the_folder(
    connected: Any, tmp_path: Path, path: str
) -> None:
    version(connected, "open", {path: b"x"})

    with pytest.raises(LocalError, match="outside"):
        read.download(Session(), "d1", 3, [path], str(tmp_path / "to"))

    assert not (tmp_path / "escape.csv").exists()


def test_download_refuses_a_path_the_version_doesnt_have(connected: Any, tmp_path: Path) -> None:
    version(connected, "open", {"data/a.csv": b"a"})

    with pytest.raises(Refused, match="data/b.csv"):
        read.download(Session(), "d1", 3, ["data/b.csv"], str(tmp_path))
