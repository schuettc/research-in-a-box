"""The change log: one `Change` per line of `changes.jsonl`."""

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field as PydanticField

from archive_contract._base import ArchiveModel
from archive_contract.findings import Evidence, Target

ActorKind = Literal["person", "tool", "agent"]

CHANGE_KINDS: tuple[str, ...] = ("rename", "retype", "recode", "fix-value")
"""The kinds of change known so far; `Change.kind` accepts others."""


class Actor(ArchiveModel):
    kind: ActorKind
    name: str


class Change(ArchiveModel):
    """One cleaning step: what changed, who made and accepted it, why, and the evidence."""

    id: str
    when: datetime
    made_by: Actor = PydanticField(alias="madeBy")
    accepted_by: Actor | None = PydanticField(default=None, alias="acceptedBy")
    kind: str
    target: Target
    before: Any = None
    after: Any = None
    reason: str
    evidence: Evidence | None = None


def read_changes(path: Path) -> list[Change]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [Change.model_validate_json(line) for line in lines if line.strip()]


def write_changes(path: Path, changes: Iterable[Change]) -> None:
    text = "".join(json.dumps(c.dump(), ensure_ascii=False) + "\n" for c in changes)
    path.write_text(text, encoding="utf-8")
