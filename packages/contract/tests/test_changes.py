from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from archive_contract.changes import Change, read_changes, write_changes


def rename() -> dict[str, Any]:
    return {
        "id": "c1",
        "when": "2026-11-13T10:00:00Z",
        "madeBy": {"kind": "tool", "name": "cruise"},
        "acceptedBy": {"kind": "person", "name": "A. Researcher"},
        "kind": "rename",
        "target": {"resource": "logger", "field": "water_temp_c"},
        "before": "WTemp",
        "after": "water_temp_c",
        "reason": "Spell out the unit in the column name.",
        "evidence": {"values": ["WTemp"]},
    }


def test_change_reads_its_parts() -> None:
    change = Change.model_validate(rename())

    assert change.made_by.kind == "tool"
    assert change.accepted_by is not None and change.accepted_by.name == "A. Researcher"
    assert change.target.field == "water_temp_c"
    assert (change.before, change.after) == ("WTemp", "water_temp_c")


@pytest.mark.parametrize("kind", ["person", "tool", "agent"])
def test_changes_are_made_by_a_person_tool_or_agent(kind: str) -> None:
    raw = rename() | {"madeBy": {"kind": kind, "name": "x"}}

    assert Change.model_validate(raw).made_by.kind == kind


def test_other_makers_are_refused() -> None:
    with pytest.raises(ValidationError):
        Change.model_validate(rename() | {"madeBy": {"kind": "robot", "name": "x"}})


def test_changes_round_trip_through_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "changes.jsonl"
    changes = [Change.model_validate(rename()), Change.model_validate(rename() | {"id": "c2"})]

    write_changes(path, changes)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert read_changes(path) == changes


def test_reading_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "changes.jsonl"
    write_changes(path, [Change.model_validate(rename())])
    path.write_text(path.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")

    assert len(read_changes(path)) == 1


def test_explicit_null_before_is_kept_and_unset_stays_absent(tmp_path: Path) -> None:
    raw = rename() | {"kind": "fix-value", "before": None, "after": 12.5}
    del raw["evidence"]
    unset = rename()
    del unset["before"], unset["after"]

    dumped = Change.model_validate(raw).dump()
    path = tmp_path / "changes.jsonl"
    write_changes(path, [Change.model_validate(raw)])

    assert "before" in dumped and dumped["before"] is None
    assert '"before": null' in path.read_text(encoding="utf-8")
    assert read_changes(path)[0].dump()["before"] is None
    assert "before" not in Change.model_validate(unset).dump()
    assert "after" not in Change.model_validate(unset).dump()
