"""cruise diagnose: the structure check, then every quality rule that applies, then the score."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from archive_contract import __version__ as contract_version
from archive_contract.findings import Finding
from archive_contract.manifest import Manifest, QualityVerdict, ValidationVerdict
from archive_contract.profile import Profile
from archive_contract.resources import Resource
from archive_contract.validate import MANIFEST, validate_package
from cruise.rules import REGISTRY, Context, Registry, RuleResult, required_fields
from cruise.score import Score, completeness


@dataclass(frozen=True)
class Diagnosis:
    """What diagnose found: structure findings first, then the rules' findings.

    `quality` and `score` are None when the manifest can't be read and no rule ran.
    """

    path: Path
    structure: list[Finding]
    findings: list[Finding]
    results: list[RuleResult]
    validation: ValidationVerdict
    quality: QualityVerdict | None
    score: Score | None

    @property
    def blocking(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")


def _resource_paths(resource: Resource) -> set[str]:
    paths = {m.path for m in resource.files or []}
    if isinstance(resource.path, str):
        paths.add(resource.path)
    elif isinstance(resource.path, list):
        paths.update(resource.path)
    return paths


def _failed_resources(manifest: Manifest, structure: list[Finding]) -> frozenset[str]:
    """The resources a structure finding names, or whose files one names."""
    names = {f.target.resource for f in structure if f.target and f.target.resource}
    paths = {f.target.path for f in structure if f.target and f.target.path}
    return frozenset(
        r.name for r in manifest.resources if r.name in names or _resource_paths(r) & paths
    )


def _count(findings: list[Finding], severity: str) -> int:
    return sum(1 for f in findings if f.severity == severity)


def diagnose(
    path: Path,
    profiles: Sequence[Profile] = (),
    required: Sequence[str] = (),
    *,
    registry: Registry = REGISTRY,
    now: datetime | None = None,
) -> Diagnosis:
    """Diagnose the package at `path` under the given profiles and extra required fields."""
    rules = registry.select(profiles)
    when = now or datetime.now(UTC)
    structure = validate_package(path)
    validation = ValidationVerdict(
        valid=not structure, contract_version=contract_version, checked_at=when
    )
    if any(f.target is not None and f.target.path == MANIFEST for f in structure):
        return Diagnosis(path, structure, structure, [], validation, None, None)
    manifest = Manifest.model_validate(json.loads((path / MANIFEST).read_text(encoding="utf-8")))
    ctx = Context.for_package(
        path,
        manifest,
        required=required_fields(profiles, required),
        skip=_failed_resources(manifest, structure),
    )
    results = [r.run(ctx) for r in rules]
    findings = structure + [f for result in results for f in result.findings]
    score = completeness(results)
    quality = QualityVerdict(
        errors=_count(findings, "error"),
        warnings=_count(findings, "warning"),
        notes=_count(findings, "note"),
        audited_at=when,
        score=score.percent,
        find=score.parts["find"],
        understand=score.parts["understand"],
        trust=score.parts["trust"],
    )
    return Diagnosis(path, structure, findings, results, validation, quality, score)
