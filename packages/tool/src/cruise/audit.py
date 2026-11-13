"""cruise audit: diagnose every package under some folders, ranked by what needs fixing."""

import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from archive_contract.profile import Profile
from archive_contract.validate import BUILD, MANIFEST
from cruise.diagnose import Diagnosis, diagnose

SKIPPED = frozenset({BUILD, "node_modules"})
"""Folders never searched for packages."""


@dataclass(frozen=True)
class AuditRow:
    """One package's line in the audit."""

    path: Path
    diagnosis: Diagnosis

    def _count(self, severity: str) -> int:
        return sum(1 for f in self.diagnosis.findings if f.severity == severity)

    @property
    def errors(self) -> int:
        return self._count("error")

    @property
    def warnings(self) -> int:
        return self._count("warning")

    @property
    def notes(self) -> int:
        return self._count("note")

    @property
    def top_rule(self) -> str | None:
        """The rule that fired most; on a tie, the one that fired first."""
        counts = Counter(f.rule_id for f in self.diagnosis.findings)
        return counts.most_common(1)[0][0] if counts else None

    def rank(self) -> tuple[bool, int, int, str]:
        """Unreadable manifests first, then most errors, then lowest score, then path."""
        score = self.diagnosis.score
        return (score is not None, -self.errors, score.percent if score else 0, str(self.path))


def find_packages(folders: Sequence[Path]) -> list[Path]:
    """Every folder holding a `datapackage.json`, without entering `_build/` or
    `node_modules/` or following symlinks. A folder that doesn't exist is an error."""
    found: list[Path] = []
    for folder in folders:
        if not folder.is_dir():
            raise FileNotFoundError(f"no folder at {folder}")
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIPPED)
            if MANIFEST in filenames:
                found.append(Path(dirpath))
    return sorted(found)


def audit(
    folders: Sequence[Path], profiles: Sequence[Profile] = (), required: Sequence[str] = ()
) -> list[AuditRow]:
    rows = [AuditRow(path, diagnose(path, profiles, required)) for path in find_packages(folders)]
    return sorted(rows, key=AuditRow.rank)
