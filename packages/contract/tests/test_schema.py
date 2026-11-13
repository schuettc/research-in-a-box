import json
from pathlib import Path
from typing import Any

from archive_contract.schema import main, render


def written(tmp_path: Path) -> dict[str, Any]:
    out = tmp_path / "schema.json"
    main([str(out)])
    schema: dict[str, Any] = json.loads(out.read_text(encoding="utf-8"))
    return schema


def test_root_is_the_manifest(tmp_path: Path) -> None:
    schema = written(tmp_path)

    assert schema["title"] == "Manifest"
    assert "archive:rightsStatus" in schema["properties"]
    assert "$schema" in schema["properties"]


def test_other_records_are_under_defs(tmp_path: Path) -> None:
    defs = written(tmp_path)["$defs"]

    for name in ["Project", "Change", "Finding", "ArchiveConfig", "Resource", "Field"]:
        assert name in defs
    assert "archive:kind" in defs["Resource"]["properties"]
    assert "archive:sourceName" in defs["Field"]["properties"]


def test_every_ref_resolves(tmp_path: Path) -> None:
    schema = written(tmp_path)
    text = json.dumps(schema)
    refs = {part.split('"')[0] for part in text.split('"$ref": "#/$defs/')[1:]}

    assert refs
    assert refs <= set(schema["$defs"])


def test_render_is_stable() -> None:
    assert render() == render()
