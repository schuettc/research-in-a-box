import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from archive_agent import local
from archive_agent.errors import LocalError
from archive_contract.exports.readme import render_readme
from archive_contract.manifest import Manifest

SAMPLE = Path(__file__).parents[3] / "examples" / "sample-package"
WRITTEN = ("datapackage.json", "README.md", "checksums.sha256")


@pytest.fixture
def package(tmp_path: Path) -> Path:
    root = tmp_path / "sample"
    shutil.copytree(SAMPLE, root)
    return root


def snapshot(root: Path) -> dict[str, bytes]:
    return {name: (root / name).read_bytes() for name in WRITTEN}


def rule_ids(answer: dict[str, Any]) -> list[str]:
    return [f["ruleId"] for f in answer["findings"]]


def test_diagnose_answers_the_json_cruise_prints_with_the_verdict(package: Path) -> None:
    answer = local.diagnose(str(package))

    assert set(answer) == {"validation", "quality", "findings", "verdict"}
    assert answer["validation"]["valid"] is True
    assert answer["quality"]["score"] == 95
    assert "field.description-missing" in rule_ids(answer)
    assert answer["verdict"] == "publishable, with 4 warnings"


def test_diagnose_refuses_a_folder_that_isnt_there(tmp_path: Path) -> None:
    with pytest.raises(LocalError, match="no folder"):
        local.diagnose(str(tmp_path / "missing"))


def test_edit_manifest_applies_a_column_description_and_a_license(package: Path) -> None:
    license_ = {"name": "CC0-1.0", "path": "https://creativecommons.org/publicdomain/zero/1.0/"}
    edits: list[dict[str, Any]] = [
        {
            "target": "description",
            "resource": "logger",
            "column": "battery_v",
            "value": "Logger battery voltage at each reading.",
        },
        {"target": "licenses", "value": [license_]},
    ]

    answer = local.edit_manifest(str(package), edits)

    document = json.loads((package / "datapackage.json").read_text())
    battery = next(
        f
        for r in document["resources"]
        if r["name"] == "logger"
        for f in r["schema"]["fields"]
        if f["name"] == "battery_v"
    )
    assert battery["description"] == "Logger battery voltage at each reading."
    assert document["licenses"] == [license_]
    manifest = Manifest.model_validate(document)
    assert (package / "README.md").read_text() == render_readme(manifest)
    assert "Logger battery voltage at each reading." in (package / "README.md").read_text()
    assert answer["written"] == list(WRITTEN)
    assert answer["applied"] == 2

    after = local.diagnose(str(package))
    assert after["validation"]["valid"] is True
    assert not [r for r in rule_ids(after) if r.startswith("structure.")]
    assert "field.description-missing" not in rule_ids(after)
    assert not [p for p in package.iterdir() if p.name.startswith(".")]


def test_edit_manifest_keeps_every_other_byte_of_the_manifest_meaning(package: Path) -> None:
    before = json.loads((package / "datapackage.json").read_text())

    local.edit_manifest(str(package), [{"target": "title", "value": "A new title"}])

    after = json.loads((package / "datapackage.json").read_text())
    assert after == {**before, "title": "A new title"}


@pytest.mark.parametrize(
    "bad",
    [
        {"target": "resources", "value": []},
        {"target": "name", "value": "renamed"},
        {"target": "licenses", "value": [{"title": "No name or path"}]},
        {"target": "type", "resource": "logger", "column": "battery_v", "value": "string"},
        {"target": "description", "resource": "logger", "column": "nope", "value": "x"},
        {"target": "description", "resource": "nope", "column": "battery_v", "value": "x"},
        {"target": "archive:temporalCoverage", "value": {"start": "not a date"}},
    ],
)
def test_one_invalid_edit_leaves_all_three_files_byte_for_byte(
    package: Path, bad: dict[str, Any]
) -> None:
    before = snapshot(package)
    edits = [{"target": "title", "value": "Changed"}, bad]

    with pytest.raises(LocalError, match="edit 2") as raised:
        local.edit_manifest(str(package), edits)

    assert "edit 1" not in str(raised.value)
    assert snapshot(package) == before


def test_every_failing_edit_is_named(package: Path) -> None:
    edits: list[dict[str, Any]] = [
        {"target": "resources", "value": []},
        {"target": "title", "value": "fine"},
        {"target": "licenses", "value": [{}]},
    ]

    with pytest.raises(LocalError) as raised:
        local.edit_manifest(str(package), edits)

    message = str(raised.value)
    assert "edit 1" in message and "edit 3" in message and "edit 2" not in message
    assert "nothing was written" in message.lower()


def test_edit_manifest_refuses_a_folder_with_no_manifest(tmp_path: Path) -> None:
    with pytest.raises(LocalError, match="datapackage.json"):
        local.edit_manifest(str(tmp_path), [{"target": "title", "value": "x"}])
